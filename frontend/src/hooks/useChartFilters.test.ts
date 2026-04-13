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
    Categoria1: 'Ingresos',
    Categoria2: '',
    Categoria3: '',
    ...overrides,
  }
}

const JAN_INCOME = makeRecord({ Categoria1: 'Ingresos', date: '2026-01-10' })
const JAN_EXPENSE = makeRecord({ Categoria1: 'Gastos Operacionales', date: '2026-01-20', debit: 50000, credit: 0 })
const FEB_INCOME = makeRecord({ Categoria1: 'Ingresos', date: '2026-02-05' })
const FEB_OTHER = makeRecord({ Categoria1: 'Otros Ingresos', date: '2026-02-10' })

describe('useChartFilters', () => {
  it('initializes with empty filters and hasActiveFilters=false', () => {
    const { result } = renderHook(() => useChartFilters())
    expect(result.current.selectedCategories).toEqual([])
    expect(result.current.selectedPeriods).toEqual([])
    expect(result.current.hasActiveFilters).toBe(false)
  })

  it('toggleCategory adds a category', () => {
    const { result } = renderHook(() => useChartFilters())
    act(() => result.current.toggleCategory('Ingresos'))
    expect(result.current.selectedCategories).toContain('Ingresos')
    expect(result.current.hasActiveFilters).toBe(true)
  })

  it('toggleCategory removes an already-selected category', () => {
    const { result } = renderHook(() => useChartFilters())
    act(() => result.current.toggleCategory('Ingresos'))
    act(() => result.current.toggleCategory('Ingresos'))
    expect(result.current.selectedCategories).toHaveLength(0)
  })

  it('toggleCategory accumulates multiple selections', () => {
    const { result } = renderHook(() => useChartFilters())
    act(() => result.current.toggleCategory('Ingresos'))
    act(() => result.current.toggleCategory('Gastos Operacionales'))
    expect(result.current.selectedCategories).toHaveLength(2)
  })

  it('togglePeriod adds a period', () => {
    const { result } = renderHook(() => useChartFilters())
    act(() => result.current.togglePeriod('2026-01'))
    expect(result.current.selectedPeriods).toContain('2026-01')
  })

  it('togglePeriod removes an already-selected period', () => {
    const { result } = renderHook(() => useChartFilters())
    act(() => result.current.togglePeriod('2026-01'))
    act(() => result.current.togglePeriod('2026-01'))
    expect(result.current.selectedPeriods).toHaveLength(0)
  })

  it('resetFilters clears both selectedCategories and selectedPeriods', () => {
    const { result } = renderHook(() => useChartFilters())
    act(() => result.current.toggleCategory('Ingresos'))
    act(() => result.current.togglePeriod('2026-01'))
    act(() => result.current.resetFilters())
    expect(result.current.selectedCategories).toHaveLength(0)
    expect(result.current.selectedPeriods).toHaveLength(0)
    expect(result.current.hasActiveFilters).toBe(false)
  })

  describe('applyFilters', () => {
    const ALL = [JAN_INCOME, JAN_EXPENSE, FEB_INCOME, FEB_OTHER]

    it('returns all records when no filters active', () => {
      const { result } = renderHook(() => useChartFilters())
      expect(result.current.applyFilters(ALL)).toHaveLength(4)
    })

    it('filters by selected category (OR within dimension)', () => {
      const { result } = renderHook(() => useChartFilters())
      act(() => result.current.toggleCategory('Ingresos'))
      const filtered = result.current.applyFilters(ALL)
      expect(filtered).toHaveLength(2)
      expect(filtered.every(r => r.Categoria1 === 'Ingresos')).toBe(true)
    })

    it('multiple categories are OR within dimension', () => {
      const { result } = renderHook(() => useChartFilters())
      act(() => result.current.toggleCategory('Ingresos'))
      act(() => result.current.toggleCategory('Otros Ingresos'))
      const filtered = result.current.applyFilters(ALL)
      expect(filtered).toHaveLength(3) // JAN_INCOME + FEB_INCOME + FEB_OTHER
    })

    it('filters by selected period (OR within dimension)', () => {
      const { result } = renderHook(() => useChartFilters())
      act(() => result.current.togglePeriod('2026-01'))
      const filtered = result.current.applyFilters(ALL)
      expect(filtered).toHaveLength(2)
    })

    it('multiple periods are OR within dimension', () => {
      const { result } = renderHook(() => useChartFilters())
      act(() => result.current.togglePeriod('2026-01'))
      act(() => result.current.togglePeriod('2026-02'))
      const filtered = result.current.applyFilters(ALL)
      expect(filtered).toHaveLength(4)
    })

    it('category AND period filters use AND logic across dimensions', () => {
      const { result } = renderHook(() => useChartFilters())
      act(() => result.current.toggleCategory('Ingresos'))
      act(() => result.current.togglePeriod('2026-01'))
      const filtered = result.current.applyFilters(ALL)
      expect(filtered).toHaveLength(1)
      expect(filtered[0]).toBe(JAN_INCOME)
    })

    it('returns empty when filters match nothing', () => {
      const { result } = renderHook(() => useChartFilters())
      act(() => result.current.toggleCategory('Inexistente'))
      expect(result.current.applyFilters(ALL)).toHaveLength(0)
    })
  })
})
