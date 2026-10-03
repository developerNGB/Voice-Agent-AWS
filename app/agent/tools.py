"""Business tools with mandatory authorization.

Every tool validates: agent, session, skill ownership (when relevant) and
input shape before doing anything.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.models.call import Lead
from app.models.session import Session
from app.security.authorization import Authorizer
from app.security.exceptions import AccessDeniedError
from app.skills.registry import SkillRegistry


@dataclass
class ToolResult:
    ok: bool
    data: dict = field(default_factory=dict)
    error: str = ""


class ToolBox:
    """The agent's controlled tool surface."""

    def __init__(self, registry: SkillRegistry, authorizer: Authorizer,
                 on_save_call=None):
        self.registry = registry
        self.authorizer = authorizer
        self._on_save_call = on_save_call
        self.leads: list[Lead] = []
        self.viewings: list[dict] = []

    # -- helpers -------------------------------------------------------------

    def _check(self, session: Session, skill_id: str = "") -> set[str]:
        self.authorizer.authorize_session(session.agent_id, session.agent_id,
                                          session_closed=session.closed)
        owned = set(self.registry.list_ids(session.agent_id))
        if skill_id:
            self.authorizer.authorize_skill(session.agent_id, skill_id, owned)
        return owned

    def _log_tool(self, session: Session, name: str, args: dict, result: ToolResult) -> None:
        session.tool_calls.append({
            "tool": name,
            "args": args,
            "ok": result.ok,
            "error": result.error,
            "at": time.time(),
        })

    # -- tools ---------------------------------------------------------------

    def search_skills(self, session: Session, query: str) -> ToolResult:
        """List header-index matches for this agent only."""
        try:
            self._check(session)
        except AccessDeniedError as exc:
            result = ToolResult(False, error=str(exc))
            self._log_tool(session, "search_skills", {"query": query}, result)
            return result
        from app.router.matcher import candidate_search
        from app.router.scorer import score_all

        index = self.registry.header_index(session.agent_id)
        scored = score_all(candidate_search(index, query), query)
        result = ToolResult(True, {"candidates": scored[:5]})
        self._log_tool(session, "search_skills", {"query": query}, result)
        return result

    def load_skill(self, session: Session, skill_id: str) -> ToolResult:
        try:
            self._check(session, skill_id)
            skill = self.registry.get(session.agent_id, skill_id)
        except AccessDeniedError as exc:
            result = ToolResult(False, error=str(exc))
            self._log_tool(session, "load_skill", {"skill_id": skill_id}, result)
            return result
        result = ToolResult(True, {"skill_id": skill.skill_id, "name": skill.name})
        self._log_tool(session, "load_skill", {"skill_id": skill_id}, result)
        return result

    def switch_skill(self, session: Session, skill_id: str) -> ToolResult:
        try:
            self._check(session, skill_id)
        except AccessDeniedError as exc:
            result = ToolResult(False, error=str(exc))
            self._log_tool(session, "switch_skill", {"skill_id": skill_id}, result)
            return result
        previous = session.active_skill_id
        session.active_skill_id = skill_id
        if skill_id not in session.skills_used:
            session.skills_used.append(skill_id)
        result = ToolResult(True, {"from": previous, "to": skill_id})
        self._log_tool(session, "switch_skill", {"skill_id": skill_id}, result)
        return result

    def create_lead(self, session: Session, **fields) -> ToolResult:
        try:
            self._check(session)
        except AccessDeniedError as exc:
            return ToolResult(False, error=str(exc))
        lead = Lead(session_id=session.session_id, agent_id=session.agent_id, **fields)
        if not (lead.name or lead.phone or lead.email):
            return ToolResult(False, error="lead needs at least one contact field")
        self.leads.append(lead)
        result = ToolResult(True, {"lead": lead.to_dict()})
        self._log_tool(session, "create_lead", {"name": lead.name}, result)
        return result

    def schedule_viewing(self, session: Session, when: str) -> ToolResult:
        try:
            self._check(session, session.active_skill_id) if session.active_skill_id else self._check(session)
        except AccessDeniedError as exc:
            result = ToolResult(False, error=str(exc))
            self._log_tool(session, "schedule_viewing", {"when": when}, result)
            return result
        if not when.strip():
            return ToolResult(False, error="missing time")
        record = {
            "session_id": session.session_id,
            "agent_id": session.agent_id,
            "skill_id": session.active_skill_id,
            "when": when,
            "at": time.time(),
        }
        self.viewings.append(record)
        result = ToolResult(True, record)
        self._log_tool(session, "schedule_viewing", {"when": when}, result)
        return result

    def save_call(self, session: Session) -> ToolResult:
        try:
            self._check(session)
        except AccessDeniedError as exc:
            return ToolResult(False, error=str(exc))
        if self._on_save_call:
            self._on_save_call(session)
        result = ToolResult(True, {"session_id": session.session_id})
        self._log_tool(session, "save_call", {}, result)
        return result

    def end_call(self, session: Session) -> ToolResult:
        try:
            self._check(session)
        except AccessDeniedError as exc:
            return ToolResult(False, error=str(exc))
        result = ToolResult(True, {"session_id": session.session_id})
        self._log_tool(session, "end_call", {}, result)
        return result
