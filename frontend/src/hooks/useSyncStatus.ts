import { useQuery } from '@tanstack/react-query'
import { getSyncStatus } from '@/services/sync'
import { errorAwareInterval } from '@/lib/pollInterval'
import type { SyncStatus } from '@/types'

export function useSyncStatus() {
  return useQuery<SyncStatus>({
    queryKey: ['sync', 'status'],
    queryFn: getSyncStatus,
    refetchInterval: (query) => {
      // Cadencia base según el job (5s corriendo / 60s idle), estirada ×4 si el poll falla (F8).
      // En error la base es la de idle: un 'running' stale no debe hacer que la caída
      // polee MÁS rápido (5s×4=20s) que el idle sano (60s) — outage → 60s×4 = 240s.
      const running = query.state.data?.job_status === 'running'
      const base = query.state.status === 'error' ? 60_000 : (running ? 5_000 : 60_000)
      return errorAwareInterval(base)(query)
    },
    staleTime: 5_000,
  })
}
