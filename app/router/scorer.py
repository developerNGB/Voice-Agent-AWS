"""Relevance scoring for skill candidates.

Scores are in ``[0, 1]``:

* exact keyword/name substring match        ~0.95
* street/keyword number agreement           ~0.92
* number disagreement                       ~0.35
* partial token overlap (ambiguous request) 0.45 – 0.75

Routing thresholds live in :class:`app.config.Settings`
(``SKILL_ACTIVATE_THRESHOLD``, ``SKILL_CLARIFY_THRESHOLD``).
"""

from __future__ import annotations

import re

from app.models.skill import Skill

NUM_RE = re.compile(r"\d+")

STOPWORDS = {
    "the", "a", "an", "about", "tell", "me", "house", "property", "properties",
    "home", "listing", "listings", "i", "want", "to", "know", "on", "in", "of",
    "for", "is", "it", "and", "please", "info", "information", "at", "my",
    "this", "that", "what", "whats", "how", "do", "does", "can", "you", "we",
    "are", "there", "any", "some", "with", "or", "call", "calling", "talk",
    "speaking", "looking", "get", "need",
    # generic address words: they appear in every listing, so they never discriminate
    "street", "st", "avenue", "ave", "road", "rd", "lane", "ln", "drive", "dr",
    "court", "ct", "place", "pl", "way", "boulevard", "blvd", "terrace", "close",
}


def tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def score_skill(skill: Skill, query: str) -> float:
    """Score how well a skill matches the caller's request."""
    q_norm = _normalize(query)
    q_tokens = tokenize(query) - STOPWORDS
    q_digits = set(NUM_RE.findall(query))
    best = 0.0

    for kw in [skill.name, *skill.keywords]:
        kw_norm = _normalize(kw)
        if not kw_norm:
            continue

        # 1) exact phrase present in the request → confident match, but a
        #    number-less keyword ("Main Street") is not discriminating when the
        #    caller also said a number, so it is capped below the threshold.
        if kw_norm in q_norm:
            kw_has_digits = bool(NUM_RE.findall(kw))
            if q_digits and not kw_has_digits:
                best = max(best, 0.60)
            else:
                best = max(best, 0.95)
            continue

        kw_tokens = tokenize(kw) - STOPWORDS
        if not kw_tokens:
            continue
        overlap = q_tokens & kw_tokens
        if not overlap:
            continue
        kw_digits = set(NUM_RE.findall(kw))

        if q_digits and kw_digits:
            # a number was said: it must agree with this skill's number
            best = max(best, 0.92 if q_digits <= kw_digits else 0.35)
        else:
            ratio = len(overlap) / len(kw_tokens)
            raw = 0.45 + 0.30 * ratio
            if not kw_digits:
                # a generic keyword ("house on Main Street") never discriminates
                raw = min(raw, 0.55)
            elif not q_digits:
                # caller named the street but no number → ambiguous
                raw = min(raw, 0.70)
            best = max(best, raw)

    if best < 0.45:
        # weak fallback: description/token overlap only
        desc_tokens = tokenize(skill.description) - STOPWORDS
        if desc_tokens and q_tokens and (q_tokens & desc_tokens):
            ratio = len(q_tokens & desc_tokens) / len(desc_tokens)
            best = max(best, min(0.40, 0.20 + 0.30 * ratio))

    return round(min(best, 0.99), 3)


def score_all(skills: list[Skill], query: str) -> list[tuple[str, float]]:
    """Score candidates and return them sorted best-first."""
    scored = [(s.skill_id, score_skill(s, query)) for s in skills]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored
