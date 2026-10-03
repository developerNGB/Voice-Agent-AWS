# IAM Roles and Least Privilege

Five distinct roles — never use `AdministratorAccess` for runtime.

| Role | Assumed by | Policy |
|---|---|---|
| `AgentCoreRuntimeRole` | `bedrock-agentcore.amazonaws.com` | [runtime-policy.json](iam/runtime-policy.json) — reads **only** `agents/<its-agent-id>/*`, writes its own rows, invokes one model |
| `TelephonyRole` | Twilio webhook handlers / Lambda | [telephony-policy.json](iam/telephony-policy.json) — read secrets + session lookups |
| `LoggingRole` | log shipper / CloudWatch agent | [logging-policy.json](iam/logging-policy.json) — write logs + metrics only |
| `DeployRole` | developer running CDK + AgentCore CLI | cloudformation/s3/dynamodb/iam:PassRole for stack resources |
| `DeveloperRole` | human developer (SSO) | read-only + test-bucket write; no prod data access |

## Isolation guarantees

1. **Path isolation** — objects live under `agents/<agent_id>/`.
2. **IAM isolation** — the runtime role's `s3:prefix` condition restricts it to
   its own namespace, so even a code bug cannot read another agent's files.
3. **Application isolation** — `app/security/isolation.py` validates every
   `agent_id`/`skill_id` before any path is built.
4. **Session isolation** — one session per call; state is in memory and
   discarded at call end (no cross-session memory by design).
5. **Test isolation** — `tests/security/test_isolation.py` deliberately tries
   `realestate_001 → cleaning_001/sofa.txt` and asserts `ACCESS_DENIED`.

## Placeholders

Replace `YOUR_BUCKET_NAME`, `YOUR_TABLE_NAME`, `YOUR_REGION`, `YOUR_ACCOUNT_ID`,
`YOUR_LOG_GROUP` before applying. `scripts/deploy.py` fills these from the CDK
stack outputs automatically.
