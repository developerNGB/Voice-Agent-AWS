"""SignalWire helpers (Compatibility API / CXML).

SignalWire's bidirectional media stream is protocol-compatible with the
Twilio dialect we already speak: ``start`` / ``media`` / ``stop`` events with
base64 ``media.payload``, and we reply with ``media`` / ``clear`` messages.

Differences handled here:
* the WebSocket URL must **not** carry a query string → the agent id travels
  as a ``<Parameter>`` and arrives in ``start.customParameters``;
* webhook authenticity uses HTTP Basic auth (Project ID : Token) instead of a
  request signature.
"""

from __future__ import annotations

import base64
from xml.sax.saxutils import quoteattr

DEFAULT_CODEC = "PCMU@8000h"


def validate_signalwire_auth(project_id: str, token: str, header_value: str) -> bool:
    """Validate SignalWire's ``Authorization: Basic …`` webhook header."""
    if not (project_id and token and header_value):
        return False
    if not header_value.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(header_value.split(None, 1)[1]).decode("utf-8")
    except Exception:  # noqa: BLE001 - malformed header
        return False
    expected = f"{project_id}:{token}"
    import hmac

    return hmac.compare_digest(decoded, expected)


def connect_stream_xml(ws_url: str, agent_id: str = "", call_sid: str = "") -> str:
    """CXML that opens a *bidirectional* stream to our WebSocket gateway."""
    if not ws_url.startswith(("wss://", "ws://")):
        raise ValueError("Stream URL must be a WebSocket URL (wss:// in production)")
    params = ""
    if agent_id:
        params += f"<Parameter name=\"agent\" value={quoteattr(agent_id)}/>"
    if call_sid:
        params += f"<Parameter name=\"callSid\" value={quoteattr(call_sid)}/>"
    stream = f"<Stream url={quoteattr(ws_url)} codec={quoteattr(DEFAULT_CODEC)}>{params}</Stream>"
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Response>"
        f"<Connect>{stream}</Connect>"
        "</Response>"
    )


def hangup_xml() -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Response><Hangup/></Response>"
    )
