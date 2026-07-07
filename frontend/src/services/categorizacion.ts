import { api, apiFetch } from './api'

export interface PendingTx {
  tx_id: string
  bank_account_id: string | null
  date: string
  narration: string | null
  amount: number | null
  current_category: string | null
  current_flag: string | null
  current_match_source: string | null
  current_category_status: string | null
  current_color: 'green' | 'yellow' | 'red' | null
  current_confidence: number | null
}

/** GET /api/v1/categorization/pending — tx con category_status ∈ (suggested, pending) (Story 9.7 AC9). */
export async function getPendingCategorization(): Promise<PendingTx[]> {
  const res = await apiFetch(`${api.baseUrl}/api/v1/categorization/pending`, { credentials: 'include' })
  if (!res.ok) throw new Error(`Error cargando pendientes (${res.status})`)
  return res.json()
}

/** PATCH /api/v1/transactions/{tx_id}/category — corrige/confirma (Story 9.7 AC7). */
export async function confirmCategory(txId: string, categoryAccount: string): Promise<void> {
  const res = await apiFetch(`${api.baseUrl}/api/v1/transactions/${txId}/category`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category_account: categoryAccount }),
  })
  if (!res.ok) {
    const d = await res.json().catch(() => null)
    throw new Error(d?.detail ?? `Error confirmando (${res.status})`)
  }
}

/** POST /api/v1/transactions/bulk-categorize — confirma varias con su categoría en UN commit. */
export async function bulkCategorize(
  items: { tx_id: string; category_account: string }[],
): Promise<{ confirmed: number; git_sha: string | null }> {
  const res = await apiFetch(`${api.baseUrl}/api/v1/transactions/bulk-categorize`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  })
  if (!res.ok) {
    const d = await res.json().catch(() => null)
    throw new Error(d?.detail ?? `Error confirmando en lote (${res.status})`)
  }
  return res.json()
}
