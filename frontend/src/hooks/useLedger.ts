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
