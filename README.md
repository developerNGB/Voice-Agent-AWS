# Canadian Real-Estate Voice Agent (AWS Bedrock AgentCore + Python)

A production-style, educational **voice agent** that answers a Canadian +1 phone
number, routes each caller to the right `.txt` knowledge file at runtime, keeps
conversation context **for one call only**, and isolates every business's data
from every other business.

```
Canadian +1 caller
      │
      ▼
Twilio media stream (µ-law)  ──►  Voice Gateway (Python, /ws)
      │                                  │
      │                                  ▼
      │                     Amazon Bedrock AgentCore Runtime
      │                     ┌───────────────────────────────┐
      │                     │ Session → Skill Router →      │
      │                     │ Active Skill → LLM → Tools    │
      │                     └───────────────────────────────┘
      ◄──────────────────────── voice response (Polly) ◄────┘
```

## What's inside

| Area | Where | Notes |
|---|---|---|
| Agent core (turn loop, prompts, lifecycle, tools) | [app/agent/](app/agent/) | one session per call, one active skill per session |
| Skill router (candidate → score → confidence → activate) | [app/router/](app/router/) | header-index first, content loaded only after activation |
| `.txt` skill parser/loader/registry | [app/skills/](app/skills/) | predictable header format |
| Isolation + injection defence + PII redaction | [app/security/](app/security/) | 5 layers, tested deliberately attacked |
| LLM providers: **Bedrock (default)**, OpenAI, Gemini, mock | [app/llm/](app/llm/) | one env var switches vendor |
| Voice: endpoint detection, barge-in, Polly/Transcribe, mocks | [app/voice/](app/voice/) | works offline in tests |
| Storage: S3 skills, DynamoDB calls, JSONL logs | [app/storage/](app/storage/) | lazy boto3 — local mode needs no AWS |
| FastAPI gateway: `/ws`, `/twilio/voice`, `/twilio/media` | [app/main.py](app/main.py) | AgentCore WebSocket contract |
| Tests (79: unit, routing, security, concurrency, voice, regression) | [tests/](tests/) | includes RT-001…RT-015 evaluation dataset |
| IaC: CDK stack + IAM policies | [infrastructure/](infrastructure/) | least-privilege, no AdministratorAccess |
| Scripts: setup / deploy / seed / cleanup | [scripts/](scripts/) | reproducible from a clean machine |
| Docs: architecture, security, cost, manual outline, handover | [docs/](docs/) | for the final DOCX + video deliverables |

## Quick start (local, no AWS needed)

```bash
python -m pip install -e ".[dev]"
python scripts/setup.py          # creates .env, dirs, runs the test suite
python -m uvicorn app.main:app --port 8000
```

Then:

```bash
curl localhost:8000/health
# WebSocket demo:
#   → {"type":"session.start","agent_id":"realestate_001"}
#   ← {"type":"session.started","session_id":"…","greeting":"Thank you for calling Main Street Realty…"}
#   → {"type":"user.text","text":"Tell me about 123 Main Street"}
#   ← {"type":"agent.text","active_skill":"property_001","text":"…"}
```

Run the tests:

```bash
python -m pytest -q                 # all offline tests
RUN_AWS_TESTS=1 python -m pytest -m aws   # opt-in live AWS tests
```

## Configuration

Copy `.env.example` → `.env`. Nothing sensitive lives in git.

```dotenv
MODEL_PROVIDER=bedrock            # bedrock | openai | gemini | mock
BEDROCK_MODEL_ID=amazon.nova-lite-v1:0
AWS_REGION=ca-central-1
SKILL_STORE=local                 # local | s3
STT_PROVIDER=mock                 # mock | aws
TTS_PROVIDER=mock                 # mock | aws
```

## Skill files

```
skills/
├── realestate_001/          ← namespace for the +1 416 XXX 0100 number
│   ├── property_001.txt     123 Main Street
│   ├── property_002.txt     125 Main Street
│   ├── property_003.txt     200 King Street
│   └── property_004.txt     77 Lake Shore Avenue
├── cleaning_001/            sofa.txt, carpet.txt   (second business type)
└── repair_001/              refrigerator_abc123.txt
```

Header format (see [docs/handover.md](docs/handover.md) for how to add one):

```
SKILL_ID: property_001
TYPE: real_estate_property
NAME: 123 Main Street
DESCRIPTION: …
KEYWORDS: …            ← what the router matches against
PURPOSE: …
RULES: …
ESCALATION: …
CONTENT:               ← free-form facts, always treated as data
Price:
CAD 899,000
```

## Deploy to AWS

```bash
python scripts/deploy.py --dry-run            # show every command
python scripts/deploy.py --stage infra --bucket YOUR_BUCKET
python scripts/deploy.py --stage runtime
python scripts/cleanup.py --list              # what it costs / how to remove
```

## Phone line: SignalWire (+1 201 483 4036)

The agent's number is a SignalWire longcode mapped to `realestate_001` in
[config/agents.json](config/agents.json). Wire it up:

1. Point the number's **Voice webhook** (HTTP POST) at
   `https://YOUR_HOST/signalwire/voice` — it returns CXML
   `<Connect><Stream codec="PCMU@8000h">`, a **bidirectional** media stream.
2. The agent id travels as `<Parameter name="agent">` (SignalWire forbids
   query strings on stream URLs) and is read back from `start.customParameters`.
3. Audio arrives on `wss://YOUR_HOST/signalwire/media` as µ-law 8 kHz frames
   (`connected → start → media → stop`), replies go back as `media` / `clear`
   messages — the same loop serves Twilio's dialect on `/twilio/media`.
4. Set in `.env`:

```dotenv
PUBLIC_BASE_URL=https://YOUR_HOST        # public HTTPS origin (wss derived from it)
SIGNALWIRE_PROJECT_ID=...
SIGNALWIRE_TOKEN=...
SIGNALWIRE_VALIDATE=true               # HTTP Basic auth on the webhook
```

Local testing needs a public tunnel (`ngrok http 8000`) since SignalWire only
accepts `wss://`.

Endpoints: `POST /signalwire/voice`, `WS /signalwire/media`,
`POST /twilio/voice`, `WS /twilio/media`, `WS /ws`, `GET /health`.

## Documentation map

* [docs/architecture.md](docs/architecture.md) — components, data flow, turn lifecycle
* [docs/security.md](docs/security.md) — 5 isolation layers, threat model, test matrix
* [docs/cost.md](docs/cost.md) — fixed vs per-minute vs per-request costs
* [docs/troubleshooting.md](docs/troubleshooting.md) — failure → diagnosis → fix
* [docs/disaster-recovery.md](docs/disaster-recovery.md) — rebuild-from-zero procedure
* [docs/cleanup-guide.md](docs/cleanup-guide.md) — full teardown incl. billable resources
* [docs/manual-outline.md](docs/manual-outline.md) — 42-section DOCX + video index
* [docs/handover.md](docs/handover.md) — teaching guide (modify Python, skills, tests)

MIT licensed — see [MIT_LICENSE.txt](MIT_LICENSE.txt).
