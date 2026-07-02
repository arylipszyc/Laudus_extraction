import { api } from './api'

// Mirrors backend `CartolaCanonicalV1` (architecture-c4 §4.1).
// Numeric fields arrive as strings (Pydantic Decimal serialisation) — the UI
// renders them with Intl.NumberFormat, so we keep them typed as string here.
export interface CartolaCanonical {
  schema_version: '1.0'
  source: {
    bank_account_id: string
    bank_name: string
    account_label: string
    account_type: string
    entity: string
  }
  period: { start: string; end: string }
  currency: string
  balances: { opening: string; closing: string }
  transactions: Array<{
    line_no: number
    date: string
    description: string
    amount: string
    currency: string
    raw: Record<string, unknown>
  }>
  extraction: {
    model: string
    extracted_at: string
    warnings: Array<{ code: string; line_no: number | null; detail: string }>
  }
}

export interface UploadAccepted {
  status: 'processing'
  batch_id: string
}

export interface CartolaStatus {
  batch_id: string
  status: 'processing' | 'ready' | 'failed'
  canonical: CartolaCanonical | null
  error: { code: string; message: string; detail?: unknown } | null
}

export interface CartolaError {
  code: string
  message: string
}

/**
 * El handler global del backend a veces mete un objeto `{code, message}` dentro de
 * `error.message` (HTTPException con `detail` dict — p.ej. staging expirado → 404).
 * El panel renderiza `err.message` directo, así que un objeto ahí crashea el árbol de
 * React (error #31 → pantalla en blanco). Normalizamos `code`/`message` a string.
 */
function normalizeApiError(
  raw: unknown,
  fallback: CartolaError,
): CartolaError & Record<string, unknown> {
  const e = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const code = typeof e.code === 'string' ? e.code : fallback.code
  const m = e.message
  const message =
    typeof m === 'string'
      ? m
      : m && typeof m === 'object' && typeof (m as Record<string, unknown>).message === 'string'
        ? ((m as Record<string, unknown>).message as string)
        : m == null
          ? fallback.message
          : JSON.stringify(m)
  return { ...e, code, message }
}

/** POST /api/v1/cartolas/upload — multipart. Resolves to 202 batch_id. */
export async function uploadCartola(
  pdfFile: File,
  bankAccountId: string,
): Promise<UploadAccepted> {
  const form = new FormData()
  form.append('pdf_file', pdfFile)
  form.append('bank_account_id', bankAccountId)
  const res = await fetch(`${api.baseUrl}/api/v1/cartolas/upload`, {
    method: 'POST',
    credentials: 'include',
    body: form,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw normalizeApiError(body?.error, {
      code: 'UNKNOWN',
      message: `Upload failed: HTTP ${res.status}`,
    })
  }
  return res.json()
}

export interface ValidateBalanceResult {
  status: 'validated'
  file: string
  git_sha: string | null
  override: boolean
}

export interface BalanceDiscrepancyError extends CartolaError {
  diff?: number
  calculated?: number
  stated?: number
}

/** PATCH /api/v1/cartolas/{batch_id}/validate-balance — Story 9.9. */
export async function validateBalance(
  batchId: string,
  body: { opening: string; closing: string; override_justification: string | null },
): Promise<ValidateBalanceResult> {
  const res = await fetch(`${api.baseUrl}/api/v1/cartolas/${batchId}/validate-balance`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    throw normalizeApiError(data?.error, { code: 'UNKNOWN', message: `HTTP ${res.status}` }) as BalanceDiscrepancyError
  }
  return res.json()
}

/** GET /api/v1/cartolas/{batch_id} — polled by useCartolaUpload. */
export async function getCartolaStatus(batchId: string): Promise<CartolaStatus> {
  const res = await fetch(`${api.baseUrl}/api/v1/cartolas/${batchId}`, {
    credentials: 'include',
  })
  if (!res.ok) {
    if (res.status === 404) {
      throw { code: 'NOT_FOUND', message: 'batch_id not found or expired' } as CartolaError
    }
    throw { code: 'UNKNOWN', message: `Status check failed: HTTP ${res.status}` } as CartolaError
  }
  return res.json()
}
