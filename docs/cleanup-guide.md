# Cleanup Guide

Run in this order — cheapest-to-forget first, biggest bill last.

## 1. Local artefacts (free)

```bash
python scripts/cleanup.py --list      # inventory + cost drivers
python scripts/cleanup.py --confirm   # removes logs/, empties/deletes configured AWS data
```

## 2. Telephony (⚠ bills monthly from day one)

* **Twilio**: Console → Phone Numbers → your Canadian number → **Release**.
  Removing the webhook first stops call charges immediately.
* **Amazon Connect**: delete the contact flow / instance if you chose Connect.

## 3. AgentCore runtime

```bash
agentcore delete --name realestate-voice-agent
```

Stops per-runtime charges.

## 4. Infrastructure

```bash
cd infrastructure/cdk
cdk destroy          # deletes stack; S3/DynamoDB are RETAIN → step 5 handles them
```

CloudWatch log groups and alarms created by the stack are removed here.

## 5. Retained data (⚠ still bills storage)

```bash
python scripts/cleanup.py --confirm   # empties + deletes the skill bucket and table
```

Or in the console: empty the S3 bucket (including versions) → delete bucket;
delete the DynamoDB table.

## 6. Secrets

* delete `OPENAI_API_KEY` / `GEMINI_API_KEY` from the runtime environment
* Secrets Manager → delete `voice-agent/twilio-*` (with recovery window)
* delete local `.env`

## 7. IAM

```bash
cd infrastructure/cdk && cdk destroy   # removes the roles it created
```

Manually detach/delete any roles you attached the JSON policies from
`infrastructure/iam/` to.

## Billable-resource warning table

| Resource | Bills after creation? | Stopped by |
|---|---|---|
| Phone number | **yes, monthly** | releasing the number |
| Call minutes | **yes, per call** | releasing the number / removing webhook |
| AgentCore runtime | yes, while deployed | `agentcore delete` |
| S3 storage | yes, per GB (tiny) | step 5 |
| DynamoDB | yes, per GB (tiny) | step 5 |
| CloudWatch logs/alarms | yes, per GB/alarm | `cdk destroy` |
| Bedrock/Polly/Transcribe | per use | stops with the runtime |

## Verifying zero spend

AWS Console → Billing → **Cost Explorer** (filter: last 30 days, service).
Twilio Console → **Usage**. Expect only prorated leftovers for the day of
teardown.
