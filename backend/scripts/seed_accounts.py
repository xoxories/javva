"""Seed mock accounts, transactions, and KYC statuses into Postgres.

Generates 1000 (default) realistic-looking accounts using Faker, then for each
account a kyc_status row and a status-dependent number of transactions:

    active     5–30 transactions   (within last 180 days)
    inactive   3–15 transactions   (all before last_login_at)
    suspended  2–10 transactions   (all before a random suspension cutoff)

All inserts run in a single transaction; on any error the whole batch rolls
back. Reproducible by default (seeded random), pass --seed N to vary.

Usage:
    # Full seed: 1000 accounts (~13K transactions)
    uv run python scripts/seed_accounts.py

    # Smaller test set
    uv run python scripts/seed_accounts.py --count 50

    # Reset (TRUNCATE accounts CASCADE) before seeding — required when re-seeding
    uv run python scripts/seed_accounts.py --reset

    # Different random seed
    uv run python scripts/seed_accounts.py --seed 7

The migrate_db.py schema must already exist; this script does NOT create tables.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import psycopg
from faker import Faker
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from app.config import settings

console = Console()


# ---------------------------------------------------------------------------
# Distributions — exact-ratio, pre-sized lists shuffled per run
# ---------------------------------------------------------------------------

STATUS_PCT = {"active": 60, "inactive": 30, "suspended": 10}
ACCOUNT_TYPE_PCT = {"standard": 50, "cent": 30, "demo": 20}
LEVERAGE_PCT = {500: 50, 100: 30, 1000: 20}
KYC_STATUS_PCT = {"verified": 70, "pending": 20, "rejected": 5, "not_started": 5}
COUNTRY_PCT = {
    "ID": 40,
    "MY": 20,
    "SG": 10,
    "TH": 10,
    "VN": 10,
    "PH": 4,
    "BD": 3,
    "IN": 3,
}


# ---------------------------------------------------------------------------
# Currency by country — probabilistic, not pre-sized
# ---------------------------------------------------------------------------

CURRENCY_BY_COUNTRY: dict[str, list[tuple[str, float]]] = {
    "ID": [("IDR", 0.5), ("USD", 0.5)],
    "MY": [("MYR", 0.5), ("USD", 0.5)],
    "SG": [("SGD", 0.3), ("USD", 0.7)],
    "TH": [("THB", 0.5), ("USD", 0.5)],
    "VN": [("VND", 0.6), ("USD", 0.4)],
    # PH, BD, IN, etc. → USD only
}


# ---------------------------------------------------------------------------
# Faker locale routing
# ---------------------------------------------------------------------------

LOCALE_BY_COUNTRY: dict[str, str] = {
    "ID": "id_ID",
}
DEFAULT_LOCALE = "en_US"


# ---------------------------------------------------------------------------
# Transaction generation constants
# ---------------------------------------------------------------------------

DEPOSIT_METHODS = ["bank_transfer", "crypto", "ewallet"]
WITHDRAWAL_METHODS = ["bank_transfer", "crypto", "ewallet"]

TXN_COUNT_BY_STATUS = {
    "active": (5, 30),
    "inactive": (3, 15),
    "suspended": (2, 10),
}

REJECTION_REASONS = [
    "Document image quality is too low to verify identity.",
    "Document appears to be expired.",
    "Information on submitted document does not match account details.",
    "Document type submitted is not on our list of accepted IDs.",
    "Selfie does not match the photo on the submitted document.",
    "Document shows signs of tampering or alteration.",
    "Address on document does not match the address on file.",
    "Submitted document is partially obscured or unreadable.",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def distribute(pct_map: dict, total: int) -> list:
    """Build a shuffled list of `total` items, sized proportionally to pct_map.

    For total=1000 and clean percentages, ratios are exact. For other totals,
    proportional rounding may be off by 1-2; adjusted to hit exactly `total`
    by padding/popping the first bucket.
    """
    items: list = []
    for value, pct in pct_map.items():
        items.extend([value] * round(total * pct / 100))
    while len(items) > total:
        items.pop()
    while len(items) < total:
        items.append(next(iter(pct_map)))
    random.shuffle(items)
    return items


def random_dt_between(start: datetime, end: datetime) -> datetime:
    delta = end - start
    seconds = random.randint(0, max(1, int(delta.total_seconds())))
    return start + timedelta(seconds=seconds)


def pick_currency(country: str) -> str:
    spec = CURRENCY_BY_COUNTRY.get(country)
    if not spec:
        return "USD"
    options, weights = zip(*spec)
    return random.choices(options, weights=weights, k=1)[0]


def pick_balance(account_type: str) -> Decimal:
    if account_type == "demo":
        raw = random.uniform(5000, 50000)
    elif account_type == "cent":
        raw = random.uniform(0, 500)
    else:  # standard: 60% in 100-2000, 25% in 2000-5000, 15% in 5000-10000
        bucket = random.choices([0, 1, 2], weights=[60, 25, 15], k=1)[0]
        if bucket == 0:
            raw = random.uniform(100, 2000)
        elif bucket == 1:
            raw = random.uniform(2000, 5000)
        else:
            raw = random.uniform(5000, 10000)
    return Decimal(f"{raw:.2f}")


def pick_account_dates(status: str) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if status == "active":
        age_days = random.randint(1, 730)
        last_login_days = random.randint(0, min(90, age_days))
    elif status == "inactive":
        age_days = random.randint(91, 730)
        last_login_days = random.randint(91, age_days)
    else:  # suspended
        age_days = random.randint(1, 730)
        last_login_days = random.randint(0, age_days)

    created_at = now - timedelta(days=age_days, hours=random.randint(0, 23))
    last_login_at = now - timedelta(days=last_login_days, hours=random.randint(0, 23))
    return created_at, last_login_at


def pick_txn_type() -> str:
    return random.choices(["trade", "deposit", "withdrawal"], weights=[60, 25, 15], k=1)[0]


def pick_txn_status() -> str:
    return random.choices(["completed", "pending", "failed"], weights=[90, 7, 3], k=1)[0]


def pick_txn_amount(ttype: str) -> Decimal:
    if ttype == "trade":
        raw = max(-500.0, min(500.0, random.gauss(0, 75)))
    elif ttype == "deposit":
        raw = random.uniform(50, 5000)
    else:  # withdrawal
        raw = random.uniform(50, 3000)
    return Decimal(f"{raw:.2f}")


def pick_txn_method(ttype: str) -> str | None:
    if ttype == "trade":
        return "trade_pl"
    if ttype == "deposit":
        return random.choice(DEPOSIT_METHODS)
    if ttype == "withdrawal":
        return random.choice(WITHDRAWAL_METHODS)
    return None


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------


def gen_account(
    *,
    idx: int,
    country: str,
    account_type: str,
    status: str,
    leverage: int,
    fakers: dict[str, Faker],
) -> dict[str, Any]:
    locale = LOCALE_BY_COUNTRY.get(country, DEFAULT_LOCALE)
    fake = fakers[locale]

    full_name = fake.name()
    raw_username = re.sub(r"[^a-z0-9]", "", fake.user_name().lower())[:20] or "user"
    email = f"{raw_username}{idx:04d}@example.com"
    user_id = f"USR{idx:06d}"

    created_at, last_login_at = pick_account_dates(status)

    return {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "email": email,
        "full_name": full_name,
        "country_code": country,
        "account_type": account_type,
        "base_currency": pick_currency(country),
        "balance": pick_balance(account_type),
        "leverage": leverage,
        "status": status,
        "created_at": created_at,
        "last_login_at": last_login_at,
    }


def gen_kyc(account: dict[str, Any], kyc_status: str) -> dict[str, Any]:
    kyc: dict[str, Any] = {
        "id": uuid.uuid4(),
        "account_id": account["id"],
        "status": kyc_status,
        "document_type": None,
        "submitted_at": None,
        "verified_at": None,
        "rejection_reason": None,
    }

    if kyc_status == "not_started":
        return kyc

    kyc["document_type"] = random.choices(
        ["passport", "id_card", "drivers_license"],
        weights=[50, 30, 20],
        k=1,
    )[0]

    now = datetime.now(timezone.utc)
    age_days = max(1, (now - account["created_at"]).days)
    submitted_at = account["created_at"] + timedelta(
        days=random.randint(0, min(30, age_days)),
        hours=random.randint(0, 23),
    )
    kyc["submitted_at"] = min(submitted_at, now)

    if kyc_status == "verified":
        verified_at = kyc["submitted_at"] + timedelta(
            days=random.randint(1, 14),
            hours=random.randint(0, 23),
        )
        kyc["verified_at"] = min(verified_at, now)
    elif kyc_status == "rejected":
        kyc["rejection_reason"] = random.choice(REJECTION_REASONS)
    # 'pending' has submitted_at but no verified_at / rejection_reason

    return kyc


def gen_transactions(account: dict[str, Any]) -> list[dict[str, Any]]:
    status = account["status"]
    n_min, n_max = TXN_COUNT_BY_STATUS[status]
    n = random.randint(n_min, n_max)

    now = datetime.now(timezone.utc)
    created_at = account["created_at"]
    last_login_at = account["last_login_at"]

    if status == "active":
        latest = now
        earliest = max(created_at, now - timedelta(days=180))
    elif status == "inactive":
        latest = last_login_at
        earliest = max(created_at, latest - timedelta(days=180))
    else:  # suspended — all txns must precede a random suspension cutoff
        suspension_cutoff = now - timedelta(days=random.randint(30, 180))
        latest = min(suspension_cutoff, last_login_at)
        earliest = created_at

    if latest <= earliest:
        return []

    transactions: list[dict[str, Any]] = []
    for _ in range(n):
        ts = random_dt_between(earliest, latest)
        ttype = pick_txn_type()
        tstatus = pick_txn_status()

        completed_at: datetime | None = None
        if tstatus == "completed":
            completed_at = min(
                ts + timedelta(days=random.randint(0, 3), hours=random.randint(0, 23)),
                now,
            )

        transactions.append(
            {
                "id": uuid.uuid4(),
                "account_id": account["id"],
                "type": ttype,
                "amount": pick_txn_amount(ttype),
                "currency": account["base_currency"],
                "status": tstatus,
                "method": pick_txn_method(ttype),
                "reference": f"TXN-{uuid.uuid4().hex[:8].upper()}",
                "created_at": ts,
                "completed_at": completed_at,
            }
        )
    return transactions


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

INSERT_ACCOUNT_SQL = """
INSERT INTO accounts
    (id, user_id, email, full_name, country_code, account_type, base_currency,
     balance, leverage, status, created_at, last_login_at)
VALUES (%(id)s, %(user_id)s, %(email)s, %(full_name)s, %(country_code)s,
        %(account_type)s, %(base_currency)s, %(balance)s, %(leverage)s,
        %(status)s, %(created_at)s, %(last_login_at)s);
"""

INSERT_KYC_SQL = """
INSERT INTO kyc_statuses
    (id, account_id, status, document_type, submitted_at, verified_at, rejection_reason)
VALUES (%(id)s, %(account_id)s, %(status)s, %(document_type)s,
        %(submitted_at)s, %(verified_at)s, %(rejection_reason)s);
"""

INSERT_TXN_SQL = """
INSERT INTO transactions
    (id, account_id, type, amount, currency, status, method, reference,
     created_at, completed_at)
VALUES (%(id)s, %(account_id)s, %(type)s, %(amount)s, %(currency)s,
        %(status)s, %(method)s, %(reference)s, %(created_at)s, %(completed_at)s);
"""


# ---------------------------------------------------------------------------
# Verification queries (run after insert)
# ---------------------------------------------------------------------------

VERIFY_QUERIES = [
    ("Total accounts", "SELECT COUNT(*) FROM accounts;"),
    ("Total transactions", "SELECT COUNT(*) FROM transactions;"),
    ("Total kyc_statuses", "SELECT COUNT(*) FROM kyc_statuses;"),
    (
        "Account status distribution",
        "SELECT status, COUNT(*) FROM accounts GROUP BY status ORDER BY COUNT(*) DESC;",
    ),
    (
        "KYC status distribution",
        "SELECT status, COUNT(*) FROM kyc_statuses GROUP BY status ORDER BY COUNT(*) DESC;",
    ),
    (
        "Country distribution",
        "SELECT country_code, COUNT(*) FROM accounts GROUP BY country_code ORDER BY COUNT(*) DESC;",
    ),
]

SAMPLE_JOIN_QUERY = """
SELECT a.user_id, a.full_name, a.country_code, a.account_type, a.balance,
       k.status AS kyc_status, COUNT(t.id) AS tx_count
FROM accounts a
LEFT JOIN kyc_statuses k ON k.account_id = a.id
LEFT JOIN transactions t ON t.account_id = a.id
GROUP BY a.id, a.user_id, a.full_name, a.country_code, a.account_type,
         a.balance, k.status
ORDER BY a.user_id
LIMIT 3;
"""


def show_db_stats(cur) -> None:
    for label, sql in VERIFY_QUERIES:
        cur.execute(sql)
        rows = cur.fetchall()
        console.print(f"[bold cyan]{label}[/bold cyan]")
        if len(rows) == 1 and len(rows[0]) == 1:
            console.print(f"  {rows[0][0]}")
        else:
            for row in rows:
                console.print(f"  {row}")
        console.print()

    cur.execute(SAMPLE_JOIN_QUERY)
    rows = cur.fetchall()
    headers = [d.name for d in cur.description]

    t = Table(title="3 sample accounts (JOIN)")
    for h in headers:
        t.add_column(h, overflow="fold")
    for row in rows:
        t.add_row(*[str(c) for c in row])
    console.print(t)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed mock accounts, transactions, and KYC.")
    parser.add_argument("--count", type=int, default=1000, help="Number of accounts (default 1000)")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="TRUNCATE accounts CASCADE before seeding (clears all 3 tables).",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default 42)")
    args = parser.parse_args()

    if not settings.database_url:
        console.print("[red]ERROR: DATABASE_URL is not set in .env[/red]")
        return 1

    random.seed(args.seed)
    Faker.seed(args.seed)

    fakers = {
        "en_US": Faker("en_US"),
        "id_ID": Faker("id_ID"),
    }

    console.rule("[bold]seed_accounts")
    console.print(f"DB host: [dim]{settings.database_url.split('@')[-1].split('/')[0]}[/dim]")
    console.print(
        f"Count: [cyan]{args.count}[/cyan]   "
        f"Seed: [cyan]{args.seed}[/cyan]   "
        f"Reset: [cyan]{args.reset}[/cyan]"
    )

    statuses = distribute(STATUS_PCT, args.count)
    account_types = distribute(ACCOUNT_TYPE_PCT, args.count)
    countries = distribute(COUNTRY_PCT, args.count)
    leverages = distribute(LEVERAGE_PCT, args.count)
    kyc_statuses = distribute(KYC_STATUS_PCT, args.count)

    console.print("[blue]Generating accounts ...[/blue]")
    accounts = [
        gen_account(
            idx=i + 1,
            country=countries[i],
            account_type=account_types[i],
            status=statuses[i],
            leverage=leverages[i],
            fakers=fakers,
        )
        for i in range(args.count)
    ]

    console.print("[blue]Generating KYC statuses ...[/blue]")
    kycs = [gen_kyc(accounts[i], kyc_statuses[i]) for i in range(args.count)]

    console.print("[blue]Generating transactions ...[/blue]")
    all_txns: list[dict[str, Any]] = []
    with Progress(console=console) as progress:
        task = progress.add_task("[cyan]transactions", total=args.count)
        for a in accounts:
            all_txns.extend(gen_transactions(a))
            progress.update(task, advance=1)

    console.print(
        f"\nGenerated: [cyan]{len(accounts)}[/cyan] accounts, "
        f"[cyan]{len(kycs)}[/cyan] kyc rows, "
        f"[cyan]{len(all_txns)}[/cyan] transactions\n"
    )

    try:
        # Disable prepared statements — required for Supabase pooler (port 6543).
        # See: https://www.psycopg.org/psycopg3/docs/advanced/prepare.html
        with psycopg.connect(settings.database_url, prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                if args.reset:
                    console.print("[yellow]TRUNCATE accounts CASCADE[/yellow]")
                    cur.execute("TRUNCATE accounts CASCADE;")

                console.print("[blue]Inserting accounts ...[/blue]")
                cur.executemany(INSERT_ACCOUNT_SQL, accounts)

                console.print("[blue]Inserting kyc_statuses ...[/blue]")
                cur.executemany(INSERT_KYC_SQL, kycs)

                console.print("[blue]Inserting transactions ...[/blue]")
                cur.executemany(INSERT_TXN_SQL, all_txns)

                conn.commit()
                console.print("[green]Inserts complete.[/green]\n")

                console.rule("[bold]verification queries from DB")
                show_db_stats(cur)
    except psycopg.Error as e:
        console.print(f"[red]DB ERROR: {e}[/red]")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
