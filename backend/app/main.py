"""Javva FastAPI application entry point.

Wires up CORS middleware, mounts the API router from `app.api.routes`,
and exposes a public welcome endpoint at the root path. All `/chat*` and
`/health` endpoints live in the API router.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.config import settings
from app.credentials import decode_service_account_credentials
from app.observability import flush_traces, is_observability_enabled


log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Resolve Vertex AI credentials first; later startup steps (and the
    # first request) may instantiate the genai client, which reads
    # GOOGLE_APPLICATION_CREDENTIALS at construction time.
    decode_service_account_credentials()
    if not settings.api_key:
        log.warning(
            "api_auth_disabled",
            reason=(
                "api_key not set in .env — /chat endpoints are unauthenticated "
                "(dev mode). Set API_KEY before deploying."
            ),
        )
    if is_observability_enabled():
        log.info("observability_enabled", provider="langfuse")
    log.info(
        "javva_api_started",
        llm_provider="vertex_ai" if settings.use_vertex_ai else "aistudio",
        env=settings.env,
    )
    yield
    flush_traces()


app = FastAPI(
    title="Javva API",
    description="AI customer support agent for forex/CFD trading.",
    version="0.1.0",
    lifespan=lifespan,
)


# Phase G will tighten allow_origins for production; "*" is fine for dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict:
    """Public welcome with API metadata."""
    return {
        "name": "Javva",
        "description": "AI customer support agent",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


app.include_router(api_router)
