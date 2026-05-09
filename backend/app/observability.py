"""Langfuse observability integration.

Centralizes the Langfuse client and provides graceful degradation when keys
are missing or `LANGFUSE_ENABLED=false`. Callers should treat
`get_langfuse()` returning None as "tracing off — proceed normally".

Targets langfuse SDK v4.x (OpenTelemetry-based). Span creation lives in
`app.agent.chat`; this module only owns the singleton lifecycle.
"""

from __future__ import annotations

import structlog
from langfuse import Langfuse

from app.config import settings


log = structlog.get_logger(__name__)


_langfuse_client: Langfuse | None = None
_initialized = False


def get_langfuse() -> Langfuse | None:
    """Return the cached Langfuse client, or None if disabled / unconfigured.

    Idempotent: caches both the client and the disabled-state decision so
    repeated calls don't re-log the warning.
    """
    global _langfuse_client, _initialized

    if _initialized:
        return _langfuse_client

    _initialized = True

    if not settings.langfuse_enabled:
        log.info("langfuse_disabled", reason="LANGFUSE_ENABLED=false")
        return None

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        log.warning("langfuse_disabled", reason="missing_keys")
        return None

    try:
        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        log.info("langfuse_initialized", host=settings.langfuse_host)
    except Exception as e:
        log.error("langfuse_init_failed", error=str(e))
        _langfuse_client = None

    return _langfuse_client


def is_observability_enabled() -> bool:
    """Quick check used by startup logs and conditional instrumentation."""
    return get_langfuse() is not None


def flush_traces() -> None:
    """Flush pending traces. Call on shutdown to avoid losing in-flight spans."""
    client = get_langfuse()
    if client is None:
        return
    try:
        client.flush()
        log.info("langfuse_flushed")
    except Exception as e:
        log.error("langfuse_flush_failed", error=str(e))
