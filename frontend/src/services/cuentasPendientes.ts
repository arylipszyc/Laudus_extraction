import { api, apiFetch } from './api'

// Espeja backend `cuentas_pendientes.schemas`.
export interface Suggestion {
  categoria1: string
  categoria2: string
  account: string
}

export interface PendingAccount {
  code: string
  pending_account: string
  monto_acumulado: number
  laudus_account_name: string | null
  suggestion: Suggestion
}

export interface PromoteResponse {
  code: string
  account: string
  git_commit_sha: string | null
  backfill_recommended: boolean
  message: string
}

/** GET /api/v1/cuentas-pendientes/ — cuentas en cuarentena + sugerencia (contador/admin). */
export async function listCuentasPendientes(): Promise<PendingAccount[]> {
  const res = await apiFetch(`${api.baseUrl}/api/v1/cuentas-pendientes/`, { credentials: 'include' })
  if (!res.ok) throw new Error(`Error listando cuentas pendientes (${res.status})`)
  return res.json()
}

/** POST /api/v1/cuentas-pendientes/{code}/promover — escribe el open final al plan. */
export async function promoverCuenta(
  code: string,
  body: { categoria1: string; categoria2: string; categoria3: string; laudus_account_name?: string; account?: string },
): Promise<PromoteResponse> {
  const res = await apiFetch(`${api.baseUrl}/api/v1/cuentas-pendientes/${code}/promover`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    // FastAPI devuelve `detail` como string (HTTPException) o como array (422 de validación).
    const detail = Array.isArray(body?.detail)
      ? body.detail.map((e: { msg?: string }) => e.msg ?? '').filter(Boolean).join('; ')
      : body?.detail
    throw new Error(detail || `Error promoviendo cuenta (${res.status})`)
  }
  return res.json()
}
