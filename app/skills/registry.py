"""Header index over an agent's skill files.

The registry only parses the *headers* it needs for routing and loads full
skill content lazily — so the whole knowledge base never lands in a prompt.
"""

from __future__ import annotations

import threading

from app.models.skill import Skill
from app.skills.loader import SkillStore


class SkillRegistry:
    """Per-agent skill index with lazy content loading."""

    def __init__(self, store: SkillStore):
        self.store = store
        self._headers: dict[str, dict[str, Skill]] = {}
        self._lock = threading.Lock()

    def refresh(self, agent_id: str) -> int:
        """(Re)build the header index for an agent. Returns skill count."""
        skills: dict[str, Skill] = {}
        for skill_id in self.store.list_skill_ids(agent_id):
            try:
                skills[skill_id] = self.store.load(agent_id, skill_id)
            except Exception:  # noqa: BLE001 - a broken file must not kill routing
                continue
        with self._lock:
            self._headers[agent_id] = skills
        return len(skills)

    def _ensure(self, agent_id: str) -> dict[str, Skill]:
        if agent_id not in self._headers:
            self.refresh(agent_id)
        return self._headers.get(agent_id, {})

    def header_index(self, agent_id: str) -> dict[str, Skill]:
        """skill_id -> parsed header (content included, but only used for routing)."""
        return dict(self._ensure(agent_id))

    def header_lines(self, agent_id: str) -> list[str]:
        """Human-readable header index (used in prompts/tests)."""
        return [s.header_index_line for s in self._ensure(agent_id).values()]

    def get(self, agent_id: str, skill_id: str) -> Skill:
        """Load a skill the agent is authorized for (raises on unknown/denied)."""
        skills = self._ensure(agent_id)
        if skill_id not in skills:
            # re-check the store directly to give a precise error
            return self.store.load(agent_id, skill_id)
        return skills[skill_id]

    def known(self, agent_id: str, skill_id: str) -> bool:
        return skill_id in self._ensure(agent_id)

    def list_ids(self, agent_id: str) -> list[str]:
        return sorted(self._ensure(agent_id))
