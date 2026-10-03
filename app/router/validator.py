"""Validation of routing decisions before a skill is activated."""

from __future__ import annotations

from app.models.skill import Skill
from app.security.isolation import validate_agent_id, validate_skill_id


def validate_activation(agent_id: str, skill_id: str, index: dict[str, Skill]) -> str:
    """Ensure the skill exists in *this agent's* index before activation.

    Raises ``AccessDeniedError`` for anything outside the namespace — this is
    the last line of defence even if a router bug slipped a foreign skill id in.
    """
    from app.security.exceptions import AccessDeniedError

    validate_agent_id(agent_id)
    validate_skill_id(skill_id)
    if skill_id not in index:
        raise AccessDeniedError(
            f"Skill {skill_id!r} is not in agent {agent_id!r}'s namespace"
        )
    return skill_id


def margin_ok(scored: list[tuple[str, float]], margin: float = 0.10) -> bool:
    """True when the top candidate clearly beats the runner-up."""
    if len(scored) < 2:
        return True
    top, second = scored[0][1], scored[1][1]
    return (top - second) >= margin
