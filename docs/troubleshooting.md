# Troubleshooting Guide

Symptom → check → fix. Every command is copy-pasteable.

## Calls don't connect

| Check | Where / command | Fix |
|---|---|---|
| Webhook URL | Twilio console → Phone Numbers → your number | set Voice webhook to `https://YOUR_HOST/twilio/voice`, HTTP POST |
| No public HTTPS | `curl -X POST https://YOUR_HOST/twilio/voice` | local dev needs a tunnel (`ngrok http 8000`) or the deployed runtime |
| Signature rejected (403) | app output: `invalid signature` | `TWILIO_VALIDATE_SIGNATURE=true` requires the real auth token in the env; set `false` only for local dev |
| Wrong agent selected | TwiML contains `agent=…` | number must exist in `config/agents.json` (`agent_id_for_phone`) |

## Caller hears nothing / no reply

| Check | Where / command | Fix |
|---|---|---|
| Gateway alive | `curl localhost:8000/health` | restart `uvicorn app.main:app` |
| WebSocket path | TwiML `<Stream url=…>` must be `wss://` | `PUBLIC_BASE_URL` must be the public HTTPS origin |
| STT provider | `STT_PROVIDER=aws` but package missing | `pip install -e ".[voice]"` or use `mock` |
| Endpoint never fires | `logs/events.jsonl` has no `agent_turn` | audio must be µ-law 8 kHz; check frame energy (silence threshold) |
| TTS empty | `TTS_PROVIDER=aws` without AWS creds | set credentials / IAM role, or `TTS_PROVIDER=mock` |

## Wrong skill / wrong answer

| Check | Where / command | Fix |
|---|---|---|
| Routing decision | `logs/events.jsonl` → `{"type":"routing", …}` shows status/score/candidates | tune `SKILL_ACTIVATE_THRESHOLD` / `SKILL_CLARIFY_THRESHOLD` |
| Header keywords | `python scripts/seed_skills.py` (validates + prints names) | add the phrases callers actually say to `KEYWORDS:` |
| Skill file broken | validator prints `INVALID …` | fix the header; `SKILL_ID`/`CONTENT` are mandatory |
| Skill not visible | registry lists only `skills/<agent_id>/` | confirm the file is in **this** agent's namespace |
| LLM answering oddly | `logs/events.jsonl` → `llm` events, `errors` in the call record | switch `MODEL_PROVIDER` (bedrock/openai/gemini/mock) to isolate |

## LLM errors

| Symptom | Cause | Fix |
|---|---|---|
| `llm_failure` in call record | timeout/throttle/model access | check model id, region access, raise `LLM_TIMEOUT_SECONDS` |
| Fallback reply heard by caller | retries exhausted (by design, never a stack trace) | inspect `logs/events.jsonl` → `error` events |
| ThrottlingException | request volume | request a quota increase / add backoff (`LLM_MAX_RETRIES`) |

## Tests

```bash
python -m pytest -q                       # everything offline
python -m pytest tests/security -q        # isolation suite only
python -m pytest -k RT-004                # one evaluation scenario
RUN_AWS_TESTS=1 python -m pytest -m aws   # live AWS (needs creds + seeded bucket)
```

| Failure | Meaning | Fix |
|---|---|---|
| scorer band assertions fail | keyword/scoring change | re-run the full RT dataset, then adjust keywords not thresholds |
| `ACCESS_DENIED` test fails | isolation regression | check `app/security/isolation.py` changes first |
| websocket tests 404 | routes not registered | `create_app()` must call `register_routes()` |

## Logs

```bash
tail -f logs/events.jsonl          # routing, security, session events
cat logs/calls.jsonl | python -m json.tool   # final call records
ls logs/transcripts/               # per-call transcripts (redacted)
```
