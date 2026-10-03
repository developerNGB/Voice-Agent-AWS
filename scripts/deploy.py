#!/usr/bin/env python3
"""Deployment driver: infrastructure → skills → runtime → verification.

Usage:
    python scripts/deploy.py --dry-run     # show the exact commands
    python scripts/deploy.py --stage infra # CDK only
    python scripts/deploy.py --stage all   # everything (requires AWS + CLI)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], dry_run: bool, cwd: Path | None = None) -> None:
    printable = " ".join(cmd)
    print(f"\n$ {printable}")
    if dry_run:
        return
    result = subprocess.run(cmd, cwd=cwd or ROOT)
    if result.returncode != 0:
        print(f"command failed: {printable}", file=sys.stderr)
        sys.exit(result.returncode)


def stage_tests(dry_run: bool) -> None:
    run([sys.executable, "-m", "pytest", "-q"], dry_run)


def stage_infra(dry_run: bool) -> None:
    cdk_dir = ROOT / "infrastructure" / "cdk"
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], dry_run, cdk_dir)
    run(["cdk", "bootstrap"], dry_run, cdk_dir)
    run(["cdk", "deploy", "--require-approval", "never"], dry_run, cdk_dir)


def stage_skills(dry_run: bool, bucket: str | None) -> None:
    cmd = [sys.executable, "scripts/seed_skills.py"]
    if bucket:
        cmd += ["--bucket", bucket]
    run(cmd, dry_run)


def stage_runtime(dry_run: bool) -> None:
    """AgentCore CLI workflow (see docs/manual-outline.md §25)."""
    if not dry_run and shutil.which("agentcore") is None:
        print("agentcore CLI not found — install: npm install -g @aws/agentcore-cli",
              file=sys.stderr)
        sys.exit(1)
    run(["agentcore", "validate"], dry_run)
    run(["agentcore", "deploy",
         "--name", "realestate-voice-agent",
         "--protocol", "ws"], dry_run)


def stage_verify(dry_run: bool) -> None:
    run([sys.executable, "-m", "pytest", "-q", "tests/integration"], dry_run)
    print("\nNext: place a real call to your Canadian number and watch "
          "`tail -f logs/calls.jsonl`.")


STAGES = {
    "tests": stage_tests,
    "infra": stage_infra,
    "skills": stage_skills,
    "runtime": stage_runtime,
    "verify": stage_verify,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="print commands only")
    parser.add_argument("--stage", default="all",
                        choices=["all", *STAGES])
    parser.add_argument("--bucket", help="S3 bucket for skills")
    args = parser.parse_args()

    order = ["tests", "infra", "skills", "runtime", "verify"]
    for name in order:
        if args.stage not in ("all", name):
            continue
        print(f"\n=== stage: {name} ===")
        if name == "skills":
            stage_skills(args.dry_run, args.bucket)
        else:
            STAGES[name](args.dry_run)
    print("\nDeployment flow complete.")


if __name__ == "__main__":
    main()
