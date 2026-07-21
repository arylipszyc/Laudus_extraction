import { afterEach, describe, expect, it, vi } from 'vitest'
import { favaEditorUrl } from './fava'

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('favaEditorUrl', () => {
  it('builds the editor URL with the Fava-absolute file_path and line', () => {
    vi.stubEnv('VITE_FAVA_URL', 'https://laudus-fava.onrender.com')
    const url = favaEditorUrl('ledger/imports/laudus/2026-06.beancount', 5624)
    const parsed = new URL(url!)
    expect(parsed.origin).toBe('https://laudus-fava.onrender.com')
    expect(parsed.pathname).toBe('/laudus-eag-family-office/editor/')
    // Fava valida file_path contra options["include"] (absoluto del clon /ledger).
    expect(parsed.searchParams.get('file_path')).toBe('/ledger/ledger/imports/laudus/2026-06.beancount')
    expect(parsed.searchParams.get('line')).toBe('5624')
  })

  it('tolerates a trailing slash in VITE_FAVA_URL', () => {
    vi.stubEnv('VITE_FAVA_URL', 'https://laudus-fava.onrender.com/')
    const url = favaEditorUrl('ledger/manual/ajustes.beancount', 12)
    expect(url).toBe(
      'https://laudus-fava.onrender.com/laudus-eag-family-office/editor/?file_path=%2Fledger%2Fledger%2Fmanual%2Fajustes.beancount&line=12',
    )
  })

  it('returns null when config is missing (fail-safe → no affordance)', () => {
    vi.stubEnv('VITE_FAVA_URL', '')
    expect(favaEditorUrl('ledger/x.beancount', 1)).toBeNull()
  })

  it('returns null when filename or lineno is absent', () => {
    vi.stubEnv('VITE_FAVA_URL', 'https://laudus-fava.onrender.com')
    expect(favaEditorUrl(null, 5)).toBeNull()
    expect(favaEditorUrl('ledger/x.beancount', null)).toBeNull()
    expect(favaEditorUrl('ledger/x.beancount', undefined)).toBeNull()
  })
})
