import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

vi.mock('@/hooks/useLedger', () => ({ useLedger: vi.fn() }))
vi.mock('@/services/ownerComments', () => ({ listThreads: vi.fn(), createComment: vi.fn() }))

import { TransactionRows } from './IncomeExpensesDrilldown'
import { useLedger } from '@/hooks/useLedger'
import { listThreads, createComment } from '@/services/ownerComments'
import type { LedgerEntryRecord } from '@/types'

const row = (over: Partial<LedgerEntryRecord>): LedgerEntryRecord => ({
  journalentryid: 1,
  journalentrynumber: 1,
  date: '2026-04-05',
  accountnumber: '511005',
  lineid: 1,
  description: 'FILA',
  debit: 300,
  credit: 0,
  currencycode: 'CLP',
  paritytomaincurrency: 1,
  periodo: '',
  accountName: 'Gastos',
  Categoria1: '',
  Categoria2: '',
  Categoria3: '',
  ...over,
})

const ROWS: LedgerEntryRecord[] = [
  row({ description: 'CON HILO', tx_id: 'tx-con-hilo' }),
  row({ description: 'SIN HILO', tx_id: 'tx-sin-hilo' }),
  row({ description: 'SIN TXID', tx_id: null }),
]

function renderRows() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route
            path="/"
            element={
              <table>
                <tbody>
                  <TransactionRows accountNumber="511005" type="expenses" selectedPeriods={[]} />
                </tbody>
              </table>
            }
          />
          <Route path="/comments" element={<div>INBOX-PROBE</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('<TransactionRows /> — affordance de comentarios (Story 7.1b)', () => {
  beforeEach(() => {
    vi.mocked(useLedger).mockReturnValue({ data: { data: ROWS, meta: { last_sync: null } }, isLoading: false } as never)
    vi.mocked(listThreads).mockResolvedValue([
      { thread_id: 'th1', tx_id: 'tx-con-hilo' } as never,
    ])
    vi.mocked(createComment).mockResolvedValue({
      thread_id: 'th-nuevo', comment_id: 'c1', created_at: '2026-07-10T10:00:00Z',
    })
  })

  it('AC4: fila con hilo muestra el badge "ver hilo" y navega al inbox', async () => {
    renderRows()
    const badge = await screen.findByLabelText('Ver hilo de comentarios')
    expect(listThreads).toHaveBeenCalledWith('all')
    fireEvent.click(badge)
    expect(await screen.findByText('INBOX-PROBE')).toBeInTheDocument()
  })

  it('AC3: fila sin hilo abre el form inline, submit llama createComment y confirma', async () => {
    renderRows()
    // hay UNA sola affordance de crear (la fila CON HILO tiene badge, la SIN TXID nada)
    const openBtn = await screen.findByLabelText('Comentar esta transacción')
    fireEvent.click(openBtn)
    const textarea = screen.getByPlaceholderText('¿Qué quieres preguntar sobre este movimiento?')
    // vacío → Enviar deshabilitado
    expect(screen.getByText('Enviar')).toBeDisabled()
    fireEvent.change(textarea, { target: { value: '¿qué es este cargo?' } })
    fireEvent.click(screen.getByText('Enviar'))
    await waitFor(() => expect(createComment).toHaveBeenCalledWith('tx-sin-hilo', '¿qué es este cargo?'))
    // confirmación inline, sin toasts
    expect(await screen.findByText(/Comentario enviado/)).toBeInTheDocument()
  })

  it('AC3: fila sin tx_id no muestra affordance', async () => {
    renderRows()
    await screen.findByText('SIN TXID')
    // exactamente 1 badge (CON HILO, espera a que resuelva la query de hilos) + 1 crear (SIN HILO)
    // — la fila sin tx_id no suma ninguna
    expect(await screen.findAllByLabelText('Ver hilo de comentarios')).toHaveLength(1)
    expect(screen.getAllByLabelText('Comentar esta transacción')).toHaveLength(1)
  })
})
