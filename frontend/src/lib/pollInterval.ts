const DEFAULT_MAX_MS = 600_000 // tope 10 min

/** Mínimo estructural de la Query de react-query v5 que consulta el callback de refetchInterval. */
interface QueryLike {
  state: { status: 'pending' | 'error' | 'success'; fetchFailureCount: number }
}

/**
 * refetchInterval error-aware (Fase 3 F8): con el backend caído el poll se estira ×4
 * (con tope) en vez de martillar a cadencia plena; al primer éxito vuelve la cadencia base.
 * Compatible con la firma `refetchInterval: (query) => number` de react-query v5.
 */
export function errorAwareInterval(baseMs: number, opts?: { maxMs?: number }) {
  const maxMs = opts?.maxMs ?? DEFAULT_MAX_MS
  return (query: QueryLike): number => {
    const failing = query.state.status === 'error' || query.state.fetchFailureCount > 0
    return failing ? Math.min(baseMs * 4, maxMs) : baseMs
  }
}
