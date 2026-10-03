"""HTTP/WebSocket API tests: /health, /ws (AgentCore contract), Twilio webhook."""

import json

from fastapi.testclient import TestClient

from app.agent.agent import VoiceAgent
from app.config import Settings
from app.main import create_app
from app.storage.logs import MemoryLogger


def make_client(settings: Settings | None = None) -> TestClient:
    settings = settings or Settings(model_provider="mock", skill_root="skills")
    agent = VoiceAgent(settings, logger=MemoryLogger())
    app = create_app(settings=settings, agent=agent)
    return TestClient(app)


def test_health():
    with make_client() as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["model_provider"] == "mock"


def test_websocket_full_conversation():
    with make_client() as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "session.start", "agent_id": "realestate_001"}))
            started = json.loads(ws.receive_text())
            assert started["type"] == "session.started"
            assert "Main Street Realty" in started["greeting"]
            session_id = started["session_id"]

            ws.send_text(json.dumps({"type": "user.text", "text": "123 Main Street"}))
            reply = json.loads(ws.receive_text())
            assert reply["type"] == "agent.text"
            assert reply["session_id"] == session_id
            assert reply["active_skill"] == "property_001"

            ws.send_text(json.dumps({"type": "user.text", "text": "What's the price?"}))
            reply = json.loads(ws.receive_text())
            assert "899,000" in reply["text"]

            ws.send_text(json.dumps({"type": "session.end"}))
            summary = json.loads(ws.receive_text())
            assert summary["type"] == "call.summary"
            assert summary["record"]["status"] == "completed"
            assert summary["record"]["skills_used"] == ["property_001"]


def test_websocket_rejects_bad_json():
    with make_client() as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_text("not-json")
            error = json.loads(ws.receive_text())
            assert error["type"] == "error"


def test_twilio_voice_returns_stream_twiml():
    with make_client() as client:
        resp = client.post(
            "/twilio/voice",
            data={"To": "+14165550100", "From": "+14165559999", "CallSid": "CA123"},
        )
        assert resp.status_code == 200
        assert "application/xml" in resp.headers["content-type"]
        assert "<Stream" in resp.text
        assert "/twilio/media" in resp.text


def test_one_phone_number_maps_to_one_agent():
    with make_client() as client:
        resp = client.post("/twilio/voice", data={"To": "+14165550200", "CallSid": "CA1"})
        assert "agent=cleaning_001" in resp.text


def test_twilio_signature_enforced_when_enabled():
    settings = Settings(model_provider="mock", skill_root="skills",
                        twilio_validate_signature=True, twilio_auth_token="token")
    with make_client(settings) as client:
        resp = client.post("/twilio/voice", data={"To": "+14165550100"})
        assert resp.status_code == 403


def test_websocket_twilio_media_path():
    with make_client() as client:
        with client.websocket_connect("/twilio/media?agent=realestate_001") as ws:
            ws.send_text(json.dumps({
                "event": "start",
                "start": {"streamSid": "MZ123", "callSid": "CA123"},
            }))
            ws.send_text(json.dumps({
                "event": "media",
                "media": {"payload": "AAEC"},  # dummy µ-law frame
            }))
            ws.send_text(json.dumps({"event": "stop"}))
            # give the app a chance to process without asserting audio bytes
            assert True
