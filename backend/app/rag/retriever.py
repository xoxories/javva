"""FAQ retrieval over Qdrant collection 'javva_kb'.

Imported by the agent in Phase C. See `search_faqs()` for the convenience
entry point and `FaqRetriever.search()` for full control.

Notes for callers:
    - Sync API today; the agent (Phase C, FastAPI/async) can wrap with
      asyncio.to_thread() until a real async path is needed.
    - Cross-language retrieval works natively due to Gemini's multilingual
      embeddings — an EN query can match ID FAQs and vice versa.
    - Qdrant filters on payload fields (category, language, tags) compose
      with AND across fields and OR within the tags list.
"""

from __future__ import annotations

import structlog
from qdrant_client import QdrantClient, models

from app.config import settings
from app.rag.embedder import embed_query
from app.rag.schemas import RetrievalFilter, RetrievalResult, RetrievedFaq


COLLECTION_NAME = "javva_kb"

log = structlog.get_logger(__name__)


class RetrievalError(Exception):
    """Raised when retrieval fails due to a Qdrant or Gemini issue.

    Wraps the underlying exception; callers can catch this single type
    and inspect the cause via `__cause__`. Input-validation errors
    (e.g. empty query) are NOT wrapped — they pass through as-is.
    """


class FaqRetriever:
    """Semantic search over the Javva FAQ knowledge base.

    Holds a single QdrantClient; safe to reuse across queries. Use
    `get_retriever()` for the module-level singleton.
    """

    def __init__(self, collection_name: str = COLLECTION_NAME) -> None:
        if not settings.qdrant_url:
            raise RuntimeError("QDRANT_URL is not set in .env")
        if not settings.qdrant_api_key:
            raise RuntimeError("QDRANT_API_KEY is not set in .env")
        self.collection_name = collection_name
        self.qdrant = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )

    def search(
        self,
        query: str,
        k: int = 3,
        filters: RetrievalFilter | None = None,
        score_threshold: float = 0.5,
    ) -> RetrievalResult:
        """Semantic search over the FAQ knowledge base.

        Args:
            query: User's question in any language.
            k: Maximum number of results to return.
            filters: Optional category / language / tag constraints.
            score_threshold: Minimum cosine similarity (0..1). Results
                below this are dropped from the response.

        Returns:
            RetrievalResult with results sorted by descending score.
            `total_found` reflects the candidate count BEFORE the
            threshold filter.

        Raises:
            ValueError: from `embed_query` if `query` is empty.
            RetrievalError: if embedding or Qdrant query fails.
        """
        filters_dict = filters.model_dump(exclude_none=True) if filters else {}
        log.info(
            "retrieval_query",
            query=query[:80],
            k=k,
            score_threshold=score_threshold,
            filters=filters_dict,
        )

        # Embed — let ValueError pass through for input-validation issues;
        # wrap anything else as RetrievalError so callers have one type.
        try:
            query_vec = embed_query(query)
        except ValueError:
            raise
        except Exception as e:
            log.error("retrieval_embed_failed", error=str(e))
            raise RetrievalError(f"Embedding failed: {e}") from e

        qdrant_filter = self._build_qdrant_filter(filters)

        # Over-fetch k*2 so the score-threshold filter has headroom while
        # still respecting the caller's k.
        try:
            response = self.qdrant.query_points(
                collection_name=self.collection_name,
                query=query_vec,
                query_filter=qdrant_filter,
                limit=k * 2,
                with_payload=True,
            )
        except Exception as e:
            log.error("retrieval_qdrant_failed", error=str(e))
            raise RetrievalError(f"Qdrant query failed: {e}") from e

        raw_points = response.points
        above = [p for p in raw_points if p.score >= score_threshold]
        top_k = above[:k]

        results: list[RetrievedFaq] = []
        for p in top_k:
            payload = p.payload or {}
            results.append(
                RetrievedFaq(
                    id=payload.get("id", ""),
                    category=payload.get("category", ""),
                    language=payload.get("language", ""),
                    question=payload.get("question", ""),
                    answer=payload.get("answer", ""),
                    tags=payload.get("tags", []),
                    score=float(p.score),
                )
            )

        if not results:
            log.warning(
                "retrieval_empty",
                query=query[:80],
                total_found=len(raw_points),
                threshold=score_threshold,
            )
        else:
            log.info(
                "retrieval_result",
                total_found=len(raw_points),
                returned=len(results),
                top_score=results[0].score,
            )

        return RetrievalResult(
            query=query,
            results=results,
            total_found=len(raw_points),
            filters_applied=filters,
        )

    @staticmethod
    def _build_qdrant_filter(f: RetrievalFilter | None) -> models.Filter | None:
        if f is None:
            return None
        conditions: list[models.FieldCondition] = []
        if f.category:
            conditions.append(
                models.FieldCondition(
                    key="category",
                    match=models.MatchValue(value=f.category),
                )
            )
        if f.language:
            conditions.append(
                models.FieldCondition(
                    key="language",
                    match=models.MatchValue(value=f.language),
                )
            )
        if f.tags:
            # MatchAny = OR semantics across the tag list.
            conditions.append(
                models.FieldCondition(
                    key="tags",
                    match=models.MatchAny(any=f.tags),
                )
            )
        return models.Filter(must=conditions) if conditions else None


_retriever_instance: FaqRetriever | None = None


def get_retriever() -> FaqRetriever:
    """Return the module-level singleton FaqRetriever (lazy-init)."""
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = FaqRetriever()
    return _retriever_instance


def search_faqs(
    query: str,
    k: int = 3,
    filters: RetrievalFilter | None = None,
    score_threshold: float = 0.5,
) -> RetrievalResult:
    """Convenience: one-shot retrieval via the singleton FaqRetriever."""
    return get_retriever().search(
        query=query,
        k=k,
        filters=filters,
        score_threshold=score_threshold,
    )
