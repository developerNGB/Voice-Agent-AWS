"""Temporary live watcher: polls for evidence of inbound calls for N seconds.

Writes findings to /tmp/watch.log (or %TEMP%/watch.log on Windows):
  - new POST/WebSocket lines in the uvicorn log
  - new call records appearing in the SignalWire LAML Calls API
  - tunnel errors
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from base64 import b64encode
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402

DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 300
OUT = Path("/tmp/watch.log") if sys.platform != "win32" else Path(os.environ.get("TEMP", ".")) / "watch.log"
UV = Path("/tmp/uv_live.log") if sys.platform != "win32" else Path(os.environ.get("TEMP", ".")) / "uv_live.log"

s = get_settings()
PROJ = s.signalwire_project_id
TOKEN = s.signalwire_token
SPACE = os.environ.get("SIGNALWIRE_SPACE", "zephyr-automations.signalwire.com")


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    with OUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def laml(path: str):
    req = urllib.request.Request(f"https://{SPACE}/api/laml/2010-04-01/Accounts/{PROJ}{path}")
    cred = b64encode(f"{PROJ}:{TOKEN}".encode()).decode()
    req.add_header("Authorization", f"Basic {cred}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    OUT.write_text("", encoding="utf-8")
    log(f"watching for {DURATION}s — call +12014834036 now")
    uv_seen = UV.read_text(errors="ignore").count("\n") if UV.exists() else 0
    try:
        prev_calls = len(laml("/Calls?PageSize=50").get("calls", []))
    except Exception as exc:  # noqa: BLE001
        prev_calls = -1
        log(f"calls API error: {exc}")
    deadline = time.time() + DURATION
    while time.time() < deadline:
        time.sleep(2)
        if UV.exists():
            lines = UV.read_text(errors="ignore").splitlines()
            for line in lines[uv_seen:]:
                if any(k in line for k in ("POST", "WebSocket", "ERROR", "Traceback")):
                    log(f"SERVER: {line.strip()}")
            uv_seen = len(lines)
        try:
            calls = laml("/Calls?PageSize=50").get("calls", [])
            if prev_calls >= 0 and len(calls) != prev_calls:
                for c in calls[: max(0, prev_calls - len(calls)) or 1][:5]:
                    log(f"SIGNALWIRE: call {c.get('sid','')[:12]} status={c.get('status')} "
                        f"from={c.get('from')} dur={c.get('duration')} start={c.get('start_time')}")
                prev_calls = len(calls)
        except Exception as exc:  # noqa: BLE001
            log(f"calls API error: {exc}")
    log("watch finished")


if __name__ == "__main__":
    main()
