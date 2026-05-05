"""Tests for app.agent.tools.

Integration tests — they hit real Postgres + Qdrant + Gemini. Required:
  - .env with DATABASE_URL, GEMINI_API_KEY, QDRANT_URL, QDRANT_API_KEY
  - Postgres seeded by scripts/seed_accounts.py (USR000001 exists, USR999999
    intentionally does not)
  - Qdrant 'javva_kb' collection populated by scripts/embed_faqs.py

Run from backend/:
    uv run pytest tests/unit/test_tools.py -v
"""

from __future__ import annotations

import pytest

from app.agent.schemas import (
    AccountLookupInput,
    CheckKycStatusInput,
    EscalateInput,
    FaqSearchInput,
    ListTransactionsInput,
)
from app.agent.tools import (
    check_kyc_status_tool,
    escalate_to_human_tool,
    list_transactions_tool,
    lookup_account_tool,
    search_faqs_tool,
)


pytestmark = pytest.mark.asyncio


async def test_search_faqs_basic() -> None:
    result = await search_faqs_tool(FaqSearchInput(query="How do I withdraw money?"))
    assert result.total_found > 0
    assert len(result.results) <= 3


async def test_search_faqs_with_filters() -> None:
    result = await search_faqs_tool(
        FaqSearchInput(query="leverage", category="forex_basics", language="en")
    )
    assert all(r.category == "forex_basics" for r in result.results)
    assert all(r.language == "en" for r in result.results)


async def test_search_faqs_hybrid() -> None:
    result = await search_faqs_tool(
        FaqSearchInput(query="MT5 setup", use_hybrid=True)
    )
    assert result.total_found > 0


async def test_lookup_account_existing() -> None:
    result = await lookup_account_tool(AccountLookupInput(user_id="USR000001"))
    assert result.found
    assert result.account is not None
    assert result.account.user_id == "USR000001"


async def test_lookup_account_not_found() -> None:
    result = await lookup_account_tool(AccountLookupInput(user_id="USR999999"))
    assert not result.found
    assert result.error is not None


async def test_list_transactions_existing() -> None:
    result = await list_transactions_tool(
        ListTransactionsInput(user_id="USR000001", limit=5)
    )
    assert result.found
    assert result.total_count <= 5


async def test_list_transactions_filtered() -> None:
    result = await list_transactions_tool(
        ListTransactionsInput(user_id="USR000001", transaction_type="deposit")
    )
    # Either empty (user has no deposits) or all results are deposits.
    assert all(t.type == "deposit" for t in result.transactions)


async def test_check_kyc_status() -> None:
    result = await check_kyc_status_tool(CheckKycStatusInput(user_id="USR000001"))
    assert result.found
    assert result.kyc is not None
    assert result.kyc.status in {"not_started", "pending", "verified", "rejected"}


async def test_escalate_to_human() -> None:
    result = await escalate_to_human_tool(
        EscalateInput(
            reason="Test escalation",
            priority="medium",
            summary="User test summary",
        )
    )
    assert result.escalated
    assert result.ticket_id.startswith("TKT-")
    assert len(result.ticket_id) == 12  # "TKT-" + 8 hex chars
