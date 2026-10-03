"""Twilio helpers: signature validation and TwiML for media streaming."""

from __future__ import annotations

import hmac
import hashlib
from urllib.parse import urlencode
from xml.sax.saxutils import escape, quoteattr


def validate_twilio_signature(url: str, params: dict, signature: str,
                              auth_token: str) -> bool:
    """Validate ``X-Twilio-Signature`` (HMAC-SHA1 of URL + sorted params)."""
    if not (auth_token and signature):
        return False
    data = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    expected = hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"),
                        hashlib.sha1).digest()
    import base64

    return hmac.compare_digest(base64.b64encode(expected).decode("ascii"), signature)


def media_stream_ws_url(base_url: str, agent_id: str) -> str:
    base = (base_url or "").rstrip("/")
    ws = base.replace("https://", "wss://").replace("http://", "ws://")
    query = urlencode({"agent": agent_id})
    return f"{ws}/twilio/media?{query}"


def twiml_start_stream(ws_url: str, call_sid: str = "", stream_sid: str = "") -> str:
    """TwiML that streams call audio to our WebSocket gateway."""
    attrs = f"url={quoteattr(ws_url)}"
    if call_sid:
        attrs += f" callSid={quoteattr(call_sid)}"
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Response>"
        "<Connect>"
        f"<Stream {attrs}>"
        "<Parameter name=\"callSid\" value=\""
        f"{escape(call_sid)}\" />"
        "</Stream>"
        "</Connect>"
        "</Response>"
    )


def twiml_hangup() -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Response><Hangup/></Response>"
    )
