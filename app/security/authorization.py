"""Layer 2 + Layer 4/5 authorization: who may do what, in which session.

Tools and skill loads check: known agent, active session, skill ownership.
"""

from __future__ import annotations

from app.security.exceptions import AccessDeniedError
from app.security.isolation import validate_agent_id, validate_skill_id


class Authorizer:
    """Central authorization checks used by tools and the router."""

    def __init__(self, known_agents: set[str] | None = None):
        self.known_agents = set(known_agents) if known_agents else None

    def authorize_agent(self, agent_id: str) -> str:
        validate_agent_id(agent_id)
        if self.known_agents is not None and agent_id not in self.known_agents:
            raise AccessDeniedError(f"Unknown agent {agent_id!r}")
        return agent_id

    def authorize_session(self, agent_id: str, session_agent_id: str, session_closed: bool = False) -> None:
        self.authorize_agent(agent_id)
        if session_agent_id != agent_id:
            raise AccessDeniedError("Session does not belong to this agent")
        if session_closed:
            raise AccessDeniedError("Session is closed")

    def authorize_skill(self, agent_id: str, skill_id: str, owned_skill_ids: set[str] | None = None) -> str:
        """A skill must belong to *this* agent's namespace."""
        self.authorize_agent(agent_id)
        validate_skill_id(skill_id)
        if owned_skill_ids is not None and skill_id not in owned_skill_ids:
            raise AccessDeniedError(
                f"Skill {skill_id!r} is not owned by agent {agent_id!r}"
            )
        return skill_id


def deny(reason: str) -> AccessDeniedError:
    """Build a denial (helper so callers never forget the ACCESS_DENIED prefix)."""
    return AccessDeniedError(reason)
