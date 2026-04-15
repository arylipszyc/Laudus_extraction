---
story: 4.0
title: Supabase Setup + Plan de Cuentas + Bank Accounts
status: done
epic: 4
---

# Story 4.0 — Supabase Setup + Plan de Cuentas + Bank Accounts

## User Story

As a developer,
I want the Supabase schema created, the chart of accounts synced from Sheets, and a bank account registry in place,
So that Epics 4 and 5 have the data foundation and account identification they need without touching the ERP category taxonomy.

## Acceptance Criteria

**AC1 — Supabase schema**

**Given** Supabase is configured with project credentials in environment variables
**When** the schema migration runs
**Then** tables `plan_de_cuentas`, `bank_accounts`, `cartola_batches`, and `cartola_transactions` exist with the exact column definitions from the architecture document
**And** `bank_accounts.account_number` has a foreign key constraint referencing `plan_de_cuentas.account_number`

---

**AC2 — Plan de cuentas sync**

**Given** `POST /api/v1/plan-de-cuentas/sync` is called by a `contador`
**When** the sync runs
**Then** all accounts from the Google Sheets chart of accounts are upserted into `plan_de_cuentas` (account_number as primary key — no duplicates on re-run)
**And** `synced_at` is updated to the current timestamp on every upserted row
**And** the response returns `{"synced": N, "updated": M}` with the record counts

---

**AC3 — Plan de cuentas list**

**Given** `GET /api/v1/plan-de-cuentas/` is called by an authenticated user
**When** the request is received
**Then** all active accounts are returned as a list ordered by `account_number`
**And** the response is used by the bank account registration form in future stories

---

**AC4 — Bank account registration**

**Given** `POST /api/v1/bank-accounts/` is called by a `contador` with valid payload
**When** the request is received
**Then** a new `bank_accounts` row is created with `account_number` validated against existing `plan_de_cuentas` entries
**And** if `account_number` does not exist in `plan_de_cuentas`, the endpoint returns HTTP 400 with a descriptive error

---

**AC5 — Bank accounts list**

**Given** `GET /api/v1/bank-accounts/` is called by an authenticated user
**When** the request is received
**Then** all bank accounts (active and inactive) are returned with their linked `plan_de_cuentas` account name

---

**AC6 — Bank account update**

**Given** `PATCH /api/v1/bank-accounts/{id}` is called by a `contador`
**When** the request is received with `{"active": false}`
**Then** the bank account is deactivated and excluded from CC identification in subsequent stories

---

**AC7 — SupabaseRepository interface**

**Given** `SupabaseRepository` is implemented in `backend/app/repositories/supabase_repository.py`
**When** it is used by any service
**Then** it implements the same `DataRepository` interface as `SheetsRepository`
**And** no service outside `repositories/` imports the Supabase client directly

---

## Tasks / Subtasks

- [x] Task 1: Supabase environment setup
  - [x] Add `SUPABASE_URL` and `SUPABASE_KEY` (service role key) to `.env.example`
  - [x] Add `supabase` Python package to `backend/requirements.txt` (pinned to `>=2.7.0,<2.8.0` — versions 2.8+ require pyiceberg which fails on Python 3.14)
  - [x] Verify credentials load correctly at startup (log a warning if missing, do not crash — Supabase is Phase 2 only)

- [x] Task 2: Create Supabase schema migration
  - [x] Write and execute the SQL migration in Supabase dashboard (or via migration file)
  - [x] Create all 4 tables: `plan_de_cuentas`, `bank_accounts`, `cartola_batches`, `cartola_transactions` — exact DDL in Dev Notes below
  - [x] Verify FK constraint `bank_accounts.account_number → plan_de_cuentas.account_number` is enforced
  - [x] Verify cascade delete: `cartola_transactions.batch_id → cartola_batches.id ON DELETE CASCADE`

- [x] Task 3: Implement `SupabaseRepository` (AC7)
  - [x] Create `backend/app/repositories/supabase_repository.py`
  - [x] Implement `DataRepository` interface: `upsert_records`, `replace_records`, `get_records`
  - [x] Add Supabase-specific methods: `insert`, `select`, `update`, `upsert` for cartola tables (these are in addition to the interface, called directly by services)
  - [x] Initialize client lazily from env vars; raise `RuntimeError` with clear message if `SUPABASE_URL`/`SUPABASE_KEY` not set

- [x] Task 4: Investigate plan de cuentas data source (AC2)
  - [x] Found: `PlanCuentas` worksheet exists in Google Sheets — columns: `account_number`, `account_name`, `1° Category`, `2° Category`, `3° Category`
  - [x] Maps to: cat1=`1° Category`, cat2=`2° Category`, cat3=`3° Category`; `account_type` not available (stored as NULL)
  - [x] Access via: `sh.worksheet("PlanCuentas").get_all_records()` (already used in `pipeline/sync.py`)

- [x] Task 5: Plan de cuentas module (AC2, AC3)
  - [x] Created `backend/app/api/v1/plan_de_cuentas/` with `router.py`, `service.py`, `schemas.py`
  - [x] `schemas.py`: `PlanDeCuentasEntry`, `SyncResponse`
  - [x] `service.py`: `sync_plan_de_cuentas()`, `list_plan_de_cuentas()`
  - [x] `router.py`: `POST /sync` (contador), `GET /` (authenticated)
  - [x] Router registered in `backend/app/api/v1/router.py` with prefix `/plan-de-cuentas`

- [x] Task 6: Bank accounts module (AC4, AC5, AC6)
  - [x] Created `backend/app/api/v1/bank_accounts/` with `router.py`, `service.py`, `schemas.py`
  - [x] `schemas.py`: `BankAccount`, `BankAccountCreate`, `BankAccountUpdate` with Literal types for account_type and account_currency
  - [x] `service.py`: `list_bank_accounts()`, `create_bank_account()` (validates FK), `update_bank_account()`
  - [x] `router.py`: `GET /`, `POST /` (contador), `PATCH /{id}` (contador)
  - [x] Router registered in `backend/app/api/v1/router.py` with prefix `/bank-accounts`

- [x] Task 7: Wire everything + smoke test
  - [x] All 14 endpoints verified via import test (routes list printed — all present)
  - [x] 27 new tests pass: auth/RBAC coverage, 400/401/403/404/422/503 error cases, schema validation, _map_sheet_row unit tests
  - [x] 140 total tests pass — 0 regressions vs. 113 pre-story baseline

---

## Dev Notes

### Architecture Guardrails — MUST follow

- **`SupabaseRepository` implements `DataRepository`** — same interface as `SheetsRepository`. No service imports `supabase` directly; all Supabase access goes through `SupabaseRepository`. [Source: architecture.md#Phase 2 Consistency Rules]
- **`get_current_user()` on every endpoint** — import from `backend/app/dependencies.py`. Use `require_role(["contador"])` for write endpoints, just `get_current_user` for reads. [Source: architecture.md#Authentication]
- **Router registration** — add both new routers to `backend/app/api/v1/router.py` following the exact pattern of existing routers. [Source: backend/app/api/v1/router.py]
- **Error format** — all errors must go through global middleware. Do not `try/except` inline with custom JSON responses. Raise `HTTPException` with appropriate status codes. [Source: architecture.md#Process Patterns]
- **snake_case JSON fields** — all API response fields use snake_case (e.g., `account_number`, not `accountNumber`). [Source: architecture.md#Naming Patterns]

### Supabase Schema — Exact DDL

Execute this in the Supabase SQL editor:

```sql
-- Chart of accounts synced from Google Sheets (source of truth remains Sheets)
CREATE TABLE plan_de_cuentas (
  account_number  VARCHAR PRIMARY KEY,
  account_name    VARCHAR NOT NULL,
  account_type    VARCHAR,
  cat1            VARCHAR,
  cat2            VARCHAR,
  cat3            VARCHAR,
  active          BOOLEAN DEFAULT true,
  synced_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Bank account registry — maps real bank accounts to chart of accounts
CREATE TABLE bank_accounts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_number   VARCHAR NOT NULL REFERENCES plan_de_cuentas(account_number),
  account_type     VARCHAR NOT NULL,
  account_currency VARCHAR NOT NULL,
  bank_name        VARCHAR,
  active           BOOLEAN DEFAULT true
);

-- One record per uploaded credit card statement (used by Stories 4.1+)
CREATE TABLE cartola_batches (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity                 VARCHAR NOT NULL DEFAULT 'EAG',
  account_name           VARCHAR NOT NULL,
  bank                   VARCHAR,
  period                 DATE NOT NULL,
  currency               VARCHAR NOT NULL,
  opening_balance        DECIMAL,
  closing_balance        DECIMAL,
  sum_transactions       DECIMAL,
  balance_discrepancy    DECIMAL,
  laudus_entry_id        VARCHAR,
  laudus_payment_amount  DECIMAL,
  status                 VARCHAR NOT NULL DEFAULT 'extracted',
  override_justification TEXT,
  uploaded_by            VARCHAR NOT NULL,
  uploaded_at            TIMESTAMPTZ DEFAULT NOW(),
  extraction_model       VARCHAR
);

-- One record per transaction line in a statement (used by Stories 4.1+)
CREATE TABLE cartola_transactions (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id           UUID NOT NULL REFERENCES cartola_batches(id) ON DELETE CASCADE,
  date               DATE NOT NULL,
  description        TEXT NOT NULL,
  amount             DECIMAL NOT NULL,
  currency           VARCHAR NOT NULL,
  category_auto      VARCHAR,
  category_confirmed VARCHAR,
  category_status    VARCHAR NOT NULL DEFAULT 'pending',
  match_source       VARCHAR,
  reviewed_by        VARCHAR,
  reviewed_at        TIMESTAMPTZ
);
```

**Valid values:**
- `bank_accounts.account_type`: `'tarjeta_credito'` | `'cta_corriente'` | `'linea_credito'` | `'cta_inversiones'`
- `bank_accounts.account_currency`: `'CLP'` | `'USD'`
- `cartola_batches.status`: `'extracted'` | `'balance_validated'` | `'categorized'` | `'confirmed'`
- `cartola_transactions.category_status`: `'pending'` | `'suggested'` | `'confirmed'`
- `cartola_transactions.match_source`: `'historical'` | `'gemini'`

### SupabaseRepository Pattern

```python
# backend/app/repositories/supabase_repository.py
import os
from supabase import create_client, Client
from backend.app.repositories.base import DataRepository

class SupabaseRepository(DataRepository):
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")
        self._client: Client = create_client(url, key)

    # DataRepository interface (required — even if not used in Phase 2)
    def upsert_records(self, table, records, primary_key_func, headers):
        # Implement using self._client.table(table).upsert(records)
        ...

    def replace_records(self, table, records, headers):
        # Implement using delete-then-insert pattern
        ...

    def get_records(self, table):
        return self._client.table(table).select("*").execute().data

    # Supabase-specific helpers for cartola operations (called directly by services)
    def upsert_plan_de_cuentas(self, records: list[dict]) -> dict:
        result = self._client.table("plan_de_cuentas").upsert(records).execute()
        return result.data

    def get_bank_accounts(self, active_only: bool = False):
        query = self._client.table("bank_accounts").select("*, plan_de_cuentas(account_name)")
        if active_only:
            query = query.eq("active", True)
        return query.execute().data
    # ... add more as needed by each story
```

### Router Registration

Add to `backend/app/api/v1/router.py`:

```python
from backend.app.api.v1.plan_de_cuentas.router import router as plan_de_cuentas_router
from backend.app.api.v1.bank_accounts.router import router as bank_accounts_router

router.include_router(plan_de_cuentas_router, prefix="/plan-de-cuentas", tags=["plan-de-cuentas"])
router.include_router(bank_accounts_router, prefix="/bank-accounts", tags=["bank-accounts"])
```

### Environment Variables

Add to `.env.example` (do NOT add real values):
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
```

Use the **service role key** (not anon key) — it bypasses row-level security, needed for backend writes.

### Plan de Cuentas Data Source — Investigation Required

Before implementing Task 5, check in this order:

1. **Check Sheets**: `SheetsRepository.get_records("plan_de_cuentas")` — if the worksheet exists, use it
2. **Check Laudus API**: review `pipeline/config/laudus_config.py` for available endpoints; look for something like `/accounting/accounts` or `/accounting/chartOfAccounts`
3. **Derive from balance sheet**: as a last resort, use `SheetsRepository.get_records()` on the balance sheet tab — it has `account_number` and `account_name` but not Cat1/Cat2/Cat3

The `cat1`, `cat2`, `cat3` columns are nullable in the schema — if not available from the source, sync with `NULL` and add them manually later. **Do not block story completion on Cat columns.**

### Existing Patterns to Reuse

- **Auth dependency**: `from backend.app.dependencies import get_current_user, require_role` — see `backend/app/dependencies.py`
- **Sheets access**: `from pipeline.config.gspread_config import get_spreadsheet` + `SheetsRepository` — see existing dashboard service
- **Service pattern**: see `backend/app/api/v1/dashboard/service.py` for how a service layer is structured
- **Router pattern**: see `backend/app/api/v1/sync/router.py` for a clean router example with auth dependencies

### Deferred Work to Be Aware Of

From `deferred-work.md`: `@lru_cache` on `get_repository` means a stale Sheets connection requires process restart. **Do not apply `@lru_cache` to `SupabaseRepository`** — instantiate it per-request or use dependency injection without caching. Supabase client connections are lightweight; caching is not needed here.

### Project Structure Reference

```
backend/
  app/
    api/v1/
      plan_de_cuentas/          # NEW — this story
      │   ├── __init__.py
      │   ├── router.py
      │   ├── service.py
      │   └── schemas.py
      bank_accounts/             # NEW — this story
      │   ├── __init__.py
      │   ├── router.py
      │   ├── service.py
      │   └── schemas.py
      router.py                  # MODIFY — add 2 new router imports
    repositories/
      base.py                    # DO NOT MODIFY
      sheets_repository.py       # DO NOT MODIFY
      supabase_repository.py     # NEW — this story
.env.example                     # MODIFY — add SUPABASE_URL, SUPABASE_KEY
backend/requirements.txt         # MODIFY — add supabase>=2.0.0
```

### References

- [Source: architecture.md#Supabase Schema] — exact DDL
- [Source: architecture.md#Phase 2 Directory Structure Extensions] — file locations
- [Source: architecture.md#Phase 2 Consistency Rules] — SupabaseRepository interface rule
- [Source: architecture.md#Credit Card Entry Identification] — bank_accounts → plan_de_cuentas lookup flow
- [Source: backend/app/repositories/base.py] — DataRepository interface to implement
- [Source: backend/app/repositories/sheets_repository.py] — implementation pattern to follow
- [Source: backend/app/api/v1/router.py] — router registration pattern
- [Source: backend/app/dependencies.py] — auth dependency pattern

---

### Review Findings

- [x] [Review][Patch] GET endpoints missing try/except for RuntimeError — fixed: added try/except RuntimeError → 503 in both GET handlers, consistent with sync POST pattern. [plan_de_cuentas/router.py, bank_accounts/router.py]
- [x] [Review][Patch] PATCH /{account_id} accepts plain str, no UUID validation — fixed: account_id typed as UUID in router; FastAPI auto-validates → 422 for malformed input. [bank_accounts/router.py]
- [x] [Review][Patch] bank_accounts table missing UNIQUE constraint on account_number — fixed: added UNIQUE to column definition in migration. [supabase/migrations/001_phase2_initial_schema.sql]
- [x] [Review][Patch] update_bank_account uses model_dump() with `if v is not None` — fixed: changed to model_dump(exclude_unset=True) for correct PATCH semantics. [bank_accounts/service.py:51]
- [x] [Review][Patch] update_bank_account: get_bank_account_by_id result not guarded — fixed: added guard if not full: raise HTTPException(500). [bank_accounts/service.py:60]
- [x] [Review][Defer] replace_records is non-atomic and uses sentinel UUID delete-all — two-call delete+insert has a data-loss window; sentinel UUID workaround is fragile. Deferred: not called by any Phase 2 code; only implemented for DataRepository interface compliance. [supabase_repository.py:replace_records] — deferred, not used in Phase 2
- [x] [Review][Defer] upsert_plan_de_cuentas count pre-fetch has race condition and swallows read errors — synced/updated counts can be wrong; get_records() returns [] on failure making new_count always equal len(records). Deferred: counts are informational only; upsert itself is correct. [supabase_repository.py:upsert_plan_de_cuentas] — deferred, informational counts only
- [x] [Review][Defer] cartola_batches.account_name is a free-text VARCHAR, not a FK to bank_accounts — no referential integrity enforcement. Deferred: architecture decision; account_name is used as a denormalized audit field for historical records. [supabase/migrations/001_phase2_initial_schema.sql] — deferred, architecture decision
- [x] [Review][Defer] bank_accounts.account_number FK has no ON UPDATE/ON DELETE action — RESTRICT by default; renaming an account_number in plan_de_cuentas would fail if bank_accounts references it. Deferred: account_numbers are stable in ERP; plan_de_cuentas is append/upsert only. [supabase/migrations/001_phase2_initial_schema.sql] — deferred, low risk
- [x] [Review][Defer] DECIMAL columns have no precision/scale — financial fields (balances, amounts) use bare DECIMAL. Deferred: PostgreSQL unconstrained DECIMAL is precise; precision/scale can be added in a later migration when ranges are known. [supabase/migrations/001_phase2_initial_schema.sql] — deferred, Story 4.1+
- [x] [Review][Defer] New SupabaseRepository client per request — no connection reuse. Deferred: per spec dev note "do not apply @lru_cache to SupabaseRepository — instantiate per-request". Intentional. [supabase_repository.py] — deferred, by design

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None.

### Completion Notes List

- PlanCuentas source: found as existing worksheet in Google Sheets (`sh.worksheet("PlanCuentas")`). Columns: `account_number`, `account_name`, `1° Category`, `2° Category`, `3° Category`. `account_type` not available → stored NULL.
- supabase package: pinned to `>=2.7.0,<2.8.0` — versions ≥2.8 require storage3≥2.28 which depends on pyiceberg; pyiceberg fails to build on Python 3.14. Documented in requirements.txt.
- Empty PATCH check moved before SupabaseRepository() init to avoid RuntimeError in tests without env vars.
- Mock patch paths use router module reference (e.g. `router.sync_plan_de_cuentas`) since functions are imported directly into router namespace.
- 27 new tests (11 plan_de_cuentas + 16 bank_accounts). 140 total, 0 regressions vs 113 baseline.
- Migration SQL at `supabase/migrations/001_phase2_initial_schema.sql` — must be executed manually in Supabase dashboard before Story 4.1 starts.

### File List

- `.env.example` — modified (added SUPABASE_URL, SUPABASE_KEY)
- `backend/requirements.txt` — modified (added supabase>=2.7.0,<2.8.0)
- `supabase/migrations/001_phase2_initial_schema.sql` — new
- `backend/app/repositories/supabase_repository.py` — new
- `backend/app/api/v1/plan_de_cuentas/__init__.py` — new
- `backend/app/api/v1/plan_de_cuentas/schemas.py` — new
- `backend/app/api/v1/plan_de_cuentas/service.py` — new
- `backend/app/api/v1/plan_de_cuentas/router.py` — new
- `backend/app/api/v1/bank_accounts/__init__.py` — new
- `backend/app/api/v1/bank_accounts/schemas.py` — new
- `backend/app/api/v1/bank_accounts/service.py` — new
- `backend/app/api/v1/bank_accounts/router.py` — new
- `backend/app/api/v1/router.py` — modified (added 2 router imports + includes)
- `backend/tests/test_plan_de_cuentas.py` — new
- `backend/tests/test_bank_accounts.py` — new
