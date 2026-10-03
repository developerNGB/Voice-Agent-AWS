"""Application configuration.

All configuration comes from environment variables (optionally loaded from a
``.env`` file).  No credentials are ever hard-coded in source.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields

try:  # pragma: no cover - dotenv is optional at runtime
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    if not value or value.startswith("#"):
        # empty or an inline-comment-only value ("KEY=   # explanation")
        return default
    return value


@dataclass
class Settings:
    """Runtime configuration.  Every field has a safe local default."""

    # General
    aws_region: str = "ca-central-1"
    agent_id: str = "realestate_001"
    log_dir: str = "logs"
    skill_store: str = "local"          # local | s3
    skill_root: str = "skills"
    skill_bucket: str = ""
    dynamodb_table: str = ""

    # LLM
    model_provider: str = "bedrock"      # bedrock | openai | gemini | mock
    bedrock_model_id: str = "amazon.nova-lite-v1:0"
    openai_model_id: str = "gpt-4o-mini"
    gemini_model_id: str = "gemini-2.0-flash"
    openai_api_key: str = ""
    gemini_api_key: str = ""

    # Voice
    stt_provider: str = "mock"           # mock | vosk | aws
    tts_provider: str = "mock"           # mock | edge | aws
    polly_voice_id: str = "Joanna"
    polly_engine: str = "neural"
    vosk_model_path: str = "models/vosk-model-small-en-us-0.15"
    edge_voice: str = "en-CA-ClaraNeural"

    # Routing
    skill_activate_threshold: float = 0.75
    skill_clarify_threshold: float = 0.45

    # Resilience
    llm_timeout_seconds: float = 15.0
    llm_max_retries: int = 2

    # Telephony
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_validate_signature: bool = False
    signalwire_project_id: str = ""
    signalwire_token: str = ""
    signalwire_validate: bool = False
    public_base_url: str = ""

    # Deployment
    agentcore_runtime_name: str = "realestate-voice-agent"

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment variables."""
        kwargs: dict = {
            "aws_region": _env("AWS_REGION", "ca-central-1"),
            "agent_id": _env("AGENT_ID", "realestate_001"),
            "log_dir": _env("LOG_DIR", "logs"),
            "skill_store": _env("SKILL_STORE", "local"),
            "skill_root": _env("SKILL_ROOT", "skills"),
            "skill_bucket": _env("SKILL_BUCKET", ""),
            "dynamodb_table": _env("DYNAMODB_TABLE", ""),
            "model_provider": _env("MODEL_PROVIDER", "bedrock"),
            "bedrock_model_id": _env("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
            "openai_model_id": _env("OPENAI_MODEL_ID", "gpt-4o-mini"),
            "gemini_model_id": _env("GEMINI_MODEL_ID", "gemini-2.0-flash"),
            "openai_api_key": _env("OPENAI_API_KEY", ""),
            "gemini_api_key": _env("GEMINI_API_KEY", ""),
            "stt_provider": _env("STT_PROVIDER", "mock"),
            "tts_provider": _env("TTS_PROVIDER", "mock"),
            "polly_voice_id": _env("POLLY_VOICE_ID", "Joanna"),
            "polly_engine": _env("POLLY_ENGINE", "neural"),
            "vosk_model_path": _env("VOSK_MODEL_PATH", "models/vosk-model-small-en-us-0.15"),
            "edge_voice": _env("EDGE_VOICE", "en-CA-ClaraNeural"),
            "skill_activate_threshold": float(_env("SKILL_ACTIVATE_THRESHOLD", "0.75")),
            "skill_clarify_threshold": float(_env("SKILL_CLARIFY_THRESHOLD", "0.45")),
            "llm_timeout_seconds": float(_env("LLM_TIMEOUT_SECONDS", "15")),
            "llm_max_retries": int(_env("LLM_MAX_RETRIES", "2")),
            "twilio_account_sid": _env("TWILIO_ACCOUNT_SID", ""),
            "twilio_auth_token": _env("TWILIO_AUTH_TOKEN", ""),
            "twilio_validate_signature": _env("TWILIO_VALIDATE_SIGNATURE", "false").lower()
            == "true",
            "signalwire_project_id": _env("SIGNALWIRE_PROJECT_ID", ""),
            "signalwire_token": _env("SIGNALWIRE_TOKEN", ""),
            "signalwire_validate": _env("SIGNALWIRE_VALIDATE", "false").lower() == "true",
            "public_base_url": _env("PUBLIC_BASE_URL", ""),
            "agentcore_runtime_name": _env("AGENTCORE_RUNTIME_NAME", "realestate-voice-agent"),
        }
        return cls(**kwargs)

    def replace(self, **overrides) -> "Settings":
        """Return a copy with overrides applied (handy in tests)."""
        for key in overrides:
            if key not in {f.name for f in fields(self)}:
                raise AttributeError(f"Unknown setting: {key}")
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        data.update(overrides)
        return Settings(**data)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Cached process-wide settings."""
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def set_settings(settings: Settings) -> None:
    """Replace the cached settings (used by tests and the FastAPI app factory)."""
    global _settings
    _settings = settings
