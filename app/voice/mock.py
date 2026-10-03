"""Mock voice providers — used by tests and offline demos.

``MockSTT`` accepts *scripted* utterances (``feed_text``) and returns them as
transcripts; audio frames are ignored.  ``MockTTS`` returns deterministic
silent-ish audio so byte-level assertions are stable.
"""

from __future__ import annotations

from app.voice.base import (
    AudioChunk,
    SpeechToTextProvider,
    StreamConfig,
    TextToSpeechProvider,
    Transcript,
)


class MockSTTProvider(SpeechToTextProvider):
    name = "mock-stt"

    def __init__(self, language: str = "en-CA"):
        self.language = language
        self.config = StreamConfig()
        self._pending: list[Transcript] = []
        self.frames_fed = 0

    async def start(self, config: StreamConfig) -> None:
        self.config = config

    def feed_text(self, text: str) -> Transcript:
        """Test/demo hook: inject a recognised utterance."""
        transcript = Transcript(text=text, is_final=True, confidence=0.99,
                                language=self.language)
        self._pending.append(transcript)
        return transcript

    async def feed_audio(self, frame: bytes) -> list[Transcript]:
        self.frames_fed += 1
        return []

    async def stop(self) -> list[Transcript]:
        pending, self._pending = self._pending, []
        return pending


class MockTTSProvider(TextToSpeechProvider):
    name = "mock-tts"

    def __init__(self):
        self.synthesized: list[str] = []

    async def synthesize(self, text: str, *, voice: str = "") -> AudioChunk:
        self.synthesized.append(text)
        # 20 ms of µ-law silence (0xFF) per ~20 characters, capped small
        frames = max(1, min(len(text), 60))
        return AudioChunk(data=b"\xff" * (80 * frames), content_type="audio/x-mulaw;rate=8000")
