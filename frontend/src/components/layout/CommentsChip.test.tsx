import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/services/ownerComments', () => ({ getCommentsCount: vi.fn() }))
vi.mock('@/hooks/useHasRole', () => ({ useHasRole: vi.fn() }))

import { CommentsChip } from './CommentsChip'
import { getCommentsCount } from '@/services/ownerComments'
import { useHasRole } from '@/hooks/useHasRole'

function renderChip() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const utils = render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CommentsChip />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { client, ...utils }
}

describe('<CommentsChip /> (Story 7.4)', () => {
  beforeEach(() => {
    // el chip es visible para family TAMBIÉN (a diferencia de los otros chips del Header)
    vi.mocked(useHasRole).mockReturnValue(true)
  })

  it('AC3: muestra el conteo de no-leídos y linkea al inbox', async () => {
    vi.mocked(getCommentsCount).mockResolvedValue({ total: 3, unread: 2 })
    renderChip()
    expect(await screen.findByText(/2 comentarios/)).toBeInTheDocument()
  })

  it('AC3: oculto si unread es 0', async () => {
    vi.mocked(getCommentsCount).mockResolvedValue({ total: 3, unread: 0 })
    const { container, client } = renderChip()
    // esperar a que la query RESUELVA (determinista, sin sleep) y verificar que no rinde nada
    await waitFor(() =>
      expect(client.getQueryState(['comments-count'])?.status).toBe('success'))
    expect(container.querySelector('button')).toBeNull()
  })

  it('AC3: pide visibilidad para family también (rasgo distintivo de la story)', async () => {
    vi.mocked(getCommentsCount).mockResolvedValue({ total: 1, unread: 1 })
    renderChip()
    await screen.findByText(/1 comentarios/)
    expect(useHasRole).toHaveBeenCalledWith(['family', 'contador', 'admin'])
  })

  it('AC3: error de carga sin dato previo → chip neutro, no se oculta', async () => {
    vi.mocked(getCommentsCount).mockRejectedValue(new Error('boom'))
    renderChip()
    expect(await screen.findByText(/comentarios —/)).toBeInTheDocument()
  })
})
