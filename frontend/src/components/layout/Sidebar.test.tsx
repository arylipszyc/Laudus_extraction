import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from './Sidebar'
import type { UserRole } from '@/types'

// Mock auth hook so we can drive role per-test (Story 9.13 frontend gate AC4 + AC6/AC7/AC8)
vi.mock('@/hooks/useAuth', () => ({
  useAuth: vi.fn(),
}))

import { useAuth } from '@/hooks/useAuth'

const mockedUseAuth = vi.mocked(useAuth)

function renderSidebar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function setRole(role: UserRole | null) {
  // Cast minimal shape — Sidebar only reads `data` and `isLoading`.
  mockedUseAuth.mockReturnValue({
    data: role ? { email: `${role}@test.com`, role } : null,
    isLoading: false,
  // biome-ignore lint/suspicious/noExplicitAny: test stub
  } as any)
}

describe('<Sidebar /> RBAC gates (Story 9.13)', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  const dashboardLabels = [
    'Activos / Pasivos',
    'Ingresos / Gastos',
    'Estado de Resultado',
    'Variación Patrimonial',
  ]
  const contadorLabels = ['Cargar Cartola', 'Reconciliación']

  it('AC6: family ve dashboards pero NO items contador (cartola/reconciliación)', () => {
    setRole('family')
    renderSidebar()
    for (const label of dashboardLabels) expect(screen.getByText(label)).toBeInTheDocument()
    for (const label of contadorLabels) expect(screen.queryByText(label)).not.toBeInTheDocument()
  })

  it('AC7: contador ve dashboards y items contador', () => {
    setRole('contador')
    renderSidebar()
    for (const label of dashboardLabels) expect(screen.getByText(label)).toBeInTheDocument()
    for (const label of contadorLabels) expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('AC8: admin ve dashboards y items contador (hereda de contador)', () => {
    setRole('admin')
    renderSidebar()
    for (const label of dashboardLabels) expect(screen.getByText(label)).toBeInTheDocument()
    for (const label of contadorLabels) expect(screen.getByText(label)).toBeInTheDocument()
  })
})
