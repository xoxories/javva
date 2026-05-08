"""Tests for app.agent.chat — integration tests.

These hit real Gemini + Postgres + Qdrant. Required env (.env):
GEMINI_API_KEY, DATABASE_URL, QDRANT_URL, QDRANT_API_KEY. The DB and
Qdrant collection must already be seeded (Phase A.2 / B.1).

Each test invokes the full agent loop, which can take 2–10s per call due
to LLM latency + tool round-trips.

Quota note: gemini-2.5 models on the *free tier* have a 20-request-per-day
cap. Running this whole suite uses ~14 LLM calls. If quota is exhausted,
all tests fail with 429s; resume after quota reset (~midnight Pacific) or
on a paid-tier project.

Throttling: `throttle` is a SYNC autouse fixture that calls `time.sleep(7)`
after each test. Earlier `@pytest_asyncio.fixture` async-autouse pattern
caused "Event loop is closed" failures because pytest-asyncio's per-function
loop scope tears down the loop before the post-yield `await` runs. Sync
sleep sidesteps the loop entirely.

Run from backend/:
    uv run pytest tests/unit/test_agent.py -v
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.agent import ChatResponse, chat


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def throttle():
    """Sleep 7s after every test to stay clear of Gemini RPM caps.

    Sync fixture by design — see module docstring.
    """
    yield
    time.sleep(7)


async def test_general_faq_en() -> None:
    result = await chat("How do I withdraw money?")
    assert isinstance(result, ChatResponse)
    assert len(result.reply) > 20
    assert "search_faqs_tool" in result.tools_called
    assert result.error is None


async def test_general_faq_id() -> None:
    result = await chat("Apa itu leverage?")
    assert len(result.reply) > 20
    assert result.error is None


async def test_account_lookup() -> None:
    result = await chat("What's my balance? USR000001")
    assert "lookup_account_tool" in result.tools_called
    assert result.error is None


async def test_invalid_user_id_handled() -> None:
    # Format is too short to be valid (USR + 6 digits expected)
    result = await chat("Check my account: USR123")
    # Agent should ask for the correct format rather than silently fail.
    assert result.error is None
    assert len(result.reply) > 0


async def test_trading_advice_refused() -> None:
    result = await chat("Should I buy EUR/USD now?")
    # Should not give specific buy/sell advice. Soft assertion: agent
    # response should either decline explicitly or pivot to risk concepts.
    reply_lower = result.reply.lower()
    assert (
        "cannot" in reply_lower
        or "can't" in reply_lower
        or "unable" in reply_lower
        or "advice" in reply_lower
        or "risk" in reply_lower
    )
    assert result.error is None


async def test_escalation_triggered() -> None:
    result = await chat(
        "This is the third time my withdrawal failed! "
        "I demand to speak to a manager NOW!"
    )
    assert "escalate_to_human_tool" in result.tools_called
    assert result.error is None


async def test_multi_turn_context() -> None:
    turn1 = await chat("I want to know about deposits")
    assert turn1.error is None

    # Throttle between back-to-back calls inside a single test (the autouse
    # fixture only fires between tests).
    await asyncio.sleep(7)

    turn2 = await chat(
        "What about for IDR currency specifically?",
        message_history=turn1.message_history,
    )
    assert turn2.error is None
    # Soft check: turn 2 should produce a substantive response.
    assert len(turn2.reply) > 20
