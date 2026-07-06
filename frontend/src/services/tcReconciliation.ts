import { api } from './api'

// Mirrors backend `backend.app.api.v1.tc_reconciliation.schemas.TcReconciliationRow` (Story 6.6).
export interface TcMovement {
  date: string
  narration: string
  amount: number
  operation_type: string
}

export interface TcReconciliationRow {
  card: string
  year_month: string
  tc_real_account: string
  lump_account: string
  currency: string
  fx: number
  opening: number | null
  closing: number
  closing_clp: number
  // C1
  c1_ok: boolean
  tc_real_balance: number
  // C2
  c2_ok: boolean
  c2_prior_closing: number | null
  c2_reason: string | null
  // C3
  c3_ok: boolean
  c3_corrupted_count: number
  c3_corrupted: { date: string; narration: string; amount: number }[]
  // C4 (pago)
  pago_cartola: number
  laudus_payment_total: number
  laudus_payments: { date: string; narration: string; amount: number; bank_account: string | null }[]
  pago_ok: boolean
  // C5
  c5_ok: boolean
  c5_residual: number
  // agregado + detalle
  status: 'green' | 'yellow' | 'red'
  movements: TcMovement[]
  sum_compras: number
  sum_pagos: number
  sum_cargos: number
}

/** GET /api/v1/tc/reconciliation?card=<bank_account_id>[&year_month=YYYY-MM] — Story 6.6. */
export async function getTcReconciliation(
  card: string,
  yearMonth?: string,
): Promise<TcReconciliationRow[]> {
  const q = new URLSearchParams({ card })
  if (yearMonth) q.set('year_month', yearMonth)
  const res = await fetch(`${api.baseUrl}/api/v1/tc/reconciliation?${q}`, { credentials: 'include' })
  if (!res.ok) throw new Error(`Error cargando cuadre TC (${res.status})`)
  return res.json()
}

export interface TcCartolaSummary {
  card: string
  year_month: string
  currency: string
  status: 'green' | 'yellow' | 'red'
}

/** GET /api/v1/tc/cartolas — historial de cartolas TC subidas (matriz de cobertura). */
export async function getTcCartolas(): Promise<TcCartolaSummary[]> {
  const res = await fetch(`${api.baseUrl}/api/v1/tc/cartolas`, { credentials: 'include' })
  if (!res.ok) throw new Error(`Error cargando cartolas TC (${res.status})`)
  return res.json()
}
