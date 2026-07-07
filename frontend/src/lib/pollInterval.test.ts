import { describe, it, expect } from 'vitest'
import { errorAwareInterval } from './pollInterval'

const query = (status: 'pending' | 'error' | 'success', fetchFailureCount = 0) => ({
  state: { status, fetchFailureCount },
})

describe('errorAwareInterval — polls error-aware (Fase 3 F8)', () => {
  it('éxito → cadencia base', () => {
    expect(errorAwareInterval(60_000)(query('success'))).toBe(60_000)
  })

  it('error → ×4', () => {
    expect(errorAwareInterval(60_000)(query('error'))).toBe(240_000)
  })

  it('reintentos fallando (fetchFailureCount > 0) también estiran, aunque status siga success', () => {
    expect(errorAwareInterval(60_000)(query('success', 2))).toBe(240_000)
  })

  it('×4 con tope default 10 min', () => {
    expect(errorAwareInterval(5 * 60 * 1000)(query('error'))).toBe(600_000)
  })

  it('tope configurable via maxMs', () => {
    expect(errorAwareInterval(60_000, { maxMs: 120_000 })(query('error'))).toBe(120_000)
  })

  it('al primer éxito vuelve la cadencia normal', () => {
    const interval = errorAwareInterval(5_000)
    expect(interval(query('error'))).toBe(20_000)
    expect(interval(query('success'))).toBe(5_000)
  })
})
