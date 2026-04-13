import { useState, useCallback, useMemo } from 'react'
import type { LedgerEntryRecord } from '@/types'

export interface ChartFilters {
  selectedPeriods: string[]
  hasActiveFilters: boolean
  togglePeriod: (period: string) => void
  resetFilters: () => void
  applyFilters: (records: LedgerEntryRecord[]) => LedgerEntryRecord[]
}

export function useChartFilters(): ChartFilters {
  const [selectedPeriods, setSelectedPeriods] = useState<string[]>([])

  const hasActiveFilters = selectedPeriods.length > 0

  const togglePeriod = useCallback((period: string) => {
    setSelectedPeriods(prev =>
      prev.includes(period) ? prev.filter(p => p !== period) : [...prev, period]
    )
  }, [])

  const resetFilters = useCallback(() => {
    setSelectedPeriods([])
  }, [])

  const applyFilters = useCallback((records: LedgerEntryRecord[]): LedgerEntryRecord[] => {
    if (selectedPeriods.length === 0) return records
    return records.filter(r => {
      const period = r.date?.slice(0, 7)
      return period ? selectedPeriods.includes(period) : false
    })
  }, [selectedPeriods])

  return useMemo(() => ({
    selectedPeriods,
    hasActiveFilters,
    togglePeriod,
    resetFilters,
    applyFilters,
  }), [selectedPeriods, hasActiveFilters, togglePeriod, resetFilters, applyFilters])
}
