"""Skill router behaviour: activate, clarify, keep, switch, none."""

import pytest

from app.models.session import Session


@pytest.fixture
def session():
    return Session(session_id="s1", agent_id="realestate_001")


def test_exact_address_activates(router, session):
    decision = router.route("realestate_001", "I'm asking about 123 Main Street.", session)
    assert decision.status == "activate"
    assert decision.skill_id == "property_001"
    assert decision.candidates[0][1] >= 0.9


def test_ambiguous_street_name_asks_for_clarification(router, session):
    decision = router.route("realestate_001", "Tell me about the house on Main.", session)
    assert decision.status == "clarify"
    ids = [sid for sid, _ in decision.candidates]
    assert "property_001" in ids and "property_002" in ids
    assert session.active_skill_id == ""  # nothing activated on ambiguity


def test_disambiguating_answer_activates(router, session):
    router.route("realestate_001", "Tell me about the house on Main.", session)
    decision = router.route("realestate_001", "123 Main.", session)
    assert decision.status == "activate"
    assert decision.skill_id == "property_001"
    router.activate_skill("realestate_001", decision.skill_id, session)
    assert session.active_skill_id == "property_001"
    assert session.pending_candidates == []


def test_skill_lock_keeps_active_skill_for_followups(router, session):
    router.activate_skill("realestate_001", "property_001", session)
    decision = router.route("realestate_001", "How many bedrooms does it have?", session)
    assert decision.status == "keep"
    assert decision.skill_id == "property_001"


def test_topic_change_switches_skill(router, session):
    router.activate_skill("realestate_001", "property_001", session)
    decision = router.route("realestate_001", "What about 200 King Street?", session)
    assert decision.status == "activate"
    router.activate_skill("realestate_001", decision.skill_id, session)
    assert session.active_skill_id == "property_003"
    assert session.skills_used == ["property_001", "property_003"]


def test_no_match_without_active_skill(router, session):
    decision = router.route("realestate_001", "What areas do you cover?", session)
    assert decision.status == "none"
    assert decision.skill_id == ""


def test_number_mismatch_does_not_activate(router, session):
    decision = router.route("realestate_001", "Tell me about 999 Queen Street.", session)
    assert decision.status in ("none", "keep")
    assert decision.status != "activate"


def test_header_index_needs_only_metadata(router):
    index = router.load_metadata("realestate_001")
    assert set(index) >= {"property_001", "property_002", "property_003", "property_004"}
    lines = router.registry.header_lines("realestate_001")
    assert any("123 Main Street" in line for line in lines)


def test_unknown_agent_has_no_skills(router):
    assert router.load_metadata("nobody_999") == {}


def test_foreign_skill_cannot_be_activated(router, session):
    from app.security.exceptions import AccessDeniedError

    # `sofa` exists, but only for cleaning_001 — not for realestate_001
    with pytest.raises(AccessDeniedError):
        router.activate_skill("realestate_001", "sofa", session)
