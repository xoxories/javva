"""Javva agent module — tools, schemas, system prompt, and agent loop.

Phase C.1 shipped tool definitions, C.2 the system prompt, C.3 the
agent loop (this).

Public surface:
    chat()                   - main async entry point (stateless)
    ChatResponse             - response schema with metadata
    get_agent()              - lazy singleton Pydantic AI Agent

    JAVVA_SYSTEM_PROMPT      - production system prompt
    TONE_GUIDELINES          - tone label -> short description
    validate_prompt()        - structural integrity check

    *_tool                   - 5 async tool implementations
    *Input / *Output / *Info - Pydantic schemas for tool I/O
"""

from app.agent.agent import ChatResponse, chat, get_agent, summarize_messages
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
    # Agent
    "ChatResponse",
    "chat",
    "get_agent",
    "summarize_messages",
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
