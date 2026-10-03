"""Session lifecycle state machine.

CALL_STARTED → CREATE_SESSION → IDENTIFY_AGENT → INITIALIZE_CONTEXT →
VOICE_CONVERSATION ⇄ SKILL_ROUTING ⇄ SKILL_ACTIVE → CALL_ENDED →
FINALIZE_LOG → SESSION_CLOSED
"""

from __future__ import annotations

from app.models.session import ALLOWED_TRANSITIONS, Session, SessionState, new_session_id
from app.security.exceptions import AccessDeniedError


class LifecycleError(RuntimeError):
    """Illegal state transition."""


class SessionLifecycle:
    """Validates and applies session state transitions."""

    def advance(self, session: Session, target: SessionState) -> SessionState:
        allowed = ALLOWED_TRANSITIONS.get(session.state, set())
        if target not in allowed:
            raise LifecycleError(
                f"Illegal transition {session.state.value} -> {target.value}"
            )
        session.state = target
        return session.state

    def open(self, agent_id: str, caller_id: str = "redacted") -> Session:
        """Run the first four stages of the lifecycle in order."""
        session = Session(session_id=new_session_id(), agent_id=agent_id, caller_id=caller_id)
        for state in (
            SessionState.CREATE_SESSION,
            SessionState.IDENTIFY_AGENT,
            SessionState.INITIALIZE_CONTEXT,
            SessionState.VOICE_CONVERSATION,
        ):
            self.advance(session, state)
        return session

    def begin_routing(self, session: Session) -> None:
        if session.state in (SessionState.VOICE_CONVERSATION, SessionState.SKILL_ACTIVE):
            self.advance(session, SessionState.SKILL_ROUTING)

    def skill_activated(self, session: Session) -> None:
        if session.state == SessionState.SKILL_ROUTING:
            self.advance(session, SessionState.SKILL_ACTIVE)

    def resume_conversation(self, session: Session) -> None:
        if session.state == SessionState.SKILL_ROUTING:
            self.advance(session, SessionState.VOICE_CONVERSATION)

    def end_call(self, session: Session) -> None:
        if session.state in (SessionState.CALL_ENDED, SessionState.SESSION_CLOSED):
            return
        self.advance(session, SessionState.CALL_ENDED)
        session.ended_at = session.ended_at or __import__("time").time()
        session.status = "completed"
        self.advance(session, SessionState.FINALIZE_LOG)
        self.advance(session, SessionState.SESSION_CLOSED)

    def require_active(self, session: Session) -> None:
        if session.state == SessionState.SESSION_CLOSED:
            raise AccessDeniedError("Session is closed")
