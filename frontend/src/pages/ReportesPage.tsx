import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useSyncStatus } from '@/hooks/useSyncStatus'
import { triggerSync } from '@/services/sync'
import { downloadReporteFondoComun, downloadReporteGastos } from '@/services/reportes'

type Libro = 'EAG' | 'FondoComun'

export function ReportesPage() {
  const [start, setStart] = useState('2025-01-01')
  const [end, setEnd] = useState('2025-12-31')
  const [libro, setLibro] = useState<Libro>('EAG')
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { data: sync } = useSyncStatus()
  const qc = useQueryClient()

  const running = sync?.job_status === 'running'
  const invalidRange = start > end
  const lastSync = sync?.ledger?.last_sync
    ? new Date(sync.ledger.last_sync).toLocaleDateString('es-CL')
    : '—'

  async function onGenerar() {
    setError(null)
    setDownloading(true)
    try {
      if (libro === 'FondoComun') {
        await downloadReporteFondoComun(start, end)
      } else {
        await downloadReporteGastos(start, end)
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setDownloading(false)
    }
  }

  async function onSync() {
    setError(null)
    try {
      await triggerSync('normal')
      qc.invalidateQueries({ queryKey: ['sync', 'status'] })
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-2xl">
      <h1 className="text-2xl font-semibold">Reportes</h1>

      <Card className="p-6 space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">Libro</label>
          <select
            value={libro}
            onChange={(e) => setLibro(e.target.value as Libro)}
            className="w-full border rounded-md px-3 py-2 bg-background"
          >
            <option value="EAG">EAG</option>
            <option value="FondoComun">Fondo Común (FFCC / JAB)</option>
          </select>
        </div>

        <div className="flex gap-4">
          <div className="flex-1">
            <label className="block text-sm font-medium mb-1">Desde</label>
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="w-full border rounded-md px-3 py-2 bg-background"
            />
          </div>
          <div className="flex-1">
            <label className="block text-sm font-medium mb-1">Hasta</label>
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="w-full border rounded-md px-3 py-2 bg-background"
            />
          </div>
        </div>

        <div className="flex gap-3">
          <Button onClick={onGenerar} disabled={downloading || invalidRange}>
            {downloading ? 'Generando…' : 'Generar y descargar'}
          </Button>
          <Button variant="outline" onClick={onSync} disabled={running}>
            {running ? 'Sincronizando…' : 'Sincronizar ahora'}
          </Button>
        </div>

        {invalidRange && (
          <p className="text-sm text-destructive">La fecha "Desde" debe ser anterior o igual a "Hasta".</p>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}

        <p className="text-sm text-muted-foreground">
          Datos de Laudus al: <strong>{lastSync}</strong>
          {running && <span className="text-blue-500"> · sincronizando con Laudus…</span>}
          {sync?.job_status === 'failed' && (
            <span className="text-destructive"> · error en la sincronización</span>
          )}
        </p>
      </Card>

      {libro === 'FondoComun' ? (
        <p className="text-sm text-muted-foreground">
          El reporte del Fondo Común trae dos hojas: <strong>Gastos</strong> (FFCC/JAB por
          encabezado) y <strong>Distribuciones</strong> (cuenta corriente de cada socio: retiros,
          repartos y saldo). Los saldos son fieles a Laudus. El balance del fondo está incompleto
          (inversiones y activos reales aún no cargados), por eso el reporte lleva una advertencia:
          no representa el patrimonio real del fondo.
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">
          El reporte trae lo que está en Laudus. Las celdas vacías —desglose de tarjeta de crédito y
          clasificación manual— las completa el contador; subtotales y totales son fórmulas que se
          recalculan solas.
        </p>
      )}
    </div>
  )
}
