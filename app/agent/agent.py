"""The Voice Agent — one session per call, one active skill per session.

Turn flow: guardrail → profile extraction → skill routing → prompt build →
LLM (with retry/fallback) → transcript + logs.
"""

from __future__ import annotations

import asyncio
import re
import time

from app.agent_configs import agent_config_for
from app.agent.context import ContextManager, context_metadata
from app.agent.lifecycle import SessionLifecycle
from app.agent.prompts import (
    build_session_context,
    build_system_prompt,
    greeting_for,
)
from app.agent.tools import ToolBox
from app.config import Settings, get_settings
from app.llm.base import LLMMessage, LLMProvider, LLMRequest
from app.llm.factory import build_llm
from app.llm.mock import NOT_IN_LISTINGS
from app.models.call import AgentTurn, CallRecord, RoutingDecision
from app.models.session import Session, SessionState
from app.router.skill_router import SkillRouter
from app.security.authorization import Authorizer
from app.security.exceptions import AccessDeniedError
from app.security.sanitization import (
    INJECTION_RESPONSE,
    contains_injection,
    hash_caller_id,
)
from app.skills.loader import build_skill_store
from app.skills.registry import SkillRegistry
from app.storage.logs import StructuredLogger

GOODBYE_RE = re.compile(r"\b(bye|goodbye|that's all|that is all|no thanks|have a good (day|evening))\b",
                        re.IGNORECASE)
PROPERTY_MENTION_RE = re.compile(
    r"(?i)\b\d{1,5}\s+\w+\s*(street|st|avenue|ave|road|rd|lane|drive|court|"
    r"boulevard|blvd|place|way)\b|\bproperty\s*#?\d+\b"
)
LLM_FAILURE_RESPONSE = (
    "I'm having trouble accessing that information right now. "
    "I don't want to give you incorrect information. "
    "Could you give me a moment, or would you like me to connect you with an agent?"
)


class VoiceAgent:
    """Orchestrates sessions, routing, knowledge and the LLM."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        registry: SkillRegistry | None = None,
        router: SkillRouter | None = None,
        llm: LLMProvider | None = None,
        logger: StructuredLogger | None = None,
        authorizer: Authorizer | None = None,
        tools: ToolBox | None = None,
        lifecycle: SessionLifecycle | None = None,
        agent_config: dict | None = None,
    ):
        self.settings = settings or get_settings()
        store = build_skill_store(self.settings)
        self.registry = registry or SkillRegistry(store)
        self.router = router or SkillRouter(self.registry, self.settings)
        self.llm = llm or build_llm(self.settings)
        self.logger = logger or StructuredLogger(self.settings.log_dir)
        self.authorizer = authorizer or Authorizer()
        self.lifecycle = lifecycle or SessionLifecycle()
        self.context = ContextManager()
        self.tools = tools or ToolBox(self.registry, self.authorizer,
                                      on_save_call=lambda s: self.logger.finalize(s))
        self.agent_config = agent_config or agent_config_for(self.settings.agent_id)

        self.sessions: dict[str, Session] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    # -- session lifecycle ---------------------------------------------------

    async def _lock_for(self, session_id: str) -> asyncio.Lock:
        async with self._locks_guard:
            return self._locks.setdefault(session_id, asyncio.Lock())

    def start_session(self, agent_id: str | None = None,
                      caller_id: str = "redacted") -> Session:
        """Create and open a session (CALL_STARTED → VOICE_CONVERSATION)."""
        agent_id = agent_id or self.settings.agent_id
        self.authorizer.authorize_agent(agent_id)
        hashed = caller_id if caller_id == "redacted" else hash_caller_id(caller_id)
        session = self.lifecycle.open(agent_id, hashed)
        self.sessions[session.session_id] = session
        self.logger.event("session_started", session_id=session.session_id,
                          agent_id=agent_id, caller_id=hashed)
        return session

    def greeting(self, session: Session | None = None) -> str:
        cfg = self.agent_config if session is None else agent_config_for(session.agent_id)
        return greeting_for(cfg)

    def get_session(self, session_id: str) -> Session:
        session = self.sessions.get(session_id)
        if session is None:
            raise AccessDeniedError(f"Unknown session {session_id!r}")
        return session

    async def end_session(self, session_id: str) -> CallRecord:
        """CALL_ENDED → FINALIZE_LOG → SESSION_CLOSED."""
        lock = await self._lock_for(session_id)
        async with lock:
            session = self.get_session(session_id)
            if session.state != SessionState.SESSION_CLOSED:
                self.lifecycle.end_call(session)
                record = self.logger.finalize(session)
                self.logger.event("session_closed", session_id=session_id,
                                  agent_id=session.agent_id)
                return record
            return self.logger.build_record(session)

    # -- the turn loop -------------------------------------------------------

    async def handle_turn(self, session_id: str, text: str) -> AgentTurn:
        """Process one caller utterance and return the agent's reply."""
        lock = await self._lock_for(session_id)
        async with lock:
            return await self._turn_locked(session_id, text)

    async def _turn_locked(self, session_id: str, text: str) -> AgentTurn:
        session = self.get_session(session_id)
        self.lifecycle.require_active(session)
        text = (text or "").strip()
        if not text:
            return AgentTurn(reply="", session_id=session_id,
                             active_skill_id=session.active_skill_id)

        started = time.monotonic()
        events: list[dict] = []

        # 1. Guardrail: prompt injection is refused deterministically
        if contains_injection(text):
            session.security_events.append({
                "type": "prompt_injection", "at": time.time(),
                "snippet": text[:120],
            })
            self.logger.event("security_event", kind="prompt_injection",
                              session_id=session_id, agent_id=session.agent_id)
            reply = INJECTION_RESPONSE
            route_status = "denied"
            clarify: list[str] = []
        else:
            # 2. Extract caller facts (name, budget, bedrooms, intent…)
            changed = self.context.extract(session, text)
            self._maybe_create_lead(session, changed)

            # 3. Skill routing
            decision = self._route(session, text)
            route_status = decision.status
            clarify = []

            if decision.status == "clarify":
                session.pending_candidates = [sid for sid, _ in decision.candidates]
                reply = self._clarify_reply(session, session.pending_candidates)
            elif self._is_unknown_property(text, decision):
                # A specific property was named that we do not carry at all
                reply = NOT_IN_LISTINGS
            else:
                reply = await self._generate(session, text, events)

        session.turn_count += 1
        session.history.append(session_history_turn("caller", text,
                                                    session.active_skill_id))
        session.history.append(session_history_turn(
            "agent", reply, session.active_skill_id,
            latency_ms=(time.monotonic() - started) * 1000.0,
        ))

        end_call = bool(GOODBYE_RE.search(text))
        return AgentTurn(
            reply=reply,
            session_id=session_id,
            route_status=route_status,
            active_skill_id=session.active_skill_id,
            clarify_candidates=clarify,
            events=events,
            latency_ms=(time.monotonic() - started) * 1000.0,
            end_call=end_call,
        )

    # -- steps ---------------------------------------------------------------

    def _route(self, session: Session, text: str) -> RoutingDecision:
        self.lifecycle.begin_routing(session)
        decision = self.router.route(session.agent_id, text, session)

        event = {
            "status": decision.status,
            "skill_id": decision.skill_id,
            "top_score": decision.candidates[0][1] if decision.candidates else 0.0,
            "candidates": decision.candidates,
            "reason": decision.reason,
            "at": time.time(),
        }
        session.routing_events.append(event)
        self.logger.event("routing", session_id=session.session_id,
                          agent_id=session.agent_id, **{k: v for k, v in event.items()
                                                        if k != "at"})

        if decision.status == "activate":
            previous = session.active_skill_id
            self.router.activate_skill(session.agent_id, decision.skill_id, session)
            self.lifecycle.skill_activated(session)
            if previous and previous != decision.skill_id:
                self.logger.event("skill_switch", session_id=session.session_id,
                                  from_skill=previous, to_skill=decision.skill_id)
        else:
            self.lifecycle.resume_conversation(session)
        return decision

    def _is_unknown_property(self, text: str, decision: RoutingDecision) -> bool:
        """True when a concrete address was named but nothing matched it."""
        if decision.status not in ("keep", "none"):
            return False
        if not PROPERTY_MENTION_RE.search(text):
            return False
        top = decision.candidates[0][1] if decision.candidates else 0.0
        return top < self.settings.skill_clarify_threshold

    def _clarify_reply(self, session: Session, skill_ids: list[str]) -> str:
        names: list[str] = []
        for skill_id in skill_ids:
            try:
                names.append(self.registry.get(session.agent_id, skill_id).name)
            except Exception:  # noqa: BLE001 - never fail a clarification on one bad file
                continue
        if not names:
            return "Could you tell me the full address of the property you mean?"
        if len(names) == 1:
            return f"Do you mean {names[0]}?"
        return "Did you mean " + " or ".join(names[:-1]) + f" or {names[-1]}?"

    async def _generate(self, session: Session, text: str, events: list[dict]) -> str:
        system = build_system_prompt(agent_config_for(session.agent_id))
        context = build_session_context(session, agent_config_for(session.agent_id))
        skill_block = ""
        if session.active_skill_id:
            skill_block = self._active_skill_block(session)

        prompt_context = context + ("\n\n" + skill_block if skill_block else "")
        messages = [
            LLMMessage(role=("assistant" if t.speaker == "agent" else "user"), content=t.text)
            for t in session.history[-6:]
        ]
        messages.append(LLMMessage(role="user", content=text))

        request = LLMRequest(
            system=system,
            messages=messages,
            context=prompt_context,
            metadata=context_metadata(session),
            timeout=self.settings.llm_timeout_seconds,
        )
        try:
            response = await self.llm.generate(request)
            reply = (response.text or "").strip()
            if not reply:
                raise RuntimeError("empty LLM response")
            events.append({"type": "llm", "provider": response.provider,
                           "model": response.model, "latency_ms": response.latency_ms})
            return reply
        except Exception as exc:  # noqa: BLE001 - degrade gracefully, never leak traces
            session.errors.append(f"llm_failure: {exc}")
            self.logger.error(f"llm_failure session={session.session_id}: {exc}")
            return LLM_FAILURE_RESPONSE

    def _active_skill_block(self, session: Session) -> str:
        try:
            skill = self.registry.get(session.agent_id, session.active_skill_id)
            return skill.as_context_block()
        except AccessDeniedError as exc:
            # A skill outside the namespace must never reach the prompt
            session.security_events.append({
                "type": "skill_access_denied", "at": time.time(), "reason": str(exc),
            })
            self.logger.event("security_event", kind="skill_access_denied",
                              session_id=session.session_id)
            session.active_skill_id = ""
            return ""
        except Exception as exc:  # noqa: BLE001 - missing file etc.
            session.errors.append(f"skill_load_failure: {exc}")
            return ""

    def _maybe_create_lead(self, session: Session, changed: list[str]) -> None:
        profile = session.profile
        if session.metadata.get("lead_created"):
            return
        if not profile.name and not profile.phone:
            return
        if not (set(changed) & {"name", "phone", "email", "budget", "intent", "bedrooms"}):
            return
        result = self.tools.create_lead(
            session,
            name=profile.name,
            phone=profile.phone,
            email=profile.email,
            budget=profile.budget,
            bedrooms=profile.bedrooms,
            intent=profile.intent,
            timeline=profile.timeline,
            property_interest=session.active_skill_id,
        )
        if result.ok:
            session.metadata["lead_created"] = True


def session_history_turn(speaker: str, text: str, skill_id: str = "",
                         latency_ms: float = 0.0):
    from app.models.session import Turn

    return Turn(speaker=speaker, text=text, skill_id=skill_id, latency_ms=latency_ms)
