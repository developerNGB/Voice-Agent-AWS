"""Online TTS for live calls → 8 kHz µ-law audio (free, no API key).

Two backends, tried in order:

1. **edge-tts** — Microsoft Edge online voices (Canadian English neural).
2. **gTTS**     — Google Translate TTS (``tld="ca"``), used automatically
                  when the Edge endpoint is unreachable from the host.

Either way the MP3 is decoded with libsndfile (soundfile) and converted to
8 kHz 16-bit PCM → G.711 µ-law so the bytes drop straight into a
SignalWire/Twilio media stream.
"""

from __future__ import annotations

import audioop
import asyncio
import io

from app.voice.base import AudioChunk, TextToSpeechProvider

_mulaw_cache: dict[str, bytes] = {}


class EdgeTTSProvider(TextToSpeechProvider):
    """Free neural TTS → 8 kHz µ-law audio chunks for telephony."""

    name = "edge"

    def __init__(self, voice: str = "en-CA-ClaraNeural",
                 sample_rate: int = 8000, timeout: float = 20.0):
        self.voice = voice
        self.sample_rate = sample_rate
        self.timeout = timeout
        self.synthesized: list[str] = []

    async def synthesize(self, text: str, *, voice: str = "") -> AudioChunk:
        text = (text or "").strip()
        if not text:
            return AudioChunk(data=b"\xff" * 160,
                              content_type="audio/x-mulaw;rate=8000")

        chosen = voice or self.voice
        cache_key = f"{chosen}|{text}"
        cached = _mulaw_cache.get(cache_key)
        if cached is None:
            mp3 = await self._fetch_mp3(text, chosen)
            cached = self._mp3_to_mulaw(mp3)
            if len(_mulaw_cache) < 256:          # bounded
                _mulaw_cache[cache_key] = cached
        self.synthesized.append(text)
        return AudioChunk(data=cached,
                          content_type="audio/x-mulaw;rate=8000")

    # -- internals -----------------------------------------------------------

    async def _fetch_mp3(self, text: str, voice: str) -> bytes:
        try:
            return await self._edge_mp3(text, voice)
        except Exception as exc:                # endpoint unreachable/blocked
            self._warn_once(f"edge-tts unavailable ({exc.__class__.__name__}); "
                            "falling back to gTTS")
            return await asyncio.to_thread(self._gtts_mp3, text)

    async def _edge_mp3(self, text: str, voice: str) -> bytes:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice)
        buffer = bytearray()
        async with asyncio.timeout(self.timeout):
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    buffer.extend(chunk["data"])
        if not buffer:
            raise RuntimeError(f"edge-tts returned no audio for voice {voice!r}")
        return bytes(buffer)

    @staticmethod
    def _gtts_mp3(text: str) -> bytes:
        import io as _io

        from gtts import gTTS

        buf = _io.BytesIO()
        gTTS(text, lang="en", tld="ca").write_to_fp(buf)
        return buf.getvalue()

    _warned = False

    @classmethod
    def _warn_once(cls, message: str) -> None:
        if not cls._warned:
            cls._warned = True
            import logging

            logging.getLogger("voice.tts").warning(message)

    def _mp3_to_mulaw(self, mp3: bytes) -> bytes:
        import soundfile as sf

        data, samplerate = sf.read(io.BytesIO(mp3), dtype="int16")
        if getattr(data, "ndim", 1) > 1:         # stereo → mono
            data = data.mean(axis=1).astype("int16")
        pcm = data.tobytes()
        if samplerate != self.sample_rate:
            pcm, _ = audioop.ratecv(pcm, 2, 1, samplerate, self.sample_rate, None)
        return audioop.lin2ulaw(pcm, 2)
