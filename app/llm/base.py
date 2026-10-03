"""LLM provider abstraction.

Every provider implements the same interface so the model layer can be
swapped (``bedrock`` / ``openai`` / ``gemini`` / ``mock``) without touching
the agent, router or voice code.
"""

from __future__ import annotations

import abc
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class LLMMessage:
    role: str          # system | user | assistant
    content: str


@dataclass
class LLMRequest:
    system: str
    messages: list[LLMMessage] = field(default_factory=list)
    context: str = ""                       # session context + active skill (data)
    metadata: dict[str, Any] = field(default_factory=dict)
    max_tokens: int = 400
    temperature: float = 0.3
    timeout: float | None = None

    @property
    def user_message(self) -> str:
        for msg in reversed(self.messages):
            if msg.role == "user":
                return msg.content
        return ""


@dataclass
class LLMResponse:
    text: str
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    fallback: bool = False
    error: str = ""


class LLMProvider(abc.ABC):
    """One method to rule them all: ``generate``."""

    name = "llm"

    @abc.abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError

    async def stream(self, request: LLMRequest):  # pragma: no cover - optional
        """Default: no token streaming, yield one completed response."""
        yield await self.generate(request)


class LLMError(RuntimeError):
    """Raised when a provider keeps failing after retries."""


async def with_retries(
    operation: Callable[[], Any],
    *,
    retries: int = 2,
    base_delay: float = 0.4,
    timeout: float | None = None,
) -> Any:
    """Run a (possibly sync) operation with timeout + exponential backoff.

    ``operation`` may be a zero-arg callable or a coroutine function; sync
    callables run in a worker thread so the event loop is never blocked.
    """
    attempts = max(1, retries + 1)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            result = operation()
            if asyncio.iscoroutine(result):
                if timeout:
                    result = asyncio.wait_for(result, timeout=timeout)
                return await result
            return result
        except Exception as exc:  # noqa: BLE001 - normalised into LLMError by callers
            last_error = exc
            if attempt < attempts - 1:
                await asyncio.sleep(base_delay * (2 ** attempt))
    assert last_error is not None
    raise last_error


def now_ms() -> float:
    return time.monotonic() * 1000.0
