"""Dashboard API router — GET /balance-sheets, GET /ledger-entries."""
import re

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.api.v1.dashboard.schemas import (
    VALID_ENTITIES,
    BalanceSheetRecord,
    BalanceSheetResponse,
    DashboardMeta,
    LedgerEntriesResponse,
    LedgerEntryRecord,
)
from backend.app.api.v1.dashboard.service import get_balance_sheets, get_ledger_entries
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import get_current_user, get_repository
from backend.app.repositories.base import DataRepository

router = APIRouter(tags=["dashboard"])

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_entity(entity: str) -> str:
    """Raise 422 if entity is not in the allowed set."""
    if entity not in VALID_ENTITIES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid entity '{entity}'. Valid values: {sorted(VALID_ENTITIES)}",
        )
    return entity


def _validate_dates(date_from: str | None, date_to: str | None) -> None:
    """Raise 422 for non-ISO date strings or inverted range."""
    for name, value in [("date_from", date_from), ("date_to", date_to)]:
        if value is not None and not _ISO_DATE_RE.match(value):
            raise HTTPException(
                status_code=422,
                detail=f"Invalid date format for '{name}': expected YYYY-MM-DD, got '{value}'",
            )
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail=f"date_from ({date_from}) must be <= date_to ({date_to})",
        )


@router.get("/balance-sheets", response_model=BalanceSheetResponse)
def list_balance_sheets(
    entity: str = Query(..., description="Entity name: EAG | Jocelyn | Jeannette | Johanna | Jael"),
    date_from: str | None = Query(default=None, description="ISO date YYYY-MM-DD (inclusive)"),
    date_to: str | None = Query(default=None, description="ISO date YYYY-MM-DD (inclusive)"),
    user: UserSession = Depends(get_current_user),
    repo: DataRepository = Depends(get_repository),
) -> BalanceSheetResponse:
    """Return balance sheet records for an entity, optionally filtered by date range."""
    _validate_entity(entity)
    _validate_dates(date_from, date_to)
    result = get_balance_sheets(repo, entity, date_from, date_to)
    return BalanceSheetResponse(
        data=[BalanceSheetRecord(**r) for r in result["data"]],
        meta=DashboardMeta(last_sync=result["meta"]["last_sync"]),
    )


@router.get("/ledger-entries", response_model=LedgerEntriesResponse, response_model_by_alias=True)
def list_ledger_entries(
    entity: str = Query(..., description="Entity name: EAG | Jocelyn | Jeannette | Johanna | Jael"),
    date_from: str | None = Query(default=None, description="ISO date YYYY-MM-DD (inclusive)"),
    date_to: str | None = Query(default=None, description="ISO date YYYY-MM-DD (inclusive)"),
    account_number: str | None = Query(
        default=None,
        description="Filter by accountnumber (for drill-down, Story 3.5)",
    ),
    user: UserSession = Depends(get_current_user),
    repo: DataRepository = Depends(get_repository),
) -> LedgerEntriesResponse:
    """Return ledger entries for an entity, optionally filtered by date range and account."""
    _validate_entity(entity)
    _validate_dates(date_from, date_to)
    result = get_ledger_entries(repo, entity, date_from, date_to, account_number)
    return LedgerEntriesResponse(
        data=[LedgerEntryRecord(**r) for r in result["data"]],
        meta=DashboardMeta(last_sync=result["meta"]["last_sync"]),
    )
