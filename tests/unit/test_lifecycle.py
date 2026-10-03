"""Session lifecycle state machine."""

import pytest

from app.agent.lifecycle import LifecycleError, SessionLifecycle
from app.models.session import SessionState


@pytest.fixture
def lifecycle():
    return SessionLifecycle()


def test_open_runs_all_stages(lifecycle):
    session = lifecycle.open("realestate_001")
    assert session.state == SessionState.VOICE_CONVERSATION
    assert session.session_id


def test_illegal_transition_rejected(lifecycle):
    session = lifecycle.open("realestate_001")
    with pytest.raises(LifecycleError):
        lifecycle.advance(session, SessionState.SESSION_CLOSED)


def test_full_cycle_to_closed(lifecycle):
    session = lifecycle.open("realestate_001")
    lifecycle.begin_routing(session)
    lifecycle.skill_activated(session)
    lifecycle.end_call(session)
    assert session.state == SessionState.SESSION_CLOSED
    assert session.status == "completed"
    assert session.ended_at > 0


def test_end_call_idempotent(lifecycle):
    session = lifecycle.open("realestate_001")
    lifecycle.end_call(session)
    lifecycle.end_call(session)  # must not raise
    assert session.state == SessionState.SESSION_CLOSED
