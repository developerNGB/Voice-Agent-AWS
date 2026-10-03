# Developer Handover Guide

After handover the client must be able to modify each part independently.
Every section: what to change → how to test → how to deploy.

## 1. Repository map (5-minute tour)

```
app/agent/     turn loop, prompts, lifecycle, tools      ← start here
app/router/    skill selection (matcher → scorer → router)
app/skills/    .txt parsing + loading + header registry
app/llm/       model providers (one per vendor)
app/voice/     STT/TTS, endpoint detection, barge-in
app/security/  isolation, authorization, sanitization
app/storage/   JSONL logs, S3, DynamoDB
app/main.py    FastAPI: /ws + Twilio webhook/media
skills/        knowledge, one folder per agent namespace
tests/         unit · routing · security · concurrency · voice · regression
```

Read in this order: `app/agent/agent.py` → `app/router/skill_router.py` →
`app/skills/parser.py` → `tests/regression/evaluation_dataset.json`.

## 2. Add / edit / remove a property (no code changes)

1. Copy an existing file: `skills/realestate_001/property_001.txt` →
   `property_005.txt`.
2. Edit `SKILL_ID` (must equal the filename stem), `NAME`, `KEYWORDS`,
   `CONTENT`.
3. Validate + upload: `python scripts/seed_skills.py --bucket YOUR_BUCKET`.
4. Test routing: add a case to `tests/regression/evaluation_dataset.json`
   or run the app and say the address.

```bash
python -m pytest tests/routing -q
```

Remove = delete the file + its dataset rows. The router only sees files that
exist, so removal takes effect on the next registry refresh (process restart
or redeploy).

## 3. Add a new business type (the point of the architecture)

Real estate is **not** hard-coded. To add e.g. a cleaning business:

1. Create `skills/cleaning_001/sofa.txt` (already in this repo as an example).
2. Register the number in `config/agents.json`:

```json
{ "agent_id": "cleaning_001", "business_type": "cleaning",
  "phone_number": "+14165550200", "skill_namespace": "cleaning_001",
  "greeting": "Thank you for calling Fresh Home Cleaning…" }
```

3. Set `AGENT_ID=cleaning_001` in the runtime env (one runtime per agent).
4. Nothing in `app/agent`, `app/router`, `app/voice` changes.
   Business-specific behaviour comes from `business_type` + skill files; the
   system prompt's `ROLE` line is the only place to specialise further
   (`app/agent/prompts.py`).

Caller says *"I need my sofa cleaned"* → router matches `sofa` → same flow.

## 4. Modify Python

| Goal | File(s) | Test to update |
|---|---|---|
| Change reply style/length | `app/agent/prompts.py` | add/adjust an RT case |
| Change routing thresholds | `app/config.py` (or env `SKILL_ACTIVATE_THRESHOLD`) | `tests/routing/test_skill_router.py`, RT dataset |
| Change scoring | `app/router/scorer.py` | `tests/routing/test_scorer.py` (bands are asserted) |
| Add a tool | `app/agent/tools.py` (authorize first!) + call it from `agent.py` | `tests/unit/test_tools.py` |
| Add a field callers ask about | `app/llm/mock.py` `WANT_FIELD`/`FIELD_LABELS` + skill `CONTENT` label | RT-013 |
| Change guardrails | `app/security/sanitization.py` | `tests/security/test_isolation.py` |

```bash
python -m pytest -q            # always: full suite before deploying
```

## 5. Modify tests

* **New regression scenario**: append to
  `tests/regression/evaluation_dataset.json` with id `RT-016…` — the driver
  picks it up automatically.
* **New security test**: add the attack string + expected `ACCESS_DENIED`
  to `tests/security/test_isolation.py`.
* **New routing expectation**: `tests/routing/test_skill_router.py`.
* **Voice behaviour**: `tests/voice/test_streaming.py` (endpoint/barge-in).

Test layers: unit → routing → voice → security → concurrency → regression →
integration (live AWS only with `RUN_AWS_TESTS=1`).

## 6. Modify deployment

```bash
python scripts/deploy.py --dry-run           # see every command
python scripts/deploy.py --stage infra --bucket YOUR_BUCKET
python scripts/deploy.py --stage runtime
python scripts/cleanup.py --list             # teardown inventory
```

Infrastructure lives in `infrastructure/cdk/stack.py`; IAM boundaries in
`infrastructure/iam/` and [infrastructure/README.md](../infrastructure/README.md).
Never grant runtime roles `AdministratorAccess`.

## 7. Switch model vendor

```dotenv
MODEL_PROVIDER=openai      # bedrock | openai | gemini | mock
OPENAI_API_KEY=…           # from env / AgentCore identity vault, never git
```

Implementing a new vendor = one class in `app/llm/` implementing
`generate(request) -> LLMResponse`, plus one branch in `app/llm/factory.py`.

## 8. Common mistakes to avoid

1. Putting listing facts in the system prompt — knowledge belongs in skills.
2. Trusting skill text as instructions — always wrapped as data.
3. Storing caller data beyond the call — sessions must stay ephemeral.
4. Adding a tool without `authorize_*` first.
5. Committing `.env` or real credentials (screenshots/videos included).
