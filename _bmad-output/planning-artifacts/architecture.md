---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
status: complete
completedAt: '2026-04-08'
phase2AddedAt: '2026-04-14'
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/prd-validation-report.md
workflowType: 'architecture'
project_name: 'LAUDUS_Backup'
user_name: 'Ary'
date: '2026-04-08'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:** 44 FRs across 8 functional groups — Auth & Access Control (FR1–5), ERP Sync (FR6–11), Dashboards (FR12–19), Bank Statement Ingestion (FR20–27), Categorization (FR28–31), Reconciliation (FR32–35), Collaboration (FR36–41), Alerts (FR42–44). MVP scope covers FR1–19 only.

**Non-Functional Requirements:** 19 NFRs across Performance (3s initial load, 2s filter interaction, async operations), Security (HTTPS, server-side RBAC, no public endpoints, 8h session timeout), Reliability (error logging, no partial data states, append-only audit log, daily Sheets backup), and Integration (storage abstraction, single Gemini integration point, Google OAuth only).

**Scale & Complexity:**

- Primary domain: Full-stack web application + data pipeline + AI integration
- Complexity level: Medium-High
- Estimated architectural components: 6–8
- Two distinct user workflows: Owner (read + comment) and Contador (read + write + upload + reconcile)

### Technical Constraints & Dependencies

| Constraint | Detail |
|---|---|
| Backend | Python — FastAPI or Flask REST API |
| Frontend | React or Vue.js SPA (desktop-only, 1280px minimum) |
| Storage Phase 1 | Google Sheets via gspread (already integrated and working) |
| Storage Phase 2 | PostgreSQL — triggered by performance or volume, not fixed timeline |
| Authentication | Google OAuth exclusively — no username/password |
| AI Integration | Gemini API for bank statement extraction |
| ERP Integration | Laudus API — Python client already exists (laudus_service.py) |
| Existing pipeline | sync.py orchestrates Balance Sheet + Ledger sync; models.py defines schemas; gspread_utils.py handles upsert/replace with backup protection |

### Cross-Cutting Concerns Identified

- **Authentication & Authorization** — Google OAuth + server-side RBAC on every API request; owner role cannot write financial data
- **Storage Abstraction** — no component outside the data service layer writes directly to Google Sheets; enables Phase 2 PostgreSQL migration with zero frontend/API changes
- **Audit Logging** — all financial data mutations logged with timestamp and authenticated user (FR5, NFR13)
- **Async Operations** — Gemini extraction and reconciliation runs must be non-blocking with UI progress indicators (NFR3, NFR4)
- **Multi-currency** — CLP and USD throughout; storage and display must preserve currency codes
- **Error Isolation** — sync failures must not produce partial or corrupted data states; all errors logged with full detail before surfacing

## Starter Template Evaluation

### Primary Technology Domain

Full-stack web application: Python REST API + React SPA + existing data pipeline (brownfield)

### Decision: Custom Scaffold (no monorepo template)

**Rationale:** The official FastAPI Full Stack Template includes the right frontend stack (React + Vite + TypeScript + Tailwind + shadcn/ui) but bundles PostgreSQL and JWT auth — incompatible with Phase 1 Google Sheets storage and Google OAuth requirement. The existing Python sync pipeline (laudus_service, models, gspread_utils) already serves as the backend foundation.

### Frontend Initialization

**Command:**
```bash
npm create vite@latest frontend -- --template react-ts
```

**Architectural decisions provided:**
- Language: TypeScript — type safety for financial data
- Build tool: Vite v8 — fast dev server, optimized production builds
- Framework: React — largest ecosystem, best implementation coverage for AI-assisted development
- Styling: Tailwind CSS + shadcn/ui — added post-scaffold

### Backend Initialization

**Command:**
```bash
pip install "fastapi[standard]"
```

**Architectural decisions:**
- Framework: FastAPI — async support required for Gemini extraction and reconciliation operations
- Validation: Pydantic — included with FastAPI, enforces data contracts at API boundary
- Server: Uvicorn — ASGI server included in `fastapi[standard]`
- Foundation: wraps existing `laudus_service.py`, `models.py`, `gspread_utils.py` — no code discarded

**Note:** Frontend scaffold and backend FastAPI setup are the first two implementation stories.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- Storage abstraction: Repository pattern from day 1 — enables Phase 2 migration without touching API or frontend
- Authentication: Google OAuth with JWT in httpOnly cookies
- Hosting Phase 1: Google Cloud Run (scale to zero)

**Important Decisions (Shape Architecture):**
- API design: REST `/api/v1/` with Pydantic at the boundary
- Frontend state management: React Query + React Context
- Error handling: global FastAPI middleware

**Deferred Decisions (Post-MVP):**
- Hosting Phase 2: evaluate cost-efficient options based on real usage volume (Cloud SQL vs alternatives)

### Data Architecture

- **Pattern:** Repository pattern — `SheetsRepository` implements a `DataRepository` interface; Phase 2 introduces `PostgresRepository` with zero changes to API or frontend
- **API models:** Pydantic models on every FastAPI endpoint — automatic validation and generated documentation
- **Existing schemas:** `models.py` (BALANCE_HEADERS, LEDGER_HEADERS, map functions, enrich functions) retained as pipeline transformation layer; Pydantic models serve as the API contract layer above it
- **No caching (MVP):** Google Sheets is the source of truth; dashboard queries read from Sheets via the repository; caching deferred to Phase 2

### Authentication & Security

- **Provider:** Google OAuth 2.0 via `authlib` (actively maintained Python library)
- **Sessions:** JWT stored in httpOnly cookies — stateless, compatible with Cloud Run (no sticky sessions required)
- **RBAC:** two roles encoded in JWT — `owner` and `contador`; FastAPI dependency middleware verifies role on every protected endpoint
- **CORS:** configured to accept requests only from the frontend domain

### API & Communication Patterns

- **Design:** REST, prefix `/api/v1/`
- **Documentation:** auto-generated via FastAPI at `/docs`
- **Error handling:** global exception handler middleware — all errors return JSON with `status`, `message`, `detail`
- **Async operations:** Gemini extraction and reconciliation endpoints return a job ID immediately; frontend polls for status — non-blocking UI

### Frontend Architecture

- **Server state:** React Query — handles caching, loading states, and re-fetch for all dashboard data
- **App state:** React Context — user session and global filter configuration only
- **Routing:** React Router v6

### Infrastructure & Deployment

- **Phase 1 hosting:** Google Cloud Run — scale to zero, ~$0/month for 2-3 internal users
- **Phase 2 hosting:** to be evaluated post-MVP based on real usage volume
- **Sync pipeline:** GitHub Actions (already configured in repo) — existing weekly cron extended for new sync schedule
- **Secrets:** Google Secret Manager — Laudus API credentials, Google Service Account key, environment variables

### Decision Impact Analysis

**Implementation Sequence:**
1. Backend FastAPI scaffold + Repository interface definition
2. Frontend React + Vite scaffold
3. Google OAuth integration (blocks all authenticated endpoints)
4. SheetsRepository implementation (wraps existing gspread_utils)
5. Dashboard API endpoints (balance sheet + ledger reads)
6. React Query integration + dashboard views
7. Cloud Run deployment

**Cross-Component Dependencies:**
- Repository interface must be defined before any API endpoint is implemented
- Google OAuth must be working before any protected route is built
- React Query setup must precede all data-fetching components

## Implementation Patterns & Consistency Rules

### Critical Conflict Points Identified

8 areas where AI agents could make inconsistent choices without explicit rules.

### Naming Patterns

**Backend (Python) — snake_case throughout:**
```python
# ✅ Correct
def get_balance_sheet(entity_id: str): ...
balance_headers = ["account_id", "account_number"]

# ❌ Incorrect
def getBalanceSheet(entityId: str): ...
```

**API endpoints — plural nouns, kebab-case:**
```
✅ GET /api/v1/balance-sheets
✅ GET /api/v1/ledger-entries
❌ GET /api/v1/balanceSheet
❌ GET /api/v1/getBalanceSheet
```

**Frontend (TypeScript) — camelCase for variables/functions, PascalCase for components:**
```typescript
// ✅ Correct
const balanceData = useQuery(...)
function BalanceSheetView() { ... }

// ❌ Incorrect
const balance_data = useQuery(...)
function balance_sheet_view() { ... }
```

**JSON fields in API responses — snake_case** (consistent with existing Python models):
```json
{ "account_id": 273, "account_number": "111005", "query_date": "2026-03-31" }
```

### Structure Patterns

**Backend directory layout:**
```
backend/
  app/
    api/v1/          # endpoints organized by feature
    auth/            # Google OAuth logic
    repositories/    # SheetsRepository, (future) PostgresRepository
    services/        # business logic layer
    models/          # Pydantic models
  services/          # existing pipeline (laudus_service, etc.) — retained as-is
  config/            # existing configuration — retained as-is
  utils/             # existing utilities — retained as-is
```

**Frontend directory layout:**
```
frontend/src/
  pages/             # top-level views (Dashboard, Login)
  components/        # reusable UI components
  hooks/             # React Query hooks organized by feature
  services/          # API call functions
  types/             # TypeScript type definitions
```

### Format Patterns

**Successful API responses:**
```json
{ "data": { ... }, "meta": { "last_sync": "2026-04-08T10:00:00Z" } }
```

**Error responses:**
```json
{ "error": { "code": "UNAUTHORIZED", "message": "Insufficient permissions" } }
```

**Dates:** always ISO 8601 string (`"2026-03-31"`) — never Unix timestamps or locale-specific formats

**Monetary amounts:** always `float` — never string. UI formats with `toLocaleString('es-CL')`

### Process Patterns

**Loading states:** React Query manages all async state — no manual `isLoading` useState hooks

**Backend error handling:** single point — global middleware catches and formats all errors; endpoints do not handle exceptions individually except for business validation errors

**Authentication:** every protected endpoint uses the same FastAPI dependency `get_current_user()` — no inline auth logic inside endpoint handlers

### Enforcement — All AI Agents MUST

- Verify all API JSON fields use snake_case before exposing an endpoint
- Use `get_current_user()` dependency on every endpoint requiring authentication
- Route all errors through the global middleware — no bare `try/except` returning responses inline
- Use React Query for all data fetching — no `useEffect` + raw `fetch` patterns
- Store no credentials or secrets in code — use environment variables via `.env` and Google Secret Manager

## Project Structure & Boundaries

### Complete Project Directory Structure

```
LAUDUS_Backup/                        # repo root — all components coexist here
│
├── .env.example                      # environment variable template
├── .gitignore                        # existing
├── Pipfile                           # updated with dependencies
├── sync.py                           # EXISTING — main pipeline orchestrator
├── models.py                         # EXISTING — schemas + transformation functions
│
├── .github/workflows/
│   └── sync.yml                      # EXISTING — weekly cron job
│
├── config/                           # EXISTING — no changes
│   ├── laudus_config.py
│   └── gspread_config.py
│
├── services/                         # EXISTING — no changes
│   ├── laudus_service.py
│   ├── balance_sheet_service.py
│   └── ledger_service.py
│
├── utils/                            # EXISTING — no changes
│   ├── dates.py
│   └── gspread_utils.py
│
├── backend/                          # NEW — FastAPI application
│   ├── main.py                       # FastAPI entry point
│   ├── requirements.txt
│   ├── Dockerfile
│   │
│   ├── app/
│   │   ├── dependencies.py           # get_current_user() — used by all protected endpoints
│   │   ├── middleware.py             # global error handler + CORS
│   │   │
│   │   ├── auth/                     # FR1–5: Google OAuth + JWT + RBAC
│   │   │   ├── router.py             # /api/v1/auth/login, /callback, /logout
│   │   │   ├── service.py            # OAuth flow + JWT generation
│   │   │   └── schemas.py            # TokenResponse, UserSession
│   │   │
│   │   ├── api/v1/
│   │   │   ├── router.py             # aggregates all v1 routers
│   │   │   │
│   │   │   ├── dashboard/            # FR12–19: dashboards + filters + drill-down
│   │   │   │   ├── router.py         # GET /balance-sheets, /ledger-entries
│   │   │   │   ├── service.py        # query and filter logic
│   │   │   │   └── schemas.py        # BalanceSheetResponse, LedgerEntryResponse
│   │   │   │
│   │   │   └── sync/                 # FR6–11: sync status and trigger
│   │   │       ├── router.py         # GET /sync/status, POST /sync/trigger
│   │   │       └── schemas.py        # SyncStatus, SyncResult
│   │   │
│   │   └── repositories/
│   │       ├── base.py               # DataRepository abstract interface
│   │       └── sheets_repository.py  # SheetsRepository implements DataRepository
│   │
│   └── tests/
│       ├── test_auth.py
│       ├── test_dashboard.py
│       └── test_repositories.py
│
└── frontend/                         # NEW — React SPA
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── Dockerfile
    │
    └── src/
        ├── main.tsx
        ├── App.tsx                   # routes + auth guard
        │
        ├── pages/
        │   ├── Login.tsx             # FR1: Google OAuth redirect
        │   └── dashboard/
        │       ├── DashboardLayout.tsx
        │       ├── BalanceSheetPage.tsx     # FR14: assets/liabilities
        │       ├── IncomeExpensesPage.tsx   # FR15: income/expenses
        │       ├── IncomeStatementPage.tsx  # FR16: income statement
        │       └── EquityVariationPage.tsx  # FR17: equity variation
        │
        ├── components/
        │   ├── ui/                   # shadcn/ui base components
        │   ├── charts/               # FR14–19: financial data charts
        │   ├── filters/              # FR12–13: entity, date range, category
        │   │   ├── EntityFilter.tsx
        │   │   ├── DateRangeFilter.tsx
        │   │   └── CategoryFilter.tsx
        │   └── layout/
        │       ├── Sidebar.tsx
        │       └── Header.tsx
        │
        ├── hooks/                    # React Query hooks by feature
        │   ├── useBalanceSheet.ts
        │   ├── useLedger.ts
        │   └── useSyncStatus.ts
        │
        ├── services/                 # API call functions
        │   ├── api.ts                # base config (baseURL, interceptors)
        │   ├── dashboard.ts
        │   └── auth.ts
        │
        └── types/
            ├── balance-sheet.ts
            ├── ledger.ts
            └── user.ts
```

### Architectural Boundaries

**API Boundary:** Frontend communicates with backend exclusively via `/api/v1/` — the frontend never accesses Google Sheets directly.

**Data Boundary:** Backend accesses Google Sheets exclusively via `SheetsRepository` — no endpoint imports `gspread` directly.

**Sync Boundary:** The pipeline (`sync.py`) runs independently via GitHub Actions. The backend reads what sync already wrote; it does not trigger sync in real time except via `POST /sync/trigger`.

**Auth Boundary:** Every request to `/api/v1/` except `/auth/*` requires a valid JWT verified by `get_current_user()`.

### Requirements to Structure Mapping

| FRs | Feature | Location |
|---|---|---|
| FR1–5 | Auth + RBAC | `backend/app/auth/` + `frontend/src/pages/Login.tsx` |
| FR6–11 | ERP Sync | `services/` (existing) + `backend/app/api/v1/sync/` |
| FR12–13 | Filters | `frontend/src/components/filters/` |
| FR14–19 | Dashboards | `frontend/src/pages/dashboard/` + `backend/app/api/v1/dashboard/` |
| FR20–44 | Phase 2 | Not in structure — added post-MVP |

### Data Flow

1. **Sync flow (scheduled):** Laudus API → `sync.py` → `gspread_utils` → Google Sheets
2. **Read flow (on demand):** React dashboard → FastAPI `/api/v1/` → `SheetsRepository` → Google Sheets
3. **Auth flow:** Browser → `/api/v1/auth/login` → Google OAuth → `/callback` → JWT cookie → protected routes

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:** FastAPI + React + Vite + Google OAuth + Cloud Run is a proven combination. The existing Python sync pipeline and the new FastAPI backend operate in separate layers without conflict — sync writes to Sheets, the API reads from Sheets via the repository.

**Pattern Consistency:** snake_case Python → snake_case JSON → camelCase TypeScript follows the standard cross-boundary convention. React Query + REST API is the natural pairing. Repository pattern cleanly abstracts the Google Sheets storage layer.

**Structure Alignment:** Every MVP FR has a concrete location. The four boundaries (API, Data, Auth, Sync) are well-defined with no overlaps.

### Requirements Coverage Validation ✅

| Category | Status |
|---|---|
| FR1–5 (Auth + RBAC) | ✅ Covered — `auth/` + `dependencies.py` |
| FR6–11 (ERP Sync) | ✅ Covered — existing `services/` + `api/v1/sync/` |
| FR12–19 (Dashboards + filters) | ✅ Covered — `dashboard/` frontend + backend |
| FR20–44 (Phase 2) | ✅ Explicitly deferred |
| NFR1–4 (Performance) | ✅ React Query caching + async FastAPI endpoints |
| NFR5–9 (Security) | ✅ HTTPS via Cloud Run + JWT cookies + RBAC + Secret Manager |
| NFR10–12 (Reliability) | ✅ Global error middleware + existing sync protection |
| NFR15–16 (Integration abstraction) | ✅ laudus_service retained + Repository pattern |

### Gap Analysis Results

**Gap 1 — FR5 / NFR13: Financial mutation audit log**
The PRD requires all financial data mutations logged with timestamp and authenticated user. `middleware.py` exists but audit logging not explicitly structured.
**Resolution:** Add `backend/app/audit/service.py` — middleware calls it on every write operation. Added to structure.

**Gap 2 — NFR14: Daily Sheets backup**
The PRD requires a daily snapshot to a separate backup sheet. `safe_write()` provides in-operation backup but no scheduled daily snapshot.
**Resolution:** Add `.github/workflows/backup.yml` with daily cron — calls existing pipeline. No new code required.

**Gap 3 — Chart library unspecified**
`frontend/src/components/charts/` defined but no library selected.
**Resolution:** **Recharts** — React-native, TypeScript-first, well-suited for financial time-series data.

### Architecture Completeness Checklist

- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints and dependencies identified
- [x] Cross-cutting concerns mapped
- [x] Critical decisions documented with technologies
- [x] Full stack specified (FastAPI + React + Vite + TypeScript + Tailwind + shadcn/ui)
- [x] Storage abstraction pattern defined (Repository)
- [x] Authentication architecture defined (Google OAuth + JWT + RBAC)
- [x] Hosting decided (Cloud Run Phase 1, TBD Phase 2)
- [x] Naming conventions established (snake_case backend, camelCase frontend)
- [x] Structure patterns defined
- [x] Process patterns documented (error handling, loading states, auth)
- [x] Complete directory structure defined
- [x] Component boundaries established
- [x] Integration points mapped
- [x] FR-to-structure mapping complete
- [x] 3 gaps identified and resolved

### Architecture Readiness Assessment

**Overall Status: READY FOR IMPLEMENTATION**
**Confidence Level: High** — 3 minor gaps resolved, 0 critical gaps.

**Key Strengths:**
- Existing Python pipeline retained intact — zero rework of working code
- Repository pattern enables Phase 2 PostgreSQL migration with no frontend changes
- Google ecosystem consistency (OAuth, Sheets, Cloud Run, Secret Manager)
- Clear MVP scope boundary — Phase 2 FRs explicitly deferred

**Areas for Future Enhancement (Phase 2):**
- PostgreSQL migration via `PostgresRepository` — drop-in replacement for `SheetsRepository`
- Bank statement ingestion module (`api/v1/ingestion/`)
- Hosting cost optimization evaluation based on real usage data

### Implementation Handoff

**AI Agent Guidelines:**
- Follow all architectural decisions exactly as documented
- Use `get_current_user()` dependency on every protected endpoint — no exceptions
- All data access goes through `SheetsRepository` — never import `gspread` in API layer
- Use React Query for all data fetching — no raw `useEffect` + `fetch`
- All JSON fields snake_case — frontend converts to camelCase internally

**Implementation Sequence:**
1. `backend/` — FastAPI scaffold + `DataRepository` interface + `SheetsRepository`
2. `frontend/` — React + Vite + TypeScript scaffold + Tailwind + shadcn/ui
3. Google OAuth integration (`auth/`)
4. Dashboard API endpoints (`api/v1/dashboard/`)
5. React dashboard views + React Query hooks
6. Cloud Run deployment + GitHub Actions backup workflow

---

## Phase 2 Architecture: Epic 4 & 5 — Ingesta y Categorización de Cartolas

_Added: 2026-04-14. Covers FR20–FR31 (Bank Statement Ingestion + Intelligent Categorization)._

### Phase 2 Scope Boundaries

**In scope — Phase 2:**
- Credit card statements only (entity: EAG)
- Multiple banks: BCI, Santander, and others including international USD cards
- PDF format, unstructured (format varies by bank)
- Historical ingestion for accounts where cartolas are available

**Explicitly deferred:**
- Bank account statements (checking/savings) — deferred to Reconciliation phase
- Investment account statements — deferred to a future phase
- ERP data migration (Sheets → Supabase) — separate story, later in Phase 2

### Storage Architecture Decision

**Hybrid storage model — two repositories, one interface:**

| Data | Storage | Repository |
|------|---------|------------|
| ERP data (Balance Sheet, Ledger from Laudus) | Google Sheets | `SheetsRepository` (unchanged) |
| Cartola data (statements, transactions, categories) | Supabase (managed PostgreSQL) | `SupabaseRepository` (new) |

**Rationale:**
- `sync.py` pipeline writes to Google Sheets — declared untouchable; zero changes required
- Cartola data has complex relational structure (batches → transactions → category states) poorly suited to Sheets
- `DataRepository` interface (implemented in Epic 1) enables `SupabaseRepository` as a drop-in addition with zero changes to existing API or frontend
- Supabase free tier (500MB DB, 2GB storage) is sufficient for this scale (2-3 users, family office)
- No PDF file storage — PDFs are uploaded, extracted by Gemini, then discarded; user retrieves originals from their bank

**Future migration note:** Moving ERP data from Sheets to Supabase is a separate story. When done, `SheetsRepository` is retired and `SupabaseRepository` serves all data. Dashboard service already designed to query both sources independently.

### Supabase Schema

```sql
-- Chart of accounts synced from Google Sheets (source of truth remains Sheets)
CREATE TABLE plan_de_cuentas (
  account_number  VARCHAR PRIMARY KEY,       -- e.g. "111005", "411001"
  account_name    VARCHAR NOT NULL,
  account_type    VARCHAR,                   -- e.g. 'activo', 'pasivo', 'ingreso', 'gasto'
  cat1            VARCHAR,
  cat2            VARCHAR,
  cat3            VARCHAR,
  active          BOOLEAN DEFAULT true,
  synced_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Bank account registry — maps real bank accounts to the chart of accounts
CREATE TABLE bank_accounts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_number   VARCHAR NOT NULL REFERENCES plan_de_cuentas(account_number),
  account_type     VARCHAR NOT NULL,         -- 'tarjeta_credito' | 'cta_corriente' | 'linea_credito' | 'cta_inversiones'
  account_currency VARCHAR NOT NULL,         -- 'CLP' | 'USD'
  bank_name        VARCHAR,
  active           BOOLEAN DEFAULT true
);

-- One record per uploaded credit card statement
CREATE TABLE cartola_batches (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity          VARCHAR NOT NULL DEFAULT 'EAG',
  account_name    VARCHAR NOT NULL,        -- e.g. "T/C Eduardo BCI"
  bank            VARCHAR,                 -- e.g. "BCI", "Santander"
  period          DATE NOT NULL,           -- First day of statement month
  currency        VARCHAR NOT NULL,        -- 'CLP' or 'USD'
  opening_balance DECIMAL,                 -- Pre-filled by Gemini, editable by contador
  closing_balance DECIMAL,                 -- Pre-filled by Gemini, editable by contador
  sum_transactions DECIMAL,               -- Calculated: SUM(cartola_transactions.amount)
  balance_discrepancy DECIMAL,            -- closing - opening - sum_transactions; must be 0
  laudus_entry_id  VARCHAR,               -- Reference to matching Laudus ledger entry
  laudus_payment_amount DECIMAL,          -- Amount of the Laudus CC payment entry
  status          VARCHAR NOT NULL DEFAULT 'extracted',
                  -- 'extracted' | 'balance_validated' | 'categorized' | 'confirmed'
  override_justification TEXT,            -- If balance check forced past discrepancy
  uploaded_by     VARCHAR NOT NULL,
  uploaded_at     TIMESTAMPTZ DEFAULT NOW(),
  extraction_model VARCHAR                -- Gemini model version used
);

-- One record per transaction line in a credit card statement
CREATE TABLE cartola_transactions (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id           UUID NOT NULL REFERENCES cartola_batches(id) ON DELETE CASCADE,
  date               DATE NOT NULL,
  description        TEXT NOT NULL,
  amount             DECIMAL NOT NULL,
  currency           VARCHAR NOT NULL,
  category_auto      VARCHAR,             -- Category suggested (historical match or Gemini)
  category_confirmed VARCHAR,             -- Category confirmed by contador
  category_status    VARCHAR NOT NULL DEFAULT 'pending',
                     -- 'pending' | 'suggested' | 'confirmed'
  match_source       VARCHAR,             -- 'historical' | 'gemini' — how category was derived
  reviewed_by        VARCHAR,
  reviewed_at        TIMESTAMPTZ
);
```

**Transaction category states:**

| Status | Meaning | Dashboard display |
|--------|---------|-------------------|
| `pending` | No category found | Grouped under "Pendiente de categorizar" |
| `suggested` | Auto-suggested (historical or Gemini) | Shown with red badge "por revisar" |
| `confirmed` | Contador confirmed | Normal display |

### Credit Card Entry Identification

Credit card accounts are identified via the **`bank_accounts` table**, which maps real bank accounts to their corresponding entry in `plan_de_cuentas`. This replaces Cat2/Cat3 string matching and requires no changes to the ERP category taxonomy.

**Lookup flow:**
```
cartola_batch.account_number
  → bank_accounts WHERE account_number = ? AND account_type = 'tarjeta_credito'
  → plan_de_cuentas WHERE account_number = bank_accounts.account_number
  → Laudus ledger entry matched by plan_de_cuentas.account_number
```

**Prerequisite — Story 4.0 (before Epic 4 can start):**
1. Sync `plan_de_cuentas` from Sheets to Supabase (one-time load + refresh endpoint)
2. Ary registers each credit card in the `bank_accounts` table via a configuration UI or direct DB insert

**Enforcement rule for AI agents:** Never use `accountName.startsWith("T/C")`, Cat2/Cat3 string matching, or any pattern-based heuristic to identify CC entries. Always join via `bank_accounts` → `plan_de_cuentas`.

### Gemini Integration — PDF Extraction

**Single integration point** per NFR17 — one `GeminiClient` handles all bank formats without per-bank configuration.

**Extraction contract (Gemini output schema):**
```json
{
  "opening_balance": 150000.00,
  "closing_balance": 95000.00,
  "currency": "CLP",
  "transactions": [
    {
      "date": "2026-03-05",
      "description": "SUPERMERCADO JUMBO",
      "amount": 45000.00
    }
  ]
}
```

**Validation rule (NFR19):** Gemini response is validated against this schema before any processing. Malformed or incomplete responses are rejected — no partial data persisted (NFR12).

**Async pattern (NFR3):** Upload endpoint returns `{"status": "processing", "batch_id": "..."}` immediately. Frontend polls `GET /cartolas/{batch_id}` for status. UI remains responsive during extraction.

### Categorization Pipeline

Two-stage pipeline runs automatically after balance validation is confirmed:

```
For each cartola_transaction:
  Stage 1 — Historical match:
    Search existing Laudus ledger entries for same description
    If match found with confirmed category → assign that category
    Set match_source = 'historical', category_status = 'suggested'

  Stage 2 — Gemini fallback (only if Stage 1 found no match):
    Send description + amount to Gemini
    Gemini selects from the 85 expense accounts in chart of accounts
    Set match_source = 'gemini', category_status = 'suggested'

  If neither stage produces a result:
    category_status = 'pending'
```

**Learning effect:** As the contador confirms categories, the historical match base grows. Over time, Stage 2 (Gemini) is invoked less frequently.

**The 85 expense accounts** are passed to Gemini as a structured list in the prompt — not free-form classification. Gemini must select from this fixed list only.

### Ingestion Flow (Epic 4)

```
1. Contador uploads PDF via CartolaUploadPage
2. POST /api/v1/cartolas/upload
3. Backend sends PDF bytes to Gemini → receives extraction JSON
4. Validate schema (NFR19) → reject if malformed
5. Save cartola_batch (status: 'extracted') + cartola_transactions to Supabase
6. Return batch_id + extraction summary (transaction count, balances)
      ↓
7. Contador reviews balance validation in UI:
   - Opening balance (editable, pre-filled by Gemini)
   - Σ transactions (read-only, calculated)
   - Closing balance (editable, pre-filled by Gemini)
   - Discrepancy indicator (must be 0 to proceed)
8. PATCH /api/v1/cartolas/{batch_id}/validate-balance
   → If discrepancy = 0: update status → 'balance_validated'
   → If discrepancy ≠ 0: block — show error, allow manual correction of balances
      ↓
9. Categorization pipeline runs automatically
10. Update cartola_transactions with category_auto + category_status
11. Update batch status → 'categorized'
12. Notify UI: ready for category review
```

### Category Review Flow (Epic 5)

```
1. Contador navigates to CartolaReviewPage
2. GET /api/v1/categorization/pending
   → Returns cartola_transactions WHERE category_status IN ('pending', 'suggested')
   → Grouped by batch / account / period
3. For each transaction: description, amount, suggested category, match_source
4. Contador actions per transaction:
   - Accept suggestion → PATCH /transactions/{id}/category (status → 'confirmed')
   - Modify category → select from 85 accounts → PATCH (status → 'confirmed')
5. Bulk action: "Confirmar todas las sugerencias" → POST /transactions/bulk-confirm
6. When all transactions confirmed → batch status → 'confirmed'
```

### Dashboard Explosion Logic

When the income/expenses dashboard fetches data for entity=EAG + period:

```
Dashboard service:
  1. Query SheetsRepository for ledger entries (as today)
  2. For each ledger entry:
     a. Query SupabaseRepository: bank_accounts JOIN plan_de_cuentas
        WHERE plan_de_cuentas.account_number = ledger_entry.account_number
        AND bank_accounts.active = true
     b. If match found (entry is a registered bank account):
        → Query cartola_batches for account_number + period
        → If batch found AND batch.status IN ('categorized', 'confirmed'):
           → Replace the single Laudus entry with cartola_transactions
           → Apply visual status based on category_status of each transaction
        → If no batch found:
           → Show Laudus entry as-is (unchanged behavior)
     c. If no match in bank_accounts:
        → Show Laudus entry as-is (non-bank account, unchanged)
  3. Return combined response
```

**Frontend rendering rules:**
- `confirmed` transactions → normal display
- `suggested` transactions → category shown in red, badge "por revisar"
- `pending` transactions → grouped under category "Pendiente de categorizar"
- Months with no cartola loaded → Laudus CC payment entry shown unchanged

### New API Endpoints

All endpoints require `get_current_user()`. Upload/confirm endpoints require `contador` role.

```
# Story 4.0 — Plan de cuentas sync (prerequisite)
POST   /api/v1/plan-de-cuentas/sync                 # Trigger sync from Google Sheets → Supabase
GET    /api/v1/plan-de-cuentas/                     # List all accounts (for bank_accounts config UI)

# Story 4.0 — Bank accounts configuration (prerequisite)
GET    /api/v1/bank-accounts/                       # List registered bank accounts
POST   /api/v1/bank-accounts/                       # Register a new bank account (contador only)
PATCH  /api/v1/bank-accounts/{id}                   # Update bank account (e.g. deactivate)

# Epic 4 — Ingestion
POST   /api/v1/cartolas/upload                      # Upload PDF, trigger Gemini extraction
GET    /api/v1/cartolas/                            # List all batches (with status)
GET    /api/v1/cartolas/{batch_id}                  # Batch detail + transactions
PATCH  /api/v1/cartolas/{batch_id}/validate-balance # Confirm balance (with manual corrections)

# Epic 5 — Categorization
GET    /api/v1/categorization/pending               # Transactions awaiting review
PATCH  /api/v1/transactions/{id}/category           # Confirm or modify single category
POST   /api/v1/transactions/bulk-confirm            # Bulk confirm all 'suggested' in a batch
```

### Phase 2 Directory Structure Extensions

```
backend/
  app/
    api/v1/
      plan_de_cuentas/             # Story 4.0: chart of accounts sync from Sheets
      │   ├── router.py            # POST /sync, GET / (list)
      │   ├── service.py           # Sheets → Supabase sync logic
      │   └── schemas.py           # PlanDeCuentasEntry
      │
      bank_accounts/               # Story 4.0: bank account registry + config UI
      │   ├── router.py            # GET /, POST /, PATCH /{id}
      │   ├── service.py           # CRUD + validation against plan_de_cuentas
      │   └── schemas.py           # BankAccount, BankAccountCreate
      │
      cartolas/                    # Epic 4: ingestion + balance validation
      │   ├── router.py            # Upload, list, detail, validate-balance endpoints
      │   ├── service.py           # Gemini orchestration + Supabase writes
      │   └── schemas.py           # CartolaBatch, CartolaTransaction, UploadResponse
      │
      └── categorization/          # Epic 5: review + confirm
          ├── router.py            # Pending queue, patch category, bulk confirm
          ├── service.py           # Historical matching + Gemini categorization
          └── schemas.py           # CategorySuggestion, ConfirmRequest
    │
    integrations/                  # NEW: external AI/service clients
    │   └── gemini_client.py       # PDF extraction + category suggestion (single point)
    │
    repositories/
        ├── base.py                # DataRepository (unchanged)
        ├── sheets_repository.py   # SheetsRepository (unchanged)
        └── supabase_repository.py # NEW: SupabaseRepository for cartola data

frontend/src/
  pages/
    cartolas/
      ├── CartolaUploadPage.tsx    # Upload PDF + balance validation UI (contador only)
      └── CartolaReviewPage.tsx    # Category review + confirm UI (contador only)
  hooks/
    ├── useCartolaUpload.ts        # Manages upload + polling for extraction status
    └── useCategorizationQueue.ts  # Pending transactions queue + confirm actions
```

### Phase 2 Data Flows

```
Ingestion flow (Epic 4):
  Browser → POST /cartolas/upload (multipart PDF) →
  GeminiClient.extract_pdf() →
  Supabase cartola_batches + cartola_transactions (status: extracted) →
  Balance validation UI →
  PATCH /validate-balance →
  CategorizationService.run(batch_id) →
  Supabase updates category_auto + category_status →
  batch status: categorized

Review flow (Epic 5):
  Browser → GET /categorization/pending →
  Supabase cartola_transactions (status: suggested|pending) →
  Review UI →
  PATCH /transactions/{id}/category →
  Supabase update (status: confirmed) →
  Dashboard re-fetch reflects confirmed transactions

Dashboard explosion (updated read flow):
  Browser → GET /api/v1/ledger-entries?entity=EAG →
  DashboardService queries SheetsRepository (existing data) →
  For CC entries: SupabaseRepository.get_cartola_transactions(account, period) →
  Combined response with transaction-level visual status →
  Frontend renders explosion or fallback per entry
```

### Phase 2 Consistency Rules (AI Agents MUST follow)

- **CC identification:** always via `bank_accounts` JOIN `plan_de_cuentas` — never by Cat2/Cat3 string matching or `accountName` pattern matching
- **No PDF storage:** extract and discard — never persist raw PDF bytes to any storage
- **Balance check is blocking:** batch cannot advance to 'categorized' status if `balance_discrepancy ≠ 0` (unless override justification is provided and recorded)
- **Categorization is non-blocking for dashboard:** partially categorized batches (`suggested`/`pending`) are visible in dashboard; full confirmation is not required to see data
- **SupabaseRepository** follows the same `DataRepository` interface contract as `SheetsRepository`
- **GeminiClient** is the single integration point for all Gemini calls — no other file may import the Gemini SDK directly
- **Currency is always stored and returned explicitly** — never inferred; every transaction carries its own `currency` field
- **Historical matching uses confirmed transactions only** — `category_status = 'confirmed'` entries from Supabase; never use suggested categories as training signal
