import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/services/reconciliation', async (orig) => {
  const actual = await orig<typeof import('@/services/reconciliation')>()
  return { ...actual, getDiscrepancies: vi.fn(), getHistory: vi.fn(), resolveDiscrepancy: vi.fn() }
})
vi.mock('@/services/bankAccounts', () => ({ listBankAccounts: vi.fn() }))
vi.mock('@/services/accounts', () => ({ listAccounts: vi.fn() }))

import { ReconciliationPage } from './ReconciliationPage'
import { getDiscrepancies, getHistory, resolveDiscrepancy } from '@/services/reconciliation'
import { listBankAccounts } from '@/services/bankAccounts'
import { listAccounts } from '@/services/accounts'

const DISC = {
  discrepancy_id: 'd1', ts: '2026-05-05T00:00:00Z', state: 'missing-in-laudus',
  bank_account_id: 'b1', year_month: '2026-04',
  cartola: { line_no: 3, date: '2026-04-15', amount: -45000, currency: 'CLP', description: 'GASTO REAL' },
  laudus: null, fx: { implied: null, bcch: null, deviation_pct: null },
}

function renderPage(initial = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initial]}><ReconciliationPage /></MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('<ReconciliationPage /> (Story 6.4)', () => {
  beforeEach(() => {
    vi.mocked(getDiscrepancies).mockResolvedValue({
      discrepancies: [DISC], summary: { total: 1, by_state: { 'missing-in-laudus': 1 } },
    })
    vi.mocked(getHistory).mockResolvedValue({ discrepancy_id: 'd1', entries: [] })
    vi.mocked(listBankAccounts).mockResolvedValue([
      { id: 'b1', account_number: '100', account_type: 'cta', account_currency: 'CLP',
        bank_name: 'Banco BCI', active: true, account_name: 'BCI Cuenta Corriente' },
    ])
    vi.mocked(listAccounts).mockResolvedValue(['Expenses:EAG:Super', 'Expenses:EAG:Luz'])
    vi.mocked(resolveDiscrepancy).mockResolvedValue({ status: 'resolved', git_commit_sha: 'abc1234567' })
  })

  it('AC3: muestra los filtros de mes y cuenta', async () => {
    renderPage()
    await screen.findByText('GASTO REAL')
    expect(screen.getByText('Mes')).toBeInTheDocument()
    expect(screen.getByText('Todas las cuentas')).toBeInTheDocument()
    // el label de la cuenta (no el UUID) se muestra; el UUID 'b1' no aparece como texto (AC7)
    expect(screen.getAllByText('BCI Cuenta Corriente').length).toBeGreaterThan(0)
    expect(screen.queryByText('b1')).not.toBeInTheDocument()
  })

  it('AC1: confirm-cartola-only ofrece autocompletado y envía category_account', async () => {
    renderPage()
    await screen.findByText('GASTO REAL')
    fireEvent.click(screen.getByText('Revisar'))

    // la acción default para missing-in-laudus es confirm-cartola-only → aparece el campo de categoría
    const catInput = await screen.findByPlaceholderText(/Buscar cuenta/)
    fireEvent.change(catInput, { target: { value: 'Super' } })
    fireEvent.mouseDown(await screen.findByText('Expenses:EAG:Super'))

    // justificación ≥10 + confirmar
    fireEvent.change(screen.getByPlaceholderText(/Justificación/), {
      target: { value: 'gasto real verificado contra el banco' },
    })
    fireEvent.click(screen.getByText('Confirmar acción'))

    await waitFor(() => expect(resolveDiscrepancy).toHaveBeenCalledWith('d1', {
      action: 'confirm-cartola-only',
      justification: 'gasto real verificado contra el banco',
      category_account: 'Expenses:EAG:Super',
    }))
  })

  it('AC1/Q2: sin categoría envía category_account null (→ Suspense)', async () => {
    renderPage()
    await screen.findByText('GASTO REAL')
    fireEvent.click(screen.getByText('Revisar'))
    await screen.findByPlaceholderText(/Buscar cuenta/)
    fireEvent.change(screen.getByPlaceholderText(/Justificación/), {
      target: { value: 'lo categorizo despues en categorizacion' },
    })
    fireEvent.click(screen.getByText('Confirmar acción'))
    await waitFor(() => expect(resolveDiscrepancy).toHaveBeenCalledWith('d1', expect.objectContaining({
      action: 'confirm-cartola-only', category_account: null,
    })))
  })
})
