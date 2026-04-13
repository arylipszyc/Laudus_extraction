import type { LedgerEntryRecord } from '@/types'

// ── Classification ────────────────────────────────────────────────────────────

/**
 * Classify a ledger entry as income, expenses, or other.
 * Prefers Categoria1 from PlanCuentas; falls back to account number prefix.
 */
export function getLedgerCategory(
  accountNumber: unknown,
  categoria1: string = ''
): 'income' | 'expenses' | 'other' {
  if (categoria1) {
    const cat = categoria1.toLowerCase()
    if (cat.includes('ingreso') || cat.includes('revenue')) return 'income'
    if (cat.includes('gasto') || cat.includes('costo') || cat.includes('expense')) return 'expenses'
  }
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

export interface Categoria1Group {
  categoria1: string
  accounts: AccountSummary[]
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

/**
 * Group records by Categoria1, then by account, for the given type.
 * Returns groups sorted by subtotal descending.
 */
export function groupByCategoria1(
  records: LedgerEntryRecord[],
  type: 'income' | 'expenses'
): Categoria1Group[] {
  // cat1 → accountNumber → { accountName, total, currency }
  const catMap = new Map<string, Map<string, { accountName: string; total: number; currency: string }>>()

  for (const r of records) {
    if (getLedgerCategory(r.accountnumber, r.Categoria1) !== type) continue

    const amount = type === 'income'
      ? r.credit - r.debit
      : r.debit - r.credit

    const cat1 = r.Categoria1 || 'Sin categoría'
    if (!catMap.has(cat1)) catMap.set(cat1, new Map())
    const acctMap = catMap.get(cat1)!

    if (acctMap.has(r.accountnumber)) {
      acctMap.get(r.accountnumber)!.total += amount
    } else {
      acctMap.set(r.accountnumber, {
        accountName: r.accountName || String(r.accountnumber),
        total: amount,
        currency: r.currencycode || 'CLP',
      })
    }
  }

  const groups: Categoria1Group[] = []
  for (const [cat1, acctMap] of catMap.entries()) {
    const accounts: AccountSummary[] = Array.from(acctMap.entries())
      .map(([accountNumber, { accountName, total, currency }]) => ({
        accountNumber,
        accountName,
        total,
        currency,
      }))
      .sort((a, b) => b.total - a.total)

    const subtotal = accounts.reduce((s, a) => s + a.total, 0)
    groups.push({ categoria1: cat1, accounts, subtotal })
  }

  return groups.sort((a, b) => b.subtotal - a.subtotal)
}

/**
 * Build pie chart data from records for the given type.
 * Returns slices sorted by value descending, zero-total slices excluded.
 */
export function buildPieData(
  records: LedgerEntryRecord[],
  type: 'income' | 'expenses'
): PieSlice[] {
  const totals = new Map<string, number>()

  for (const r of records) {
    if (getLedgerCategory(r.accountnumber, r.Categoria1) !== type) continue

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
 * Build timeline data grouped by year-month.
 * Returns periods sorted chronologically.
 */
export function buildTimeline(records: LedgerEntryRecord[]): TimelinePeriod[] {
  const periodMap = new Map<string, { income: number; expenses: number }>()

  for (const r of records) {
    // date is ISO 8601: "2026-03-15" — extract "2026-03"
    const period = r.date?.slice(0, 7)
    if (!period) continue

    const type = getLedgerCategory(r.accountnumber, r.Categoria1)
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
