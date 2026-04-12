"""Historical backfill — Balance Sheet + Ledger from a start date to today.

Imports from services/, config/, utils/, models.py — does NOT modify them.
Writes via DataRepository.upsert_records() — no direct gspread calls.
"""
import logging
from datetime import date

from config.laudus_config import BALANCE_SHEET_URL, get_endpoints
from models import BALANCE_HEADERS, LEDGER_HEADERS, map_balance_row, map_ledger_row
from services.balance_sheet_service import fetch_balance_sheet
from services.ledger_service import fetch_ledger
from utils.dates import get_end_of_month_dates

from backend.app.repositories.base import DataRepository

logger = logging.getLogger(__name__)


def run_backfill(from_date_str: str, repo: DataRepository) -> dict:
    """Fetch all Balance Sheet (per month-end) and Ledger (full range) from from_date to today.

    Balance Sheet: one API call per month-end date, upserted with pk=account_id+query_date.
    Ledger: single call for full date range, upserted with pk=journalentryid+lineid.

    Args:
        from_date_str: ISO date string "YYYY-MM-DD" — inclusive start of backfill
        repo: DataRepository for upsert writes

    Returns:
        {"balance_sheet_upserted": int, "ledger_upserted": int}

    Raises:
        ValueError: if from_date_str is None/invalid or is in the future
    """
    if not from_date_str:
        raise ValueError("from_date is required for backfill")
    from_date = date.fromisoformat(from_date_str)
    today = date.today()
    if from_date > today:
        raise ValueError(f"from_date {from_date_str} cannot be in the future (today={today})")

    # ── Balance Sheet: one API call per month-end date ───────────────────────
    # Accumulate ALL rows first, then upsert once — avoids N× clear+write cycles
    eom_dates = get_end_of_month_dates(from_date.year, from_date.month, today.year, today.month)
    balance_rows: list[dict] = []
    for eom in eom_dates:
        raw = fetch_balance_sheet(BALANCE_SHEET_URL, {"date": str(eom)})
        items = raw if isinstance(raw, list) else (raw or {}).get("data", [])
        for item in (items or []):
            balance_rows.append(map_balance_row(item, eom))

    logger.info("Backfill: upserting %d balance sheet rows (%d months)", len(balance_rows), len(eom_dates))
    repo.upsert_records(
        "balance_sheet",
        balance_rows,
        primary_key_func=lambda r: f"{r['account_id']}_{r['query_date']}",
        headers=BALANCE_HEADERS,
    )

    # ── Ledger: single call for full date range ──────────────────────────────
    date_from = date(from_date.year, from_date.month, 1)
    ep = get_endpoints(date_from, today)["GET_LEDGER"]
    raw_ledger = fetch_ledger(ep["url"], ep["params"])
    ledger_items = raw_ledger if isinstance(raw_ledger, list) else (raw_ledger or {}).get("data", [])
    # periodo = today (the sync period's end date), not the individual transaction's date
    ledger_rows = [map_ledger_row(item, today) for item in (ledger_items or [])]

    logger.info("Backfill: upserting %d ledger rows", len(ledger_rows))
    repo.upsert_records(
        "ledger",
        ledger_rows,
        primary_key_func=lambda r: f"{r['journalentryid']}_{r['lineid']}",
        headers=LEDGER_HEADERS,
    )

    return {
        "balance_sheet_upserted": len(balance_rows),
        "ledger_upserted": len(ledger_rows),
    }
