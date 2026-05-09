"""Eval pipeline orchestrator.

Loads cases from `data/eval_cases.json`, runs the agent for each, hands
the result to the Gemini-Pro judge, and aggregates per-case evaluations
into a run summary.

Concurrency: a single asyncio.Semaphore caps in-flight cases. Each case
makes 2 LLM calls (agent + judge), so concurrency=3 means up to 6 LLM
calls in flight — well under Vertex AI's per-minute quotas for Tier 1.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import structlog

from app.agent import chat
from app.eval.judge import judge_response
from app.eval.schemas import (
    AgentRunResult,
    CaseEvaluation,
    EvalCase,
    EvalRunSummary,
)


log = structlog.get_logger(__name__)


EVAL_CASES_PATH = (
    Path(__file__).parent.parent.parent / "data" / "eval_cases.json"
)
RESULTS_DIR = Path(__file__).parent / "results"


def load_cases(path: Path = EVAL_CASES_PATH) -> list[EvalCase]:
    """Load eval cases from JSON."""
    with open(path) as f:
        data = json.load(f)
    return [EvalCase(**case) for case in data]


async def run_single_case(
    case: EvalCase, semaphore: asyncio.Semaphore
) -> CaseEvaluation:
    """Run agent on case, then judge response."""
    async with semaphore:
        start = time.time()

        try:
            result = await chat(
                user_message=case.user_query,
                message_history=None,
                session_id=f"eval-{case.id}",
            )
            agent_result = AgentRunResult(
                case_id=case.id,
                reply=result.reply,
                tools_called=result.tools_called,
                duration_ms=result.duration_ms,
                error=result.error,
            )
        except Exception as e:
            log.error("agent_run_failed", case_id=case.id, error=str(e))
            agent_result = AgentRunResult(
                case_id=case.id,
                reply=f"AGENT ERROR: {e}",
                tools_called=[],
                duration_ms=int((time.time() - start) * 1000),
                error=str(e),
            )

        judge_output = await judge_response(case, agent_result)

        scores = judge_output["scores"]
        overall = sum(s.score for s in scores.values()) / len(scores)

        return CaseEvaluation(
            case_id=case.id,
            case=case,
            agent_result=agent_result,
            scores=scores,
            overall_score=overall,
            passed=overall >= 70,
            judge_summary=judge_output["summary"],
        )


async def run_eval(
    limit: int | None = None, concurrency: int = 3
) -> dict:
    """Run the full evaluation pipeline.

    Args:
        limit: Max cases to run. None = all.
        concurrency: Max in-flight cases at any time.

    Returns:
        ``{"evaluations": [CaseEvaluation], "summary": EvalRunSummary}``
    """
    cases = load_cases()
    if limit:
        cases = cases[:limit]

    log.info(
        "eval_started", total_cases=len(cases), concurrency=concurrency
    )

    start_time = time.time()
    semaphore = asyncio.Semaphore(concurrency)

    # Sequential progress printing for human-readable CLI output. The
    # semaphore enforces concurrency inside `run_single_case`.
    results: list[CaseEvaluation] = []
    tasks = [run_single_case(case, semaphore) for case in cases]
    completed = 0
    for coro in asyncio.as_completed(tasks):
        result = await coro
        completed += 1
        status = "PASS" if result.passed else "FAIL"
        if result.agent_result.error:
            status = "ERR "
        print(
            f"  [{completed}/{len(cases)}] {result.case_id} "
            f"({result.case.language}/{result.case.difficulty}) "
            f"{status} {result.overall_score:.1f}",
            flush=True,
        )
        results.append(result)

    # Stable order for reporting: by case id.
    results.sort(key=lambda r: r.case_id)

    duration = time.time() - start_time

    passed = [r for r in results if r.passed]
    errors = [r for r in results if r.agent_result.error]
    failed = [
        r for r in results if not r.passed and not r.agent_result.error
    ]

    avg_scores = {
        dim: sum(r.scores[dim].score for r in results) / len(results)
        for dim in ["accuracy", "tone", "tool_selection", "language"]
    }

    per_difficulty: dict[str, list[float]] = {}
    per_language: dict[str, list[float]] = {}
    per_intent: dict[str, list[float]] = {}

    for r in results:
        per_difficulty.setdefault(r.case.difficulty, []).append(
            r.overall_score
        )
        per_language.setdefault(r.case.language, []).append(r.overall_score)
        per_intent.setdefault(r.case.intent, []).append(r.overall_score)

    def aggregate(buckets: dict[str, list[float]]) -> dict[str, dict]:
        return {
            k: {"count": len(v), "avg": sum(v) / len(v)}
            for k, v in buckets.items()
        }

    summary = EvalRunSummary(
        total_cases=len(results),
        passed_cases=len(passed),
        failed_cases=len(failed),
        error_cases=len(errors),
        overall_pass_rate=len(passed) / len(results) if results else 0.0,
        avg_scores=avg_scores,
        per_difficulty=aggregate(per_difficulty),
        per_language=aggregate(per_language),
        per_intent=aggregate(per_intent),
        # 2 LLM calls/case * ~$0.0003 each — order of magnitude only.
        cost_estimate_usd=len(results) * 2 * 0.0003,
        duration_seconds=int(duration),
        run_timestamp=datetime.now(timezone.utc).isoformat(),
    )

    return {"evaluations": results, "summary": summary}


def save_results(
    eval_output: dict, output_path: Path | None = None
) -> Path:
    """Persist evaluations + summary as ``results.json``."""
    if output_path is None:
        output_path = RESULTS_DIR / "results.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "summary": eval_output["summary"].model_dump(),
        "evaluations": [e.model_dump() for e in eval_output["evaluations"]],
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, default=str)

    log.info("eval_results_saved", path=str(output_path))
    return output_path
