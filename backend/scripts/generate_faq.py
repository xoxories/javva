"""Generate FAQ seed dataset using Gemini.

Generates ~204 forex/CFD trading FAQ entries across 6 categories in English
and Indonesian, saved as JSON for use as Javva's RAG seed corpus.

----------------------------------------------------------------------
MODEL LIMITS — Gemini API free-tier RPD (requests per day, approximate)
----------------------------------------------------------------------
    gemini-2.5-pro          ~25     highest quality, very tight quota
    gemini-2.5-flash        ~20     balanced quality, surprisingly tight
    gemini-2.5-flash-lite  ~1000    dev default; fits a full run with room
    gemini-2.0-flash        ~200
    gemini-2.0-flash-lite   ~200

The model is read from settings.gemini_default_model (.env).
Default for development: gemini-2.5-flash-lite — single-call mode below
needs only 12 calls per full run, comfortably within quota.
For higher-quality reruns, set GEMINI_DEFAULT_MODEL=gemini-2.5-flash and
schedule the run shortly after the daily quota reset (~midnight Pacific).

----------------------------------------------------------------------
CHECKPOINT BEHAVIOUR
----------------------------------------------------------------------
After each (category, language) combo finishes, all entries-so-far are
written to <out>.partial.json. On rerun, combos already represented in
that partial file are detected and skipped — so a 429, network blip, or
Ctrl+C never costs more than the in-flight combo. On a clean full run,
<out>.partial.json is renamed to <out> and removed.

Usage:
    # Full generation (12 API calls -> 204 entries -> data/faq_seed.json)
    uv run python scripts/generate_faq.py

    # Smoke test (1 API call -> 10 entries -> data/faq_seed.test.json)
    uv run python scripts/generate_faq.py --test

    # Multi-call mode (24 calls; better variety, only on high-RPD models)
    uv run python scripts/generate_faq.py --multi-call

    # Custom output path / per-combo count
    uv run python scripts/generate_faq.py --out data/my_faqs.json --per-combo 25
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings


CATEGORIES: dict[str, str] = {
    "forex_basics": (
        "fundamental forex concepts: currency pairs, pips, lots, leverage, "
        "margin, spread, swap/rollover, market hours, basic terminology a "
        "beginner needs to understand"
    ),
    "account_management": (
        "opening and managing trading accounts: account types (demo, "
        "standard, cent, ECN), profile updates, password/email changes, "
        "account closure, verification status"
    ),
    "deposits_withdrawals": (
        "funding and withdrawing: payment methods (bank transfer, e-wallet, "
        "crypto), processing times, fees, minimums, currency conversion, "
        "refund policies, withdrawal limits"
    ),
    "kyc_security": (
        "identity verification (KYC), required documents, two-factor "
        "authentication, account security, password reset, suspicious "
        "activity, regulatory compliance"
    ),
    "trading_mechanics": (
        "how to place and manage trades: market/limit/stop orders, "
        "stop-loss and take-profit, slippage, requotes, partial fills, "
        "hedging, scalping rules, expiration of pending orders"
    ),
    "platform_features": (
        "platform tools: MetaTrader 4 and MetaTrader 5 access, mobile app, "
        "web terminal, charts and indicators, expert advisors (EAs), "
        "copy trading, trading signals, VPS"
    ),
}

LANGUAGES: dict[str, str] = {
    "en": "English",
    "id": "Indonesian (Bahasa Indonesia)",
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "faq_seed.json"
TEST_OUTPUT = PROJECT_ROOT / "data" / "faq_seed.test.json"

console = Console()


class GeneratedFaq(BaseModel):
    question: str
    answer: str
    tags: list[str]


class FaqEntry(BaseModel):
    id: str
    category: str
    language: str
    question: str
    answer: str
    tags: list[str]


def partial_path_for(output_path: Path) -> Path:
    return output_path.with_suffix(".partial" + output_path.suffix)


def load_partial(
    partial_path: Path, per_combo: int
) -> tuple[list[FaqEntry], set[tuple[str, str]]]:
    """Load partial state. Returns (entries from complete combos, done combo keys).

    Combos with fewer than `per_combo` entries are treated as incomplete and
    discarded — only fully-completed combos carry forward.
    """
    if not partial_path.exists():
        return [], set()

    raw = json.loads(partial_path.read_text(encoding="utf-8"))
    entries = [FaqEntry.model_validate(e) for e in raw]

    counts: dict[tuple[str, str], int] = {}
    for e in entries:
        key = (e.category, e.language)
        counts[key] = counts.get(key, 0) + 1

    done = {key for key, n in counts.items() if n >= per_combo}
    kept = [e for e in entries if (e.category, e.language) in done]
    return kept, done


def save_partial(partial_path: Path, entries: list[FaqEntry]) -> None:
    partial_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path.write_text(
        json.dumps([e.model_dump() for e in entries], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def build_prompt(
    *,
    category: str,
    category_description: str,
    language_code: str,
    language_name: str,
    n: int,
    avoid_questions: list[str] | None = None,
) -> str:
    lang_directive = ""
    if language_code == "id":
        lang_directive = (
            "\n\nWrite each question and answer NATIVELY in Bahasa Indonesia, "
            "in natural conversational tone — do NOT mentally translate from "
            "English. Phrase things the way a Bahasa Indonesia speaker would."
        )

    avoid_block = ""
    if avoid_questions:
        avoid_lines = "\n".join(f'  - "{q}"' for q in avoid_questions)
        avoid_block = (
            "\n\nThe following questions have ALREADY been generated for this "
            "category. Do NOT overlap with their topics — pick different "
            "angles:\n" + avoid_lines
        )

    return (
        "You are creating FAQ content for Javva, an online forex/CFD trading "
        "platform that uses MetaTrader 4 and MetaTrader 5.\n\n"
        f"Generate {n} unique FAQs for the category **{category}** in "
        f"{language_name}.\n\n"
        f"Category context: {category_description}.\n\n"
        "Each entry must be:\n"
        "- \"question\": natural phrasing a real trader would ask. Vary "
        "openings — don't all start with the same word. 1 sentence.\n"
        "- \"answer\": 2 to 4 sentences. Concrete, accurate, beginner-"
        "friendly. Mention realistic specifics where they help (EUR/USD, "
        "1 pip = 0.0001, MT5, 100:1 leverage, typical spreads, tier-1 banks).\n"
        "- \"tags\": EXACTLY 3 lowercase English tags (single words or "
        "kebab-case like \"currency-pairs\"). Use English tags regardless "
        "of question language so the dataset is consistently indexable."
        f"{lang_directive}"
        f"{avoid_block}\n\n"
        "Avoid: repetitive openings, generic filler (\"It is important "
        "to...\"), marketing language, made-up or inaccurate facts.\n\n"
        f"Return a JSON array of exactly {n} objects."
    )


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
) -> list[GeneratedFaq]:
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[GeneratedFaq],
            temperature=0.9,
        ),
    )
    parsed = response.parsed
    if not parsed:
        raise RuntimeError(
            f"Gemini returned no parseable structured output: {response.text[:300]!r}"
        )
    return parsed


def generate_combo(
    client: genai.Client,
    *,
    category: str,
    category_description: str,
    language_code: str,
    language_name: str,
    target_count: int,
    model: str,
    multi_call: bool,
    progress: Progress,
    task_id,
) -> list[GeneratedFaq]:
    if not multi_call:
        progress.update(
            task_id,
            description=f"[{category}:{language_code}] single call ({target_count})",
        )
        batch = call_gemini(
            client,
            model=model,
            prompt=build_prompt(
                category=category,
                category_description=category_description,
                language_code=language_code,
                language_name=language_name,
                n=target_count,
            ),
        )
        console.log(f"[{category}:{language_code}] → {len(batch)} entries")
        return list(batch)

    first_n = min(10, target_count)
    second_n = target_count - first_n

    progress.update(
        task_id,
        description=f"[{category}:{language_code}] call A ({first_n})",
    )
    batch_a = call_gemini(
        client,
        model=model,
        prompt=build_prompt(
            category=category,
            category_description=category_description,
            language_code=language_code,
            language_name=language_name,
            n=first_n,
        ),
    )
    console.log(f"[{category}:{language_code}] call A → {len(batch_a)} entries")

    if second_n <= 0:
        return list(batch_a)

    progress.update(
        task_id,
        description=f"[{category}:{language_code}] call B ({second_n})",
    )
    batch_b = call_gemini(
        client,
        model=model,
        prompt=build_prompt(
            category=category,
            category_description=category_description,
            language_code=language_code,
            language_name=language_name,
            n=second_n,
            avoid_questions=[faq.question for faq in batch_a],
        ),
    )
    console.log(f"[{category}:{language_code}] call B → {len(batch_b)} entries")

    return list(batch_a) + list(batch_b)


def write_summary(
    output_path: Path,
    entries: list[FaqEntry],
) -> None:
    console.print(
        f"Wrote [bold]{len(entries)}[/bold] entries to [cyan]{output_path}[/cyan]\n"
    )
    console.print("[bold]Breakdown:[/bold]")
    for category in CATEGORIES:
        for lang in LANGUAGES:
            count = sum(
                1 for e in entries if e.category == category and e.language == lang
            )
            if count:
                console.print(f"  {category:24} {lang}  {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate FAQ seed dataset using Gemini.")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Smoke test: 10 entries (forex_basics, EN) -> faq_seed.test.json",
    )
    parser.add_argument(
        "--per-combo",
        type=int,
        default=17,
        help="Entries per (category, language) combo (default 17 -> 204 total)",
    )
    parser.add_argument(
        "--multi-call",
        action="store_true",
        help="Use 2 API calls per combo (10+7) for more variety. "
        "Only safe on high-RPD models — doubles call count.",
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

    model = settings.gemini_default_model
    client = genai.Client(api_key=settings.gemini_api_key)

    if args.test:
        combos: list[tuple[str, str]] = [("forex_basics", "en")]
        per_combo = 10
        output_path = args.out or TEST_OUTPUT
        console.rule("[bold]TEST MODE")
    else:
        combos = [(c, lang) for c in CATEGORIES for lang in LANGUAGES]
        per_combo = args.per_combo
        output_path = args.out or DEFAULT_OUTPUT
        console.rule("[bold]FULL RUN")

    partial_path = partial_path_for(output_path)
    existing_entries, done_combos = load_partial(partial_path, per_combo)

    counters: dict[str, int] = {c: 0 for c in CATEGORIES}
    for e in existing_entries:
        counters[e.category] += 1

    remaining = [(c, lang) for c, lang in combos if (c, lang) not in done_combos]
    all_entries: list[FaqEntry] = list(existing_entries)

    mode_desc = "multi-call (10+7)" if args.multi_call else "single-call"
    console.print(
        f"Model: [cyan]{model}[/cyan]   "
        f"Mode: [cyan]{mode_desc}[/cyan]   "
        f"Combos: [cyan]{len(combos)}[/cyan]   "
        f"Per combo: [cyan]{per_combo}[/cyan]   "
        f"Total target: [cyan]{len(combos) * per_combo}[/cyan]"
    )
    console.print(f"Output: [dim]{output_path}[/dim]")
    console.print(f"Partial: [dim]{partial_path}[/dim]")

    if existing_entries:
        console.print(
            f"[yellow]Resuming:[/yellow] "
            f"{len(done_combos)}/{len(combos)} combos already complete in partial file, "
            f"{len(remaining)} remaining"
        )

    if not remaining:
        console.print("[green]Nothing to do — all combos already complete.[/green]")
        if not output_path.exists():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(
                    [e.model_dump() for e in all_entries],
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            if partial_path.exists():
                partial_path.unlink()
        write_summary(output_path, all_entries)
        return 0

    save_partial(partial_path, all_entries)

    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )

    completed_this_run = 0

    try:
        with progress:
            task = progress.add_task("starting...", total=len(remaining))
            for category, lang in remaining:
                generated = generate_combo(
                    client,
                    category=category,
                    category_description=CATEGORIES[category],
                    language_code=lang,
                    language_name=LANGUAGES[lang],
                    target_count=per_combo,
                    model=model,
                    multi_call=args.multi_call,
                    progress=progress,
                    task_id=task,
                )
                for faq in generated:
                    counters[category] += 1
                    all_entries.append(
                        FaqEntry(
                            id=f"faq-{category}-{counters[category]}",
                            category=category,
                            language=lang,
                            question=faq.question.strip(),
                            answer=faq.answer.strip(),
                            tags=[t.strip().lower() for t in faq.tags],
                        )
                    )
                save_partial(partial_path, all_entries)
                completed_this_run += 1
                progress.update(task, advance=1)
    except genai_errors.ClientError as e:
        if getattr(e, "code", None) == 429:
            done_total = len(done_combos) + completed_this_run
            console.rule("[yellow]rate limited (429)")
            console.print(
                f"[yellow]Quota exhausted. {done_total}/{len(combos)} combos complete.[/yellow]"
            )
            console.print(f"[yellow]Partial state preserved: {partial_path}[/yellow]")
            console.print(
                "[yellow]Resume with the same command after the daily quota "
                "resets (~midnight Pacific Time).[/yellow]"
            )
            return 1
        raise
    except KeyboardInterrupt:
        console.rule("[yellow]interrupted")
        console.print(f"[yellow]Partial state preserved: {partial_path}[/yellow]")
        console.print("[yellow]Resume with the same command.[/yellow]")
        return 130

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            [e.model_dump() for e in all_entries],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    if partial_path.exists():
        partial_path.unlink()

    console.rule("[bold green]done")
    write_summary(output_path, all_entries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
