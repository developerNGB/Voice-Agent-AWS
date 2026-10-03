"""Endpoint detection, barge-in, and the audio path through the gateway."""

from app.gateway import VoiceGateway
from app.voice.interruption import BargeInController
from app.voice.mock import MockSTTProvider, MockTTSProvider
from app.voice.streaming import EndpointConfig, EndpointDetector, frame_energy

SPEECH = b"\x00" * 160      # 20 ms of loud µ-law audio
SILENCE = b"\xff" * 160     # 20 ms of digital silence


def test_frame_energy():
    assert frame_energy(SILENCE) == 0.0
    assert frame_energy(SPEECH) > 3.0
    assert frame_energy(b"") == 0.0


def test_endpoint_detector_emits_speech_start_and_end():
    detector = EndpointDetector(EndpointConfig(silence_endpoint_ms=600))
    events = []
    for _ in range(10):
        events.append(detector.feed(SPEECH))
    assert "speech_start" in events
    assert detector.state == "speaking"

    for _ in range(29):  # 580 ms of silence — not yet an endpoint
        assert detector.feed(SILENCE) != "speech_end"

    assert detector.feed(SILENCE) == "speech_end"  # 600 ms reached
    assert detector.state == "silence"
    assert detector.utterances  # audio captured for STT


def test_short_noise_is_not_an_utterance():
    detector = EndpointDetector(EndpointConfig(silence_endpoint_ms=400))
    detector.feed(SPEECH)
    detector.feed(SPEECH)
    detector.feed(SILENCE)
    assert detector.state == "silence"       # never reached speech_start
    assert not detector.utterances


def test_barge_in_cancels_agent_audio():
    controller = BargeInController(grace_ms=0)
    controller.agent_started_speaking()
    assert controller.on_caller_speech() is True
    assert controller.interrupt_count == 1
    assert controller.events[0]["type"] == "barge_in"
    # not speaking → no cancel
    assert controller.on_caller_speech() is False


def test_barge_in_grace_window():
    controller = BargeInController(grace_ms=60_000)
    controller.agent_started_speaking()
    assert controller.on_caller_speech() is False  # inside grace window


async def test_gateway_audio_path_runs_a_turn(agent, settings):
    stt, tts = MockSTTProvider(), MockTTSProvider()
    gateway = VoiceGateway(agent, stt=stt, tts=tts, settings=settings)
    call = await gateway.open("realestate_001")

    stt.feed_text("What about 123 Main Street?")
    events = []
    for _ in range(10):
        events += await call.handle_audio_frame(SPEECH)
    for _ in range(40):  # 800 ms silence → endpoint → utterance
        events += await call.handle_audio_frame(SILENCE)

    turns = [e for e in events if e["type"] == "agent_turn"]
    assert turns, f"expected a turn, got {events}"
    assert turns[0]["active_skill"] == "property_001"
    assert tts.synthesized  # reply was synthesised

    record = await call.close()
    assert record.status == "completed"
    assert record.turn_count == 1


async def test_gateway_text_path_synthesises_reply(agent, settings):
    gateway = VoiceGateway(agent, stt=MockSTTProvider(), tts=MockTTSProvider(),
                           settings=settings)
    call = await gateway.open("realestate_001")
    turn, audio = await call.handle_text("Tell me about 123 Main Street")
    assert turn.active_skill_id == "property_001"
    assert audio is not None and audio.data
    await call.close()
