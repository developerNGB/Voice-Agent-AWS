"""The Skill Router — the heart of the dynamic skill system.

Flow::

    caller request → extract → candidate search → score → confidence check
        → activate | clarify | keep (locked skill) | none

The router only ever sees header metadata for candidate selection; full skill
content is loaded by the agent after a skill is activated.
"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.models.call import RoutingDecision
from app.models.session import Session
from app.router.matcher import candidate_search, normalize_spoken_numbers
from app.router.scorer import score_all
from app.router.validator import validate_activation, margin_ok
from app.skills.registry import SkillRegistry


class SkillRouter:
    """Selects, locks and switches the active skill for a session."""

    def __init__(self, registry: SkillRegistry, settings: Settings | None = None):
        self.registry = registry
        self.settings = settings or get_settings()

    # -- public API ---------------------------------------------------------

    def extract_request(self, text: str) -> str:
        """Normalise the utterance for routing (kept simple and predictable).

        Spoken numbers become digits ("one twenty three" → "123") so STT
        output matches header keywords the way typed input does.
        """
        return normalize_spoken_numbers((text or "").strip())

    def load_metadata(self, agent_id: str) -> dict:
        """The header index — searchable metadata only, never full content."""
        return self.registry.header_index(agent_id)

    def candidate_search(self, agent_id: str, query: str) -> list:
        index = self.load_metadata(agent_id)
        return candidate_search(index, query)

    def score_candidates(self, query: str, candidates: list) -> list[tuple[str, float]]:
        return score_all(candidates, query)

    def route(self, agent_id: str, text: str, session: Session | None = None) -> RoutingDecision:
        """Route one utterance to a skill (or decide to keep/ask/ignore)."""
        query = self.extract_request(text)
        index = self.load_metadata(agent_id)
        if not index:
            return RoutingDecision(status="none", reason="no skills registered for agent")

        candidates = candidate_search(index, query)
        scored = self.score_candidates(query, candidates)
        if not scored:
            return self._no_match(session)

        top_id, top_score = scored[0]
        s = self.settings

        # Confident match → activate (possibly switching away from the lock)
        if top_score >= s.skill_activate_threshold and margin_ok(scored):
            validate_activation(agent_id, top_id, index)
            return RoutingDecision(
                status="activate",
                skill_id=top_id,
                candidates=scored[:3],
                reason=f"confidence {top_score:.2f} >= {s.skill_activate_threshold}",
            )

        # Ambiguous → ask the caller to choose
        if top_score >= s.skill_clarify_threshold:
            plausible = [(sid, sc) for sid, sc in scored if sc >= s.skill_clarify_threshold][:3]
            return RoutingDecision(
                status="clarify",
                candidates=plausible,
                reason=f"ambiguous match (top {top_score:.2f})",
            )

        return self._no_match(session, scored)

    # -- helpers ------------------------------------------------------------

    def confidence_check(self, scored: list[tuple[str, float]], top_score: float) -> bool:
        return top_score >= self.settings.skill_activate_threshold and margin_ok(scored)

    def ask_clarification(self, scored: list[tuple[str, float]]) -> list[str]:
        return [sid for sid, sc in scored if sc >= self.settings.skill_clarify_threshold][:3]

    def activate_skill(self, agent_id: str, skill_id: str, session: Session) -> str:
        """Set ACTIVE_SKILL for the session (replaces any previous skill)."""
        index = self.load_metadata(agent_id)
        validate_activation(agent_id, skill_id, index)
        session.active_skill_id = skill_id
        session.pending_candidates = []
        if skill_id not in session.skills_used:
            session.skills_used.append(skill_id)
        return skill_id

    def _no_match(self, session: Session | None, scored: list[tuple[str, float]] | None = None
                  ) -> RoutingDecision:
        """Nothing matched: keep the locked skill if there is one, else none."""
        if session is not None and session.active_skill_id:
            return RoutingDecision(
                status="keep",
                skill_id=session.active_skill_id,
                candidates=(scored or [])[:3],
                reason="no new match; active skill remains locked",
            )
        return RoutingDecision(status="none", reason="no candidate above threshold")
