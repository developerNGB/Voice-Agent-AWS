"""Voice Gateway — bridges telephony/WebSocket audio to the Voice Agent.

One :class:`GatewayCall` per call: endpoint detection in, barge-in control,
TTS out.  The gateway never contains business logic; it only moves audio and
text between the transport and :class:`app.agent.agent.VoiceAgent`.
"""

from __future__ import annotations

import base64
import time

from app.agent.agent import VoiceAgent
from app.config import Settings, get_settings
from app.models.call import AgentTurn, CallRecord
from app.voice.base import (
    AudioChunk,
    SpeechToTextProvider,
    StreamConfig,
    TextToSpeechProvider,
)
from app.voice.interruption import BargeInController
from app.voice.mock import MockSTTProvider, MockTTSProvider
from app.voice.streaming import EndpointConfig, EndpointDetector


class GatewayCall:
    """State for one live call."""

    def __init__(self, agent: VoiceAgent, session, stt: SpeechToTextProvider,
                 tts: TextToSpeechProvider, settings: Settings,
                 on_audio=None):
        self.agent = agent
        self.session = session
        self.stt = stt
        self.tts = tts
        self.settings = settings
        self.endpoint = EndpointDetector(EndpointConfig())
        self.bargein = BargeInController()
        self.on_audio = on_audio or (lambda chunk: None)
        self.stream_config = StreamConfig()
        self.started_at = time.time()
        self.closed = False

    # -- text path (AgentCore /ws, tests, CLI) -------------------------------

    async def handle_text(self, text: str) -> tuple[AgentTurn, AudioChunk | None]:
        turn = await self.agent.handle_turn(self.session.session_id, text)
        audio = await self.tts.synthesize(turn.reply)
        self.on_audio(audio)
        return turn, audio

    # -- audio path (Twilio media stream) ------------------------------------

    async def handle_audio_frame(self, frame: bytes) -> list[dict]:
        """Feed one telephony frame; returns gateway events."""
        events: list[dict] = []
        await self.stt.feed_audio(frame)
        event = self.endpoint.feed(frame)

        if event == "speech_start":
            if self.bargein.on_caller_speech():
                events.append({"type": "cancel_audio", "reason": "barge_in"})
        elif event == "speech_end":
            transcripts = await self.stt.stop()
            await self.stt.start(self.stream_config)
            for transcript in transcripts:
                if not transcript.text.strip():
                    continue
                turn, audio = await self.handle_text(transcript.text)
                events.append({
                    "type": "agent_turn",
                    "text": turn.reply,
                    "session_id": turn.session_id,
                    "route_status": turn.route_status,
                    "active_skill": turn.active_skill_id,
                })
                if turn.end_call:
                    events.append({"type": "end_call"})
        return events

    def agent_audio_chunk(self, chunk: AudioChunk) -> dict:
        self.bargein.agent_started_speaking()
        return {
            "type": "agent_audio",
            "data": base64.b64encode(chunk.data).decode("ascii"),
            "content_type": chunk.content_type,
        }

    async def close(self) -> CallRecord:
        if self.closed:
            return self.agent.logger.build_record(self.session)
        self.closed = True
        await self.stt.close()
        await self.tts.close()
        return await self.agent.end_session(self.session.session_id)


class VoiceGateway:
    """Creates/owns gateway calls."""

    def __init__(self, agent: VoiceAgent, stt: SpeechToTextProvider | None = None,
                 tts: TextToSpeechProvider | None = None,
                 settings: Settings | None = None):
        self.agent = agent
        self.settings = settings or agent.settings
        # Explicit instances are shared (tests); otherwise one per call.
        self._shared_stt = stt
        self._shared_tts = tts
        self.stt = stt or self._build_stt()
        self.tts = tts or self._build_tts()

    def _build_stt(self) -> SpeechToTextProvider:
        if self.settings.stt_provider == "aws":
            from app.voice.aws import TranscribeSTTProvider

            return TranscribeSTTProvider(region=self.settings.aws_region)
        return MockSTTProvider()

    def _build_tts(self) -> TextToSpeechProvider:
        if self.settings.tts_provider == "aws":
            from app.voice.aws import PollyTTSProvider

            return PollyTTSProvider(
                voice_id=self.settings.polly_voice_id,
                engine=self.settings.polly_engine,
                region=self.settings.aws_region,
            )
        return MockTTSProvider()

    async def open(self, agent_id: str | None = None, caller_id: str = "redacted",
                   on_audio=None) -> GatewayCall:
        session = self.agent.start_session(agent_id or self.settings.agent_id, caller_id)
        stt = self._shared_stt or self._build_stt()
        tts = self._shared_tts or self._build_tts()
        await stt.start(StreamConfig())
        return GatewayCall(self.agent, session, stt, tts, self.settings, on_audio=on_audio)
