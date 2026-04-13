import { describe, it, expect } from 'vitest'
import {
  getLedgerCategory,
  filterByEntity,
  groupByCategoria1,
  buildPieData,
  buildTimeline,
  periodLabel,
} from './ledgerAnalytics'
import type { LedgerEntryRecord } from '@/types'

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeRecord(overrides: Partial<LedgerEntryRecord>): LedgerEntryRecord {
  return {
    journalentryid: 1,
    journalentrynumber: 1,
    date: '2026-01-15',
    accountnumber: '400001',
    lineid: 1,
    description: 'Test entry',
    debit: 0,
    credit: 0,
    currencycode: 'CLP',
    paritytomaincurrency: 1,
    periodo: '2026-01',
    accountName: 'Cuenta Test',
    Categoria1: 'Ingresos',
    Categoria2: '',
    Categoria3: '',
    ...overrides,
  }
}

const INCOME_RECORD = makeRecord({ credit: 100000, debit: 0, Categoria1: 'Ingresos', accountnumber: '400001', accountName: 'Ventas' })
const OTHER_RECORD = makeRecord({ debit: 10000, credit: 0, Categoria1: '', accountnumber: '100001', accountName: 'Caja' })

// ── filterByEntity ────────────────────────────────────────────────────────────

describe('filterByEntity', () => {
  const eag1 = makeRecord({ Categoria1: 'Gastos Operacionales', accountnumber: '500001' })
  const eag2 = makeRecord({ Categoria1: 'Ingresos', accountnumber: '400001' })
  const jocelyn = makeRecord({ Categoria1: 'Gastos Jocelyn', accountnumber: '500002' })
  const johanna = makeRecord({ Categoria1: 'Patrimonio Johanna', accountnumber: '300001' })
  const jael = makeRecord({ Categoria1: 'Ingresos Jael', accountnumber: '400002' })
  const ALL = [eag1, eag2, jocelyn, johanna, jael]

  it('EAG returns records with no daughter name in Categoria1', () => {
    const result = filterByEntity(ALL, 'EAG')
    expect(result).toHaveLength(2)
    expect(result).toContain(eag1)
    expect(result).toContain(eag2)
  })

  it('Jocelyn returns only records containing "Jocelyn" in Categoria1', () => {
    const result = filterByEntity(ALL, 'Jocelyn')
    expect(result).toHaveLength(1)
    expect(result[0]).toBe(jocelyn)
  })

  it('Johanna returns only records containing "Johanna" in Categoria1', () => {
    expect(filterByEntity(ALL, 'Johanna')).toEqual([johanna])
  })

  it('Jael returns only records containing "Jael" in Categoria1', () => {
    expect(filterByEntity(ALL, 'Jael')).toEqual([jael])
  })

  it('returns empty when no records match the entity', () => {
    expect(filterByEntity(ALL, 'Jeannette')).toHaveLength(0)
  })

  it('EAG excludes all daughter records', () => {
    const result = filterByEntity([jocelyn, johanna, jael], 'EAG')
    expect(result).toHaveLength(0)
  })
})

// ── getLedgerCategory ─────────────────────────────────────────────────────────

describe('getLedgerCategory', () => {
  it('returns income when Categoria1 contains "ingreso"', () => {
    expect(getLedgerCategory('400001', 'Ingresos')).toBe('income')
  })

  it('returns income when Categoria1 contains "revenue" (case insensitive)', () => {
    expect(getLedgerCategory('400001', 'Revenue')).toBe('income')
  })

  it('returns expenses when Categoria1 contains "gasto"', () => {
    expect(getLedgerCategory('500001', 'Gastos Operacionales')).toBe('expenses')
  })

  it('returns expenses when Categoria1 contains "costo"', () => {
    expect(getLedgerCategory('600001', 'Costo de Ventas')).toBe('expenses')
  })

  it('falls back to account prefix "4" → income when Categoria1 empty', () => {
    expect(getLedgerCategory('400001', '')).toBe('income')
  })

  it('falls back to account prefix "5" → expenses when Categoria1 empty', () => {
    expect(getLedgerCategory('500001', '')).toBe('expenses')
  })

  it('falls back to account prefix "6" → expenses when Categoria1 empty', () => {
    expect(getLedgerCategory('600001', '')).toBe('expenses')
  })

  it('returns other for unrecognized Categoria1 and unrecognized prefix', () => {
    expect(getLedgerCategory('100001', '')).toBe('other')
  })

  it('Categoria1 takes priority over account prefix', () => {
    // Account prefix says "income" (4xx) but Categoria1 says expenses
    expect(getLedgerCategory('400001', 'Gastos Administración')).toBe('expenses')
  })
})

// ── periodLabel ───────────────────────────────────────────────────────────────

describe('periodLabel', () => {
  it('formats "2026-01" → "Ene 2026"', () => {
    expect(periodLabel('2026-01')).toBe('Ene 2026')
  })

  it('formats "2026-12" → "Dic 2026"', () => {
    expect(periodLabel('2026-12')).toBe('Dic 2026')
  })

  it('formats "2025-06" → "Jun 2025"', () => {
    expect(periodLabel('2025-06')).toBe('Jun 2025')
  })
})

// ── groupByCategoria1 ─────────────────────────────────────────────────────────

// Helper: flatten all accounts from nested structure for easy assertion
function flatAccounts(groups: ReturnType<typeof groupByCategoria1>) {
  return groups.flatMap(g => g.cat2Groups.flatMap(g2 => g2.cat3Groups.flatMap(g3 => g3.accounts)))
}

describe('groupByCategoria1', () => {
  it('returns empty array when no records match type', () => {
    expect(groupByCategoria1([INCOME_RECORD], 'expenses')).toEqual([])
  })

  it('groups income records by Categoria1 (label + subtotal)', () => {
    const records = [
      makeRecord({ credit: 100000, debit: 0, Categoria1: 'Ingresos', accountnumber: '400001', accountName: 'Ventas' }),
      makeRecord({ credit: 50000, debit: 0, Categoria1: 'Ingresos', accountnumber: '400002', accountName: 'Servicios' }),
    ]
    const groups = groupByCategoria1(records, 'income')
    expect(groups).toHaveLength(1)
    expect(groups[0].label).toBe('Ingresos')
    expect(groups[0].subtotal).toBe(150000)
    expect(flatAccounts(groups)).toHaveLength(2)
  })

  it('groups records into multiple Categoria1 groups sorted by subtotal desc', () => {
    const records = [
      makeRecord({ debit: 80000, credit: 0, Categoria1: 'Gastos Operacionales', accountnumber: '500001', accountName: 'Arriendo' }),
      makeRecord({ debit: 30000, credit: 0, Categoria1: 'Gastos Administración', accountnumber: '500002', accountName: 'Oficina' }),
    ]
    const groups = groupByCategoria1(records, 'expenses')
    expect(groups).toHaveLength(2)
    expect(groups[0].label).toBe('Gastos Operacionales')
    expect(groups[1].label).toBe('Gastos Administración')
  })

  it('accumulates amounts for same account', () => {
    const records = [
      makeRecord({ credit: 60000, debit: 0, Categoria1: 'Ingresos', accountnumber: '400001', accountName: 'Ventas' }),
      makeRecord({ credit: 40000, debit: 0, Categoria1: 'Ingresos', accountnumber: '400001', accountName: 'Ventas', date: '2026-02-15' }),
    ]
    const groups = groupByCategoria1(records, 'income')
    expect(flatAccounts(groups)[0].total).toBe(100000)
  })

  it('excludes records classified as other', () => {
    expect(groupByCategoria1([OTHER_RECORD], 'income')).toHaveLength(0)
  })

  it('uses Categoria2 and Categoria3 for nested grouping', () => {
    const records = [
      makeRecord({ debit: 50000, credit: 0, Categoria1: 'Gastos', Categoria2: 'Operacionales', Categoria3: 'Arriendos', accountnumber: '500001', accountName: 'Arriendo Oficina' }),
      makeRecord({ debit: 30000, credit: 0, Categoria1: 'Gastos', Categoria2: 'Operacionales', Categoria3: 'Servicios', accountnumber: '500002', accountName: 'Luz' }),
    ]
    const groups = groupByCategoria1(records, 'expenses')
    expect(groups[0].label).toBe('Gastos')
    expect(groups[0].cat2Groups[0].label).toBe('Operacionales')
    expect(groups[0].cat2Groups[0].cat3Groups).toHaveLength(2)
  })

  it('uses "Sin categoría" / "Sin subcategoría" when fields empty', () => {
    const record = makeRecord({ debit: 50000, credit: 0, Categoria1: '', Categoria2: '', Categoria3: '', accountnumber: '500001' })
    const groups = groupByCategoria1([record], 'expenses')
    expect(groups[0].label).toBe('Sin categoría')
    expect(groups[0].cat2Groups[0].label).toBe('Sin subcategoría')
  })
})

// ── buildPieData ──────────────────────────────────────────────────────────────

describe('buildPieData', () => {
  it('returns empty array when no records match type', () => {
    expect(buildPieData([INCOME_RECORD], 'expenses')).toEqual([])
  })

  it('aggregates income by Categoria1 into pie slices', () => {
    const records = [
      makeRecord({ credit: 100000, debit: 0, Categoria1: 'Ingresos', accountnumber: '400001' }),
      makeRecord({ credit: 50000, debit: 0, Categoria1: 'Ingresos', accountnumber: '400002' }),
      makeRecord({ credit: 30000, debit: 0, Categoria1: 'Otros Ingresos', accountnumber: '400003' }),
    ]
    const slices = buildPieData(records, 'income')
    expect(slices).toHaveLength(2)
    expect(slices[0]).toEqual({ name: 'Ingresos', value: 150000 })
    expect(slices[1]).toEqual({ name: 'Otros Ingresos', value: 30000 })
  })

  it('excludes slices with zero or negative total', () => {
    const record = makeRecord({ credit: 0, debit: 50000, Categoria1: 'Ingresos', accountnumber: '400001' })
    const slices = buildPieData([record], 'income')
    expect(slices).toHaveLength(0)
  })

  it('sorts slices by value descending', () => {
    const records = [
      makeRecord({ debit: 20000, credit: 0, Categoria1: 'Gastos Pequeños', accountnumber: '500001' }),
      makeRecord({ debit: 80000, credit: 0, Categoria1: 'Gastos Grandes', accountnumber: '500002' }),
    ]
    const slices = buildPieData(records, 'expenses')
    expect(slices[0].name).toBe('Gastos Grandes')
  })
})

// ── buildTimeline ─────────────────────────────────────────────────────────────

describe('buildTimeline', () => {
  it('returns empty array for empty records', () => {
    expect(buildTimeline([])).toEqual([])
  })

  it('groups records by year-month from date field', () => {
    const records = [
      makeRecord({ credit: 100000, debit: 0, date: '2026-01-10', Categoria1: 'Ingresos' }),
      makeRecord({ debit: 50000, credit: 0, date: '2026-01-20', Categoria1: 'Gastos Operacionales' }),
      makeRecord({ credit: 80000, debit: 0, date: '2026-02-05', Categoria1: 'Ingresos' }),
    ]
    const timeline = buildTimeline(records)
    expect(timeline).toHaveLength(2)
    expect(timeline[0].period).toBe('2026-01')
    expect(timeline[0].income).toBe(100000)
    expect(timeline[0].expenses).toBe(50000)
    expect(timeline[1].period).toBe('2026-02')
    expect(timeline[1].income).toBe(80000)
    expect(timeline[1].expenses).toBe(0)
  })

  it('sorts periods chronologically', () => {
    const records = [
      makeRecord({ credit: 50000, debit: 0, date: '2026-03-01', Categoria1: 'Ingresos' }),
      makeRecord({ credit: 50000, debit: 0, date: '2026-01-01', Categoria1: 'Ingresos' }),
      makeRecord({ credit: 50000, debit: 0, date: '2026-02-01', Categoria1: 'Ingresos' }),
    ]
    const timeline = buildTimeline(records)
    expect(timeline.map(t => t.period)).toEqual(['2026-01', '2026-02', '2026-03'])
  })

  it('excludes "other" classified records', () => {
    const timeline = buildTimeline([OTHER_RECORD])
    expect(timeline).toHaveLength(0)
  })

  it('generates correct display labels', () => {
    const records = [makeRecord({ credit: 100000, debit: 0, date: '2026-03-15', Categoria1: 'Ingresos' })]
    const timeline = buildTimeline(records)
    expect(timeline[0].label).toBe('Mar 2026')
  })

  it('skips records without a date', () => {
    const record = makeRecord({ credit: 100000, debit: 0, date: '', Categoria1: 'Ingresos' })
    const timeline = buildTimeline([record])
    expect(timeline).toHaveLength(0)
  })
})
