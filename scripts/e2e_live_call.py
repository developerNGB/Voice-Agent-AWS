"""End-to-end live-call simulator.

Drives ``/signalwire/media`` exactly like a carrier would: ``start`` event,
µ-law caller audio, trailing silence for endpointing — then transcribes the
agent's spoken reply with Vosk so you can *verify* what the caller would
hear, without placing a phone call.

Usage:
    python scripts/e2e_live_call.py                       # via $PUBLIC_BASE_URL
    python scripts/e2e_live_call.py --url ws://127.0.0.1:8000/signalwire/media
    python scripts/e2e_live_call.py --say "Is it still available?"
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.voice.base import StreamConfig  # noqa: E402
from app.voice.edge import EdgeTTSProvider  # noqa: E402
from app.voice.vosk import VoskSTTProvider  # noqa: E402

FRAME = 320  # 20 ms @ 8 kHz


async def synth_speech(text: str) -> bytes:
    chunk = await EdgeTTSProvider().synthesize(text)
    return chunk.data


async def transcribe(mulaw: bytes) -> str:
    stt = VoskSTTProvider()
    await stt.start(StreamConfig())
    texts: list[str] = []
    for i in range(0, len(mulaw), FRAME):
        texts += [t.text for t in await stt.feed_audio(mulaw[i:i + FRAME])]
    texts += [t.text for t in await stt.stop()]
    return " ".join(t for t in texts if t).strip()


async def run_call(url: str, utterance: str, agent: str, timeout: float) -> int:
    import websockets

    speech = await synth_speech(utterance)
    print(f"caller will say: {utterance!r} ({len(speech)} bytes µ-law)")

    t_start = time.time()
    greeting = bytearray()
    reply = bytearray()

    async with websockets.connect(url, max_size=32 * 1024 * 1024) as ws:
        await ws.send(json.dumps({
            "event": "start",
            "start": {
                "streamSid": "MZ-e2e-001",
                "customParameters": {"agent": agent, "callSid": "CA-e2e"},
            },
        }))

        saw_greeting = False
        cleared = False

        async def reader():
            nonlocal saw_greeting, cleared
            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                except asyncio.TimeoutError:
                    return
                if msg.get("event") == "media":
                    payload = base64.b64decode(msg["media"]["payload"])
                    # the greeting is the *first* media message the gateway sends
                    if not saw_greeting:
                        saw_greeting = True
                        greeting.extend(payload)
                    else:
                        reply.extend(payload)
                elif msg.get("event") == "clear":
                    cleared = True
                elif msg.get("event") == "stop":
                    return

        reader_task = asyncio.create_task(reader())
        await asyncio.sleep(2.5)                       # let the greeting arrive

        # stream the utterance, then enough silence to trip the 700 ms endpoint
        for i in range(0, len(speech), FRAME):
            await ws.send(json.dumps({
                "event": "media",
                "media": {"payload": base64.b64encode(speech[i:i + FRAME]).decode()},
            }))
        for _ in range(150):                           # 3 s of silence
            await ws.send(json.dumps({
                "event": "media",
                "media": {"payload": base64.b64encode(b"\xff" * FRAME).decode()},
            }))

        waited = 0.0
        while waited < timeout:                        # wait for the agent to talk
            await asyncio.sleep(0.5)
            waited += 0.5
            if len(reply) > 3200:                      # ≥ 1 s of reply audio
                await asyncio.sleep(1.5)
                break

        await ws.send(json.dumps({"event": "stop"}))
        reader_task.cancel()

    print(f"greeting audio: {len(greeting)} bytes in {time.time()-t_start:.1f}s (barge-in clear={cleared})")
    if greeting:
        print(f"  agent greeted: {(await transcribe(bytes(greeting)))!r}")
    print(f"reply audio:     {len(reply)} bytes")
    if reply:
        text = await transcribe(bytes(reply))
        print(f"  agent said:    {text!r}")
        return 0 if text else 2
    print("  NO REPLY AUDIO — check /tmp/uv_live.log")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--say", default="Hi, I'm calling about the house on 123 Main Street.")
    parser.add_argument("--agent", default="realestate_001")
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--url", default="")
    args = parser.parse_args()

    url = args.url
    if not url:
        base = os.environ.get("PUBLIC_BASE_URL") or ""
        if not base:  # read .env the same way the app does
            from app.config import get_settings
            base = get_settings().public_base_url
        if not base:
            raise SystemExit("set --url or PUBLIC_BASE_URL")
        url = base.replace("https://", "wss://").replace("http://", "ws://")
        url = url.rstrip("/") + "/signalwire/media"

    print(f"connecting: {url}")
    rc = asyncio.run(run_call(url, args.say, args.agent, args.timeout))
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
