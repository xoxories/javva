"""Javva agent module — tools, schemas, and system prompt.

Phase C.1 shipped tool definitions. Phase C.2 ships the system prompt.
Phase C.3 will add the pydantic-ai Agent that wires them together.

Public surface:
    JAVVA_SYSTEM_PROMPT      - production system prompt
    TONE_GUIDELINES          - tone label -> short description
    validate_prompt()        - structural integrity check

    *_tool                   - 5 async tool implementations
    *Input / *Output / *Info - Pydantic schemas for tool I/O
"""

from app.agent.prompts import (
    JAVVA_SYSTEM_PROMPT,
    TONE_GUIDELINES,
    validate_prompt,
)
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
from app.agent.tools import (
    check_kyc_status_tool,
    escalate_to_human_tool,
    list_transactions_tool,
    lookup_account_tool,
    search_faqs_tool,
)

__all__ = [
    # Prompt
    "JAVVA_SYSTEM_PROMPT",
    "TONE_GUIDELINES",
    "validate_prompt",
    # Tools
    "check_kyc_status_tool",
    "escalate_to_human_tool",
    "list_transactions_tool",
    "lookup_account_tool",
    "search_faqs_tool",
    # Schemas
    "AccountInfo",
    "AccountLookupInput",
    "AccountLookupOutput",
    "CheckKycStatusInput",
    "CheckKycStatusOutput",
    "EscalateInput",
    "EscalateOutput",
    "FaqResult",
    "FaqSearchInput",
    "FaqSearchOutput",
    "KycStatusInfo",
    "ListTransactionsInput",
    "ListTransactionsOutput",
    "TransactionInfo",
]
