#!/usr/bin/env python3
"""Upload local skill files to S3 (or verify the local store).

Usage:
    python scripts/seed_skills.py --local            # validate every skill file
    python scripts/seed_skills.py --bucket my-bucket # validate + upload to S3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.security.isolation import validate_agent_id  # noqa: E402
from app.skills.loader import LocalSkillStore  # noqa: E402
from app.skills.parser import SkillParseError  # noqa: E402


def validate_all() -> dict[str, list[str]]:
    store = LocalSkillStore(ROOT / "skills")
    results: dict[str, list[str]] = {}
    failed = False
    for agent_dir in sorted((ROOT / "skills").iterdir()):
        if not agent_dir.is_dir():
            continue
        agent_id = agent_dir.name
        validate_agent_id(agent_id)
        results[agent_id] = []
        for skill_id in store.list_skill_ids(agent_id):
            try:
                skill = store.load(agent_id, skill_id)
            except SkillParseError as exc:
                print(f"  INVALID {agent_id}/{skill_id}: {exc}", file=sys.stderr)
                failed = True
                continue
            results[agent_id].append(skill_id)
            print(f"  ok  {agent_id}/{skill_id}.txt  ({skill.name})")
    if failed:
        sys.exit(1)
    return results


def upload(bucket: str) -> None:
    from app.storage.s3 import S3SkillUploader

    uploader = S3SkillUploader(bucket)
    for agent_id in sorted((ROOT / "skills").iterdir()):
        if not agent_id.is_dir():
            continue
        keys = uploader.upload_agent_skills(ROOT / "skills", agent_id.name)
        for key in keys:
            print(f"  uploaded s3://{bucket}/{key}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", help="S3 bucket to upload to")
    parser.add_argument("--local", action="store_true", help="validate only")
    args = parser.parse_args()

    print("Validating skill files…")
    validate_all()

    if args.bucket:
        print(f"Uploading to s3://{args.bucket}…")
        upload(args.bucket)
    else:
        print("Local validation only (pass --bucket to upload).")


if __name__ == "__main__":
    main()
