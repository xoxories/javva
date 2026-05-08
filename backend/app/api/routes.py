"""FastAPI route handlers for the Javva HTTP API.

Endpoints (all under the same prefix-less APIRouter):
    GET  /health                  public, returns DB / Qdrant / LLM info
    POST /chat                    auth, runs one agent turn
    GET  /chat/{session_id}       auth, returns conversation history
    DELETE /chat/{session_id}     auth, deletes a session

The root path `GET /` lives in app.main (welcome JSON, public).
"""

from __future__ import annotations

import time

import psycopg
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status
from qdrant_client import QdrantClient

from app.agent import chat
from app.api.schemas import (
    ChatAPIResponse,
    ChatRequest,
    ConversationHistory,
    HealthResponse,
)
from app.api.sessions import get_session_store
from app.config import settings


log = structlog.get_logger(__name__)


router = APIRouter()


_start_time = time.monotonic()


async def verify_api_key(x_api_key: str | None = Header(None)) -> str | None:
    """Verify X-API-Key header against `settings.api_key`.

    When `settings.api_key` is unset (None or empty), authentication is
    disabled — dev mode. A startup warning is logged in `app.main` so
    this isn't silent.
    """
    if not settings.api_key:
        return None
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header required",
        )
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return x_api_key


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check.

    `status` reflects DB + Qdrant connectivity only. `services` includes
    `llm_provider` as informational (not gated on).
    """
    services: dict[str, str] = {}

    try:
        with psycopg.connect(
            settings.database_url,
            prepare_threshold=None,
            connect_timeout=5,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        services["database"] = "ok"
    except Exception as e:
        services["database"] = f"error: {str(e)[:50]}"

    try:
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=5,
        )
        client.get_collections()
        services["qdrant"] = "ok"
    except Exception as e:
        services["qdrant"] = f"error: {str(e)[:50]}"

    services["llm_provider"] = (
        "vertex_ai" if settings.use_vertex_ai else "aistudio"
    )

    overall_status = (
        "ok"
        if services["database"] == "ok" and services["qdrant"] == "ok"
        else "degraded"
    )

    return HealthResponse(
        status=overall_status,
        services=services,
        uptime_seconds=int(time.monotonic() - _start_time),
    )


@router.post(
    "/chat",
    response_model=ChatAPIResponse,
    dependencies=[Depends(verify_api_key)],
)
async def chat_endpoint(request: ChatRequest) -> ChatAPIResponse:
    """Run one agent turn.

    - If `session_id` is null, a new session is created.
    - If `session_id` is provided but missing/expired, a new session is
      created and the new id is returned (logged as
      `chat_new_session_after_expired`).
    - Otherwise the existing session's `message_history` feeds the agent.
    """
    store = get_session_store()

    if request.session_id:
        session = store.get_session(request.session_id)
        if session is None:
            session_id = store.create_session()
            message_history: list = []
            log.info(
                "chat_new_session_after_expired",
                requested_session_id=request.session_id,
                new_session_id=session_id,
            )
        else:
            session_id = request.session_id
            message_history = session["message_history"]
    else:
        session_id = store.create_session()
        message_history = []

    result = await chat(
        user_message=request.message,
        message_history=message_history,
    )

    store.update_session(
        session_id=session_id,
        message_history=result.message_history,
        increment_turn=True,
    )

    # Race-handling: a session could expire between our create/get above
    # and the update we just issued. Recreate cleanly in that case.
    updated = store.get_session(session_id)
    if updated is None:
        session_id = store.create_session()
        store.update_session(
            session_id=session_id,
            message_history=result.message_history,
            increment_turn=True,
        )
        updated = store.get_session(session_id)
        log.warning("session_recreated_post_chat", session_id=session_id)

    turn_number = updated["turn_count"] if updated else 1

    return ChatAPIResponse(
        reply=result.reply,
        session_id=session_id,
        turn_number=turn_number,
        tools_called=result.tools_called,
        duration_ms=result.duration_ms,
        error=result.error,
    )


@router.get(
    "/chat/{session_id}",
    response_model=ConversationHistory,
    dependencies=[Depends(verify_api_key)],
)
async def get_conversation(session_id: str) -> ConversationHistory:
    """Return conversation history for a session.

    Messages are projected to flat `{type, content}` dicts — opaque
    enough for client display, lossy on tool args/results. Phase D.4
    (streaming) will need a richer schema.
    """
    store = get_session_store()
    session = store.get_session(session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found or expired",
        )

    messages: list[dict] = []
    for msg in session["message_history"]:
        for part in getattr(msg, "parts", []):
            content = (
                getattr(part, "content", None)
                or getattr(part, "text", None)
                or str(part)[:200]
            )
            if not isinstance(content, str):
                content = str(content)[:500]
            messages.append(
                {"type": type(part).__name__, "content": content}
            )

    return ConversationHistory(
        session_id=session_id,
        turn_count=session["turn_count"],
        messages=messages,
        created_at=session["created_at"],
        last_active_at=session["last_active"],
    )


@router.delete(
    "/chat/{session_id}",
    dependencies=[Depends(verify_api_key)],
)
async def delete_conversation(session_id: str) -> dict:
    """Delete (reset) a conversation session."""
    store = get_session_store()
    deleted = store.delete_session(session_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    return {"deleted": True, "session_id": session_id}
