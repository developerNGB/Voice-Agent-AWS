"""S3 storage helpers: skill uploads and call-report archives."""

from __future__ import annotations

import json
from pathlib import Path


class S3SkillUploader:
    """Uploads ``skills/<agent_id>/*.txt`` to ``s3://<bucket>/agents/<agent_id>/``."""

    def __init__(self, bucket: str, region: str = "ca-central-1", prefix: str = "agents",
                 client=None):
        if not bucket:
            raise ValueError("bucket required")
        self.bucket = bucket
        self.region = region
        self.prefix = prefix.strip("/")
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("s3", region_name=self.region)
        return self._client

    def upload_agent_skills(self, local_root: str | Path, agent_id: str) -> list[str]:
        from app.security.isolation import validate_agent_id, safe_join

        validate_agent_id(agent_id)
        agent_dir = safe_join(local_root, agent_id)
        uploaded: list[str] = []
        if not agent_dir.is_dir():
            return uploaded
        for path in sorted(agent_dir.glob("*.txt")):
            key = f"{self.prefix}/{agent_id}/{path.name}"
            self.client.upload_file(str(path), self.bucket, key)
            uploaded.append(key)
        return uploaded

    def upload_json(self, key: str, payload: dict) -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(payload, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        return key


class S3ReportArchive:
    """Stores finalized call reports under ``reports/calls/<session_id>.json``."""

    def __init__(self, bucket: str, region: str = "ca-central-1", client=None):
        self.bucket = bucket
        self.region = region
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("s3", region_name=self.region)
        return self._client

    def put_record(self, record: dict) -> str:
        key = f"reports/calls/{record['session_id']}.json"
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(record, indent=2, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        return key
