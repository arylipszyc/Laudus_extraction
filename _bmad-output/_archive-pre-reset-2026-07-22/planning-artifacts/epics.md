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

### Epic 6: Reconciliación Mensual *(Fase 2 — reformulado bajo c4, activo 2026-06-20)*
**FRs cubiertos:** FR32–FR35 | **NFRs:** NFR4 · Sección detallada al final del doc (post-Epic 9).

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

---

## Epic 4: Ingesta de Cartolas Bancarias *(Phase 2)*

El contador puede subir estados de cuenta bancarios en PDF, el sistema los extrae con Gemini, valida los saldos, y deja los datos listos para categorización. Incluye el setup de Supabase, la tabla de plan de cuentas sincronizada desde Sheets, y el registro de cuentas bancarias.

**FRs cubiertos:** FR20, FR21, FR22, FR23, FR24, FR25, FR26, FR27
**NFRs cubiertos:** NFR3, NFR12, NFR17, NFR19

---

### Story 4.0: Supabase Setup + Plan de Cuentas + Bank Accounts

As a developer,
I want the Supabase schema created, the chart of accounts synced from Sheets, and a bank account registry in place,
So that Epics 4 and 5 have the data foundation and account identification they need without touching the ERP category taxonomy.

**Acceptance Criteria:**

**Given** Supabase is configured with the project credentials in environment variables
**When** the schema migration runs
**Then** tables `plan_de_cuentas`, `bank_accounts`, `cartola_batches`, and `cartola_transactions` exist with the exact column definitions from the architecture document
**And** `bank_accounts.account_number` has a foreign key constraint to `plan_de_cuentas.account_number`

**Given** `POST /api/v1/plan-de-cuentas/sync` is called by a `contador`
**When** the sync runs
**Then** all accounts from the Google Sheets chart of accounts are upserted into `plan_de_cuentas` (account_number as primary key — no duplicates)
**And** `synced_at` is updated to the current timestamp for every upserted row
**And** the response returns `{"synced": N, "updated": M}` with the counts

**Given** `GET /api/v1/plan-de-cuentas/` is called by an authenticated user
**When** the request is received
**Then** all active accounts are returned as a list, ordered by `account_number`
**And** the response is used by the frontend bank account registration form

**Given** `POST /api/v1/bank-accounts/` is called by a `contador` with valid payload
**When** the request is received
**Then** a new `bank_accounts` row is created, with `account_number` validated against existing `plan_de_cuentas` entries
**And** if `account_number` does not exist in `plan_de_cuentas`, the endpoint returns HTTP 400

**Given** `GET /api/v1/bank-accounts/` is called by an authenticated user
**When** the request is received
**Then** all bank accounts (active and inactive) are returned with their linked `plan_de_cuentas` account name

**Given** `PATCH /api/v1/bank-accounts/{id}` is called by a `contador`
**When** the request is received with `{"active": false}`
**Then** the bank account is deactivated and no longer used for CC identification in the dashboard

**Given** `SupabaseRepository` is implemented in `backend/app/repositories/supabase_repository.py`
**When** it is used by any service
**Then** it implements the same `DataRepository` interface as `SheetsRepository`
**And** no service outside `repositories/` imports the Supabase client directly

---

### Story 4.1: PDF Upload + Gemini Extraction

As a contador,
I want to upload a credit card statement PDF and have it automatically extracted into structured transactions,
So that I don't have to manually enter each transaction and can process any bank's format without configuration.

**Acceptance Criteria:**

**Given** the contador navigates to `CartolaUploadPage.tsx`
**When** the page loads
**Then** a file input accepts PDF files up to 20MB (NFR3)
**And** a dropdown lets the contador select the bank account from registered `bank_accounts` (active only)

**Given** the contador selects a file and clicks upload
**When** `POST /api/v1/cartolas/upload` is called (multipart form)
**Then** the endpoint returns immediately with `{"status": "processing", "batch_id": "..."}` — extraction runs asynchronously (NFR3)
**And** the frontend `useCartolaUpload.ts` hook polls `GET /api/v1/cartolas/{batch_id}` every 3 seconds for status

**Given** `GeminiClient.extract_pdf()` receives the PDF bytes
**When** Gemini returns a response
**Then** the response is validated against the extraction schema: `opening_balance`, `closing_balance`, `currency`, and `transactions[]` (NFR19)
**And** if the response is malformed or missing required fields, the batch is rejected cleanly — no data is persisted (NFR12)

**Given** extraction succeeds and schema validation passes
**When** the pipeline saves to Supabase
**Then** one `cartola_batches` row is created with `status = 'extracted'`
**And** one `cartola_transactions` row is created per extracted transaction, each with `category_status = 'pending'`
**And** `GeminiClient` is the only file in the codebase that imports the Gemini SDK (NFR17)

**Given** the extracted transactions are saved
**When** the pipeline checks for duplicates within the batch
**Then** any transaction with identical `date + amount + description` as another in the same batch is flagged with a warning (FR26)
**And** any transaction with `amount = 0` or an amount exceeding 3× the account's historical average is flagged (FR27)
**And** flags are stored as metadata on the `cartola_transactions` row and surfaced in the UI

**Given** the frontend polls and receives `status = 'extracted'`
**When** the extraction completes
**Then** the UI shows a summary: transaction count, opening balance, closing balance, and any flags
**And** the user is prompted to proceed to balance validation

---

### Story 4.2: Balance Validation

As a contador,
I want to review and confirm the extracted opening and closing balances before the statement is processed,
So that I catch Gemini extraction errors early and ensure the data integrity of every uploaded statement.

**Acceptance Criteria:**

**Given** the batch is in `status = 'extracted'`
**When** the balance validation section renders in `CartolaUploadPage.tsx`
**Then** three fields are shown: opening balance (editable, pre-filled from Gemini), Σ transactions (read-only, calculated), closing balance (editable, pre-filled from Gemini)
**And** a discrepancy indicator shows `closing_balance - opening_balance - sum_transactions` in real time as the user edits (FR23)

**Given** the discrepancy indicator shows `0`
**When** the contador clicks "Confirmar validación"
**Then** `PATCH /api/v1/cartolas/{batch_id}/validate-balance` is called with the confirmed balance values
**And** the batch `status` transitions to `'balance_validated'`
**And** the categorization pipeline is triggered automatically (FR22, FR24)

**Given** the discrepancy indicator shows a non-zero value
**When** the contador attempts to confirm
**Then** the confirm button is disabled and an error message is shown: "El saldo no cuadra — revisá los valores" (FR24)
**And** the contador can edit the opening or closing balance fields to correct the discrepancy

**Given** the contador cannot resolve the discrepancy
**When** they choose to override
**Then** a mandatory text input is shown: "Justificación del descuadre" (FR25)
**And** the confirm button is enabled only after the justification field is filled
**And** `override_justification` is saved on the `cartola_batches` row

---

### Story 4.3: Dashboard Integration

As an owner or contador,
I want credit card transactions from uploaded statements to appear in the dashboard at individual movement level,
So that I can see exactly what composes each credit card expense instead of a single lump-sum payment.

**Acceptance Criteria:**

**Given** `SupabaseRepository` has a method `get_cartola_transactions(account_number, period)`
**When** called with a valid account and period
**Then** it returns all `cartola_transactions` for that batch, including `category_status` and `category_confirmed` or `category_auto`

**Given** `DashboardService` processes ledger entries for entity EAG
**When** it encounters a ledger entry whose `account_number` matches a `bank_accounts` record
**Then** it queries `SupabaseRepository` for a `cartola_batch` matching that account and period
**And** if a batch exists with `status IN ('categorized', 'confirmed')`, the single ledger entry is replaced by the individual `cartola_transactions` in the response
**And** if no batch exists, the ledger entry is returned unchanged (fallback behavior preserved)

**Given** the dashboard frontend receives a response with cartola transactions
**When** the transactions render
**Then** `confirmed` transactions display normally
**And** `suggested` transactions display with a red badge "por revisar" on the category (FR19)
**And** `pending` transactions are grouped under a row labeled "Pendiente de categorizar"

**Given** a period has no uploaded cartola for a CC account
**When** the dashboard renders
**Then** the original Laudus ledger entry for that CC payment is shown unchanged — no regression in existing behavior

---

## Epic 5: Categorización Inteligente de Transacciones *(Phase 2)*

El contador puede revisar y confirmar la categorización de cada transacción de tarjeta de crédito — sugerida automáticamente por historial o Gemini — y el sistema aprende de las correcciones para mejorar sugerencias futuras.

**FRs cubiertos:** FR28, FR29, FR30, FR31
**NFRs cubiertos:** NFR19

---

### Story 5.1: Categorization Pipeline

As a system,
I want to automatically suggest a category for each extracted transaction using historical matches first, then Gemini as fallback,
So that the contador has pre-filled suggestions to review rather than categorizing every transaction from scratch.

**Acceptance Criteria:**

**Given** a batch transitions to `status = 'balance_validated'`
**When** the categorization pipeline runs automatically
**Then** for each `cartola_transaction` in the batch, Stage 1 (historical match) runs first

**Given** Stage 1 runs for a transaction
**When** it searches `cartola_transactions` for prior rows with the same `description` AND `category_status = 'confirmed'`
**Then** if a match is found, `category_auto` is set to the confirmed category, `match_source = 'historical'`, `category_status = 'suggested'`
**And** Stage 2 (Gemini) is skipped for this transaction

**Given** Stage 1 finds no match for a transaction
**When** Stage 2 (Gemini fallback) runs
**Then** `GeminiClient` is called with the transaction description, amount, and the full list of 85 expense accounts from `plan_de_cuentas`
**And** Gemini must select from this fixed list only — free-form category responses are rejected
**And** if a valid category is returned: `category_auto` is set, `match_source = 'gemini'`, `category_status = 'suggested'`
**And** if Gemini returns an invalid or no match: `category_status` remains `'pending'`

**Given** the pipeline finishes processing all transactions in a batch
**When** all rows are updated
**Then** `cartola_batches.status` transitions to `'categorized'`
**And** `GET /api/v1/cartolas/{batch_id}` reflects the updated status and category counts (suggested / pending)

**Given** the category weight update rule (FR31)
**When** a `description` pattern has been corrected by the contador 30 or more times
**Then** the corrected category takes precedence over any prior historical match for that pattern
**And** this is implemented as a count check in `CategorizationService` — no separate table required

---

### Story 5.2: Category Review UI

As a contador,
I want to review, accept, modify, or reject the suggested category for each transaction,
So that categorized data is accurate and explicitly confirmed before it affects the dashboard.

**Acceptance Criteria:**

**Given** the contador navigates to `CartolaReviewPage.tsx`
**When** the page loads
**Then** `GET /api/v1/categorization/pending` is called and returns all transactions with `category_status IN ('pending', 'suggested')`, grouped by batch → account → period

**Given** the review list is displayed
**When** the contador views a transaction
**Then** description, amount, date, suggested category (if any), and `match_source` are shown
**And** `suggested` transactions show the category pre-selected in the category dropdown
**And** `pending` transactions show an empty dropdown with placeholder "Seleccionar categoría"

**Given** the contador accepts a suggestion or selects a category
**When** they confirm the row
**Then** `PATCH /api/v1/transactions/{id}/category` is called with the selected category
**And** the transaction `category_status` transitions to `'confirmed'`, `category_confirmed` is set, `reviewed_by` and `reviewed_at` are recorded (FR30)

**Given** the contador wants to confirm all suggestions in a batch at once
**When** they click "Confirmar todas las sugerencias"
**Then** `POST /api/v1/transactions/bulk-confirm` is called for all `suggested` transactions in that batch
**And** all targeted transactions transition to `'confirmed'` in a single operation (FR29)

**Given** all transactions in a batch reach `category_status = 'confirmed'`
**When** the last confirmation is processed
**Then** `cartola_batches.status` transitions to `'confirmed'`
**And** the dashboard immediately reflects the confirmed transactions without requiring a page reload

---

### Story 5.3: Completar Story 3.5 — Drill-down Tarjetas de Crédito

As an owner,
I want to click any credit card summary figure in the dashboard and see the individual confirmed transactions behind it,
So that I can understand exactly what makes up each credit card expense at merchant level.

**Acceptance Criteria:**

**Given** a credit card entry in the dashboard has a confirmed cartola batch (Story 4.3 explosion logic active)
**When** the user clicks the summary figure
**Then** a detail panel opens showing the individual `cartola_transactions` for that account and period
**And** each row shows: date (DD/MM/YYYY), description (merchant name), amount, currency, and confirmed category (FR19)
**And** rows are sorted by date descending (FR18)

**Given** the detail panel is open
**When** any transaction has `category_status = 'suggested'`
**Then** the category is shown in red with a badge "por revisar"
**And** a link to `CartolaReviewPage` is shown for the contador role

**Given** the detail panel is open
**When** the user clicks outside the panel or the close button
**Then** the panel closes and the dashboard view is restored without data refetch

**Given** the account has no cartola uploaded for that period
**When** the user drills down
**Then** the existing ledger entry transactions are shown (original Story 3.5 fallback behavior — no regression)

---

## Epic 9: Migración a Beancount *(Phase 2 — pivot c4)*

> **Status:** epic activo desde 2026-04-30 (decisión de pivot c4 aprobada por Ary). Reemplaza el approach Sheets+Supabase de Phase 2 por un ledger Beancount versionado como source of truth.

### Goal

Reemplazar Sheets+Supabase como source of truth por un ledger Beancount versionado en `ledger/` (subfolder del repo `LAUDUS_Backup`), con **Fava** como UI del contador y el **frontend LAUDUS actual** consumiendo un thin API que expone queries BQL. Importers Laudus ERP (cron sábados 23:59 + on-demand) y cartolas PDF (beangulp + Gemini) escriben directivas a zonas disjuntas; `bean-check` valida pre-commit. La family ve dashboards idénticos visualmente — cambia el motor, no la UX.

### Justificación

Producto de la decisión de pivot c4 documentada en:
- `_bmad-output/planning-artifacts/research-beancount-pivot-2026-04-30.md` (análisis técnico de Mary)
- `_bmad-output/planning-artifacts/architecture-c4.md` (arquitectura concreta de Winston, ~5500 palabras, **input autoritativo de este epic**)
- `_bmad-output/coordination/winston-x-moishe-c4-arquitectura-2026-04-30.md` (cierre con 9 de 10 open questions resueltas por Ary)

El motor Beancount nos da: (a) double-entry validation nativa (`bean-check`), (b) directivas `Balance`/`pad` que reemplazan toda la lógica custom de FR22-25, (c) BQL para queries ad-hoc del contador vía Fava, (d) git history como audit log, (e) categorización con `smart_importer` integrada al import en lugar de pipeline separado. Costo: descartar ~30% de Story 4.0 (tablas `cartola_*`); preservar 70% (registries `plan_de_cuentas` + `bank_accounts`).

### Scope incluido — 16 stories

> **Plan original = 12 stories (9.0–9.11).** Agregadas después por correct-course: 9.12 (2026-05-05, reconciliación cartolas), 9.13 (2026-05-06, RBAC), 9.14 (2026-06-17, migrar bank-accounts → cierre de Supabase) y 9.15 (2026-06-17, flip del balance-sheet a Beancount). Además, la Story 9.5 generó spikes/sub-stories con sufijo de letra (9.5b–9.5h) documentados en `sprint-status.yaml` — no se listan acá por ser derivados de ejecución, no scope de planning.

- **Story 9.0** — Wrapper `bean-check` para Fava editor (pre-requisito de F2)
- **Story 9.1** — Bootstrap histórico Beancount (F0; depende de Q4 cerrada antes de ejecutar)
- **Story 9.2** — Backend thin API con BQL endpoints (F1)
- **Story 9.3** — Fava deploy en Render con basic auth (F2)
- **Story 9.4** — Importer Laudus en producción (F3 — cron sábados 23:59 + on-demand)
- **Story 9.5** — PDF upload + extracción a JSON canónico (F4 — era 4.1a)
- **Story 9.6** — Beangulp importer JSON → directivas (F4 — era 4.1b)
- **Story 9.7** — Categorización con `smart_importer` + Patrón B (F5 — era 5.1 reformulada)
- **Story 9.8** — Frontend LAUDUS consume thin API + badge "pendiente revisar" (era 4.3 reformulada)
- **Story 9.9** — Validación de balances post-import via `bean-check` (era 4.2 reformulada)
- **Story 9.10** — Cron prices CLP/USD *(blocked-by-Q4)*
- **Story 9.11** — Plan de cuentas en Beancount (SoT) + deprecación de Sheets/Supabase *(scope ampliado per ADR-001)*
- **Story 9.12** — Dashboard de reconciliación sobre `cartola-discrepancies.jsonl` *(NUEVA 2026-05-05)*
- **Story 9.13** — RBAC 3 roles (family / contador / admin) *(NUEVA 2026-05-06 — done)*
- **Story 9.14** — Migrar bank-accounts a Beancount + apagar Supabase *(NUEVA 2026-06-17; depends_on 9.1, 10.3 — cierra el sunk-cost de Story 4.0)*
- **Story 9.15** — Flip del balance-sheet a Beancount (dashboards Activos/Pasivos) *(NUEVA 2026-06-17; desbloqueada por 9.11 — último paso del cutover de dashboards)*

### Scope excluido (explícito)

- **Reporte HTML semanal a Eduardo** — Q8 on hold, vuelve como story propia más adelante.
- **Reformulación del PRD** — los 3 `PRD-update needed` (shape JSON 4.1a, TC como Liabilities, threshold-30 reformulado) van a John (PM) en sesión separada.
- **Aplicación cuenta-por-cuenta del mapeo a las 293 cuentas** — es trabajo de la *ejecución* de la Story 9.1 (bootstrap), no del prep.
- **UI nueva para family** — el frontend actual se preserva sin cambios visuales; Story 9.8 solo cambia el data source y agrega el badge.
- **Decisión sobre fuente de FX (Q4)** — sesión dedicada antes de ejecutar Story 9.1 / desbloquear Story 9.10.
- **Stories 5.2 y 5.3 originales** — funcionalidad subsumida por 9.7 + 9.8; quedan marcadas `superseded-by-epic-9` en Epic 5.

### Dependencias bloqueantes

| Bloqueador | Afecta a | Cuándo se resuelve |
|---|---|---|
| Q4 — fuente de tipo de cambio (FX embebido en Laudus, no externa) | Story 9.1 (ejecución), Story 9.10 (prep + ejecución) | Sesión dedicada Ary + Moishe antes de F0 ejecución |
| Asignación de "el contador" como persona real | Story 9.3 onboarding (no la implementación) | Decisión Ary, no bloquea prep ni deploy |
| 9.0 done | 9.3 (Fava deploy con editor habilitado) | Secuencial |
| 9.2 done (al menos endpoints leyendo del ledger) | 9.8 (frontend consume thin API) | Secuencial |
| 9.5 done | 9.6 (beangulp consume JSON canónico) | Secuencial — pero 9.5 es paralelizable desde el día 1 con 9.0/9.1/9.2 |
| 9.6 done | 9.7 (smart_importer integrado al pipeline de import) | Secuencial |
| Paridad Sheets ↔ Beancount confirmada | 9.11 (deprecation Sheets) | Validación en F1+F3 |

### Reorganización de epics anteriores

- **Epic 4** cambia status a `done-with-sunk-cost`. Story 4.0 se preserva como `done` con nota de costo hundido (~30% se descarta, ~70% sobrevive como registry). Stories 4.1a/4.1b/4.2/4.3 se transfieren a Epic 9 como 9.5/9.6/9.9/9.8 reformuladas.
- **Epic 5** cambia status a `superseded-by-epic-9`. Story 5.1 se transfiere como Story 9.7. Stories 5.2 y 5.3 quedan como `superseded-by-epic-9` con nota de que su funcionalidad está cubierta por 9.7 + 9.8.

### FRs / NFRs cubiertos

Inherits del Epic 4 + Epic 5 originales con reformulación bajo c4:

- **FR20-FR27** (Bank statement ingestion): cubiertos por 9.5 + 9.6 + 9.9. FR22-FR25 (balance validation) ahora son responsabilidad nativa de `bean-check` + `Balance` directives.
- **FR28-FR31** (Categorization): cubiertos por 9.7. FR31 reformulado: smart_importer + Patrón B (threshold confianza 0.85) + regla supra a 30 correcciones (`PRD-update needed`).
- **NFR3, NFR12, NFR17, NFR19** (Phase 2 NFRs): cubiertos por 9.5 + 9.6.
- **NFR13** (audit log append-only): cubierto por git history sobre `ledger/` + audit log operacional sobre acciones HTTP (mutaciones de upload/validate/categorize).

### Stories detalladas

Cada story tiene su propio archivo con AC + tasks + dev notes en `_bmad-output/implementation-artifacts/9-{n}-*.md`. La lista de stories arriba incluye links lógicos:

- [9.0 — Wrapper bean-check para Fava editor](../implementation-artifacts/9-0-wrapper-bean-check-fava-editor.md)
- [9.1 — Bootstrap histórico Beancount](../implementation-artifacts/9-1-bootstrap-historico-beancount.md)
- [9.2 — Backend thin API con BQL](../implementation-artifacts/9-2-backend-thin-api-bql.md)
- [9.3 — Fava deploy en Render](../implementation-artifacts/9-3-fava-deploy-render.md)
- [9.4 — Importer Laudus producción](../implementation-artifacts/9-4-importer-laudus-produccion.md)
- [9.5 — PDF upload + extracción JSON canónico](../implementation-artifacts/9-5-pdf-upload-gemini-json-canonico.md)
- [9.6 — Beangulp importer JSON → directivas](../implementation-artifacts/9-6-beangulp-importer-json-to-directivas.md)
- [9.7 — Categorización smart_importer + Patrón B](../implementation-artifacts/9-7-categorizacion-smart-importer-patron-b.md)
- [9.8 — Frontend LAUDUS consume thin API + badge](../implementation-artifacts/9-8-frontend-thin-api-badge-pendiente.md)
- [9.9 — Validación de balances post-import](../implementation-artifacts/9-9-validacion-balances-bean-check.md)
- [9.10 — Cron prices CLP/USD *(blocked-by-Q4)*](../implementation-artifacts/9-10-cron-prices-clp-usd.md)
- [9.11 — Plan de cuentas en Beancount (SoT) + deprecación de Sheets/Supabase](../implementation-artifacts/9-11-deprecation-sheets.md)
- [9.12 — Dashboard de reconciliación](../implementation-artifacts/9-12-dashboard-reconciliacion.md) *(NUEVA 2026-05-05)*
- [9.13 — RBAC 3 roles](../implementation-artifacts/9-13-rbac-3-roles.md) *(NUEVA 2026-05-06 — done)*
- [9.14 — Migrar bank-accounts a Beancount + apagar Supabase](../implementation-artifacts/9-14-migrar-bank-accounts-beancount.md) *(NUEVA 2026-06-17 — destapada al verificar el frontend para 9.11; bank-accounts es el último consumidor vivo de Supabase. depends_on: [9.1, 10.3]. Cierra el sunk-cost de Story 4.0.)*
- [9.15 — Flip del balance-sheet a Beancount](../implementation-artifacts/9-15-flip-balance-sheet-beancount.md) *(NUEVA 2026-06-17 — último paso del cutover de dashboards; desbloqueada por 9.11. Diseño: [design-note](design-note-balance-sheet-flip-2026-06-17.md).)*

> **Nota de actualización (2026-06-17):** el encabezado "12 stories" y el listado de scope arriba quedaron desactualizados respecto de `sprint-status.yaml` (no reflejan 9.12, 9.13 ni 9.14, agregadas después del plan original). El índice autoritativo por-story es esta lista de links + `sprint-status.yaml`.

---

## Epic 6: Reconciliación Mensual *(Phase 2 — reformulado bajo c4)*

> **Status:** reformulado y activo desde 2026-06-20. La definición original (FR32–FR35, escrita pre-pivot c4) asumía "reconciliación contra los totales de Google Sheets / ERP". Bajo c4 eso está obsoleto: Beancount es la fuente única (Sheets/Supabase apagados en 9.11/9.16) y el motor de reconciliación ya se construyó dentro de Epic 9. Este epic deja de ser "construir la reconciliación" y pasa a ser **wirear el motor existente al flujo de upload real + cerrar el lazo de resolución**.

### Goal

> **⚠️ Goal reformulado 2026-06-22 (modelo A, decisión Ary durante el dev de 6.1).** El goal original (abajo, tachado) asumía que las líneas limpias de la cartola **se contabilizan** en el ledger. El dev de 6.1 destapó que eso produce **doble conteo** vs `imports/laudus/*` (Laudus YA postea a las cuentas de banco/TC; `main.beancount` incluye ambos). Ary decidió **modelo A: la cartola reconcilia SIN postear** — detecta diferencias, no re-contabiliza. Ver `6-1-wiring-promote-reconcile.md` → "BLOCKER RESUELTO".

**Goal (modelo A): detección + anotación-on-aprobación.** Que subir una cartola bancaria dispare la **reconciliación real** cartola ↔ Laudus/Beancount: cada línea se cruza contra el asiento Laudus del mismo período/cuenta, se clasifica en uno de los 7 estados de matching, y **las diferencias** (no las coincidencias) se emiten al JSONL append-only que el dashboard 9.12 consume. La cartola **NO re-contabiliza** — Laudus sigue siendo la fuente contabilizada y validada peso-por-peso vs el contador. El contador revisa las diferencias en el dashboard y, al **aprobar** una (ej. un `missing-in-laudus` que confirma como gasto real), el sistema **anota esa transacción en Beancount** (bean-check + git). El período se marca reconciliado cuando no quedan discrepancias abiertas.

> ~~**Goal original (pre-modelo-A, OBSOLETO):** ...las líneas limpias se contabilizan en el ledger y las discrepancias se emiten al JSONL... El contador resuelve las discrepancias desde el dashboard y el sistema marca el período como reconciliado cuando no quedan discrepancias abiertas.~~

### Justificación — qué cambió con c4

El motor completo **ya existe y está testeado** (se construyó como parte de Epic 9, Stories 9.6b + 9.10 + 9.12). Verificado contra el código 2026-06-20:

| Pieza | Ubicación | Estado |
|---|---|---|
| Motor de matching (7 estados, tolerancias) | `pipeline/importers/matching_engine.py` — `match()` | ✅ testeado |
| Loader de asientos Laudus del período | `pipeline/importers/matching_engine.py` — `load_laudus_entries()` | ✅ testeado |
| FX implícita USD + validación BCCh 5% | `pipeline/importers/fx_calculator.py` | ✅ testeado |
| Orquestador matching→FX→behavior→entries | `pipeline/importers/reconcile.py` — `reconcile_and_build()` | ✅ testeado (integración) |
| JSONL append-only + dedup + resolución | `pipeline/importers/discrepancy_writer.py` | ✅ testeado |
| Re-emit del `.beancount` post-resolución | `pipeline/importers/reconcile.py` — `commit_reconciliation()` | ✅ testeado |
| Dashboard de reconciliación + badge | `frontend` — `ReconciliationPage` (9.12) | ✅ DONE, lee el JSONL |

**El gap es el SEAM del promote, no el motor.** El flujo de upload real termina en `validate_balance()` → `cartola_pdf_importer.promote()`, que llama `importer.extract()` — la ruta "match perfecto" de 9.6a, **sin reconciliación**. Ningún código de producción invoca `reconcile_and_build` (confirmado por grep: solo aparece en tests). Wirear ese seam = activar la reconciliación en vivo.

### ✅ Decisión de diseño D1 — CERRADA 2026-06-20 (Ary): Opción A, gate estricto, mismo flujo para todas las cartolas

**Decisión:** una cartola con **cualquier** discrepancia bloqueante (`value-mismatch` / `missing-in-cartola`) **NO se promueve** al ledger hasta que el contador resuelva todas vía el dashboard 9.12. El comportamiento es **"todo o nada"**: o no se contabiliza nada (cartola bloqueada) o se contabiliza todo (cartola limpia). **Mismo flujo para TC y cuenta corriente** — sin diferenciar por tipo de cuenta.

**Por qué cierra el conflicto del cuadre limpiamente:** como nunca se postea un subconjunto parcial, `Σtx emitidas = closing − opening` se cumple siempre que la cartola se promueve → la directiva `Balance` de cierre de 9.6a queda válida **tal cual**, sin tocarla. El override pad+balance de 9.9 sigue existiendo solo para su caso original (un descuadre real de extracción `closing ≠ opening + Σ`), que es distinto de una discrepancia de reconciliación.

**El conflicto que resolvía (contexto):** `reconcile_and_build` no emite `value-mismatch` ni `missing-in-cartola` (decisiones Ary 2026-06-17: la cartola es la fuente de verdad; un asiento solo-en-Laudus no se re-contabiliza para evitar doble conteo vs `imports/laudus/*`). Si se posteara el subconjunto + se mantuviera el `Balance` estricto, bean-check se pondría rojo. Opción A lo evita posteando todo-o-nada.

**Implicancia operativa (aceptada):** el contador debe resolver todas las discrepancias bloqueantes de una cartola antes de que entre algo de esa cartola al ledger. A volumen family-office es manejable.

**Flujo resultante para 6.1:**
1. Al promover, correr `reconcile_and_build` → entries + discrepancias.
2. Appendear las discrepancias al JSONL **siempre** (para que el dashboard 9.12 las muestre, haya o no bloqueo).
3. Si hay ≥1 discrepancia bloqueante → **no** escribir/commitear el `.beancount`; devolver estado "bloqueada, N discrepancias por resolver".
4. El contador resuelve cada una en 9.12 (`commit_reconciliation` re-emite).
5. Cuando no quedan bloqueantes → la cartola se promueve limpia (todo postea, `Balance` cuadra).

> **Considerado y descartado (2026-06-20):** flujo distinto para cuenta corriente vs. TC. Ary lo evaluó y decidió unificar — mismo flujo para todas las cartolas. No re-litigar sin una necesidad nueva concreta.

### Scope incluido — stories

- **Story 6.1 — Wiring del promote a `reconcile_and_build` (el SEAM)** *(core)*
  Reemplazar el `extract()` perfect-path por la construcción reconciliadora en el flujo de upload: armar `CartolaLine[]` desde el canónico staged, cargar `load_laudus_entries()` para el período/cuenta, llamar `reconcile_and_build()` (con `category_predictor` para `category_for` + `fx-bcch-eom.jsonl` para FX), renderizar las entries → `.beancount`, appendear las discrepancias retornadas a `_meta/cartola-discrepancies.jsonl`, bean-check + git commit. Implementa la decisión **D1**. Cubre FR32 (el trigger = el upload+promote por cuenta/período) + FR33 (cross-check) por construcción.

- **Story 6.2 — Desglose de cartola TC en USD + FX-por-cartola** *(core, priorizada 2026-06-22)* — `ready-for-dev`
  Disparada por revisar `samples/`: **~50% de las cartolas reales son estados de cuenta INTERNACIONALES en USD** (el companion del nacional CLP, con las compras en el exterior: eBay/Amazon/etc.). Hoy **no se pueden reconciliar**: el FX per-línea de 9.6b necesita un asiento Laudus por línea, pero Laudus solo tiene el **lump CLP** del pago (bank → `Expenses:EAG:TC:...Us-43000X`). **Regla FX (Ary):** FX único por cartola = (lump CLP en Laudus para esa cuenta `...Us` + período) ÷ (total USD facturado, excl. `MONTO CANCELADO`); cada línea USD × FX = su CLP; la suma itemizada = el lump → lo **supersede** (desglose "estado 2", `project_tc_pasivo_dos_estados`). Modelo de cuentas ya existe (cada tarjeta tiene su `Tc{n}{Nombre}Us-43000X`). Toca el reconcile (6.1) + el modelo FX. Ver `6-2-desglose-tc-usd-fx.md`.

- **Story 6.3 — Aprobar una diferencia → anotarla en Beancount** *(core, modelo A — la 2da mitad; ex-6.2, renumerada al priorizar USD)* — `ready-for-dev`
  La continuación directa de 6.1: bajo modelo A nada de la cartola se postea, así que **aprobar** una diferencia debe escribirla explícitamente al ledger. Scope núcleo = `missing-in-laudus` + acción `confirm-cartola-only` (el contador confirma que esa línea de cartola es un gasto real que Laudus no tiene) → renderizar la transacción y escribirla a la zona `manual/` con bean-check + git, **antes** de cerrar la discrepancia (atomicidad). Reusa `commit_reconciliation` (write-and-replace + bean-check + rollback + git, ya testeado) + `_build_postings` (convención de signo Liabilities/Assets). Wirea `resolve()` (hoy solo appendea la línea de resolución al JSONL — el re-emit al ledger era el seam pendiente de 9.6b/9.12). Cubre lo que Ary pidió como *"que muestre solo las diferencias y pida aprobación para anotarlas"*. Ver `6-2-aprobar-diferencia-anotar-beancount.md`.
  *Diferido a story aparte: las acciones que **editan un asiento Laudus existente** (`value-mismatch`/`accept-cartola`, soft-mismatch `accept-cartola-*`) — mecanismo distinto y más riesgoso (mutar `imports/laudus/*`).*

- **Story 6.4 — Completar el dashboard de reconciliación (FR34)** *(ex-6.2/6.3, polish de 9.12, deferido)*
  Cerrar los defers de frontend de 9.12 que hacen al reporte usable end-to-end: historial del drill-down (`getHistory` ya existe, nunca se llama), filtros `year_month`/`bank_account_id` en la UI (backend ya los soporta), badge que no desaparece en error de `/count`, moneda correcta en la celda Laudus (hoy hardcodea CLP), y action-sets/semántica blocking para los estados FX (`fx-bcch-missing`/`fx-implausible`). **+ input de categoría para `confirm-cartola-only` (movido desde 6.3).** Ver `deferred-work.md` → review de 9.12.

- **Story 6.5 — Cierre de período de reconciliación (FR35)** *(ex-6.3/6.4, small)*
  Marcar un período (cuenta + mes) como "reconciliado completo" cuando no quedan discrepancias abiertas (todas tienen línea de resolución en el JSONL). Probablemente derivable como vista sobre el JSONL existente (estado = discrepancias_abiertas == 0) + indicador en el dashboard; evaluar si requiere un marcador explícito persistido o basta con la derivación. Definir alcance al crear la story.

### Scope excluido (explícito)

- **Cron de reconciliación programada / "trigger por entidad+período" como acción standalone** — bajo c4 el trigger es el upload de la cartola (por cuenta/mes), no una corrida batch separada. FR32 se satisface por el flujo de upload; no se construye un runner aparte salvo que aparezca una necesidad real.
- **Reconciliación de cartolas de inversión / custodios** — invariantes no-aritméticos (qty×precio, Σholdings), schema canónico distinto. Fuera de scope (ver `deferred-work.md` → technical research 2026-06-10).
- **Corrección plena de TC estado 2 (desglose de cartola de TC)** — diseño de Valentina; necesita una cartola de TC de muestra. Diferido (ver memoria `project_tc_pasivo_dos_estados`).
- **Saldo corrido por línea / continuidad inter-cartola** — extensiones de validación deferidas (ver `deferred-work.md` → technical research 2026-06-10); no bloquean la reconciliación core.

### Dependencias

| Bloqueador | Afecta a | Estado |
|---|---|---|
| **D1 — decisión del cuadre** (Balance/override vs. líneas bloqueantes) | 6.1 (ejecución) | ✅ cerrada 2026-06-20 — Opción A (gate estricto, todo-o-nada, mismo flujo todas las cartolas) |
| Motor 9.6b + dashboard 9.12 + FX 9.10 | todo Epic 6 | ✅ done (Epic 9) |
| `_meta/fx-bcch-eom.jsonl` poblado para meses USD (9.10 on-demand manual) | 6.1 en cuentas USD | ⚠️ manual hoy — degrada a discrepancia `fx-bcch-missing` si falta |
| Cartolas reales subidas por el contador | validación end-to-end de 6.1 | acción de Ary/contador |

### FR mapping (reformulado bajo c4)

- **FR32** (trigger monthly reconciliation run, entity+period) → el trigger es el **upload+promote** de la cartola, por `bank_account_id` y período. Cubierto por 6.1.
- **FR33** (cross-check ERP totals vs. bank statement totals) → el motor de matching cruza línea-por-línea (más fuerte que totales). Cubierto por 6.1 (motor 9.6b).
- **FR34** (reconciliation report: matched / unmatched ERP / unmatched bank) → los 7 estados en el dashboard 9.12. Cubierto por 6.4 (polish).
- **FR35** (mark period complete when all resolved) → 6.5.
- **Anotación-on-aprobación** (modelo A — no estaba en los FR originales porque asumían auto-posteo) → 6.3: aprobar un `missing-in-laudus` escribe la tx al ledger.
- **Desglose TC USD** (no estaba en los FR — c4 lo destapa: ~50% de cartolas son estados USD internacionales) → 6.2: importar/reconciliar cartolas USD con FX-por-cartola, superseding el lump Laudus.
- **NFR4** (reconciliación asíncrona, UI responsive) → el upload ya es async (BackgroundTasks + polling de 9.5); el promote/reconcile corre dentro de ese flujo. Verificar latencia al wirear.

### Nota sobre el SEAM (Completion Notes de 9.6b)

El dev de 9.6b dejó el seam explícito y por qué no lo flipeó: *"No flipeé el `promote` de 9.6a para no cambiar su comportamiento ni romper sus tests — el cuándo corre la reconciliación es decisión del flujo de upload. Engine + loader + orquestador ya listos y testeados para wirear."* Epic 6 es exactamente esa decisión + el wiring.
