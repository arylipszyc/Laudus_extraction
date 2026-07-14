import { api, apiFetch } from './api'

/** Descarga un .xlsx desde `path` y dispara el guardado con `filename`. */
async function downloadXlsx(path: string, filename: string): Promise<void> {
  const url = `${api.baseUrl}${path}`
  // Generar el xlsx es legítimamente lento → timeout extendido.
  const res = await apiFetch(url, { credentials: 'include' }, { timeoutMs: 120_000 })
  if (!res.ok) throw new Error(`Error generando reporte (${res.status})`)
  const blob = await res.blob()
  const href = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = href
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(href)
}

/** Descarga el reporte de gastos de EAG (.xlsx) para el rango dado. */
export async function downloadReporteGastos(start: string, end: string): Promise<void> {
  await downloadXlsx(
    `/api/v1/reportes/gastos?start=${start}&end=${end}`,
    `reporte_gastos_${start}_${end}.xlsx`,
  )
}

/** Descarga el reporte del Fondo Común (RUT2 · FFCC/JAB) para el rango dado (Story 13.1). */
export async function downloadReporteFondoComun(start: string, end: string): Promise<void> {
  await downloadXlsx(
    `/api/v1/reportes/fondo-comun?start=${start}&end=${end}`,
    `reporte_fondo_comun_${start}_${end}.xlsx`,
  )
}
