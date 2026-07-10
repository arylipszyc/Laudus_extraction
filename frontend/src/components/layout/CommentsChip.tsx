import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useHasRole } from '@/hooks/useHasRole'
import { getCommentsCount } from '@/services/ownerComments'
import { errorAwareInterval } from '@/lib/pollInterval'

/**
 * Story 7.4 — chip de hilos de comentario con actividad nueva (parte in-app de FR37/FR41).
 * A diferencia de los otros chips del Header, se muestra TAMBIÉN para `family`: es el primer
 * elemento del Header dirigido al owner (el backend cuenta "no leído" según el rol del JWT).
 * Polling 60s (la conversación quiere sentirse más viva que la reconciliación batch).
 */
export function CommentsChip() {
  const navigate = useNavigate()
  const canSee = useHasRole(['family', 'contador', 'admin'])
  const { data, isError } = useQuery({
    queryKey: ['comments-count'],
    queryFn: getCommentsCount,
    refetchInterval: errorAwareInterval(60 * 1000),
    enabled: canSee,
  })

  if (!canSee) return null

  // Error de carga SIN dato previo: chip neutro, no ocultar (patrón PendingReconciliationBadge).
  if (isError && !data) {
    return (
      <button
        onClick={() => navigate('/comments')}
        title="No se pudo cargar el conteo de comentarios — reintentando."
        className="px-2 py-1 rounded-full text-xs font-medium text-muted-foreground bg-muted"
      >
        💬 comentarios —
      </button>
    )
  }

  if (!data || data.unread === 0) return null

  return (
    <button
      onClick={() => navigate('/comments')}
      title={`${data.unread} hilo(s) de comentario con actividad nueva para ti.`}
      className="px-2 py-1 rounded-full text-xs font-medium text-blue-600 bg-blue-50"
    >
      💬 {data.unread} comentarios
    </button>
  )
}
