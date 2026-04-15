---
stepsCompleted: [step-01-validate-prerequisites, step-02-design-epics, step-03-create-stories, step-04-final-validation]
workflowStatus: complete
completedAt: '2026-04-09'
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
---

# EAG Family Office - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for EAG Family Office (LAUDUS_Backup), decomposing the requirements from the PRD and Architecture into implementable stories.

**MVP Scope:** FR1–FR19 (Auth, ERP Sync, Dashboards). FR20–FR44 explicitly deferred to Phase 2.

## Requirements Inventory

### Functional Requirements

**1. Authentication & Access Control**
- FR1: Users can authenticate using their Google account (Google OAuth)
- FR2: The system grants access based on a predefined role: `owner` or `contador`
- FR3: Owner role users can view all financial data and add comments; they cannot create, edit, or delete financial records
- FR4: Contador role users can view all financial data, upload bank statements, edit categorizations, respond to comments, and trigger reconciliation
- FR5: The system logs all financial data mutations with timestamp and authenticated user

**2. ERP Data Sync**
- FR6: The system automatically syncs Balance Sheet data from the Laudus ERP API on a configurable schedule
- FR7: The system automatically syncs General Ledger data from the Laudus ERP API on a configurable schedule
- FR8: The system performs incremental sync (new records only) based on the last synced date
- FR9: The system supports full historical backfill from January 2021 to present
- FR10: The system prevents duplicate records using primary key deduplication (account+date for Balance Sheet; journalentryid+lineid for Ledger)
- FR11: The system tracks and displays the last successful sync timestamp per data type

**3. Financial Dashboards**
- FR12: Users can view financial data filtered by entity (EAG, Jocelyn, Jeannette, Johanna, Jael)
- FR13: Users can view financial data filtered by date range (month, quarter, year, custom)
- FR14: Users can view an assets/liabilities dashboard showing balance sheet positions per entity
- FR15: Users can view an income/expenses dashboard showing totals and breakdowns by account category
- FR16: Users can view an income statement (estado de resultado) per entity and period
- FR17: Users can view an equity variation dashboard comparing patrimony across periods
- FR18: Users can drill down from a dashboard summary to the individual transactions that compose a figure
- FR19: Users can view credit card transactions at individual movement level, including merchant, amount, date, and assigned category

**4. Bank Statement Ingestion (Phase 2)**
- FR20: Contador can upload bank statement files (PDF, Excel) for any configured bank account
- FR21: System sends uploaded files to Gemini with a structured extraction prompt, receives JSON payload with all transactions, opening balance, and closing balance
- FR22: System validates extracted statements: opening balance + Σ movements = closing balance
- FR23: System displays a validation summary showing calculated vs. stated closing balance and exact discrepancy if any
- FR24: System blocks confirmation of a bank statement upload when balance validation fails
- FR25: Contador can override a failed balance validation with a mandatory written justification
- FR26: System flags duplicate transactions within an uploaded statement (same date + amount + description)
- FR27: System flags anomalous transactions (zero-amount entries, unusually large amounts vs. account history)

**5. Transaction Categorization (Phase 2)**
- FR28: For each extracted bank statement transaction, system suggests a category from the chart of accounts (295 accounts)
- FR29: Contador can accept, modify, or reject the system's category suggestion for each transaction
- FR30: System saves categorized transactions only after explicit Contador confirmation
- FR31: System updates category suggestion weights based on Contador correction history; after 30 corrections of a pattern, the corrected category becomes the primary suggestion

**6. Reconciliation (Phase 2)**
- FR32: Contador can trigger a monthly reconciliation run for a selected entity and period
- FR33: System cross-checks ERP-recorded totals per account against bank statement transaction totals for the same period
- FR34: System produces a reconciliation report showing matched items, unmatched ERP entries, and unmatched bank statement entries
- FR35: System marks a reconciliation period as complete when all discrepancies are resolved or explicitly acknowledged

**7. Collaboration & Communication (Phase 2)**
- FR36: Owner can add a comment on any individual transaction or line item visible in the dashboard
- FR37: Contador receives an in-app and email notification when the owner adds a comment
- FR38: Contador can view all pending owner comments in a unified inbox
- FR39: Contador can respond to an owner comment with full context of the referenced item visible inline
- FR40: Owner and Contador can mark a comment thread as resolved
- FR41: Owner receives an in-app and email notification when Contador responds to a comment

**8. Alerts & Notifications (Phase 2)**
- FR42: System detects when an expense category for an entity increases by more than a configurable threshold (%) vs. the prior month
- FR43: Owner receives an in-app and email notification when an anomaly alert is triggered
- FR44: Users can configure alert thresholds per entity and expense category

### NonFunctional Requirements

**Performance**
- NFR1: Dashboard initial load completes in under 3 seconds on a standard Chrome desktop connection
- NFR2: Filter interactions (entity, date range, category) update visible data in under 2 seconds without full page reload
- NFR3: Bank statement file upload accepts files up to 20MB; Gemini extraction runs asynchronously and does not block the UI
- NFR4: Reconciliation runs asynchronously; the UI remains responsive and displays progress during execution

**Security**
- NFR5: All data in transit is encrypted via HTTPS/TLS
- NFR6: Google Sheets containing financial data are not publicly accessible; access restricted to the service account and authorized Google accounts only
- NFR7: API endpoints enforce role-based access on every request; no endpoint trusts client-side role claims
- NFR8: Laudus API credentials, Google service account keys, and Gemini API keys are stored securely — never hardcoded or committed to source control
- NFR9: Session tokens expire after a configurable inactivity period (default: 8 hours)

**Reliability**
- NFR10: Laudus API sync failures are logged with full error detail and do not silently produce partial or corrupted data
- NFR11: If the Laudus API returns an authentication failure response, the system retries with a fresh token exactly once before failing and logging the error
- NFR12: Bank statement uploads where Gemini extraction fails or returns incomplete data are rejected cleanly — no partial data is persisted
- NFR13: The sync pipeline maintains an append-only audit log of every run: timestamp, records processed, records added/updated, errors
- NFR14: A daily snapshot of the Google Sheets data store is written to a separate backup sheet

**Integration**
- NFR15: The Laudus API client handles token expiry transparently without requiring user intervention
- NFR16: The storage layer is accessed exclusively through an abstraction interface — no component outside the data service layer writes directly to Google Sheets
- NFR17: Bank statement extraction handles all bank formats without per-bank configuration — a single integration point processes format variation across all supported banks
- NFR18: Google OAuth is the sole authentication mechanism; no username/password authentication is implemented
- NFR19: Gemini API responses conform to a defined output schema; responses are validated against this schema before processing — malformed responses are rejected

### Additional Requirements

From Architecture document (technical requirements that affect implementation):

- **Custom scaffold required** — no starter template used. Two separate initialization commands:
  - Frontend: `npm create vite@latest frontend -- --template react-ts` + Tailwind CSS + shadcn/ui added post-scaffold + Recharts for charts
  - Backend: `pip install "fastapi[standard]"` wrapping existing `laudus_service.py`, `models.py`, `gspread_utils.py` — no existing code discarded
- **Repository pattern from day 1** — `DataRepository` abstract interface + `SheetsRepository` implementation; enables Phase 2 PostgreSQL migration with zero changes to API or frontend
- **Google OAuth via `authlib`** — JWT stored in httpOnly cookies; stateless, compatible with Cloud Run (no sticky sessions)
- **RBAC middleware** — `get_current_user()` FastAPI dependency on every protected endpoint; roles encoded in JWT
- **Global error middleware** — single error handling point in `middleware.py`; endpoints do not catch exceptions individually
- **Audit logging service** — `backend/app/audit/service.py` called by middleware on every write operation (resolves FR5/NFR13 gap)
- **Daily Sheets backup** — `.github/workflows/backup.yml` with daily cron calling existing pipeline (resolves NFR14 gap)
- **Hosting: Google Cloud Run** — scale to zero, ~$0/month for 2-3 internal users
- **Secrets: Google Secret Manager** — Laudus API credentials, Google Service Account key, Gemini API key
- **Async pattern** — Gemini extraction and reconciliation endpoints return job ID immediately; frontend polls for status
- **Existing pipeline retained intact** — `sync.py`, `services/`, `config/`, `utils/` unchanged; GitHub Actions sync workflow already configured

### UX Design Requirements

No UX Design document — not applicable for this project.

### FR Coverage Map

FR1: Epic 1 — Google OAuth authentication
FR2: Epic 1 — Role assignment (owner / contador)
FR3: Epic 1 — Owner read + comment permissions enforced
FR4: Epic 1 — Contador write + upload + reconcile permissions enforced
FR5: Epic 1 — Financial mutation audit log
FR6: Epic 2 — Balance Sheet sync schedule
FR7: Epic 2 — General Ledger sync schedule
FR8: Epic 2 — Incremental sync by last synced date
FR9: Epic 2 — Historical backfill from January 2021
FR10: Epic 2 — Duplicate prevention via primary key deduplication
FR11: Epic 2 — Last successful sync timestamp display
FR12: Epic 3 — Entity filter (EAG, Jocelyn, Jeannette, Johanna, Jael)
FR13: Epic 3 — Date range filter (month, quarter, year, custom)
FR14: Epic 3 — Assets/liabilities dashboard
FR15: Epic 3 — Income/expenses dashboard
FR16: Epic 3 — Income statement (estado de resultado)
FR17: Epic 3 — Equity variation dashboard
FR18: Epic 3 — Drill-down from summary to individual transactions
FR19: Epic 3 — Credit card transaction detail (merchant, amount, date, category)
FR20: Epic 4 — Bank statement file upload (PDF, Excel)
FR21: Epic 4 — Gemini extraction → structured JSON with transactions + balances
FR22: Epic 4 — Balance validation: opening + Σ movements = closing
FR23: Epic 4 — Validation summary display (calculated vs. stated)
FR24: Epic 4 — Block confirmation when balance validation fails
FR25: Epic 4 — Override failed validation with mandatory written justification
FR26: Epic 4 — Duplicate transaction flagging within uploaded statement
FR27: Epic 4 — Anomalous transaction flagging (zero-amount, unusually large)
FR28: Epic 5 — Category suggestion from 295-account chart of accounts
FR29: Epic 5 — Contador accepts / modifies / rejects category suggestion
FR30: Epic 5 — Save categorized transactions only after explicit confirmation
FR31: Epic 5 — Category suggestion weight update after 30 corrections of a pattern
FR32: Epic 6 — Trigger monthly reconciliation run (entity + period)
FR33: Epic 6 — Cross-check ERP totals vs. bank statement totals
FR34: Epic 6 — Reconciliation report: matched, unmatched ERP, unmatched bank
FR35: Epic 6 — Mark reconciliation period complete when all discrepancies resolved
FR36: Epic 7 — Owner adds comment on any transaction or line item
FR37: Epic 7 — Contador receives in-app + email notification on new owner comment
FR38: Epic 7 — Contador views all pending owner comments in unified inbox
FR39: Epic 7 — Contador responds with full item context visible inline
FR40: Epic 7 — Owner and Contador mark comment thread as resolved
FR41: Epic 7 — Owner receives in-app + email notification on Contador response
FR42: Epic 8 — Expense spike detection (configurable % threshold vs. prior month)
FR43: Epic 8 — Owner receives in-app + email notification on anomaly alert
FR44: Epic 8 — Users configure alert thresholds per entity and expense category

## Epic List

### Epic 1: Plataforma Base y Autenticación
Los usuarios pueden acceder de forma segura a la plataforma con su cuenta Google, y el sistema les asigna el rol correcto (owner/contador). Incluye todo el scaffolding técnico: backend FastAPI, frontend React+Vite, Repository pattern, Cloud Run deployment, Secret Manager, audit service y daily backup workflow.
**FRs cubiertos:** FR1, FR2, FR3, FR4, FR5
**NFRs cubiertos:** NFR5, NFR7, NFR8, NFR9, NFR18

### Epic 2: Sincronización Automática de Datos ERP
Los datos financieros fluyen desde Laudus ERP al sistema de forma automática — Balance Sheet y General Ledger, con historial completo desde 2021, sin duplicados, con log de cada ejecución y timestamp de último sync visible en la UI.
**FRs cubiertos:** FR6, FR7, FR8, FR9, FR10, FR11
**NFRs cubiertos:** NFR10, NFR11, NFR13, NFR14, NFR15, NFR16

### Epic 3: Dashboards Financieros Multi-Entidad
El owner puede explorar de forma independiente todos los datos financieros — filtrados por entidad y período, con cuatro vistas analíticas (activos/pasivos, ingresos/gastos, estado de resultado, variación patrimonial) y drill-down hasta el movimiento individual de tarjeta de crédito.
**FRs cubiertos:** FR12, FR13, FR14, FR15, FR16, FR17, FR18, FR19
**NFRs cubiertos:** NFR1, NFR2, NFR6

---

*(Fase 2 — diferidos)*

### Epic 4: Ingesta de Cartolas Bancarias *(Fase 2)*
**FRs cubiertos:** FR20–FR27 | **NFRs:** NFR3, NFR12, NFR17, NFR19

### Epic 5: Categorización Inteligente de Transacciones *(Fase 2)*
**FRs cubiertos:** FR28–FR31

### Epic 6: Reconciliación Mensual *(Fase 2)*
**FRs cubiertos:** FR32–FR35 | **NFRs:** NFR4

### Epic 7: Colaboración Owner-Contador *(Fase 2)*
**FRs cubiertos:** FR36–FR41

### Epic 8: Alertas y Notificaciones *(Fase 2)*
**FRs cubiertos:** FR42–FR44

---

## Epic 1: Plataforma Base y Autenticación

Los usuarios pueden acceder de forma segura a la plataforma con su cuenta Google y el sistema les asigna el rol correcto (owner/contador). Toda la infraestructura base queda lista para los épicos siguientes.

**FRs cubiertos:** FR1, FR2, FR3, FR4, FR5
**NFRs cubiertos:** NFR5, NFR7, NFR8, NFR9, NFR18

---

### Story 1.1: Backend FastAPI Scaffold + Repository Pattern

As a developer,
I want a working FastAPI backend scaffold with the Repository pattern implemented,
So that all subsequent stories have a consistent, patterned foundation with storage abstraction from day one.

**Acceptance Criteria:**

**Given** the repo root exists with the existing pipeline files (`sync.py`, `services/`, `config/`, `utils/`)
**When** the backend scaffold is complete
**Then** the directory structure matches the architecture spec: `backend/app/{auth,api/v1,repositories,models}/`, `backend/main.py`, `backend/requirements.txt`, `backend/Dockerfile`
**And** `GET /api/v1/health` returns `{"status": "ok"}` with HTTP 200

**Given** the `DataRepository` abstract interface is defined in `backend/app/repositories/base.py`
**When** `SheetsRepository` is implemented in `backend/app/repositories/sheets_repository.py`
**Then** `SheetsRepository` implements all methods of `DataRepository` using the existing `gspread_utils.py`
**And** no endpoint or service outside the `repositories/` module imports `gspread` directly

**Given** the global error middleware is configured in `backend/app/middleware.py`
**When** any unhandled exception occurs in an endpoint
**Then** the response is JSON with `{"error": {"code": "...", "message": "...", "detail": "..."}}` and an appropriate HTTP status code
**And** CORS is configured to accept requests only from the frontend domain

**Given** the backend starts with `uvicorn`
**When** the server is running
**Then** auto-generated API docs are accessible at `/docs`
**And** all existing pipeline files (`sync.py`, `services/`, `config/`, `utils/`) are untouched

---

### Story 1.2: Frontend React + Vite Scaffold

As a developer,
I want a working React + Vite frontend scaffold with the full UI toolkit configured,
So that all subsequent UI stories have consistent tooling, structure, and component primitives.

**Acceptance Criteria:**

**Given** the frontend is initialized with `npm create vite@latest frontend -- --template react-ts`
**When** Tailwind CSS, shadcn/ui, React Router v6, and React Query are added
**Then** `npm run dev` starts the dev server without errors
**And** `npm run build` produces a production build without errors

**Given** the frontend directory follows the architecture spec
**When** the scaffold is complete
**Then** the directory structure includes `src/{pages,components/{ui,charts,filters,layout},hooks,services,types}/`
**And** `src/App.tsx` configures React Router with a catch-all route to a placeholder page

**Given** the base layout components exist
**When** a user visits any page
**Then** `Sidebar.tsx` and `Header.tsx` are rendered as the application shell
**And** shadcn/ui base components are available for use in all stories

**Given** React Query is configured
**When** the app initializes
**Then** a `QueryClient` is provided at the root level
**And** all data fetching in subsequent stories must use React Query hooks — no raw `useEffect` + `fetch`

**Given** the frontend `Dockerfile` exists
**When** `docker build` is run
**Then** the container builds successfully and serves the production app

---

### Story 1.3: Google OAuth Authentication

As an owner or contador,
I want to log in to the platform using my Google account,
So that I can access financial data securely without managing a separate username and password.

**Acceptance Criteria:**

**Given** a user visits the app without an active session
**When** the app loads
**Then** the user is redirected to `Login.tsx` and cannot access any other page
**And** the Login page displays a "Iniciar sesión con Google" button

**Given** the user clicks "Iniciar sesión con Google"
**When** they complete the Google OAuth consent flow
**Then** the backend receives the OAuth callback, generates a JWT, and sets it as an httpOnly cookie
**And** the user is redirected to the main dashboard

**Given** the JWT is stored in an httpOnly cookie
**When** any subsequent API request is made
**Then** the cookie is sent automatically and the backend validates the JWT before processing the request
**And** the JWT is never accessible via JavaScript (`document.cookie`)

**Given** the user clicks "Cerrar sesión"
**When** the logout action completes
**Then** the httpOnly cookie is cleared server-side
**And** the user is redirected to the Login page and cannot access protected routes

**Given** a user attempts to access `/api/v1/` endpoints without a valid JWT
**When** the request is received by the backend
**Then** the response is HTTP 401 with `{"error": {"code": "UNAUTHORIZED", "message": "Authentication required"}}`

---

### Story 1.4: Role-Based Access Control (RBAC)

As an owner or contador,
I want the system to enforce my role permissions on every action,
So that financial data integrity is protected and each user can only do what their role allows.

**Acceptance Criteria:**

**Given** the `get_current_user()` FastAPI dependency is implemented in `backend/app/dependencies.py`
**When** it is applied to a protected endpoint
**Then** it decodes the JWT, extracts the user's role (`owner` or `contador`), and returns the user object
**And** if the JWT is missing, expired, or invalid, it raises HTTP 401

**Given** a request comes in from a user with role `owner`
**When** they attempt to call any endpoint that writes financial data (POST/PUT/DELETE on financial resources)
**Then** the backend returns HTTP 403 with `{"error": {"code": "FORBIDDEN", "message": "Insufficient permissions"}}`
**And** no data is written

**Given** a request comes in from a user with role `contador`
**When** they access any read endpoint or write endpoint within their permissions
**Then** the request is processed normally

**Given** a JWT is issued at login
**When** 8 hours of inactivity have passed (configurable via environment variable)
**Then** the JWT is expired and subsequent requests return HTTP 401, requiring re-authentication

**Given** the frontend reads the user's role from the session
**When** the navigation is rendered
**Then** features exclusive to `contador` (upload, categorize, reconcile) are not visible to `owner` users
**And** role enforcement is always server-side — the frontend restriction is UI-only

---

### Story 1.5: Audit Log, Backup Workflow y Cloud Run Deployment

As a system administrator,
I want all financial mutations logged, data backed up daily, and the application deployed to Cloud Run,
So that the system is production-ready with a full audit trail, data safety, and HTTPS access.

**Acceptance Criteria:**

**Given** `backend/app/audit/service.py` is implemented
**When** any write operation (POST/PUT/DELETE on financial data) is executed
**Then** a log entry is written with: timestamp (ISO 8601), authenticated user email, HTTP method, endpoint path, and HTTP status code
**And** the audit log is append-only — no entry can be modified or deleted

**Given** `.github/workflows/backup.yml` exists with a daily cron schedule
**When** the workflow runs
**Then** it calls the existing pipeline to write a snapshot of all Google Sheets data to a designated backup sheet
**And** the workflow logs success or failure with timestamp

**Given** all credentials (Laudus API key, Google Service Account, Gemini API key) are stored in Google Secret Manager
**When** the backend starts
**Then** it reads credentials from Secret Manager via environment variables — no credentials are hardcoded or committed to source control
**And** `.env.example` documents all required environment variables without actual values

**Given** `backend/Dockerfile` and `frontend/Dockerfile` are complete
**When** both containers are deployed to Google Cloud Run
**Then** the backend is accessible via HTTPS on its Cloud Run URL
**And** the frontend is accessible via HTTPS on its Cloud Run URL
**And** the frontend is configured to call the backend via its Cloud Run URL

**Given** 2–3 internal users access the app
**When** no requests are active
**Then** Cloud Run scales to zero instances (~$0/month cost)

---

## Epic 2: Sincronización Automática de Datos ERP

Los datos financieros fluyen desde Laudus ERP al sistema de forma automática — Balance Sheet y General Ledger, con historial completo desde 2021, sin duplicados, con log de cada ejecución y timestamp de último sync visible en la UI.

**FRs cubiertos:** FR6, FR7, FR8, FR9, FR10, FR11
**NFRs cubiertos:** NFR10, NFR11, NFR13, NFR15, NFR16

---

### Story 2.1: Sync API Endpoints + Pipeline Integration

As a contador,
I want to trigger a data sync and see its status via the API,
So that financial data can be refreshed on demand and I know when data was last updated.

**Acceptance Criteria:**

**Given** the sync router is registered at `backend/app/api/v1/sync/router.py`
**When** `GET /api/v1/sync/status` is called by an authenticated user
**Then** the response returns last successful sync timestamp per data type (balance_sheet, ledger) in ISO 8601 format
**And** if a sync has never run, the response returns `null` for that data type

**Given** a `contador` user calls `POST /api/v1/sync/trigger`
**When** the request is received
**Then** the backend invokes the existing `sync.py` pipeline for both Balance Sheet and General Ledger
**And** the response returns immediately with `{"status": "triggered", "job_id": "..."}` — the sync runs asynchronously

**Given** an `owner` user calls `POST /api/v1/sync/trigger`
**When** the request is received
**Then** the backend returns HTTP 403 — owners cannot trigger sync

**Given** the sync pipeline completes (success or failure)
**When** the run finishes
**Then** the sync status (timestamp + result) is persisted so `GET /sync/status` reflects the latest run
**And** the existing `sync.py`, `services/`, `config/`, and `utils/` files are not modified

---

### Story 2.2: Incremental Sync, Deduplicación y Confiabilidad

As a system,
I want the sync pipeline to run incrementally, deduplicate records, and handle errors safely,
So that financial data is always accurate, complete, and never partially corrupted.

**Acceptance Criteria:**

**Given** a sync is triggered after a previous successful run
**When** the pipeline executes
**Then** only records with a date after the last synced date are fetched from Laudus API (FR8)
**And** the sync log records: timestamp, records fetched, records added, records skipped (duplicates), and any errors (NFR13)

**Given** the pipeline receives Balance Sheet records
**When** it writes to Google Sheets
**Then** deduplication uses `account + date` as primary key — existing records are updated, not duplicated (FR10)

**Given** the pipeline receives General Ledger records
**When** it writes to Google Sheets
**Then** deduplication uses `journalentryid + lineid` as primary key — existing records are updated, not duplicated (FR10)

**Given** the Laudus API returns an authentication failure (401)
**When** the pipeline encounters this error
**Then** it retries exactly once with a fresh token before failing (NFR11)
**And** if the retry also fails, the run is aborted and the error is logged in full — no partial data is written (NFR10)

**Given** any other error occurs mid-sync (network timeout, Sheets write failure)
**When** the pipeline encounters it
**Then** the run is aborted cleanly — no partial records are persisted
**And** the full error detail is logged with timestamp (NFR10)

---

### Story 2.3: Backfill Histórico + UI de Estado de Sync

As a contador,
I want to trigger a full historical backfill from January 2021 and see sync status in the UI,
So that all historical financial data is available from day one and I can confirm data is current at a glance.

**Acceptance Criteria:**

**Given** `POST /api/v1/sync/trigger` accepts an optional `mode` parameter
**When** called with `{"mode": "backfill", "from_date": "2021-01-01"}`
**Then** the pipeline fetches all Balance Sheet and General Ledger records from January 2021 to present
**And** deduplication ensures no records are doubled if a partial sync already ran (FR9)

**Given** the backfill runs asynchronously
**When** it is in progress
**Then** `GET /api/v1/sync/status` reflects `"status": "running"` with a start timestamp
**And** when complete, the status updates to `"status": "done"` with timestamp and record counts

**Given** the frontend `useSyncStatus` hook polls `GET /api/v1/sync/status`
**When** the data is returned
**Then** the UI displays last sync timestamp per data type (Balance Sheet, Ledger) in the Header or a dedicated status panel (FR11)
**And** if the last sync failed, the UI displays a visible error indicator with the failure timestamp

**Given** a sync is currently running
**When** the user views the status panel
**Then** a loading indicator is shown and the trigger button is disabled to prevent concurrent syncs

---

## Epic 3: Dashboards Financieros Multi-Entidad

El owner puede explorar de forma independiente todos los datos financieros — filtrados por entidad y período, con cuatro vistas analíticas y drill-down hasta el movimiento individual de tarjeta de crédito.

**FRs cubiertos:** FR12, FR13, FR14, FR15, FR16, FR17, FR18, FR19
**NFRs cubiertos:** NFR1, NFR2, NFR6

---

### Story 3.1: Dashboard API Endpoints

As a developer,
I want backend API endpoints that return financial data filtered by entity and date range,
So that all dashboard views have a consistent, secure data source to build on.

**Acceptance Criteria:**

**Given** the dashboard router is registered at `backend/app/api/v1/dashboard/router.py`
**When** `GET /api/v1/balance-sheets` is called with `entity` and `date_range` query params
**Then** the endpoint returns Balance Sheet data filtered to that entity and period from `SheetsRepository`
**And** the response follows the standard format: `{"data": [...], "meta": {"last_sync": "..."}}`

**Given** `GET /api/v1/ledger-entries` is called with `entity` and `date_range` query params
**When** the request is received
**Then** the endpoint returns General Ledger entries filtered to that entity and period
**And** all monetary amounts are returned as `float` — never as strings

**Given** any dashboard endpoint is called
**When** the request is received
**Then** `get_current_user()` is applied — unauthenticated requests return HTTP 401
**And** both `owner` and `contador` roles can access all read endpoints (NFR6: no public endpoints)

**Given** filter params `entity` and `date_range` are provided
**When** the endpoint queries `SheetsRepository`
**Then** all JSON response fields use snake_case (e.g., `account_id`, `query_date`, `account_number`)
**And** all dates are returned as ISO 8601 strings (e.g., `"2026-03-31"`)

**Given** the dashboard loads on a standard Chrome desktop connection
**When** the API response is received
**Then** response time is under 3 seconds for a full entity + annual date range (NFR1)

---

### Story 3.2: Filtros de Entidad y Fecha

As an owner or contador,
I want to filter financial data by entity and date range from any dashboard view,
So that I can focus on the specific entity and period I need without navigating away.

**Acceptance Criteria:**

**Given** the `EntityFilter` component is rendered in the dashboard layout
**When** the user selects an entity (EAG, Jocelyn, Jeannette, Johanna, Jael)
**Then** all dashboard views update to show data for the selected entity only (FR12)
**And** the selected entity is stored in React Context and persists across dashboard page navigation

**Given** the `DateRangeFilter` component is rendered in the dashboard layout
**When** the user selects a preset (month, quarter, year) or a custom date range
**Then** all dashboard views update to show data for the selected period only (FR13)
**And** the selected date range is stored in React Context and persists across dashboard page navigation

**Given** both entity and date range filters are active
**When** the user changes either filter
**Then** React Query re-fetches data for all active dashboard views automatically
**And** the update completes in under 2 seconds without a full page reload (NFR2)

**Given** a dashboard view is loading after a filter change
**When** data is being fetched
**Then** a loading skeleton or spinner is shown in the affected panels
**And** the filter controls remain interactive during loading

---

### Story 3.3: Dashboard Activos/Pasivos e Ingresos/Gastos

As an owner,
I want to see my assets/liabilities and income/expenses dashboards for any entity and period,
So that I can understand the financial position and spending patterns of each entity at a glance.

**Acceptance Criteria:**

**Given** the user navigates to the Assets/Liabilities view (`BalanceSheetPage.tsx`)
**When** data loads for the selected entity and period
**Then** balance sheet positions are displayed grouped by account category (assets vs. liabilities) (FR14)
**And** key totals (total assets, total liabilities, net patrimony) are prominently displayed
**And** amounts are formatted with `toLocaleString('es-CL')` for Chilean peso display

**Given** the user navigates to the Income/Expenses view (`IncomeExpensesPage.tsx`)
**When** data loads for the selected entity and period
**Then** income and expense totals are shown with breakdown by account category (FR15)
**And** a Recharts chart visualizes the income vs. expense comparison for the period

**Given** either dashboard is displayed
**When** the user views the data
**Then** all monetary amounts show the correct currency (CLP or USD) as stored in the data
**And** the dashboard renders correctly at 1280px minimum viewport width (desktop-only)

**Given** no data exists for the selected entity + period combination
**When** the dashboard loads
**Then** an empty state message is displayed: "No hay datos para el período seleccionado"
**And** no errors or broken charts are shown

---

### Story 3.4: Estado de Resultado y Variación Patrimonial

As an owner,
I want to see the income statement and equity variation dashboards for any entity and period,
So that I can evaluate profitability and track how the entity's equity has changed over time.

**Acceptance Criteria:**

**Given** the user navigates to the Income Statement view (`IncomeStatementPage.tsx`)
**When** data loads for the selected entity and period
**Then** the estado de resultado is displayed with income accounts, expense accounts, and net result (FR16)
**And** account categories follow the Laudus chart of accounts structure

**Given** the user navigates to the Equity Variation view (`EquityVariationPage.tsx`)
**When** data loads for the selected entity and period
**Then** patrimony values are shown for the current period and compared against the prior equivalent period (FR17)
**And** a Recharts chart visualizes the equity variation across the selected date range

**Given** either view is displayed
**When** the user views the data
**Then** all amounts use `toLocaleString('es-CL')` formatting
**And** positive/negative values are visually distinguished (e.g., color coding for gains vs. losses)

**Given** the user switches between all four dashboard views
**When** navigating via the Sidebar
**Then** the active entity and date range filters persist across all views without resetting
**And** navigation between views completes without full page reload

---

### Story 3.5: Drill-down y Detalle de Tarjetas de Crédito

As an owner,
I want to click any summary figure in the dashboard and see the individual transactions behind it,
So that I can understand exactly what makes up each number — especially credit card transactions I couldn't see before.

**Acceptance Criteria:**

**Given** a summary figure is displayed in any dashboard view
**When** the user clicks on it
**Then** a detail panel or modal opens showing the individual transactions that compose that figure (FR18)
**And** each transaction shows: date (ISO 8601 formatted as DD/MM/YYYY), description, amount, and account category

**Given** the user drills down into a credit card category
**When** the detail panel opens
**Then** individual credit card movements are shown with: merchant name, amount, date, and assigned category (FR19)
**And** movements are sorted by date descending

**Given** the detail panel is open
**When** the user clicks outside the panel or a close button
**Then** the panel closes and the dashboard view is restored without data refetch

**Given** a drill-down query is made to `GET /api/v1/ledger-entries` with a specific account filter
**When** the response is received
**Then** only transactions belonging to the clicked account/category are returned
**And** the response time is under 2 seconds (NFR2)
