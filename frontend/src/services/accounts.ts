import { api } from './api'

/** GET /api/v1/accounts?root=Expenses — plan de cuentas para el autocompletado (Story 6.4). */
export async function listAccounts(root = 'Expenses'): Promise<string[]> {
  const res = await fetch(`${api.baseUrl}/api/v1/accounts/?root=${encodeURIComponent(root)}`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(`Error cargando cuentas (${res.status})`)
  const data: { accounts: string[] } = await res.json()
  return data.accounts
}
