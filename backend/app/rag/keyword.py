"""BM25 keyword search over the FAQ corpus.

Loads FAQs from data/faq_seed.json once on first use and builds an
in-memory BM25Okapi index. Sequential int IDs match the Qdrant point
IDs used by scripts/embed_faqs.py — both indices are aligned by
construction (same JSON file, same order).

Multilingual note: BM25 is purely lexical. Vector search (in retriever.py)
handles cross-language semantic matching; keyword catches exact terms,
acronyms, codes. Combined via RRF in hybrid.py for the best of both.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import structlog
from rank_bm25 import BM25Okapi

from app.rag.schemas import RetrievalFilter


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FAQ_PATH = PROJECT_ROOT / "data" / "faq_seed.json"

log = structlog.get_logger(__name__)


def _tokenize(text: str) -> list[str]:
    """Word-boundary tokenizer with lowercasing. Multilingual-safe."""
    return re.findall(r"\w+", text.lower())


class KeywordSearcher:
    """BM25Okapi over the Javva FAQ corpus.

    The corpus is `f"{question} {answer}"` for each FAQ; tokens are
    word-boundary lowercased. Matches Qdrant point IDs by index position.
    """

    def __init__(self, faq_path: Path = FAQ_PATH) -> None:
        if not faq_path.exists():
            raise RuntimeError(
                f"KeywordSearcher: FAQ source not found at {faq_path} — "
                "run scripts/generate_faq.py first."
            )
        faqs = json.loads(faq_path.read_text(encoding="utf-8"))
        self._payloads: list[dict] = list(faqs)
        self._corpus_tokens: list[list[str]] = [
            _tokenize(f"{e['question']} {e['answer']}") for e in faqs
        ]
        self._bm25 = BM25Okapi(self._corpus_tokens)
        log.info("keyword_searcher_init", n_docs=len(self._payloads))

    def search(
        self,
        query: str,
        k: int = 10,
        filters: RetrievalFilter | None = None,
    ) -> list[tuple[int, float]]:
        """Return list of (faq_index, bm25_score) sorted by score desc.

        Args:
            query: User's query.
            k: Maximum results to return.
            filters: Optional category / language / tag constraints.
                Applied in Python after scoring (BM25 has no native
                metadata-filter API).

        Returns:
            list of (int_id, score). Documents with score == 0 are dropped.
        """
        if not query or not query.strip():
            return []

        scores = self._bm25.get_scores(_tokenize(query))
        candidates: list[tuple[int, float]] = []
        for i, score in enumerate(scores):
            if score <= 0:
                continue
            if filters and not self._matches(self._payloads[i], filters):
                continue
            candidates.append((i, float(score)))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:k]

    def get_payload(self, idx: int) -> dict:
        """Return the FAQ payload for a given int index."""
        return self._payloads[idx]

    @staticmethod
    def _matches(payload: dict, f: RetrievalFilter) -> bool:
        if f.category and payload.get("category") != f.category:
            return False
        if f.language and payload.get("language") != f.language:
            return False
        if f.tags:
            faq_tags = set(payload.get("tags", []))
            if not faq_tags.intersection(f.tags):
                return False
        return True


_keyword_instance: KeywordSearcher | None = None


def get_keyword_searcher() -> KeywordSearcher:
    """Return the module-level singleton KeywordSearcher (lazy-init)."""
    global _keyword_instance
    if _keyword_instance is None:
        _keyword_instance = KeywordSearcher()
    return _keyword_instance
