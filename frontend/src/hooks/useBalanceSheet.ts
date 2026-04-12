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
