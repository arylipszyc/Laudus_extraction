import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/services/tcReconciliation', () => ({ getTcReconciliation: vi.fn() }))
vi.mock('@/services/bankAccounts', () => ({ listBankAccounts: vi.fn() }))

import { TcReconciliationPage } from './TcReconciliationPage'
import { getTcReconciliation, type TcReconciliationRow } from '@/services/tcReconciliation'
import { listBankAccounts } from '@/services/bankAccounts'

const base = {
  card: 'BCI_1027', tc_real_account: 'Liabilities:EAG:TC:Real:Tc1027', lump_account: 'Expenses:EAG:TC:Tc1027-430005',
  currency: 'CLP', fx: 1, opening: 1000, closing_clp: 1300,
  c2_ok: true, c2_prior_closing: 1000, c2_reason: null,
  c3_corrupted_count: 0, c3_corrupted: [], pago_cartola: 0, laudus_payment_total: 0, laudus_payments: [], pago_ok: true,
  c5_ok: true, c5_residual: 0, movements: [], sum_compras: 0, sum_pagos: 0, sum_cargos: 0,
}
const GREEN: TcReconciliationRow = {
  ...base, year_month: '2026-04', closing: 1300, tc_real_balance: -1300,
  c1_ok: true, c3_ok: true, status: 'green',
}
const RED: TcReconciliationRow = {
  ...base, year_month: '2026-03', closing: 1000, tc_real_balance: -999,
  c1_ok: false, c3_ok: true, status: 'red',
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><TcReconciliationPage /></MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('<TcReconciliationPage /> (Story 6.6)', () => {
  beforeEach(() => {
    vi.mocked(listBankAccounts).mockResolvedValue([
      { id: 'BCI_1027', account_number: '1027', account_type: 'tarjeta_credito', account_currency: 'CLP',
        bank_name: 'Banco BCI', active: true, account_name: 'Visa Infinity 1027' },
    ])
    vi.mocked(getTcReconciliation).mockResolvedValue([GREEN, RED])
  })

  it('muestra una fila por mes con semáforos; el mes rojo va arriba', async () => {
    renderPage()
    await screen.findByText('2026-04')
    expect(screen.getByText('2026-03')).toBeInTheDocument()
    // rojos arriba: la primera fila de datos es marzo (status red)
    const months = screen.getAllByText(/^2026-0[34]$/).map((el) => el.textContent)
    expect(months[0]).toBe('2026-03')
  })

  it('expande la fila y muestra la cascada de conciliación + el detalle por chequeo', async () => {
    renderPage()
    fireEvent.click(await screen.findByText('2026-03'))
    // la cascada de conciliación (la cadena de montos que ata mes a mes)
    expect(await screen.findByText('Conciliación del mes')).toBeInTheDocument()
    expect(screen.getByText('Saldo del mes anterior')).toBeInTheDocument()
    expect(screen.getByText('Saldo en la contabilidad')).toBeInTheDocument()
    // y el detalle por chequeo con la comparación C1 (dos lados + acción)
    expect(screen.getByText(/Deuda en la contabilidad/)).toBeInTheDocument()
    expect(screen.getByText(/no coincide con el estado de cuenta/)).toBeInTheDocument()
  })
})
