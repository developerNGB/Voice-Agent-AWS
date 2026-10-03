"""Parser for the structured ``.txt`` skill file format.

Format::

    SKILL_ID: property_001
    TYPE: real_estate_property
    NAME: 123 Main Street
    DESCRIPTION:
    Multi-line description...
    KEYWORDS:
    keyword one
    keyword two
    PURPOSE: ...
    RULES: ...
    ESCALATION: ...
    CONTENT:
    <free-form knowledge body, everything to end of file>

Header keys are always upper-case identifiers.  Everything after ``CONTENT:``
is treated as opaque data — never as instructions.
"""

from __future__ import annotations

import re

from app.models.skill import Skill

HEADER_RE = re.compile(r"^([A-Z][A-Z0-9_]*):\s*(.*)$")
KNOWN_FIELDS = ("SKILL_ID", "TYPE", "NAME", "DESCRIPTION", "KEYWORDS",
                "PURPOSE", "RULES", "ESCALATION", "CONTENT")

SKILL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")


class SkillParseError(ValueError):
    """Raised when a skill file does not follow the expected format."""


def _split_values(raw: str) -> list[str]:
    """Keywords may be newline- or comma-separated."""
    values: list[str] = []
    for line in raw.splitlines():
        for part in line.split(","):
            part = part.strip()
            if part:
                values.append(part)
    return values


def parse_skill_text(text: str, agent_id: str = "", source: str = "") -> Skill:
    """Parse skill file content into a :class:`Skill`."""
    if not isinstance(text, str) or not text.strip():
        raise SkillParseError("Empty skill file")

    fields: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    content_lines: list[str] | None = None

    def flush() -> None:
        nonlocal current, buffer
        if current is not None:
            fields[current] = "\n".join(buffer).strip()
        buffer = []

    for line in text.splitlines():
        if content_lines is not None:
            content_lines.append(line)
            continue
        match = HEADER_RE.match(line)
        if match and match.group(1) in KNOWN_FIELDS:
            key, inline = match.group(1), match.group(2)
            flush()
            current = key
            if key == "CONTENT":
                content_lines = [inline] if inline.strip() else []
            else:
                buffer = [inline] if inline.strip() else []
        elif current is not None:
            buffer.append(line)
        # lines before the first header are ignored (comments/blank)

    if content_lines is None:
        flush()
        content = fields.get("CONTENT", "")
    else:
        content = "\n".join(content_lines).strip()

    skill_id = fields.get("SKILL_ID", "").strip()
    if not skill_id:
        raise SkillParseError(f"Missing SKILL_ID in {source or 'skill text'}")
    if not SKILL_ID_RE.match(skill_id):
        raise SkillParseError(f"Invalid SKILL_ID {skill_id!r} (allowed: a-z 0-9 _ -)")
    if not content:
        raise SkillParseError(f"Missing CONTENT in skill {skill_id}")

    return Skill(
        skill_id=skill_id,
        type=fields.get("TYPE", "").strip() or "generic",
        name=fields.get("NAME", "").strip() or skill_id,
        description=fields.get("DESCRIPTION", "").strip(),
        keywords=_split_values(fields.get("KEYWORDS", "")),
        purpose=fields.get("PURPOSE", "").strip(),
        rules=fields.get("RULES", "").strip(),
        escalation=fields.get("ESCALATION", "").strip(),
        content=content,
        agent_id=agent_id,
        source=source,
    )
