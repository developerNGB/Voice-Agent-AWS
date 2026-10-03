"""FastAPI application: AgentCore-style ``/ws`` + Twilio webhooks.

Endpoints
---------
* ``GET  /health``            — liveness/readiness
* ``WS   /ws``                — persistent bidirectional JSON/audio channel
                                 (the AgentCore Runtime contract)
* ``POST /twilio/voice``      — inbound call webhook → TwiML media stream
* ``WS   /twilio/media``      — Twilio media stream (µ-law frames)
"""

from __future__ import annotations

import base64
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse

from app.agent.agent import VoiceAgent
from app.agent_configs import agent_id_for_phone
from app.config import Settings, get_settings, set_settings
from app.gateway import VoiceGateway
from app.telephony.signalwire import connect_stream_xml, validate_signalwire_auth
from app.telephony.twilio import twiml_start_stream, validate_twilio_signature

CALLER_ID = "redacted"

import logging

webhook_log = logging.getLogger("webhook.signalwire")


def create_app(settings: Settings | None = None, agent: VoiceAgent | None = None,
               gateway: VoiceGateway | None = None) -> FastAPI:
    """Application factory (tests inject a pre-built agent/gateway)."""
    settings = settings or get_settings()
    set_settings(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.agent = agent or VoiceAgent(settings)
        app.state.gateway = gateway or VoiceGateway(app.state.agent, settings=settings)
        yield

    app = FastAPI(title="realestate-voice-agent", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.agent = agent
    app.state.gateway = gateway
    register_routes(app)
    return app


def register_routes(app: FastAPI) -> None:
    """Attach HTTP + WebSocket routes to any app instance."""

    # -- health --------------------------------------------------------------

    @app.get("/health")
    async def health(request: Request) -> dict:
        state = request.app.state
        agent: VoiceAgent | None = state.agent
        return {
            "status": "ok",
            "agent_id": state.settings.agent_id,
            "model_provider": state.settings.model_provider,
            "skill_store": state.settings.skill_store,
            "active_sessions": sum(
                1 for s in agent.sessions.values() if not s.closed
            ) if agent else 0,
        }

    # -- AgentCore-style WebSocket -------------------------------------------

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        agent: VoiceAgent = websocket.app.state.agent
        gateway: VoiceGateway = websocket.app.state.gateway
        call = None

        async def send(payload: dict) -> None:
            await websocket.send_text(json.dumps(payload))

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await send({"type": "error", "error": "invalid_json"})
                    continue

                mtype = message.get("type", "")

                if mtype == "session.start":
                    call = await gateway.open(
                        agent_id=message.get("agent_id") or agent.settings.agent_id,
                        caller_id=message.get("caller_id") or CALLER_ID,
                    )
                    await send({
                        "type": "session.started",
                        "session_id": call.session.session_id,
                        "agent_id": call.session.agent_id,
                        "greeting": agent.greeting(call.session),
                    })

                elif mtype == "user.text":
                    if call is None:
                        call = await gateway.open(caller_id=CALLER_ID)
                    turn, _audio = await call.handle_text(message.get("text", ""))
                    await send({
                        "type": "agent.text",
                        "session_id": turn.session_id,
                        "text": turn.reply,
                        "route_status": turn.route_status,
                        "active_skill": turn.active_skill_id,
                        "latency_ms": round(turn.latency_ms, 1),
                        "end_call": turn.end_call,
                    })

                elif mtype == "audio":
                    if call is None:
                        call = await gateway.open(caller_id=CALLER_ID)
                    frame = base64.b64decode(message.get("data", ""))
                    for event in await call.handle_audio_frame(frame):
                        if event.get("type") == "agent_turn":
                            await send({"type": "agent.text", **event})
                        else:
                            await send(event)

                elif mtype == "session.end":
                    if call is not None:
                        record = await call.close()
                        await send({"type": "call.summary", "record": record.to_dict()})
                        call = None
                    else:
                        await send({"type": "error", "error": "no_active_session"})

                else:
                    await send({"type": "error", "error": f"unknown_type:{mtype}"})

        except WebSocketDisconnect:
            pass
        finally:
            if call is not None and not call.closed:
                await call.close()

    # -- Twilio --------------------------------------------------------------

    @app.post("/twilio/voice")
    async def twilio_voice(request: Request) -> Response:
        settings: Settings = request.app.state.settings
        form = dict(await request.form())
        if settings.twilio_validate_signature:
            url = str(request.url)
            signature = request.headers.get("X-Twilio-Signature", "")
            if not validate_twilio_signature(url, form, signature,
                                             settings.twilio_auth_token):
                return PlainTextResponse("invalid signature", status_code=403)

        # One phone number → exactly one agent
        to_number = form.get("To", "")
        agent_id = agent_id_for_phone(to_number) or settings.agent_id
        ws_url = f"{settings.public_base_url.rstrip('/')}/twilio/media?agent={agent_id}"
        xml = twiml_start_stream(ws_url, call_sid=form.get("CallSid", ""))
        return Response(content=xml, media_type="application/xml")

    async def serve_media_stream(websocket: WebSocket) -> None:
        """Shared bidirectional media loop (Twilio + SignalWire dialects)."""
        await websocket.accept()
        gateway: VoiceGateway = websocket.app.state.gateway
        agent: VoiceAgent = websocket.app.state.agent
        settings: Settings = websocket.app.state.settings

        agent_id = websocket.query_params.get("agent") or settings.agent_id
        call = None
        stream_sid = ""

        async def push_audio(chunk) -> None:
            if not stream_sid:
                return
            await websocket.send_text(json.dumps({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": base64.b64encode(chunk.data).decode("ascii")},
            }))

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                event = message.get("event")

                if event == "start":
                    start = message.get("start") or {}
                    stream_sid = start.get("streamSid", "")
                    custom = start.get("customParameters") or {}
                    # SignalWire cannot use query strings → agent comes as a Parameter
                    agent_id = custom.get("agent") or agent_id
                    call = await gateway.open(agent_id=agent_id, caller_id=CALLER_ID,
                                               on_audio=None)
                    greeting = agent.greeting(call.session)
                    await push_audio(await call.tts.synthesize(greeting))

                elif event == "media" and call is not None:
                    frame = base64.b64decode(message["media"]["payload"])
                    for gw_event in await call.handle_audio_frame(frame):
                        if gw_event.get("type") == "cancel_audio":
                            await websocket.send_text(json.dumps({
                                "event": "clear", "streamSid": stream_sid,
                            }))
                        elif gw_event.get("type") == "agent_turn":
                            await push_audio(
                                await call.tts.synthesize(gw_event["text"]))
                        elif gw_event.get("type") == "end_call":
                            await websocket.send_text(json.dumps({
                                "event": "stop", "streamSid": stream_sid,
                            }))

                elif event == "stop":
                    break

        except WebSocketDisconnect:
            pass
        finally:
            if call is not None and not call.closed:
                await call.close()

    # -- media stream endpoints (one loop, two telephony dialects) ----------

    @app.websocket("/twilio/media")
    async def twilio_media(websocket: WebSocket) -> None:
        await serve_media_stream(websocket)

    @app.websocket("/signalwire/media")
    async def signalwire_media(websocket: WebSocket) -> None:
        await serve_media_stream(websocket)

    @app.post("/signalwire/voice")
    async def signalwire_voice(request: Request) -> Response:
        """Inbound SignalWire call → CXML bidirectional stream to our gateway."""
        settings: Settings = request.app.state.settings
        form = dict(await request.form())
        auth_header = request.headers.get("Authorization", "")
        # log the *shape* of the auth without ever printing secrets
        import base64 as _b64

        scheme = auth_header.split(None, 1)[0].lower() if auth_header else "<none>"
        user_match = pass_match = False
        if scheme == "basic" and auth_header:
            try:
                decoded = _b64.b64decode(auth_header.split(None, 1)[1]).decode()
                user, _, pwd = decoded.partition(":")
                user_match = user == settings.signalwire_project_id
                pass_match = pwd == settings.signalwire_token
            except Exception:  # noqa: BLE001
                pass
        webhook_log.info(
            "signalwire webhook: auth scheme=%s user_match=%s pass_match=%s "
            "headers=%s validate=%s", scheme, user_match, pass_match,
            sorted(h.lower() for h in request.headers), settings.signalwire_validate,
        )
        if settings.signalwire_validate:
            valid = validate_signalwire_auth(settings.signalwire_project_id,
                                             settings.signalwire_token, auth_header)
            if not valid:
                return PlainTextResponse("unauthorized", status_code=401)

        # One phone number → exactly one agent (also passed to the WS as a Parameter)
        agent_id = agent_id_for_phone(form.get("To", "")) or settings.agent_id
        base = (settings.public_base_url or str(request.base_url)).rstrip("/")
        ws_url = base.replace("https://", "wss://").replace("http://", "ws://")
        xml = connect_stream_xml(f"{ws_url}/signalwire/media", agent_id=agent_id,
                                 call_sid=form.get("CallSid", ""))
        return Response(content=xml, media_type="application/xml")


app = create_app()


def run() -> None:  # pragma: no cover - manual entry point
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":  # pragma: no cover
    run()
