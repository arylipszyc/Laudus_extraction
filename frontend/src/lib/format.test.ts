import { describe, it, expect } from 'vitest'
import { fmt } from './format'

const intl = (n: number, currency: string) =>
  new Intl.NumberFormat('es-CL', { style: 'currency', currency }).format(n)

describe('fmt compartido (fix 6c Fase 1)', () => {
  it('formatea una moneda válida (USD)', () => {
    expect(fmt(1234.5, 'USD')).toBe(intl(1234.5, 'USD'))
  })

  it("currency vacía '' cae a CLP sin tirar", () => {
    expect(() => fmt(1000, '')).not.toThrow()
    expect(fmt(1000, '')).toBe(intl(1000, 'CLP'))
  })

  it("currency malformada 'US$' cae a CLP sin tirar (antes: RangeError)", () => {
    expect(() => fmt(1000, 'US$')).not.toThrow()
    expect(fmt(1000, 'US$')).toBe(intl(1000, 'CLP'))
  })

  it("código válido en minúsculas 'usd' se normaliza a USD (no se re-etiqueta CLP)", () => {
    expect(fmt(1000, 'usd')).toBe(intl(1000, 'USD'))
  })

  it('null/undefined → em-dash', () => {
    expect(fmt(null)).toBe('—')
    expect(fmt(undefined)).toBe('—')
  })

  it('sin currency → CLP', () => {
    expect(fmt(5000)).toBe(intl(5000, 'CLP'))
  })
})
