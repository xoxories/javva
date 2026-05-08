"""End-to-end smoke test for the Javva HTTP API.

Polls /health to confirm the server is up before issuing other requests
(no fixed-sleep race), then walks through:

    1. GET /
    2. GET /health
    3. POST /chat                           (no session_id → new)
    4. POST /chat                           (with session_id → multi-turn)
    5. GET /chat/{session_id}               (history)
    6. DELETE /chat/{session_id}            (reset)
    7. GET /chat/{session_id}               (expect 404 after delete)

Usage:
    # In one shell, start the server:
    cd backend && uv run uvicorn app.main:app --port 8000

    # In another shell:
    cd backend && uv run python scripts/test_api.py
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx
from rich.console import Console
from rich.panel import Panel

from app.config import settings


console = Console()

BASE_URL = "http://localhost:8000"
HEALTH_POLL_TIMEOUT_S = 30


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if settings.api_key:
        h["X-API-Key"] = settings.api_key
    return h


def _render(label: str, status_code: int, body, duration_ms: int) -> None:
    if isinstance(body, dict):
        body_str = json.dumps(body, indent=2, ensure_ascii=False, default=str)
    else:
        body_str = str(body)
    if len(body_str) > 1500:
        body_str = body_str[:1500] + "...[truncated]"
    title = f"{label} — HTTP {status_code} — {duration_ms} ms"
    console.print(Panel(body_str, title=title, title_align="left", expand=False))
    console.print()


async def _request(
    client: httpx.AsyncClient, method: str, path: str, **kwargs
) -> tuple[int, dict | str, int]:
    t0 = time.time()
    resp = await client.request(method, path, headers=_headers(), **kwargs)
    dt = int((time.time() - t0) * 1000)
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    return resp.status_code, body, dt


async def _wait_for_server(client: httpx.AsyncClient) -> None:
    """Poll /health until the server responds, or timeout."""
    deadline = time.time() + HEALTH_POLL_TIMEOUT_S
    while time.time() < deadline:
        try:
            resp = await client.get("/health", timeout=2)
            if resp.status_code == 200:
                console.print("[green]server is up[/green]\n")
                return
        except Exception:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError(
        f"Server did not respond on /health within {HEALTH_POLL_TIMEOUT_S}s"
    )


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as c:
        console.rule("[bold]wait for server")
        await _wait_for_server(c)

        # 1. GET /
        s, b, d = await _request(c, "GET", "/")
        _render("1. GET /", s, b, d)

        # 2. GET /health
        s, b, d = await _request(c, "GET", "/health")
        _render("2. GET /health", s, b, d)

        # 3. POST /chat — no session_id (creates new)
        s, b, d = await _request(
            c, "POST", "/chat", json={"message": "Apa itu KYC?"}
        )
        _render("3. POST /chat (new session)", s, b, d)
        sid = b.get("session_id") if isinstance(b, dict) else None

        # 4. POST /chat — with session_id (multi-turn)
        if sid:
            s, b, d = await _request(
                c,
                "POST",
                "/chat",
                json={
                    "message": "Berapa lama prosesnya?",
                    "session_id": sid,
                },
            )
            _render(f"4. POST /chat (session={sid[:8]}...)", s, b, d)

        # 5. GET /chat/{sid}
        if sid:
            s, b, d = await _request(c, "GET", f"/chat/{sid}")
            _render(f"5. GET /chat/{sid[:8]}...", s, b, d)

        # 6. DELETE /chat/{sid}
        if sid:
            s, b, d = await _request(c, "DELETE", f"/chat/{sid}")
            _render(f"6. DELETE /chat/{sid[:8]}...", s, b, d)

        # 7. GET /chat/{sid} — expect 404 after delete
        if sid:
            s, b, d = await _request(c, "GET", f"/chat/{sid}")
            _render(
                f"7. GET /chat/{sid[:8]}... (post-delete, expect 404)", s, b, d
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
