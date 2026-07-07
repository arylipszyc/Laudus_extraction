import { describe, it, expect } from 'vitest'
import { shouldKeepPolling } from './useCartolaUpload'

describe('shouldKeepPolling (refetchInterval de useCartolaStatus)', () => {
  it('sigue polleando mientras el backend trabaja', () => {
    expect(shouldKeepPolling('processing')).toBe(true)
    expect(shouldKeepPolling('confirming')).toBe(true)
  })

  it('se detiene en los estados terminales (o sin data)', () => {
    expect(shouldKeepPolling('ready')).toBe(false)
    expect(shouldKeepPolling('failed')).toBe(false)
    expect(shouldKeepPolling('confirmed')).toBe(false)
    expect(shouldKeepPolling('confirm_failed')).toBe(false)
    expect(shouldKeepPolling(undefined)).toBe(false)
  })
})
