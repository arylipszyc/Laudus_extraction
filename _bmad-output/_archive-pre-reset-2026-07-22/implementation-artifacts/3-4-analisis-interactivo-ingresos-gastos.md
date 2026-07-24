---
story: 3.4
title: Análisis Interactivo de Ingresos/Gastos
status: approved
epic: 3
---

# Story 3.4 — Análisis Interactivo de Ingresos/Gastos

## User Story

As an owner,
I want an interactive income/expenses dashboard with drill-down from Categoria1 to individual transactions,
So that I can understand the composition and trends of income and expenses at any level of detail.

## Context

This story **replaces** `IncomeExpensesPage.tsx` implemented in Story 3.3. The previous implementation provided only a flat account-level breakdown without meaningful hierarchy or interactive filtering.

This redesign provides:
- Summary cards for quick totals
- Pie charts for composition by Categoria1 (clickable)
- Bar chart for monthly timeline (clickable)
- Additive chart-level filters with reset button
- Hierarchical drill-down: Categoria1 → individual accounts → individual transactions

**No backend changes required** — all analytics are computed from the existing `GET /api/v1/ledger-entries` response, which already returns `Categoria1` and `accountName` fields.

The `getLedgerCategory()` classification logic from Story 3.3 is reused to distinguish income vs. expenses.

## Acceptance Criteria

**AC1 — Summary cards**

**Given** the user navigates to the Income/Expenses dashboard
**When** data loads for the selected entity and period
**Then** three summary cards are displayed: Total Ingresos, Total Gastos, and Resultado Neto
**And** all amounts use `toLocaleString('es-CL')` formatting
**And** Resultado Neto text is green (`text-green-600`) if ≥ 0, red (`text-destructive`) if < 0

---

**AC2 — Composition pie charts**

**Given** ledger data is loaded
**When** the user views the charts section
**Then** two pie charts are displayed side by side:
  - Left: composition of **Gastos** by Categoria1 (each slice = one Categoria1 value, sized by total)
  - Right: composition of **Ingresos** by Categoria1
**And** each slice tooltip shows: category name, formatted amount, and percentage of total
**And** categories with zero total are excluded from the pie

---

**AC3 — Timeline bar chart**

**Given** ledger data is loaded
**When** the user views the timeline chart
**Then** a grouped bar chart displays monthly Ingresos and Gastos totals across the selected period
**And** each group is labeled by month (e.g., "Ene 2026") derived from the `date` field (YYYY-MM-DD → year-month)
**And** income bars are green, expense bars are red
**And** the Y-axis uses `toLocaleString('es-CL')` tick formatting

---

**AC4 — Pie click applies Categoria1 filter**

**Given** the pie charts are displayed
**When** the user clicks a pie slice (e.g., "Gastos Operacionales")
**Then** a Categoria1 filter is added: the drill-down table shows only entries where `Categoria1` matches the selected value
**And** the clicked slice is visually highlighted (outer radius expanded or opacity change)
**And** clicking a second slice in the same pie adds it to the filter (additive — OR within Categoria1 dimension)
**And** clicking an already-selected slice removes it from the filter

---

**AC5 — Bar click applies period filter**

**Given** the timeline bar chart is displayed
**When** the user clicks a bar group (e.g., "Ene 2026")
**Then** a period filter is added: the drill-down table shows only entries from that year-month
**And** the clicked bar group is visually highlighted
**And** clicking a second bar adds it to the period filter (additive — OR within period dimension)
**And** clicking an already-selected bar removes it from the period filter

---

**AC6 — Filters are AND across dimensions**

**Given** a Categoria1 filter AND a period filter are both active
**When** the user views the drill-down table
**Then** only entries matching BOTH filters are shown (AND logic between dimensions)

---

**AC7 — Active filters display + Reset button**

**Given** one or more chart filters are active
**When** the user views the page
**Then** active filter chips are shown below the charts (one chip per selected category or period)
**And** a "Resetear filtros" button is visible
**When** the user clicks "Resetear filtros"
**Then** all chart-level filters are cleared and the full dataset is shown in the table
**And** the button and chips disappear

---

**AC8 — Drill-down table hierarchy**

**Given** the drill-down table is displayed (with or without chart filters)
**When** the user views it
**Then** entries are grouped first by Categoria1 (collapsible section), then by individual account (`accountName`)
**And** each Categoria1 section header shows the category name and subtotal
**And** each account row shows: account number, account name, and total for the period
**And** each account row is expandable to show individual transactions below it

---

**AC9 — Transaction detail on expand**

**Given** an account row is expanded
**When** transaction detail loads
**Then** individual transactions are shown: date (formatted DD/MM/YYYY), description, and amount
**And** income amounts are green, expense amounts are red
**And** transactions are sorted date descending
**And** a loading skeleton is shown while fetching
**And** "Sin movimientos en el período" is shown if no transactions exist for that account

---

**AC10 — Empty state and error state**

**Given** no data exists for the selected entity + period combination
**When** the dashboard loads
**Then** "No hay datos para el período seleccionado" is displayed with no broken charts

**Given** the API call fails
**When** the dashboard loads
**Then** "Error al cargar datos." is displayed in red

---

## Tasks

- [x] Task 1: Data aggregation helpers (`frontend/src/utils/ledgerAnalytics.ts`)
  - [x] Reuse `getLedgerCategory(accountNumber, categoria1)` logic — classify as income/expenses/other
  - [x] `groupByCategoria1(records, type: 'income'|'expenses')` — returns `{categoria1: string, accounts: {accountNumber, accountName, total, currency}[], subtotal: number}[]` sorted by subtotal desc
  - [x] `buildPieData(records, type)` — returns `{name: string, value: number}[]` per Categoria1, sorted by value desc, zero-totals excluded
  - [x] `buildTimeline(records)` — groups by year-month string ("2026-01"), returns `{period: string, label: string, income: number, expenses: number}[]` sorted chronologically
  - [x] Unit tests for all helpers with representative fixture data (multiple categories, mixed months, zero values)

- [x] Task 2: Chart filter hook (`frontend/src/hooks/useChartFilters.ts`)
  - [x] State: `selectedCategories: string[]`, `selectedPeriods: string[]`
  - [x] `toggleCategory(name: string)` — adds if not present, removes if present
  - [x] `togglePeriod(period: string)` — adds if not present, removes if present
  - [x] `resetFilters()` — clears both arrays
  - [x] `hasActiveFilters: boolean` computed from state
  - [x] `applyFilters(records: LedgerEntryRecord[])` — filters by selectedCategories (OR) AND selectedPeriods (OR), returns filtered records
  - [x] Unit tests: toggle adds/removes, reset clears, applyFilters AND logic, applyFilters with empty selection returns all records

- [x] Task 3: Composition pie chart (`frontend/src/components/charts/CompositionPieChart.tsx`)
  - [x] Recharts `PieChart` + `Pie` + `Tooltip` + `Cell` + `Legend`
  - [x] Props: `title: string`, `data: {name: string, value: number}[]`, `selectedItems: string[]`, `onSliceClick: (name: string) => void`
  - [x] Selected slices: opacity highlight + white stroke (outerRadius not a valid Cell prop — used opacity instead)
  - [x] Tooltip: category name + `toLocaleString('es-CL')` amount
  - [x] Empty state: "Sin datos" centered if data is empty

- [x] Task 4: Timeline bar chart (`frontend/src/components/charts/TimelineBarChart.tsx`)
  - [x] Recharts `BarChart` + two `Bar` components (income green `#22c55e`, expenses red `#ef4444`)
  - [x] Props: `data: {period: string, label: string, income: number, expenses: number}[]`, `selectedPeriods: string[]`, `onBarClick: (period: string) => void`
  - [x] Selected period bars: opacity 1.0, unselected: opacity 0.35 when any period selected
  - [x] Tooltip: period label + income + expenses formatted
  - [x] Y-axis: `tickFormatter` using `toLocaleString('es-CL')`
  - [x] Click handler fires `onBarClick(period)` for the clicked bar group

- [x] Task 5: Drill-down table (`frontend/src/components/charts/IncomeExpensesDrilldown.tsx`)
  - [x] Props: `records: LedgerEntryRecord[]`, `type: 'income' | 'expenses'`, `title: string`
  - [x] Renders grouped sections from `groupByCategoria1(records, type)`
  - [x] Categoria1 section header row: expandable (chevron icon), name, subtotal formatted
  - [x] Account row: account number (mono font), account name, total formatted; click expands transactions
  - [x] Transaction detail: uses existing `useLedger(accountNumber)` hook for lazy fetch on expand
  - [x] Transaction row: date DD/MM/YYYY, description, amount (green=income, red=expense)
  - [x] Loading skeleton while transaction detail fetches

- [x] Task 6: Assemble `IncomeExpensesPage.tsx` (replaces existing file)
  - [x] Fetch all ledger entries via `useLedger()` (no accountNumber — full dataset)
  - [x] Apply chart filters via `useChartFilters.applyFilters(records)` before passing to drill-down
  - [x] Summary cards row (3 cards) — computed from raw unfiltered records
  - [x] Charts row: `CompositionPieChart` (gastos) + `CompositionPieChart` (ingresos) + `TimelineBarChart`
  - [x] Filter chips row + "Resetear filtros" button (conditional on `hasActiveFilters`)
  - [x] `IncomeExpensesDrilldown` for income (filtered records) + for expenses (filtered records)
  - [x] Loading skeleton (3 skeleton rows), empty state, error state

- [x] Task 7: Cleanup
  - [x] Old inline helpers (AccountDrilldown, BreakdownTable, buildBreakdown) removed — replaced by dedicated modules
  - [x] Sidebar routing unchanged — IncomeExpensesPage export name preserved
  - [x] `npm run build` — no TypeScript errors (43 tests pass)

## Dev Agent Record

### Implementation Notes

- Installed Vitest + @testing-library/react — project had no test framework. Required to fulfill story AC tests.
- `vite.config.ts` now imports `defineConfig` from `vitest/config` (not `vite`) to enable `test` block without TS error.
- `tsconfig.node.json` — added `vitest/globals` to types array.
- `Cell.outerRadius` not a valid Recharts prop — selected pie slices use `opacity + stroke` for visual highlight instead.
- `PieLabelRenderProps` all fields are optional in Recharts types — label renderer uses Number() coercion with defaults.
- Summary cards always computed from unfiltered records; chart filters only affect the drill-down table.
- Pie charts show both gastos and ingresos with same `selectedCategories` filter — clicking a category in either pie filters the drill-down for that category regardless of type.

### Tests

- 29 tests in `ledgerAnalytics.test.ts` covering `getLedgerCategory`, `groupByCategoria1`, `buildPieData`, `buildTimeline`, `periodLabel`
- 14 tests in `useChartFilters.test.ts` covering toggle, reset, and `applyFilters` AND logic

## File List

- `frontend/src/utils/ledgerAnalytics.ts` — new
- `frontend/src/utils/ledgerAnalytics.test.ts` — new
- `frontend/src/hooks/useChartFilters.ts` — new
- `frontend/src/hooks/useChartFilters.test.ts` — new
- `frontend/src/components/charts/CompositionPieChart.tsx` — new
- `frontend/src/components/charts/TimelineBarChart.tsx` — new
- `frontend/src/components/charts/IncomeExpensesDrilldown.tsx` — new
- `frontend/src/pages/IncomeExpensesPage.tsx` — replaced (Story 3.3 version removed)
- `frontend/src/test/setup.ts` — new (Vitest setup)
- `frontend/vite.config.ts` — modified (added test block, vitest/config import)
- `frontend/tsconfig.node.json` — modified (added vitest/globals to types)
- `frontend/package.json` — modified (added test scripts + vitest devDependencies)
- `_bmad-output/implementation-artifacts/deferred-work.md` — updated (Story 3.5 deferral documented)
