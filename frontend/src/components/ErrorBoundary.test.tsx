import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ErrorBoundary } from './ErrorBoundary'

function Bomb(): never {
  throw new Error('boom de prueba')
}

describe('<ErrorBoundary /> (fix 6b Fase 1)', () => {
  beforeEach(() => {
    // React y el propio boundary loguean el error atrapado — silenciarlo en el test.
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('un hijo que tira → fallback en vez de pantalla blanca', () => {
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    )
    expect(screen.getByText('Algo salió mal')).toBeInTheDocument()
    expect(screen.getByText('boom de prueba')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Recargar página' })).toBeInTheDocument()
  })

  it('sin error renderiza los hijos', () => {
    render(
      <ErrorBoundary>
        <p>contenido sano</p>
      </ErrorBoundary>,
    )
    expect(screen.getByText('contenido sano')).toBeInTheDocument()
    expect(screen.queryByText('Algo salió mal')).not.toBeInTheDocument()
  })
})
