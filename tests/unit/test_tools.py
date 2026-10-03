"""Tool layer: authorization, lead capture, viewing scheduling."""


async def test_search_skills_scoped_to_agent(agent, session):
    result = agent.tools.search_skills(session, "123 Main Street")
    assert result.ok
    assert result.data["candidates"][0][0] == "property_001"
    # another agent's skills never appear
    assert all(sid.startswith("property_") for sid, _ in result.data["candidates"])


async def test_load_skill_owns_it_or_denies(agent, session):
    ok = agent.tools.load_skill(session, "property_001")
    assert ok.ok and ok.data["name"] == "123 Main Street"

    denied = agent.tools.load_skill(session, "sofa")  # belongs to cleaning_001
    assert not denied.ok
    assert "ACCESS_DENIED" in denied.error


async def test_switch_skill_updates_lock(agent, session):
    agent.tools.switch_skill(session, "property_001")
    assert session.active_skill_id == "property_001"
    result = agent.tools.switch_skill(session, "property_003")
    assert result.ok and session.active_skill_id == "property_003"
    assert session.skills_used == ["property_001", "property_003"]

    denied = agent.tools.switch_skill(session, "refrigerator_abc123")
    assert not denied.ok


async def test_create_lead_requires_contact(agent, session):
    empty = agent.tools.create_lead(session)
    assert not empty.ok

    lead = agent.tools.create_lead(session, name="Peter", budget="800000",
                                   intent="buying")
    assert lead.ok
    assert agent.tools.leads[-1].session_id == session.session_id


async def test_schedule_viewing_needs_active_skill(agent, session):
    no_skill = agent.tools.schedule_viewing(session, "Saturday at 10")
    assert not no_skill.ok and "no active skill" in no_skill.error

    agent.tools.switch_skill(session, "property_001")
    result = agent.tools.schedule_viewing(session, "Saturday at 10:00")
    assert result.ok
    assert result.data["skill_id"] == "property_001"


async def test_lead_captured_during_conversation(agent, session):
    await agent.handle_turn(session.session_id, "My name is Peter, I'm interested in 123 Main Street")
    assert session.profile.name == "Peter"
    assert agent.tools.leads
    assert agent.tools.leads[-1].property_interest == "property_001"
    # only one lead per session even after more turns
    count = len(agent.tools.leads)
    await agent.handle_turn(session.session_id, "What's the price?")
    assert len(agent.tools.leads) == count
