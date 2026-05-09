"""Gemini-2.5-Pro judge for the eval pipeline.

Uses the centralized `genai.Client` (Vertex AI) directly rather than going
through pydantic-ai — a single structured-JSON call with no tools is
faster and easier to make reproducible. We pin temperature low (0.1) so
re-runs of the same case produce nearly-identical scores.

Model choice: gemini-2.5-pro. Same provider as the agent (gemini-2.5-
flash-lite) but a different tier — Pro is significantly more capable, so
it can grade Lite without rubber-stamping its own family's output. This
risk is documented in `REPORT.md`; an external GPT-4o judge would
strengthen the methodology before any production claim.
"""

from __future__ import annotations

import json
import re

import structlog
from google.genai import types as genai_types

from app.eval.schemas import AgentRunResult, EvalCase, JudgeScore
from app.llm_client import get_genai_client


log = structlog.get_logger(__name__)


JUDGE_MODEL = "gemini-2.5-pro"


JUDGE_SYSTEM_PROMPT = """You are an expert AI quality evaluator for Javva, a forex/CFD trading platform's customer support agent.

Your task: Score the agent's response across 4 dimensions, each 0-100:

1. ACCURACY (0-100): Did the agent answer the user's question correctly and completely? Compare against `should_mention` keywords and reference behavior. Penalize if `should_not_mention` topics appear. Score 0 if wrong, 50 if partially correct, 100 if complete and accurate.

2. TONE (0-100): Does the response tone match expected? Tones include:
   - informational: neutral, factual, helpful
   - professional: formal, business-appropriate
   - empathetic: warm, understanding (for user struggles)
   - apologetic: acknowledging fault (only if Javva at fault)
   - reassuring: calming, confidence-building
   Score 100 if tone matches expected, 0 if completely wrong tone.

3. TOOL_SELECTION (0-100): Were the right tools called?
   - 100: Tools called match the expected ones (ignore `_tool` suffix differences — `search_faq` and `search_faqs_tool` are the same).
   - 80: Most expected tools called, no extra
   - 50: Some expected tools called, or extra tools beyond expected
   - 20: Wrong tools called
   - 0: No tools called when needed (or many wrong tools)

4. LANGUAGE (0-100): Did the agent respond in the same language as the user?
   - 100: Native and consistent in expected language
   - 70: Mostly correct language but some mixing
   - 30: Mostly wrong language
   - 0: Wrong language entirely

Output STRICT JSON format only:
{
  "accuracy": {"score": 85, "reasoning": "..."},
  "tone": {"score": 100, "reasoning": "..."},
  "tool_selection": {"score": 100, "reasoning": "..."},
  "language": {"score": 100, "reasoning": "..."},
  "summary": "Overall: agent answered correctly with right tools..."
}

Be strict but fair. Most professional answers should score 70-90. Reserve 95+ for exceptional responses."""


def build_judge_prompt(case: EvalCase, agent_result: AgentRunResult) -> str:
    eb = case.expected_behavior
    return f"""Evaluate this agent response.

---USER MESSAGE---
Language: {case.language}
Difficulty: {case.difficulty}
Scenario: {case.scenario}
Intent: {case.intent}
Message: {case.user_query}

---EXPECTED BEHAVIOR---
Tools to use: {eb.should_use_tools}
Tone: {eb.tone}
Should mention: {eb.should_mention or 'N/A'}
Should NOT mention: {eb.should_not_mention or 'N/A'}
Should escalate: {eb.should_escalate}

---AGENT RESPONSE---
Tools called: {agent_result.tools_called}
Reply: {agent_result.reply}
Error: {agent_result.error or 'None'}

Score this response. Output JSON only, no preamble."""


def _parse_judge_json(text: str) -> dict:
    """Parse Gemini's JSON output, tolerating markdown code fences.

    Even with `response_mime_type="application/json"` the model occasionally
    wraps the JSON in ```json fences. Strip those and try again.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to extract JSON from a code fence.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    # Last resort: grab the largest {...} block.
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        return json.loads(brace.group(0))
    raise ValueError(f"Could not extract JSON from judge response: {text[:200]}")


async def judge_response(
    case: EvalCase, agent_result: AgentRunResult
) -> dict:
    """Score one agent response across the 4 rubric dimensions."""
    client = get_genai_client()
    prompt = build_judge_prompt(case, agent_result)

    try:
        response = await client.aio.models.generate_content(
            model=JUDGE_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=JUDGE_SYSTEM_PROMPT,
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )

        data = _parse_judge_json(response.text or "")

        scores = {
            dim: JudgeScore(**data[dim])
            for dim in ["accuracy", "tone", "tool_selection", "language"]
        }
        summary = data.get("summary", "")
        return {"scores": scores, "summary": summary}

    except Exception as e:
        log.error("judge_failed", case_id=case.id, error=str(e))
        # Return neutral scores so a single judge failure doesn't sink the
        # case's overall score to 0 (which would conflate infrastructure
        # problems with quality problems).
        return {
            "scores": {
                "accuracy": JudgeScore(
                    score=50, reasoning=f"Judge error: {e}"
                ),
                "tone": JudgeScore(score=50, reasoning="Judge error"),
                "tool_selection": JudgeScore(
                    score=50, reasoning="Judge error"
                ),
                "language": JudgeScore(score=50, reasoning="Judge error"),
            },
            "summary": f"Judge failed: {e}",
        }
