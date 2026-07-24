# Story 3.2: Filtros de Entidad y Fecha

Status: review

## Story

As an owner or contador,
I want to filter financial data by entity and date range from any dashboard view,
So that I can focus on the specific entity and period I need without navigating away.

## Acceptance Criteria

1. `EntityFilter` component is rendered in the dashboard layout; selecting an entity (EAG, Jocelyn, Jeannette, Johanna, Jael) updates all dashboard views; selected entity is stored in React Context and persists across dashboard page navigation (FR12)
2. `DateRangeFilter` component is rendered in the dashboard layout; selecting a preset (month, quarter, year) or a custom date range updates all dashboard views; selected date range is stored in React Context and persists across dashboard page navigation (FR13)
3. When either filter changes, React Query automatically re-fetches data for all active dashboard views; update completes in under 2 seconds without full page reload (NFR2)
4. During data fetch after a filter change, a loading skeleton or spinner is shown in the affected panels; filter controls remain interactive during loading

## Architecture Context

### What This Story Builds

This is a **pure frontend story**. The backend API (Story 3.1) is already `done`. This story wires up:
- A global `FilterContext` (entity + date range state) that persists across dashboard navigation
- `EntityFilter` and `DateRangeFilter` UI components in the dashboard filter bar
- `services/dashboard.ts` — API fetch functions for balance-sheets and ledger-entries
- `hooks/useBalanceSheet.ts` and `hooks/useLedger.ts` — React Query hooks consuming filter state
- TypeScript types for dashboard API responses

Stories 3.3–3.5 **depend on** the hooks and context this story creates — build them right.

### Existing Frontend Structure (READ THESE FILES BEFORE CODING)

| File | What to know |
|---|---|
| `frontend/src/main.tsx` | `QueryClientProvider` wraps app — React Query already set up, `staleTime: 60_000` |
| `frontend/src/App.tsx` | Routes: `/dashboard/balance-sheet`, `/income-expenses`, `/income-statement`, `/equity-variation` — all render `DashboardPlaceholder` (stub to remain until 3.3) |
| `frontend/src/components/layout/DashboardLayout.tsx` | `Sidebar + Header + <Outlet />` — filter bar goes HERE between Header and main |
| `frontend/src/services/api.ts` | `api.baseUrl = VITE_API_URL ?? 'http://localhost:8000'` — always use this, never hardcode |
| `frontend/src/services/auth.ts` | Auth pattern: `fetch(url, { credentials: 'include' })` — replicate exactly |
| `frontend/src/hooks/useAuth.ts` | React Query hook pattern — replicate for dashboard hooks |
| `frontend/src/types/index.ts` | Add new types HERE — do not create a separate file |
| `frontend/src/hooks/index.ts` | Barrel file — add exports here for new hooks |
| `frontend/src/components/ui/skeleton.tsx` | Already installed — use for loading states |

### API Endpoints (Story 3.1 — Already Implemented)

```
GET /api/v1/balance-sheets?entity=EAG&date_from=2026-01-01&date_to=2026-12-31
→ { "data": [BalanceSheetRecord], "meta": { "last_sync": "2026-03-31" | null } }

GET /api/v1/ledger-entries?entity=EAG&date_from=2026-01-01&date_to=2026-12-31&account_number=111005
→ { "data": [LedgerEntryRecord], "meta": { "last_sync": "2026-03-15" | null } }
```

- Auth via httpOnly cookie — automatic when `credentials: 'include'`; no manual token handling
- Both `owner` and `contador` can read all dashboard endpoints
- `date_from` and `date_to` are optional — omit both to get all records for entity
- `account_number` is optional on ledger — for drill-down (Story 3.5)

**CRITICAL — Ledger JSON field names are non-snake_case (backend not yet patched):**

Balance sheet fields: `account_id`, `account_number`, `account_name`, `debit`, `credit`, `debit_balance`, `credit_balance`, `query_date`, `is_latest`

Ledger fields (use as-is — do NOT rename or alias): `journalentryid`, `journalentrynumber`, `date`, `accountnumber`, `lineid`, `description`, `debit`, `credit`, `currencycode`, `paritytomaincurrency`, `periodo`

### Filter State Design

```typescript
// Scoped to dashboard section — FilterProvider wraps DashboardLayout content
interface FilterContextValue {
  entity: Entity          // 'EAG' | 'Jocelyn' | 'Jeannette' | 'Johanna' | 'Jael'
  setEntity: (e: Entity) => void
  dateFrom: string        // ISO 'YYYY-MM-DD'
  dateTo: string          // ISO 'YYYY-MM-DD'
  datePreset: DatePreset  // 'month' | 'quarter' | 'year' | 'custom'
  setPreset: (preset: Exclude<DatePreset, 'custom'>) => void
  setCustomRange: (from: string, to: string) => void
}
```

**Default on mount:** `entity='EAG'`, `datePreset='year'`, `dateFrom='2026-01-01'`, `dateTo=today`

**Do NOT put `FilterProvider` in `App.tsx`** — it belongs inside `DashboardLayout` so it's scoped to the dashboard section only.

### React Query Key Pattern (CRITICAL for AC3)

Query key MUST include filter params — when context state changes, key changes, React Query auto-refetches. No manual `invalidateQueries` needed.

```typescript
queryKey: ['balance-sheets', entity, dateFrom, dateTo]
queryKey: ['ledger-entries', entity, dateFrom, dateTo, accountNumber ?? '']
```

## Files To Create

```
frontend/src/contexts/
    FilterContext.tsx          (FilterProvider, useFilters, ENTITIES, getDateRange)
frontend/src/components/filters/
    EntityFilter.tsx
    DateRangeFilter.tsx
frontend/src/services/
    dashboard.ts               (getBalanceSheets, getLedgerEntries)
frontend/src/hooks/
    useBalanceSheet.ts
    useLedger.ts
```

## Files To Modify

```
frontend/src/components/layout/DashboardLayout.tsx   — FilterProvider + filter bar
frontend/src/types/index.ts                          — dashboard types
frontend/src/hooks/index.ts                          — export new hooks
```

## Dev Notes

### `FilterContext.tsx` — Full Implementation

```typescript
import { createContext, useContext, useState, type ReactNode } from 'react'

export type Entity = 'EAG' | 'Jocelyn' | 'Jeannette' | 'Johanna' | 'Jael'
export type DatePreset = 'month' | 'quarter' | 'year' | 'custom'

export const ENTITIES: Entity[] = ['EAG', 'Jocelyn', 'Jeannette', 'Johanna', 'Jael']

function getDateRange(preset: Exclude<DatePreset, 'custom'>): { dateFrom: string; dateTo: string } {
  const today = new Date()
  const yyyy = today.getFullYear()
  const mm = today.getMonth() // 0-indexed
  const todayStr = today.toISOString().slice(0, 10)
  switch (preset) {
    case 'month':
      return { dateFrom: `${yyyy}-${String(mm + 1).padStart(2, '0')}-01`, dateTo: todayStr }
    case 'quarter': {
      const qStart = Math.floor(mm / 3) * 3
      return { dateFrom: `${yyyy}-${String(qStart + 1).padStart(2, '0')}-01`, dateTo: todayStr }
    }
    case 'year':
      return { dateFrom: `${yyyy}-01-01`, dateTo: todayStr }
  }
}

interface FilterContextValue {
  entity: Entity
  setEntity: (e: Entity) => void
  dateFrom: string
  dateTo: string
  datePreset: DatePreset
  setPreset: (preset: Exclude<DatePreset, 'custom'>) => void
  setCustomRange: (from: string, to: string) => void
}

const FilterContext = createContext<FilterContextValue | null>(null)

const initialRange = getDateRange('year')

export function FilterProvider({ children }: { children: ReactNode }) {
  const [entity, setEntity] = useState<Entity>('EAG')
  const [datePreset, setDatePreset] = useState<DatePreset>('year')
  const [dateFrom, setDateFrom] = useState(initialRange.dateFrom)
  const [dateTo, setDateTo] = useState(initialRange.dateTo)

  function setPreset(preset: Exclude<DatePreset, 'custom'>) {
    const range = getDateRange(preset)
    setDatePreset(preset)
    setDateFrom(range.dateFrom)
    setDateTo(range.dateTo)
  }

  function setCustomRange(from: string, to: string) {
    setDatePreset('custom')
    setDateFrom(from)
    setDateTo(to)
  }

  return (
    <FilterContext.Provider value={{ entity, setEntity, dateFrom, dateTo, datePreset, setPreset, setCustomRange }}>
      {children}
    </FilterContext.Provider>
  )
}

export function useFilters(): FilterContextValue {
  const ctx = useContext(FilterContext)
  if (!ctx) throw new Error('useFilters must be inside FilterProvider')
  return ctx
}
```

### TypeScript Types — Add to `frontend/src/types/index.ts`

```typescript
// ── Dashboard types ──────────────────────────────────────────────────────────

export type Entity = 'EAG' | 'Jocelyn' | 'Jeannette' | 'Johanna' | 'Jael'
export type DatePreset = 'month' | 'quarter' | 'year' | 'custom'

export interface DashboardMeta {
  last_sync: string | null
}

export interface BalanceSheetRecord {
  account_id: number | string
  account_number: string
  account_name: string
  debit: number
  credit: number
  debit_balance: number
  credit_balance: number
  query_date: string
  is_latest: string
}

export interface BalanceSheetResponse {
  data: BalanceSheetRecord[]
  meta: DashboardMeta
}

// Ledger field names match the backend's actual JSON keys — do NOT rename
export interface LedgerEntryRecord {
  journalentryid: number | string
  journalentrynumber: number | string
  date: string
  accountnumber: string
  lineid: number | string
  description: string
  debit: number
  credit: number
  currencycode: string
  paritytomaincurrency: number
  periodo: string
}

export interface LedgerEntriesResponse {
  data: LedgerEntryRecord[]
  meta: DashboardMeta
}
```

### `services/dashboard.ts` — Full Implementation

```typescript
import { api } from '@/services/api'
import type { BalanceSheetResponse, LedgerEntriesResponse } from '@/types'

interface DashboardParams {
  entity: string
  dateFrom?: string
  dateTo?: string
}

interface LedgerParams extends DashboardParams {
  accountNumber?: string
}

export async function getBalanceSheets(params: DashboardParams): Promise<BalanceSheetResponse> {
  const url = new URL(`${api.baseUrl}/api/v1/balance-sheets`)
  url.searchParams.set('entity', params.entity)
  if (params.dateFrom) url.searchParams.set('date_from', params.dateFrom)
  if (params.dateTo) url.searchParams.set('date_to', params.dateTo)
  const res = await fetch(url.toString(), { credentials: 'include' })
  if (!res.ok) throw new Error(`balance-sheets: ${res.status}`)
  return res.json() as Promise<BalanceSheetResponse>
}

export async function getLedgerEntries(params: LedgerParams): Promise<LedgerEntriesResponse> {
  const url = new URL(`${api.baseUrl}/api/v1/ledger-entries`)
  url.searchParams.set('entity', params.entity)
  if (params.dateFrom) url.searchParams.set('date_from', params.dateFrom)
  if (params.dateTo) url.searchParams.set('date_to', params.dateTo)
  if (params.accountNumber) url.searchParams.set('account_number', params.accountNumber)
  const res = await fetch(url.toString(), { credentials: 'include' })
  if (!res.ok) throw new Error(`ledger-entries: ${res.status}`)
  return res.json() as Promise<LedgerEntriesResponse>
}
```

### React Query Hooks

```typescript
// hooks/useBalanceSheet.ts
import { useQuery } from '@tanstack/react-query'
import { getBalanceSheets } from '@/services/dashboard'
import { useFilters } from '@/contexts/FilterContext'
import type { BalanceSheetResponse } from '@/types'

export function useBalanceSheet() {
  const { entity, dateFrom, dateTo } = useFilters()
  return useQuery<BalanceSheetResponse>({
    queryKey: ['balance-sheets', entity, dateFrom, dateTo],
    queryFn: () => getBalanceSheets({ entity, dateFrom, dateTo }),
    staleTime: 60 * 1000,
  })
}
```

```typescript
// hooks/useLedger.ts
import { useQuery } from '@tanstack/react-query'
import { getLedgerEntries } from '@/services/dashboard'
import { useFilters } from '@/contexts/FilterContext'
import type { LedgerEntriesResponse } from '@/types'

export function useLedger(accountNumber?: string) {
  const { entity, dateFrom, dateTo } = useFilters()
  return useQuery<LedgerEntriesResponse>({
    queryKey: ['ledger-entries', entity, dateFrom, dateTo, accountNumber ?? ''],
    queryFn: () => getLedgerEntries({ entity, dateFrom, dateTo, accountNumber }),
    staleTime: 60 * 1000,
  })
}
```

`useLedger` accepts optional `accountNumber` — Stories 3.3/3.4 call it without it; Story 3.5 drill-down passes it.

### `DashboardLayout.tsx` — Full Replacement

```typescript
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { FilterProvider } from '@/contexts/FilterContext'
import { EntityFilter } from '@/components/filters/EntityFilter'
import { DateRangeFilter } from '@/components/filters/DateRangeFilter'

export function DashboardLayout() {
  return (
    <FilterProvider>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <div className="flex flex-col flex-1 overflow-hidden">
          <Header />
          <div className="flex items-center gap-4 px-6 py-3 border-b bg-card flex-shrink-0">
            <EntityFilter />
            <DateRangeFilter />
          </div>
          <main className="flex-1 overflow-auto p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </FilterProvider>
  )
}
```

### `EntityFilter.tsx` — Full Implementation

```typescript
import { ENTITIES, useFilters, type Entity } from '@/contexts/FilterContext'

export function EntityFilter() {
  const { entity, setEntity } = useFilters()
  return (
    <div className="flex items-center gap-2">
      <label className="text-sm font-medium text-muted-foreground whitespace-nowrap">Entidad:</label>
      <select
        value={entity}
        onChange={(e) => setEntity(e.target.value as Entity)}
        className="text-sm border rounded-md px-2 py-1 bg-background focus:outline-none focus:ring-1 focus:ring-primary"
      >
        {ENTITIES.map((e) => (
          <option key={e} value={e}>{e}</option>
        ))}
      </select>
    </div>
  )
}
```

### `DateRangeFilter.tsx` — Full Implementation

```typescript
import { useFilters, type DatePreset } from '@/contexts/FilterContext'

const PRESETS: { label: string; value: Exclude<DatePreset, 'custom'> }[] = [
  { label: 'Mes', value: 'month' },
  { label: 'Trimestre', value: 'quarter' },
  { label: 'Año', value: 'year' },
]

export function DateRangeFilter() {
  const { datePreset, dateFrom, dateTo, setPreset, setCustomRange } = useFilters()

  return (
    <div className="flex items-center gap-2">
      <label className="text-sm font-medium text-muted-foreground whitespace-nowrap">Período:</label>
      <div className="flex gap-1">
        {PRESETS.map(({ label, value }) => (
          <button
            key={value}
            type="button"
            onClick={() => setPreset(value)}
            className={`text-sm px-3 py-1 rounded-md border transition-colors ${
              datePreset === value
                ? 'bg-primary text-primary-foreground border-primary'
                : 'bg-background text-muted-foreground border-input hover:bg-accent hover:text-accent-foreground'
            }`}
          >
            {label}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setCustomRange(dateFrom, dateTo)}
          className={`text-sm px-3 py-1 rounded-md border transition-colors ${
            datePreset === 'custom'
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-background text-muted-foreground border-input hover:bg-accent hover:text-accent-foreground'
          }`}
        >
          Personalizado
        </button>
      </div>
      {datePreset === 'custom' && (
        <div className="flex items-center gap-1">
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setCustomRange(e.target.value, dateTo)}
            className="text-sm border rounded-md px-2 py-1 bg-background focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <span className="text-muted-foreground text-sm">—</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setCustomRange(dateFrom, e.target.value)}
            className="text-sm border rounded-md px-2 py-1 bg-background focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      )}
    </div>
  )
}
```

### Loading Skeleton Pattern (for Stories 3.3–3.5)

Dashboard views that use `useBalanceSheet()` or `useLedger()` must handle loading:

```typescript
import { Skeleton } from '@/components/ui/skeleton'

function MyDashboardView() {
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

  // render data...
}
```

Filter bar stays interactive during loading because `FilterProvider` is a parent of the loading component — state changes in context are independent of the child's loading state.

### `hooks/index.ts` — Update

```typescript
// React Query hooks — export from here as they are created
export { useSyncStatus } from './useSyncStatus'
export { useBalanceSheet } from './useBalanceSheet'
export { useLedger } from './useLedger'
```

### Scope Boundary — What This Story Does NOT Build

- Dashboard page views (BalanceSheetPage, IncomeExpensesPage, etc.) — those are Stories 3.3 and 3.4
- `DashboardPlaceholder.tsx` remains unchanged — routes still render it
- No Recharts charts — Story 3.3+
- No drill-down panel — Story 3.5

The dev agent's job for this story ends when:
1. Filter bar is visible on all dashboard routes
2. `useBalanceSheet()` and `useLedger()` hooks are importable and callable
3. Changing entity or date updates the query key (verify in React Query Devtools)

## Anti-Patterns to Avoid

- **DO NOT** use `useEffect` + raw `fetch` for data loading — always React Query
- **DO NOT** put `FilterProvider` in `App.tsx` — it belongs inside `DashboardLayout`
- **DO NOT** call `queryClient.invalidateQueries` when filters change — changing the query key auto-triggers refetch
- **DO NOT** store filter state in React Query cache — it's UI state, belongs in React Context
- **DO NOT** rename ledger JSON fields — keep `journalentryid`, `accountnumber`, etc. exactly as the backend returns them
- **DO NOT** hardcode `http://localhost:8000` — always use `api.baseUrl` from `@/services/api`
- **DO NOT** forget `credentials: 'include'` on every `fetch` call — auth uses httpOnly cookies
- **DO NOT** add a `type="button"` omission on filter buttons — they're inside layout divs, not forms, but add it defensively

## Dependencies

All already in `frontend/package.json` — **no new packages needed**:
- React 19.2 — `createContext`, `useContext`, `useState`, `ReactNode`
- `@tanstack/react-query` ^5.97 — `useQuery` (v5 API)
- `react-router-dom` ^7.14 — `Outlet`
- Tailwind CSS 3.4, lucide-react, shadcn/ui components

## Testing

No frontend test framework is configured (`package.json` has no Vitest/Jest). **Do not add tests.**

Manual verification checklist:
- [ ] Filter bar visible on all 4 dashboard sub-routes without resetting on navigation
- [ ] Selecting entity changes `queryKey` (check React Query Devtools)
- [ ] Mes/Trimestre/Año buttons update dateFrom/dateTo correctly
- [ ] Custom date inputs appear on "Personalizado" click; changing them updates filter state
- [ ] `useBalanceSheet()` and `useLedger()` importable and return `{ data, isLoading, isError }` without crashes
- [ ] `DashboardPlaceholder` still renders on all 4 routes (no regression)

## Dev Agent Record

### Agent Model Used
claude-sonnet-4-6 (Amelia)

### Completion Notes
- `FilterContext.tsx`: FilterProvider con entity (default EAG) y datePreset (default year). `getDateRange()` calcula dateFrom/dateTo para presets; custom mode preserva el rango anterior como punto de partida para los inputs.
- `services/dashboard.ts`: `getBalanceSheets` y `getLedgerEntries` usan `URL` + `searchParams` para construir la query string; ambas con `credentials: 'include'` para auth por cookie.
- `useBalanceSheet` y `useLedger`: query keys incluyen [entity, dateFrom, dateTo] — React Query re-fetch automático al cambiar filtros. `useLedger` acepta `accountNumber` opcional para drill-down de Story 3.5.
- `DashboardLayout.tsx`: `FilterProvider` envuelve todo el layout; filter bar (`EntityFilter` + `DateRangeFilter`) entre `<Header />` y `<main>` con `flex-shrink-0`.
- TypeScript check: `tsc --noEmit` pasa sin errores.
- `DashboardPlaceholder` sin cambios — todas las rutas siguen renderizándola correctamente.

### Debug Log
No issues. TypeScript limpio en primera pasada.

## Tasks / Subtasks

- [x] Add dashboard TypeScript types to `frontend/src/types/index.ts` (Entity, DatePreset, DashboardMeta, BalanceSheetRecord, BalanceSheetResponse, LedgerEntryRecord, LedgerEntriesResponse)
- [x] Create `frontend/src/contexts/FilterContext.tsx` — FilterProvider, useFilters, ENTITIES, getDateRange
- [x] Create `frontend/src/services/dashboard.ts` — getBalanceSheets, getLedgerEntries
- [x] Create `frontend/src/hooks/useBalanceSheet.ts` — React Query hook with [entity, dateFrom, dateTo] key
- [x] Create `frontend/src/hooks/useLedger.ts` — React Query hook with optional accountNumber param
- [x] Create `frontend/src/components/filters/EntityFilter.tsx`
- [x] Create `frontend/src/components/filters/DateRangeFilter.tsx`
- [x] Modify `frontend/src/components/layout/DashboardLayout.tsx` — wrap with FilterProvider, add filter bar
- [x] Update `frontend/src/hooks/index.ts` — export useBalanceSheet and useLedger
- [x] Manual verification against checklist above

## Story File List

### Files To Create
- `frontend/src/contexts/FilterContext.tsx`
- `frontend/src/services/dashboard.ts`
- `frontend/src/hooks/useBalanceSheet.ts`
- `frontend/src/hooks/useLedger.ts`
- `frontend/src/components/filters/EntityFilter.tsx`
- `frontend/src/components/filters/DateRangeFilter.tsx`

### Files To Modify
- `frontend/src/components/layout/DashboardLayout.tsx`
- `frontend/src/types/index.ts`
- `frontend/src/hooks/index.ts`
