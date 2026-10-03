# Cost Documentation

Fill every figure below with the vendor's published price **on the delivery
date** — record the date and source URL next to each number in the final
manual. Costs fall into three buckets.

## 1. Fixed monthly costs

| Item | Billing | Notes |
|---|---|---|
| Canadian phone number (Twilio) | monthly per number | release it in the Twilio console to stop billing |
| Amazon Connect (alternative) | monthly per number, varies by province | choose one telephony provider, not both |
| AgentCore Runtime | per runtime deployment/hour | see AWS pricing page at delivery time |
| CloudWatch alarms | per alarm/month | 2 alarms in the CDK stack |
| S3 (empty bucket) | negligible | storage per GB |
| DynamoDB (idle) | negligible | per GB stored |

## 2. Per-minute / per-request costs

| Item | Unit | Driven by |
|---|---|---|
| Phone call minutes | per minute | call duration + Canadian inbound rate |
| Twilio media streaming | per minute | simultaneous calls |
| STT (Transcribe streaming) | per minute of audio | call duration |
| TTS (Polly) | per 1M characters | average reply length × calls |
| LLM (Bedrock Nova / OpenAI / Gemini) | per 1M input+output tokens | prompt size (skill content!) × turns |
| Data transfer | per GB | media streams out |

## 3. One-time / development costs

AWS account, domain/tunnel for the webhook, DOCX/video production time.

## Cost-control levers (implemented)

1. **Header-index routing** — only one skill file enters the prompt, not the
   whole knowledge base → directly cuts LLM input tokens.
2. **Small system prompt** — role/voice/rules only, no listing data.
3. **Short voice replies** — enforced by the prompt (`one or two sentences`)
   → fewer TTS characters.
4. **Session memory is in-memory** — no long-term memory storage bill.
5. **`mock` providers** — full test suite and demo run with $0 AWS usage.
6. **Log retention 30 days**, DynamoDB TTL 90 days.
7. **Alarm on error rate/latency** — catches runaway retries before they bill.

## Worked example (fill in at delivery)

| Scenario | Assumption | Formula | Cost |
|---|---|---|---|
| 100 calls × 3 min | — | 300 min × per-minute rate | CAD ___ |
| 1,000 turns LLM | ~1.5k input tokens each | 1.5M in + 0.3M out × rates | CAD ___ |
| TTS for 1,000 replies | ~60 chars each | 60k characters | CAD ___ |
| Storage | 1 GB S3 + 50 MB DynamoDB | — | CAD ___ |

## Where to watch it

* AWS Console → **Billing dashboard** (set a monthly budget alarm at CAD ___)
* Twilio Console → **Usage** (set a spending limit)
* CloudWatch alarms from the CDK stack
* `logs/calls.jsonl` → `duration_seconds` per call for per-minute forecasting
