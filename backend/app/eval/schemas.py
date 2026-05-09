"""Pydantic schemas for the Phase H evaluation pipeline.

`EvalCase` mirrors the structure produced by Phase A.3
(`backend/data/eval_cases.json`): a flat top-level case with a nested
`expected_behavior` block. The case fields here are descriptive (used by
the judge prompt) rather than enforceable — `should_use_tools` is just a
hint for scoring, not a hard match.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExpectedBehavior(BaseModel):
    """Reference behavior the judge scores against."""

    intent_match: str | None = None
    should_escalate: bool = False
    should_mention: list[str] = Field(default_factory=list)
    should_not_mention: list[str] = Field(default_factory=list)
    should_use_tools: list[str] = Field(default_factory=list)
    tone: str = "informational"


class EvalCase(BaseModel):
    """One case from `data/eval_cases.json`."""

    model_config = ConfigDict(extra="ignore")

    id: str
    scenario: str
    difficulty: Literal["easy", "medium", "hard"]
    intent: str
    language: Literal["en", "id"]
    user_query: str
    context: dict = Field(default_factory=dict)
    expected_behavior: ExpectedBehavior
    tags: list[str] = Field(default_factory=list)


class AgentRunResult(BaseModel):
    """Output from running the agent on a single case."""

    case_id: str
    reply: str
    tools_called: list[str]
    duration_ms: int
    error: str | None = None


class JudgeScore(BaseModel):
    """Score for one rubric dimension."""

    score: int = Field(..., ge=0, le=100)
    reasoning: str


class CaseEvaluation(BaseModel):
    """Full per-case evaluation: case + agent run + judge scores."""

    case_id: str
    case: EvalCase
    agent_result: AgentRunResult
    scores: dict[str, JudgeScore]
    overall_score: float
    passed: bool
    judge_summary: str


class EvalRunSummary(BaseModel):
    """Aggregate stats for a full eval run."""

    total_cases: int
    passed_cases: int
    failed_cases: int
    error_cases: int
    overall_pass_rate: float
    avg_scores: dict[str, float]
    per_difficulty: dict[str, dict]
    per_language: dict[str, dict]
    per_intent: dict[str, dict]
    cost_estimate_usd: float
    duration_seconds: int
    run_timestamp: str
