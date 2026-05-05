"""Manual CLI test for the FAQ retriever — 7 scenarios.

Exercises basic search, category/language/tag filters, high score
threshold, and an edge-case garbage query. For each scenario prints
the request and the top-3 results.

Usage:
    uv run python scripts/test_retriever.py
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table

from app.rag import RetrievalFilter, search_faqs


console = Console()


SCENARIOS: list[tuple[str, str, dict[str, Any]]] = [
    ("1. Basic EN, no filter", "How do I withdraw money?", {}),
    ("2. Basic ID, no filter", "Apa itu KYC?", {}),
    ("3. Category filter (forex_basics)", "What is leverage?",
        {"filters": RetrievalFilter(category="forex_basics")}),
    ("4. Language filter (id)", "trading basics",
        {"filters": RetrievalFilter(language="id")}),
    ("5. Tag filter (leverage / kyc)", "explain it",
        {"filters": RetrievalFilter(tags=["leverage", "kyc"])}),
    ("6. High threshold (0.7)", "How do I withdraw money?",
        {"score_threshold": 0.7}),
    ("7. Edge case — garbage query", "asdfghjkl random gibberish nonsense", {}),
]


def render(label: str, query: str, opts: dict[str, Any]) -> None:
    console.rule(f"[bold]{label}")
    filters = opts.get("filters")
    threshold = opts.get("score_threshold", 0.5)
    filters_repr = filters.model_dump(exclude_none=True) if filters else None
    console.print(f"[bold]Query:[/bold] {query}")
    console.print(f"[dim]filters: {filters_repr}   threshold: {threshold}[/dim]")

    result = search_faqs(query, k=3, **opts)
    console.print(
        f"[dim]total_found: {result.total_found}   "
        f"returned: {len(result.results)}[/dim]\n"
    )

    if not result.results:
        console.print("[yellow]No results above threshold.[/yellow]\n")
        return

    t = Table(show_lines=False)
    t.add_column("rank", style="cyan", no_wrap=True)
    t.add_column("score", style="green", no_wrap=True)
    t.add_column("lang", style="magenta", no_wrap=True)
    t.add_column("id", style="dim", no_wrap=True)
    t.add_column("question", overflow="fold")
    for i, r in enumerate(result.results, 1):
        t.add_row(str(i), f"{r.score:.4f}", r.language, r.id, r.question)
    console.print(t)
    console.print()


def main() -> int:
    for label, query, opts in SCENARIOS:
        render(label, query, opts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
