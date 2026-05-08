"""Embed FAQ seed dataset into Qdrant collection 'javva_kb'.

Uses Gemini text-embedding-004 (768-dim) with task_type=RETRIEVAL_DOCUMENT
for asymmetric embedding quality. Queries should embed with task_type=
RETRIEVAL_QUERY (see verify_qdrant.py).

Sequential int point IDs (0..N-1) — running this script twice without
--reset upserts in place (idempotent).

Usage:
    # Dry-run: show plan and exit without API calls
    uv run python scripts/embed_faqs.py --dry-run

    # Normal: embed + index 204 FAQs (creates collection if needed)
    uv run python scripts/embed_faqs.py

    # Reset: delete and recreate collection before indexing
    uv run python scripts/embed_faqs.py --reset

    # Override default batch size
    uv run python scripts/embed_faqs.py --batch-size 50
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types
from qdrant_client import QdrantClient, models
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.llm_client import get_genai_client


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FAQ_PATH = PROJECT_ROOT / "data" / "faq_seed.json"

COLLECTION_NAME = "javva_kb"
EMBEDDING_MODEL = "gemini-embedding-001"
VECTOR_DIM = 768

# Qdrant Cloud requires explicit payload-field indexes before you can
# filter on those fields. Without these, retriever.py's category/language/tag
# filters return 400 Bad Request.
PAYLOAD_INDEXES: list[tuple[str, models.PayloadSchemaType]] = [
    ("category", models.PayloadSchemaType.KEYWORD),
    ("language", models.PayloadSchemaType.KEYWORD),
    ("tags",     models.PayloadSchemaType.KEYWORD),
]

console = Console()


def build_text(entry: dict) -> str:
    return f"Q: {entry['question']}\nA: {entry['answer']}"


def build_payload(entry: dict) -> dict:
    return {
        "id":       entry["id"],
        "category": entry["category"],
        "language": entry["language"],
        "tags":     entry["tags"],
        "question": entry["question"],
        "answer":   entry["answer"],
    }


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=10, max=60),
    retry=retry_if_not_exception_type((KeyboardInterrupt, SystemExit)),
    reraise=True,
)
def embed_batch(client: genai.Client, texts: list[str]) -> list:
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=VECTOR_DIM,
        ),
    )
    return response.embeddings


def host_only(url: str) -> str:
    return url.split("://")[-1].split("/")[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Embed FAQ seed dataset into Qdrant.")
    parser.add_argument(
        "--reset", action="store_true",
        help="Delete and recreate the collection before indexing.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show plan; make no API calls.",
    )
    parser.add_argument(
        "--batch-size", type=int, default=100,
        help="Texts per embedding API call (default 100, max 100).",
    )
    args = parser.parse_args()

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

    if not FAQ_PATH.exists():
        console.print(f"[red]ERROR: {FAQ_PATH} not found — run generate_faq.py first[/red]")
        return 1

    faqs = json.loads(FAQ_PATH.read_text(encoding="utf-8"))
    total = len(faqs)
    n_batches = (total + args.batch_size - 1) // args.batch_size

    console.rule("[bold]embed_faqs")
    console.print(f"FAQ source:   [cyan]{FAQ_PATH}[/cyan]   ({total} entries)")
    console.print(f"Collection:   [cyan]{COLLECTION_NAME}[/cyan] @ [dim]{host_only(settings.qdrant_url)}[/dim]")
    console.print(f"Model:        [cyan]{EMBEDDING_MODEL}[/cyan] (dim {VECTOR_DIM}, cosine)")
    console.print(f"Batches:      [cyan]{n_batches}[/cyan] of {args.batch_size}")
    console.print(f"Mode:         [cyan]{'reset' if args.reset else 'create-or-append'}[/cyan]")

    if args.dry_run:
        console.print("\n[yellow]Dry-run — no API calls.[/yellow]\n")
        sample = faqs[0]
        console.print("[bold]Sample text (first entry):[/bold]")
        console.print(f"  [dim]{build_text(sample)[:240]}...[/dim]")
        console.print("\n[bold]Sample payload (first entry):[/bold]")
        console.print(f"  [dim]{json.dumps(build_payload(sample), ensure_ascii=False, indent=2)}[/dim]")
        return 0

    gemini = get_genai_client()
    qdrant = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)

    console.print("\n[blue]Probing embedding dimension...[/blue]")
    probe = embed_batch(gemini, [build_text(faqs[0])])
    got_dim = len(probe[0].values)
    if got_dim != VECTOR_DIM:
        console.print(f"[red]Dim mismatch: got {got_dim}, expected {VECTOR_DIM}[/red]")
        return 1
    console.print(f"[green]Probe OK — dim {got_dim}[/green]")

    if args.reset and qdrant.collection_exists(COLLECTION_NAME):
        qdrant.delete_collection(COLLECTION_NAME)
        console.print(f"[yellow]Deleted existing {COLLECTION_NAME}[/yellow]")

    if not qdrant.collection_exists(COLLECTION_NAME):
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=VECTOR_DIM,
                distance=models.Distance.COSINE,
            ),
        )
        console.print(f"[green]Created {COLLECTION_NAME} ({VECTOR_DIM}d, cosine)[/green]")
    else:
        info = qdrant.get_collection(COLLECTION_NAME)
        existing_dim = info.config.params.vectors.size
        if existing_dim != VECTOR_DIM:
            console.print(
                f"[red]Dim mismatch in existing collection: "
                f"{existing_dim} vs expected {VECTOR_DIM}[/red]"
            )
            return 1
        console.print(f"[dim]Appending into existing {COLLECTION_NAME}[/dim]")

    # Ensure payload indexes exist on filterable fields (idempotent).
    for field, schema in PAYLOAD_INDEXES:
        qdrant.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name=field,
            field_schema=schema,
        )
    console.print(f"[dim]Payload indexes ensured on: {', '.join(f for f, _ in PAYLOAD_INDEXES)}[/dim]")

    start_time = time.time()
    api_calls = 1  # the probe
    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )

    with progress:
        task = progress.add_task("embed+upsert", total=total)
        for batch_idx in range(n_batches):
            offset = batch_idx * args.batch_size
            batch = faqs[offset:offset + args.batch_size]
            texts = [build_text(e) for e in batch]

            embeddings = embed_batch(gemini, texts)
            api_calls += 1

            points = [
                models.PointStruct(
                    id=offset + i,
                    vector=embeddings[i].values,
                    payload=build_payload(batch[i]),
                )
                for i in range(len(batch))
            ]
            qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
            progress.update(task, advance=len(batch))

    elapsed = time.time() - start_time
    info = qdrant.get_collection(COLLECTION_NAME)

    console.rule("[bold green]done")
    console.print(f"Vectors in collection: [bold]{info.points_count}[/bold]")
    console.print(f"API calls:             [cyan]{api_calls}[/cyan] (1 probe + {n_batches} batches)")
    console.print(f"Elapsed:               [cyan]{elapsed:.2f}s[/cyan]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
