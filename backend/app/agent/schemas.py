"""Pydantic schemas for the 5 Javva agent tools.

Each tool has an Input model (what the LLM passes in) and an Output model
(what the tool returns). Field descriptions are intentionally verbose —
the LLM reads these and uses them to plan tool calls correctly.

Tools never raise from their handlers; failure modes are encoded as
`found=False` + `error=...` on the Output models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# search_faqs
# ---------------------------------------------------------------------------


class FaqSearchInput(BaseModel):
    """Input for search_faqs."""

    query: str = Field(
        ..., description="The user's question or search query."
    )
    k: int = Field(
        3,
        description="Number of FAQ results to return.",
        ge=1,
        le=10,
    )
    category: str | None = Field(
        None,
        description=(
            "Optional filter to one of: forex_basics, account_management, "
            "deposits_withdrawals, kyc_security, trading_mechanics, "
            "platform_features."
        ),
    )
    language: Literal["en", "id"] | None = Field(
        None,
        description="Optional filter: 'en' for English, 'id' for Indonesian.",
    )
    use_hybrid: bool = Field(
        False,
        description=(
            "Use hybrid search (vector + BM25 keyword). Better for queries "
            "containing exact terms like MT5, KYC, EUR/USD; for purely "
            "conceptual queries leave this False."
        ),
    )


class FaqResult(BaseModel):
    """One FAQ search hit."""

    question: str
    answer: str
    category: str
    language: str
    score: float


class FaqSearchOutput(BaseModel):
    """Output from search_faqs."""

    results: list[FaqResult]
    total_found: int


# ---------------------------------------------------------------------------
# lookup_account
# ---------------------------------------------------------------------------


class AccountLookupInput(BaseModel):
    """Input for lookup_account."""

    user_id: str = Field(
        ...,
        description=(
            "User ID in format USR followed by 6 digits (e.g., USR000123). "
            "Required exactly as the user provides it."
        ),
    )


class AccountInfo(BaseModel):
    """Full account record."""

    user_id: str
    full_name: str
    email: str
    country_code: str
    account_type: str  # standard, cent, demo
    base_currency: str  # USD, IDR, etc.
    balance: float
    leverage: int  # 100, 500, 1000
    status: str  # active, inactive, suspended
    created_at: datetime
    last_login_at: datetime | None


class AccountLookupOutput(BaseModel):
    """Output from lookup_account."""

    found: bool
    account: AccountInfo | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# list_transactions
# ---------------------------------------------------------------------------


class ListTransactionsInput(BaseModel):
    """Input for list_transactions."""

    user_id: str = Field(
        ...,
        description="User ID in format USR followed by 6 digits (e.g., USR000123).",
    )
    limit: int = Field(
        10,
        description="Maximum number of transactions to return.",
        ge=1,
        le=50,
    )
    transaction_type: Literal["deposit", "withdrawal", "trade", "all"] = Field(
        "all",
        description="Filter by transaction type. 'all' returns every type.",
    )
    status: Literal["pending", "completed", "failed", "all"] = Field(
        "all",
        description="Filter by transaction status. 'all' returns every status.",
    )


class TransactionInfo(BaseModel):
    """One transaction record."""

    type: str  # deposit, withdrawal, trade
    amount: float
    currency: str
    status: str  # pending, completed, failed
    method: str | None  # bank_transfer, crypto, ewallet, trade_pl
    created_at: datetime
    completed_at: datetime | None


class ListTransactionsOutput(BaseModel):
    """Output from list_transactions."""

    found: bool
    transactions: list[TransactionInfo] = []
    total_count: int = 0
    error: str | None = None


# ---------------------------------------------------------------------------
# check_kyc_status
# ---------------------------------------------------------------------------


class CheckKycStatusInput(BaseModel):
    """Input for check_kyc_status."""

    user_id: str = Field(
        ...,
        description="User ID in format USR followed by 6 digits (e.g., USR000123).",
    )


class KycStatusInfo(BaseModel):
    """KYC verification record."""

    user_id: str
    status: str  # not_started, pending, verified, rejected
    document_type: str | None  # passport, id_card, drivers_license, or None
    submitted_at: datetime | None
    verified_at: datetime | None
    rejection_reason: str | None


class CheckKycStatusOutput(BaseModel):
    """Output from check_kyc_status."""

    found: bool
    kyc: KycStatusInfo | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# escalate_to_human
# ---------------------------------------------------------------------------


class EscalateInput(BaseModel):
    """Input for escalate_to_human."""

    reason: str = Field(
        ...,
        description=(
            "Brief reason for escalation, e.g. 'complex complaint', "
            "'fraud suspicion', 'agent unable to resolve withdrawal issue'."
        ),
    )
    priority: Literal["low", "medium", "high"] = Field(
        "medium",
        description=(
            "Escalation priority. Use 'high' for fraud / security / loss-of-"
            "funds, 'medium' for stuck-but-not-urgent issues, 'low' for "
            "general policy questions the agent can't answer."
        ),
    )
    summary: str = Field(
        ...,
        description=(
            "Short summary of the conversation so far for the human agent's "
            "context. Include user_id if known and what's already been tried."
        ),
    )


class EscalateOutput(BaseModel):
    """Output from escalate_to_human."""

    escalated: bool
    ticket_id: str  # TKT-XXXXXXXX
    message: str
