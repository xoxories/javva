"""Query embedding for FAQ retrieval.

Uses gemini-embedding-001 with task_type=RETRIEVAL_QUERY. This pairs with
the documents indexed by scripts/embed_faqs.py which use task_type=
RETRIEVAL_DOCUMENT — the asymmetric setup measurably improves retrieval
recall vs using the same task type on both sides.

The Gemini client is cached at module level (one client per process).
"""

from __future__ import annotations

from google import genai
from google.genai import types
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings


EMBEDDING_MODEL = "gemini-embedding-001"
VECTOR_DIM = 768

_client: genai.Client | None = None


def get_gemini_client() -> genai.Client:
    """Return a cached genai.Client (lazy-initialized on first call)."""
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set in .env")
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=10, max=60),
    retry=retry_if_not_exception_type((KeyboardInterrupt, SystemExit, ValueError)),
    reraise=True,
)
def embed_query(text: str) -> list[float]:
    """Embed a query string for retrieval. Returns a 768-dim vector.

    Args:
        text: The user's query (any language).

    Returns:
        list[float] of length 768.

    Raises:
        ValueError: if `text` is empty or whitespace-only. Not retried.
        google.genai.errors.ClientError: from the Gemini API after retries
            exhaust (rate limits, quota, etc).
    """
    if not text or not text.strip():
        raise ValueError("embed_query: text must be non-empty")

    client = get_gemini_client()
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=[text],
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=VECTOR_DIM,
        ),
    )
    return response.embeddings[0].values
