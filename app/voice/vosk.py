"""Real offline speech-to-text using Vosk (Kaldi).

Telephony audio arrives as 8 kHz µ-law frames.  Each frame is decoded to
16-bit PCM, up-sampled to the model rate (16 kHz for the small English
model) and pushed through a :class:`vosk.KaldiRecognizer`.

The model is loaded once per process (it is ~40 MB / ~150 MB RAM — never
per call).  The gateway calls ``stop()`` then ``start()`` between
utterances, so each utterance gets a fresh recognizer while the model and
resampler context survive.
"""

from __future__ import annotations

import audioop
import json
from pathlib import Path

from app.voice.base import (
    SpeechToTextProvider,
    StreamConfig,
    Transcript,
)

# process-wide model cache: {path: vosk.Model}
_MODELS: dict[str, object] = {}


def load_model(path: str):
    """Load (and cache) a Vosk model from ``path``."""
    key = str(Path(path).resolve())
    if key not in _MODELS:
        from vosk import Model  # lazy: tests never import vosk

        if not Path(path).exists():
            raise FileNotFoundError(
                f"Vosk model not found at {path!r}. Download it with: "
                f"curl -o /tmp/vosk.zip https://alphacephei.com/vosk/models/"
                f"vosk-model-small-en-us-0.15.zip && unzip /tmp/vosk.zip -d models"
            )
        _MODELS[key] = Model(path)
    return _MODELS[key]


class VoskSTTProvider(SpeechToTextProvider):
    """Offline streaming STT — no cloud dependency, no API key."""

    name = "vosk"

    def __init__(self, model_path: str = "models/vosk-model-small-en-us-0.15",
                 sample_rate: int = 16000):
        self.model_path = model_path
        self.sample_rate = sample_rate          # model rate (16 kHz)
        self.source_rate = 8000                 # telephony rate
        self._rec = None
        self._resampler_state = None
        self._partial = ""

    # -- lifecycle -----------------------------------------------------------

    async def start(self, config: StreamConfig) -> None:
        from vosk import KaldiRecognizer

        model = load_model(self.model_path)
        self.source_rate = config.sample_rate or 8000
        self._resampler_state = None             # fresh utterance
        self._partial = ""
        self._rec = KaldiRecognizer(model, self.sample_rate)
        self._rec.SetWords(False)

    async def feed_audio(self, frame: bytes) -> list[Transcript]:
        if self._rec is None or not frame:
            return []
        pcm = self._decode(frame)                # s16le @ self.sample_rate
        if not pcm:
            return []
        transcripts: list[Transcript] = []
        if self._rec.AcceptWaveform(pcm):
            text = json.loads(self._rec.Result()).get("text", "").strip()
            self._partial = ""
            if text:
                transcripts.append(Transcript(text=text, is_final=True,
                                              confidence=0.9))
        return transcripts

    async def stop(self) -> list[Transcript]:
        """Flush the utterance in progress (endpoint detector said done)."""
        if self._rec is None:
            return []
        text = json.loads(self._rec.FinalResult()).get("text", "").strip()
        self._partial = ""
        self._rec = None
        return [Transcript(text=text, is_final=True, confidence=0.9)] if text else []

    async def close(self) -> None:
        self._rec = None

    # -- audio conversion ----------------------------------------------------

    def _decode(self, frame: bytes) -> bytes:
        """µ-law 8 kHz → PCM 16 kHz (mono, 16-bit little-endian)."""
        # Telephony frames may be µ-law or (from /ws tests) already PCM.
        pcm = audioop.ulaw2lin(frame, 2)         # → s16le @ 8 kHz
        if self.source_rate != self.sample_rate:
            pcm, self._resampler_state = audioop.ratecv(
                pcm, 2, 1, self.source_rate, self.sample_rate,
                self._resampler_state,
            )
        return pcm
