---
stepsCompleted: [step-01-init, step-02-discovery, step-02b-vision, step-02c-executive-summary, step-03-success, step-04-journeys, step-05-domain, step-06-innovation, step-07-project-type, step-08-scoping, step-09-functional, step-10-nonfunctional, step-11-polish, step-12-complete, step-e-01-discovery, step-e-02-review, step-e-03-edit]
workflowStatus: complete
completedAt: '2026-04-06'
lastEdited: '2026-04-08'
editHistory:
  - date: '2026-04-08'
    changes: 'FR31 rewritten with testable acceptance criteria (30-correction threshold). NFR8/11/17/19 verified clean — no implementation leakage found.'
classification:
  projectType: web_app
  domain: fintech
  complexity: medium-high
  projectContext: brownfield
inputDocuments:
  - CLAUDE.md
  - estado_actual.md
projectDocsCount: 2
briefCount: 0
researchCount: 0
workflowType: 'prd'
---

# Product Requirements Document — EAG Family Office

**Author:** Ary
**Date:** 2026-04-06

## Executive Summary

EAG Family Office is a platform that restores financial visibility to the head of a multi-entity family office by automating the full data pipeline from source systems (Laudus ERP + bank statements) to actionable, interactive dashboards. The system eliminates the manual Excel-based reporting process that has rendered financial data inaccessible to the primary decision-maker, replacing it with a continuously updated financial data layer featuring intelligent categorization, anomaly alerts, and a direct communication channel between the owner and the accountant.

**Target users:**
- **Owner** — head of the family economic group; consumes dashboards, sets financial priorities, flags questions on specific line items
- **Contador** — reviews and responds to owner queries, uploads bank statements, validates categorizations, executes monthly reconciliation

**Problem being solved:** Five related entities (EAG + 4 family members), 7 credit cards, and 10+ bank accounts across national and international banks (including Citi and Julius Baer) in two currencies (CLP + USD) are tracked in Laudus ERP — but detailed credit card transaction data is missing from the ERP entirely, reporting is too complex for the owner to consume independently, and there is no structured channel for owner-accountant collaboration on specific items. The owner has stopped reviewing financial data.

### What Makes This Special

Existing accounting tools (including Laudus itself) generate reports for accountants, not for owners. EAG Family Office inverts that: Laudus data is the input, not the output. The differentiator is the combination of:

1. **Automated ERP sync** — Laudus data flows in without manual intervention, eliminating transcription errors and version drift
2. **LLM-powered bank statement ingestion** — unstructured statements from any bank are sent to Gemini for extraction; each transaction receives a suggested category from the chart of accounts, refined by the accountant's corrections over time
3. **Owner-native dashboards** — predefined filter-driven views (assets/liabilities, income/expenses, income statement, equity variation) designed for a non-accountant decision-maker
4. **Proactive anomaly alerts** — month-over-month expense spikes surfaced automatically, before end-of-month review
5. **Structured owner ↔ accountant communication** — threaded comments on specific line items replace ad-hoc WhatsApp and email threads
6. **Monthly reconciliation** — automated cross-check between ERP records and bank statement data closes the gap created by the current credit-card-as-expense accounting practice

## Project Classification

| Dimension | Value |
|-----------|-------|
| **Project Type** | Web application with data pipeline backend |
| **Domain** | Fintech — family office financial reporting and reconciliation |
| **Complexity** | Medium-High — multi-entity, multi-currency, multi-bank, AI categorization |
| **Project Context** | Brownfield — existing Python sync pipeline (Laudus → Google Sheets) serves as the data layer foundation |
| **Team** | Solo developer (Ary + Claude) |

## Success Criteria

### User Success

- **Owner "aha moment":** Owner opens the dashboard and navigates financial data without accountant assistance — including credit card transaction detail previously invisible in the ERP
- Owner answers "what did we spend on X last month?" without opening Laudus or requesting an Excel file
- Owner identifies an expense anomaly through the dashboard before being notified by the accountant
- Owner sends a query on a specific line item and receives a response — entirely within the platform

### Business Success

- **3-month target:** Both accountants actively use the system as their primary workflow tool — uploading bank statements, categorizing transactions, and responding to owner queries through the app
- Reconciliation between Laudus ERP records and bank statement data is fully operational and validated by the accountants as accountably accurate
- Zero reliance on Excel for financial reporting or owner communication

### Technical Success

- Dashboard renders complete multi-entity financial data with filters responding in under 2 seconds
- Gemini-based extraction successfully processes statements from all active banks (BCI, Edwards/Chile, Santander, Citi, Julius Baer) in CLP and USD
- Reconciliation engine produces zero false positives on matched transactions
- AI categorization suggestion accuracy improves measurably month-over-month as accountant corrections accumulate

### Measurable Outcomes

| Metric | Target | Timeframe |
|--------|--------|-----------|
| Owner dashboard sessions per week | ≥ 3 | Month 2 onward |
| Accountant bank statement uploads via app | 100% of monthly statements | Month 3 |
| Reconciliation completion rate | 100% | Month 3 |
| Time to monthly financial close | Reduced vs current Excel baseline | Month 3 |

## User Journeys

### Journey 1 — Owner: First Dashboard View (Success Path)

**Persona:** Head of the family economic group. Relies on the accountant for financial data and has stopped reviewing financial reports because Excel-based reporting is too complex to consume independently.

**Opening Scene:** Monday morning. The owner wants to know how March closed on credit card expenses. Previously this required calling the accountant, waiting for an Excel file, and likely still not understanding the numbers.

**Journey:**
1. Opens the app → selects entity "EAG" + period "March 2026"
2. Views income/expenses panel with key amounts highlighted
3. Filters by "Tarjetas de Crédito" category → sees transaction-level breakdown per card
4. Notices an unusually high expense on Visa Infinity
5. Clicks the line item → leaves a comment: "What is this $2.4M expense?"
6. Accountant receives notification and responds the next day with detail

**Climax:** For the first time, the owner sees credit card detail broken down by transaction — not a global number in Excel, but what, when, and how much.

**Resolution:** The owner reviews financial data independently, weekly, without requiring accountant intervention.

---

### Journey 2 — Owner: Anomaly Alert (Edge Case)

**Opening Scene:** The system detects that Jocelyn Avayu's BCI checking account expenses increased 180% vs. the prior month.

**Journey:**
1. Owner receives notification: "Alert: JOCELYN expenses up 180% vs prior month"
2. Opens app → navigates directly to month-over-month variance view
3. Identifies the category responsible for the spike
4. Leaves comment: "Is this correct or a categorization error?"
5. Accountant confirms it was a one-time extraordinary expense → responds in-app

**Climax:** Owner is informed before month-end, with context, without searching for the data.

**Resolution:** Anomalies are caught proactively rather than discovered during monthly close.

---

### Journey 3 — Accountant: Monthly Bank Statement Upload (Core Workflow)

**Persona:** Accountant responsible for monthly financial close. Currently downloads bank statements manually, transcribes into Excel, and sends reports. Process is error-prone and time-consuming.

**Opening Scene:** April 5th. The accountant has downloaded March statements from BCI, Santander, and American Express.

**Journey:**
1. Opens "Cartolas" section → selects entity and bank → uploads PDF
2. System sends the file to Gemini → receives structured JSON with all transactions, opening balance, and closing balance
3. System validates: "Opening: $X · Movements: +$Y / -$Z · Calculated closing: $W · Statement closing: $W ✓"
4. If validation fails → "Discrepancy of $45,320 — review flagged transactions"; accountant cannot confirm without resolving or overriding with written justification
5. For each transaction, system shows suggested chart of accounts category
6. Accountant reviews: accepts 85 of 101, corrects 16 → confirms and saves
7. At month-end, triggers reconciliation → system cross-checks card totals against Laudus ERP records

**Climax:** What previously took hours of manual transcription now takes 20 minutes of review.

**Resolution:** Bank statement data is in the system, validated, categorized, and reconciled with full audit trail.

---

### Journey 4 — Accountant: Responding to Owner Queries

**Opening Scene:** Accountant receives a notification that the owner left 3 comments on transactions from the prior week.

**Journey:**
1. Opens "Pending queries" → sees 3 owner questions
2. For each: views the item in context (account, amount, date, category)
3. Responds directly in-app → marks as resolved

**Climax:** Full context is available inline — no Excel files or email threads to search.

**Resolution:** Owner-accountant communication is structured, traceable, and resolved faster.

## Domain-Specific Requirements

### Compliance & Regulatory

- System is an **internal reporting layer only** — Laudus ERP remains the authoritative source for SII tax compliance; no regulatory reporting obligations apply to this system
- Financial data belongs to private individuals and one legal entity — subject to Chilean data protection law (Ley 19.628); access restricted to authorized users only
- No KYC, AML, PCI-DSS, or open banking regulatory requirements apply given the internal, non-transactional nature of the product

### Technical Constraints

- **Storage Phase 1:** Google Sheets — prioritizes ease of manual inspection and correction during early validation; data models must be storage-agnostic from day one
- **Storage Phase 2:** PostgreSQL or equivalent — migration triggered by performance or volume constraints, not a fixed timeline
- **Access control:** Owner (read + comment) and Contador (read + write + upload + reconcile); Owner role cannot write financial data
- **Data sensitivity:** Financial data must not be exposed via public URLs, unauthenticated endpoints, or shared Google Sheets links

### Integration Requirements

- **Laudus ERP API:** Primary data source — existing Python sync pipeline to be refactored; incremental + historical sync of Balance Sheet and General Ledger
- **Gemini API:** LLM-based bank statement extraction — handles all bank formats and currencies without bank-specific configuration
- **Open banking APIs (to evaluate):** BCI has a documented API; other Chilean banks TBD; international banks (Citi, Julius Baer) unlikely — feasibility assessment required before committing
- **Google Sheets API:** Phase 1 data store — gspread-based integration already exists
- **Google OAuth:** Authentication layer — consistent with existing Google Workspace ecosystem

## Web Application Specific Requirements

### Architecture

- **Type:** Single Page Application (SPA) — required for interactive filter-driven dashboards without full page reloads
- **Frontend:** Open source framework (React or Vue.js); choice delegated to developer
- **Backend:** Python — FastAPI or Flask REST API layer, consistent with existing sync pipeline
- **Storage abstraction:** All data access goes through a backend service layer; no component writes directly to Google Sheets

### Browser & Device Support

- **Primary target:** Chrome (latest) — full support
- **Other browsers:** Added on explicit request only
- **Mobile/tablet:** Not required — desktop-only (minimum 1280px viewport)

### Authentication & Roles

- **Authentication:** Google OAuth — no username/password implemented
- **`owner` role:** Read all data, add/view comments, receive alerts
- **`contador` role:** Read all data, upload statements, categorize, respond to comments, run reconciliation
- **Authorization:** Enforced server-side on every API request

### Async Operations

- Bank statement LLM extraction and reconciliation runs are asynchronous with UI progress indicators
- No silent background jobs — all long-running operations surface status to the user
- All financial data mutations logged with timestamp and authenticated user

## Project Scoping & Phased Roadmap

### MVP Strategy

**Approach:** Experience MVP — restore financial visibility to the owner with the minimum viable system. Validate that automated ERP sync + multi-entity dashboards eliminate Excel dependency before building the more complex ingestion pipeline.

**Explicitly out of MVP:** Bank statement upload, AI categorization, reconciliation engine, comment system, anomaly alerts.

### Phase 1 — MVP

| Capability | Detail |
|-----------|--------|
| Laudus ERP sync | Balance Sheet + General Ledger, incremental + historical backfill |
| Multi-entity support | EAG + Jocelyn, Jeannette, Johanna, Jael as separate filterable entities |
| Dashboards | Assets/liabilities, income/expenses, income statement, equity variation |
| Filters | Entity, date range (month/quarter/year/custom), account category |
| Auth | Google OAuth with Owner/Contador role separation |
| Backend | Python FastAPI/Flask + storage abstraction layer |
| Storage | Google Sheets via gspread |

### Phase 2 — Growth (3-month target)

- Bank statement ingestion via Gemini: national banks (BCI, Edwards, Santander) + American Express, CLP and USD — pending real statement samples
- Balance validation gate: opening + Σ movements = closing before save
- AI-assisted categorization with accountant correction loop (295-account chart)
- ERP vs. bank statement monthly reconciliation engine
- Owner ↔ accountant threaded comments on line items
- Anomaly alerts: configurable month-over-month expense thresholds

### Phase 3 — Expansion

- International bank statement ingestion (Citibank, Julius Baer) — pending sample format availability
- Open banking API integration — pending feasibility assessment
- Fully automated reconciliation with no manual review
- Predictive alerts based on spending pattern history
- PostgreSQL migration from Google Sheets

### Risk Register

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Gemini extraction incomplete or inconsistent | High | Structured JSON schema in prompt; balance validation blocks save on mismatch |
| Julius Baer / Citi statement formats inaccessible | High | Defer to Phase 3; obtain samples before scoping |
| AI categorization accuracy insufficient for accountant trust | Medium | Suggestion-only model — accountant always reviews before save |
| Google Sheets performance at 2+ years of transaction volume | Medium | Storage abstraction from day one; PostgreSQL migration path defined |
| Solo team velocity | High | One feature at a time, fully functional before advancing; Phase 2 scoped iteratively |

## Functional Requirements

### 1. Authentication & Access Control

- **FR1:** Users can authenticate using their Google account (Google OAuth)
- **FR2:** The system grants access based on a predefined role: `owner` or `contador`
- **FR3:** Owner role users can view all financial data and add comments; they cannot create, edit, or delete financial records
- **FR4:** Contador role users can view all financial data, upload bank statements, edit categorizations, respond to comments, and trigger reconciliation
- **FR5:** The system logs all financial data mutations with timestamp and authenticated user

### 2. ERP Data Sync

- **FR6:** The system automatically syncs Balance Sheet data from the Laudus ERP API on a configurable schedule
- **FR7:** The system automatically syncs General Ledger data from the Laudus ERP API on a configurable schedule
- **FR8:** The system performs incremental sync (new records only) based on the last synced date
- **FR9:** The system supports full historical backfill from January 2021 to present
- **FR10:** The system prevents duplicate records using primary key deduplication (account+date for Balance Sheet; journalentryid+lineid for Ledger)
- **FR11:** The system tracks and displays the last successful sync timestamp per data type

### 3. Financial Dashboards

- **FR12:** Users can view financial data filtered by entity (EAG, Jocelyn, Jeannette, Johanna, Jael)
- **FR13:** Users can view financial data filtered by date range (month, quarter, year, custom)
- **FR14:** Users can view an assets/liabilities dashboard showing balance sheet positions per entity
- **FR15:** Users can view an income/expenses dashboard showing totals and breakdowns by account category
- **FR16:** Users can view an income statement (estado de resultado) per entity and period
- **FR17:** Users can view an equity variation dashboard comparing patrimony across periods
- **FR18:** Users can drill down from a dashboard summary to the individual transactions that compose a figure
- **FR19:** Users can view credit card transactions at individual movement level, including merchant, amount, date, and assigned category

### 4. Bank Statement Ingestion

- **FR20:** Contador can upload bank statement files (PDF, Excel) for any configured bank account
- **FR21:** The system sends uploaded bank statement files to Gemini with a structured extraction prompt, and receives a JSON payload containing all transactions (date, description, amount, currency), opening balance, and closing balance — regardless of source bank or document format
- **FR22:** The system validates extracted statements by confirming: opening balance + Σ movements = closing balance stated in the statement
- **FR23:** The system displays a validation summary showing calculated vs. stated closing balance and exact discrepancy if any
- **FR24:** The system blocks confirmation of a bank statement upload when balance validation fails
- **FR25:** Contador can override a failed balance validation with a mandatory written justification
- **FR26:** The system flags duplicate transactions within an uploaded statement (same date + amount + description)
- **FR27:** The system flags anomalous transactions (zero-amount entries, unusually large amounts vs. account history)

### 5. Transaction Categorization

- **FR28:** For each extracted bank statement transaction, the system suggests a category from the chart of accounts (295 accounts)
- **FR29:** Contador can accept, modify, or reject the system's category suggestion for each transaction
- **FR30:** The system saves categorized transactions only after explicit Contador confirmation
- **FR31:** The system updates category suggestion weights based on Contador correction history, such that previously corrected transaction patterns receive the corrected category as the primary suggestion on subsequent similar transactions. After 30 corrections of a given pattern, the corrected category becomes the primary suggestion for that pattern

### 6. Reconciliation

- **FR32:** Contador can trigger a monthly reconciliation run for a selected entity and period
- **FR33:** The system cross-checks ERP-recorded totals per account against bank statement transaction totals for the same period
- **FR34:** The system produces a reconciliation report showing matched items, unmatched ERP entries, and unmatched bank statement entries
- **FR35:** The system marks a reconciliation period as complete when all discrepancies are resolved or explicitly acknowledged

### 7. Collaboration & Communication

- **FR36:** Owner can add a comment on any individual transaction or line item visible in the dashboard
- **FR37:** Contador receives an in-app and email notification when the owner adds a comment
- **FR38:** Contador can view all pending owner comments in a unified inbox
- **FR39:** Contador can respond to an owner comment with full context of the referenced item visible inline
- **FR40:** Owner and Contador can mark a comment thread as resolved
- **FR41:** Owner receives an in-app and email notification when Contador responds to a comment

### 8. Alerts & Notifications

- **FR42:** The system detects when an expense category for an entity increases by more than a configurable threshold (%) vs. the prior month
- **FR43:** Owner receives an in-app and email notification when an anomaly alert is triggered
- **FR44:** Users can configure alert thresholds per entity and expense category

## Non-Functional Requirements

### Performance

- **NFR1:** Dashboard initial load completes in under 3 seconds on a standard Chrome desktop connection
- **NFR2:** Filter interactions (entity, date range, category) update visible data in under 2 seconds without full page reload
- **NFR3:** Bank statement file upload accepts files up to 20MB; Gemini extraction runs asynchronously and does not block the UI
- **NFR4:** Reconciliation runs asynchronously; the UI remains responsive and displays progress during execution

### Security

- **NFR5:** All data in transit is encrypted via HTTPS/TLS
- **NFR6:** Google Sheets containing financial data are not publicly accessible; access restricted to the service account and authorized Google accounts only
- **NFR7:** API endpoints enforce role-based access on every request; no endpoint trusts client-side role claims
- **NFR8:** Laudus API credentials, Google service account keys, and Gemini API keys are stored securely — never hardcoded or committed to source control
- **NFR9:** Session tokens expire after a configurable inactivity period (default: 8 hours)

### Reliability

- **NFR10:** Laudus API sync failures are logged with full error detail and do not silently produce partial or corrupted data
- **NFR11:** If the Laudus API returns an authentication failure response, the system retries with a fresh token exactly once before failing and logging the error
- **NFR12:** Bank statement uploads where Gemini extraction fails or returns incomplete data are rejected cleanly — no partial data is persisted
- **NFR13:** The sync pipeline maintains an append-only audit log of every run: timestamp, records processed, records added/updated, errors
- **NFR14:** A daily snapshot of the Google Sheets data store is written to a separate backup sheet

### Integration

- **NFR15:** The Laudus API client handles token expiry transparently without requiring user intervention
- **NFR16:** The storage layer is accessed exclusively through an abstraction interface — no component outside the data service layer writes directly to Google Sheets
- **NFR17:** Bank statement extraction handles all bank formats without per-bank configuration — a single integration point processes format variation across all supported banks
- **NFR18:** Google OAuth is the sole authentication mechanism; no username/password authentication is implemented
- **NFR19:** Gemini API responses conform to a defined output schema; responses are validated against this schema before processing — malformed responses are rejected
