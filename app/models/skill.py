"""Skill domain model."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Skill:
    """A parsed .txt knowledge/skill file."""

    skill_id: str
    type: str
    name: str
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    purpose: str = ""
    rules: str = ""
    escalation: str = ""
    content: str = ""
    agent_id: str = ""
    source: str = ""

    @property
    def header_index_line(self) -> str:
        """One-line description used in the header index sent to the LLM/router."""
        summary = self.description or self.purpose
        if len(summary) > 120:
            summary = summary[:117] + "..."
        return f"{self.skill_id}: {self.name} — {summary}"

    def as_context_block(self) -> str:
        """Render the skill as *data* for prompt injection (never as instructions)."""
        return (
            "<active_skill>\n"
            f"skill_id: {self.skill_id}\n"
            f"name: {self.name}\n"
            f"type: {self.type}\n\n"
            f"{self.content.strip()}\n"
            "</active_skill>"
        )
