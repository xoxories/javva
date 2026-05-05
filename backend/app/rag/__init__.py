"""FAQ retrieval module — semantic search over Qdrant 'javva_kb'.

Imported by the agent in Phase C. Public API:

    RetrievalFilter        - filter spec (category / language / tags)
    RetrievedFaq           - a single result
    RetrievalResult        - full response (results + total_found + filters_applied)
    RetrievalError         - raised on Qdrant / Gemini failures
    FaqRetriever           - the workhorse class
    get_retriever()        - lazy module-level singleton
    search_faqs()          - one-shot convenience helper

Quickstart:
    from app.rag import search_faqs, RetrievalFilter
    result = search_faqs("How do I withdraw money?", k=3)
    for r in result.results:
        print(r.score, r.id, r.question)
"""

from app.rag.hybrid import reciprocal_rank_fusion
from app.rag.keyword import KeywordSearcher, get_keyword_searcher
from app.rag.retriever import (
    FaqRetriever,
    RetrievalError,
    get_retriever,
    search_faqs,
    search_faqs_hybrid,
)
from app.rag.schemas import RetrievalFilter, RetrievalResult, RetrievedFaq

__all__ = [
    "FaqRetriever",
    "KeywordSearcher",
    "RetrievalError",
    "RetrievalFilter",
    "RetrievalResult",
    "RetrievedFaq",
    "get_keyword_searcher",
    "get_retriever",
    "reciprocal_rank_fusion",
    "search_faqs",
    "search_faqs_hybrid",
]
