#!/usr/bin/env python3
"""Remove everything this project created — billable resources first.

Usage:
    python scripts/cleanup.py --list      # show what would be removed
    python scripts/cleanup.py --confirm   # actually remove (AWS required)

WARNINGS
-------
* S3/DynamoDB resources are created with RemovalPolicy.RETAIN: data survives
  ``cdk destroy`` on purpose. ``--confirm`` empties and deletes them.
* Twilio phone numbers keep billing until you release them in the Twilio
  console — this script cannot do that for you.
* CloudWatch alarms/log groups are removed by ``cdk destroy``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings  # noqa: E402


def billable_inventory(settings: Settings) -> list[tuple[str, str, str]]:
    return [
        ("Amazon Connect / Twilio", "phone number", "per minute + monthly number fee"),
        ("AgentCore Runtime", "runtime deployment", "per runtime hour / request"),
        ("S3", settings.skill_bucket or "YOUR_BUCKET_NAME", "storage + requests"),
        ("DynamoDB", settings.dynamodb_table or "YOUR_TABLE_NAME", "on-demand RCU/WCU"),
        ("CloudWatch", "log group + alarms", "ingestion + alarms"),
        ("Bedrock", settings.bedrock_model_id, "per input/output token"),
        ("Polly / Transcribe", "speech synthesis / transcription", "per character / minute"),
    ]


def empty_bucket(s3_client, bucket: str) -> None:
    paginator = s3_client.get_paginator("list_object_versions")
    for page in paginator.paginate(Bucket=bucket):
        objects = [{"Key": o["Key"], "VersionId": o.get("VersionId")}
                   for o in page.get("Versions", [])]
        objects += [{"Key": o["Key"], "VersionId": o.get("VersionId")}
                    for o in page.get("DeleteMarkers", [])]
        if objects:
            s3_client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
    # also plain list (non-versioned leftovers)
    for page in s3_client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if objs:
            s3_client.delete_objects(Bucket=bucket, Delete={"Objects": objs})
    s3_client.delete_bucket(Bucket=bucket)
    print(f"  deleted s3://{bucket}")


def cleanup_local() -> None:
    import shutil

    for relative in ("logs",):
        path = ROOT / relative
        if path.is_dir():
            shutil.rmtree(path)
            print(f"  removed {relative}/")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    print("Resources this project can create (and their cost drivers):")
    for name, resource, cost in billable_inventory(settings):
        print(f"  - {name:22} {resource:32} {cost}")

    if args.list or not args.confirm:
        print("\nDry run. Add --confirm to delete local logs and (if configured) "
              "the S3 skill bucket, then run: cdk destroy")
        return

    print("\nCleaning up…")
    cleanup_local()

    if settings.skill_bucket:
        try:
            import boto3
            empty_bucket(boto3.client("s3", region_name=settings.aws_region),
                         settings.skill_bucket)
        except Exception as exc:  # noqa: BLE001
            print(f"  S3 cleanup skipped: {exc}", file=sys.stderr)

    if settings.dynamodb_table:
        try:
            import boto3
            dynamodb = boto3.client("dynamodb", region_name=settings.aws_region)
            dynamodb.delete_table(TableName=settings.dynamodb_table)
            print(f"  deleted table {settings.dynamodb_table}")
        except Exception as exc:  # noqa: BLE001
            print(f"  DynamoDB cleanup skipped: {exc}", file=sys.stderr)

    print("\nRemaining manual steps (see docs/cleanup-guide.md):")
    print("  1. cdk destroy                      (infrastructure/cdk)")
    print("  2. release the Twilio phone number  (Twilio console)")
    print("  3. delete AgentCore runtime         (agentcore delete)")


if __name__ == "__main__":
    main()
