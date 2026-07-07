import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/services/cartolas', async (orig) => {
  const actual = await orig<typeof import('@/services/cartolas')>()
  return { ...actual, getCartolaStatus: vi.fn(), validateBalance: vi.fn(), uploadCartola: vi.fn() }
})
vi.mock('@/services/bankAccounts', () => ({ listBankAccounts: vi.fn() }))

import { CartolaUploadPage } from './CartolaUploadPage'
import { ACTIVE_BATCH_KEY } from '@/hooks/useCartolaUpload'
import { getCartolaStatus, validateBalance, type CartolaCanonical, type CartolaStatus } from '@/services/cartolas'
import { listBankAccounts } from '@/services/bankAccounts'

const BATCH = 'batch-1'

const CANONICAL: CartolaCanonical = {
  schema_version: '1.0',
  source: {
    bank_account_id: 'b1', bank_name: 'BCI', account_label: 'TC 1027',
    account_type: 'credit_card', entity: 'EAG',
  },
  period: { start: '2026-06-01', end: '2026-06-30' },
  currency: 'CLP',
  // closing - opening - Σtx = 0 → balance cuadra → botón Confirmar habilitado
  balances: { opening: '0', closing: '-1000' },
  transactions: [
    { line_no: 1, date: '2026-06-15', description: 'COMPRA', amount: '-1000', currency: 'CLP', raw: {} },
  ],
  extraction: { model: 'gemini', extracted_at: '2026-07-06T00:00:00Z', warnings: [] },
}

function status(overrides: Partial<CartolaStatus>): CartolaStatus {
  return { batch_id: BATCH, status: 'ready', canonical: CANONICAL, error: null, ...overrides }
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <CartolaUploadPage />
    </QueryClientProvider>,
  )
}

describe('<CartolaUploadPage /> — confirm async (Fase 3 batch 2)', () => {
  beforeEach(() => {
    sessionStorage.setItem(ACTIVE_BATCH_KEY, BATCH)
    vi.mocked(listBankAccounts).mockResolvedValue([])
  })

  afterEach(() => {
    sessionStorage.clear()
    vi.clearAllMocks()
  })

  it("poll reporta 'confirming' → muestra el estado Confirmando (retoma al volver a la página)", async () => {
    vi.mocked(getCartolaStatus).mockResolvedValue(status({ status: 'confirming' }))
    renderPage()
    expect(await screen.findByText(/Confirmando cartola… esto puede tardar un minuto/)).toBeInTheDocument()
  })

  it("poll reporta 'confirmed' → renderiza el resultado como la respuesta sincrónica de hoy", async () => {
    vi.mocked(getCartolaStatus).mockResolvedValue(
      status({
        status: 'confirmed',
        result: { status: 'reconciled', git_sha: 'abc1234', override: false },
      }),
    )
    renderPage()
    expect(await screen.findByText(/Cartola importada — 1 transacciones/)).toBeInTheDocument()
  })

  it("poll reporta 'confirm_failed' BEAN_CHECK_FAILED → error card con código + detalle", async () => {
    vi.mocked(getCartolaStatus).mockResolvedValue(
      status({
        status: 'confirm_failed',
        canonical: null,
        error: { code: 'BEAN_CHECK_FAILED', message: 'bean-check falló', detail: 'sibling roto: linea 42' },
      }),
    )
    renderPage()
    expect(await screen.findByText(/La confirmación falló/)).toBeInTheDocument()
    expect(screen.getByText(/BEAN_CHECK_FAILED: bean-check falló/)).toBeInTheDocument()
    expect(screen.getByText('sibling roto: linea 42')).toBeInTheDocument()
  })

  it('confirmar → PATCH responde 202 → la página pasa a Confirmando y el poll retoma', async () => {
    let current = status({ status: 'ready' })
    vi.mocked(getCartolaStatus).mockImplementation(async () => current)
    vi.mocked(validateBalance).mockImplementation(async () => {
      current = status({ status: 'confirming' })
      return { status: 'confirming', batch_id: BATCH }
    })

    renderPage()
    fireEvent.click(await screen.findByText('Confirmar validación'))

    await waitFor(() =>
      expect(validateBalance).toHaveBeenCalledWith(BATCH, {
        opening: '0',
        closing: '-1000',
        override_justification: null,
      }),
    )
    expect(await screen.findByText(/Confirmando cartola… esto puede tardar un minuto/)).toBeInTheDocument()
  })
})
