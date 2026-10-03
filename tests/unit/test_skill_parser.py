"""Skill .txt parsing."""

import pytest

from app.skills.parser import SkillParseError, parse_skill_text


VALID = """SKILL_ID: property_001
TYPE: real_estate_property
NAME: 123 Main Street
DESCRIPTION:
Residential property located at 123 Main Street.

KEYWORDS:
123 Main Street
Main Street
property 123

PURPOSE:
Answer questions about this property.

RULES:
Only provide information contained in this file.

ESCALATION:
If information is unavailable, do not invent it.

CONTENT:

Price:
CAD 899,000

Bedrooms:
4
"""


def test_parses_all_headers():
    skill = parse_skill_text(VALID, agent_id="realestate_001")
    assert skill.skill_id == "property_001"
    assert skill.type == "real_estate_property"
    assert skill.name == "123 Main Street"
    assert "123 Main Street" in skill.keywords
    assert "property 123" in skill.keywords
    assert skill.agent_id == "realestate_001"


def test_content_kept_verbatim_as_data():
    skill = parse_skill_text(VALID)
    assert "Price:" in skill.content
    assert "CAD 899,000" in skill.content
    assert "Bedrooms:" in skill.content


def test_missing_skill_id_rejected():
    broken = VALID.replace("SKILL_ID: property_001\n", "")
    with pytest.raises(SkillParseError):
        parse_skill_text(broken)


def test_missing_content_rejected():
    broken = VALID.split("CONTENT:")[0]
    with pytest.raises(SkillParseError):
        parse_skill_text(broken)


def test_invalid_skill_id_rejected():
    with pytest.raises(SkillParseError):
        parse_skill_text(VALID.replace("property_001", "../../etc/passwd"))


def test_empty_rejected():
    with pytest.raises(SkillParseError):
        parse_skill_text("   ")


def test_context_block_wraps_content_as_data():
    skill = parse_skill_text(VALID)
    block = skill.as_context_block()
    assert block.startswith("<active_skill>")
    assert block.endswith("</active_skill>")
    assert "CAD 899,000" in block
