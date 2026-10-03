#!/usr/bin/env python3
"""Bootstrap the development machine.

Usage:
    python scripts/setup.py            # local setup + tests
    python scripts/setup.py --check    # verify environment only
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_python() -> bool:
    version = sys.version_info
    print(f"[1/4] Python {version.major}.{version.minor}.{version.micro}")
    if version < (3, 10):
        print("      ERROR: Python 3.10+ is required", file=sys.stderr)
        return False
    return True


def check_env_file(check_only: bool) -> None:
    env_example = ROOT / ".env.example"
    env_file = ROOT / ".env"
    print("[2/4] .env file")
    if env_file.is_file():
        print("      .env already exists (left untouched)")
    elif check_only:
        print("      MISSING — copy .env.example to .env")
    else:
        shutil.copy(env_example, env_file)
        print("      created .env from .env.example (edit credentials there)")


def check_dirs() -> None:
    print("[3/4] Directories")
    for relative in ("logs", "logs/transcripts", "skills/realestate_001"):
        path = ROOT / relative
        path.mkdir(parents=True, exist_ok=True)
        print(f"      {relative}/")


def run_tests() -> None:
    print("[4/4] Tests")
    result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT)
    if result.returncode != 0:
        print("      tests FAILED — fix before continuing", file=sys.stderr)
        sys.exit(result.returncode)
    print("      all tests passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify only")
    args = parser.parse_args()

    if not check_python():
        sys.exit(1)
    check_env_file(args.check)
    check_dirs()
    if not args.check:
        run_tests()
    print("\nSetup complete. Next: python scripts/deploy.py --help")


if __name__ == "__main__":
    main()
