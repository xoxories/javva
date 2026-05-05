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

from app.rag import RetrievalFilter, search_faqs, search_faqs_hybrid


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


COMPARISON_SCENARIOS: list[tuple[str, str]] = [
    ("8. Exact term: 'MT5 setup'", "MT5 setup"),
    ("9. Acronym + term: 'EUR/USD pip'", "EUR/USD pip"),
    ("10. Acronym: 'KYC documents'", "KYC documents"),
    ("11. Conceptual: 'How does leverage work?'", "How does leverage work?"),
]


def render_comparison(label: str, query: str) -> None:
    console.rule(f"[bold]{label}")
    console.print(f"[bold]Query:[/bold] {query}\n")

    vec = search_faqs(query, k=5)
    hyb = search_faqs_hybrid(query, k=5)

    t = Table(title="vector (left) vs hybrid (right) — top 5")
    t.add_column("rank", style="cyan", no_wrap=True)
    t.add_column("vector id", style="green", no_wrap=True)
    t.add_column("v score", style="dim", no_wrap=True)
    t.add_column("hybrid id", style="magenta", no_wrap=True)
    t.add_column("h score", style="dim", no_wrap=True)

    n = max(len(vec.results), len(hyb.results))
    for i in range(n):
        v_id = vec.results[i].id if i < len(vec.results) else "-"
        v_score = f"{vec.results[i].score:.4f}" if i < len(vec.results) else "-"
        h_id = hyb.results[i].id if i < len(hyb.results) else "-"
        h_score = f"{hyb.results[i].score:.4f}" if i < len(hyb.results) else "-"
        t.add_row(str(i + 1), v_id, v_score, h_id, h_score)
    console.print(t)

    vec_ids = [r.id for r in vec.results]
    hyb_ids = [r.id for r in hyb.results]
    overlap = set(vec_ids) & set(hyb_ids)
    console.print(
        f"[dim]overlap: {len(overlap)}/{n}   "
        f"vector-only: {sorted(set(vec_ids) - set(hyb_ids))}   "
        f"hybrid-only: {sorted(set(hyb_ids) - set(vec_ids))}[/dim]\n"
    )


def main() -> int:
    for label, query, opts in SCENARIOS:
        render(label, query, opts)

    console.print()
    console.rule("[bold]Hybrid vs Vector Comparison (scenarios 8-11)")
    console.print()
    for label, query in COMPARISON_SCENARIOS:
        render_comparison(label, query)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
