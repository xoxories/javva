"""Pydantic types for FAQ retrieval requests and responses."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RetrievalFilter(BaseModel):
    """Optional filters narrowing FAQ retrieval results.

    All fields are optional. When multiple are set they combine with AND
    semantics. The `tags` field uses OR semantics within itself — match
    if the FAQ has ANY of the listed tags.
    """

    category: str | None = None
    language: Literal["en", "id"] | None = None
    tags: list[str] | None = None


class RetrievedFaq(BaseModel):
    """A single FAQ result returned by retrieval.

    `score` semantics depend on which retrieval method produced this:
      - search()        -> Qdrant cosine similarity in [0, 1] (typically 0.5–0.85)
      - search_hybrid() -> Reciprocal Rank Fusion combined score (small, < 0.05;
                           rank-meaningful but NOT directly comparable to cosine)

    Compare scores within a single retrieval call, not across methods.
    The type is unconstrained so unusual values surface clearly rather
    than failing validation.
    """

    id: str
    category: str
    language: str
    question: str
    answer: str
    tags: list[str]
    score: float


class RetrievalResult(BaseModel):
    """Response from a retrieval query.

    `total_found` is the count of candidates fetched from Qdrant BEFORE
    the score-threshold filter — i.e. the raw signal of how many vectors
    matched the embedding/filter query. `results` is the post-threshold
    top-k.
    """

    query: str
    results: list[RetrievedFaq]
    total_found: int
    filters_applied: RetrievalFilter | None = None
