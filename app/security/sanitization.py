"""Input sanitization: prompt-injection detection and PII redaction."""

from __future__ import annotations

import hashlib
import re

# --- Prompt injection -------------------------------------------------------

INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
        r"disregard\s+(all\s+)?(previous|prior|system)\s+",
        r"system\s*override",
        r"you\s+are\s+now\s+(a|in)\s+",
        r"new\s+instructions\s*:",
        r"show\s+me\s+all\s+(other\s+)?(properties|skills|files|listings|agents)",
        r"list\s+all\s+(skills|files|properties|agents|sessions)",
        r"reveal\s+(your\s+)?(system\s+prompt|instructions|all\s+skills)",
        r"forget\s+(everything|all\s+previous|your\s+instructions)",
        r"pretend\s+(you\s+are|to\s+be)\s+",
        r"act\s+as\s+if\s+you\s+have\s+no\s+restrictions",
        r"print\s+the\s+contents\s+of\s+",
        r"\bsudo\s+",
        r"developer\s+mode",
    )
]

INJECTION_RESPONSE = (
    "I can't do that. I can only help with the listing we're discussing, "
    "or find another property for you. What would you like to know?"
)


def contains_injection(text: str) -> bool:
    if not text:
        return False
    return any(p.search(text) for p in INJECTION_PATTERNS)


# --- PII redaction ----------------------------------------------------------

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}(?!\d)")


def redact_text(text: str) -> str:
    """Best-effort redaction of direct identifiers before logging."""
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _PHONE_RE.sub("[PHONE]", text)
    return text


def hash_caller_id(raw: str, salt: str = "freebuff-voice-agent") -> str:
    """One-way hashed caller id for logs (never store the raw number)."""
    if not raw:
        return "redacted"
    digest = hashlib.sha256(f"{salt}:{raw}".encode("utf-8")).hexdigest()
    return digest[:16]


def sanitize_for_log(value: str, max_len: int = 500) -> str:
    value = redact_text(value or "")
    return value if len(value) <= max_len else value[: max_len - 3] + "..."
