# Story 2.3: Backfill Histórico + UI de Estado de Sync

Status: done

## Story

As a contador,
I want to trigger a full historical backfill from January 2021 and see sync status in the UI,
So that all historical financial data is available from day one and I can confirm data is current at a glance.

## Acceptance Criteria

1. `POST /api/v1/sync/trigger` accepts an optional JSON body `{"mode": "backfill", "from_date": "2021-01-01"}` — when `mode="backfill"`, the pipeline fetches Balance Sheet (one call per month-end date from `from_date` to today) and General Ledger (single call for full date range) using `fetch_balance_sheet`, `fetch_ledger`, `map_balance_row`, `map_ledger_row`, `get_end_of_month_dates`, `BALANCE_SHEET_URL`, `get_endpoints`, and `repo.upsert_records()` (FR9)
2. Deduplication in backfill is handled by `repo.upsert_records()` with the same primary keys as incremental sync: `account_id + query_date` for Balance Sheet; `journalentryid + lineid` for Ledger — no records are doubled if a partial sync already ran (FR10)
3. When `mode="backfill"` and `from_date` is absent, `POST /trigger` returns HTTP 422
4. When `mode="normal"` (default), behavior is identical to Story 2.1/2.2 — `sync_api()` is called; no regression
5. Backfill runs asynchronously — `POST /trigger` returns 202 + `{status: "triggered", job_id: ...}` immediately; `GET /sync/status` reflects `job_status="running"` while in progress and `job_status="done"` with `stats` when complete (FR11)
6. The frontend `useSyncStatus` hook polls `GET /api/v1/sync/status` every 5 s when `job_status="running"`, every 60 s otherwise
7. The Header displays: "Sincronizando…" (blue) when running; "Error en sync" (destructive) when failed; last `balance_sheet.last_sync` date when idle/done — replaces the placeholder comment in `Header.tsx`
8. `sync.py`, `services/`, `config/`, `utils/` files are NOT modified

## Dev Notes

### Architecture

- `backfill.py` is a NEW file at `backend/app/api/v1/sync/backfill.py`
- It IMPORTS (does not modify) from: `services/`, `config/`, `utils/dates.py`, `models.py`
- It USES `repo.upsert_records()` for writes — no direct gspread calls
- `SheetsRepository.upsert_records()` delegates to `gspread_utils.upsert_to_sheet()` — no new dependency
- No frontend tests per project convention

### Key Imports Available (do NOT modify these files)

```python
# from config/laudus_config.py
from config.laudus_config import BALANCE_SHEET_URL, get_endpoints
# get_endpoints(date_from, date_to) → {"GET_LEDGER": {"url": LEDGER_URL, "params": {"dateFrom": ..., "dateTo": ...}}}

# from models.py
from models import BALANCE_HEADERS, LEDGER_HEADERS, map_balance_row, map_ledger_row
# map_balance_row(item, query_date, is_latest=False) → dict aligned to BALANCE_HEADERS
# map_ledger_row(item, periodo) → dict aligned to LEDGER_HEADERS

# from services/
from services.balance_sheet_service import fetch_balance_sheet
from services.ledger_service import fetch_ledger
# fetch_balance_sheet(endpoint, params) → API JSON response (list or dict with list)
# fetch_ledger(endpoint, params) → API JSON response (list or dict with list)

# from utils/dates.py
from utils.dates import get_end_of_month_dates
# get_end_of_month_dates(start_year, start_month, end_year, end_month) → list[date]
# e.g. get_end_of_month_dates(2021, 1, 2021, 3) → [date(2021,1,31), date(2021,2,28), date(2021,3,31)]
```

### Repository Interface (already implemented in SheetsRepository)

```python
# DataRepository.upsert_records() signature
repo.upsert_records(
    sheet_name: str,                        # "balance_sheet" | "ledger"
    records: list[dict],                    # list of mapped rows
    primary_key_func: Callable[[dict], str], # lambda for deduplication key
    headers: list[str],                     # BALANCE_HEADERS or LEDGER_HEADERS
) -> list[dict]  # merged records
```

### `backfill.py` Implementation Guide

```python
"""Historical backfill — Balance Sheet + Ledger from a start date to today."""
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
    
    Args:
        from_date_str: ISO date string "YYYY-MM-DD" — inclusive start of backfill
        repo: DataRepository for upsert writes
    
    Returns:
        {"balance_sheet_upserted": int, "ledger_upserted": int}
    """
    from_date = date.fromisoformat(from_date_str)
    today = date.today()

    # Balance Sheet: one API call per month-end date
    eom_dates = get_end_of_month_dates(from_date.year, from_date.month, today.year, today.month)
    balance_rows = []
    for eom in eom_dates:
        raw = fetch_balance_sheet(BALANCE_SHEET_URL, {"date": str(eom)})
        items = raw if isinstance(raw, list) else (raw or {}).get("data", [])
        for item in (items or []):
            balance_rows.append(map_balance_row(item, eom))

    repo.upsert_records(
        "balance_sheet",
        balance_rows,
        primary_key_func=lambda r: f"{r['account_id']}_{r['query_date']}",
        headers=BALANCE_HEADERS,
    )

    # Ledger: single call for the full date range
    date_from = date(from_date.year, from_date.month, 1)
    ep = get_endpoints(date_from, today)["GET_LEDGER"]
    raw_ledger = fetch_ledger(ep["url"], ep["params"])
    ledger_items = raw_ledger if isinstance(raw_ledger, list) else (raw_ledger or {}).get("data", [])
    ledger_rows = [map_ledger_row(item, item.get("date", "")) for item in (ledger_items or [])]

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
```

### `service.py` Changes

Add `_run_backfill` function and update `trigger_sync`:

```python
def trigger_sync(repo: DataRepository, mode: str = "normal", from_date: str | None = None) -> str:
    """Start sync or backfill in a background thread. Returns job_id.
    Raises ValueError if a sync is already running.
    """
    with _job_lock:
        if _current_job["status"] == "running":
            raise ValueError("Sync already running")
        job_id = str(uuid4())
        _current_job.update({
            "job_id": job_id,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "error": None,
            "stats": None,
        })

    if mode == "backfill":
        thread = threading.Thread(target=_run_backfill, args=(job_id, repo, from_date), daemon=True)
    else:
        thread = threading.Thread(target=_run_sync, args=(job_id, repo), daemon=True)
    thread.start()
    return job_id


def _run_backfill(job_id: str, repo: DataRepository, from_date: str) -> None:
    """Execute run_backfill() in background thread. Updates _current_job on completion/failure."""
    try:
        from backend.app.api.v1.sync.backfill import run_backfill
        result = run_backfill(from_date, repo)
        stats = {
            "balance_sheet_added": result["balance_sheet_upserted"],
            "ledger_added": result["ledger_upserted"],
        }
        with _job_lock:
            if _current_job["job_id"] == job_id:
                _current_job.update({
                    "status": "done",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "stats": stats,
                })
    except Exception as exc:
        logger.error("Background backfill failed: %s", exc, exc_info=True)
        with _job_lock:
            if _current_job["job_id"] == job_id:
                _current_job.update({
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(exc),
                    "stats": None,
                })
```

### `schemas.py` Changes

Add `TriggerRequest`:

```python
class TriggerRequest(BaseModel):
    mode: Literal["normal", "backfill"] = "normal"
    from_date: str | None = None  # ISO date "YYYY-MM-DD", required when mode="backfill"
```

### `router.py` Changes

Update POST /trigger to accept optional body:

```python
from fastapi import APIRouter, Body, Depends, HTTPException
from backend.app.api.v1.sync.schemas import TriggerRequest, TriggerResponse

@router.post("/trigger", response_model=TriggerResponse, status_code=202)
def sync_trigger(
    request: TriggerRequest = Body(default=TriggerRequest()),
    user: UserSession = Depends(require_role(["contador"])),
    repo: DataRepository = Depends(get_repository),
) -> TriggerResponse:
    """Trigger async sync (normal or backfill). Returns job_id immediately."""
    if request.mode == "backfill" and not request.from_date:
        raise HTTPException(status_code=422, detail="from_date is required when mode='backfill'")
    try:
        job_id = trigger_sync(repo, mode=request.mode, from_date=request.from_date)
    except ValueError:
        raise HTTPException(status_code=409, detail="Sync already running")
    return TriggerResponse(status="triggered", job_id=job_id)
```

### Frontend: `types/index.ts` Additions

Append to existing types (do NOT remove existing types):

```typescript
export interface DataTypeSyncStatus {
  last_sync: string | null
}

export interface SyncRunStats {
  balance_sheet_added: number | null
  ledger_added: number | null
}

export interface SyncStatus {
  balance_sheet: DataTypeSyncStatus
  ledger: DataTypeSyncStatus
  job_status: 'idle' | 'running' | 'done' | 'failed'
  job_id: string | null
  error: string | null
  stats: SyncRunStats | null
}
```

### Frontend: `services/sync.ts` (NEW FILE)

```typescript
import { api } from './api'
import type { SyncStatus } from '@/types'

export async function getSyncStatus(): Promise<SyncStatus> {
  const res = await fetch(`${api.baseUrl}/api/v1/sync/status`, { credentials: 'include' })
  if (!res.ok) throw new Error('Failed to fetch sync status')
  return res.json()
}

export async function triggerSync(
  mode: 'normal' | 'backfill' = 'normal',
  from_date?: string,
): Promise<{ status: string; job_id: string }> {
  const body: Record<string, string> = { mode }
  if (mode === 'backfill' && from_date) body.from_date = from_date
  const res = await fetch(`${api.baseUrl}/api/v1/sync/trigger`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`Trigger failed: ${res.status}`)
  return res.json()
}
```

### Frontend: `hooks/useSyncStatus.ts` (NEW FILE)

Pattern mirrors `useAuth` — uses React Query, `credentials: 'include'` via `getSyncStatus`.

```typescript
import { useQuery } from '@tanstack/react-query'
import { getSyncStatus } from '@/services/sync'
import type { SyncStatus } from '@/types'

export function useSyncStatus() {
  return useQuery<SyncStatus>({
    queryKey: ['sync', 'status'],
    queryFn: getSyncStatus,
    refetchInterval: (query) => {
      const status = query.state.data?.job_status
      return status === 'running' ? 5_000 : 60_000
    },
    staleTime: 5_000,
  })
}
```

### Frontend: `hooks/index.ts`

Replace file content with re-exports:

```typescript
export { useSyncStatus } from './useSyncStatus'
```

### Frontend: `Header.tsx` Changes

Replace the placeholder `<span>` (currently contains comment "Sync status will go here in Story 2.3"):

```tsx
// Add import at top:
import { useSyncStatus } from '@/hooks'

// Inside Header(), before return:
const { data: syncStatus } = useSyncStatus()

// Replace the placeholder <span>:
<span className="text-sm text-muted-foreground">
  {syncStatus?.job_status === 'running' && (
    <span className="text-blue-500">Sincronizando…</span>
  )}
  {syncStatus?.job_status === 'failed' && (
    <span className="text-destructive" title={syncStatus.error ?? undefined}>
      Error en sync
    </span>
  )}
  {syncStatus?.job_status !== 'running' &&
    syncStatus?.job_status !== 'failed' &&
    syncStatus?.balance_sheet?.last_sync && (
      <span>
        Sync:{' '}
        {new Date(syncStatus.balance_sheet.last_sync).toLocaleDateString('es-CL')}
      </span>
    )}
</span>
```

### Test Patterns (backend — `backend/tests/test_sync.py`)

Follow existing patterns from Stories 2.1/2.2. New tests to add:

**AC1 — backfill mode trigger:**
- `test_sync_trigger_backfill_returns_triggered`: `POST /trigger` with `{"mode":"backfill","from_date":"2021-01-01"}` → 202 + `{status:"triggered"}`
- Patch `backend.app.api.v1.sync.service._run_backfill` (same pattern as `_run_sync` patches)

**AC3 — 422 when from_date missing:**
- `test_sync_trigger_backfill_missing_from_date_returns_422`: `POST /trigger` with `{"mode":"backfill"}` → 422

**AC4 — normal mode default (regression):**
- `test_sync_trigger_no_body_defaults_to_normal`: `POST /trigger` with empty body → 202 (normal mode)

**AC5 — `_run_backfill` sets done state with stats:**
```python
def test_run_backfill_sets_done_state_with_stats():
    import backend.app.api.v1.sync.service as svc
    reset_job_state()
    mock_repo = MagicMock()
    job_id = "backfill-test-job"
    with svc._job_lock:
        svc._current_job.update({"job_id": job_id, "status": "running"})
    with patch("backend.app.api.v1.sync.backfill.run_backfill",
               return_value={"balance_sheet_upserted": 120, "ledger_upserted": 450}):
        svc._run_backfill(job_id, mock_repo, "2021-01-01")
    with svc._job_lock:
        assert svc._current_job["status"] == "done"
        assert svc._current_job["stats"]["balance_sheet_added"] == 120
        assert svc._current_job["stats"]["ledger_added"] == 450
    reset_job_state()
```

**P1 (error path) — `_run_backfill` sets failed state:**
```python
def test_run_backfill_sets_failed_state_on_error():
    import backend.app.api.v1.sync.service as svc
    reset_job_state()
    mock_repo = MagicMock()
    job_id = "backfill-fail-job"
    with svc._job_lock:
        svc._current_job.update({"job_id": job_id, "status": "running"})
    with patch("backend.app.api.v1.sync.backfill.run_backfill",
               side_effect=RuntimeError("API timeout")):
        svc._run_backfill(job_id, mock_repo, "2021-01-01")
    with svc._job_lock:
        assert svc._current_job["status"] == "failed"
        assert svc._current_job["error"] == "API timeout"
        assert svc._current_job["stats"] is None
    reset_job_state()
```

**Backfill unit test — `run_backfill` integration:**
```python
def test_run_backfill_calls_upsert_for_both_sheets():
    """run_backfill() calls repo.upsert_records for balance_sheet and ledger."""
    from backend.app.api.v1.sync.backfill import run_backfill
    mock_repo = MagicMock()
    mock_repo.upsert_records.return_value = []

    with patch("backend.app.api.v1.sync.backfill.fetch_balance_sheet", return_value=[
        {"accountId": 1, "accountNumber": "1-1", "accountName": "Caja",
         "debit": 100, "credit": 0, "debitBalance": 100, "creditBalance": 0}
    ]):
        with patch("backend.app.api.v1.sync.backfill.fetch_ledger", return_value=[]):
            result = run_backfill("2026-04-01", mock_repo)

    assert mock_repo.upsert_records.call_count == 2
    calls = [c.args[0] for c in mock_repo.upsert_records.call_args_list]
    assert "balance_sheet" in calls
    assert "ledger" in calls
    assert "balance_sheet_upserted" in result
    assert "ledger_upserted" in result
```

**Import note:** `run_backfill` patch path is `backend.app.api.v1.sync.backfill.run_backfill` when patching inside `_run_backfill`, and `backend.app.api.v1.sync.backfill.fetch_balance_sheet` etc. when patching inside `run_backfill`.

## Tasks / Subtasks

- [x] Update `backend/app/api/v1/sync/schemas.py` — add `TriggerRequest` (AC: 1, 3)
  - [x] Add `TriggerRequest(mode: Literal["normal","backfill"]="normal", from_date: str | None = None)`
- [x] Create `backend/app/api/v1/sync/backfill.py` — `run_backfill(from_date_str, repo)` (AC: 1, 2)
  - [x] Import from services/, config/, utils/dates.py, models.py — do NOT modify these files
  - [x] Loop month-end dates for Balance Sheet (one call per month)
  - [x] Single Ledger call for full date range
  - [x] Use `repo.upsert_records()` for both sheets
- [x] Update `backend/app/api/v1/sync/service.py` — backfill support (AC: 4, 5)
  - [x] Update `trigger_sync(repo, mode="normal", from_date=None)` to dispatch to `_run_backfill` when `mode="backfill"`
  - [x] Add `_run_backfill(job_id, repo, from_date)` — mirrors `_run_sync` error handling pattern
- [x] Update `backend/app/api/v1/sync/router.py` — optional body on POST /trigger (AC: 1, 3, 4)
  - [x] Accept `TriggerRequest` body with `Body(default=TriggerRequest())`
  - [x] Return 422 when `mode="backfill"` and `from_date` absent
  - [x] Pass `mode` and `from_date` to `trigger_sync()`
- [x] Add backend tests to `backend/tests/test_sync.py` (AC: 1, 3, 4, 5)
  - [x] `test_sync_trigger_backfill_returns_triggered`
  - [x] `test_sync_trigger_backfill_missing_from_date_returns_422`
  - [x] `test_sync_trigger_no_body_defaults_to_normal`
  - [x] `test_run_backfill_sets_done_state_with_stats`
  - [x] `test_run_backfill_sets_failed_state_on_error`
  - [x] `test_run_backfill_calls_upsert_for_both_sheets`
- [x] Update `frontend/src/types/index.ts` — add `DataTypeSyncStatus`, `SyncRunStats`, `SyncStatus` (AC: 6, 7)
- [x] Create `frontend/src/services/sync.ts` — `getSyncStatus()` + `triggerSync()` (AC: 6, 7)
- [x] Create `frontend/src/hooks/useSyncStatus.ts` — adaptive polling hook (AC: 6)
- [x] Update `frontend/src/hooks/index.ts` — re-export `useSyncStatus` (AC: 6)
- [x] Update `frontend/src/components/layout/Header.tsx` — replace placeholder with sync status (AC: 7)

### Review Findings

- [x] [Review][Patch] P1 — `from_date=None` llega a `run_backfill` → TypeError en thread [backfill.py:33, service.py:113]
- [x] [Review][Patch] P2 — `from_date` en el futuro → loop vacío, job "done" con 0 filas silenciosamente [backfill.py:37]
- [x] [Review][Patch] P3 — `map_ledger_row` recibe `item.get("date","")` como `periodo` en lugar de fecha de cierre del sync [backfill.py:58]
- [x] [Review][Patch] P4 — `upsert_records` llamado dentro del loop mensual (36× clear+write) — debe acumularse fuera [backfill.py:39-51]
- [x] [Review][Patch] P5 — Anotación de tipo `_run_backfill(from_date: str)` inconsistente con caller que pasa `str | None` [service.py:113]
- [x] [Review][Patch] P6 — `from_date` sin validación de formato ISO — cadena inválida alcanza thread y produce job failed [schemas.py:28]
- [x] [Review][Defer] D1 — Multi-worker job state not process-safe [service.py] — pre-existente 2.1
- [x] [Review][Defer] D2 — `repo` capturado en thread / lru_cache stale — pre-existente 1.1
- [x] [Review][Defer] D3 — Ledger sin paginación, llamada única — por diseño, igual que sync_api()
- [x] [Review][Defer] D4 — `str(exc)` expuesto en /sync/status — pre-existente 2.1
- [x] [Review][Defer] D5 — Global `_token` race en laudus_service.py — pre-existente
- [x] [Review][Defer] D6 — `query_date` puede llegar como int de Sheets — pre-existente _read_balance_sheet_last_sync
- [x] [Review][Defer] D7 — useSyncStatus 60s sin backoff — MVP scope aceptable

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6 (Amelia)

### Completion Notes

- 26/26 backend tests pass. TypeScript compile clean (0 errors).
- `backfill.py` uses `repo.upsert_records()` — routes cleanly through DataRepository abstraction; no direct gspread calls.
- `router.py` uses `Body(default=TriggerRequest())` so POST /trigger remains backward-compatible with no body (mode defaults to "normal").
- Frontend: `useSyncStatus` adaptive polling via `refetchInterval` callback (5s running / 60s idle) — same pattern as `useAuth` staleTime approach.
- `Header.tsx`: shows "Sincronizando…" (blue) | "Error en sync" (destructive, title=error msg) | "Sync: DD-MM-YYYY" (es-CL locale). No trigger button added — AC7 only requires display.

### Debug Log

No issues. All 26 tests green on first run.

## Story File List

### Files Modified
- `backend/app/api/v1/sync/schemas.py`
- `backend/app/api/v1/sync/service.py`
- `backend/app/api/v1/sync/router.py`
- `backend/tests/test_sync.py`
- `frontend/src/types/index.ts`
- `frontend/src/hooks/index.ts`
- `frontend/src/components/layout/Header.tsx`

### Files Created
- `backend/app/api/v1/sync/backfill.py`
- `frontend/src/services/sync.ts`
- `frontend/src/hooks/useSyncStatus.ts`
