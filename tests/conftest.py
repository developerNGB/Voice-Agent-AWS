"""Shared fixtures: agent under test always uses the mock LLM + memory logs."""

from __future__ import annotations

import pytest

from app.agent.agent import VoiceAgent
from app.config import Settings
from app.router.skill_router import SkillRouter
from app.skills.loader import LocalSkillStore
from app.skills.registry import SkillRegistry
from app.storage.logs import MemoryLogger


@pytest.fixture
def settings() -> Settings:
    return Settings(
        model_provider="mock",
        skill_store="local",
        skill_root="skills",
        stt_provider="mock",
        tts_provider="mock",
        dynamodb_table="",
        twilio_validate_signature=False,
    )


@pytest.fixture
def logger() -> MemoryLogger:
    return MemoryLogger()


@pytest.fixture
def store() -> LocalSkillStore:
    return LocalSkillStore("skills")


@pytest.fixture
def registry(store) -> SkillRegistry:
    return SkillRegistry(store)


@pytest.fixture
def router(registry, settings) -> SkillRouter:
    return SkillRouter(registry, settings)


@pytest.fixture
def agent(settings, logger) -> VoiceAgent:
    return VoiceAgent(settings, logger=logger)


@pytest.fixture
async def session(agent):
    sess = agent.start_session("realestate_001")
    yield sess
    if not sess.closed:
        await agent.end_session(sess.session_id)


async def run_dialogue(agent, session, lines: list[str]):
    """Feed utterances in order; returns the list of AgentTurn results."""
    turns = []
    for line in lines:
        turns.append(await agent.handle_turn(session.session_id, line))
    return turns
