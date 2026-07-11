import { useQuery } from '@tanstack/react-query'
import { getLedgerEntries } from '@/services/dashboard'
import { useFilters, isRut2Entity } from '@/contexts/FilterContext'
import type { LedgerEntriesResponse } from '@/types'

// Libro principal: all ledger data lives in the EAG sheet — entity filtering is
// applied client-side based on Categoria1 content (daughters' names appear in
// Categoria1). Libro RUT2 (FFCC/JAB, Story 11.2): per-entity real del backend —
// se pide la entidad al API y no hay filtrado client-side.
const SHEET_ENTITY = 'EAG'

export function useLedger(accountNumber?: string) {
  const { entity, dateFrom, dateTo } = useFilters()
  const apiEntity = isRut2Entity(entity) ? entity : SHEET_ENTITY
  return useQuery<LedgerEntriesResponse>({
    // apiEntity en la key: sin ella react-query serviría el cache de EAG al
    // seleccionar FFCC/JAB (números de otra entidad).
    queryKey: ['ledger-entries', apiEntity, dateFrom, dateTo, accountNumber ?? ''],
    queryFn: () => getLedgerEntries({ entity: apiEntity, dateFrom, dateTo, accountNumber }),
    staleTime: 60 * 1000,
  })
}
