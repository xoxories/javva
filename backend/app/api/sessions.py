"""In-memory conversation session store.

Thread-safe dict for development. Phase F may swap in Redis for
multi-instance horizontal scale; the public interface here is the
intended boundary for that swap.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

import structlog


log = structlog.get_logger(__name__)


class SessionStore:
    """Thread-safe in-memory session store with TTL + capacity eviction.

    Each session value is a dict with:
        message_history: list (opaque pydantic-ai ModelMessage list)
        turn_count:      int
        created_at:      datetime (UTC)
        last_active:     datetime (UTC) — refreshed on every read/update
    """

    def __init__(self, max_sessions: int = 1000, ttl_minutes: int = 60) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = Lock()
        self._max_sessions = max_sessions
        self._ttl = timedelta(minutes=ttl_minutes)

    def create_session(self) -> str:
        """Create a new session, return its session_id (UUID4)."""
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        with self._lock:
            if len(self._sessions) >= self._max_sessions:
                self._evict_expired_locked()
                if len(self._sessions) >= self._max_sessions:
                    oldest = min(
                        self._sessions,
                        key=lambda k: self._sessions[k]["last_active"],
                    )
                    del self._sessions[oldest]
                    log.info("session_evicted_oldest", session_id=oldest)

            self._sessions[session_id] = {
                "message_history": [],
                "turn_count": 0,
                "created_at": now,
                "last_active": now,
            }

        log.info("session_created", session_id=session_id)
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Return the session dict, or None if missing/expired.

        Auto-evicts expired sessions on read.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if datetime.now(timezone.utc) - session["last_active"] > self._ttl:
                del self._sessions[session_id]
                log.info("session_expired", session_id=session_id)
                return None
            return session

    def update_session(
        self,
        session_id: str,
        message_history: list,
        increment_turn: bool = True,
    ) -> None:
        """Replace message_history, refresh last_active, optionally bump turn_count."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["message_history"] = message_history
                if increment_turn:
                    self._sessions[session_id]["turn_count"] += 1
                self._sessions[session_id]["last_active"] = datetime.now(timezone.utc)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session. Returns True if it existed, False otherwise."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                log.info("session_deleted", session_id=session_id)
                return True
            return False

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "active_sessions": len(self._sessions),
                "max_sessions": self._max_sessions,
            }

    def _evict_expired_locked(self) -> None:
        """Remove sessions older than TTL. Caller must hold self._lock."""
        now = datetime.now(timezone.utc)
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s["last_active"] > self._ttl
        ]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            log.info("sessions_evicted", count=len(expired))


_session_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    """Return the module-level singleton SessionStore (lazy-init)."""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store
