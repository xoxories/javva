"""Generate evaluation test cases for the Javva agent.

Generates 100 test cases across 8 scenarios in English and Indonesian, with
varying difficulty (easy/medium/hard) and intent (faq/account_query/escalate).
Account_query cases reference realistic user_ids drawn from the seeded
Postgres so the agent's tool calls return matching state at eval time.

Free-tier daily request limits — see scripts/generate_faq.py for the table.
This script issues 8 API calls baseline (one per scenario), well under any
free-tier cap on gemini-2.5-flash-lite.

Checkpoint behaviour:
    After each scenario batch finishes, all cases-so-far are written to
    data/eval_cases.partial.json. On rerun, scenarios already represented
    are detected and skipped. On a clean full run, partial is renamed to
    data/eval_cases.json.

Usage:
    # Full generation (8 API calls -> 100 cases -> data/eval_cases.json)
    uv run python scripts/generate_eval.py

    # Smoke test (1 API call -> 5 new_user cases -> data/eval_cases.test.json)
    uv run python scripts/generate_eval.py --test

    # Force fresh start (delete any existing partial)
    uv run python scripts/generate_eval.py --reset

    # Custom seed for reproducibility (default 42)
    uv run python scripts/generate_eval.py --seed 7
"""

# Model history for Phase A.3:
# - Attempt 1: gemini-2.5-flash (20 RPD limit hit)
# - Attempt 2: gemini-2.5-flash-lite (project quota exhausted)
# - Attempt 3: gemini-2.0-flash-lite (model deprecated for new accounts)
# - Final: gemini-2.5-flash-lite with billing enabled (current)

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import psycopg
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "eval_cases.json"
TEST_OUTPUT = PROJECT_ROOT / "data" / "eval_cases.test.json"

console = Console()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

INTENTS = ("faq", "account_query", "escalate")
DIFFICULTIES = ("easy", "medium", "hard")
LANGUAGES = ("en", "id")
TONES = ("professional", "empathetic", "informational", "apologetic")
TOOL_NAMES = (
    "search_faq",
    "lookup_account",
    "list_transactions",
    "check_kyc_status",
    "escalate_to_human",
)


# ---------------------------------------------------------------------------
# Batch specifications
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BatchSpec:
    scenario: str
    scenario_desc: str
    count: int
    en: int
    id_count: int  # 'id' is a builtin
    easy: int
    medium: int
    hard: int
    faq: int
    account_query: int
    escalate: int
    multi_turn: bool


FULL_BATCHES: list[BatchSpec] = [
    BatchSpec(
        scenario="new_user",
        scenario_desc=(
            "A new user — just signed up, or considering signing up — asking how "
            "to use the platform, what account types exist, basic getting-started "
            "questions, registration steps, demo vs live"
        ),
        count=10, en=5, id_count=5,
        easy=7, medium=2, hard=1,
        faq=8, account_query=2, escalate=0,
        multi_turn=False,
    ),
    BatchSpec(
        scenario="account_issues",
        scenario_desc=(
            "User reporting problems with their existing account: suspended, "
            "locked, can't log in, missing balance, unauthorized activity, "
            "profile update issues"
        ),
        count=15, en=7, id_count=8,
        easy=9, medium=4, hard=2,
        faq=2, account_query=8, escalate=5,
        multi_turn=False,
    ),
    BatchSpec(
        scenario="trading_questions",
        scenario_desc=(
            "Questions about how trading works on the platform: order types "
            "(market/limit/stop), leverage, margin calls, spreads, swaps, "
            "scalping rules, expert advisors, hedging, position management"
        ),
        count=15, en=8, id_count=7,
        easy=9, medium=5, hard=1,
        faq=8, account_query=6, escalate=1,
        multi_turn=False,
    ),
    BatchSpec(
        scenario="withdrawal_deposit",
        scenario_desc=(
            "Questions about depositing or withdrawing funds: methods "
            "(bank/crypto/e-wallet), fees, processing times, minimums, why a "
            "transaction is pending or failed, currency conversion"
        ),
        count=15, en=8, id_count=7,
        easy=9, medium=5, hard=1,
        faq=6, account_query=7, escalate=2,
        multi_turn=False,
    ),
    BatchSpec(
        scenario="kyc_verification",
        scenario_desc=(
            "Identity verification (KYC) questions: required documents, "
            "submission status, why was it rejected, how to resubmit, "
            "verification timelines"
        ),
        count=10, en=5, id_count=5,
        easy=6, medium=3, hard=1,
        faq=1, account_query=7, escalate=2,
        multi_turn=False,
    ),
    BatchSpec(
        scenario="technical_platform",
        scenario_desc=(
            "Technical issues with the trading platform: MT4/MT5 won't connect, "
            "mobile app crashes, charts not loading, indicators missing, EA "
            "installation, password reset, login problems"
        ),
        count=10, en=5, id_count=5,
        easy=7, medium=2, hard=1,
        faq=8, account_query=1, escalate=1,
        multi_turn=False,
    ),
    BatchSpec(
        scenario="complaints",
        scenario_desc=(
            "User expressing dissatisfaction or filing a complaint: bad service, "
            "lost money, withdrawal disputes, alleged unfair treatment, "
            "demanding refund or compensation"
        ),
        count=10, en=5, id_count=5,
        easy=6, medium=3, hard=1,
        faq=1, account_query=3, escalate=6,
        multi_turn=False,
    ),
    BatchSpec(
        scenario="multi_turn",
        scenario_desc=(
            "A continuing support conversation where the current user_query "
            "references something from earlier in the dialogue. Tests context "
            "retention. Each case has 1-2 prior user-agent exchange pairs "
            "(2-4 turns total)."
        ),
        count=15, en=8, id_count=7,
        easy=7, medium=5, hard=3,
        faq=6, account_query=6, escalate=3,
        multi_turn=True,
    ),
]


TEST_BATCHES: list[BatchSpec] = [
    BatchSpec(
        scenario="new_user",
        scenario_desc=FULL_BATCHES[0].scenario_desc,
        count=5, en=3, id_count=2,
        easy=4, medium=1, hard=0,
        faq=4, account_query=1, escalate=0,
        multi_turn=False,
    ),
]


# ---------------------------------------------------------------------------
# Pydantic schemas (Gemini output)
# ---------------------------------------------------------------------------


class HistoryTurn(BaseModel):
    role: Literal["user", "agent"]
    message: str


class ExpectedBehavior(BaseModel):
    intent_match: Literal["faq", "account_query", "escalate"]
    should_use_tools: list[
        Literal[
            "search_faq",
            "lookup_account",
            "list_transactions",
            "check_kyc_status",
            "escalate_to_human",
        ]
    ]
    should_mention: list[str]
    should_not_mention: list[str]
    tone: Literal["professional", "empathetic", "informational", "apologetic"]
    should_escalate: bool


class GeneratedCaseSingle(BaseModel):
    user_query: str
    language: Literal["en", "id"]
    difficulty: Literal["easy", "medium", "hard"]
    expected_behavior: ExpectedBehavior
    tags: list[str]


class GeneratedCaseMulti(BaseModel):
    history: list[HistoryTurn]
    user_query: str
    language: Literal["en", "id"]
    difficulty: Literal["easy", "medium", "hard"]
    expected_behavior: ExpectedBehavior
    tags: list[str]


# ---------------------------------------------------------------------------
# Pre-fetch user_id pools from Postgres
# ---------------------------------------------------------------------------

USER_ID_QUERIES: dict[str, str] = {
    "suspended_users": (
        "SELECT user_id FROM accounts WHERE status = 'suspended' LIMIT 30"
    ),
    "kyc_pending_users": (
        "SELECT a.user_id FROM accounts a "
        "JOIN kyc_statuses k ON k.account_id = a.id "
        "WHERE k.status = 'pending' LIMIT 30"
    ),
    "kyc_rejected_users": (
        "SELECT a.user_id FROM accounts a "
        "JOIN kyc_statuses k ON k.account_id = a.id "
        "WHERE k.status = 'rejected' LIMIT 30"
    ),
    "pending_txn_users": (
        "SELECT DISTINCT a.user_id FROM accounts a "
        "JOIN transactions t ON t.account_id = a.id "
        "WHERE t.status = 'pending' LIMIT 30"
    ),
    "failed_txn_users": (
        "SELECT DISTINCT a.user_id FROM accounts a "
        "JOIN transactions t ON t.account_id = a.id "
        "WHERE t.status = 'failed' LIMIT 30"
    ),
    "general_active_users": (
        "SELECT user_id FROM accounts WHERE status = 'active' LIMIT 50"
    ),
}


SCENARIO_TO_POOLS: dict[str, list[str]] = {
    "account_issues": ["suspended_users", "general_active_users"],
    "kyc_verification": ["kyc_rejected_users", "kyc_pending_users"],
    "withdrawal_deposit": ["pending_txn_users", "failed_txn_users", "general_active_users"],
    "trading_questions": ["general_active_users"],
    "new_user": ["general_active_users"],
    "technical_platform": ["general_active_users"],
    "complaints": ["general_active_users", "suspended_users"],
    "multi_turn": ["general_active_users", "pending_txn_users"],
}


def prefetch_user_id_pools(db_url: str | None) -> dict[str, list[str]]:
    pools: dict[str, list[str]] = {key: [] for key in USER_ID_QUERIES}
    if not db_url:
        console.print("[yellow]No DATABASE_URL — pools empty; account_query cases will use random USR_IDs.[/yellow]")
        return pools
    try:
        # Disable prepared statements — required for Supabase pooler (port 6543).
        # See: https://www.psycopg.org/psycopg3/docs/advanced/prepare.html
        with psycopg.connect(db_url, prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                for key, sql in USER_ID_QUERIES.items():
                    cur.execute(sql)
                    pools[key] = [row[0] for row in cur.fetchall()]
    except psycopg.Error as e:
        console.print(f"[yellow]DB pre-fetch failed ({e}) — falling back to random USR_IDs.[/yellow]")
    return pools


def pick_user_id(scenario: str, pools: dict[str, list[str]]) -> str:
    for pool_name in SCENARIO_TO_POOLS.get(scenario, ["general_active_users"]):
        if pools.get(pool_name):
            return random.choice(pools[pool_name])
    return f"USR{random.randint(1, 1000):06d}"


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def build_prompt(batch: BatchSpec) -> str:
    multi_turn_block = ""
    if batch.multi_turn:
        multi_turn_block = (
            "\n\nMULTI-TURN: Each case must include a `history` field with "
            "1-2 prior user-agent exchange pairs (so 2-4 messages total: at "
            "minimum one user message and one agent reply before the current "
            "turn). The current `user_query` MUST reference something from "
            "the history — e.g., \"the one you mentioned\", \"about that "
            "withdrawal we just discussed\", \"can you explain it again\" — "
            "so the case actually tests context retention."
        )

    return (
        "You are creating evaluation test cases for Javva, an AI customer "
        "support agent for a forex/CFD trading platform that uses MetaTrader 4 "
        "and MetaTrader 5.\n\n"
        f"Generate {batch.count} test cases for scenario: **{batch.scenario}**\n\n"
        f"Scenario description: {batch.scenario_desc}.\n\n"
        "Required mix in this batch:\n"
        f"- Language: {batch.en} in English, {batch.id_count} in Indonesian (Bahasa Indonesia)\n"
        f"- Difficulty: {batch.easy} easy, {batch.medium} medium, {batch.hard} hard\n"
        f"- Intent: {batch.faq} faq, {batch.account_query} account_query, {batch.escalate} escalate\n\n"
        "Each case must have:\n"
        "- user_query: 1-3 sentences, realistic customer phrasing for this "
        "scenario. Vary openings — don't repeat the same starter.\n"
        "- language: \"en\" or \"id\" — must match the language of the "
        "user_query.\n"
        "- difficulty: \"easy\" | \"medium\" | \"hard\".\n"
        "- expected_behavior:\n"
        "    - intent_match: \"faq\" | \"account_query\" | \"escalate\"\n"
        "    - should_use_tools: list of tool names from "
        "{search_faq, lookup_account, list_transactions, check_kyc_status, "
        "escalate_to_human}. Empty list if none.\n"
        "    - should_mention: 2-4 specific phrases the agent's response "
        "should include. These MUST be CONCRETE assertions an evaluator can "
        "check against the agent's output, NOT response templates or "
        "greetings.\n"
        "        Good: \"minimum deposit is $10\", \"1 pip = 0.0001\", "
        "\"verification typically takes 24-48 hours\", "
        "\"requires a passport or national ID\".\n"
        "        Bad: \"Welcome to our platform\", \"we have many options\", "
        "\"getting started is easy\", \"you can begin by exploring\".\n"
        "    - should_not_mention: 1-3 phrases the agent should AVOID. "
        "These MUST be things that would be WRONG or HARMFUL to say. Do NOT "
        "include factually-correct statements here even if they sound "
        "cautionary.\n"
        "        Good: \"trading guarantees profit\", \"your funds are "
        "gone\", \"this is your fault\", \"USR000123 had the same issue\".\n"
        "        Bad: \"trading involves risk\" (this is TRUE and the agent "
        "SHOULD say it), \"verification can be slow\" (factual, not "
        "harmful).\n"
        "    - tone: \"professional\" | \"empathetic\" | \"informational\" | "
        "\"apologetic\"\n"
        "    - should_escalate: true if intent is \"escalate\", else false\n"
        "- tags: exactly 3 lowercase English kebab-case tags. Use HYPHENS "
        "not spaces. ALWAYS English even for Indonesian cases.\n"
        "    Tag examples: \"demo-account\", \"kyc-rejection\", \"mt5-setup\", "
        "\"pending-withdrawal\", \"context-retention\".\n\n"
        "For Indonesian cases: write NATIVELY in Bahasa Indonesia. Do NOT "
        "translate from English. Phrase questions as a native Bahasa Indonesia "
        "speaker would (e.g., \"Bagaimana cara...\" not \"Bagaimana untuk...\").\n\n"
        "Difficulty guide:\n"
        "- easy: clear question, single tool, obvious answer\n"
        "- medium: ambiguous phrasing, may need clarification, or 2-tool chain\n"
        "- hard: complex multi-step reasoning, edge cases, gray-area escalation\n\n"
        "Tone guide:\n"
        "- professional: factual, neutral, business-formal (default for FAQ)\n"
        "- empathetic: acknowledges user's frustration without admitting fault\n"
        "- informational: pure facts/instructions, no emotional layer\n"
        "- apologetic: acknowledges Javva's fault or service issue, offers to "
        "make it right (use ONLY when Javva is at fault)\n\n"
        "Avoid: repetitive phrasings, generic filler, marketing language, "
        "made-up facts, brand mentions other than Javva."
        f"{multi_turn_block}\n\n"
        f"Return a JSON array of exactly {batch.count} objects."
    )


# ---------------------------------------------------------------------------
# Gemini call (with tenacity retry, but NOT on ClientError — those should
# surface immediately so we can checkpoint cleanly on 429)
# ---------------------------------------------------------------------------


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    retry=retry_if_not_exception_type(
        (KeyboardInterrupt, SystemExit, genai_errors.ClientError)
    ),
    reraise=True,
)
def call_gemini(
    client: genai.Client,
    *,
    model: str,
    prompt: str,
    schema: type[BaseModel],
) -> list[BaseModel]:
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[schema],
            temperature=0.9,
        ),
    )
    parsed = response.parsed
    if not parsed:
        raise RuntimeError(
            f"Gemini returned no parseable structured output: {response.text[:300]!r}"
        )
    return parsed


# ---------------------------------------------------------------------------
# Case construction
# ---------------------------------------------------------------------------


def build_eval_case(
    *,
    generated: BaseModel,
    seq: int,
    scenario: str,
    pools: dict[str, list[str]],
    is_multi_turn: bool,
) -> dict:
    eb = generated.expected_behavior
    intent = eb.intent_match

    user_id: str | None = None
    if intent == "account_query":
        user_id = pick_user_id(scenario, pools)

    history: list[dict] = []
    if is_multi_turn and hasattr(generated, "history"):
        history = [{"role": h.role, "message": h.message} for h in generated.history]

    return {
        "id": f"eval-{seq:03d}",
        "scenario": scenario,
        "language": generated.language,
        "difficulty": generated.difficulty,
        "intent": intent,
        "user_query": generated.user_query.strip(),
        "context": {
            "user_id": user_id,
            "history": history,
        },
        "expected_behavior": {
            "intent_match": eb.intent_match,
            "should_use_tools": list(eb.should_use_tools),
            "should_mention": [s.strip() for s in eb.should_mention],
            "should_not_mention": [s.strip() for s in eb.should_not_mention],
            "tone": eb.tone,
            "should_escalate": eb.should_escalate,
        },
        "tags": [t.strip().lower() for t in generated.tags],
    }


# ---------------------------------------------------------------------------
# Checkpoint / resume
# ---------------------------------------------------------------------------


def partial_path_for(output_path: Path) -> Path:
    return output_path.with_suffix(".partial" + output_path.suffix)


def load_partial(
    partial_path: Path,
    expected_per_scenario: dict[str, int],
) -> tuple[list[dict], set[str]]:
    if not partial_path.exists():
        return [], set()
    raw = json.loads(partial_path.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for case in raw:
        counts[case["scenario"]] = counts.get(case["scenario"], 0) + 1
    done = {s for s, n in counts.items() if n >= expected_per_scenario.get(s, 0)}
    kept = [c for c in raw if c["scenario"] in done]
    return kept, done


def save_partial(partial_path: Path, cases: list[dict]) -> None:
    partial_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path.write_text(
        json.dumps(cases, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def show_pool_sizes(pools: dict[str, list[str]]) -> None:
    t = Table(title="user_id pools (pre-fetched from DB)")
    t.add_column("pool", style="cyan", no_wrap=True)
    t.add_column("size", style="green", justify="right")
    for name, ids in pools.items():
        t.add_row(name, str(len(ids)))
    console.print(t)


def show_case_summary(cases: list[dict]) -> None:
    by_scenario: dict[str, int] = {}
    by_language: dict[str, int] = {}
    by_difficulty: dict[str, int] = {}
    by_intent: dict[str, int] = {}
    for c in cases:
        by_scenario[c["scenario"]] = by_scenario.get(c["scenario"], 0) + 1
        by_language[c["language"]] = by_language.get(c["language"], 0) + 1
        by_difficulty[c["difficulty"]] = by_difficulty.get(c["difficulty"], 0) + 1
        by_intent[c["intent"]] = by_intent.get(c["intent"], 0) + 1

    console.print(f"[bold]Total cases:[/bold] {len(cases)}\n")

    for label, dist in [
        ("by scenario", by_scenario),
        ("by language", by_language),
        ("by difficulty", by_difficulty),
        ("by intent", by_intent),
    ]:
        console.print(f"[bold cyan]{label}[/bold cyan]")
        for k, v in sorted(dist.items(), key=lambda kv: -kv[1]):
            console.print(f"  {k:24} {v}")
        console.print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate eval cases using Gemini.")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Smoke test: 5 cases (new_user, mixed lang) -> eval_cases.test.json",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete any existing partial/final and start fresh.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default 42)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"Output path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    if not settings.gemini_api_key:
        console.print("[red]ERROR: GEMINI_API_KEY is not set in .env[/red]")
        return 1

    random.seed(args.seed)

    batches = TEST_BATCHES if args.test else FULL_BATCHES
    output_path = args.out or (TEST_OUTPUT if args.test else DEFAULT_OUTPUT)
    partial_path = partial_path_for(output_path)
    expected_per_scenario = {b.scenario: b.count for b in batches}

    if args.reset:
        partial_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)

    console.rule("[bold]TEST MODE" if args.test else "[bold]FULL RUN")
    console.print(f"Model: [cyan]{settings.gemini_default_model}[/cyan]")
    console.print(f"Batches: [cyan]{len(batches)}[/cyan]   Total target: [cyan]{sum(b.count for b in batches)}[/cyan]")
    console.print(f"Output: [dim]{output_path}[/dim]")
    console.print(f"Partial: [dim]{partial_path}[/dim]\n")

    pools = prefetch_user_id_pools(settings.database_url)
    show_pool_sizes(pools)
    console.print()

    existing_cases, done_scenarios = load_partial(partial_path, expected_per_scenario)
    if existing_cases:
        console.print(
            f"[yellow]Resuming:[/yellow] "
            f"{len(done_scenarios)}/{len(batches)} scenarios already complete, "
            f"{len(existing_cases)} cases preserved"
        )

    remaining = [b for b in batches if b.scenario not in done_scenarios]
    all_cases: list[dict] = list(existing_cases)

    if not remaining:
        console.print("[green]Nothing to do — all scenarios already complete.[/green]")
        if not output_path.exists():
            output_path.write_text(
                json.dumps(all_cases, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            partial_path.unlink(missing_ok=True)
        show_case_summary(all_cases)
        return 0

    save_partial(partial_path, all_cases)
    client = genai.Client(api_key=settings.gemini_api_key)

    completed_this_run = 0

    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )

    try:
        with progress:
            task = progress.add_task("starting...", total=len(remaining))
            for i, batch in enumerate(remaining):
                progress.update(task, description=f"[{batch.scenario}] generating ({batch.count})")

                schema = GeneratedCaseMulti if batch.multi_turn else GeneratedCaseSingle
                generated = call_gemini(
                    client,
                    model=settings.gemini_default_model,
                    prompt=build_prompt(batch),
                    schema=schema,
                )
                console.log(
                    f"[{batch.scenario}] -> {len(generated)} cases "
                    f"(requested {batch.count})"
                )

                for gen in generated:
                    all_cases.append(
                        build_eval_case(
                            generated=gen,
                            seq=len(all_cases) + 1,
                            scenario=batch.scenario,
                            pools=pools,
                            is_multi_turn=batch.multi_turn,
                        )
                    )

                save_partial(partial_path, all_cases)
                completed_this_run += 1
                progress.update(task, advance=1)
                # Rate limit: free-tier flash-lite is ~15 RPM. Sleep between
                # batches to stay safely under that ceiling.
                if i < len(remaining) - 1:
                    time.sleep(5)
    except genai_errors.ClientError as e:
        if getattr(e, "code", None) == 429:
            done_total = len(done_scenarios) + completed_this_run
            console.rule("[yellow]rate limited (429)")
            console.print(
                f"[yellow]Quota exhausted. {done_total}/{len(batches)} scenarios complete.[/yellow]"
            )
            console.print(f"[yellow]Partial state preserved: {partial_path}[/yellow]")
            console.print(
                "[yellow]Resume with the same command after the daily quota resets.[/yellow]"
            )
            return 1
        raise
    except KeyboardInterrupt:
        console.rule("[yellow]interrupted")
        console.print(f"[yellow]Partial state preserved: {partial_path}[/yellow]")
        return 130

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(all_cases, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    partial_path.unlink(missing_ok=True)

    console.rule("[bold green]done")
    console.print(f"Wrote [bold]{len(all_cases)}[/bold] cases to [cyan]{output_path}[/cyan]\n")
    show_case_summary(all_cases)
    return 0


if __name__ == "__main__":
    sys.exit(main())
