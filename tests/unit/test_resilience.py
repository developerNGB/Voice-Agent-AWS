"""Resilience: LLM failure → retry → safe fallback, never a stack trace."""

import pytest

from app.agent.agent import LLM_FAILURE_RESPONSE, VoiceAgent
from app.llm.base import LLMProvider, LLMRequest, LLMResponse, with_retries
from app.storage.logs import MemoryLogger


class FailingLLM(LLMProvider):
    name = "failing"

    def __init__(self):
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        raise RuntimeError("simulated outage")


async def test_llm_failure_returns_safe_fallback(settings):
    failing = FailingLLM()
    agent = VoiceAgent(settings, llm=failing, logger=MemoryLogger())
    session = agent.start_session("realestate_001")

    turn = await agent.handle_turn(session.session_id, "Tell me about 123 Main Street")

    assert turn.reply == LLM_FAILURE_RESPONSE
    assert "Traceback" not in turn.reply
    assert "simulated outage" not in turn.reply       # never leak internals
    assert session.errors and "llm_failure" in session.errors[0]
    # session survives the failure
    turn2 = await agent.handle_turn(session.session_id, "What's the price?")
    assert turn2.reply == LLM_FAILURE_RESPONSE
    await agent.end_session(session.session_id)


async def test_with_retries_retries_then_succeeds():
    attempts = {"n": 0}

    def operation():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ValueError("flaky")
        return "ok"

    result = await with_retries(operation, retries=3, base_delay=0.01)
    assert result == "ok"
    assert attempts["n"] == 3


async def test_with_retries_gives_up():
    def always_fails():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        await with_retries(always_fails, retries=1, base_delay=0.01)


async def test_clarification_happens_even_if_llm_is_down(settings):
    """Routing decisions are deterministic and must not depend on the LLM."""
    agent = VoiceAgent(settings, llm=FailingLLM(), logger=MemoryLogger())
    session = agent.start_session("realestate_001")
    turn = await agent.handle_turn(session.session_id, "Tell me about the house on Main.")
    assert turn.route_status == "clarify"
    assert "123 Main Street" in turn.reply and "125 Main Street" in turn.reply
    await agent.end_session(session.session_id)
