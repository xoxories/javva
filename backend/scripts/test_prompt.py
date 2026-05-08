"""Validate the Javva system prompt structure.

Loads JAVVA_SYSTEM_PROMPT, runs validate_prompt(), reports stats and any
missing sections, and prints a head-of-prompt preview so it's easy to
eyeball after edits.

Usage:
    uv run python scripts/test_prompt.py
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from app.agent import JAVVA_SYSTEM_PROMPT, TONE_GUIDELINES, validate_prompt


console = Console()


def main() -> int:
    console.rule("[bold]Javva system prompt — validation")

    result = validate_prompt()
    # rough token estimate: ~1 token per 4 chars for English text
    est_tokens = result["length_chars"] // 4

    console.print(f"length_chars:    [cyan]{result['length_chars']}[/cyan]")
    console.print(f"length_words:    [cyan]{result['length_words']}[/cyan]")
    console.print(f"~tokens (est.):  [cyan]{est_tokens}[/cyan]")
    console.print()

    if result["valid"]:
        console.print(f"[green]Structural check OK — {len(result['sections_found'])} sections present[/green]")
    else:
        console.print(
            f"[red]Structural check FAILED — missing {len(result['sections_missing'])} sections[/red]"
        )

    sections_table = Table(title="sections", show_lines=False)
    sections_table.add_column("section", style="cyan")
    sections_table.add_column("status", no_wrap=True)
    for s in result["sections_found"]:
        sections_table.add_row(s, "[green]found[/green]")
    for s in result["sections_missing"]:
        sections_table.add_row(s, "[red]MISSING[/red]")
    console.print(sections_table)

    console.rule("[bold]Tone guidelines")
    tones_table = Table(show_lines=False)
    tones_table.add_column("tone", style="cyan", no_wrap=True)
    tones_table.add_column("description", overflow="fold")
    for tone, desc in TONE_GUIDELINES.items():
        tones_table.add_row(tone, desc)
    console.print(tones_table)

    console.rule("[bold]Prompt preview (first 500 chars)")
    console.print(f"[dim]{JAVVA_SYSTEM_PROMPT[:500]}...[/dim]")

    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
