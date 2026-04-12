"""Dashboard query and filter logic."""
import logging

from backend.app.repositories.base import DataRepository

logger = logging.getLogger(__name__)


def get_balance_sheets(
    repo: DataRepository,
    entity: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Return balance sheet records for entity, optionally filtered by date range."""
    sheet_name = f"balance_sheet_{entity.lower()}"
    records = repo.get_records(sheet_name)  # returns [] if sheet doesn't exist
    if date_from or date_to:
        records = [r for r in records if _in_date_range(str(r.get("query_date", "")), date_from, date_to)]
    last_sync = _max_date(records, "query_date")
    return {"data": records, "meta": {"last_sync": last_sync}}


def get_ledger_entries(
    repo: DataRepository,
    entity: str,
    date_from: str | None = None,
    date_to: str | None = None,
    account_number: str | None = None,
) -> dict:
    """Return ledger entries for entity, optionally filtered by date range and/or account."""
    sheet_name = f"ledger_{entity.lower()}"
    records = repo.get_records(sheet_name)  # returns [] if sheet doesn't exist
    if date_from or date_to:
        records = [r for r in records if _in_date_range(str(r.get("date", "")), date_from, date_to)]
    if account_number is not None:
        records = [r for r in records if str(r.get("accountnumber", "")) == account_number]
    last_sync = _max_date(records, "date")
    return {"data": records, "meta": {"last_sync": last_sync}}


def _in_date_range(record_date: str, date_from: str | None, date_to: str | None) -> bool:
    """Inclusive ISO string date range check. Empty/invalid dates are excluded."""
    if not record_date or record_date == "None":
        return False
    # Patch 7: removed bare except — inputs are guaranteed str; real bugs should propagate
    record_date = record_date[:10]  # truncate to YYYY-MM-DD
    if date_from and record_date < date_from[:10]:
        return False
    if date_to and record_date > date_to[:10]:
        return False
    return True


def _max_date(records: list[dict], date_field: str) -> str | None:
    """Return the max ISO date string from records[date_field], or None if empty."""
    dates = [str(r.get(date_field, ""))[:10] for r in records if r.get(date_field)]
    if not dates:
        return None
    return max(dates)
