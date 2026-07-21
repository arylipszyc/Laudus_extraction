/**
 * fmt de moneda compartido (fix 6c Fase 1) — valida la moneda antes de pasarla a Intl:
 * una currency malformada desde extracción (''/'US$') caía en RangeError. Fallback CLP.
 */
export function fmt(n: number | null | undefined, currency?: string | null): string {
  if (n == null) return '—'
  // Un código válido en minúsculas ('usd') es moneda real, no basura: normalizar
  // en vez de re-etiquetarlo como CLP.
  const cur = currency && /^[A-Za-z]{3}$/.test(currency) ? currency.toUpperCase() : 'CLP'
  return new Intl.NumberFormat('es-CL', { style: 'currency', currency: cur }).format(n)
}

/**
 * Formatea un número SIN símbolo de moneda. CLP no lleva decimales (no tienen sentido
 * para pesos); el resto (USD, etc.) lleva 2. Fallback CLP para códigos malformados.
 */
export function fmtNum(n: number | null | undefined, currency?: string | null): string {
  if (n == null) return '—'
  const cur = currency && /^[A-Za-z]{3}$/.test(currency) ? currency.toUpperCase() : 'CLP'
  const digits = cur === 'CLP' ? 0 : 2
  return new Intl.NumberFormat('es-CL', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n)
}
