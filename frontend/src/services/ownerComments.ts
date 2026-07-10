import { api, apiFetch } from './api'

/** Contexto de la transacción ancla, re-resuelto en caliente al listar (Story 7.2 AC2). */
export interface TxContext {
  date: string | null
  amount: number | null
  currency: string | null
  account: string | null
  narration: string
  anchor_status: AnchorStatus
}

export type AnchorStatus = 'resolved' | 're-anchored' | 'orphaned'

export interface CommentRoot {
  comment_id: string
  author_email: string
  author_role: string
  body: string
  ts: string
}

export interface Reply {
  reply_id: string
  author_email: string
  author_role: string
  body: string
  ts: string
}

export interface Thread {
  thread_id: string
  root: CommentRoot
  replies: Reply[]
  resolution: Record<string, unknown> | null
  anchor_status: AnchorStatus
  /** 7.1b AC2: tx_id ACTUAL de la tx ancla (el nuevo si re-anchored, null si orphaned). */
  tx_id: string | null
  tx_context: TxContext
  /** 7.4: actividad de la otra parte sin leer PARA el usuario actual. */
  unread: boolean
}

const base = `${api.baseUrl}/api/v1/comments`

async function errorMessage(res: Response, fallback: string): Promise<string> {
  const d = await res.json().catch(() => null)
  const detail = d?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const err = detail[0]
    if (err && typeof err === 'object') {
      const loc = Array.isArray(err.loc) ? err.loc.join('.') : ''
      const msg = err.msg || fallback
      return loc ? `${loc}: ${msg}` : msg
    }
  }
  return fallback
}

export async function listThreads(status: 'open' | 'resolved' | 'all' = 'open'): Promise<Thread[]> {
  const res = await apiFetch(`${base}?status=${status}`, { credentials: 'include' })
  if (!res.ok) throw new Error(`Error cargando comentarios (${res.status})`)
  return res.json()
}

export async function replyThread(
  thread_id: string,
  body: string,
): Promise<{ comment_id: string; created_at: string }> {
  const res = await apiFetch(`${base}/${thread_id}/reply`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ body }),
  })
  if (!res.ok) throw new Error(await errorMessage(res, `Error respondiendo (${res.status})`))
  return res.json()
}

/** 7.4 AC1: conteo de hilos abiertos + no-leídos para el usuario actual (alimenta el chip). */
export async function getCommentsCount(): Promise<{ total: number; unread: number }> {
  const res = await apiFetch(`${base}/count`, { credentials: 'include' })
  if (!res.ok) throw new Error(`Error cargando conteo de comentarios (${res.status})`)
  return res.json()
}

/** 7.4 AC2/AC6: marca el hilo como leído por el usuario actual (marcador append-only). */
export async function markThreadRead(
  thread_id: string,
): Promise<{ thread_id: string; read_at: string }> {
  const res = await apiFetch(`${base}/${thread_id}/read`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await errorMessage(res, `Error marcando leído (${res.status})`))
  return res.json()
}

/** 7.3 AC6: marca el hilo como resuelto (nota opcional). Doble resolución → 400 legible. */
export async function resolveThread(
  thread_id: string,
  note?: string,
): Promise<{ thread_id: string; resolved_at: string }> {
  const res = await apiFetch(`${base}/${thread_id}/resolve`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(note ? { note } : {}),
  })
  if (!res.ok) throw new Error(await errorMessage(res, `Error resolviendo (${res.status})`))
  return res.json()
}

/** 7.1b AC3: crea el hilo raíz sobre una transacción del drill-down (POST de 7.1). */
export async function createComment(
  tx_id: string,
  body: string,
): Promise<{ thread_id: string; comment_id: string; created_at: string }> {
  const res = await apiFetch(base, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tx_id, body }),
  })
  if (!res.ok) throw new Error(await errorMessage(res, `Error creando el comentario (${res.status})`))
  return res.json()
}
