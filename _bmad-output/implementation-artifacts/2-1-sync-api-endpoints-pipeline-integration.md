# Story 2.1: Sync API Endpoints + Pipeline Integration

Status: done

## Story

As a contador,
I want to trigger a data sync and see its status via the API,
So that financial data can be refreshed on demand and I know when data was last updated.

## Acceptance Criteria

1. `GET /api/v1/sync/status` returns last successful sync timestamp per data type (`balance_sheet`, `ledger`) in ISO 8601 format; if never synced, returns `null` for that data type
2. `POST /api/v1/sync/trigger` (contador only) invokes the existing `sync_api()` pipeline asynchronously; returns immediately with `{"status": "triggered", "job_id": "..."}` — the sync runs in the background
3. `owner` calling `POST /api/v1/sync/trigger` → HTTP 403
4. Unauthenticated calls to either endpoint → HTTP 401
5. After sync completes (success or failure), `GET /sync/status` reflects the latest run timestamp
6. `sync.py`, `services/`, `config/`, `utils/` files are NOT modified

## Tasks / Subtasks

- [x] Create `backend/app/api/v1/sync/` module (AC: 1, 2, 3, 4)
  - [x] `backend/app/api/v1/sync/__init__.py` (empty)
  - [x] `backend/app/api/v1/sync/schemas.py` — Pydantic models: `SyncStatusResponse`, `TriggerResponse`
  - [x] `backend/app/api/v1/sync/service.py` — `SyncService`: in-memory job tracking + background runner
  - [x] `backend/app/api/v1/sync/router.py` — `GET /sync/status` + `POST /sync/trigger`
- [x] Register sync router in `backend/app/api/v1/router.py` (AC: 1, 2)
- [x] Backend: tests `backend/tests/test_sync.py` (AC: 1–6)
  - [x] `GET /sync/status` with no prior sync → `null` timestamps
  - [x] `GET /sync/status` after a sync run → ISO 8601 timestamps
  - [x] `POST /sync/trigger` as `contador` → 200 + `{"status": "triggered", "job_id": "..."}`
  - [x] `POST /sync/trigger` as `owner` → 403
  - [x] `POST /sync/trigger` unauthenticated → 401
  - [x] `GET /sync/status` unauthenticated → 401
  - [x] Background sync job updates status on completion

## Dev Notes

### Critical: What Already Exists — Do NOT Reinvent

**`sync_api()` is the pipeline entry point** — `sync.py` line 1+:
```python
from sync import sync_api  # NOT from services/ — the top-level sync.py
```
Call it exactly as `sync_api()`. It returns `None`, logs to `sync.log` + stdout, and writes to Google Sheets via `gspread_utils`. **Do NOT modify `sync.py`.**

**`date_range` sheet** — `sync.py` writes `{dateTo: "2026-04-10", dateFrom: "2026-04-01"}` after each run. Use `SheetsRepository.get_records("date_range")` to read last sync date. `dateTo` is the last sync date for both `balance_sheet` and `ledger` (single run covers both).

**`get_repository()` dependency** in `backend/app/dependencies.py`:
```python
@lru_cache(maxsize=1)
def get_repository() -> SheetsRepository:
    ...
```
Override in tests via `app.dependency_overrides[get_repository]`.

**`require_role(["contador"])` and `get_current_user()`** already in `backend/app/dependencies.py` — use exactly as in Story 1.4.

**`backend/app/api/v1/router.py`** aggregates all v1 routers — add sync router there, same pattern as auth router.

**`sync/` directory does NOT exist yet** — create it fresh.

### Schemas: `backend/app/api/v1/sync/schemas.py`

```python
"""Pydantic schemas for sync API endpoints."""
from datetime import datetime
from pydantic import BaseModel


class DataTypeSyncStatus(BaseModel):
    last_sync: datetime | None = None


class SyncStatusResponse(BaseModel):
    balance_sheet: DataTypeSyncStatus
    ledger: DataTypeSyncStatus
    job_status: str  # "idle" | "running" | "done" | "failed"
    job_id: str | None = None


class TriggerResponse(BaseModel):
    status: str  # always "triggered"
    job_id: str
```

### Service: `backend/app/api/v1/sync/service.py`

The service holds an **in-memory job tracker** (acceptable for MVP — 2-3 users, no concurrency). Persistent last-sync date comes from the `date_range` Google Sheet.

```python
"""Sync orchestration service — job tracking + background runner."""
import logging
import threading
from datetime import datetime, timezone
from uuid import uuid4

from backend.app.repositories.base import DataRepository

logger = logging.getLogger(__name__)

# In-memory job state — volatile (lost on Cloud Run restart, acceptable for MVP)
_current_job: dict = {
    "job_id": None,
    "status": "idle",   # idle | running | done | failed
    "started_at": None,
    "completed_at": None,
    "error": None,
}
_job_lock = threading.Lock()


def get_sync_status(repo: DataRepository) -> dict:
    """Return current sync status: last sync dates + current job state."""
    last_sync = _read_last_sync_date(repo)
    with _job_lock:
        return {
            "balance_sheet": {"last_sync": last_sync},
            "ledger": {"last_sync": last_sync},
            "job_status": _current_job["status"],
            "job_id": _current_job["job_id"],
        }


def trigger_sync(repo: DataRepository) -> str:
    """Start sync_api() in a background thread. Returns job_id.

    If a sync is already running, raises ValueError.
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
        })

    thread = threading.Thread(target=_run_sync, args=(job_id,), daemon=True)
    thread.start()
    return job_id


def _run_sync(job_id: str) -> None:
    """Execute sync_api() in background thread, update job state on completion."""
    try:
        from sync import sync_api  # top-level sync.py
        sync_api()
        with _job_lock:
            if _current_job["job_id"] == job_id:
                _current_job.update({
                    "status": "done",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
    except Exception as exc:
        logger.error("Background sync failed: %s", exc, exc_info=True)
        with _job_lock:
            if _current_job["job_id"] == job_id:
                _current_job.update({
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(exc),
                })


def _read_last_sync_date(repo: DataRepository) -> datetime | None:
    """Read last sync date from date_range sheet. Returns None if never synced."""
    try:
        records = repo.get_records("date_range")
        if not records:
            return None
        # Most recent record: sort by dateTo descending
        latest = max(records, key=lambda r: str(r.get("dateTo", "")))
        date_str = str(latest.get("dateTo", ""))
        if not date_str:
            return None
        # Parse date string — sync.py writes "YYYY-MM-DD" format
        return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    except Exception:
        return None
```

**Critical design notes:**
- `threading.Thread(daemon=True)` — daemon threads die with the process (correct for Cloud Run)
- `_job_lock` — protects `_current_job` dict from concurrent access
- `from sync import sync_api` is a **deferred import inside the thread** — this avoids import-time side effects and works with the existing Python path setup
- Only one sync can run at a time — returns 409 if already running (see router)
- `_read_last_sync_date` silently returns `None` on any Sheet error (read-only, safe)

### Router: `backend/app/api/v1/sync/router.py`

```python
"""Sync API router — GET /sync/status, POST /sync/trigger."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from backend.app.api.v1.sync.schemas import SyncStatusResponse, TriggerResponse, DataTypeSyncStatus
from backend.app.api.v1.sync.service import get_sync_status, trigger_sync
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import get_current_user, get_repository, require_role
from backend.app.repositories.base import DataRepository

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/status", response_model=SyncStatusResponse)
def sync_status(
    user: UserSession = Depends(get_current_user),
    repo: DataRepository = Depends(get_repository),
) -> SyncStatusResponse:
    """Return last sync timestamp per data type and current job status."""
    state = get_sync_status(repo)
    return SyncStatusResponse(
        balance_sheet=DataTypeSyncStatus(last_sync=state["balance_sheet"]["last_sync"]),
        ledger=DataTypeSyncStatus(last_sync=state["ledger"]["last_sync"]),
        job_status=state["job_status"],
        job_id=state["job_id"],
    )


@router.post("/trigger", response_model=TriggerResponse, status_code=200)
def sync_trigger(
    user: UserSession = Depends(require_role(["contador"])),
    repo: DataRepository = Depends(get_repository),
) -> TriggerResponse:
    """Trigger an async sync run. Returns job_id immediately."""
    try:
        job_id = trigger_sync(repo)
    except ValueError:
        raise HTTPException(status_code=409, detail="Sync already running")
    return TriggerResponse(status="triggered", job_id=job_id)
```

**Note:** `BackgroundTasks` is NOT used here — the thread is started inside `trigger_sync()` directly. FastAPI's `BackgroundTasks` runs after the response is sent but is still in the same worker process/thread pool — for a long-running sync (30+ seconds), `threading.Thread` is more robust.

### Register Router: `backend/app/api/v1/router.py`

```python
"""Aggregates all v1 API routers."""
from fastapi import APIRouter

from backend.app.api.v1.health import router as health_router
from backend.app.auth.router import router as auth_router
from backend.app.api.v1.sync.router import router as sync_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(sync_router)
```

### Testing: `backend/tests/test_sync.py`

Use the same mini-app pattern. Mock `get_repository` via `app.dependency_overrides`. Mock `sync_api` via `unittest.mock.patch` to avoid executing the real pipeline in tests.

```python
"""Tests for sync API endpoints — Story 2.1."""
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.sync.router import router as sync_router
from backend.app.auth.service import create_jwt
from backend.app.dependencies import get_current_user, get_repository, require_role
from backend.app.middleware import add_middleware


def make_sync_test_app(mock_repo=None) -> TestClient:
    """Mini FastAPI app with sync router and mocked repository."""
    app = FastAPI()
    add_middleware(app)
    app.include_router(sync_router, prefix="/api/v1")

    if mock_repo:
        app.dependency_overrides[get_repository] = lambda: mock_repo

    return TestClient(app, raise_server_exceptions=False)


def make_mock_repo(date_range_records=None):
    """Return a MagicMock repository with configurable date_range data."""
    repo = MagicMock()
    repo.get_records.return_value = date_range_records or []
    return repo


def contador_cookie():
    return create_jwt(email="contador@test.com", role="contador")

def owner_cookie():
    return create_jwt(email="owner@test.com", role="owner")


# ── GET /sync/status ──────────────────────────────────────────────────────

def test_sync_status_unauthenticated():
    client = make_sync_test_app(mock_repo=make_mock_repo())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 401

def test_sync_status_no_prior_sync():
    """AC1: never synced → null timestamps."""
    client = make_sync_test_app(mock_repo=make_mock_repo(date_range_records=[]))
    client.cookies.set("access_token", contador_cookie())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["balance_sheet"]["last_sync"] is None
    assert data["ledger"]["last_sync"] is None

def test_sync_status_with_prior_sync():
    """AC1: prior sync → ISO 8601 timestamps."""
    mock_repo = make_mock_repo(date_range_records=[{"dateTo": "2026-04-10", "dateFrom": "2026-04-01"}])
    client = make_sync_test_app(mock_repo=mock_repo)
    client.cookies.set("access_token", contador_cookie())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["balance_sheet"]["last_sync"] is not None
    assert "2026-04-10" in data["balance_sheet"]["last_sync"]
    assert data["ledger"]["last_sync"] is not None

def test_sync_status_owner_can_read():
    """GET /sync/status is accessible to owner (read endpoint)."""
    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", owner_cookie())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200


# ── POST /sync/trigger ────────────────────────────────────────────────────

def test_sync_trigger_unauthenticated():
    client = make_sync_test_app(mock_repo=make_mock_repo())
    response = client.post("/api/v1/sync/trigger")
    assert response.status_code == 401

def test_sync_trigger_owner_forbidden():
    """AC3: owner → 403."""
    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", owner_cookie())
    response = client.post("/api/v1/sync/trigger")
    assert response.status_code == 403

def test_sync_trigger_contador_returns_job_id():
    """AC2: contador → 200 + {status: triggered, job_id: ...}."""
    with patch("backend.app.api.v1.sync.service._run_sync"):
        client = make_sync_test_app(mock_repo=make_mock_repo())
        client.cookies.set("access_token", contador_cookie())
        response = client.post("/api/v1/sync/trigger")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "triggered"
    assert "job_id" in data
    assert len(data["job_id"]) > 0

def test_sync_trigger_response_is_immediate():
    """AC2: trigger returns before sync completes (non-blocking)."""
    import time

    def slow_sync(job_id):
        time.sleep(5)  # simulate slow sync — should not block response

    with patch("backend.app.api.v1.sync.service._run_sync", side_effect=slow_sync):
        # Note: we patch _run_sync but the thread is still started — just patched to be slow
        # This test verifies the endpoint returns quickly
        client = make_sync_test_app(mock_repo=make_mock_repo())
        client.cookies.set("access_token", contador_cookie())
        start = time.monotonic()
        # Reset job state first
        import backend.app.api.v1.sync.service as svc
        svc._current_job["status"] = "idle"
        response = client.post("/api/v1/sync/trigger")
        elapsed = time.monotonic() - start
    assert response.status_code == 200
    assert elapsed < 2.0  # must return in under 2 seconds
```

**Critical testing rules:**
- Always patch `_run_sync` (not `sync_api`) to prevent actual pipeline execution in tests
- Reset `_current_job["status"] = "idle"` between tests that call trigger (module-level state persists)
- Mock `get_repository` with `app.dependency_overrides[get_repository] = lambda: mock_repo`

### What NOT to Do

- **Do NOT modify `sync.py`** — call `from sync import sync_api` and invoke as-is
- **Do NOT modify `services/`, `config/`, `utils/`** — these are the existing pipeline
- **Do NOT use FastAPI `BackgroundTasks`** for the sync — use `threading.Thread` (sync is long-running, 30+ seconds)
- **Do NOT use `asyncio.run()`** inside the thread — `sync_api()` is synchronous
- **Do NOT add a new Google Sheet** just for status tracking — read from existing `date_range` sheet
- **Do NOT add PATCH endpoint** — only GET and POST per spec
- **Do NOT apply `require_role` to GET /sync/status** — both owner and contador can read status
- **Do NOT import `gspread` directly** in any new file — use `SheetsRepository.get_records()`

### Story 2.1 Implementation Sequence

1. Create schemas (no dependencies)
2. Create service (`SyncService` — no FastAPI imports)
3. Create router (imports schemas + service)
4. Register router in `api/v1/router.py`
5. Write tests (mock repo + mock `_run_sync`)
6. Run full test suite — 47 existing + new sync tests must all pass

### Environment Variables

No new env vars needed. All existing ones apply:
- `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRE_HOURS` — auth middleware
- `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_SHEET_ID` — SheetsRepository (real calls only, mocked in tests)

## Story 1.5 Learnings (Apply Here)

- `app.dependency_overrides[get_repository] = lambda: mock_repo` is the correct pattern for mocking the repository in tests
- `TestClient(app, raise_server_exceptions=False)` + `add_middleware()` for consistent error formatting
- `frozenset` for immutable method/role sets
- Bare `except Exception` acceptable in service infrastructure for resilience — not in endpoint handlers
- `create_jwt(email, role)` from `backend.app.auth.service` for test token generation
- In-memory module-level state persists across tests in the same pytest session — reset it explicitly in tests or use fixtures

## Senior Developer Review (AI)

**Review Date:** 2026-04-11
**Outcome:** Changes Requested
**Layers:** Blind Hunter + Edge Case Hunter + Acceptance Auditor

### Review Findings

- [x] [Review][Patch] P1 (LOW) `error` field de sync failure no expuesto en `SyncStatusResponse` — cliente solo ve `job_status: "failed"` sin diagnóstico [`backend/app/api/v1/sync/schemas.py`, `backend/app/api/v1/sync/service.py`]
- [x] [Review][Patch] P2 (LOW) `job_status` tipado como `str` sin enforcement — usar `Literal["idle", "running", "done", "failed"]` [`backend/app/api/v1/sync/schemas.py`]
- [x] [Review][Patch] P3 (LOW) `POST /trigger` retorna `200` — semánticamente debe ser `202 Accepted` para operaciones async [`backend/app/api/v1/sync/router.py`]
- [x] [Review][Patch] P4 (LOW) Sin test para `job_status="failed"` visible en `GET /sync/status` [`backend/tests/test_sync.py`]
- [x] [Review][Defer] Global mutable state no process-safe en multi-worker — deferred, MVP con 1 worker uvicorn; documentado en story spec como aceptable
- [x] [Review][Defer] `from sync import sync_api` import path-dependent — deferred, by spec design; repo root en sys.path; deferred import intencional
- [x] [Review][Defer] Daemon thread muere en container restart → stale "running" — deferred, SIGTERM kills daemon threads; MVP architectural decision aceptable para 2-3 usuarios
- [x] [Review][Defer] `balance_sheet` y `ledger` comparten mismo `last_sync` — deferred, by story spec Dev Notes; "dateTo covers both types, single run"; Story 2.2 agrega per-type tracking
- [x] [Review][Defer] Timestamp es date range (dateTo), no run time — deferred, by story spec Dev Notes design explícito
- [x] [Review][Defer] Silent exception swallowing en `_read_last_sync_date` — deferred, patrón consistente en el proyecto (audit middleware); best-effort read
- [x] [Review][Defer] No rate limiting en /trigger — deferred, MVP scope; 2-3 usuarios internos
- [x] [Review][Defer] Thread no almacenado sin join/cancel — deferred, daemon fire-and-forget correcto para este patrón

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Completion Notes List

- All 6 ACs satisfied. Backend: 59/59 tests passing (12 new in test_sync.py).
- `backend/app/api/v1/sync/` module created with 4 files: `__init__.py`, `schemas.py`, `service.py`, `router.py`.
- `service.py` uses module-level `_current_job` dict + `threading.Lock` for thread-safe in-memory job tracking.
- Background sync uses `threading.Thread(daemon=True)` — deferred import of `sync_api` inside thread to avoid import-time side effects.
- `_read_last_sync_date` reads `date_range` sheet via `SheetsRepository` — same sheet `sync.py` already writes. Picks most recent `dateTo` via `max()`.
- `sync.py` NOT modified (AC6).
- Concurrent trigger protection: 409 if `status == "running"`.
- Tests mock `_run_sync` (not `sync_api`) to prevent actual pipeline execution. `reset_job_state()` helper clears module-level state between tests.

### File List

- `backend/app/api/v1/sync/__init__.py` (new — empty package)
- `backend/app/api/v1/sync/schemas.py` (new — `DataTypeSyncStatus`, `SyncStatusResponse`, `TriggerResponse`)
- `backend/app/api/v1/sync/service.py` (new — `get_sync_status`, `trigger_sync`, `_run_sync`, `_read_last_sync_date`)
- `backend/app/api/v1/sync/router.py` (new — `GET /sync/status`, `POST /sync/trigger`)
- `backend/app/api/v1/router.py` (modified — added sync router import and registration)
- `backend/tests/test_sync.py` (new — 12 tests covering all ACs)
