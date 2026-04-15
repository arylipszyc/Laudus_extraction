"""Business logic for plan_de_cuentas sync from Google Sheets to Supabase."""
import logging
from datetime import datetime, timezone

from pipeline.config.gspread_config import get_spreadsheet
from backend.app.repositories.supabase_repository import SupabaseRepository

logger = logging.getLogger(__name__)

# Column names in the PlanCuentas Google Sheet
_SHEET_NAME = "PlanCuentas"
_COL_ACCOUNT_NUMBER = "account_number"
_COL_ACCOUNT_NAME = "account_name"
_COL_CAT1 = "1\u00b0 Category"   # "1° Category"
_COL_CAT2 = "2\u00b0 Category"   # "2° Category"
_COL_CAT3 = "3\u00b0 Category"   # "3° Category"


def _map_sheet_row(row: dict, synced_at: str) -> dict | None:
    """Map a PlanCuentas sheet row to a plan_de_cuentas Supabase record."""
    account_number = str(row.get(_COL_ACCOUNT_NUMBER, "")).strip()
    if not account_number:
        return None
    return {
        "account_number": account_number,
        "account_name": str(row.get(_COL_ACCOUNT_NAME, "")).strip() or "Sin Nombre",
        "account_type": None,  # Not available in PlanCuentas sheet
        "cat1": str(row.get(_COL_CAT1, "")).strip() or None,
        "cat2": str(row.get(_COL_CAT2, "")).strip() or None,
        "cat3": str(row.get(_COL_CAT3, "")).strip() or None,
        "active": True,
        "synced_at": synced_at,
    }


def sync_plan_de_cuentas() -> dict:
    """Sync PlanCuentas from Google Sheets to Supabase.

    Reads the 'PlanCuentas' worksheet, maps rows to plan_de_cuentas schema,
    and upserts into Supabase. Sheets is the source of truth.

    Returns:
        {"synced": N, "updated": M} — counts of new and updated records.

    Raises:
        RuntimeError: If Google Sheets connection fails or sheet not found.
    """
    sh = get_spreadsheet()
    if not sh:
        raise RuntimeError("Could not connect to Google Sheets. Check GOOGLE_APPLICATION_CREDENTIALS and GOOGLE_SHEET_ID.")

    try:
        raw_rows = sh.worksheet(_SHEET_NAME).get_all_records()
    except Exception as exc:
        raise RuntimeError(f"Sheet '{_SHEET_NAME}' not found or unreadable: {exc}") from exc

    synced_at = datetime.now(timezone.utc).isoformat()
    records = [
        mapped for row in raw_rows
        if (mapped := _map_sheet_row(row, synced_at)) is not None
    ]

    if not records:
        logger.warning("PlanCuentas sync: no valid records found in sheet.")
        return {"synced": 0, "updated": 0}

    repo = SupabaseRepository()
    result = repo.upsert_plan_de_cuentas(records)
    logger.info("PlanCuentas sync complete: %s", result)
    return result


def list_plan_de_cuentas(active_only: bool = True) -> list[dict]:
    """Return all plan_de_cuentas entries from Supabase."""
    repo = SupabaseRepository()
    return repo.list_plan_de_cuentas(active_only=active_only)
