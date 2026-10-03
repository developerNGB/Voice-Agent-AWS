"""Layer 1 + Layer 3 isolation: path and identifier validation.

Every read of a skill file must pass through :func:`safe_join`, which
guarantees the resolved path stays inside the agent's own namespace.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from app.security.exceptions import AccessDeniedError

AGENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,31}$")
SKILL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")

_TRAVERSAL = ("..", "\\", "\x00")


def validate_agent_id(agent_id: str) -> str:
    """Agent ids are lower-case identifiers — no separators, no traversal."""
    if not isinstance(agent_id, str) or not AGENT_ID_RE.match(agent_id):
        raise AccessDeniedError(f"Invalid agent_id: {agent_id!r}")
    return agent_id


def validate_skill_id(skill_id: str) -> str:
    """Skill ids are slugs — critically, they can never contain a path separator."""
    if not isinstance(skill_id, str) or not SKILL_ID_RE.match(skill_id):
        raise AccessDeniedError(f"Invalid skill_id: {skill_id!r}")
    if any(tok in skill_id for tok in _TRAVERSAL):
        raise AccessDeniedError(f"Invalid skill_id: {skill_id!r}")
    return skill_id


def safe_join(root: str | Path, *parts: str) -> Path:
    """Join path parts under ``root`` and refuse anything that escapes it."""
    root_path = Path(root).resolve()
    for part in parts:
        if not isinstance(part, str) or any(tok in part for tok in _TRAVERSAL) or "/" in part:
            # allow callers to pass "file.txt" only; separators are added by us
            if isinstance(part, str) and "/" not in part and "\\" not in part and ".." not in part:
                continue
            raise AccessDeniedError(f"Path traversal rejected: {part!r}")
    candidate = root_path.joinpath(*parts).resolve()
    if candidate != root_path and root_path not in candidate.parents:
        raise AccessDeniedError(f"Path escapes namespace: {candidate}")
    return candidate


def validate_object_key(prefix: str, agent_id: str, skill_id: str) -> str:
    """Build and validate an object key such as ``agents/<agent>/<skill>.txt``."""
    validate_agent_id(agent_id)
    validate_skill_id(skill_id)
    key = str(PurePosixPath(prefix) / agent_id / f"{skill_id}.txt")
    if ".." in key or "\\" in key:
        raise AccessDeniedError(f"Invalid object key: {key}")
    return key


def assert_same_agent(requester_agent_id: str, resource_agent_id: str) -> None:
    """Cross-agent access is always denied."""
    if requester_agent_id != resource_agent_id:
        raise AccessDeniedError(
            f"Agent {requester_agent_id!r} may not access resources of "
            f"{resource_agent_id!r}"
        )
