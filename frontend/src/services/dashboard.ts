import { api } from '@/services/api'
import type { BalanceSheetResponse, LedgerEntriesResponse } from '@/types'

interface DashboardParams {
  entity: string
  dateFrom?: string
  dateTo?: string
}

interface LedgerParams extends DashboardParams {
  accountNumber?: string
}

export async function getBalanceSheets(params: DashboardParams): Promise<BalanceSheetResponse> {
  const url = new URL(`${api.baseUrl}/api/v1/balance-sheets`)
  url.searchParams.set('entity', params.entity)
  if (params.dateFrom) url.searchParams.set('date_from', params.dateFrom)
  if (params.dateTo) url.searchParams.set('date_to', params.dateTo)
  const res = await fetch(url.toString(), { credentials: 'include' })
  if (!res.ok) throw new Error(`balance-sheets: ${res.status}`)
  return res.json() as Promise<BalanceSheetResponse>
}

export async function getLedgerEntries(params: LedgerParams): Promise<LedgerEntriesResponse> {
  const url = new URL(`${api.baseUrl}/api/v1/ledger-entries`)
  url.searchParams.set('entity', params.entity)
  if (params.dateFrom) url.searchParams.set('date_from', params.dateFrom)
  if (params.dateTo) url.searchParams.set('date_to', params.dateTo)
  if (params.accountNumber) url.searchParams.set('account_number', params.accountNumber)
  const res = await fetch(url.toString(), { credentials: 'include' })
  if (!res.ok) throw new Error(`ledger-entries: ${res.status}`)
  return res.json() as Promise<LedgerEntriesResponse>
}
