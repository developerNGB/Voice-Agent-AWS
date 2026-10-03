"""Voice provider interfaces (STT in, TTS out).

Keeping these as small protocols means the transport (Twilio, AgentCore
WebSocket, a test harness) can be swapped without touching agent logic.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class Transcript:
    """A finished (or partial) utterance from the caller."""

    text: str
    is_final: bool = True
    confidence: float = 0.0
    language: str = "en-CA"


@dataclass
class AudioChunk:
    """Synthesised audio ready to be streamed back to the caller."""

    data: bytes
    content_type: str = "audio/x-mulaw;rate=8000"
    sequence: int = 0


@dataclass
class StreamConfig:
    sample_rate: int = 8000
    encoding: str = "mulaw"
    channels: int = 1


class SpeechToTextProvider(abc.ABC):
    """Streaming speech → text."""

    name = "stt"

    @abc.abstractmethod
    async def start(self, config: StreamConfig) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def feed_audio(self, frame: bytes) -> list[Transcript]:
        """Push one audio frame; return any transcripts completed by it."""
        raise NotImplementedError

    @abc.abstractmethod
    async def stop(self) -> list[Transcript]:
        raise NotImplementedError

    async def close(self) -> None:  # pragma: no cover - default no-op
        return None


class TextToSpeechProvider(abc.ABC):
    """Text → audio."""

    name = "tts"

    @abc.abstractmethod
    async def synthesize(self, text: str, *, voice: str = "") -> AudioChunk:
        raise NotImplementedError

    async def close(self) -> None:  # pragma: no cover - default no-op
        return None
