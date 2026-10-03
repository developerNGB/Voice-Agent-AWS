"""SignalWire webhook + bidirectional media stream tests."""

import json

from fastapi.testclient import TestClient

from app.agent.agent import VoiceAgent
from app.config import Settings
from app.main import create_app
from app.storage.logs import MemoryLogger
from app.telephony.signalwire import connect_stream_xml, validate_signalwire_auth

NUMBER = "+12014834036"


def make_client(settings: Settings | None = None) -> TestClient:
    settings = settings or Settings(model_provider="mock", skill_root="skills",
                                    public_base_url="https://example.com")
    agent = VoiceAgent(settings, logger=MemoryLogger())
    return TestClient(create_app(settings=settings, agent=agent))


def test_cxml_declares_bidirectional_stream():
    xml = connect_stream_xml("wss://example.com/signalwire/media",
                             agent_id="realestate_001", call_sid="CA1")
    assert "<Connect>" in xml
    assert 'url="wss://example.com/signalwire/media"' in xml
    assert 'codec="PCMU@8000h"' in xml
    assert 'name="agent" value="realestate_001"' in xml
    # no query strings — SignalWire forbids them on stream URLs
    assert "wss://example.com/signalwire/media?" not in xml


def test_plain_ws_url_rejected():
    import pytest

    with pytest.raises(ValueError):
        connect_stream_xml("http://example.com/media")


def test_voice_webhook_returns_signalwire_cxml():
    with make_client() as client:
        resp = client.post("/signalwire/voice",
                           data={"To": NUMBER, "From": "+15555550101",
                                 "CallSid": "abc-123"})
        assert resp.status_code == 200
        assert "application/xml" in resp.headers["content-type"]
        assert "<Connect>" in resp.text
        assert "<Parameter name=\"agent\" value=\"realestate_001\"/>" in resp.text


def test_voice_webhook_basic_auth_enforced_when_enabled():
    settings = Settings(model_provider="mock", skill_root="skills",
                        signalwire_validate=True,
                        signalwire_project_id="PROJ123",
                        signalwire_token="tok_secret",
                        public_base_url="https://example.com")
    with make_client(settings) as client:
        denied = client.post("/signalwire/voice", data={"To": NUMBER})
        assert denied.status_code == 401

        import base64
        good = base64.b64encode(b"PROJ123:tok_secret").decode()
        ok = client.post("/signalwire/voice", data={"To": NUMBER},
                         headers={"Authorization": f"Basic {good}"})
        assert ok.status_code == 200 and "<Connect>" in ok.text


def test_validate_signalwire_auth():
    header = "Basic " + __import__("base64").b64encode(b"p:t").decode()
    assert validate_signalwire_auth("p", "t", header)
    assert not validate_signalwire_auth("p", "WRONG", header)
    assert not validate_signalwire_auth("p", "t", "")
    assert not validate_signalwire_auth("", "", header)


def test_media_stream_protocol_start_media_stop():
    """SignalWire dialect: connected → start(customParameters) → media → stop."""
    with make_client() as client:
        with client.websocket_connect("/signalwire/media") as ws:
            ws.send_text(json.dumps({"event": "connected", "protocol": "Call",
                                     "version": "0.2.0"}))
            ws.send_text(json.dumps({
                "event": "start",
                "sequenceNumber": "1",
                "start": {
                    "streamSid": "sw-stream-1",
                    "callSid": "sw-call-1",
                    "customParameters": {"agent": "realestate_001"},
                    "mediaFormat": {"encoding": "audio/x-mulaw",
                                    "sampleRate": 8000, "channels": 1},
                },
            }))
            # greeting audio pushed back to SignalWire
            greeting = json.loads(ws.receive_text())
            assert greeting["event"] == "media"
            assert greeting["streamSid"] == "sw-stream-1"
            assert greeting["media"]["payload"]

            # caller speaks: 10 speech frames + endpoint silence
            speech = __import__("base64").b64encode(b"\x00" * 160).decode()
            silence = __import__("base64").b64encode(b"\xff" * 160).decode()
            for _ in range(10):
                ws.send_text(json.dumps({"event": "media", "media": {
                    "track": "inbound", "chunk": "1", "timestamp": "0",
                    "payload": speech}}))
            # transcript arrives via mock STT only if fed — the gateway still
            # completes the utterance without error
            for _ in range(40):
                ws.send_text(json.dumps({"event": "media", "media": {
                    "track": "inbound", "chunk": "1", "timestamp": "0",
                    "payload": silence}}))

            ws.send_text(json.dumps({"event": "stop", "sequenceNumber": "9"}))
            # connection closes cleanly after stop
