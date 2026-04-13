import { useQuery } from '@tanstack/react-query'
import { getLedgerEntries } from '@/services/dashboard'
import { useFilters } from '@/contexts/FilterContext'
import type { LedgerEntriesResponse } from '@/types'

// All ledger data lives in the EAG sheet — entity filtering is applied client-side
// based on Categoria1 content (daughters' names appear in Categoria1).
const SHEET_ENTITY = 'EAG'

export function useLedger(accountNumber?: string) {
  const { dateFrom, dateTo } = useFilters()
  return useQuery<LedgerEntriesResponse>({
    queryKey: ['ledger-entries', dateFrom, dateTo, accountNumber ?? ''],
    queryFn: () => getLedgerEntries({ entity: SHEET_ENTITY, dateFrom, dateTo, accountNumber }),
    staleTime: 60 * 1000,
  })
}
