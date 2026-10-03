# Disaster Recovery & Rebuild From Zero

Acceptance criterion: **a clean machine + a clean AWS account + only (1) this
repository, (2) the DOCX manual, (3) the videos** must reproduce a working
Canadian phone agent.

## RTO / RPO targets

| Scenario | Recovery time | Data loss |
|---|---|---|
| Single call crashes | caller redials | current call only (by design — sessions are in-memory) |
| Runtime process dies | redeploy `python scripts/deploy.py --stage runtime` (minutes) | in-flight calls only |
| Region outage | redeploy stack in a second region (skills are in S3, re-seedable) | call history not yet exported |
| Total account loss | full rebuild from zero, below | completed call records retained in S3 (if exported) |

## Rebuild procedure (clean machine + clean account)

```bash
# 1. toolchain
winget install Python.3.11 Python.Python.3.11   # Windows
winget install Amazon.AWSCLI OpenJS.NodeJS.LTS
aws configure                                   # region ca-central-1

# 2. project
git clone <repo> && cd realestate-voice-agent
python -m pip install -e ".[dev]"
python scripts/setup.py                          # .env, dirs, full test suite

# 3. infrastructure
python scripts/deploy.py --stage infra --bucket YOUR_NEW_BUCKET

# 4. configuration
copy .env.example .env                           # fill SKILL_BUCKET, DYNAMODB_TABLE
python scripts/seed_skills.py --bucket YOUR_NEW_BUCKET

# 5. runtime
python scripts/deploy.py --stage runtime         # AgentCore CLI

# 6. telephony
#   buy Canadian number → webhook https://YOUR_HOST/twilio/voice → save

# 7. verify
RUN_AWS_TESTS=1 python -m pytest -m aws
#   place a real call; confirm logs/calls.jsonl gains a record
```

No step may require undocumented manual configuration — anything the script
cannot do must appear in the DOCX with a screenshot.

## Data recovery

| Data | Source of truth | Recovered by |
|---|---|---|
| Skill `.txt` files | this repository (`skills/`) | `scripts/seed_skills.py` |
| Infrastructure | `infrastructure/cdk` | `cdk deploy` |
| Call history | DynamoDB/S3 (retained) | never deleted by deploys |
| Session memory | — | intentionally not recoverable (privacy) |
| Configuration | `.env` (out of git) | re-create from `.env.example` + secret store |

S3 and DynamoDB use `RemovalPolicy.RETAIN`, so a stack delete never
accidentally destroys knowledge or call history.

## Verification checklist after any recovery

- [ ] `curl /health` → `ok`
- [ ] test suite green (`python -m pytest -q`)
- [ ] inbound call reaches `/twilio/voice` (TwiML returned)
- [ ] greeting heard, skill routes correctly (`RT-001`)
- [ ] `logs/calls.jsonl` gains a record with the right `skills_used`
- [ ] security suite still denies `realestate_001 → cleaning_001/sofa.txt`
