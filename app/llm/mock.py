"""Offline rule-based LLM used for tests, demos and failure fallbacks.

It never invents property facts: every answer is extracted from the active
skill content the agent injected into ``request.context``.
"""

from __future__ import annotations

import re
import time

from app.llm.base import LLMProvider, LLMRequest, LLMResponse

NOT_IN_LISTINGS = (
    "I don't currently have that property in my available listings. "
    "I can help you with another property or connect you with the right information."
)

GOODBYE_RE = re.compile(
    r"^(bye+\b|goodbye\b|that's all\b|that is all\b|no thanks\b|no,? thanks\b|"
    r"thank(s| you)\b.*$)",
    re.IGNORECASE,
)
GREETING_RE = re.compile(
    r"^(hi|hello|hey|good (morning|afternoon|evening))\b",
    re.IGNORECASE,
)
NAME_BLOCKLIST = {
    "the", "a", "an", "looking", "interested", "calling", "hoping", "thinking",
    "wondering", "just", "here", "so", "yeah", "hi", "hello",
}
NAME_RE = re.compile(r"(?:my name is|this is|i'm|im|i am|it's)\s+([A-Za-z][A-Za-z'\-]{1,30})",
                     re.IGNORECASE)
ASK_NAME_RE = re.compile(r"(what(?:'s| is)?\s+my name|do you (?:know|remember)\s+my name)",
                         re.IGNORECASE)
FIELD_LABELS = {
    "price": "Price",
    "bedrooms": "Bedrooms",
    "bathrooms": "Bathrooms",
    "garage": "Garage",
    "status": "Status",
    "size": "Size",
    "year": "Year Built",
}

WANT_FIELD = {
    "price": r"(price|asking|how much|cost)",
    "bedrooms": r"(bedroom|bed\b|how many beds)",
    "bathrooms": r"(bathroom|bath\b)",
    "garage": r"(garage|parking)",
    "status": r"(available|still for sale|status|on the market)",
    "size": r"(square feet|sq ft|size|big is|how big)",
    "year": r"(year built|how old)",
    "fees": r"(maintenance fee|condo fee|fees)",
}
BUY_RE = re.compile(r"\b(buy|buying|purchase|looking for|budget|under \$)\b", re.IGNORECASE)
SELL_RE = re.compile(r"\b(sell|selling|estimate|my own house|my house)\b", re.IGNORECASE)
VIEWING_RE = re.compile(r"\b(viewing|see it|visit|tour|showing|appointment|this weekend)\b",
                        re.IGNORECASE)
UNKNOWN_PROPERTY_RE = re.compile(r"\b(\d+\s+\w+|\w+\s+street|\w+\s+avenue|\w+\s+road|property)\b",
                                 re.IGNORECASE)


def _skill_line(context: str, label: str) -> str:
    """Return ``Label: value`` from the active skill block."""
    match = re.search(rf"(?im)^\s*{re.escape(label)}:\s*(.+)$", context)
    return match.group(1).strip() if match else ""


def _skill_name(context: str) -> str:
    match = re.search(r"(?m)^name:\s*(.+)$", context, re.IGNORECASE)
    return match.group(1).strip() if match else ""


class MockLLMProvider(LLMProvider):
    """Deterministic, offline responder — no network, no hallucination."""

    name = "mock"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        started = time.monotonic()
        text = self._respond(request)
        return LLMResponse(
            text=text,
            provider=self.name,
            model="rules-v1",
            latency_ms=(time.monotonic() - started) * 1000.0,
        )

    # -- rules --------------------------------------------------------------

    def _respond(self, request: LLMRequest) -> str:
        utterance = request.user_message.strip()
        context = request.context or ""
        meta = request.metadata or {}
        profile_name = (meta.get("profile_name") or "").strip()
        has_skill = "<active_skill>" in context        # 1. Caller just introduced themselves (only when it looks like a name)
        name_match = NAME_RE.search(utterance)
        if name_match and not ASK_NAME_RE.search(utterance):
            captured = name_match.group(1).strip(" ,.!" )
            if captured[:1].isupper() and captured.lower() not in NAME_BLOCKLIST:
                return f"Nice to meet you, {captured}."

        # 2. Caller asks for their name → never leak another session's data
        if ASK_NAME_RE.search(utterance):
            if profile_name:
                return f"I have you as {profile_name} on this call."
            return "I don't have your name on file for this call. How would you like to be addressed?"

        # 3. Farewells and small talk
        if GOODBYE_RE.match(utterance):
            return "You're welcome. Is there anything else I can help you with before you go?"
        if GREETING_RE.search(utterance) and len(utterance.split()) <= 6:
            return "Hello. What can I help you with today?"

        # 4. Field questions against the active skill (never invented)
        for field_name, pattern in WANT_FIELD.items():
            if re.search(pattern, utterance, re.IGNORECASE):
                if not has_skill:
                    break
                if field_name == "fees":
                    value = _skill_line(context, "Maintenance Fees") or _skill_line(
                        context, "Diagnostic Fee"
                    )
                else:
                    value = _skill_line(context, FIELD_LABELS[field_name])
                if value:
                    return self._phrase(field_name, value, profile_name)
                return (
                    f"I don't have that detail in the listing for "
                    f"{_skill_name(context) or 'this property'}. "
                    "Is there something else I can check?"
                )

        # 5. Workflow intents
        if VIEWING_RE.search(utterance):
            if has_skill:
                return "I can help with that. What day works best for you?"
            return "I can help you schedule a viewing. Which property are you interested in?"
        if SELL_RE.search(utterance):
            return "I'd be happy to help with that. What's the address of the property you want to sell?"
        if BUY_RE.search(utterance):
            budget = (meta.get("profile_budget") or "").strip()
            if budget:
                return f"Thanks — I've noted the budget of {budget}. How many bedrooms do you need?"
            return "Understood. What's your budget range, and how many bedrooms do you need?"

        # 6. Unknown property with no active skill
        if not has_skill:
            if UNKNOWN_PROPERTY_RE.search(utterance):
                return NOT_IN_LISTINGS
            return "I can help with that. Could you tell me a bit more about what you're looking for?"

        # 7. Generic follow-up while a skill is active
        name = _skill_name(context) or "this listing"
        price = _skill_line(context, "Price")
        tail = f" It's listed at {price}." if price else ""
        return f"I have the details for {name} in front of me.{tail} What would you like to know next?"

    @staticmethod
    def _phrase(field_name: str, value: str, profile_name: str = "") -> str:
        prefix = f"{profile_name}, " if profile_name and field_name == "price" else ""
        if field_name == "price":
            if prefix:
                return f"{prefix}the asking price is {value}."
            return f"The asking price is {value}."
        if field_name == "bedrooms":
            return f"It has {value} bedrooms."
        if field_name == "bathrooms":
            return f"{value} bathrooms."
        if field_name == "garage":
            if value.lower().startswith("none"):
                return f"There isn't a garage included — the listing says {value}."
            return f"The garage is {value}."
        if field_name == "status":
            return f"The current status is {value}."
        if field_name == "size":
            return f"The size is {value}."
        if field_name == "year":
            return f"It was built in {value}."
        if field_name == "fees":
            return f"That works out to {value}."
        return f"{value}."
