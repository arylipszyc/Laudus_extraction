import { api } from './api'

// Mirrors backend `backend.app.api.v1.bank_accounts.schemas.BankAccount`.
export interface BankAccount {
  id: string
  account_number: string
  account_type: string
  account_currency: string
  bank_name: string | null
  active: boolean
  account_name: string | null  // joined from plan_de_cuentas
}

/** GET /api/v1/bank-accounts/ — used by CartolaUploadPage dropdown. */
export async function listBankAccounts(): Promise<BankAccount[]> {
  const res = await fetch(`${api.baseUrl}/api/v1/bank-accounts/`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(`Failed to list bank accounts: HTTP ${res.status}`)
  return res.json()
}
