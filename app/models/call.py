"""Call records, leads and routing decisions."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RoutingDecision:
    """Outcome of skill routing for a single utterance."""

    status: str                        # activate | clarify | keep | none
    skill_id: str = ""
    candidates: list[tuple[str, float]] = field(default_factory=list)
    reason: str = ""

    @property
    def activated(self) -> bool:
        return self.status == "activate"


@dataclass
class Lead:
    """Captured real-estate lead."""

    name: str = ""
    phone: str = ""
    email: str = ""
    property_interest: str = ""
    budget: str = ""
    location: str = ""
    intent: str = ""
    timeline: str = ""
    bedrooms: str = ""
    session_id: str = ""
    agent_id: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class CallRecord:
    """Structured per-call log written at call end."""

    session_id: str
    agent_id: str
    caller_id: str
    started_at: str
    ended_at: str
    duration_seconds: float
    skills_used: list[str]
    turn_count: int
    routing_events: int
    errors: list[str]
    status: str
    transcript: list[dict] = field(default_factory=list)
    security_events: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "caller_id": self.caller_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds,
            "skills_used": self.skills_used,
            "turn_count": self.turn_count,
            "routing_events": self.routing_events,
            "errors": self.errors,
            "status": self.status,
            "transcript": self.transcript,
            "security_events": self.security_events,
        }


@dataclass
class AgentTurn:
    """What the agent returns for one caller utterance."""

    reply: str
    session_id: str
    route_status: str = "keep"
    active_skill_id: str = ""
    clarify_candidates: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    latency_ms: float = 0.0
    end_call: bool = False
