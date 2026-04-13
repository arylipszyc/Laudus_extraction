import type { LedgerEntryRecord } from '@/types'

// ── Entity filtering ──────────────────────────────────────────────────────────

// All data lives in a single EAG sheet. Each daughter's records have her name
// embedded in Categoria1 (e.g. "Gastos Jocelyn", "Patrimonio Johanna").
// EAG records are those that don't match any daughter's name.
// Sheet stores Categoria1 in ALL-CAPS (e.g. "EGRESOS JOCELYN AVAYU DEUTSCH")
const DAUGHTERS = ['JOCELYN', 'JEANNETTE', 'JOHANNA', 'JAEL'] as const

export function filterByEntity(records: LedgerEntryRecord[], entity: string): LedgerEntryRecord[] {
  if (entity === 'EAG') {
    // EAG = records whose Categoria1 does NOT contain any daughter name
    return records.filter(r => !DAUGHTERS.some(d => (r.Categoria1 ?? '').toUpperCase().includes(d)))
  }
  // Daughter entity = records whose Categoria1 contains her name (case-insensitive)
  return records.filter(r => (r.Categoria1 ?? '').toUpperCase().includes(entity.toUpperCase()))
}

// ── Classification ────────────────────────────────────────────────────────────

/**
 * Classify a ledger entry as income, expenses, or other.
 * Prefers Categoria1 from PlanCuentas; falls back to account number prefix.
 */
export function getLedgerCategory(
  accountNumber: unknown,
  categoria1: string = '',
  categoria2: string = ''
): 'income' | 'expenses' | 'other' {
  // Check Cat1 and Cat2 — daughter records embed accounting type in Cat1
  // (e.g. "Egresos Jocelyn Avayu Deutsch"), EAG records use standard terms in Cat1
  for (const cat of [categoria1.toLowerCase(), categoria2.toLowerCase()]) {
    if (!cat) continue
    if (cat.includes('ingreso') || cat.includes('revenue')) return 'income'
    if (
      cat.includes('egreso') ||
      cat.includes('gasto') ||
      cat.includes('costo') ||
      cat.includes('expense')
    ) return 'expenses'
  }
  // Fallback: account number prefix
  const s = String(accountNumber ?? '')
  if (s.startsWith('4')) return 'income'
  if (s.startsWith('5') || s.startsWith('6')) return 'expenses'
  return 'other'
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AccountSummary {
  accountNumber: string
  accountName: string
  total: number
  currency: string
}

export interface Categoria3Group {
  label: string              // Categoria3 value (or 'Sin subcategoría')
  accounts: AccountSummary[]
  subtotal: number
}

export interface Categoria2Group {
  label: string              // Categoria2 value (or 'Sin subcategoría')
  cat3Groups: Categoria3Group[]
  subtotal: number
}

export interface Categoria1Group {
  label: string              // Categoria1 value
  cat2Groups: Categoria2Group[]
  subtotal: number
}

export interface PieSlice {
  name: string
  value: number
}

export interface TimelinePeriod {
  period: string   // "2026-01" for sorting/filtering
  label: string    // "Ene 2026" for display
  income: number
  expenses: number
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const MONTH_LABELS: string[] = [
  'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
  'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic',
]

export function periodLabel(yearMonth: string): string {
  const [year, month] = yearMonth.split('-')
  const idx = parseInt(month, 10) - 1
  const monthName = MONTH_LABELS[idx] ?? month
  return `${monthName} ${year}`
}

// ── Aggregations ──────────────────────────────────────────────────────────────

type AccountKey = string // accountnumber
type Cat3Key = string
type Cat2Key = string

interface AcctData { accountName: string; total: number; currency: string }
type Cat3Map = Map<AccountKey, AcctData>
type Cat2Map = Map<Cat3Key, Cat3Map>
type Cat1Map = Map<Cat2Key, Cat2Map>

/**
 * Group records by Categoria1 → Categoria2 → Categoria3 → account.
 * Returns groups sorted by subtotal descending at each level.
 */
export function groupByCategoria1(
  records: LedgerEntryRecord[],
  type: 'income' | 'expenses'
): Categoria1Group[] {
  // cat1 → cat2 → cat3 → accountnumber → AcctData
  const rootMap = new Map<string, Cat1Map>()

  for (const r of records) {
    if (getLedgerCategory(r.accountnumber, r.Categoria1, r.Categoria2) !== type) continue

    const amount = type === 'income'
      ? r.credit - r.debit
      : r.debit - r.credit

    const cat1 = r.Categoria1 || 'Sin categoría'
    const cat2 = r.Categoria2 || 'Sin subcategoría'
    const cat3 = r.Categoria3 || 'Sin subcategoría'

    if (!rootMap.has(cat1)) rootMap.set(cat1, new Map())
    const c1Map = rootMap.get(cat1)!

    if (!c1Map.has(cat2)) c1Map.set(cat2, new Map())
    const c2Map = c1Map.get(cat2)!

    if (!c2Map.has(cat3)) c2Map.set(cat3, new Map())
    const c3Map = c2Map.get(cat3)!

    if (c3Map.has(r.accountnumber)) {
      c3Map.get(r.accountnumber)!.total += amount
    } else {
      c3Map.set(r.accountnumber, {
        accountName: r.accountName || String(r.accountnumber),
        total: amount,
        currency: r.currencycode || 'CLP',
      })
    }
  }

  const result: Categoria1Group[] = []

  for (const [cat1Label, c1Map] of rootMap.entries()) {
    const cat2Groups: Categoria2Group[] = []

    for (const [cat2Label, c2Map] of c1Map.entries()) {
      const cat3Groups: Categoria3Group[] = []

      for (const [cat3Label, c3Map] of c2Map.entries()) {
        const accounts: AccountSummary[] = Array.from(c3Map.entries())
          .map(([accountNumber, { accountName, total, currency }]) => ({
            accountNumber,
            accountName,
            total,
            currency,
          }))
          .sort((a, b) => b.total - a.total)

        const subtotal = accounts.reduce((s, a) => s + a.total, 0)
        cat3Groups.push({ label: cat3Label, accounts, subtotal })
      }

      cat3Groups.sort((a, b) => b.subtotal - a.subtotal)
      const subtotal = cat3Groups.reduce((s, g) => s + g.subtotal, 0)
      cat2Groups.push({ label: cat2Label, cat3Groups, subtotal })
    }

    cat2Groups.sort((a, b) => b.subtotal - a.subtotal)
    const subtotal = cat2Groups.reduce((s, g) => s + g.subtotal, 0)
    result.push({ label: cat1Label, cat2Groups, subtotal })
  }

  return result.sort((a, b) => b.subtotal - a.subtotal)
}

/**
 * Build pie chart data grouped by Categoria1 for the given type.
 * Returns slices sorted by value descending, zero-total slices excluded.
 */
export function buildPieData(
  records: LedgerEntryRecord[],
  type: 'income' | 'expenses'
): PieSlice[] {
  const totals = new Map<string, number>()

  for (const r of records) {
    if (getLedgerCategory(r.accountnumber, r.Categoria1, r.Categoria2) !== type) continue

    const amount = type === 'income'
      ? r.credit - r.debit
      : r.debit - r.credit

    const cat1 = r.Categoria1 || 'Sin categoría'
    totals.set(cat1, (totals.get(cat1) ?? 0) + amount)
  }

  return Array.from(totals.entries())
    .filter(([, value]) => value > 0)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
}

/**
 * Build pie chart data grouped by Categoria2 for the given type.
 * Used in charts so the pie shows one level deeper than the summary cards.
 * Returns slices sorted by value descending, zero-total slices excluded.
 */
export function buildPieDataByCat2(
  records: LedgerEntryRecord[],
  type: 'income' | 'expenses'
): PieSlice[] {
  const totals = new Map<string, number>()

  for (const r of records) {
    if (getLedgerCategory(r.accountnumber, r.Categoria1, r.Categoria2) !== type) continue

    const amount = type === 'income'
      ? r.credit - r.debit
      : r.debit - r.credit

    const cat2 = r.Categoria2 || r.Categoria1 || 'Sin categoría'
    totals.set(cat2, (totals.get(cat2) ?? 0) + amount)
  }

  return Array.from(totals.entries())
    .filter(([, value]) => value > 0)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
}

/**
 * Build pie chart data grouped by Categoria3 for the given type and Cat2 value.
 * Used when user drills into a Cat2 slice in the pie chart.
 */
export function buildPieDataByCat3(
  records: LedgerEntryRecord[],
  type: 'income' | 'expenses',
  cat2: string
): PieSlice[] {
  const totals = new Map<string, number>()

  for (const r of records) {
    const recordCat2 = r.Categoria2 || r.Categoria1 || ''
    if (recordCat2 !== cat2) continue
    if (getLedgerCategory(r.accountnumber, r.Categoria1, r.Categoria2) !== type) continue

    const amount = type === 'income'
      ? r.credit - r.debit
      : r.debit - r.credit

    const cat3 = r.Categoria3 || 'Sin subcategoría'
    totals.set(cat3, (totals.get(cat3) ?? 0) + amount)
  }

  return Array.from(totals.entries())
    .filter(([, value]) => value > 0)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
}

/**
 * Build timeline data grouped by year-month.
 * Returns periods sorted chronologically.
 */
export function buildTimeline(records: LedgerEntryRecord[]): TimelinePeriod[] {
  const periodMap = new Map<string, { income: number; expenses: number }>()

  for (const r of records) {
    // date is ISO 8601: "2026-03-15" — extract "2026-03"
    const period = r.date?.slice(0, 7)
    if (!period) continue

    const type = getLedgerCategory(r.accountnumber, r.Categoria1, r.Categoria2)
    if (type === 'other') continue

    if (!periodMap.has(period)) periodMap.set(period, { income: 0, expenses: 0 })
    const entry = periodMap.get(period)!

    if (type === 'income') {
      entry.income += r.credit - r.debit
    } else {
      entry.expenses += r.debit - r.credit
    }
  }

  return Array.from(periodMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([period, { income, expenses }]) => ({
      period,
      label: periodLabel(period),
      income,
      expenses,
    }))
}
