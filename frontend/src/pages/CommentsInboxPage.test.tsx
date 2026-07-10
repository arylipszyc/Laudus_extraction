import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/services/ownerComments', () => ({ listThreads: vi.fn(), replyThread: vi.fn() }))
vi.mock('@/hooks/useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('@/hooks/useHasRole', () => ({ useHasRole: vi.fn() }))

import { CommentsInboxPage } from './CommentsInboxPage'
import { listThreads, replyThread, type Thread } from '@/services/ownerComments'
import { useAuth } from '@/hooks/useAuth'
import { useHasRole } from '@/hooks/useHasRole'

const THREAD_RESOLVED: Thread = {
  thread_id: 't1',
  root: { comment_id: 't1', author_email: 'ary@eag.cl', author_role: 'family',
    body: '¿qué es este cargo?', ts: '2026-05-01T10:00:00Z' },
  replies: [],
  resolution: null,
  anchor_status: 'resolved',
  tx_id: 'abc123def456',
  tx_context: { date: '2026-04-05', amount: -300, currency: 'CLP',
    account: 'Liabilities:EAG:TC:Real:TestCard', narration: 'COMPRA X', anchor_status: 'resolved' },
}

const THREAD_ORPHANED: Thread = {
  thread_id: 't2',
  root: { comment_id: 't2', author_email: 'otro@eag.cl', author_role: 'family',
    body: 'comentario huérfano', ts: '2026-05-02T10:00:00Z' },
  replies: [],
  resolution: null,
  anchor_status: 'orphaned',
  tx_id: null,
  tx_context: { date: '2026-03-01', amount: -999, currency: 'CLP',
    account: 'Expenses:EAG:Suspense', narration: 'TX VIEJA', anchor_status: 'orphaned' },
}

function renderPage(initialPath = '/comments') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <CommentsInboxPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('<CommentsInboxPage /> (Story 7.2)', () => {
  beforeEach(() => {
    vi.mocked(listThreads).mockResolvedValue([THREAD_RESOLVED, THREAD_ORPHANED])
    vi.mocked(replyThread).mockResolvedValue({ comment_id: 'r1', created_at: '2026-05-03T10:00:00Z' })
    vi.mocked(useAuth).mockReturnValue({ data: { email: 'ary@eag.cl', role: 'family' } } as never)
    vi.mocked(useHasRole).mockReturnValue(true) // contador por defecto
  })

  it('AC6: el contador ve ambos hilos con contexto inline y el huérfano marcado', async () => {
    renderPage()
    // contexto inline: glosa + cuenta de cada hilo
    expect(await screen.findByText('COMPRA X')).toBeInTheDocument()
    expect(screen.getByText('TX VIEJA')).toBeInTheDocument()
    expect(screen.getByText('Liabilities:EAG:TC:Real:TestCard')).toBeInTheDocument()
    // el huérfano se marca como degradado
    expect(screen.getByText(/ya no encontrada en el ledger actual/)).toBeInTheDocument()
  })

  it('AC3: escribir y responder llama a replyThread', async () => {
    renderPage()
    await screen.findByText('COMPRA X')
    const inputs = screen.getAllByPlaceholderText('Escribe una respuesta…')
    fireEvent.change(inputs[0], { target: { value: 'es el arriendo de abril' } })
    fireEvent.click(screen.getAllByText('Responder')[0])
    await waitFor(() => expect(replyThread).toHaveBeenCalledWith('t1', 'es el arriendo de abril'))
  })

  it('AC4/AC6: el owner (family) solo ve sus propios hilos', async () => {
    vi.mocked(useHasRole).mockReturnValue(false) // family, no contador
    vi.mocked(useAuth).mockReturnValue({ data: { email: 'ary@eag.cl', role: 'family' } } as never)
    renderPage()
    // ary es autor de t1 (COMPRA X) pero NO de t2 (TX VIEJA, autor otro@eag.cl)
    expect(await screen.findByText('COMPRA X')).toBeInTheDocument()
    expect(screen.queryByText('TX VIEJA')).not.toBeInTheDocument()
  })

  // ── 7.1b AC5: deep-link ?thread=<id> ──────────────────────────────────────

  it('7.1b AC5: ?thread= arranca en filtro "all" y destaca el hilo', async () => {
    renderPage('/comments?thread=t1')
    await screen.findByText('COMPRA X')
    // arranca en 'all' para que el hilo aparezca aunque esté resuelto
    expect(listThreads).toHaveBeenCalledWith('all')
    // el hilo deep-linkeado se destaca (ring en la Card)
    const card = screen.getByText('COMPRA X').closest('[class*="ring-2"]')
    expect(card).not.toBeNull()
  })

  it('7.1b AC5: un thread_id inexistente no rompe la página', async () => {
    renderPage('/comments?thread=no-existe')
    // la página carga normal con los hilos del filtro
    expect(await screen.findByText('COMPRA X')).toBeInTheDocument()
    expect(screen.getByText('TX VIEJA')).toBeInTheDocument()
  })
})
