"""Caller interruption (barge-in) handling."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class BargeInController:
    """Decides whether caller speech should cut off agent speech.

    Rules:
    * caller speaks while the agent is talking → cancel playback (barge-in)
    * a short grace window after the agent *starts* speaking avoids clipping
      the agent's own echo/room noise
    """

    grace_ms: int = 250
    enabled: bool = True
    agent_speaking: bool = False
    interrupt_count: int = 0
    _agent_started_at: float = 0.0
    events: list[dict] = field(default_factory=list)

    def agent_started_speaking(self) -> None:
        self.agent_speaking = True
        self._agent_started_at = time.monotonic() * 1000.0

    def agent_stopped_speaking(self) -> None:
        self.agent_speaking = False

    def on_caller_speech(self) -> bool:
        """Returns True when playback of the agent's audio must stop now."""
        if not self.enabled or not self.agent_speaking:
            return False
        elapsed = (time.monotonic() * 1000.0) - self._agent_started_at
        if elapsed < self.grace_ms:
            return False
        self.interrupt_count += 1
        self.agent_speaking = False
        self.events.append({"type": "barge_in", "after_ms": round(elapsed, 1)})
        return True
