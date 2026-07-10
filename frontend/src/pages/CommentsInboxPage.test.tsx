import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/services/ownerComments', () => ({
  listThreads: vi.fn(), replyThread: vi.fn(), resolveThread: vi.fn(), markThreadRead: vi.fn(),
}))
vi.mock('@/hooks/useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('@/hooks/useHasRole', () => ({ useHasRole: vi.fn() }))

import { CommentsInboxPage } from './CommentsInboxPage'
import {
  listThreads, markThreadRead, replyThread, resolveThread, type Thread,
} from '@/services/ownerComments'
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
  unread: true,
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
  unread: false,
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
    vi.clearAllMocks() // los conteos de llamadas no deben arrastrarse entre tests
    vi.mocked(listThreads).mockResolvedValue([THREAD_RESOLVED, THREAD_ORPHANED])
    vi.mocked(replyThread).mockResolvedValue({ comment_id: 'r1', created_at: '2026-05-03T10:00:00Z' })
    vi.mocked(markThreadRead).mockResolvedValue({ thread_id: 't1', read_at: '2026-05-03T10:00:00Z' })
    vi.mocked(useAuth).mockReturnValue({ data: { email: 'ary@eag.cl', role: 'family' } } as never)
    vi.mocked(useHasRole).mockReturnValue(true) // contador por defecto
  })

  it('AC6: el contador ve ambos hilos (resumen colapsado) y el huérfano marcado al expandir', async () => {
    renderPage()
    // resumen colapsado: la glosa de cada hilo visible sin expandir (7.4)
    expect(await screen.findByText('COMPRA X')).toBeInTheDocument()
    expect(screen.getByText('TX VIEJA')).toBeInTheDocument()
    // expandir muestra el contexto completo
    fireEvent.click(screen.getByText('COMPRA X'))
    expect(screen.getByText('Liabilities:EAG:TC:Real:TestCard')).toBeInTheDocument()
    fireEvent.click(screen.getByText('TX VIEJA'))
    // el huérfano se marca como degradado
    expect(screen.getByText(/ya no encontrada en el ledger actual/)).toBeInTheDocument()
  })

  it('AC3: escribir y responder llama a replyThread', async () => {
    renderPage()
    fireEvent.click(await screen.findByText('COMPRA X')) // expandir (7.4)
    const inputs = screen.getAllByPlaceholderText('Escribe una respuesta…')
    fireEvent.change(inputs[0], { target: { value: 'es el arriendo de abril' } })
    fireEvent.click(screen.getAllByText('Responder')[0])
    await waitFor(() => expect(replyThread).toHaveBeenCalledWith('t1', 'es el arriendo de abril'))
  })

  // ── 7.4 AC6: expandir un hilo no-leído lo marca leído (una vez) ────────────

  it('7.4 AC6: expandir un hilo unread llama markThreadRead una sola vez', async () => {
    renderPage()
    const header = await screen.findByText('COMPRA X') // t1 es unread: true
    fireEvent.click(header)
    await waitFor(() => expect(markThreadRead).toHaveBeenCalledWith('t1'))
    // colapsar y re-expandir no re-marca
    fireEvent.click(header)
    fireEvent.click(header)
    expect(markThreadRead).toHaveBeenCalledTimes(1)
  })

  it('7.4 AC6: expandir un hilo ya leído NO llama markThreadRead', async () => {
    renderPage()
    fireEvent.click(await screen.findByText('TX VIEJA')) // t2 es unread: false
    await screen.findByText(/ya no encontrada en el ledger actual/)
    expect(markThreadRead).not.toHaveBeenCalledWith('t2')
  })

  it('7.4: el hilo no-leído muestra el indicador "nuevo" en el resumen', async () => {
    renderPage()
    await screen.findByText('COMPRA X')
    expect(screen.getByText('nuevo')).toBeInTheDocument() // solo t1 (unread)
  })

  it('AC4/AC6: el owner (family) solo ve sus propios hilos', async () => {
    vi.mocked(useHasRole).mockReturnValue(false) // family, no contador
    vi.mocked(useAuth).mockReturnValue({ data: { email: 'ary@eag.cl', role: 'family' } } as never)
    renderPage()
    // ary es autor de t1 (COMPRA X) pero NO de t2 (TX VIEJA, autor otro@eag.cl)
    expect(await screen.findByText('COMPRA X')).toBeInTheDocument()
    expect(screen.queryByText('TX VIEJA')).not.toBeInTheDocument()
  })

  // ── 7.3 AC6: marcar resuelto ──────────────────────────────────────────────

  it('7.3 AC6: "Marcar resuelto" llama resolveThread y el hilo desaparece de abiertos', async () => {
    vi.mocked(resolveThread).mockResolvedValue({ thread_id: 't1', resolved_at: '2026-07-10T10:00:00Z' })
    // unread: false para que expandir no dispare mark-read (aísla el refetch del resolve)
    vi.mocked(listThreads).mockResolvedValue([{ ...THREAD_RESOLVED, unread: false }, THREAD_ORPHANED])
    renderPage()
    fireEvent.click(await screen.findByText('COMPRA X')) // expandir (7.4)
    // tras resolver, el backend ya no devuelve t1 en "Abiertos" → el refetch por invalidación lo saca
    vi.mocked(listThreads).mockResolvedValue([THREAD_ORPHANED])
    fireEvent.click(screen.getAllByText('Marcar resuelto')[0])
    await waitFor(() => expect(resolveThread).toHaveBeenCalledWith('t1'))
    await waitFor(() => expect(screen.queryByText('COMPRA X')).not.toBeInTheDocument())
  })

  it('7.3 AC6: un hilo ya resuelto no muestra el botón', async () => {
    vi.mocked(listThreads).mockResolvedValue([
      { ...THREAD_RESOLVED, resolution: { action: 'resolve', resolved_by: 'c@eag.cl' }, unread: false },
    ])
    renderPage()
    fireEvent.click(await screen.findByText('COMPRA X')) // expandir (7.4)
    expect(screen.queryByText('Marcar resuelto')).not.toBeInTheDocument()
  })

  // ── 7.1b AC5: deep-link ?thread=<id> ──────────────────────────────────────

  it('7.1b AC5: ?thread= arranca en filtro "all", destaca y auto-expande el hilo', async () => {
    renderPage('/comments?thread=t1')
    // auto-expandido (7.4): la glosa aparece en el resumen Y en el contexto expandido
    const matches = await screen.findAllByText('COMPRA X')
    // arranca en 'all' para que el hilo aparezca aunque esté resuelto
    expect(listThreads).toHaveBeenCalledWith('all')
    // el hilo deep-linkeado se destaca (ring en la Card) y está expandido (cuerpo visible)
    const card = matches[0].closest('[class*="ring-2"]')
    expect(card).not.toBeNull()
    expect(screen.getByText('¿qué es este cargo?')).toBeInTheDocument()
  })

  it('7.1b AC5: un thread_id inexistente no rompe la página', async () => {
    renderPage('/comments?thread=no-existe')
    // la página carga normal con los hilos del filtro
    expect(await screen.findByText('COMPRA X')).toBeInTheDocument()
    expect(screen.getByText('TX VIEJA')).toBeInTheDocument()
  })
})
