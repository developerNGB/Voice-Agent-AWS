"""Scorer behaviour."""

from app.router.scorer import score_all, score_skill
from app.skills.loader import LocalSkillStore
from app.skills.registry import SkillRegistry


def skills():
    registry = SkillRegistry(LocalSkillStore("skills"))
    return registry.header_index("realestate_001")


def test_exact_phrase_scores_high():
    index = skills()
    score = score_skill(index["property_001"], "what about 123 Main Street?")
    assert score >= 0.9


def test_wrong_number_scores_low():
    index = skills()
    score = score_skill(index["property_002"], "123 Main Street")
    assert score < 0.75


def test_partial_street_match_is_ambiguous_band():
    index = skills()
    score = score_skill(index["property_001"], "the house on Main")
    assert 0.45 <= score < 0.75


def test_unrelated_query_scores_near_zero():
    index = skills()
    score = score_skill(index["property_001"], "what areas do you cover?")
    assert score < 0.45


def test_sorted_best_first():
    index = skills()
    scored = score_all(list(index.values()), "123 Main Street")
    assert scored[0][0] == "property_001"
    assert scored[0][1] >= scored[-1][1]
