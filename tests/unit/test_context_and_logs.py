"""Caller profile extraction and structured call logging."""

from app.agent.context import ContextManager
from app.config import Settings
from app.agent.agent import VoiceAgent
from app.models.session import Session
from app.storage.logs import MemoryLogger


def make_session() -> Session:
    return Session(session_id="sess-1", agent_id="realestate_001")


def test_extracts_name_and_budget():
    session = make_session()
    changed = ContextManager().extract(session, "My name is Peter and my budget is under $800,000")
    assert "name" in changed and session.profile.name == "Peter"
    assert "budget" in changed and session.profile.budget == "800,000"


def test_extracts_bedrooms_intent_timeline():
    session = make_session()
    ContextManager().extract(
        session, "I want to buy with three bedrooms and I'd like to see it this weekend"
    )
    assert session.profile.bedrooms == "three"
    assert session.profile.intent in ("buying", "viewing")
    assert session.profile.timeline == "this weekend"


def test_does_not_capture_name_from_questions():
    session = make_session()
    ContextManager().extract(session, "What is my name?")
    assert session.profile.name == ""


async def test_call_record_contains_transcript_and_events(settings):
    logger = MemoryLogger()
    agent = VoiceAgent(settings, logger=logger)
    session = agent.start_session("realestate_001")

    await agent.handle_turn(session.session_id, "I'm interested in 123 Main Street")
    await agent.handle_turn(session.session_id, "What's the price?")
    record = await agent.end_session(session.session_id)

    data = record.to_dict()
    assert data["status"] == "completed"
    assert data["turn_count"] == 2  # one increment per caller utterance
    assert data["skills_used"] == ["property_001"]
    assert data["routing_events"] >= 2
    assert len(data["transcript"]) == 4
    assert data["transcript"][0]["speaker"] == "caller"
    assert data["duration_seconds"] >= 0
    assert logger.calls and logger.calls[-1]["session_id"] == session.session_id


async def test_caller_id_is_hashed_not_stored(settings):
    logger = MemoryLogger()
    agent = VoiceAgent(settings, logger=logger)
    session = agent.start_session("realestate_001", caller_id="+14165551234")
    assert session.caller_id != "+14165551234"
    assert len(session.caller_id) == 16
    record = await agent.end_session(session.session_id)
    assert "+14165551234" not in str(record.to_dict())
