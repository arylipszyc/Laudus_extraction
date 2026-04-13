import { useState, useCallback, useMemo } from 'react'
import type { LedgerEntryRecord } from '@/types'

export interface ChartFilters {
  selectedCategories: string[]
  selectedPeriods: string[]
  hasActiveFilters: boolean
  toggleCategory: (name: string) => void
  togglePeriod: (period: string) => void
  resetFilters: () => void
  applyFilters: (records: LedgerEntryRecord[]) => LedgerEntryRecord[]
}

export function useChartFilters(): ChartFilters {
  const [selectedCategories, setSelectedCategories] = useState<string[]>([])
  const [selectedPeriods, setSelectedPeriods] = useState<string[]>([])

  const hasActiveFilters = selectedCategories.length > 0 || selectedPeriods.length > 0

  const toggleCategory = useCallback((name: string) => {
    setSelectedCategories(prev =>
      prev.includes(name) ? prev.filter(c => c !== name) : [...prev, name]
    )
  }, [])

  const togglePeriod = useCallback((period: string) => {
    setSelectedPeriods(prev =>
      prev.includes(period) ? prev.filter(p => p !== period) : [...prev, period]
    )
  }, [])

  const resetFilters = useCallback(() => {
    setSelectedCategories([])
    setSelectedPeriods([])
  }, [])

  const applyFilters = useCallback((records: LedgerEntryRecord[]): LedgerEntryRecord[] => {
    let result = records

    if (selectedCategories.length > 0) {
      result = result.filter(r => {
        const cat1 = r.Categoria1 || 'Sin categoría'
        return selectedCategories.includes(cat1)
      })
    }

    if (selectedPeriods.length > 0) {
      result = result.filter(r => {
        const period = r.date?.slice(0, 7)
        return period ? selectedPeriods.includes(period) : false
      })
    }

    return result
  }, [selectedCategories, selectedPeriods])

  return useMemo(() => ({
    selectedCategories,
    selectedPeriods,
    hasActiveFilters,
    toggleCategory,
    togglePeriod,
    resetFilters,
    applyFilters,
  }), [selectedCategories, selectedPeriods, hasActiveFilters, toggleCategory, togglePeriod, resetFilters, applyFilters])
}
