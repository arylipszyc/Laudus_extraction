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
    const err: CartolaError = body?.error ?? {
      code: 'UNKNOWN',
      message: `Upload failed: HTTP ${res.status}`,
    }
    throw err
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
