"""Start the live call stack: uvicorn + cloudflared tunnel, one command.

Prints the public webhook URL to paste into SignalWire (or Twilio).

    python scripts/start_live.py            # start both
    python scripts/start_live.py --stop     # stop both
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("PORT", "8000"))
CF_LOG = Path("/tmp/cf.log") if sys.platform != "win32" else Path(os.environ.get("TEMP", ".")) / "cf.log"
UV_LOG = Path("/tmp/uv_live.log") if sys.platform != "win32" else Path(os.environ.get("TEMP", ".")) / "uv_live.log"


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def pids_on_port(port: int) -> list[str]:
    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True, errors="ignore")
    except Exception:
        return []
    pids = set()
    for line in out.splitlines():
        if f":{port}" in line and "LISTENING" in line:
            pids.add(line.split()[-1])
    return sorted(pids)


def stop_all() -> None:
    for pid in pids_on_port(PORT):
        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
        print(f"stopped server pid {pid}")
    for line in subprocess.run(["tasklist"], capture_output=True, text=True,
                               errors="ignore").stdout.splitlines():
        if "cloudflared" in line:
            pid = line.split()[1]
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
            print(f"stopped cloudflared pid {pid}")


def start_server() -> None:
    if port_in_use(PORT):
        print(f"server already running on :{PORT}")
        return
    log = open(UV_LOG, "w")
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "0.0.0.0", "--port", str(PORT)],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
    )
    for _ in range(30):
        time.sleep(0.5)
        if port_in_use(PORT):
            print(f"server up on :{PORT}")
            return
    raise SystemExit(f"server failed to start — see {UV_LOG}")


def start_tunnel() -> str:
    cf = ROOT / "tools" / ("cloudflared.exe" if os.name == "nt" else "cloudflared")
    if not cf.exists():
        raise SystemExit(f"missing {cf} — download cloudflared first")
    if CF_LOG.exists():
        CF_LOG.write_text("")
    log = open(CF_LOG, "w")
    subprocess.Popen([str(cf), "tunnel", "--url", f"http://127.0.0.1:{PORT}",
                      "--no-autoupdate"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(40):
        time.sleep(0.5)
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", CF_LOG.read_text(errors="ignore"))
        if m:
            return m.group(0)
    raise SystemExit(f"tunnel did not report a URL — see {CF_LOG}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()

    if args.stop:
        stop_all()
        return

    start_server()
    url = start_tunnel()
    print()
    print(f"public base URL : {url}")
    print(f"webhook (CXML)  : POST {url}/signalwire/voice")
    print(f"media stream WS : wss://{url.removeprefix('https://')}/signalwire/media")
    print(f"health check    : {url}/health")
    print()
    print("SignalWire console → Phone Numbers → your number → Voice URL:")
    print(f"  {url}/signalwire/voice   (HTTP POST)")
    print()
    print("keep this window open; close with: python scripts/start_live.py --stop")


if __name__ == "__main__":
    main()
