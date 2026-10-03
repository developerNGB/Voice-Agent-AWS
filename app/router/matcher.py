"""Candidate search over the skill header index."""

from __future__ import annotations

from app.models.skill import Skill


def candidate_search(index: dict[str, Skill], query: str) -> list[Skill]:
    """Return every skill whose header *could* match the request.

    Cheap pre-filter: any keyword/name/description token overlap.  Precise
    scoring happens later in :mod:`app.router.scorer`.
    """
    from app.router.scorer import tokenize, STOPWORDS

    q_tokens = tokenize(query) - STOPWORDS
    if not q_tokens:
        # keep digits-only queries working (e.g. "123")
        from app.router.scorer import NUM_RE

        q_tokens = set(NUM_RE.findall(query))
    if not q_tokens:
        return []

    candidates: list[Skill] = []
    for skill in index.values():
        haystack = tokenize(
            " ".join([skill.name, skill.description] + skill.keywords)
        ) - STOPWORDS
        if q_tokens & haystack or q_tokens & set(skill.keywords):
            candidates.append(skill)
    return candidates
