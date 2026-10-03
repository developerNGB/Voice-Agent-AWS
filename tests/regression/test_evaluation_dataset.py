"""Dataset-driven regression tests (RT-001 … RT-015).

``evaluation_dataset.json`` is the shared evaluation dataset: every scenario
lists its input, expected routing, expected skill and expected behaviour.
Cases marked ``custom`` are exercised by dedicated tests (voice, security,
concurrency) — this driver still asserts they are covered somewhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.agent import VoiceAgent

DATASET = json.loads(
    (Path(__file__).parent / "evaluation_dataset.json").read_text(encoding="utf-8")
)
CASES = DATASET["cases"]


def as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def dataset_ids(case) -> str:
    return case["id"]


def test_dataset_covers_all_fifteen_scenarios():
    ids = {case["id"] for case in CASES}
    assert ids == {f"RT-{n:03d}" for n in range(1, 16)}


def test_custom_cases_declare_coverage():
    custom = [c for c in CASES if c.get("custom")]
    assert {c["id"] for c in custom} == {"RT-006", "RT-007", "RT-014", "RT-015"}
    for case in custom:
        target = case["covered_by"]
        path, _, name = target.partition("::")
        assert (Path(__file__).parents[2] / path).is_file(), f"{case['id']} → {path}"


@pytest.mark.parametrize("case", [c for c in CASES if not c.get("custom")],
                         ids=dataset_ids)
async def test_evaluation_case(case, settings, logger):
    agent = VoiceAgent(settings, logger=logger)
    session = agent.start_session(case.get("agent_id", "realestate_001"))

    for turn_spec in case["turns"]:
        turn = await agent.handle_turn(session.session_id, turn_spec["text"])
        expect = turn_spec.get("expect", {})
        label = f"{case['id']} :: {turn_spec['text']!r}"

        if "route_status" in expect:
            assert turn.route_status == expect["route_status"], \
                f"{label} → status {turn.route_status}, expected {expect['route_status']}"
        if "active_skill" in expect:
            assert turn.active_skill_id == expect["active_skill"], \
                f"{label} → skill {turn.active_skill_id!r}, expected {expect['active_skill']!r}"
        for needle in as_list(expect.get("reply_contains")):
            assert needle in turn.reply, f"{label} → {needle!r} missing from {turn.reply!r}"
        for needle in as_list(expect.get("reply_not_contains")):
            assert needle not in turn.reply, f"{label} → {needle!r} leaked into {turn.reply!r}"
        if "profile_name" in expect:
            assert session.profile.name == expect["profile_name"]
        if "profile_bedrooms" in expect:
            assert session.profile.bedrooms == expect["profile_bedrooms"]
        if "security_event" in expect:
            kinds = [e["type"] for e in session.security_events]
            assert expect["security_event"] in kinds, f"{label} → {kinds}"

    record = await agent.end_session(session.session_id)
    assert record.status == "completed"
    assert record.errors == []
