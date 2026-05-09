"""CLI entry point for the Javva eval pipeline.

Usage:
    uv run python scripts/run_eval.py [--limit N] [--concurrency N]

Examples:
    uv run python scripts/run_eval.py --limit 5    # quick smoke test
    uv run python scripts/run_eval.py              # full 100 cases
"""

from __future__ import annotations

import argparse
import asyncio

from app.eval.reporter import generate_report
from app.eval.runner import run_eval, save_results


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max cases to run (None = all)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Parallel cases (Vertex rate-limit safe)",
    )
    args = parser.parse_args()

    print(
        f"Running eval (limit={args.limit or 'all'}, "
        f"concurrency={args.concurrency})"
    )
    print("=" * 70)

    eval_output = await run_eval(
        limit=args.limit, concurrency=args.concurrency
    )

    print("\n" + "=" * 70)
    print("Saving results…")
    results_path = save_results(eval_output)

    print("Generating report…")
    report_path = generate_report(eval_output)

    summary = eval_output["summary"]
    print("\nEval complete.")
    print(f"  Pass rate:     {summary.overall_pass_rate * 100:.1f}%")
    print(f"  Avg accuracy:  {summary.avg_scores['accuracy']:.1f}%")
    print(f"  Avg tone:      {summary.avg_scores['tone']:.1f}%")
    print(f"  Avg tools:     {summary.avg_scores['tool_selection']:.1f}%")
    print(f"  Avg language:  {summary.avg_scores['language']:.1f}%")
    print(f"  Errors:        {summary.error_cases}")
    print(f"  Duration:      {summary.duration_seconds}s")
    print(f"  Results:       {results_path}")
    print(f"  Report:        {report_path}")
    print(f"  Charts:        {report_path.parent / 'charts'}")


if __name__ == "__main__":
    asyncio.run(main())
