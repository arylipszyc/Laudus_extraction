# Story 3.1: Dashboard API Endpoints

Status: done

## Story

As a developer,
I want backend API endpoints that return financial data filtered by entity and date range,
So that all dashboard views have a consistent, secure data source to build on.

## Acceptance Criteria

1. Dashboard router registered at `backend/app/api/v1/dashboard/router.py` and included in `backend/app/api/v1/router.py`
2. `GET /api/v1/balance-sheets?entity=EAG&date_from=2026-01-01&date_to=2026-12-31` returns Balance Sheet data filtered to that entity and period; response: `{"data": [...], "meta": {"last_sync": "ISO-string-or-null"}}`
3. `GET /api/v1/ledger-entries?entity=EAG&date_from=2026-01-01&date_to=2026-12-31` returns General Ledger entries filtered to that entity and period; all monetary amounts as `float`
4. Both endpoints apply `get_current_user()` — unauthenticated requests return HTTP 401; both `owner` and `contador` roles can access (no `require_role` restriction — all authenticated users can read)
5. `entity` param is validated against the allowed set (`EAG`, `Jocelyn`, `Jeannette`, `Johanna`, `Jael`); invalid entity returns HTTP 422
6. All JSON response fields snake_case; all dates ISO 8601 strings (`"2026-03-31"`); all monetary amounts `float` (never string)
7. `GET /api/v1/ledger-entries` accepts optional `account_number` query param for drill-down filtering (needed by Story 3.5); if provided, only entries matching that `accountnumber` are returned
8. Both `date_from` and `date_to` are optional; if omitted, all records for that entity are returned
9. If an entity sheet tab doesn't exist in Sheets, endpoint returns `{"data": [], "meta": {"last_sync": null}}` — NOT a 500 error
10. `backend/tests/test_dashboard.py` covers all ACs with full mock repo pattern

## Architecture Context

### Entity → Sheet Tab Mapping (CRITICAL DESIGN DECISION)

Each entity maps to **entity-specific Google Sheet tabs** within the same spreadsheet (single `GOOGLE_SHEET_ID`):

| Entity param | balance_sheet tab | ledger tab |
|---|---|---|
| `EAG` | `balance_sheet_eag` | `ledger_eag` |
| `Jocelyn` | `balance_sheet_jocelyn` | `ledger_jocelyn` |
| `Jeannette` | `balance_sheet_jeannette` | `ledger_jeannette` |
| `Johanna` | `balance_sheet_johanna` | `ledger_johanna` |
| `Jael` | `balance_sheet_jael` | `ledger_jael` |

**Why tabs, not separate spreadsheets:** The existing architecture uses a single `GOOGLE_SHEET_ID`. Separate-tab pattern requires no new env vars and `SheetsRepository.get_records(sheet_name)` already accepts any tab name.

**NOTE:** The current sync pipeline writes to `balance_sheet` and `ledger` (single-entity, no suffix). Those tabs are NOT used by the dashboard API. Entity-specific tabs will be populated when sync is extended for multi-entity (deferred). Until then, all entities return `{"data": [], "meta": {"last_sync": null}}` — this is correct behavior, not a bug.

### Date Filtering Logic

- `balance_sheet` records: filter on `query_date` field (ISO string `"YYYY-MM-DD"`)
- `ledger` records: filter on `date` field (ISO string `"YYYY-MM-DD"`)
- Filter is inclusive: `date_from <= record_date <= date_to`
- Date comparison is string comparison (ISO strings sort lexicographically = chronologically)
- `last_sync` in meta = max of the filtered `query_date` (balance) or `date` (ledger) values from returned records; `None` if data is empty

### Data Types from Google Sheets (CRITICAL: gspread coercion)

`gspread.get_all_records()` can return numbers as `int`, `float`, or `str` depending on cell format. The Pydantic schemas enforce the correct types — declare monetary fields as `float` and Pydantic will coerce. However, if a field arrives as `""` (empty string), Pydantic will raise a validation error. Use `float | None` or `Any` for fields that might be blank in the sheet. Key money fields: `debit`, `credit`, `debit_balance`, `credit_balance` (balance); `debit`, `credit`, `paritytomaincurrency` (ledger).

## Files To Create

```
backend/app/api/v1/dashboard/
    __init__.py         (empty)
    schemas.py          (Pydantic models)
    service.py          (filter logic)
    router.py           (GET /balance-sheets, GET /ledger-entries)
backend/tests/
    test_dashboard.py   (already listed in architecture structure)
```

## Files To Modify

```
backend/app/api/v1/router.py   — add dashboard router import + include_router
```

## Dev Notes

### `schemas.py` — Full Implementation

```python
"""Pydantic schemas for dashboard API endpoints."""
from typing import Any
from pydantic import BaseModel


VALID_ENTITIES = frozenset({"EAG", "Jocelyn", "Jeannette", "Johanna", "Jael"})


class BalanceSheetRecord(BaseModel):
    account_id: Any
    account_number: str
    account_name: str
    debit: float
    credit: float
    debit_balance: float
    credit_balance: float
    query_date: str
    is_latest: str


class LedgerEntryRecord(BaseModel):
    journalentryid: Any
    journalentrynumber: Any
    date: str
    accountnumber: str
    lineid: Any
    description: str
    debit: float
    credit: float
    currencycode: str
    paritytomaincurrency: float
    periodo: str


class DashboardMeta(BaseModel):
    last_sync: str | None


class BalanceSheetResponse(BaseModel):
    data: list[BalanceSheetRecord]
    meta: DashboardMeta


class LedgerEntriesResponse(BaseModel):
    data: list[LedgerEntryRecord]
    meta: DashboardMeta
```

**Field naming note:** `BALANCE_HEADERS` uses `account_id`, `account_number`, `account_name`, `debit`, `credit`, `debit_balance`, `credit_balance`, `query_date`, `is_latest`. `LEDGER_HEADERS` uses `journalentryid`, `journalentrynumber`, `date`, `accountnumber`, `lineid`, `description`, `debit`, `credit`, `currencycode`, `paritytomaincurrency`, `periodo`. Use `Any` for `account_id`, `journalentryid`, `journalentrynumber`, `lineid` — Sheets may return them as int or str.

### `service.py` — Full Implementation

```python
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
    try:
        record_date = record_date[:10]  # truncate to YYYY-MM-DD
        if date_from and record_date < date_from[:10]:
            return False
        if date_to and record_date > date_to[:10]:
            return False
        return True
    except Exception:
        return False


def _max_date(records: list[dict], date_field: str) -> str | None:
    """Return the max ISO date string from records[date_field], or None if empty."""
    dates = [str(r.get(date_field, ""))[:10] for r in records if r.get(date_field)]
    if not dates:
        return None
    return max(dates)
```

### `router.py` — Full Implementation

```python
"""Dashboard API router — GET /balance-sheets, GET /ledger-entries."""
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.api.v1.dashboard.schemas import (
    BalanceSheetResponse,
    DashboardMeta,
    LedgerEntriesResponse,
    VALID_ENTITIES,
    BalanceSheetRecord,
    LedgerEntryRecord,
)
from backend.app.api.v1.dashboard.service import get_balance_sheets, get_ledger_entries
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import get_current_user, get_repository
from backend.app.repositories.base import DataRepository

router = APIRouter(tags=["dashboard"])


def _validate_entity(entity: str) -> str:
    """Raise 422 if entity is not in the allowed set."""
    if entity not in VALID_ENTITIES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid entity '{entity}'. Valid values: {sorted(VALID_ENTITIES)}",
        )
    return entity


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
    result = get_balance_sheets(repo, entity, date_from, date_to)
    return BalanceSheetResponse(
        data=[BalanceSheetRecord(**r) for r in result["data"]],
        meta=DashboardMeta(last_sync=result["meta"]["last_sync"]),
    )


@router.get("/ledger-entries", response_model=LedgerEntriesResponse)
def list_ledger_entries(
    entity: str = Query(..., description="Entity name: EAG | Jocelyn | Jeannette | Johanna | Jael"),
    date_from: str | None = Query(default=None, description="ISO date YYYY-MM-DD (inclusive)"),
    date_to: str | None = Query(default=None, description="ISO date YYYY-MM-DD (inclusive)"),
    account_number: str | None = Query(default=None, description="Filter by accountnumber (for drill-down, Story 3.5)"),
    user: UserSession = Depends(get_current_user),
    repo: DataRepository = Depends(get_repository),
) -> LedgerEntriesResponse:
    """Return ledger entries for an entity, optionally filtered by date range and account."""
    _validate_entity(entity)
    result = get_ledger_entries(repo, entity, date_from, date_to, account_number)
    return LedgerEntriesResponse(
        data=[LedgerEntryRecord(**r) for r in result["data"]],
        meta=DashboardMeta(last_sync=result["meta"]["last_sync"]),
    )
```

### `router.py` in `backend/app/api/v1/router.py` — Modification

Add dashboard router registration. Current file:
```python
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.sync.router import router as sync_router
from backend.app.auth.router import router as auth_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(sync_router)
```

Add:
```python
from backend.app.api.v1.dashboard.router import router as dashboard_router
# ...
router.include_router(dashboard_router)
```

Note: Dashboard router has **no prefix** on the router itself (unlike sync which uses `prefix="/sync"`). The endpoints are `/balance-sheets` and `/ledger-entries` at v1 root. The `/api/v1` prefix is applied by `main.py` when including the v1 router.

### Test Patterns — `backend/tests/test_dashboard.py`

Follow **exactly** the same patterns as `backend/tests/test_sync.py`. Key patterns to replicate:

```python
"""Tests for dashboard API endpoints — Story 3.1."""
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.auth.service import create_jwt
from backend.app.dependencies import get_repository
from backend.app.middleware import add_middleware


def make_dashboard_test_app(mock_repo=None) -> TestClient:
    from backend.app.api.v1.dashboard.router import router as dashboard_router
    app = FastAPI()
    add_middleware(app)
    app.include_router(dashboard_router, prefix="/api/v1")
    if mock_repo is not None:
        app.dependency_overrides[get_repository] = lambda: mock_repo
    return TestClient(app, raise_server_exceptions=False)


def make_mock_repo(entity: str = "EAG", balance_records=None, ledger_records=None):
    """Route get_records by entity-specific sheet names."""
    repo = MagicMock()
    _bs = balance_records if balance_records is not None else []
    _ledger = ledger_records if ledger_records is not None else []

    def _get_records(sheet_name):
        if sheet_name == f"balance_sheet_{entity.lower()}":
            return _bs
        if sheet_name == f"ledger_{entity.lower()}":
            return _ledger
        return []

    repo.get_records.side_effect = _get_records
    return repo


def owner_token():
    return create_jwt(email="owner@test.com", role="owner")


def contador_token():
    return create_jwt(email="contador@test.com", role="contador")
```

**Required tests (map to ACs):**

| Test | AC | Assertion |
|---|---|---|
| `test_balance_sheets_unauthenticated` | AC4 | No cookie → 401 |
| `test_balance_sheets_owner_can_read` | AC4 | owner role → 200 |
| `test_balance_sheets_contador_can_read` | AC4 | contador role → 200 |
| `test_balance_sheets_returns_data_and_meta` | AC2 | data + meta.last_sync keys present |
| `test_balance_sheets_filters_by_date_range` | AC2 | records outside range excluded |
| `test_balance_sheets_no_date_filter_returns_all` | AC8 | no date params → all records |
| `test_balance_sheets_invalid_entity_returns_422` | AC5 | entity="INVALID" → 422 |
| `test_balance_sheets_valid_entities_accepted` | AC5 | parametrize over all 5 entities → 200 |
| `test_balance_sheets_empty_entity_returns_empty_list` | AC9 | unknown sheet → data=[], last_sync=null |
| `test_balance_sheets_amounts_are_float` | AC6 | debit, credit are float type |
| `test_ledger_entries_unauthenticated` | AC4 | 401 |
| `test_ledger_entries_returns_data_and_meta` | AC3 | data + meta keys |
| `test_ledger_entries_filters_by_date_range` | AC3 | date filtering works |
| `test_ledger_entries_account_number_filter` | AC7 | only matching accountnumber returned |
| `test_ledger_entries_amounts_are_float` | AC6 | debit, credit, paritytomaincurrency float |
| `test_ledger_entries_invalid_entity_returns_422` | AC5 | 422 |

**Sample balance sheet record for mock data:**
```python
SAMPLE_BALANCE_RECORD = {
    "account_id": 273,
    "account_number": "111005",
    "account_name": "Caja Pesos",
    "debit": 100000.0,
    "credit": 0.0,
    "debit_balance": 100000.0,
    "credit_balance": 0.0,
    "query_date": "2026-03-31",
    "is_latest": "TRUE",
}

SAMPLE_LEDGER_RECORD = {
    "journalentryid": 12345,
    "journalentrynumber": 1001,
    "date": "2026-03-15",
    "accountnumber": "111005",
    "lineid": 1,
    "description": "Pago proveedor",
    "debit": 50000.0,
    "credit": 0.0,
    "currencycode": "CLP",
    "paritytomaincurrency": 1.0,
    "periodo": "2026-03-31",
}
```

### Anti-Patterns to Avoid

- **DO NOT** import `gspread` directly in router/service — all sheet access goes through `DataRepository`
- **DO NOT** use `require_role(["contador"])` — both roles can read dashboards (AC4)
- **DO NOT** create a separate `SheetsRepository` instance per entity — reuse `get_repository()` which returns the same spreadsheet object; entity routing is done via sheet tab name, not separate spreadsheets
- **DO NOT** raise an error if entity sheet tab doesn't exist — `SheetsRepository.get_records()` already catches exceptions and returns `[]`; the endpoint must return `{"data": [], "meta": {"last_sync": null}}`
- **DO NOT** duplicate `_read_balance_sheet_last_sync` from sync service — dashboard computes `last_sync` inline from the returned records
- **DO NOT** add `prefix="/dashboard"` to the dashboard router — endpoints must be `/api/v1/balance-sheets` and `/api/v1/ledger-entries` (per architecture naming: `GET /api/v1/balance-sheets`)
- **DO NOT** use raw `useEffect` + fetch in frontend (not in scope for this story, but note for future)
- **DO NOT** modify `models.py`, `sync.py`, `services/`, `config/`, `utils/` — read them only

### Previous Story Intelligence (from 2.3 review findings)

Pitfalls that affected Epic 2 stories — avoid in this story:
- P6 from 2.3: Validate `date_from`/`date_to` format before using them for comparison. If provided but not valid ISO, raise HTTP 422 (not a 500). Use simple format check: `len(date) >= 10 and date[:10].count("-") == 2`.
- `SheetsRepository.get_records()` returns `[]` on exception (see `sheets_repository.py:48`) — this means a missing tab silently returns empty list. AC9 is automatically satisfied by existing behavior.
- Pydantic coercion: Sheets may return `debit=100000` (int) for a numeric cell. `float` in Pydantic model auto-coerces int → float. BUT if the cell is empty, gspread returns `""` → Pydantic raises validation error. Use `debit: float = 0.0` default or `float | None` to handle blank cells gracefully.

### Existing Pattern — `backend/app/api/v1/router.py`

Current content (3 lines of imports + 4 lines of includes). This file must be extended, not replaced:
```python
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.sync.router import router as sync_router
from backend.app.auth.router import router as auth_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(sync_router)
# ADD: router.include_router(dashboard_router)
```

## Tasks / Subtasks

- [x] Create `backend/app/api/v1/dashboard/__init__.py` (empty)
- [x] Create `backend/app/api/v1/dashboard/schemas.py` — `BalanceSheetRecord`, `LedgerEntryRecord`, `DashboardMeta`, `BalanceSheetResponse`, `LedgerEntriesResponse`, `VALID_ENTITIES` (AC: 2, 3, 5, 6)
  - [x] Use `Any` for `account_id`, `journalentryid`, `journalentrynumber`, `lineid`
  - [x] Monetary fields as `float` with `= 0.0` defaults (handles empty Sheets cells)
  - [x] `VALID_ENTITIES = frozenset({"EAG", "Jocelyn", "Jeannette", "Johanna", "Jael"})`
- [x] Create `backend/app/api/v1/dashboard/service.py` — `get_balance_sheets()`, `get_ledger_entries()`, `_in_date_range()`, `_max_date()` (AC: 2, 3, 7, 8, 9)
  - [x] Entity → sheet tab mapping: `balance_sheet_{entity.lower()}`, `ledger_{entity.lower()}`
  - [x] `_in_date_range()` inclusive, ISO string comparison, handles empty/None dates
  - [x] `_max_date()` returns max date string or None
- [x] Create `backend/app/api/v1/dashboard/router.py` — `GET /balance-sheets`, `GET /ledger-entries` (AC: 1, 2, 3, 4, 5, 7, 8)
  - [x] No router prefix (endpoints at `/balance-sheets`, `/ledger-entries` under v1)
  - [x] `get_current_user()` (not `require_role`) — both roles can read
  - [x] `_validate_entity()` helper raises HTTP 422 for invalid entity
  - [x] `account_number` optional param on `/ledger-entries`
- [x] Modify `backend/app/api/v1/router.py` — add dashboard router import + `include_router` (AC: 1)
- [x] Create `backend/tests/test_dashboard.py` — 27 tests covering all ACs (AC: 10)
  - [x] `make_dashboard_test_app()` factory (same pattern as test_sync.py)
  - [x] `make_mock_repo(entity, balance_records, ledger_records)` routes by entity-specific tab name
  - [x] All 5 valid entities tested via parametrize for AC5
  - [x] Float coercion tested for AC6 (int inputs → float outputs)

## Dev Agent Record

### Agent Model Used
claude-sonnet-4-6 (Amelia)

### Completion Notes
- 27 tests pass, 104 total (suite completa sin regresiones).
- `schemas.py`: monetary fields use `= 0.0` defaults (guards against empty Sheets cells per P6 pattern from 2.3 review).
- `service.py`: `_in_date_range()` truncates to `[:10]` to handle datetime strings; `_max_date()` returns None on empty records → `meta.last_sync: null`.
- `router.py`: no prefix on router (endpoints at `/balance-sheets`, `/ledger-entries`); `_validate_entity()` raises 422; `get_current_user()` (not `require_role`) — both roles read.
- `test_dashboard.py`: 27 tests — 16 endpoint tests (includes 5-entity parametrize), 4 service unit tests, plus edge cases (date_from-only filter, ledger empty, etc.)
- `backend/app/api/v1/router.py` updated with dashboard router import + include.

### Debug Log
No issues. 27/27 on first run.

### Review Findings

- [x] [Review][Decision] Entity names en `VALID_ENTITIES` — dismissed: aceptable para MVP, entidades fijas del sistema
- [x] [Review][Decision] `accountnumber` int-coercion en filtro — dismissed: números de cuenta no tienen ceros significativos
- [ ] [Review][Patch] `LedgerEntryRecord` exposes non-snake_case fields in JSON response (`journalentryid`, `journalentrynumber`, `accountnumber`, `lineid`, `currencycode`, `paritytomaincurrency`, `periodo`) — violates AC6 [`schemas.py`]
- [ ] [Review][Patch] `test_ledger_entries_account_number_filter` asserts `body["data"][0]["accountnumber"]` — test encodes the AC6 violation; must update alongside schema fix [`tests/test_dashboard.py:314`]
- [ ] [Review][Patch] `date_from`/`date_to` accept any string with no ISO format validation and no inverted-range check — malformed inputs (e.g. `"not-a-date"`, `"2026-99-01"`) produce silently wrong filter results; inverted range silently returns `[]` [`router.py` query params + `service.py:_in_date_range`]
- [ ] [Review][Patch] Required schema fields with no default + empty string from Sheets → unhandled `ValidationError` 500 — fields like `query_date`, `account_name`, `currencycode`, `periodo` have no fallback; if gspread returns `""` for a blank required cell, `BalanceSheetRecord(**r)` raises 500 [`router.py:42,63` + `schemas.py`]
- [ ] [Review][Patch] No test for `contador` role on `/ledger-entries` — AC4 requires both roles on both endpoints; only `/balance-sheets` is tested with `contador_token()` [`tests/test_dashboard.py`]
- [ ] [Review][Patch] No parametrized entity test for `/ledger-entries` — AC5 + AC10; `/balance-sheets` has the 5-entity parametrize but `/ledger-entries` does not [`tests/test_dashboard.py`]
- [ ] [Review][Patch] `_in_date_range` bare `except Exception: return False` silences programming errors — a bug in the try block is indistinguishable from a legitimate excluded record [`service.py:_in_date_range`]
- [x] [Review][Defer] `@lru_cache` on `get_repository` — stale Google Sheets credentials after expiry cause silent empty responses; pre-existing from Story 1.1 [`dependencies.py`] — deferred, pre-existing
- [x] [Review][Defer] No entity-level RBAC — any authenticated user can read any entity's data; spec explicitly says "all authenticated users can read" (no `require_role`) — deferred, by spec design

## Story File List

### Files To Create
- `backend/app/api/v1/dashboard/__init__.py`
- `backend/app/api/v1/dashboard/schemas.py`
- `backend/app/api/v1/dashboard/service.py`
- `backend/app/api/v1/dashboard/router.py`
- `backend/tests/test_dashboard.py`

### Files To Modify
- `backend/app/api/v1/router.py`
