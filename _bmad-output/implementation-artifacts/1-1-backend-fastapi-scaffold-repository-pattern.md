# Story 1.1: Backend FastAPI Scaffold + Repository Pattern

Status: review

## Story

As a developer,
I want a working FastAPI backend scaffold with the Repository pattern implemented,
so that all subsequent stories have a consistent, patterned foundation with storage abstraction from day one.

## Acceptance Criteria

1. Directory structure matches architecture spec: `backend/app/{auth/,api/v1/,repositories/,models/,audit/}/`, `backend/main.py`, `backend/requirements.txt`, `backend/Dockerfile`
2. `GET /api/v1/health` returns `{"status": "ok"}` with HTTP 200
3. `DataRepository` abstract interface defined in `backend/app/repositories/base.py`
4. `SheetsRepository` in `backend/app/repositories/sheets_repository.py` implements all `DataRepository` methods using the existing `gspread_utils.py` — **no gspread import outside `repositories/`**
5. Global error middleware in `backend/app/middleware.py` catches all unhandled exceptions and returns `{"error": {"code": "...", "message": "...", "detail": "..."}}` with appropriate HTTP status
6. CORS configured to accept requests from frontend domain only (env var `FRONTEND_URL`)
7. Auto-generated API docs accessible at `/docs` when server is running
8. All existing pipeline files (`sync.py`, `services/`, `config/`, `utils/`) are **untouched**
9. `backend/requirements.txt` and `Pipfile` updated with new FastAPI dependencies
10. `backend/Dockerfile` builds successfully with `docker build`

## Tasks / Subtasks

- [x] Create backend directory structure (AC: 1)
  - [x] Create `backend/` at repo root
  - [x] Create `backend/app/api/v1/`, `backend/app/auth/`, `backend/app/repositories/`, `backend/app/models/`, `backend/app/audit/`
  - [x] Add `__init__.py` to each package
- [x] Create `backend/main.py` with FastAPI app and router registration (AC: 2, 7)
  - [x] Initialize FastAPI app
  - [x] Register middleware
  - [x] Register health endpoint at `/api/v1/health`
  - [x] Mount v1 router at `/api/v1`
  - [x] Uvicorn entry point in `if __name__ == "__main__"`
- [x] Create global error middleware and CORS (AC: 5, 6)
  - [x] `backend/app/middleware.py` with exception handler returning standard error JSON
  - [x] CORS middleware restricted to `FRONTEND_URL` env var
- [x] Implement `DataRepository` abstract interface (AC: 3)
  - [x] `backend/app/repositories/base.py` — abstract base class with methods:
    - `upsert_records(sheet_name, records, primary_key_func, headers)`
    - `replace_records(sheet_name, records, headers)`
    - `get_records(sheet_name)` → `list[dict]`
- [x] Implement `SheetsRepository` (AC: 4)
  - [x] `backend/app/repositories/sheets_repository.py`
  - [x] Constructor accepts `spreadsheet` object from `gspread_config.py`
  - [x] `upsert_records` delegates to `utils.gspread_utils.upsert_to_sheet`
  - [x] `replace_records` delegates to `utils.gspread_utils.replace_sheet`
  - [x] `get_records` calls `ws.get_all_records()` via spreadsheet
  - [x] **No direct `import gspread` in this file** — use the passed-in spreadsheet object
- [x] Create `backend/requirements.txt` and update `Pipfile` (AC: 9)
  - [x] `fastapi[standard]` (includes uvicorn, pydantic, httpx)
  - [x] `authlib` (for Google OAuth in Story 1.3)
  - [x] `python-jose[cryptography]` (for JWT in Story 1.3)
  - [x] `google-cloud-secret-manager` (for Story 1.5)
  - [x] Retain existing: `requests`, `gspread`, `python-dotenv`, `python-dateutil`
- [x] Create `backend/Dockerfile` (AC: 10)
  - [x] Base image: `python:3.14-slim`
  - [x] Copy `requirements.txt`, install deps
  - [x] Copy app code
  - [x] Expose port 8000
  - [x] CMD: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
- [x] Create `.env.example` at repo root
  - [x] Document: `FRONTEND_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `JWT_SECRET`, `GOOGLE_SHEET_ID`, `GOOGLE_APPLICATION_CREDENTIALS`

## Dev Notes

### Existing Code — DO NOT TOUCH

These files are **off-limits** — they are the working sync pipeline:

```
sync.py                          # pipeline orchestrator
models.py                        # BALANCE_HEADERS, LEDGER_HEADERS, map/enrich functions
services/laudus_service.py       # Laudus API client (token cache, pagination)
services/balance_sheet_service.py
services/ledger_service.py
config/laudus_config.py          # LOGIN_URL, default_headers, payload
config/gspread_config.py         # spreadsheet connection setup
utils/dates.py
utils/gspread_utils.py           # upsert_to_sheet, replace_sheet, safe_write
```

### SheetsRepository Design

`SheetsRepository` wraps `gspread_utils` — do NOT reimplent its logic:

```python
# utils/gspread_utils.py provides:
upsert_to_sheet(spreadsheet, sheet_name, data_list, primary_key_func, headers) -> list[dict]
replace_sheet(spreadsheet, sheet_name, data_list, headers) -> None
safe_write(ws, rows_to_write, backup_rows, sheet_name) -> None  # lower-level, rarely call directly
```

`SheetsRepository.upsert_records(...)` just calls `upsert_to_sheet(self.spreadsheet, ...)`.
The `spreadsheet` object comes from `config/gspread_config.py` — inject it at construction time.

### DataRepository Interface Shape

```python
from abc import ABC, abstractmethod

class DataRepository(ABC):
    @abstractmethod
    def upsert_records(self, sheet_name: str, records: list[dict],
                       primary_key_func, headers: list[str]) -> list[dict]: ...
    @abstractmethod
    def replace_records(self, sheet_name: str, records: list[dict],
                        headers: list[str]) -> None: ...
    @abstractmethod
    def get_records(self, sheet_name: str) -> list[dict]: ...
```

Future stories (Epics 2–3) will add more methods (e.g., `get_balance_sheet(entity, date_range)`). Add only what's needed now.

### API Response Standards (ALL future stories must follow)

```python
# Success
{"data": {...}, "meta": {"last_sync": "2026-04-09T00:00:00Z"}}

# Error (from middleware)
{"error": {"code": "INTERNAL_ERROR", "message": "...", "detail": "..."}}
```

### Error Middleware Pattern

```python
from fastapi import Request
from fastapi.responses import JSONResponse

async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": str(exc), "detail": None}}
    )
```

Register with `app.add_exception_handler(Exception, global_exception_handler)`.
HTTP exceptions (404, 422, etc.) should be handled separately to preserve their status codes.

### Naming Conventions (ALL future stories must follow)

- **Python (backend):** `snake_case` for variables, functions, modules
- **API endpoints:** plural nouns, kebab-case → `GET /api/v1/balance-sheets`, `GET /api/v1/ledger-entries`
- **JSON response fields:** `snake_case` → `{"account_id": 273, "query_date": "2026-03-31"}`
- **NO:** `getBalanceSheet`, `balanceSheet` in endpoints or JSON

### Dependency to Inject (for testing)

Register `SheetsRepository` as a FastAPI dependency so it can be overridden in tests:

```python
# backend/app/dependencies.py
from functools import lru_cache
from backend.app.repositories.sheets_repository import SheetsRepository

@lru_cache
def get_repository() -> SheetsRepository:
    from config.gspread_config import get_spreadsheet  # existing function
    return SheetsRepository(spreadsheet=get_spreadsheet())
```

### Dockerfile Notes

The backend runs from repo root context (not inside `backend/`), so the Dockerfile needs to copy both `backend/` and the existing `services/`, `config/`, `utils/` since `SheetsRepository` imports from them:

```dockerfile
COPY backend/ ./backend/
COPY services/ ./services/
COPY config/ ./config/
COPY utils/ ./utils/
```

### Python Version

Existing `Pipfile` declares `python_version = "3.14"`. Use `python:3.14-slim` in Dockerfile.

### Project Structure Notes

- Repo root is `LAUDUS_Backup/` — backend lives at `LAUDUS_Backup/backend/`
- Existing pipeline files stay at repo root level (not inside `backend/`)
- `SheetsRepository` imports from `utils.gspread_utils` and `config.gspread_config` — these relative imports work when uvicorn runs from repo root: `uvicorn backend.main:app`
- `serviceAccountKey.json` is in `config/` — must NOT be committed; add to `.gitignore`

### References

- Architecture: directory structure → `architecture.md#Complete Project Directory Structure`
- Architecture: naming conventions → `architecture.md#Naming Patterns`
- Architecture: API patterns → `architecture.md#API & Communication Patterns`
- Architecture: repository pattern → `architecture.md#Data Architecture`
- Architecture: error handling → `architecture.md#Process Patterns`
- Existing gspread_utils: `utils/gspread_utils.py` — `upsert_to_sheet`, `replace_sheet`
- Existing gspread config: `config/gspread_config.py`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — clean implementation, all 15 tests passed on first run.

### Completion Notes List

- All 10 ACs satisfied.
- `gspread_config.py` uses `GOOGLE_SHEET_ID` (not `SPREADSHEET_ID`) — `.env.example` corrected to match.
- `*.json` already in `.gitignore` — `serviceAccountKey.json` protected.
- `SheetsRepository` has zero direct gspread imports — confirmed by AST test.
- `get_repository()` uses `lru_cache` for singleton pattern, overridable in tests via `app.dependency_overrides`.
- CORS: `FRONTEND_URL` env var defaults to `http://localhost:5173` for local dev.

### File List

- `backend/__init__.py`
- `backend/main.py`
- `backend/app/__init__.py`
- `backend/app/dependencies.py`
- `backend/app/middleware.py`
- `backend/app/api/__init__.py`
- `backend/app/api/v1/__init__.py`
- `backend/app/api/v1/router.py`
- `backend/app/api/v1/health.py`
- `backend/app/auth/__init__.py`
- `backend/app/repositories/__init__.py`
- `backend/app/repositories/base.py`
- `backend/app/repositories/sheets_repository.py`
- `backend/app/models/__init__.py`
- `backend/app/audit/__init__.py`
- `backend/tests/__init__.py`
- `backend/tests/test_health.py`
- `backend/tests/test_repositories.py`
- `backend/requirements.txt`
- `backend/Dockerfile`
- `.env.example`
- `Pipfile` (updated)
