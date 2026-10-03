"""Google Gemini provider (REST, no SDK dependency)."""

from __future__ import annotations

import time

import httpx

from app.llm.base import LLMProvider, LLMRequest, LLMResponse, with_retries


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, model_id: str, api_key: str, max_retries: int = 2,
                 timeout: float = 15.0, client: httpx.AsyncClient | None = None):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for MODEL_PROVIDER=gemini")
        self.model_id = model_id
        self.api_key = api_key
        self.max_retries = max_retries
        self.timeout = timeout
        self._client = client

    async def generate(self, request: LLMRequest) -> LLMResponse:
        started = time.monotonic()
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_id}:generateContent"
        )
        contents = [
            {
                "role": "user" if m.role == "user" else "model",
                "parts": [{"text": m.content}],
            }
            for m in request.messages
            if m.role in ("user", "assistant")
        ]
        system_text = request.system + ("\n\n" + request.context if request.context else "")
        body = {
            "systemInstruction": {"parts": [{"text": system_text}]},
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": request.max_tokens,
                "temperature": request.temperature,
            },
        }

        async def _call():
            async with (self._client or httpx.AsyncClient()) as client:
                resp = await client.post(
                    url, json=body, params={"key": self.api_key},
                    timeout=request.timeout or self.timeout,
                )
                resp.raise_for_status()
                return resp.json()

        try:
            data = await with_retries(_call, retries=self.max_retries)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Gemini call failed: {exc}") from exc

        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model_id,
            latency_ms=(time.monotonic() - started) * 1000.0,
        )
