"""Verify Qdrant collection 'javva_kb' state and retrieval quality.

Shows collection stats, samples 5 vectors with their metadata, and runs 4
test queries (2 EN + 2 ID) to confirm cross-language semantic retrieval is
working — an EN query should be able to retrieve relevant ID FAQs and
vice versa.

Usage:
    uv run python scripts/verify_qdrant.py
"""

from __future__ import annotations

import sys

from google import genai
from google.genai import types
from qdrant_client import QdrantClient
from rich.console import Console

from app.config import settings
from app.llm_client import get_genai_client


COLLECTION_NAME = "javva_kb"
EMBEDDING_MODEL = "gemini-embedding-001"
VECTOR_DIM = 768

console = Console()

TEST_QUERIES: list[tuple[str, str]] = [
    ("en", "How do I withdraw money?"),
    ("id", "Bagaimana cara menarik dana?"),
    ("en", "What is leverage?"),
    ("id", "Apa itu KYC?"),
]


def embed_query(gemini: genai.Client, text: str) -> list[float]:
    response = gemini.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=[text],
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=VECTOR_DIM,
        ),
    )
    return response.embeddings[0].values


def main() -> int:
    missing = []
    if not settings.gemini_api_key:
        missing.append("GEMINI_API_KEY")
    if not settings.qdrant_url:
        missing.append("QDRANT_URL")
    if not settings.qdrant_api_key:
        missing.append("QDRANT_API_KEY")
    if missing:
        console.print(f"[red]ERROR: missing settings: {', '.join(missing)}[/red]")
        return 1

    qdrant = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    gemini = get_genai_client()

    console.rule("[bold]verify_qdrant")

    if not qdrant.collection_exists(COLLECTION_NAME):
        console.print(f"[red]Collection '{COLLECTION_NAME}' does not exist — run embed_faqs.py first.[/red]")
        return 1

    info = qdrant.get_collection(COLLECTION_NAME)
    console.print("\n[bold]Collection info[/bold]")
    console.print(f"  Name:      [cyan]{COLLECTION_NAME}[/cyan]")
    console.print(f"  Vectors:   [cyan]{info.points_count}[/cyan]")
    console.print(f"  Dimension: [cyan]{info.config.params.vectors.size}[/cyan]")
    console.print(f"  Distance:  [cyan]{info.config.params.vectors.distance}[/cyan]")
    console.print(f"  Status:    [cyan]{info.status}[/cyan]")

    console.print("\n[bold]5 sample vectors[/bold]")
    sample_points, _ = qdrant.scroll(
        collection_name=COLLECTION_NAME,
        limit=5,
        with_payload=True,
        with_vectors=False,
    )
    for pt in sample_points:
        p = pt.payload
        console.print(
            f"  [cyan]point id={pt.id}[/cyan] "
            f"[dim]({p['language']} | {p['category']} | {p['id']})[/dim]"
        )
        console.print(f"    Q: {p['question'][:100]}")

    console.print("\n[bold]Test queries — top 3 each[/bold]")
    cross_language_hits = 0
    total_hits = 0

    for query_lang, query_text in TEST_QUERIES:
        console.print(f"\n[bold magenta]Query ({query_lang})[/bold magenta]: \"{query_text}\"")
        query_vec = embed_query(gemini, query_text)
        results = qdrant.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vec,
            limit=3,
            with_payload=True,
        ).points

        for rank, hit in enumerate(results, 1):
            p = hit.payload
            total_hits += 1
            cross_marker = ""
            if p["language"] != query_lang:
                cross_marker = "  [yellow]← cross-language[/yellow]"
                cross_language_hits += 1
            console.print(
                f"  [cyan]#{rank}[/cyan] score={hit.score:.4f}  "
                f"[dim]{p['language']} {p['id']}[/dim]{cross_marker}"
            )
            console.print(f"      {p['question']}")

    console.rule("[bold green]done")
    if total_hits == 0:
        console.print("[yellow]No hits — collection appears empty.[/yellow]")
    else:
        console.print(
            f"Cross-language matches: [bold]{cross_language_hits}[/bold] of {total_hits} hits "
            f"({cross_language_hits / total_hits:.0%})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
