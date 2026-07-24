# Story 3.3: Dashboard Activos/Pasivos e Ingresos/Gastos

Status: review

## Story

As an owner,
I want to see my assets/liabilities and income/expenses dashboards for any entity and period,
So that I can understand the financial position and spending patterns of each entity at a glance.

## Acceptance Criteria

1. `BalanceSheetPage.tsx` displays balance sheet positions grouped by account category (assets vs. liabilities); key totals (total assets, total liabilities, net patrimony) are prominently displayed (FR14)
2. `IncomeExpensesPage.tsx` displays income and expense totals with breakdown by account category; a Recharts chart visualizes income vs. expense comparison for the period (FR15)
3. All monetary amounts formatted with `toLocaleString('es-CL')` — CLP and USD currencies preserved as stored in data
4. Dashboard renders correctly at 1280px minimum viewport width (desktop-only)
5. When no data exists for selected entity + period: empty state message "No hay datos para el período seleccionado" is shown; no broken charts or errors
6. Loading state: Skeleton components shown while data is fetching; filter controls remain interactive during loading
7. Routes `/dashboard/balance-sheet` and `/dashboard/income-expenses` now render the real page components instead of `DashboardPlaceholder`
8. Routes `/dashboard/income-statement` and `/dashboard/equity-variation` continue rendering `DashboardPlaceholder` (unchanged — Story 3.4)

## Architecture Context

### What This Story Builds

This is a **pure frontend story**. The backend API (Story 3.1) is `done` and the filter infrastructure (Story 3.2) is `review`. This story wires real page components to replace `DashboardPlaceholder` on two routes:

- `/dashboard/balance-sheet` → `BalanceSheetPage.tsx` — groups balance sheet records by assets vs. liabilities
- `/dashboard/income-expenses` → `IncomeExpensesPage.tsx` — shows income/expense totals + Recharts chart

### Prerequisite: Story 3.2 Infrastructure (READ BEFORE CODING)

Story 3.2 is in `review` but ALL files it created are implemented and functional. The developer MUST read these files before writing any code:

| File | What to know |
|---|---|
| `frontend/src/contexts/FilterContext.tsx` | `FilterProvider`, `useFilters()` — entity, dateFrom, dateTo state |
| `frontend/src/hooks/useBalanceSheet.ts` | React Query hook — `queryKey: ['balance-sheets', entity, dateFrom, dateTo]` |
| `frontend/src/hooks/useLedger.ts` | React Query hook — accepts optional `accountNumber` |
| `frontend/src/services/dashboard.ts` | `getBalanceSheets()`, `getLedgerEntries()` — already implemented |
| `frontend/src/types/index.ts` | `BalanceSheetRecord`, `LedgerEntryRecord`, `BalanceSheetResponse`, `LedgerEntriesResponse` — already defined |
| `frontend/src/components/ui/skeleton.tsx` | Already installed — use for loading states |
| `frontend/src/components/layout/DashboardLayout.tsx` | Already wraps with `FilterProvider` + filter bar |

### Key Types (from `frontend/src/types/index.ts`)

```typescript
interface BalanceSheetRecord {
  account_id: number | string
  account_number: string
  account_name: string
  debit: number
  credit: number
  debit_balance: number   // ← PRIMARY display field for balance sheet positions
  credit_balance: number  // ← Use when debit_balance = 0
  query_date: string
  is_latest: string
}

interface LedgerEntryRecord {
  // Non-snake_case field names — match backend exactly, do NOT rename
  journalentryid: number | string
  date: string
  accountnumber: string
  description: string
  debit: number
  credit: number
  currencycode: string   // 'CLP' or 'USD'
  paritytomaincurrency: number
  periodo: string
}
```

### API Endpoints (Story 3.1 — Already Implemented)

```
GET /api/v1/balance-sheets?entity=EAG&date_from=2026-01-01&date_to=2026-12-31
→ { "data": [BalanceSheetRecord], "meta": { "last_sync": "2026-03-31" | null } }

GET /api/v1/ledger-entries?entity=EAG&date_from=2026-01-01&date_to=2026-12-31
→ { "data": [LedgerEntryRecord], "meta": { "last_sync": "2026-03-15" | null } }
```

**NOTE:** Entity-specific sheet tabs are not yet populated by the sync pipeline (multi-entity sync is deferred). Until then, ALL entities return `{"data": [], "meta": {"last_sync": null}}`. The empty state component handles this — it is NOT a bug to display.

### Balance Sheet Grouping Logic

Balance sheet records do not have an explicit `category` field from the API. Group by `account_number` prefix:

| account_number prefix | Category |
|---|---|
| `1` | Activos (Assets) |
| `2` | Pasivos (Liabilities) |
| `3` | Patrimonio (Equity) |

```typescript
function getCategory(accountNumber: string): 'assets' | 'liabilities' | 'equity' | 'other' {
  if (accountNumber.startsWith('1')) return 'assets'
  if (accountNumber.startsWith('2')) return 'liabilities'
  if (accountNumber.startsWith('3')) return 'equity'
  return 'other'
}
```

**Net position per record:** Use `debit_balance - credit_balance`. For assets, a positive net is normal. For liabilities, a positive credit_balance is the liability amount.

**Key totals for BalanceSheetPage:**
- Total Activos = Σ(debit_balance - credit_balance) for accounts starting with `1`
- Total Pasivos = Σ(credit_balance - debit_balance) for accounts starting with `2`
- Patrimonio Neto = Total Activos - Total Pasivos

### Income/Expenses Grouping Logic

Ledger records do not have an explicit income/expense flag. Classify by `accountnumber` prefix:

| accountnumber prefix | Category |
|---|---|
| `4` | Ingresos (Income) |
| `5` | Gastos (Expenses) |
| `6` | Costos (Costs — treat as Expenses for display) |

```typescript
function getLedgerCategory(accountNumber: string): 'income' | 'expenses' | 'other' {
  if (accountNumber.startsWith('4')) return 'income'
  if (accountNumber.startsWith('5') || accountNumber.startsWith('6')) return 'expenses'
  return 'other'
}
```

**Income total:** Σ(credit - debit) for income accounts (credit entries are income)
**Expenses total:** Σ(debit - credit) for expense accounts (debit entries are expenses)

### Recharts Chart for IncomeExpensesPage

Use `BarChart` from Recharts (already in `package.json`: `"recharts": "^3.8.1"`). Show two bars: Ingresos vs. Gastos for the selected period.

```typescript
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

const chartData = [
  { name: 'Ingresos', value: totalIncome },
  { name: 'Gastos', value: totalExpenses },
]

// Inside component:
<ResponsiveContainer width="100%" height={300}>
  <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
    <XAxis dataKey="name" />
    <YAxis tickFormatter={(v) => v.toLocaleString('es-CL')} />
    <Tooltip formatter={(v: number) => v.toLocaleString('es-CL')} />
    <Bar dataKey="value">
      <Cell key="income" fill="#22c55e" />   {/* green for income */}
      <Cell key="expenses" fill="#ef4444" />  {/* red for expenses */}
    </Bar>
  </BarChart>
</ResponsiveContainer>
```

**CRITICAL:** `Cell` must be direct children of `Bar` with unique `key` — Recharts 3.x requires this for per-bar coloring.

### Currency Formatting

All amounts: `amount.toLocaleString('es-CL')`. This formats as Chilean locale (period thousands separator, comma decimal).

For multi-currency awareness: ledger records have `currencycode` (`'CLP'` or `'USD'`). For MVP display, show the `currencycode` next to amounts that are not CLP:

```typescript
function formatAmount(amount: number, currency: string = 'CLP'): string {
  const formatted = amount.toLocaleString('es-CL')
  return currency !== 'CLP' ? `${formatted} ${currency}` : formatted
}
```

Balance sheet records don't have `currencycode` — assume CLP.

### Loading Pattern (MANDATORY — from Story 3.2)

```typescript
import { Skeleton } from '@/components/ui/skeleton'

const { data, isLoading, isError } = useBalanceSheet()

if (isLoading) {
  return (
    <div className="space-y-3">
      <Skeleton className="h-8 w-full" />
      <Skeleton className="h-8 w-full" />
      <Skeleton className="h-8 w-3/4" />
    </div>
  )
}

if (isError) {
  return <p className="text-destructive text-sm">Error al cargar datos.</p>
}
```

### Empty State (MANDATORY)

```typescript
if (!data || data.data.length === 0) {
  return (
    <div className="flex items-center justify-center h-48 text-muted-foreground">
      <p>No hay datos para el período seleccionado</p>
    </div>
  )
}
```

### App.tsx Route Updates (AC7 + AC8)

Replace `DashboardPlaceholder` only for the two routes this story builds:

```typescript
// BEFORE (current App.tsx):
<Route path="balance-sheet" element={<DashboardPlaceholder />} />
<Route path="income-expenses" element={<DashboardPlaceholder />} />
<Route path="income-statement" element={<DashboardPlaceholder />} />
<Route path="equity-variation" element={<DashboardPlaceholder />} />

// AFTER:
<Route path="balance-sheet" element={<BalanceSheetPage />} />
<Route path="income-expenses" element={<IncomeExpensesPage />} />
<Route path="income-statement" element={<DashboardPlaceholder />} />  // unchanged
<Route path="equity-variation" element={<DashboardPlaceholder />} />   // unchanged
```

Add the two new imports at the top of `App.tsx`.

### Sidebar Navigation

Check `frontend/src/components/layout/Sidebar.tsx` — it likely has navigation links to dashboard sub-routes. The `balance-sheet` and `income-expenses` links should already be there; if not, add them. Keep the same nav pattern as existing links.

## Files To Create

```
frontend/src/pages/
    BalanceSheetPage.tsx      (FR14 — assets/liabilities dashboard)
    IncomeExpensesPage.tsx    (FR15 — income/expenses dashboard + Recharts chart)
```

## Files To Modify

```
frontend/src/App.tsx          — replace DashboardPlaceholder on 2 routes, add imports
```

## Anti-Patterns to Avoid

- **DO NOT** use `useEffect` + raw `fetch` for data loading — always use `useBalanceSheet()` / `useLedger()` hooks
- **DO NOT** call `useBalanceSheet()` or `useLedger()` outside a component inside `FilterProvider` tree — they depend on `useFilters()`; the component is already inside `DashboardLayout` which wraps with `FilterProvider`
- **DO NOT** hardcode entity names or date ranges — all filtering is handled by the filter context
- **DO NOT** rename ledger JSON field names (`journalentryid`, `accountnumber`, etc.) — they match the backend exactly
- **DO NOT** import `recharts` as a default import — use named imports: `import { BarChart, Bar, ... } from 'recharts'`
- **DO NOT** remove or modify `DashboardPlaceholder` — routes 3.4 still use it
- **DO NOT** put `formatAmount` or grouping helpers in a separate utility file — inline them in the page components (YAGNI — only 2 pages use them)
- **DO NOT** add a `components/charts/` directory — Recharts is used inline in `IncomeExpensesPage.tsx`; no abstraction needed for 1 chart
- **DO NOT** add Vitest/Jest tests — no frontend test framework is configured (`package.json` has none)
- **DO NOT** format monetary amounts as strings in the data layer — formatting is display-only in components

## Dependencies

All already in `frontend/package.json` — **no new packages needed**:
- `recharts` ^3.8.1 — `BarChart`, `Bar`, `XAxis`, `YAxis`, `Tooltip`, `ResponsiveContainer`, `Cell`
- `@tanstack/react-query` ^5.97 — via `useBalanceSheet()` and `useLedger()` hooks
- React 19.2 — standard hooks
- Tailwind CSS 3.4 + shadcn/ui — existing design system
- `frontend/src/components/ui/skeleton.tsx` — already installed

## Review Findings from Story 3.1 (Context — Do NOT Fix in This Story)

Story 3.1 has open Review Patches. These are NOT in scope for Story 3.3 but the developer must be aware:

- Ledger JSON fields are non-snake_case in the API response (`journalentryid`, `accountnumber`, etc.) — this is a known issue, accepted for MVP. The TypeScript types already match the actual response.
- `date_from`/`date_to` have no ISO format validation on the backend — not a concern for this story.

## Previous Story Intelligence

From **Story 3.2** (filters — in review):
- `FilterProvider` is in `DashboardLayout.tsx` — already wraps all dashboard routes
- `useBalanceSheet()` and `useLedger()` hooks are implemented and exported from `frontend/src/hooks/index.ts`
- `queryKey` includes `[entity, dateFrom, dateTo]` — React Query auto-refetches when filters change; no manual `invalidateQueries` needed
- `DashboardPlaceholder` is unchanged and still renders on `/dashboard/income-statement` and `/dashboard/equity-variation`

From **Story 3.1** (API — done):
- Entity-specific sheet tabs (`balance_sheet_eag`, `ledger_eag`, etc.) return `[]` until multi-entity sync is extended — empty state will always render in dev environment
- Both `owner` and `contador` roles can read dashboard endpoints (no RBAC restriction on reads)
- `meta.last_sync` is `null` when data is empty

## Git Intelligence

Recent commits:
- `efba9bd` — feat: agregar estructura completa de backend y frontend (Epics 1-3) — includes all 3.1 and 3.2 files

All dashboard infrastructure (hooks, context, services, types) was committed in `efba9bd`.

## Testing

No frontend test framework configured — **do not add tests**.

Manual verification checklist:
- [ ] `/dashboard/balance-sheet` renders `BalanceSheetPage` (not `DashboardPlaceholder`)
- [ ] `/dashboard/income-expenses` renders `IncomeExpensesPage` (not `DashboardPlaceholder`)
- [ ] `/dashboard/income-statement` and `/dashboard/equity-variation` still render `DashboardPlaceholder`
- [ ] Changing entity or date range triggers re-fetch (loading skeleton appears briefly)
- [ ] Empty state message "No hay datos para el período seleccionado" appears when data is empty
- [ ] `BalanceSheetPage` shows Activos / Pasivos sections with totals
- [ ] `IncomeExpensesPage` renders Recharts `BarChart` without errors
- [ ] No TypeScript errors: `tsc --noEmit` passes
- [ ] Filter bar remains interactive during loading

## Tasks / Subtasks

- [x] Read `frontend/src/hooks/useBalanceSheet.ts`, `useLedger.ts`, `contexts/FilterContext.tsx`, and `types/index.ts` before writing any code (verify what 3.2 built)
- [x] Read `frontend/src/components/layout/Sidebar.tsx` — check if nav links for balance-sheet and income-expenses already exist; add if missing
- [x] Create `frontend/src/pages/BalanceSheetPage.tsx` — grouping by account prefix, totals (assets, liabilities, net), loading + empty state, `toLocaleString('es-CL')` formatting (AC1, AC3, AC4, AC5, AC6)
- [x] Create `frontend/src/pages/IncomeExpensesPage.tsx` — income/expense totals by category, Recharts BarChart with green/red bars, loading + empty state (AC2, AC3, AC4, AC5, AC6)
- [x] Modify `frontend/src/App.tsx` — replace `DashboardPlaceholder` on `balance-sheet` and `income-expenses` routes; add imports for new pages (AC7, AC8)
- [x] Run `tsc --noEmit` — fix any TypeScript errors before marking complete
- [ ] Manual verification against checklist above

## Dev Agent Record

### Agent Model Used
claude-sonnet-4-6

### Completion Notes
- `BalanceSheetPage.tsx`: Agrupa registros por prefijo de `account_number` (1=Activos, 2=Pasivos, 3=Patrimonio). Totales: Total Activos = Σ(debit_balance - credit_balance) prefijo '1', Total Pasivos = Σ(credit_balance - debit_balance) prefijo '2', Patrimonio Neto = Activos - Pasivos. Tabla por sección con loading Skeleton y empty state.
- `IncomeExpensesPage.tsx`: Clasifica ledger records por prefijo de `accountnumber` (4=Ingresos, 5/6=Gastos). Recharts `BarChart` con `Cell` verde (#22c55e) para ingresos y rojo (#ef4444) para gastos. Tablas de detalle side-by-side. Respeta `currencycode` para multi-moneda.
- `App.tsx`: 2 imports agregados; rutas `balance-sheet` e `income-expenses` apuntan a nuevos componentes; `income-statement` y `equity-variation` sin cambios.
- Sidebar ya tenía los nav links — sin cambios.
- `tsc --noEmit`: sin errores en primera pasada.

### Debug Log
Sin issues. TypeScript limpio en primera pasada.

## Story File List

### Files To Create
- `frontend/src/pages/BalanceSheetPage.tsx`
- `frontend/src/pages/IncomeExpensesPage.tsx`

### Files To Modify
- `frontend/src/App.tsx`
