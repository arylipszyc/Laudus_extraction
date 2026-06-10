import { api } from './api'

/** Descarga el reporte de gastos (.xlsx) para el rango dado. */
export async function downloadReporteGastos(start: string, end: string): Promise<void> {
  const url = `${api.baseUrl}/api/v1/reportes/gastos?start=${start}&end=${end}`
  const res = await fetch(url, { credentials: 'include' })
  if (!res.ok) throw new Error(`Error generando reporte (${res.status})`)
  const blob = await res.blob()
  const href = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = href
  link.download = `reporte_gastos_${start}_${end}.xlsx`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(href)
}
