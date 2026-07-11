import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useLedger } from './useLedger'
import type { Entity } from '@/contexts/FilterContext'

vi.mock('@/services/dashboard', () => ({
  getLedgerEntries: vi.fn(),
}))

// useFilters mockeado (isRut2Entity queda real) — la entidad se drivea por test.
vi.mock('@/contexts/FilterContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/contexts/FilterContext')>()
  return { ...actual, useFilters: vi.fn() }
})

import { getLedgerEntries } from '@/services/dashboard'
import { useFilters } from '@/contexts/FilterContext'

const mockedGetLedgerEntries = vi.mocked(getLedgerEntries)
const mockedUseFilters = vi.mocked(useFilters)

const EMPTY_RESPONSE = { data: [], meta: { last_sync: null } }

function setEntity(entity: Entity) {
  mockedUseFilters.mockReturnValue({
    entity,
    setEntity: () => {},
    dateFrom: '2026-01-01',
    dateTo: '2026-06-30',
    datePreset: 'year',
    setPreset: () => {},
    setCustomRange: () => {},
  })
}

function makeWrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

describe('useLedger — ruteo por libro (Story 11.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedGetLedgerEntries.mockResolvedValue(EMPTY_RESPONSE)
  })

  it('FFCC (libro RUT2) pide entity=FFCC al API', async () => {
    setEntity('FFCC')
    const { result } = renderHook(() => useLedger(), { wrapper: makeWrapper(newClient()) })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(mockedGetLedgerEntries).toHaveBeenCalledWith(
      expect.objectContaining({ entity: 'FFCC' }),
    )
  })

  it('EAG y las hijas siguen pidiendo entity=EAG (filtrado client-side intacto)', async () => {
    for (const entity of ['EAG', 'Jocelyn'] as Entity[]) {
      vi.clearAllMocks()
      mockedGetLedgerEntries.mockResolvedValue(EMPTY_RESPONSE)
      setEntity(entity)
      const { result } = renderHook(() => useLedger(), { wrapper: makeWrapper(newClient()) })
      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(mockedGetLedgerEntries).toHaveBeenCalledWith(
        expect.objectContaining({ entity: 'EAG' }),
      )
    }
  })

  it('queryKey incluye la entidad: EAG→FFCC refetchea en vez de servir el cache de EAG', async () => {
    const client = newClient()
    setEntity('EAG')
    const { result, rerender } = renderHook(() => useLedger(), { wrapper: makeWrapper(client) })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(mockedGetLedgerEntries).toHaveBeenCalledTimes(1)

    setEntity('FFCC')
    rerender()
    // Sin la entidad en la queryKey, staleTime 60s serviría el cache de EAG sin refetch.
    await waitFor(() => expect(mockedGetLedgerEntries).toHaveBeenCalledTimes(2))
    expect(mockedGetLedgerEntries).toHaveBeenLastCalledWith(
      expect.objectContaining({ entity: 'FFCC' }),
    )
  })
})
