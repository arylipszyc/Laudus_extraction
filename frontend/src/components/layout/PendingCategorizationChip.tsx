import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useHasRole } from '@/hooks/useHasRole'
import { getPendingCategorization } from '@/services/categorizacion'

/**
 * Story 9.8 AC10 — chip global de categorías pendientes (smart_importer flag `!`).
 * Siempre amber (nunca bloqueante). Oculto si count=0 o rol family. Coexiste con el chip
 * de reconciliación (9.12). Polling 60s.
 */
export function PendingCategorizationChip() {
  const navigate = useNavigate()
  const canSee = useHasRole(['contador', 'admin'])
  const { data } = useQuery({
    queryKey: ['categorization-pending'],
    queryFn: getPendingCategorization,
    refetchInterval: 60 * 1000,
    enabled: canSee,
  })

  const count = data?.length ?? 0
  if (!canSee || count === 0) return null

  return (
    <button
      onClick={() => navigate('/categorizacion')}
      title={`${count} transacciones con categoría sugerida pendiente de confirmar. Click para revisar.`}
      className="px-2 py-1 rounded-full text-xs font-medium text-amber-600 bg-amber-50"
    >
      ⚠ {count} categorías
    </button>
  )
}
