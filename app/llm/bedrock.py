"""Amazon Bedrock provider (AWS-native default)."""

from __future__ import annotations


from app.llm.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    with_retries,
)


class BedrockProvider(LLMProvider):
    """Calls Bedrock ``converse`` through boto3 (region from settings)."""

    name = "bedrock"

    def __init__(self, model_id: str, region: str = "ca-central-1",
                 max_retries: int = 2, timeout: float = 15.0, client=None):
        if not model_id:
            raise ValueError("BEDROCK_MODEL_ID is required")
        self.model_id = model_id
        self.region = region
        self.max_retries = max_retries
        self.timeout = timeout
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    async def generate(self, request: LLMRequest) -> LLMResponse:
        import time

        started = time.monotonic()

        def _call():
            system_blocks = [{"text": request.system}] if request.system else []
            messages = [
                {"role": m.role, "content": [{"text": (request.context + "\n\n" + m.content)
                                              if m.role == "user" and request.context
                                              else m.content}]}
                for m in request.messages
                if m.role in ("user", "assistant")
            ]
            kwargs = {
                "modelId": self.model_id,
                "system": system_blocks,
                "messages": messages,
                "inferenceConfig": {
                    "maxTokens": request.max_tokens,
                    "temperature": request.temperature,
                },
            }
            return self.client.converse(**kwargs)

        try:
            response = await with_retries(
                _call,
                retries=self.max_retries,
                timeout=request.timeout or self.timeout,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the agent's fallback
            raise RuntimeError(f"Bedrock call failed: {exc}") from exc

        chunks = response.get("output", {}).get("message", {}).get("content", [])
        text = "".join(c.get("text", "") for c in chunks if "text" in c).strip()
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model_id,
            latency_ms=(time.monotonic() - started) * 1000.0,
        )
