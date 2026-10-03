"""Configuration-driven agents (one phone number → one agent → one namespace)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("config/agents.json")


def load_agent_configs(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, dict]:
    """agent_id → config. Falls back to a minimal default when file missing."""
    config_path = Path(path)
    if config_path.is_file():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return {a["agent_id"]: a for a in data.get("agents", [])}
    return {}


@lru_cache(maxsize=4)
def _cached_configs(path: str) -> dict[str, dict]:
    return load_agent_configs(path)


def agent_config_for(agent_id: str, path: str | Path = DEFAULT_CONFIG_PATH) -> dict:
    configs = _cached_configs(str(path))
    return configs.get(agent_id, {"agent_id": agent_id, "display_name": "our office"})


def agent_id_for_phone(phone_number: str, path: str | Path = DEFAULT_CONFIG_PATH) -> str | None:
    """Phone Number → Agent ID mapping (one number serves exactly one agent)."""
    configs = _cached_configs(str(path))
    for agent_id, cfg in configs.items():
        if cfg.get("phone_number") == phone_number:
            return agent_id
    return None
