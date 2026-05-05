# app/rag — Retrieval-Augmented Generation

Production retrieval module for the Javva agent. Provides semantic search and
hybrid (vector + BM25) search over a 204-entry FAQ knowledge base covering
forex/CFD trading topics in English and Indonesian. Two retrieval modes: pure
vector search via Qdrant cosine similarity, and hybrid search combining vector
with BM25 keyword matching via Reciprocal Rank Fusion. Imported by the agent
in Phase C — see `search_faqs` for the typical entry point.

## Public API

### Functions

- **`search_faqs(query, k=3, filters=None, score_threshold=0.5) → RetrievalResult`**
  Semantic search via Qdrant cosine similarity. Use for conceptual queries —
  paraphrases, cross-language matching, intent recognition.

- **`search_faqs_hybrid(query, k=3, filters=None) → RetrievalResult`**
  Hybrid vector + BM25 search combined via RRF. Use when queries contain exact
  terms, acronyms, codes, or numbers where pure vector tends to drift.

- **`get_retriever() → FaqRetriever`**
  Lazy module-level singleton. Use directly if you want both `.search()` and
  `.search_hybrid()` in tight loops without redoing client setup.

- **`get_keyword_searcher() → KeywordSearcher`**
  Lazy singleton for the BM25 side. Loads `data/faq_seed.json` and builds the
  in-memory index on first call (~10–50 ms).

- **`reciprocal_rank_fusion(vector_results, keyword_results, k_constant=60, vector_weight=1.0, keyword_weight=1.0) → list[tuple[int, float]]`**
  Pure function — combine two ranked lists into a single ranking via RRF.
  No API calls.

### Types

| Type | Fields | Purpose |
|---|---|---|
| `RetrievalFilter` | `category`, `language`, `tags` | Optional constraints. AND across fields, OR within tags. |
| `RetrievedFaq` | `id`, `category`, `language`, `question`, `answer`, `tags`, `score` | A single ranked result. |
| `RetrievalResult` | `query`, `results`, `total_found`, `filters_applied` | Full search response. |
| `RetrievalError` | (Exception subclass) | Wraps Qdrant/Gemini failures. Input `ValueError` passes through unwrapped. |

## Usage examples

```python
from app.rag import search_faqs, search_faqs_hybrid, RetrievalFilter

# Basic semantic search
result = search_faqs("How do I withdraw money?")
for r in result.results:
    print(r.score, r.id, r.question)

# Cross-language: ID query, mix of EN+ID FAQs in results
result = search_faqs("Apa itu KYC?")

# Force ID-only results
result = search_faqs(
    "trading basics",
    filters=RetrievalFilter(language="id"),
)

# Multi-filter (category + tags, AND across fields)
result = search_faqs(
    "leverage",
    filters=RetrievalFilter(category="forex_basics", tags=["leverage"]),
)

# Hybrid for exact terms — better recall on MT5, EUR/USD, KYC
result = search_faqs_hybrid("MT5 setup")
```

## When to use which method

| Query type | Method | Reason |
|---|---|---|
| Conceptual ("how do I withdraw") | `search()` | Vector handles paraphrasing |
| Cross-language ("apa itu leverage") | `search()` | Multilingual embeddings |
| Exact terms (MT5, EUR/USD) | `search_hybrid()` | BM25 catches exact tokens |
| Acronyms (KYC, AML, SCA) | `search_hybrid()` | Stronger keyword signal |
| Codes / numbers (USR000123) | `search_hybrid()` | Vector drifts on opaque tokens |

## Architecture

- **Vector store:** Qdrant Cloud collection `javva_kb` (768-dim, cosine, 204 points).
- **Embedding model:** `gemini-embedding-001` with `output_dimensionality=768`.
- **Task-type asymmetry:** documents indexed with `RETRIEVAL_DOCUMENT`, queries with `RETRIEVAL_QUERY` — measurably improves recall.
- **BM25:** in-memory `BM25Okapi` over `f"{question} {answer}"`; tokenizer is `re.findall(r"\w+", text.lower())`.
- **RRF:** `k_constant=60` (literature standard, Cormack et al. 2009), equal weights by default.
- **Filters:** category/language as Qdrant payload indexes (keyword type), tags as `MatchAny`. BM25 side filters in Python after scoring.
- **Singletons:** lazy-init module-level — `QdrantClient`, `genai.Client`, `KeywordSearcher`, `FaqRetriever`. One instance per process.
- **Sync API.** Wrap with `asyncio.to_thread` for FastAPI / async use.

## Score field semantics ⚠️

`RetrievedFaq.score` means different things depending on the retrieval method:

| Method | Score is... | Typical range |
|---|---|---|
| `search()` | Qdrant cosine similarity | 0.5 – 0.85 |
| `search_hybrid()` | RRF combined score | < 0.05 |

**Compare scores within a single retrieval call, not across methods.** RRF
scores are inherently small but rank-meaningful; cosine values reflect actual
similarity magnitude.

## Logging

Module emits structlog events on every search call:

| Event | Level | Fields |
|---|---|---|
| `retrieval_query` | info | `mode`, `query` (truncated 80), `k`, `filters`, `score_threshold` |
| `retrieval_result` | info | `total_found`, `returned`, `top_score`, `vector_hits` + `keyword_hits` (hybrid) |
| `retrieval_empty` | warning | `query`, `total_found`, `threshold` |
| `retrieval_embed_failed` / `retrieval_qdrant_failed` | error | `error` |
| `keyword_searcher_init` | info | `n_docs` (one-time on first hybrid call) |

Phase F observability will route these to structured logs / metrics.

## Tests

- **16 pytest tests** in `tests/unit/test_retriever.py` — basic search, filters, threshold, ordering, k limits, payload completeness, empty-query guards, hybrid basics, RRF pure-function unit, hybrid-vs-vector exact terms.
- **11 CLI scenarios** in `scripts/test_retriever.py` — interactive smoke check including 4 side-by-side hybrid-vs-vector comparisons.

Run from `backend/`:

```bash
uv run pytest tests/unit/test_retriever.py -v
uv run python scripts/test_retriever.py
```
