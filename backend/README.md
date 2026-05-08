# Javva Backend

AI customer support agent for the Javva forex/CFD trading platform.
Bilingual (English + Bahasa Indonesia), tool-calling agent over a real
RAG knowledge base and seeded user database.

## Modules

| Module | Status | Description |
|---|---|---|
| `app.config` | ✓ | Pydantic Settings reading from `.env` |
| [`app.rag`](app/rag/README.md) | ✓ Phase B | RAG pipeline — vector search (Qdrant) + hybrid (BM25 + RRF) |
| [`app.agent`](app/agent/README.md) | ✓ Phase C | Pydantic AI agent loop with 5 tools |
| `app.routes` | ⏳ Phase D | FastAPI HTTP endpoints |
| `app.observability` | ⏳ Phase F | Langfuse tracing + metrics |
| `app.security` | ⏳ Phase G | PII redaction (Presidio), JWT auth |

## Data

- **204** multilingual FAQ entries — `data/faq_seed.json` (Phase A.1)
- **1,000** mock user accounts — Postgres (Phase A.2)
- **13,905** transactions across `accounts` (Phase A.2)
- **1,000** KYC status records, one per account (Phase A.2)
- **100** evaluation test cases — `data/eval_cases.json` (Phase A.3)

## Quick Start

```bash
cd backend
uv sync                        # install deps from pyproject.toml + uv.lock
cp .env.example .env           # then fill in credentials
uv run python scripts/test_agent.py   # CLI smoke test (14 scenarios)
```

## Architecture

```
User Message
    ↓
[Agent Loop (app.agent)]
    ↓
├── Tool: search_faqs        → [RAG Pipeline (app.rag)] → Qdrant Cloud
├── Tool: lookup_account     → Postgres (Supabase)
├── Tool: list_transactions  → Postgres (Supabase)
├── Tool: check_kyc_status   → Postgres (Supabase)
└── Tool: escalate_to_human  → ticket generation (in-memory; Phase D persists)
    ↓
ChatResponse → User
```

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11 |
| Package manager | uv |
| Web framework | FastAPI (Phase D) |
| Agent framework | Pydantic AI 1.x |
| LLM | Gemini 2.5 Flash / Flash-Lite (`gemini-embedding-001` for embeddings) |
| Vector store | Qdrant Cloud |
| Database | Postgres on Supabase |
| Observability | structlog (today) → Langfuse (Phase F) |

## Module READMEs

- [`app/rag/README.md`](app/rag/README.md) — retrieval API, types, and when to use which method
- [`app/agent/README.md`](app/agent/README.md) — agent API, tool reference, error contract

## Tests

```bash
# RAG retrieval (16 tests)
uv run pytest tests/unit/test_retriever.py -v

# Agent loop (11 tests — integration, hits real LLM + DB + Qdrant)
uv run pytest tests/unit/test_agent.py -v

# Tool implementations (9 tests)
uv run pytest tests/unit/test_tools.py -v
```

## Scripts

| Script | Purpose |
|---|---|
| `scripts/migrate_db.py` | Create Postgres tables + indexes (idempotent) |
| `scripts/seed_accounts.py` | Seed 1,000 accounts + 13.9K transactions + 1K KYC |
| `scripts/generate_faq.py` | Generate FAQ corpus via Gemini (with checkpointing) |
| `scripts/embed_faqs.py` | Embed FAQs into Qdrant `javva_kb` collection |
| `scripts/verify_qdrant.py` | Inspect Qdrant collection + run test queries |
| `scripts/generate_eval.py` | Generate 100 eval cases via Gemini |
| `scripts/normalize_eval_tags.py` | Map Indonesian tag stems to English (post-process) |
| `scripts/test_retriever.py` | 11 CLI scenarios for retrieval (vector + hybrid) |
| `scripts/test_tools.py` | 10 CLI scenarios for the 5 tools |
| `scripts/test_agent.py` | 14 CLI scenarios for the agent loop |
| `scripts/test_prompt.py` | Validate system prompt structure |
