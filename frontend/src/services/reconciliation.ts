import { api, apiFetch } from './api'

export interface Discrepancy {
  discrepancy_id: string
  ts: string
  state: string
  bank_account_id: string | null
  year_month: string
  cartola: { line_no: number; date: string; amount: number; currency: string; description: string } | null
  laudus: { journal_entry_id: string; date: string; amount: number; currency?: string; description: string } | null
  fx: { implied: number | null; bcch: number | null; deviation_pct: number | null }
}

export interface HistoryEntry {
  discrepancy_id?: string
  ref_discrepancy_id?: string
  ts?: string
  state?: string
  resolution?: {
    action: string; resolved_by?: string; resolved_at?: string
    justification?: string; escalated_at?: string
  } | null
}

/** Error de resolución que conserva el status HTTP (422 = anotación falló → discrepancia abierta). */
export class ResolveHttpError extends Error {
  status: number
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.name = 'ResolveHttpError'
  }
}

export interface DiscrepanciesResponse {
  discrepancies: Discrepancy[]
  summary: { total: number; by_state: Record<string, number> }
}

/** Estado de un período de reconciliación (Story 6.5). */
export interface PeriodStatus {
  bank_account_id: string | null
  year_month: string
  reconciled_at: string | null
  matched: number
  differences: number
  open: number
  status: 'complete' | 'pending'
}

// Acciones permitidas por estado (espeja backend ACTIONS_BY_STATE, Story 9.12 AC4).
export const ACTIONS_BY_STATE: Record<string, string[]> = {
  'value-mismatch': ['accept-cartola', 'accept-laudus', 'escalate'],
  'missing-in-laudus': ['confirm-cartola-only', 'escalate'],
  'missing-in-cartola': ['confirm-laudus-only', 'escalate'],
  'date-mismatch': ['accept-cartola-date', 'accept-laudus-date', 'escalate'],
  'description-mismatch': ['accept-cartola-description', 'accept-laudus-description', 'merge', 'escalate'],
  'category-mismatch': ['accept-cartola-category', 'accept-laudus-category', 'manual-category', 'escalate'],
  'fx-out-of-tolerance': ['accept-derived-fx', 'accept-bcch-fx', 'manual-fx', 'escalate'],
}

const base = `${api.baseUrl}/api/v1/reconciliation`

export async function getDiscrepancies(params: {
  state?: string; year_month?: string; bank_account_id?: string; discrepancy_id?: string
} = {}): Promise<DiscrepanciesResponse> {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][])
  const res = await apiFetch(`${base}/discrepancies?${q}`, { credentials: 'include' })
  if (!res.ok) throw new Error(`Error cargando discrepancias (${res.status})`)
  return res.json()
}

export async function getReconciliationCount(): Promise<{ total: number; blocking: number }> {
  const res = await apiFetch(`${base}/count`, { credentials: 'include' })
  if (!res.ok) throw new Error(`Error (${res.status})`)
  return res.json()
}

export async function getPeriods(): Promise<PeriodStatus[]> {
  const res = await apiFetch(`${base}/periods`, { credentials: 'include' })
  if (!res.ok) throw new Error(`Error cargando períodos (${res.status})`)
  return res.json()
}

export async function getHistory(id: string): Promise<{ discrepancy_id: string; entries: HistoryEntry[] }> {
  const res = await apiFetch(`${base}/history/${id}`, { credentials: 'include' })
  if (!res.ok) throw new Error(`Error (${res.status})`)
  return res.json()
}

export async function resolveDiscrepancy(
  id: string,
  body: { action: string; justification: string | null; category_account?: string | null },
): Promise<{ status: string; git_commit_sha?: string | null }> {
  const res = await apiFetch(`${base}/discrepancies/${id}/resolve`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const d = await res.json().catch(() => null)
    throw new ResolveHttpError(res.status, d?.detail ?? `Error resolviendo (${res.status})`)
  }
  return res.json()
}
