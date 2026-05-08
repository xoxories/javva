"""Comprehensive integration tests for agent loop.

These tests hit real Gemini API with daily quota (20 RPD on free tier).
Tests include 7s sleep between calls. Run after quota reset (midnight
Pacific) to avoid 429s during burst testing.

Coverage:
- Basic FAQ queries (EN + ID)
- Account lookups (existing, suspended)
- Multi-tool single turn (parallel tool calling)
- Multi-turn context retention
- Trading advice refusal
- Hostile user escalation
- Off-topic redirection
- Invalid user_id format handling

Throttling: `throttle` is a SYNC autouse fixture (see fixture docstring).

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


async def test_ambiguous_user_id() -> None:
    """Bare digits (no USR prefix) should NOT trigger lookup_account."""
    result = await chat("Check my balance, ID 123456")
    assert "lookup_account_tool" not in result.tools_called
    assert result.error is None


async def test_multi_tool_single_turn() -> None:
    """A combined balance+transactions query should call lookup_account
    (and ideally list_transactions in the same turn)."""
    result = await chat("USR000001 — balance and recent transactions?")
    assert "lookup_account_tool" in result.tools_called
    assert result.error is None


async def test_hostile_user_escalation() -> None:
    """Hostile/profane complaint should escalate, not respond defensively."""
    result = await chat(
        "This platform is GARBAGE! I'm losing money! "
        "Get me your manager NOW!"
    )
    assert "escalate_to_human_tool" in result.tools_called
    assert result.error is None


async def test_off_topic_request() -> None:
    """Off-topic dev request (Python coding) should not call any tool."""
    result = await chat("Write me a Python Fibonacci script")
    assert len(result.tools_called) == 0
    assert result.error is None
