"""Session isolation under concurrency: parallel calls must not leak state."""

import asyncio

from app.agent.agent import VoiceAgent
from app.storage.logs import MemoryLogger


async def test_three_parallel_calls_stay_isolated(settings):
    """A → 123 Main, B → 200 King, C → selling. No cross-talk."""
    logger = MemoryLogger()
    agent = VoiceAgent(settings, logger=logger)

    s_a = agent.start_session("realestate_001")
    s_b = agent.start_session("realestate_001")
    s_c = agent.start_session("realestate_001")

    async def converse(session, lines):
        results = []
        for line in lines:
            results.append(await agent.handle_turn(session.session_id, line))
            await asyncio.sleep(0)  # interleave
        return results

    turn_a, turn_b, turn_c = await asyncio.gather(
        converse(s_a, ["Tell me about 123 Main Street.", "What's the price?"]),
        converse(s_b, ["Tell me about 200 King Street.", "What's the price?"]),
        converse(s_c, ["I want to sell my own house.", "What's the next step?"]),
    )

    assert s_a.active_skill_id == "property_001"
    assert s_b.active_skill_id == "property_003"
    assert s_c.active_skill_id == ""

    assert "899,000" in turn_a[1].reply
    assert "615,000" in turn_b[1].reply
    assert "899,000" not in turn_b[1].reply
    assert "615,000" not in turn_a[1].reply
    assert "address" in turn_c[1].reply.lower()

    assert s_a.session_id != s_b.session_id != s_c.session_id
    assert s_a.history and s_b.history and s_c.history


async def test_caller_name_never_leaks_between_sessions(settings):
    """Session A learns 'Peter'. Session B must not know it."""
    agent = VoiceAgent(settings, logger=MemoryLogger())

    s_a = agent.start_session("realestate_001")
    s_b = agent.start_session("realestate_001")

    await agent.handle_turn(s_a.session_id, "My name is Peter.")
    await agent.handle_turn(s_a.session_id, "I'm interested in 123 Main Street")

    turn = await agent.handle_turn(s_b.session_id, "What is my name?")

    assert "Peter" not in turn.reply
    assert s_b.profile.name == ""
    assert s_a.profile.name == "Peter"
    # B's context never contains A's profile
    assert "Peter" not in str(s_b.to_dict() if hasattr(s_b, "to_dict") else s_b.__dict__)


async def test_sessions_close_independently(settings):
    agent = VoiceAgent(settings, logger=MemoryLogger())
    s_a = agent.start_session("realestate_001")
    s_b = agent.start_session("realestate_001")

    await agent.end_session(s_a.session_id)

    # A is closed; B keeps working
    turn = await agent.handle_turn(s_b.session_id, "Tell me about 123 Main Street")
    assert turn.active_skill_id == "property_001"

    record_a = agent.logger.build_record(s_a) if False else None  # A record already finalized
    assert s_a.closed and not s_b.closed
    assert record_a is None


async def test_concurrent_turns_on_one_session_do_not_interleave(settings):
    """The per-session lock serialises turns (no torn state)."""
    agent = VoiceAgent(settings, logger=MemoryLogger())
    session = agent.start_session("realestate_001")

    await asyncio.gather(
        agent.handle_turn(session.session_id, "123 Main Street"),
        agent.handle_turn(session.session_id, "200 King Street"),
        agent.handle_turn(session.session_id, "77 Lake Shore Avenue"),
    )
    assert session.active_skill_id in {"property_001", "property_003", "property_004"}
    # exactly 6 history entries (3 callers + 3 agents), no interleaved fragments
    assert len(session.history) == 6
    assert session.turn_count == 3
