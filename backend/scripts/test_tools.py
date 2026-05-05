"""Manual async CLI test for the 5 agent tools.

Exercises each tool with realistic inputs to verify end-to-end behavior:
RAG hits, DB connectivity, error handling for not-found cases, async
plumbing.

Requires the seeded backing infrastructure:
  - Postgres seeded by scripts/seed_accounts.py (USR000001 exists)
  - Qdrant collection populated by scripts/embed_faqs.py

Usage:
    uv run python scripts/test_tools.py
"""

from __future__ import annotations

import asyncio
from typing import Any

from rich.console import Console
from rich.panel import Panel

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


console = Console()


def render(label: str, output: Any) -> None:
    body = output.model_dump_json(indent=2)
    console.print(Panel(body, title=label, title_align="left", expand=False))
    console.print()


async def main() -> None:
    # search_faqs
    render(
        "search_faqs — basic EN query",
        await search_faqs_tool(FaqSearchInput(query="How do I withdraw money?")),
    )
    render(
        "search_faqs — filtered (forex_basics, en)",
        await search_faqs_tool(
            FaqSearchInput(query="leverage", category="forex_basics", language="en")
        ),
    )
    render(
        "search_faqs — hybrid (MT5 setup)",
        await search_faqs_tool(
            FaqSearchInput(query="MT5 setup", use_hybrid=True, k=2)
        ),
    )

    # lookup_account
    render(
        "lookup_account — USR000001 (existing)",
        await lookup_account_tool(AccountLookupInput(user_id="USR000001")),
    )
    render(
        "lookup_account — USR999999 (not found)",
        await lookup_account_tool(AccountLookupInput(user_id="USR999999")),
    )

    # list_transactions
    render(
        "list_transactions — USR000001 latest 5",
        await list_transactions_tool(
            ListTransactionsInput(user_id="USR000001", limit=5)
        ),
    )
    render(
        "list_transactions — USR000001 deposits only",
        await list_transactions_tool(
            ListTransactionsInput(
                user_id="USR000001", transaction_type="deposit", limit=3
            )
        ),
    )

    # check_kyc_status
    render(
        "check_kyc_status — USR000001",
        await check_kyc_status_tool(CheckKycStatusInput(user_id="USR000001")),
    )
    render(
        "check_kyc_status — USR000050",
        await check_kyc_status_tool(CheckKycStatusInput(user_id="USR000050")),
    )

    # escalate_to_human
    render(
        "escalate_to_human",
        await escalate_to_human_tool(
            EscalateInput(
                reason="agent unable to resolve withdrawal issue",
                priority="medium",
                summary=(
                    "User USR000001 reports their withdrawal of $500 has been "
                    "pending for 5 days. Lookup confirmed pending status. "
                    "Standard processing time exceeded."
                ),
            )
        ),
    )


if __name__ == "__main__":
    asyncio.run(main())
