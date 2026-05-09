"""Generate the human-readable eval report (REPORT.md + matplotlib charts).

Charts use the Agg backend so this works in headless WSL without an X
display. Style is dark-background to match the Javva UI palette.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from app.eval.schemas import CaseEvaluation, EvalRunSummary  # noqa: E402


JAVVA_GREEN = "#00D582"
JAVVA_RED = "#EF4444"
JAVVA_AMBER = "#FFA500"


def generate_charts(
    summary: EvalRunSummary, output_dir: Path
) -> None:
    """Write three PNG charts: per-dimension, pass/fail pie, per-difficulty."""
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.style.use("dark_background")

    # 1. Per-dimension scores
    fig, ax = plt.subplots(figsize=(10, 6))
    dims = list(summary.avg_scores.keys())
    scores = [summary.avg_scores[d] for d in dims]
    bars = ax.bar(dims, scores, color=JAVVA_GREEN, alpha=0.85)
    ax.set_ylabel("Average Score (%)")
    ax.set_title("Agent Performance by Dimension")
    ax.set_ylim(0, 100)
    ax.axhline(
        y=70,
        color=JAVVA_RED,
        linestyle="--",
        alpha=0.5,
        label="Pass threshold (70%)",
    )
    ax.legend()
    for bar, score in zip(bars, scores):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1,
            f"{score:.1f}",
            ha="center",
            fontweight="bold",
        )
    plt.tight_layout()
    plt.savefig(
        output_dir / "scores_by_dimension.png", dpi=150, bbox_inches="tight"
    )
    plt.close()

    # 2. Pass/fail pie
    labels = ["Passed", "Failed", "Errored"]
    sizes = [
        summary.passed_cases,
        summary.failed_cases,
        summary.error_cases,
    ]
    colors = [JAVVA_GREEN, JAVVA_AMBER, JAVVA_RED]
    keep = [(l, s, c) for l, s, c in zip(labels, sizes, colors) if s > 0]
    if keep:
        labels_f, sizes_f, colors_f = zip(*keep)
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.pie(
            sizes_f,
            labels=labels_f,
            colors=colors_f,
            autopct="%1.1f%%",
            startangle=90,
        )
        ax.set_title(f"Overall Pass Rate ({summary.total_cases} cases)")
        plt.tight_layout()
        plt.savefig(
            output_dir / "pass_fail_pie.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.close()

    # 3. Per-difficulty
    if summary.per_difficulty:
        # Sort difficulties in logical order if present.
        order = ["easy", "medium", "hard"]
        difficulties = [
            d for d in order if d in summary.per_difficulty
        ] + [d for d in summary.per_difficulty if d not in order]
        avgs = [summary.per_difficulty[d]["avg"] for d in difficulties]
        counts = [summary.per_difficulty[d]["count"] for d in difficulties]
        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(difficulties, avgs, color=JAVVA_GREEN, alpha=0.85)
        ax.set_ylabel("Average Score (%)")
        ax.set_title("Performance by Difficulty")
        ax.set_ylim(0, 100)
        ax.axhline(y=70, color=JAVVA_RED, linestyle="--", alpha=0.5)
        for bar, avg, count in zip(bars, avgs, counts):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1,
                f"{avg:.1f}\n(n={count})",
                ha="center",
                fontweight="bold",
            )
        plt.tight_layout()
        plt.savefig(
            output_dir / "by_difficulty.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.close()


def generate_report(
    eval_output: dict, output_path: Path | None = None
) -> Path:
    """Write `REPORT.md` and the chart PNGs alongside it."""
    summary: EvalRunSummary = eval_output["summary"]
    evaluations: list[CaseEvaluation] = eval_output["evaluations"]

    if output_path is None:
        output_path = (
            Path(__file__).parent / "results" / "REPORT.md"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    charts_dir = output_path.parent / "charts"
    generate_charts(summary, charts_dir)

    failures = [
        e for e in evaluations if not e.passed and not e.agent_result.error
    ]
    failures_sorted = sorted(failures, key=lambda e: e.overall_score)
    failure_examples = failures_sorted[:5]

    report = f"""# Javva Evaluation Report

Generated: {summary.run_timestamp}
Total cases: {summary.total_cases}
Duration: {summary.duration_seconds // 60}m {summary.duration_seconds % 60}s
Estimated cost: ~${summary.cost_estimate_usd:.3f} USD

## Summary

- **Pass rate**: {summary.overall_pass_rate * 100:.1f}% ({summary.passed_cases}/{summary.total_cases})
- **Errors**: {summary.error_cases}
- **Failed cases**: {summary.failed_cases}

## Average Scores by Dimension

| Dimension | Score |
|-----------|-------|
| Accuracy | {summary.avg_scores['accuracy']:.1f}% |
| Tone | {summary.avg_scores['tone']:.1f}% |
| Tool Selection | {summary.avg_scores['tool_selection']:.1f}% |
| Language | {summary.avg_scores['language']:.1f}% |

![Scores by Dimension](charts/scores_by_dimension.png)

## Pass/Fail Distribution

![Pass/Fail Pie](charts/pass_fail_pie.png)

## Performance by Difficulty

"""
    for diff in ["easy", "medium", "hard"]:
        if diff in summary.per_difficulty:
            stats = summary.per_difficulty[diff]
            report += (
                f"- **{diff.upper()}**: {stats['avg']:.1f}% avg "
                f"({stats['count']} cases)\n"
            )

    report += """
![By Difficulty](charts/by_difficulty.png)

## Performance by Language

"""
    for lang, stats in sorted(summary.per_language.items()):
        report += (
            f"- **{lang.upper()}**: {stats['avg']:.1f}% avg "
            f"({stats['count']} cases)\n"
        )

    report += """
## Performance by Intent

"""
    for intent, stats in sorted(
        summary.per_intent.items(), key=lambda x: -x[1]["avg"]
    ):
        report += (
            f"- **{intent}**: {stats['avg']:.1f}% avg "
            f"({stats['count']} cases)\n"
        )

    if failure_examples:
        report += "\n## Failure Examples (lowest 5)\n\n"
        for i, fe in enumerate(failure_examples, 1):
            reply = fe.agent_result.reply
            reply_excerpt = reply[:300] + ("…" if len(reply) > 300 else "")
            acc_reason = fe.scores["accuracy"].reasoning[:160]
            report += f"""### {i}. Case `{fe.case_id}` — Score: {fe.overall_score:.1f}%

**User**: {fe.case.user_query}
**Expected tools**: {fe.case.expected_behavior.should_use_tools}
**Agent tools called**: {fe.agent_result.tools_called}
**Agent reply**: {reply_excerpt}

**Judge breakdown**:
- Accuracy: {fe.scores['accuracy'].score} ({acc_reason})
- Tone: {fe.scores['tone'].score}
- Tool Selection: {fe.scores['tool_selection'].score}
- Language: {fe.scores['language'].score}

**Judge summary**: {fe.judge_summary[:200]}

---

"""

    report += """
## Methodology

- **Agent**: gemini-2.5-flash-lite via Vertex AI
- **Judge**: gemini-2.5-pro via Vertex AI (different tier to reduce same-provider bias)
- **Eval set**: 100 cases from `data/eval_cases.json` (Phase A.3)
- **Concurrency**: 3 parallel cases (Vertex rate-limit safe)
- **Pass threshold**: overall score ≥ 70%
- **Scoring**: 4 dimensions (accuracy, tone, tool_selection, language), 0-100 each

## Caveats

- Same-provider risk: agent and judge both come from the Gemini family. The
  tier gap (Pro vs Flash-Lite) reduces but does not eliminate this; an
  external judge (e.g. GPT-4o) is recommended before any production claim.
- Cost figure is an order-of-magnitude estimate, not actual billing.

---

*Generated by Javva Phase H eval pipeline.*
"""

    output_path.write_text(report)
    return output_path
