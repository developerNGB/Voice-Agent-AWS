"""Session domain models and lifecycle states."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SessionState(str, Enum):
    CALL_STARTED = "CALL_STARTED"
    CREATE_SESSION = "CREATE_SESSION"
    IDENTIFY_AGENT = "IDENTIFY_AGENT"
    INITIALIZE_CONTEXT = "INITIALIZE_CONTEXT"
    VOICE_CONVERSATION = "VOICE_CONVERSATION"
    SKILL_ROUTING = "SKILL_ROUTING"
    SKILL_ACTIVE = "SKILL_ACTIVE"
    CALL_ENDED = "CALL_ENDED"
    FINALIZE_LOG = "FINALIZE_LOG"
    SESSION_CLOSED = "SESSION_CLOSED"


ALLOWED_TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.CALL_STARTED: {SessionState.CREATE_SESSION},
    SessionState.CREATE_SESSION: {SessionState.IDENTIFY_AGENT},
    SessionState.IDENTIFY_AGENT: {SessionState.INITIALIZE_CONTEXT},
    SessionState.INITIALIZE_CONTEXT: {SessionState.VOICE_CONVERSATION},
    SessionState.VOICE_CONVERSATION: {
        SessionState.SKILL_ROUTING,
        SessionState.CALL_ENDED,
    },
    SessionState.SKILL_ROUTING: {
        SessionState.SKILL_ACTIVE,
        SessionState.VOICE_CONVERSATION,
    },
    SessionState.SKILL_ACTIVE: {
        SessionState.SKILL_ROUTING,   # topic change re-routes
        SessionState.VOICE_CONVERSATION,
        SessionState.CALL_ENDED,
    },
    SessionState.CALL_ENDED: {SessionState.FINALIZE_LOG},
    SessionState.FINALIZE_LOG: {SessionState.SESSION_CLOSED},
    SessionState.SESSION_CLOSED: set(),
}


def new_session_id() -> str:
    """Sortable-ish unique session id (ULID-like)."""
    return f"{int(time.time() * 1000):012x}{uuid.uuid4().hex[:16]}"


@dataclass
class Turn:
    """One conversational turn."""

    speaker: str                      # caller | agent
    text: str
    at: float = field(default_factory=time.time)
    skill_id: str = ""
    latency_ms: float = 0.0


@dataclass
class CallerProfile:
    """PII-minimised facts captured during the call."""

    name: str = ""
    phone: str = ""
    email: str = ""
    budget: str = ""
    bedrooms: str = ""
    intent: str = ""                  # buying | selling | viewing | inquiry
    timeline: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "budget": self.budget,
            "bedrooms": self.bedrooms,
            "intent": self.intent,
            "timeline": self.timeline,
        }


@dataclass
class Session:
    """In-memory conversation state. One per call; discarded at call end."""

    session_id: str
    agent_id: str
    caller_id: str = "redacted"        # hashed/redacted caller identifier
    state: SessionState = SessionState.CALL_STARTED
    active_skill_id: str = ""
    pending_candidates: list[str] = field(default_factory=list)
    profile: CallerProfile = field(default_factory=CallerProfile)
    history: list[Turn] = field(default_factory=list)
    skills_used: list[str] = field(default_factory=list)
    routing_events: list[dict] = field(default_factory=list)
    security_events: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    ended_at: float = 0.0
    turn_count: int = 0
    status: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def closed(self) -> bool:
        return self.state in (SessionState.CALL_ENDED, SessionState.SESSION_CLOSED)

    @property
    def duration_seconds(self) -> float:
        end = self.ended_at or time.time()
        return round(end - self.started_at, 1)
