# app/agent — Production AI Agent

## Overview

Pydantic AI-based customer support agent for the Javva forex/CFD trading
platform. Combines RAG knowledge (Phase B) with structured tool calling over
the user database (Phase A.2). Supports bilingual conversation (English +
Bahasa Indonesia) with multi-turn context retention.

## Public API

### Functions

- **`chat(user_message, message_history=None) → ChatResponse`** — main entry
  point. Stateless async function; the caller passes `message_history`
  between turns.
- **`get_agent() → Agent`** — lazy singleton accessor for the underlying
  Pydantic AI `Agent`. Useful if you want to bypass `chat()` and call
  `agent.run()` directly.
- **`summarize_messages(message_history) → dict`** — extract conversation
  stats (`turn_count`, `user_messages`, `tool_calls`, `assistant_responses`)
  from a message history list. Phase D will use this for HTTP API metrics.

### Types

| Type | Purpose |
|---|---|
| `ChatResponse` | reply, message_history, tools_called, usage, duration_ms, error |
| `FaqSearchInput` / `FaqSearchOutput` | `search_faqs_tool` I/O |
| `AccountLookupInput` / `AccountLookupOutput` / `AccountInfo` | `lookup_account_tool` I/O |
| `ListTransactionsInput` / `ListTransactionsOutput` / `TransactionInfo` | `list_transactions_tool` I/O |
| `CheckKycStatusInput` / `CheckKycStatusOutput` / `KycStatusInfo` | `check_kyc_status_tool` I/O |
| `EscalateInput` / `EscalateOutput` | `escalate_to_human_tool` I/O |

## Tools (5)

| Tool | Purpose | When the agent uses it |
|---|---|---|
| `search_faqs_tool` | RAG over FAQ knowledge base | General "how does X work" questions |
| `lookup_account_tool` | DB query by user_id | User mentions USR000XXX or asks about their account |
| `list_transactions_tool` | Filtered transaction history | Withdrawal/deposit/trade activity questions |
| `check_kyc_status_tool` | KYC verification status | "Why is my withdrawal restricted?" |
| `escalate_to_human_tool` | Generate ticket | Complaints, fraud, repeated failures, hostile users |

## Usage

```python
from app.agent import chat

# Single turn
result = await chat("How do I withdraw money?")
print(result.reply)
print(f"Tools: {result.tools_called}")
print(f"Duration: {result.duration_ms}ms")

# Multi-turn
result1 = await chat("I want to know about deposits")
result2 = await chat(
    "What about IDR specifically?",
    message_history=result1.message_history,
)
```

## Architecture

- **Framework:** Pydantic AI 1.x
- **Model:** `gemini-2.5-flash-lite` (free-tier testing) or `gemini-2.5-flash`
  (production). Set via `GEMINI_DEFAULT_MODEL` in `.env`.
- **Tool registration:** auto-schema from each tool's Pydantic input model
  (single `input: SomeInputModel` argument).
- **Async:** stateless `chat()`. Sync I/O (psycopg, app.rag) wrapped via
  `asyncio.to_thread`.
- **Singleton:** lazy-init `Agent` via `get_agent()`. One instance per
  process.
- **Timeout:** 30s hard timeout via `asyncio.wait_for(agent.run(...), 30.0)`.
- **Retries:** 4 (compensates for flash-lite occasional malformed structured
  output on FAQ tool calls).

## System Prompt

See [`prompts.py`](prompts.py). 938 words / ~1.6K tokens, 9 markdown sections:

- Identity, Tools Available, When to Use Which Tool
- Tone Guidelines (4 tones from Phase A.3 eval taxonomy: informational,
  professional, empathetic, apologetic)
- Response Format, Multi-Turn Conversations
- Safety Rules (no trading advice, no return promises, no hallucinated FAQ
  answers, escalate fraud/threats)
- Language Handling (EN + Bahasa Indonesia)
- 3 few-shot examples (EN FAQ, ID account query, escalation)

## Error Handling

The agent **never raises**. Every failure mode returns a `ChatResponse`:

| Failure | `error` field | User-facing `reply` |
|---|---|---|
| Tool failure (DB / RAG) | tool returns `found=False, error="..."`; agent reads it | agent generates appropriate response from tool's error |
| Network / API error | `str(e)[:200]` | apology message |
| 429 quota | `str(e)[:200]` | apology message |
| Validation failure (after retries) | `str(e)[:200]` | apology message |
| Timeout (>30s) | `"timeout"` | "request is taking longer than expected" |

This guarantees Phase D's HTTP API can call `chat()` without a try/except
wrapper — the response is always a structured `ChatResponse`.

## Testing

- **CLI smoke test:** 14 scenarios covering basic FAQ, account queries,
  multi-tool turns, multi-turn context, hostile escalation, off-topic
  redirect, ambiguous user_id.
  ```bash
  uv run python scripts/test_agent.py
  ```
- **Pytest:** 11 integration tests covering the same scenarios.
  ```bash
  uv run pytest tests/unit/test_agent.py -v
  ```

Both hit real Gemini + Postgres + Qdrant. The pytest suite uses a sync
autouse `throttle` fixture (7s after each test) to stay clear of Gemini
RPM caps.

## Known Issues / Notes

1. **Free-tier daily quota.** All `gemini-2.5` models on free tier share a
   20-request-per-day cap (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`).
   Enabling GCP billing does NOT auto-promote the project to a paid tier;
   that requires explicit upgrade in the Cloud Console. Throttle for tests
   or move to a paid-tier project.
2. **flash-lite output validation.** flash-lite occasionally produces
   slightly malformed structured output on FAQ tool calls (manifests as
   `Exceeded maximum retries for output validation`). `Agent(retries=4)`
   absorbs most of these.
3. **Async fixture pattern.** Tests use a sync `time.sleep` autouse fixture
   instead of an async one — pytest-asyncio's per-function event-loop scope
   tears down the loop before an async fixture's post-yield `await` can
   complete (`Event loop is closed` errors).

## Logging Events (structlog)

| Event | Source | Fields |
|---|---|---|
| `agent_initialized` | `get_agent()` | `model`, `tool_count` (once per process) |
| `chat_request` | `chat()` | `message` (truncated 100), `history_length` |
| `chat_response` | `chat()` success | `tools_called`, `total_tokens`, `duration_ms` |
| `chat_failed` | `chat()` exception | `error`, `duration_ms` |
| `chat_timeout` | `chat()` 30s wait_for | `duration_ms` |
| `tool_search_faqs` / `tool_lookup_account` / etc. | each tool | per-tool input fields |

Phase F observability will route these to structured logs and dashboards.
