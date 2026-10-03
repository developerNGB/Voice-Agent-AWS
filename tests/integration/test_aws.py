"""Tests that need real AWS credentials — skipped unless RUN_AWS_TESTS=1.

Run with::

    RUN_AWS_TESTS=1 aws sts get-caller-identity && pytest -m aws
"""

import os

import pytest

pytestmark = [
    pytest.mark.aws,
    pytest.mark.skipif(
        os.environ.get("RUN_AWS_TESTS") != "1",
        reason="set RUN_AWS_TESTS=1 with valid AWS credentials to run",
    ),
]


def test_s3_skill_store_roundtrip():
    from app.config import get_settings
    from app.skills.loader import S3SkillStore

    settings = get_settings()
    assert settings.skill_bucket, "SKILL_BUCKET must be set"
    store = S3SkillStore(settings.skill_bucket, region=settings.aws_region)
    ids = store.list_skill_ids(settings.agent_id)
    assert ids, "seed skills first: python scripts/seed_skills.py"


def test_dynamodb_call_store_write():
    from app.config import get_settings
    from app.models.call import CallRecord
    from app.storage.dynamodb import DynamoDBCallStore

    settings = get_settings()
    assert settings.dynamodb_table, "DYNAMODB_TABLE must be set"
    store = DynamoDBCallStore(settings.dynamodb_table, region=settings.aws_region)
    store.put_call(CallRecord(
        session_id="aws-test-session",
        agent_id=settings.agent_id,
        caller_id="redacted",
        started_at="2026-01-01T00:00:00+00:00",
        ended_at="2026-01-01T00:00:05+00:00",
        duration_seconds=5,
        skills_used=[],
        turn_count=0,
        routing_events=0,
        errors=[],
        status="aws-test",
    ))


def test_bedrock_provider_call():
    import asyncio

    from app.config import get_settings
    from app.llm.bedrock import BedrockProvider
    from app.llm.base import LLMMessage, LLMRequest

    settings = get_settings()
    provider = BedrockProvider(settings.bedrock_model_id, region=settings.aws_region)
    response = asyncio.run(provider.generate(LLMRequest(
        system="Answer with one short sentence.",
        messages=[LLMMessage(role="user", content="Say hello to a caller.")],
        max_tokens=50,
    )))
    assert response.text
