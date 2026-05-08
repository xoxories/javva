"""Pydantic AI agent for Javva customer support.

Wires together the Phase C.1 tools and the Phase C.2 system prompt into a
single agent loop. Stateless API: caller passes message_history between
turns.

API note: this file targets pydantic-ai 1.x. Result attributes are
`result.output` (not `result.data` from older docs) and `RunUsage` exposes
`input_tokens` / `output_tokens` (not `request_tokens` / `response_tokens`).

Quota note: gemini-2.5 models on Gemini's *free tier* have a 20-request-
per-day cap (per project, per model — `quotaId` is
`GenerateRequestsPerDayPerProjectPerModel-FreeTier`). Enabling GCP billing
does NOT auto-promote a project to a paid tier; that needs an explicit
upgrade in the Cloud Console. Production deployments should run on a
paid-tier project to lift this cap.

Retries: `Agent(retries=4, ...)` — bumped from 2 to compensate for
flash-lite occasionally producing slightly malformed structured output
on FAQ tool calls (manifests as `Exceeded maximum retries for output
validation`).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent, Tool
from pydantic_ai.messages import TextPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from app.agent.prompts import JAVVA_SYSTEM_PROMPT
from app.agent.tools import (
    check_kyc_status_tool,
    escalate_to_human_tool,
    list_transactions_tool,
    lookup_account_tool,
    search_faqs_tool,
)
from app.config import settings


log = structlog.get_logger(__name__)


class ChatResponse(BaseModel):
    """Agent response with metadata for observability.

    `message_history` carries pydantic-ai ModelMessage objects opaquely;
    callers store and pass back without inspecting. Phase D will add
    serialization for cross-process transport.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    reply: str
    message_history: list[Any] = []
    tools_called: list[str] = []
    usage: dict[str, int] = {}
    duration_ms: int = 0
    error: str | None = None


_agent_instance: Agent | None = None


def get_agent() -> Agent:
    """Return the module-level singleton Pydantic AI agent (lazy-init).

    Provider is chosen by `settings.use_vertex_ai`. We use the unified
    `GoogleProvider` for both paths — the legacy split (`GoogleGLAProvider`
    / `GoogleVertexProvider`) has an internal bug on pydantic-ai 1.90.0
    with the current google-genai SDK (`'AsyncClient' object has no
    attribute 'aio'`).
    """
    global _agent_instance
    if _agent_instance is None:
        if settings.use_vertex_ai:
            if not settings.gcp_project_id:
                raise RuntimeError(
                    "use_vertex_ai=True requires GCP_PROJECT_ID in .env"
                )
            provider = GoogleProvider(
                vertexai=True,
                project=settings.gcp_project_id,
                location=settings.gcp_location,
            )
        else:
            if not settings.gemini_api_key:
                raise RuntimeError(
                    "use_vertex_ai=False requires GEMINI_API_KEY in .env"
                )
            provider = GoogleProvider(api_key=settings.gemini_api_key)

        _agent_instance = Agent(
            GoogleModel(settings.gemini_default_model, provider=provider),
            system_prompt=JAVVA_SYSTEM_PROMPT,
            tools=[
                Tool(search_faqs_tool),
                Tool(lookup_account_tool),
                Tool(list_transactions_tool),
                Tool(check_kyc_status_tool),
                Tool(escalate_to_human_tool),
            ],
            retries=4,
        )
        log.info(
            "agent_initialized",
            model=settings.gemini_default_model,
            provider="vertex_ai" if settings.use_vertex_ai else "aistudio",
            tool_count=5,
        )
    return _agent_instance


def _extract_tools_called(messages: list) -> list[str]:
    """Collect tool names from ToolCallPart instances in the message stream.

    Uses `isinstance` rather than duck-typing on `tool_name`, because
    ToolReturnPart also has that attribute and was double-counting tools
    in the earlier implementation.
    """
    tools: list[str] = []
    for msg in messages:
        for part in getattr(msg, "parts", []):
            if isinstance(part, ToolCallPart):
                tools.append(part.tool_name)
    return tools


def summarize_messages(message_history: list) -> dict[str, int]:
    """Extract observability stats from a pydantic-ai message_history list.

    Useful for the Phase D HTTP API to surface session-level metrics in
    structured logs and dashboards.

    Returns a dict with:
      - turn_count: number of user turns in the conversation
      - user_messages: same as turn_count (kept for clarity in logs)
      - tool_calls: total ToolCallPart instances across all messages
      - assistant_responses: total TextPart instances (model replies)
    """
    turn_count = 0
    user_messages = 0
    tool_calls = 0
    assistant_responses = 0

    for msg in message_history:
        for part in getattr(msg, "parts", []):
            if isinstance(part, UserPromptPart):
                user_messages += 1
                turn_count += 1
            elif isinstance(part, ToolCallPart):
                tool_calls += 1
            elif isinstance(part, TextPart):
                assistant_responses += 1

    return {
        "turn_count": turn_count,
        "user_messages": user_messages,
        "tool_calls": tool_calls,
        "assistant_responses": assistant_responses,
    }


def _extract_usage(usage_obj: Any) -> dict[str, int]:
    """Pull token counts off RunUsage in a version-tolerant way."""
    input_tokens = int(getattr(usage_obj, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage_obj, "output_tokens", 0) or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


async def chat(
    user_message: str,
    message_history: list | None = None,
) -> ChatResponse:
    """Run a single turn of the Javva agent.

    Args:
        user_message: User's input message in any supported language.
        message_history: List of pydantic-ai ModelMessage objects from prior
            turns (pass `previous_response.message_history`). None or
            empty list = first turn.

    Returns:
        ChatResponse. On failure, returns a user-facing apology message
        with `error` set; never raises.
    """
    start = time.time()
    log.info(
        "chat_request",
        message=user_message[:100],
        history_length=len(message_history or []),
    )

    try:
        agent = get_agent()
        result = await asyncio.wait_for(
            agent.run(user_message, message_history=message_history or []),
            timeout=30.0,
        )

        all_messages = result.all_messages()
        tools_called = _extract_tools_called(all_messages)
        usage = _extract_usage(result.usage())
        duration_ms = int((time.time() - start) * 1000)

        reply = (
            result.output
            if isinstance(result.output, str)
            else str(result.output)
        )

        log.info(
            "chat_response",
            tools_called=tools_called,
            total_tokens=usage["total_tokens"],
            duration_ms=duration_ms,
        )

        return ChatResponse(
            reply=reply,
            message_history=all_messages,
            tools_called=tools_called,
            usage=usage,
            duration_ms=duration_ms,
        )

    except asyncio.TimeoutError:
        duration_ms = int((time.time() - start) * 1000)
        log.error("chat_timeout", duration_ms=duration_ms)
        return ChatResponse(
            reply=(
                "I apologize, the request is taking longer than expected. "
                "Please try again."
            ),
            message_history=message_history or [],
            error="timeout",
            duration_ms=duration_ms,
        )
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log.error("chat_failed", error=str(e), duration_ms=duration_ms)
        return ChatResponse(
            reply=(
                "I apologize, but I'm experiencing technical difficulties. "
                "Please try again, or contact our support team if the issue persists."
            ),
            message_history=message_history or [],
            error=str(e)[:200],
            duration_ms=duration_ms,
        )
