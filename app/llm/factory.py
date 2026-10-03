"""Provider factory — switches model vendors with one env var."""

from __future__ import annotations

from app.config import Settings
from app.llm.base import LLMProvider
from app.llm.mock import MockLLMProvider


def build_llm(settings: Settings) -> LLMProvider:
    """Build the configured provider, falling back to the offline mock (with a
    loud warning) when its credentials are missing — so the gateway still boots."""
    provider = (settings.model_provider or "gemini").lower()
    try:
        return _build(settings, provider)
    except ValueError as exc:
        import sys

        print(f"WARNING: {exc} — falling back to MockLLMProvider (offline rules).",
              file=sys.stderr)
        return MockLLMProvider()


def _build(settings: Settings, provider: str) -> LLMProvider:
    if provider == "mock":
        return MockLLMProvider()

    if provider == "bedrock":
        from app.llm.bedrock import BedrockProvider
        return BedrockProvider(
            model_id=settings.bedrock_model_id,
            region=settings.aws_region,
            max_retries=settings.llm_max_retries,
            timeout=settings.llm_timeout_seconds,
        )

    if provider == "openai":
        from app.llm.openai import OpenAIProvider
        return OpenAIProvider(
            model_id=settings.openai_model_id,
            api_key=settings.openai_api_key,
            max_retries=settings.llm_max_retries,
            timeout=settings.llm_timeout_seconds,
        )

    if provider == "gemini":
        from app.llm.gemini import GeminiProvider
        return GeminiProvider(
            model_id=settings.gemini_model_id,
            api_key=settings.gemini_api_key,
            max_retries=settings.llm_max_retries,
            timeout=settings.llm_timeout_seconds,
        )

    raise ValueError(f"Unknown MODEL_PROVIDER: {provider!r}")
