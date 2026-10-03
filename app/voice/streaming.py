"""Audio framing, energy-based VAD and speech endpoint detection.

Telephony audio arrives as 20 ms µ-law frames.  The endpoint detector
decides when the caller has started speaking and when they have stopped,
which is what drives turn-taking (and barge-in).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

FRAME_MS = 20


def frame_energy(frame: bytes) -> float:
    """Cheap energy proxy for µ-law frames (0xFF/0x7F ≈ digital silence)."""
    if not frame:
        return 0.0
    return sum(min(abs(b - 0xFF), abs(b - 0x7F)) for b in frame) / len(frame)


@dataclass
class EndpointConfig:
    frame_ms: int = FRAME_MS
    silence_endpoint_ms: int = 700      # caller stopped talking
    speech_start_frames: int = 4        # ~80 ms of sound to call it speech
    speech_threshold: float = 3.0       # mean energy
    max_utterance_ms: int = 20_000      # force-close runaway utterances


class EndpointDetector:
    """State machine: silence → speaking → (silence) → utterance complete."""

    def __init__(self, config: EndpointConfig | None = None):
        self.config = config or EndpointConfig()
        self.state = "silence"
        self._run: list[bytes] = []
        self._speech_run = 0
        self._silence_ms = 0
        self._duration_ms = 0
        self.utterances: list[bytes] = []

    def reset(self) -> None:
        self.state = "silence"
        self._run.clear()
        self._speech_run = 0
        self._silence_ms = 0
        self._duration_ms = 0

    def feed(self, frame: bytes) -> str:
        """Feed one frame; returns ``""``, ``"speech_start"`` or ``"speech_end"``."""
        cfg = self.config
        is_speech = frame_energy(frame) >= cfg.speech_threshold
        event = ""

        if self.state == "silence":
            if is_speech:
                self._speech_run += 1
                if self._speech_run >= cfg.speech_start_frames:
                    self.state = "speaking"
                    self._run.append(frame)
                    self._duration_ms += cfg.frame_ms
                    event = "speech_start"
                else:
                    self._run.append(frame)
                    self._duration_ms += cfg.frame_ms
            else:
                self._speech_run = 0
                self._run.clear()
                self._duration_ms = 0
            return event

        # state == speaking
        self._run.append(frame)
        self._duration_ms += cfg.frame_ms
        if is_speech:
            self._silence_ms = 0
        else:
            self._silence_ms += cfg.frame_ms

        if self._silence_ms >= cfg.silence_endpoint_ms or self._duration_ms >= cfg.max_utterance_ms:
            self.utterances.append(b"".join(self._run))
            self.reset()
            return "speech_end"
        return event


class AudioAccumulator:
    """Bounded buffer that stitches frames for STT/TTS queues."""

    def __init__(self, max_frames: int = 1000):
        self.max_frames = max_frames
        self._frames: deque[bytes] = deque(maxlen=max_frames)

    def add(self, frame: bytes) -> None:
        self._frames.append(frame)

    def drain(self) -> bytes:
        data = b"".join(self._frames)
        self._frames.clear()
        return data

    def __len__(self) -> int:
        return len(self._frames)
