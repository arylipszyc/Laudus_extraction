import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useHasRole } from '@/hooks/useHasRole'
import { getReconciliationCount } from '@/services/reconciliation'

/**
 * Story 9.12 AC9 — chip global de reconciliaciones pendientes.
 * Amber por default; rojo si hay ≥1 bloqueante (value-mismatch / fx-out-of-tolerance).
 * Oculto si total=0 o rol family. Polling cada 5 min.
 */
export function PendingReconciliationBadge() {
  const navigate = useNavigate()
  const canSee = useHasRole(['contador', 'admin'])
  const { data } = useQuery({
    queryKey: ['reconciliation-count'],
    queryFn: getReconciliationCount,
    refetchInterval: 5 * 60 * 1000,
    enabled: canSee,
  })

  if (!canSee || !data || data.total === 0) return null

  const red = data.blocking > 0
  const tooltip = red
    ? `${data.total} diferencias entre cartola y Laudus — ${data.blocking} con valores que no cuadran (bloqueante).`
    : `${data.total} diferencias entre cartola y Laudus para revisar.`

  return (
    <button
      onClick={() => navigate('/reconciliation')}
      title={tooltip}
      className={`px-2 py-1 rounded-full text-xs font-medium ${
        red ? 'text-red-600 bg-red-50' : 'text-amber-600 bg-amber-50'
      }`}
    >
      ⚠ {data.total} reconciliaciones
    </button>
  )
}
