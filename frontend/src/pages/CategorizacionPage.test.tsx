import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/services/categorizacion', async (orig) => {
  const actual = await orig<typeof import('@/services/categorizacion')>()
  return { ...actual, getPendingCategorization: vi.fn(), confirmCategory: vi.fn() }
})

import { CategorizacionPage } from './CategorizacionPage'
import { getPendingCategorization, type PendingTx } from '@/services/categorizacion'

const tx = (over: Partial<PendingTx>): PendingTx => ({
  tx_id: 't', bank_account_id: 'b1', date: '2026-03-10', narration: 'X', amount: -1000,
  current_category: 'Expenses:EAG:Super', current_flag: '!', current_match_source: 'historical',
  current_category_status: 'suggested', current_color: 'green', current_confidence: 0.8, ...over,
})

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}><CategorizacionPage /></QueryClientProvider>,
  )
}

describe('<CategorizacionPage /> Goal B colores', () => {
  beforeEach(() => vi.clearAllMocks())

  it('pinta un badge de color por ítem', async () => {
    vi.mocked(getPendingCategorization).mockResolvedValue([
      tx({ tx_id: 'green', narration: 'VERDE', current_color: 'green' }),
    ])
    renderPage()
    await screen.findByText('VERDE')
    const badges = screen.getAllByTestId('color-badge')
    expect(badges).toHaveLength(1)
    expect(badges[0]).toHaveAttribute('data-color', 'green')
  })

  it('ordena los rojos arriba', async () => {
    vi.mocked(getPendingCategorization).mockResolvedValue([
      tx({ tx_id: 'g', narration: 'VERDE', current_color: 'green' }),
      tx({ tx_id: 'r', narration: 'ROJO', current_color: 'red' }),
      tx({ tx_id: 'y', narration: 'AMARILLO', current_color: 'yellow' }),
    ])
    renderPage()
    await screen.findByText('ROJO')
    const order = screen.getAllByTestId('color-badge').map((b) => b.getAttribute('data-color'))
    expect(order).toEqual(['red', 'yellow', 'green'])
  })

  it('color ausente cae a rojo (señal de revisar)', async () => {
    vi.mocked(getPendingCategorization).mockResolvedValue([
      tx({ tx_id: 'n', narration: 'SIN COLOR', current_color: null }),
    ])
    renderPage()
    await screen.findByText('SIN COLOR')
    expect(screen.getByTestId('color-badge')).toHaveAttribute('data-color', 'red')
  })
})
