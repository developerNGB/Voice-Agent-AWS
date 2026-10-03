# Architecture

## Principle

Separate **voice transport**, **agent reasoning**, **skill routing**,
**knowledge storage**, **session state** and **model provider** so each can be
understood, tested and replaced independently.

```
Phone number ─► voice transport ─► AgentCore ─► session ─► router ─►
authorized skill ─► LLM ─► voice response
```

## Components

| Component | File | Responsibility |
|---|---|---|
| FastAPI gateway | `app/main.py` | `/ws` (AgentCore JSON contract), Twilio webhook + media stream |
| Voice gateway | `app/gateway.py` | per-call bridge: endpoint detection in, TTS out, barge-in |
| VoiceAgent | `app/agent/agent.py` | the turn loop: guardrail → profile → routing → prompt → LLM → logs |
| SessionLifecycle | `app/agent/lifecycle.py` | state machine `CALL_STARTED → … → SESSION_CLOSED` |
| ContextManager | `app/agent/context.py` | extracts name/budget/bedrooms/intent/timeline (PII-minimised) |
| ToolBox | `app/agent/tools.py` | `search_skills, load_skill, switch_skill, create_lead, schedule_viewing, save_call, end_call` — every tool authorizes first |
| SkillRouter | `app/router/skill_router.py` | `extract → candidate_search → score → confidence → activate/clarify/keep/none` |
| SkillRegistry | `app/skills/registry.py` | header index per agent; content loaded lazily |
| SkillStore | `app/skills/loader.py` | `LocalSkillStore` / `S3SkillStore`, both agent-scoped |
| LLM providers | `app/llm/` | `BedrockProvider` (default), `OpenAIProvider`, `GeminiProvider`, `MockLLMProvider` |
| Voice providers | `app/voice/` | `EndpointDetector` (energy VAD), `BargeInController`, Polly TTS, Transcribe STT, mocks |
| Storage | `app/storage/` | JSONL structured logs (always), DynamoDB + S3 (when configured) |

## One turn, step by step

```
caller utterance (text or STT transcript)
 1. per-session asyncio lock acquired           (no interleaved turns)
 2. injection guard → refuse + log security event
 3. ContextManager extracts caller facts
 4. SkillRouter.route(agent_id, text, session)
      header index → candidate search → scoring → thresholds
      activate  → ACTIVE_SKILL replaced, routing event logged
      clarify   → deterministic "Did you mean …?" (never the LLM)
      keep      → skill lock holds (follow-up question)
      none      → no skill referenced
 5. lead capture (after routing, so it can reference the skill)
 6. prompt = small SYSTEM PROMPT
             + session context        (this call only)
             + <active_skill> data    (one file, wrapped as data)
             + last 6 turns + utterance
 7. LLM with timeout + retry → safe fallback on failure
 8. transcript turns appended, Turn returned to gateway
```

## Session lifecycle

```
CALL_STARTED → CREATE_SESSION → IDENTIFY_AGENT → INITIALIZE_CONTEXT
→ VOICE_CONVERSATION ⇄ SKILL_ROUTING ⇄ SKILL_ACTIVE
→ CALL_ENDED → FINALIZE_LOG → SESSION_CLOSED
```

State lives **in memory only** and dies with the call: there is deliberately no
long-term conversational memory, so `SESSION A` can never inform `SESSION B`.

## Skill locking & recovery

* A confident match **locks** `ACTIVE_SKILL`.
* Follow-ups that match nothing keep the lock (they belong to the active skill).
* A confident match on a *different* skill **switches** the lock (topic change).
* An ambiguous match asks the caller to choose; the answer replaces the pending
  candidates and activates the chosen skill.
* A concrete address that matches nothing → the fixed "not in my available
  listings" reply (never a guess).

## Scoring (deterministic, unit-tested)

| Signal | Score |
|---|---|
| exact keyword/name phrase inside the request | 0.95 |
| caller's number equals the skill's number | 0.92 |
| caller's number conflicts with the skill's number | 0.35 |
| shared street name, number-less keyword phrase | ≤ 0.60 |
| partial token overlap (ambiguous) | 0.45 – 0.70 |
| thresholds | activate ≥ 0.75, clarify ≥ 0.45 |

Margin rule: activation also requires ≥ 0.10 lead over the runner-up, otherwise
the router clarifies.

## Provider abstraction

```python
class LLMProvider:      async def generate(request) -> LLMResponse
class SpeechToTextProvider: async def feed_audio(frame) -> [Transcript]
class TextToSpeechProvider: async def synthesize(text) -> AudioChunk
```

`MODEL_PROVIDER=bedrock|openai|gemini|mock` and `STT/TTS_PROVIDER=mock|aws`
switch implementations without touching agent code.

## Concurrency

One `asyncio.Lock` per session, one `Session` object per call, sessions stored
in a dict keyed by `session_id`. Three simultaneous callers keep independent
history, active skill, profile, tools and logs (see
`tests/concurrency/test_parallel_calls.py`).
