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
  tx_context: TxContext
}

const base = `${api.baseUrl}/api/v1/comments`

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
  if (!res.ok) {
    const d = await res.json().catch(() => null)
    const detail = d?.detail
    // FastAPI 422 devuelve `detail` como lista de {msg,...} (no string) → sin esto se renderiza
    // "[object Object]". Un 4xx/5xx propio devuelve `detail` string.
    const msg =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? (detail[0]?.msg ?? `Error respondiendo (${res.status})`)
          : `Error respondiendo (${res.status})`
    throw new Error(msg)
  }
  return res.json()
}
