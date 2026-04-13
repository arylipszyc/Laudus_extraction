import { createContext, useContext, useState, type ReactNode } from 'react'

export type Entity = 'EAG' | 'Jocelyn' | 'Jeannette' | 'Johanna' | 'Jael'
export type DatePreset = 'month' | 'quarter' | 'year' | 'custom'

export const ENTITIES: Entity[] = ['EAG', 'Jocelyn', 'Jeannette', 'Johanna', 'Jael']

function getDateRange(preset: Exclude<DatePreset, 'custom'>): { dateFrom: string; dateTo: string } {
  const today = new Date()
  const yyyy = today.getFullYear()
  const mm = today.getMonth() // 0-indexed: Jan=0, Apr=3

  switch (preset) {
    case 'month': {
      // Previous complete month: e.g. on Apr 13 → Mar 1 – Mar 31
      const dateFrom = new Date(yyyy, mm - 1, 1).toISOString().slice(0, 10)
      const dateTo   = new Date(yyyy, mm, 0).toISOString().slice(0, 10)   // day 0 = last day of prev month
      return { dateFrom, dateTo }
    }
    case 'quarter': {
      // 3 previous complete months: e.g. on Apr 13 → Jan 1 – Mar 31
      const dateFrom = new Date(yyyy, mm - 3, 1).toISOString().slice(0, 10)
      const dateTo   = new Date(yyyy, mm, 0).toISOString().slice(0, 10)
      return { dateFrom, dateTo }
    }
    case 'year':
      return { dateFrom: `${yyyy}-01-01`, dateTo: new Date(yyyy, mm, 0).toISOString().slice(0, 10) }
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
