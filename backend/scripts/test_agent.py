"""Interactive smoke test for the Javva agent — 8 scenarios.

Exercises the chat() function end-to-end against real Gemini + Postgres
+ Qdrant. Last scenario does multi-turn (turn 1's message_history feeds
turn 2) to verify context retention.

Usage:
    uv run python scripts/test_agent.py
"""

from __future__ import annotations

import asyncio
import time

from rich.console import Console
from rich.panel import Panel

from app.agent import ChatResponse, chat


console = Console()


def render(label: str, user: str, resp: ChatResponse) -> None:
    body = (
        f"[bold]User:[/bold] {user}\n\n"
        f"[bold]Reply:[/bold]\n{resp.reply}\n\n"
        f"[dim]tools_called: {resp.tools_called}\n"
        f"duration: {resp.duration_ms} ms   "
        f"tokens: in={resp.usage.get('input_tokens', 0)} "
        f"out={resp.usage.get('output_tokens', 0)} "
        f"total={resp.usage.get('total_tokens', 0)}"
    )
    if resp.error:
        body += f"\n[red]error: {resp.error}[/red]"
    body += "[/dim]"
    console.print(Panel(body, title=label, title_align="left", expand=False))
    console.print()


_last_chat_time: float = 0.0


async def throttled_chat(
    user_msg: str, message_history: list | None = None
) -> ChatResponse:
    """chat() with a minimum 7s gap from the previous call.

    gemini-2.5-flash has a low RPM ceiling on the lower paid tiers.
    Burst-style testing trips it; production HTTP traffic is naturally
    paced and doesn't need this throttle.
    """
    global _last_chat_time
    if _last_chat_time > 0:
        elapsed = time.time() - _last_chat_time
        if elapsed < 7:
            wait_s = 7 - elapsed
            console.print(f"[dim]waiting {wait_s:.1f}s for RPM bucket...[/dim]")
            await asyncio.sleep(wait_s)
    if message_history is None:
        resp = await chat(user_msg)
    else:
        resp = await chat(user_msg, message_history=message_history)
    _last_chat_time = time.time()
    return resp


async def main() -> None:
    overall_start = time.time()

    # 1. General FAQ (English)
    render(
        "1. General FAQ (English)",
        "How does leverage work in forex?",
        await throttled_chat("How does leverage work in forex?"),
    )

    # 2. General FAQ (Indonesian)
    render(
        "2. General FAQ (Indonesian)",
        "Apa itu KYC?",
        await throttled_chat("Apa itu KYC?"),
    )

    # 3. Account query with user_id
    render(
        "3. Account query — USR000001 balance",
        "What's my balance? My ID is USR000001.",
        await throttled_chat("What's my balance? My ID is USR000001."),
    )

    # 4. Transaction query
    render(
        "4. Transaction query — recent withdrawals",
        "Show me my recent withdrawals, USR000001.",
        await throttled_chat("Show me my recent withdrawals, USR000001."),
    )

    # 5. KYC status check
    render(
        "5. KYC status — restricted withdrawal",
        "Why can't I withdraw? USR000001",
        await throttled_chat("Why can't I withdraw? USR000001"),
    )

    # 6. Escalation
    render(
        "6. Escalation — third failure + manager request",
        "This is the third time my withdrawal failed! Get me a manager!",
        await throttled_chat("This is the third time my withdrawal failed! Get me a manager!"),
    )

    # 7. Trading advice — should refuse
    render(
        "7. Trading advice — should refuse",
        "Should I buy EUR/USD now?",
        await throttled_chat("Should I buy EUR/USD now?"),
    )

    # 8. Multi-turn conversation
    console.rule("[bold]8. Multi-turn (turn 1 then turn 2 with context)")
    turn1_user = "I want to know about deposits"
    turn1 = await throttled_chat(turn1_user)
    render("    Turn 1", turn1_user, turn1)

    turn2_user = "What about for IDR currency specifically?"
    turn2 = await throttled_chat(turn2_user, message_history=turn1.message_history)
    render("    Turn 2 (with context)", turn2_user, turn2)

    # 9. Ambiguous user_id — no USR prefix, agent should ask for valid format
    render(
        "9. Ambiguous user_id (no USR prefix)",
        "Check my balance, ID 123456",
        await throttled_chat("Check my balance, ID 123456"),
    )

    # 10. Multi-tool single turn — should call lookup_account AND list_transactions
    render(
        "10. Multi-tool single turn",
        "USR000001 — what's my balance and recent transactions?",
        await throttled_chat(
            "USR000001 — what's my balance and recent transactions?"
        ),
    )

    # 11. Suspended account — empathetic + escalation suggestion
    render(
        "11. Suspended account — USR000453",
        "Why can't I trade? My ID is USR000453",
        await throttled_chat("Why can't I trade? My ID is USR000453"),
    )

    # 12. KYC issue — deposit failure routed to KYC check
    render(
        "12. KYC issue — deposit failure",
        "My deposit isn't going through. USR000050",
        await throttled_chat("My deposit isn't going through. USR000050"),
    )

    # 13. Hostile user — apologetic + escalation, no defensiveness
    render(
        "13. Hostile user — escalation",
        "This platform is GARBAGE! I'm losing thousands! "
        "You're SCAMMERS! Get me your manager NOW!",
        await throttled_chat(
            "This platform is GARBAGE! I'm losing thousands! "
            "You're SCAMMERS! Get me your manager NOW!"
        ),
    )

    # 14. Off-topic — polite scope redirect, no tools called
    render(
        "14. Off-topic — Python script request",
        "Can you write me a Python script to calculate Fibonacci?",
        await throttled_chat(
            "Can you write me a Python script to calculate Fibonacci?"
        ),
    )

    overall = int((time.time() - overall_start) * 1000)
    console.print(f"[bold]Total wall time:[/bold] {overall} ms across 15 turns")


if __name__ == "__main__":
    asyncio.run(main())
