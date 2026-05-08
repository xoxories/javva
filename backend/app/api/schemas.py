"""Pydantic schemas for the FastAPI HTTP layer."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for POST /chat."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="User message",
    )
    session_id: str | None = Field(
        None,
        description=(
            "Session ID for multi-turn conversations. Pass None to create "
            "a new session — the response will include the new session_id."
        ),
    )


class ChatAPIResponse(BaseModel):
    """Response body from POST /chat."""

    reply: str
    session_id: str
    turn_number: int
    tools_called: list[str]
    duration_ms: int
    error: str | None = None


class ConversationHistory(BaseModel):
    """Response body from GET /chat/{session_id}."""

    session_id: str
    turn_count: int
    messages: list[dict]
    created_at: datetime
    last_active_at: datetime


class HealthResponse(BaseModel):
    """Response body from GET /health."""

    status: str = "ok"
    version: str = "0.1.0"
    services: dict[str, str]
    uptime_seconds: int
