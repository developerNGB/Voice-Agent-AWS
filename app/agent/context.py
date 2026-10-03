"""Conversation context extraction (PII-minimised)."""

from __future__ import annotations

import re

from app.models.session import CallerProfile, Session

NAME_RE = re.compile(
    r"(?:my name is|this is|i'm|im|i am|it's|my wife is|my husband is)\s+([A-Za-z][A-Za-z'\-]{1,30})",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)")
BUDGET_RE = re.compile(r"(?:under|below|budget(?:\s+of)?|up to|around|about)?\s*\$?\s*([\d]{2,3}(?:,\d{3})+|\d{6,9})",
                       re.IGNORECASE)
BEDROOMS_RE = re.compile(r"(\d+|two|three|four|five|six)\s+bedrooms?", re.IGNORECASE)
TIMELINE_RE = re.compile(
    r"(this weekend|next week|asap|immediately|in a month|by the end of (?:the )?month|before \w+)",
    re.IGNORECASE,
)
SELL_RE = re.compile(r"\b(sell|selling|list my|my house is)\b", re.IGNORECASE)
BUY_RE = re.compile(r"\b(buy|buying|purchase)\b", re.IGNORECASE)
VIEW_RE = re.compile(r"\b(viewing|see it|visit|tour|showing)\b", re.IGNORECASE)


class ContextManager:
    """Extracts caller facts without interrupting the conversation."""

    def extract(self, session: Session, text: str) -> list[str]:
        """Update ``session.profile``; returns the names of changed fields."""
        changed: list[str] = []
        profile: CallerProfile = session.profile

        name_match = NAME_RE.search(text)
        if name_match and not re.search(r"what(?:'s| is) my name", text, re.IGNORECASE):
            name = name_match.group(1).strip(" ,.!")
            if name.lower() not in {"the", "a", "looking", "interested", "calling"}:
                if profile.name != name:
                    profile.name = name
                    changed.append("name")

        email_match = EMAIL_RE.search(text)
        if email_match and profile.email != email_match.group(0):
            profile.email = email_match.group(0)
            changed.append("email")

        phone_match = PHONE_RE.search(text)
        if phone_match and profile.phone != phone_match.group(0):
            profile.phone = phone_match.group(0)
            changed.append("phone")

        budget_match = BUDGET_RE.search(text)
        if budget_match and re.search(r"\$|\bunder\b|\bbudget\b|\bbelow\b", text, re.IGNORECASE):
            budget = budget_match.group(1)
            if profile.budget != budget:
                profile.budget = budget
                changed.append("budget")

        bed_match = BEDROOMS_RE.search(text)
        if bed_match and profile.bedrooms != bed_match.group(1).lower():
            profile.bedrooms = bed_match.group(1).lower()
            changed.append("bedrooms")

        time_match = TIMELINE_RE.search(text)
        if time_match and profile.timeline != time_match.group(1).lower():
            profile.timeline = time_match.group(1).lower()
            changed.append("timeline")

        if VIEW_RE.search(text):
            profile.intent = "viewing"
            changed.append("intent")
        elif SELL_RE.search(text):
            profile.intent = "selling"
            changed.append("intent")
        elif BUY_RE.search(text) and profile.intent not in ("buying", "viewing"):
            profile.intent = "buying"
            changed.append("intent")

        return list(dict.fromkeys(changed))


def context_metadata(session: Session) -> dict:
    """Metadata handed to providers (used by the mock LLM and analytics)."""
    return {
        "profile_name": session.profile.name,
        "profile_budget": session.profile.budget,
        "profile_bedrooms": session.profile.bedrooms,
        "profile_intent": session.profile.intent,
        "profile_timeline": session.profile.timeline,
        "active_skill": session.active_skill_id,
    }
