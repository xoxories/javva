"""Async tool implementations for the Javva agent.

Each tool wraps a sync I/O call (Postgres or app.rag) inside
`asyncio.to_thread` so the agent's async event loop isn't blocked. Tools
never raise — failures are encoded as `found=False` + `error=...` on the
output schema, so the LLM gets structured signal it can react to.

Phase C.1 ships the bare functions. Phase C.3 will wrap them with
pydantic-ai's `@agent.tool` and assemble the agent loop.
"""

from __future__ import annotations

import asyncio
import uuid

import psycopg
import structlog
from psycopg.rows import dict_row

from app.agent.schemas import (
    AccountInfo,
    AccountLookupInput,
    AccountLookupOutput,
    CheckKycStatusInput,
    CheckKycStatusOutput,
    EscalateInput,
    EscalateOutput,
    FaqResult,
    FaqSearchInput,
    FaqSearchOutput,
    KycStatusInfo,
    ListTransactionsInput,
    ListTransactionsOutput,
    TransactionInfo,
)
from app.config import settings
from app.rag import RetrievalFilter, search_faqs, search_faqs_hybrid


log = structlog.get_logger(__name__)


def _db_connect() -> psycopg.Connection:
    """Open a Postgres connection.

    Uses prepare_threshold=None for Supabase Transaction Pooler compatibility
    (the same pattern as scripts/migrate_db.py and scripts/seed_accounts.py).
    Connection per call — no pool yet; Phase D will introduce psycopg_pool.
    """
    return psycopg.connect(
        settings.database_url,
        prepare_threshold=None,
        row_factory=dict_row,
    )


# ---------------------------------------------------------------------------
# search_faqs
# ---------------------------------------------------------------------------


async def search_faqs_tool(input: FaqSearchInput) -> FaqSearchOutput:
    """Search the Javva FAQ knowledge base.

    Use this for general questions about:
      - Forex/CFD trading basics
      - Account management
      - Deposits / withdrawals
      - KYC / security
      - Trading mechanics
      - Platform features (MT4 / MT5)

    Don't use this for account-specific queries — use lookup_account or
    list_transactions instead.
    """
    log.info(
        "tool_search_faqs",
        query=input.query[:50],
        k=input.k,
        category=input.category,
        language=input.language,
        use_hybrid=input.use_hybrid,
    )

    filters = None
    if input.category or input.language:
        filters = RetrievalFilter(
            category=input.category,
            language=input.language,
        )

    if input.use_hybrid:
        result = await asyncio.to_thread(
            search_faqs_hybrid,
            input.query,
            k=input.k,
            filters=filters,
        )
    else:
        result = await asyncio.to_thread(
            search_faqs,
            input.query,
            k=input.k,
            filters=filters,
        )

    return FaqSearchOutput(
        results=[
            FaqResult(
                question=r.question,
                answer=r.answer,
                category=r.category,
                language=r.language,
                score=r.score,
            )
            for r in result.results
        ],
        total_found=result.total_found,
    )


# ---------------------------------------------------------------------------
# lookup_account
# ---------------------------------------------------------------------------


async def lookup_account_tool(input: AccountLookupInput) -> AccountLookupOutput:
    """Look up account information by user_id.

    Use this when the user mentions their user_id (USR000XXX format) or asks
    about their account status, balance, leverage, or other account-level
    settings.
    """
    log.info("tool_lookup_account", user_id=input.user_id)

    def _query() -> dict | None:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, full_name, email, country_code,
                           account_type, base_currency, balance, leverage,
                           status, created_at, last_login_at
                    FROM accounts
                    WHERE user_id = %s;
                    """,
                    (input.user_id,),
                )
                return cur.fetchone()

    try:
        row = await asyncio.to_thread(_query)
    except Exception as e:
        log.error("tool_lookup_account_failed", error=str(e))
        return AccountLookupOutput(found=False, error=f"Database error: {str(e)[:100]}")

    if row is None:
        return AccountLookupOutput(found=False, error=f"Account {input.user_id} not found")

    return AccountLookupOutput(
        found=True,
        account=AccountInfo(
            user_id=row["user_id"],
            full_name=row["full_name"],
            email=row["email"],
            country_code=row["country_code"],
            account_type=row["account_type"],
            base_currency=row["base_currency"],
            balance=float(row["balance"]),
            leverage=row["leverage"],
            status=row["status"],
            created_at=row["created_at"],
            last_login_at=row["last_login_at"],
        ),
    )


# ---------------------------------------------------------------------------
# list_transactions
# ---------------------------------------------------------------------------


async def list_transactions_tool(
    input: ListTransactionsInput,
) -> ListTransactionsOutput:
    """List a user's recent transactions.

    Use this when the user asks about:
      - Recent trade activity
      - Deposit / withdrawal history
      - Whether a specific transaction has completed or is still pending
    """
    log.info(
        "tool_list_transactions",
        user_id=input.user_id,
        type=input.transaction_type,
        status=input.status,
        limit=input.limit,
    )

    def _query() -> list[dict]:
        # WHERE clause built from hardcoded SQL fragments only (no user input
        # interpolated). User values are passed through psycopg parameters.
        where_parts = ["a.user_id = %s"]
        params: list = [input.user_id]
        if input.transaction_type != "all":
            where_parts.append("t.type = %s")
            params.append(input.transaction_type)
        if input.status != "all":
            where_parts.append("t.status = %s")
            params.append(input.status)
        params.append(input.limit)
        where_clause = " AND ".join(where_parts)

        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT t.type, t.amount, t.currency, t.status,
                           t.method, t.created_at, t.completed_at
                    FROM transactions t
                    JOIN accounts a ON a.id = t.account_id
                    WHERE {where_clause}
                    ORDER BY t.created_at DESC
                    LIMIT %s;
                    """,
                    params,
                )
                return cur.fetchall()

    try:
        rows = await asyncio.to_thread(_query)
    except Exception as e:
        log.error("tool_list_transactions_failed", error=str(e))
        return ListTransactionsOutput(found=False, error=f"Database error: {str(e)[:100]}")

    return ListTransactionsOutput(
        found=True,
        transactions=[
            TransactionInfo(
                type=row["type"],
                amount=float(row["amount"]),
                currency=row["currency"],
                status=row["status"],
                method=row["method"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            )
            for row in rows
        ],
        total_count=len(rows),
    )


# ---------------------------------------------------------------------------
# check_kyc_status
# ---------------------------------------------------------------------------


async def check_kyc_status_tool(
    input: CheckKycStatusInput,
) -> CheckKycStatusOutput:
    """Check the KYC verification status for a user.

    Use this when the user asks:
      - Why withdrawal is restricted
      - What their verification status is
      - Whether their documents have been reviewed
      - Why their KYC was rejected
    """
    log.info("tool_check_kyc", user_id=input.user_id)

    def _query() -> dict | None:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT k.status, k.document_type, k.submitted_at,
                           k.verified_at, k.rejection_reason
                    FROM kyc_statuses k
                    JOIN accounts a ON a.id = k.account_id
                    WHERE a.user_id = %s;
                    """,
                    (input.user_id,),
                )
                return cur.fetchone()

    try:
        row = await asyncio.to_thread(_query)
    except Exception as e:
        log.error("tool_check_kyc_failed", error=str(e))
        return CheckKycStatusOutput(found=False, error=f"Database error: {str(e)[:100]}")

    if row is None:
        return CheckKycStatusOutput(found=False, error=f"No KYC record for {input.user_id}")

    return CheckKycStatusOutput(
        found=True,
        kyc=KycStatusInfo(
            user_id=input.user_id,
            status=row["status"],
            document_type=row["document_type"],
            submitted_at=row["submitted_at"],
            verified_at=row["verified_at"],
            rejection_reason=row["rejection_reason"],
        ),
    )


# ---------------------------------------------------------------------------
# escalate_to_human
# ---------------------------------------------------------------------------


async def escalate_to_human_tool(input: EscalateInput) -> EscalateOutput:
    """Escalate the conversation to a human support agent.

    Use this when:
      - The complaint is complex and requires policy review
      - You suspect fraud or a security issue
      - The user explicitly asks for a human
      - You've tried 2-3 turns and can't resolve the issue

    Generates a ticket ID and returns a user-facing message. Phase D will
    persist the ticket to a support_tickets table; for now the structlog
    event is the durable record.
    """
    log.info(
        "tool_escalate",
        reason=input.reason[:80],
        priority=input.priority,
        summary_length=len(input.summary),
    )

    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"

    return EscalateOutput(
        escalated=True,
        ticket_id=ticket_id,
        message=(
            f"I've escalated your case to our human support team. "
            f"Your ticket number is {ticket_id}. "
            f"A specialist will respond within 24 hours via email."
        ),
    )
