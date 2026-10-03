"""Skill loading with strict per-agent isolation.

Two back-ends share one interface:

* :class:`LocalSkillStore` — reads ``<root>/<agent_id>/*.txt`` from disk
* :class:`S3SkillStore`     — reads ``agents/<agent_id>/*.txt`` from S3

Both enforce Layer-1 (path) isolation before any read happens; application
level checks live in :mod:`app.security.isolation`.
"""

import abc
from pathlib import Path

from app.security.isolation import (
    validate_agent_id,
    validate_skill_id,
    safe_join,
)
from app.skills.parser import parse_skill_text, SkillParseError
from app.models.skill import Skill


class SkillAccessError(PermissionError):
    """Raised when a skill read is denied or a file is malformed."""


class SkillStore(abc.ABC):
    """Abstract skill store. Every method is agent-scoped."""

    @abc.abstractmethod
    def list_skill_ids(self, agent_id: str) -> list[str]:
        raise NotImplementedError

    @abc.abstractmethod
    def read(self, agent_id: str, skill_id: str) -> str:
        raise NotImplementedError

    def load(self, agent_id: str, skill_id: str) -> Skill:
        text = self.read(agent_id, skill_id)
        try:
            return parse_skill_text(text, agent_id=agent_id, source=skill_id)
        except SkillParseError as exc:
            raise SkillAccessError(str(exc)) from exc


class LocalSkillStore(SkillStore):
    """Reads skills from ``<root>/<agent_id>/<skill_id>.txt``."""

    def __init__(self, root: str | Path = "skills"):
        self.root = Path(root)

    def list_skill_ids(self, agent_id: str) -> list[str]:
        validate_agent_id(agent_id)
        agent_dir = safe_join(self.root, agent_id)
        if not agent_dir.is_dir():
            return []
        return sorted(p.stem for p in agent_dir.glob("*.txt"))

    def read(self, agent_id: str, skill_id: str) -> str:
        validate_agent_id(agent_id)
        validate_skill_id(skill_id)
        path = safe_join(self.root, agent_id, f"{skill_id}.txt")
        if not path.is_file():
            raise SkillAccessError(f"Skill {skill_id!r} not found for agent {agent_id!r}")
        return path.read_text(encoding="utf-8")


class S3SkillStore(SkillStore):
    """Reads skills from ``s3://<bucket>/agents/<agent_id>/<skill_id>.txt``."""

    def __init__(self, bucket: str, prefix: str = "agents", region: str | None = None,
                 client=None):
        if not bucket:
            raise ValueError("S3 skill store requires a bucket name")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self._client = client
        self._region = region

    @property
    def client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("s3", region_name=self._region)
        return self._client

    def _key(self, agent_id: str, skill_id: str) -> str:
        validate_agent_id(agent_id)
        validate_skill_id(skill_id)
        # safe_join-style validation for the object key
        if ".." in agent_id or "/" in skill_id or "\\" in skill_id:
            raise SkillAccessError("Invalid skill path")
        return f"{self.prefix}/{agent_id}/{skill_id}.txt"

    def list_skill_ids(self, agent_id: str) -> list[str]:
        key_prefix = self._key(agent_id, "")[:-1]  # strip trailing '/'
        resp = self.client.list_objects_v2(Bucket=self.bucket, Prefix=key_prefix)
        ids = []
        for obj in resp.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".txt") and key.count("/") == key_prefix.count("/"):
                ids.append(key.rsplit("/", 1)[-1][:-4])
        return sorted(ids)

    def read(self, agent_id: str, skill_id: str) -> str:
        key = self._key(agent_id, skill_id)
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:  # noqa: BLE001 - normalised below
            raise SkillAccessError(f"Skill {skill_id!r} not found for agent {agent_id!r}") from exc
        return resp["Body"].read().decode("utf-8")


def build_skill_store(settings) -> SkillStore:
    """Factory driven by ``SKILL_STORE`` (``local`` | ``s3``)."""
    if settings.skill_store == "s3":
        return S3SkillStore(settings.skill_bucket, region=settings.aws_region)
    return LocalSkillStore(settings.skill_root)
