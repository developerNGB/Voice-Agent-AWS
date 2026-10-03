"""Candidate search over the skill header index."""

from __future__ import annotations

from app.models.skill import Skill

# -- spoken-number normalisation -------------------------------------------
# STT renders "123 Main Street" as "one twenty three main street".  Header
# keywords carry digits, so the utterance must be converted back or
# address matching misses (and the router asks a pointless clarification).

_ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
         "six": 6, "seven": 7, "eight": 8, "nine": 9}
_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
          "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
          "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40,
         "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
         "ninety": 90}
_HUNDRED = {"hundred": 100, "thousand": 1000}
_SKIP = {"and", "a"}


def _run_to_digits(run: list[str]) -> str:
    """"one twenty three" → "123", "two hundred twelve" → "212".

    Standalone digits before another number word start a *new* group
    (address style concatenation); tens/teens/hundreds fold into the
    current group (place value).
    """
    parts: list[str] = []
    cur = 0
    active = False
    lone = False          # current group ends with a standalone 0-9 digit

    def flush() -> None:
        nonlocal cur, active, lone
        if active:
            parts.append(str(cur))
        cur, active, lone = 0, False, False

    for word in run:
        if word in _SKIP:
            continue
        if word in _HUNDRED:
            if active:
                cur = cur * _HUNDRED[word]
                lone = False
            continue
        if word in _ONES:
            value, is_lone = _ONES[word], True
        elif word in _TEENS:
            value, is_lone = _TEENS[word], False
        elif word in _TENS:
            value, is_lone = _TENS[word], False
        else:
            flush()
            continue

        if active and lone:
            flush()                      # "one" then "twenty" → new group
        if active and not lone:
            cur += value                 # place value inside one group
        else:
            cur = value
        active = True
        lone = is_lone
    flush()
    return "".join(parts)


def normalize_spoken_numbers(text: str) -> str:
    """Convert runs of number words in *text* to digits (other words kept).

    Punctuation on number-run tokens is dropped — the result is only used
    for routing/scoring, never shown verbatim to the caller.
    """
    if not text:
        return text
    out: list[str] = []
    run: list[str] = []
    numberish = _ONES.keys() | _TEENS.keys() | _TENS.keys() | _HUNDRED.keys()
    punct = ".,!?;:\"'()"
    for token in text.split():
        core = token.strip(punct).lower()
        if core in numberish or (run and core in _SKIP):
            run.append(core)
        else:
            if run:
                out.append(_run_to_digits(run))
                run = []
            out.append(token)
    if run:
        out.append(_run_to_digits(run))
    return " ".join(out)



def candidate_search(index: dict[str, Skill], query: str) -> list[Skill]:
    """Return every skill whose header *could* match the request.

    Cheap pre-filter: any keyword/name/description token overlap.  Precise
    scoring happens later in :mod:`app.router.scorer`.
    """
    from app.router.scorer import tokenize, STOPWORDS

    query = normalize_spoken_numbers(query)
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
