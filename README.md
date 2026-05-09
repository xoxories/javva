# Javva (TradeAssist)

AI customer support agent for forex/CFD trading platforms. Bilingual
(EN/ID), tool-calling, RAG, observable, evaluated.

## 🌐 Live Demo

- **Backend API**: https://javva-production.up.railway.app
- **API Docs (Swagger)**: https://javva-production.up.railway.app/docs

Try asking:

- "What is KYC?" (English FAQ)
- "Apa itu margin call?" (Indonesian FAQ)
- "I can't login to my account" (escalation flow)
- "User ID USR000123" (account lookup)

## 📊 Evaluation Results (100 cases)

| Dimension | Score |
|-----------|-------|
| Pass rate (overall ≥ 70%) | **69.0%** |
| Accuracy | 64.6% |
| Tone | 90.7% |
| Tool selection | 68.7% |
| Language matching | 94.0% |

Judge: Gemini 2.5 Pro (different tier from the agent's Flash-Lite).
Full breakdown, charts, and failure analysis:
[backend/app/eval/results/REPORT.md](backend/app/eval/results/REPORT.md).

## 🏗️ Architecture

```
┌─────────────┐      ┌──────────────┐      ┌──────────────┐
│   Vercel    │─────▶│   Railway    │─────▶│  Vertex AI   │
│  (Next.js)  │      │  (FastAPI)   │      │  Gemini 2.5  │
└─────────────┘      └──────────────┘      └──────────────┘
                            │  │  │
                            │  │  └────▶ Qdrant Cloud (vector)
                            │  └───────▶ Supabase (Postgres)
                            └──────────▶ Langfuse (observability)
```

## 🛠️ Tech Stack

### Backend

- FastAPI 0.115+ (async Python)
- Pydantic AI 1.x (agent framework)
- Vertex AI Gemini 2.5 Flash-Lite (LLM)
- Qdrant Cloud (vector search, hybrid retrieval)
- Supabase (PostgreSQL, sessions)
- Langfuse (observability)
- uv (package manager)
- Python 3.11

### Frontend

- Next.js 16 (App Router)
- TypeScript
- Tailwind CSS v4
- shadcn/ui components
- framer-motion (animations)
- next-themes (dark/light)

### Infrastructure

- Vercel (frontend)
- Railway (backend)

## ✨ Features

- **Bilingual**: auto-detects EN/ID, sticky language across turns
- **Tool-calling**: 5 tools — FAQ Search, Account Lookup,
  Transactions, KYC Check, Escalation
- **RAG**: hybrid retrieval (vector + keyword) over a 204-entry FAQ
  corpus
- **Multi-turn**: session-based context (60-min TTL, recreate-on-stale)
- **Production observability**: Langfuse traces every chat request
  (input, output, tools called, duration, tokens)
- **Quantitative evaluation**: 100-case LLM-as-judge pipeline with
  per-dimension scoring and chart generation
- **Modern UI**: dark fintech aesthetic, mobile-responsive, theme
  toggle, language switcher

## 🚀 Local Development

See [docs/setup.md](docs/setup.md) and
[docs/architecture.md](docs/architecture.md).

## 📐 Engineering Notes

### Phases (30+ atomic commits)

- **Phase A** — Data foundation: FAQs, eval cases, mock account data
- **Phase B** — RAG pipeline: Qdrant + hybrid (vector + keyword) search
- **Phase C** — Backend agent: Pydantic AI + 5 tools + system prompt
- **Phase D** — HTTP API: FastAPI + X-API-Key auth + sessions
- **Phase E** — Frontend: Next.js 16 chat UI with markdown, tool
  badges, animations
- **Phase F** — Observability: Langfuse v4 integration
- **Phase H** — Evaluation: LLM-as-judge pipeline (Gemini 2.5 Pro),
  100 real cases scored
- **Phase Deploy** — Railway + Vercel, service-account base64 decoder,
  nixpacks config

### Decisions Documented

- Vertex AI over direct Gemini API (production billing, GCP credit;
  the direct API caps at 20 RPD on `gemini-2.5-*` free tier)
- LLM-as-judge with Gemini 2.5 Pro — different tier from the agent's
  Flash-Lite to reduce same-family rubber-stamping
- Hybrid retrieval (vector + keyword via RRF) for FAQ matching
- Session-based memory (60-min TTL, recreate-on-stale pattern)
- Service-Account base64 decoder so production platforms without
  filesystem persistence can still authenticate Vertex AI
- Honest commit messages — when a Phase H commit message described a
  `--judge` CLI flag that didn't exist, dropped the bullet rather
  than ship a misleading message

### Real-World Catches

- pydantic-ai 1.90.0's split `GoogleVertexProvider` had an
  `'AsyncClient' object has no attribute 'aio'` bug → switched to
  the unified `GoogleProvider(vertexai=True, ...)`
- langfuse v4 dropped the v2/v3 `Langfuse.trace()` API in favour of
  OpenTelemetry-style `start_observation` + `propagate_attributes` —
  rewrote the integration accordingly
- GCP free-tier 20-requests-per-day cap on `gemini-2.5-*` → migrated
  to Vertex AI Cloud Prepay (the credit applies to Vertex billing,
  not direct Gemini)
- Nixpacks default config tried `pip install uv==$NIXPACKS_UV_VERSION`
  with the env var undefined → committed an explicit
  `backend/nixpacks.toml`
- `create-next-app` shipped `frontend/AGENTS.md` and
  `frontend/CLAUDE.md` containing prompt-injection text aimed at AI
  coding assistants → flagged and deleted

## 📄 License

MIT — see [LICENSE](LICENSE) (or apply your own).

---

Built for the Deriv Malaysia AI Engineer internship application.
