"""Tests for app.rag.search_faqs.

These are integration tests — they hit real Gemini and Qdrant APIs.
Required env (.env): GEMINI_API_KEY, QDRANT_URL, QDRANT_API_KEY.
The 'javva_kb' collection must already be populated by
scripts/embed_faqs.py.

Run from backend/:
    uv run pytest tests/unit/test_retriever.py -v
"""

from __future__ import annotations

import pytest

from app.rag import RetrievalFilter, search_faqs


def test_basic_search_en() -> None:
    result = search_faqs("How do I withdraw money?", k=3)
    assert result.total_found > 0
    assert len(result.results) <= 3
    assert all(r.score >= 0.5 for r in result.results)


def test_basic_search_id() -> None:
    result = search_faqs("Apa itu leverage?", k=3)
    assert result.total_found > 0
    assert len(result.results) > 0


def test_language_filter() -> None:
    result = search_faqs(
        "trading basics",
        k=5,
        filters=RetrievalFilter(language="id"),
    )
    assert all(r.language == "id" for r in result.results)


def test_category_filter() -> None:
    result = search_faqs(
        "withdraw funds",
        k=5,
        filters=RetrievalFilter(category="deposits_withdrawals"),
    )
    assert all(r.category == "deposits_withdrawals" for r in result.results)


def test_tag_filter() -> None:
    result = search_faqs(
        "explain it",
        k=5,
        filters=RetrievalFilter(tags=["leverage", "kyc"]),
    )
    for r in result.results:
        assert any(t in r.tags for t in ["leverage", "kyc"]), (
            f"unexpected tags: {r.tags}"
        )


def test_low_relevance_filtered() -> None:
    result = search_faqs("asdfghjkl random nonsense", k=3, score_threshold=0.7)
    assert len(result.results) <= 2


def test_results_sorted_by_score() -> None:
    result = search_faqs("How do I withdraw money?", k=5)
    scores = [r.score for r in result.results]
    assert scores == sorted(scores, reverse=True)


def test_k_limit() -> None:
    result = search_faqs("How do I withdraw money?", k=1)
    assert len(result.results) <= 1


def test_payload_completeness() -> None:
    result = search_faqs("How do I withdraw money?", k=1)
    assert len(result.results) >= 1
    r = result.results[0]
    assert r.id.startswith("faq-")
    assert r.category
    assert r.language in ("en", "id")
    assert r.question
    assert r.answer
    assert isinstance(r.tags, list) and len(r.tags) > 0


def test_filters_applied_passthrough() -> None:
    f = RetrievalFilter(language="en", category="forex_basics")
    result = search_faqs("leverage", k=3, filters=f)
    assert result.filters_applied is not None
    assert result.filters_applied.language == "en"
    assert result.filters_applied.category == "forex_basics"


def test_empty_query_raises() -> None:
    with pytest.raises(ValueError):
        search_faqs("", k=3)


def test_whitespace_query_raises() -> None:
    with pytest.raises(ValueError):
        search_faqs("   ", k=3)
