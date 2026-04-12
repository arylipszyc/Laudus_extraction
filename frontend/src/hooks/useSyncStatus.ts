import { useQuery } from '@tanstack/react-query'
import { getSyncStatus } from '@/services/sync'
import type { SyncStatus } from '@/types'

export function useSyncStatus() {
  return useQuery<SyncStatus>({
    queryKey: ['sync', 'status'],
    queryFn: getSyncStatus,
    refetchInterval: (query) => {
      const status = query.state.data?.job_status
      return status === 'running' ? 5_000 : 60_000
    },
    staleTime: 5_000,
  })
}
