"""Create accounts, transactions, and kyc_statuses tables in the configured Postgres.

Idempotent: safe to re-run. Uses CREATE TABLE / INDEX IF NOT EXISTS throughout,
so re-running is a no-op when the schema already matches.

Usage:
    # Create tables and indexes (no-op if everything already exists)
    uv run python scripts/migrate_db.py

    # Drop existing tables (CASCADE) and recreate from scratch
    uv run python scripts/migrate_db.py --drop
"""

from __future__ import annotations

import argparse
import sys

import psycopg
from rich.console import Console
from rich.table import Table

from app.config import settings

console = Console()


ACCOUNTS_DDL = """
CREATE TABLE IF NOT EXISTS accounts (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       VARCHAR(20)    UNIQUE NOT NULL,
    email         VARCHAR(255)   UNIQUE NOT NULL,
    full_name     VARCHAR(255)   NOT NULL,
    country_code  CHAR(2)        NOT NULL,
    account_type  VARCHAR(20)    NOT NULL,
    base_currency CHAR(3)        NOT NULL,
    balance       DECIMAL(15, 2) NOT NULL DEFAULT 0,
    leverage      INTEGER        NOT NULL,
    status        VARCHAR(20)    NOT NULL DEFAULT 'active',
    created_at    TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);
"""

TRANSACTIONS_DDL = """
CREATE TABLE IF NOT EXISTS transactions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id   UUID           NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    type         VARCHAR(20)    NOT NULL,
    amount       DECIMAL(15, 2) NOT NULL,
    currency     CHAR(3)        NOT NULL,
    status       VARCHAR(20)    NOT NULL,
    method       VARCHAR(50),
    reference    VARCHAR(100),
    created_at   TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
"""

KYC_STATUSES_DDL = """
CREATE TABLE IF NOT EXISTS kyc_statuses (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id       UUID         UNIQUE NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    status           VARCHAR(20)  NOT NULL,
    document_type    VARCHAR(50),
    submitted_at     TIMESTAMPTZ,
    verified_at      TIMESTAMPTZ,
    rejection_reason TEXT
);
"""

INDEXES = [
    # accounts (user_id and email already indexed via UNIQUE)
    "CREATE INDEX IF NOT EXISTS idx_accounts_country_code ON accounts (country_code);",
    "CREATE INDEX IF NOT EXISTS idx_accounts_status       ON accounts (status);",
    "CREATE INDEX IF NOT EXISTS idx_accounts_created_at   ON accounts (created_at);",
    # transactions (PG does not auto-index FK columns)
    "CREATE INDEX IF NOT EXISTS idx_transactions_account_id           ON transactions (account_id);",
    "CREATE INDEX IF NOT EXISTS idx_transactions_status               ON transactions (status);",
    "CREATE INDEX IF NOT EXISTS idx_transactions_created_at_desc      ON transactions (created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_transactions_account_created_desc ON transactions (account_id, created_at DESC);",
    # kyc_statuses (account_id already indexed via UNIQUE)
    "CREATE INDEX IF NOT EXISTS idx_kyc_statuses_status ON kyc_statuses (status);",
]

DROP_SQL = "DROP TABLE IF EXISTS transactions, kyc_statuses, accounts CASCADE;"

TABLES = ("accounts", "transactions", "kyc_statuses")


def show_schema(cur) -> None:
    cur.execute(
        """
        SELECT table_name, column_name, data_type, character_maximum_length,
               numeric_precision, numeric_scale, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ANY(%s)
        ORDER BY table_name, ordinal_position;
        """,
        (list(TABLES),),
    )
    rows = cur.fetchall()

    by_table: dict[str, list[tuple]] = {t: [] for t in TABLES}
    for r in rows:
        by_table[r[0]].append(r)

    for tname in TABLES:
        t = Table(title=f"public.{tname}")
        t.add_column("column", style="cyan", no_wrap=True)
        t.add_column("type", style="green", no_wrap=True)
        t.add_column("null", style="yellow")
        t.add_column("default", style="dim", overflow="fold")
        for r in by_table[tname]:
            _, col, dtype, char_max, num_prec, num_scale, nullable, default = r
            type_str = dtype
            if char_max:
                type_str = f"{dtype}({char_max})"
            elif dtype == "numeric" and num_prec is not None:
                type_str = f"numeric({num_prec},{num_scale})"
            t.add_row(
                col,
                type_str,
                "YES" if nullable == "YES" else "no",
                str(default) if default else "",
            )
        console.print(t)
        console.print()

    cur.execute(
        """
        SELECT tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = ANY(%s)
        ORDER BY tablename, indexname;
        """,
        (list(TABLES),),
    )
    idx_rows = cur.fetchall()

    idx_table = Table(title="indexes")
    idx_table.add_column("table", style="cyan", no_wrap=True)
    idx_table.add_column("index", style="green", no_wrap=True)
    idx_table.add_column("definition", style="dim", overflow="fold")
    for tablename, indexname, indexdef in idx_rows:
        idx_table.add_row(tablename, indexname, indexdef)
    console.print(idx_table)


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Javva Postgres schema.")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop existing tables (CASCADE) before recreating.",
    )
    args = parser.parse_args()

    if not settings.database_url:
        console.print("[red]ERROR: DATABASE_URL is not set in .env[/red]")
        return 1

    console.rule("[bold]migrate_db")
    console.print(f"DB host: [dim]{settings.database_url.split('@')[-1].split('/')[0]}[/dim]")

    try:
        # Disable prepared statements — required for Supabase pooler (port 6543).
        # See: https://www.psycopg.org/psycopg3/docs/advanced/prepare.html
        with psycopg.connect(settings.database_url, prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                if args.drop:
                    console.print("[yellow]DROP TABLE ... CASCADE[/yellow]")
                    cur.execute(DROP_SQL)

                console.print("[blue]Creating tables ...[/blue]")
                cur.execute(ACCOUNTS_DDL)
                cur.execute(TRANSACTIONS_DDL)
                cur.execute(KYC_STATUSES_DDL)

                console.print("[blue]Creating indexes ...[/blue]")
                for stmt in INDEXES:
                    cur.execute(stmt)

                conn.commit()
                console.print("[green]Migration complete.[/green]\n")

                console.rule("[bold]actual schema in Postgres")
                show_schema(cur)
    except psycopg.Error as e:
        console.print(f"[red]DB ERROR: {e}[/red]")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
