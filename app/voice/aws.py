"""AWS-native voice providers.

* :class:`PollyTTSProvider`       — Amazon Polly ``synthesize_speech``
* :class:`TranscribeSTTProvider`  — Amazon Transcribe streaming (optional extra)

Both import their SDK lazily so unit tests never need AWS packages/credentials.
"""

from __future__ import annotations

import asyncio

from app.voice.base import (
    AudioChunk,
    SpeechToTextProvider,
    StreamConfig,
    TextToSpeechProvider,
    Transcript,
)


class PollyTTSProvider(TextToSpeechProvider):
    """Amazon Polly neural TTS (8 kHz mono so it fits telephony)."""

    name = "polly"

    def __init__(self, voice_id: str = "Joanna", engine: str = "neural",
                 region: str = "ca-central-1", client=None):
        self.voice_id = voice_id
        self.engine = engine
        self.region = region
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("polly", region_name=self.region)
        return self._client

    async def synthesize(self, text: str, *, voice: str = "") -> AudioChunk:
        def _call():
            return self.client.synthesize_speech(
                Text=text,
                VoiceId=voice or self.voice_id,
                Engine=self.engine,
                OutputFormat="pcm",
                SampleRate="8000",
                TextType="text",
            )

        response = await asyncio.to_thread(_call)
        audio = await asyncio.to_thread(response["AudioStream"].read)
        return AudioChunk(data=audio, content_type="audio/x-l16;rate=8000")


class TranscribeSTTProvider(SpeechToTextProvider):
    """Amazon Transcribe streaming STT (requires ``amazon-transcribe-streaming``)."""

    name = "transcribe"

    def __init__(self, language_code: str = "en-CA", region: str = "ca-central-1"):
        self.language_code = language_code
        self.region = region
        self._stream = None
        self._results: list[Transcript] = []

    async def start(self, config: StreamConfig) -> None:
        try:
            from amazon_transcribe.stream import TranscribeStream  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "STT_PROVIDER=aws requires: pip install "
                "'realestate-voice-agent[voice]' (amazon-transcribe-streaming)"
            ) from exc
        stream = TranscribeStream(region_name=self.region,
                                  language_code=self.language_code)
        await stream.start_stream(self._audio_generator(config))
        self._stream = stream

    async def _audio_generator(self, config: StreamConfig):  # pragma: no cover
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._queue = queue
        while True:
            frame = await queue.get()
            if frame is None:
                break
            yield frame

    async def feed_audio(self, frame: bytes) -> list[Transcript]:  # pragma: no cover
        if getattr(self, "_queue", None) is not None:
            await self._queue.put(frame)
        return []

    async def stop(self) -> list[Transcript]:  # pragma: no cover
        if self._stream is not None:
            await self._stream.stop_stream()
        results, self._results = self._results, []
        return results

    def push_result(self, text: str) -> None:  # pragma: no cover - used by the gateway
        self._results.append(Transcript(text=text, is_final=True, confidence=0.9))
