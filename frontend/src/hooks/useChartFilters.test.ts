import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useChartFilters } from './useChartFilters'
import type { LedgerEntryRecord } from '@/types'

function makeRecord(overrides: Partial<LedgerEntryRecord>): LedgerEntryRecord {
  return {
    journalentryid: 1,
    journalentrynumber: 1,
    date: '2026-01-15',
    accountnumber: '400001',
    lineid: 1,
    description: 'Test',
    debit: 0,
    credit: 100000,
    currencycode: 'CLP',
    paritytomaincurrency: 1,
    periodo: '2026-01',
    accountName: 'Ventas',
    Categoria1: 'INGRESOS',
    Categoria2: 'Ingresos',
    Categoria3: '',
    ...overrides,
  }
}

const JAN_INCOME  = makeRecord({ date: '2026-01-10' })
const JAN_EXPENSE = makeRecord({ Categoria1: 'GASTOS - EGRESOS', Categoria2: 'Gastos Operacionales', date: '2026-01-20', debit: 50000, credit: 0 })
const FEB_INCOME  = makeRecord({ date: '2026-02-05' })
const FEB_OTHER   = makeRecord({ Categoria1: 'INGRESOS', Categoria2: 'Otros Ingresos', date: '2026-02-10' })

describe('useChartFilters', () => {
  it('initializes with empty filters and hasActiveFilters=false', () => {
    const { result } = renderHook(() => useChartFilters())
    expect(result.current.selectedPeriods).toEqual([])
    expect(result.current.hasActiveFilters).toBe(false)
  })

  it('togglePeriod adds a period and sets hasActiveFilters', () => {
    const { result } = renderHook(() => useChartFilters())
    act(() => result.current.togglePeriod('2026-01'))
    expect(result.current.selectedPeriods).toContain('2026-01')
    expect(result.current.hasActiveFilters).toBe(true)
  })

  it('togglePeriod removes an already-selected period', () => {
    const { result } = renderHook(() => useChartFilters())
    act(() => result.current.togglePeriod('2026-01'))
    act(() => result.current.togglePeriod('2026-01'))
    expect(result.current.selectedPeriods).toHaveLength(0)
  })

  it('togglePeriod accumulates multiple selections', () => {
    const { result } = renderHook(() => useChartFilters())
    act(() => result.current.togglePeriod('2026-01'))
    act(() => result.current.togglePeriod('2026-02'))
    expect(result.current.selectedPeriods).toHaveLength(2)
  })

  it('resetFilters clears selectedPeriods and hasActiveFilters', () => {
    const { result } = renderHook(() => useChartFilters())
    act(() => result.current.togglePeriod('2026-01'))
    act(() => result.current.resetFilters())
    expect(result.current.selectedPeriods).toHaveLength(0)
    expect(result.current.hasActiveFilters).toBe(false)
  })

  describe('applyFilters', () => {
    const ALL = [JAN_INCOME, JAN_EXPENSE, FEB_INCOME, FEB_OTHER]

    it('returns all records when no period selected', () => {
      const { result } = renderHook(() => useChartFilters())
      expect(result.current.applyFilters(ALL)).toHaveLength(4)
    })

    it('filters by selected period', () => {
      const { result } = renderHook(() => useChartFilters())
      act(() => result.current.togglePeriod('2026-01'))
      const filtered = result.current.applyFilters(ALL)
      expect(filtered).toHaveLength(2)
      expect(filtered.every(r => r.date.startsWith('2026-01'))).toBe(true)
    })

    it('multiple periods are OR logic', () => {
      const { result } = renderHook(() => useChartFilters())
      act(() => result.current.togglePeriod('2026-01'))
      act(() => result.current.togglePeriod('2026-02'))
      expect(result.current.applyFilters(ALL)).toHaveLength(4)
    })

    it('returns empty when no records match selected period', () => {
      const { result } = renderHook(() => useChartFilters())
      act(() => result.current.togglePeriod('2026-06'))
      expect(result.current.applyFilters(ALL)).toHaveLength(0)
    })
  })
})
