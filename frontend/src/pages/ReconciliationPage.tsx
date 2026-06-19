import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  ACTIONS_BY_STATE,
  getDiscrepancies,
  resolveDiscrepancy,
  type Discrepancy,
} from '@/services/reconciliation'

const fmt = (n: number | null | undefined, c = 'CLP') =>
  n == null ? '—' : new Intl.NumberFormat('es-CL', { style: 'currency', currency: c }).format(n)

/** Story 9.12 — dashboard de reconciliación cartola ↔ Laudus. */
export function ReconciliationPage() {
  const [searchParams] = useSearchParams()
  const deepLinkId = searchParams.get('discrepancy_id')
  const [stateFilter, setStateFilter] = useState<string | null>(null)
  const [selected, setSelected] = useState<Discrepancy | null>(null)
  const qc = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['reconciliation', stateFilter, deepLinkId],
    queryFn: () => getDiscrepancies({ state: stateFilter ?? undefined, discrepancy_id: deepLinkId ?? undefined }),
  })

  // Deep-link: abrir el drill-down automáticamente al cargar (AC5).
  if (deepLinkId && !selected && data?.discrepancies.length) {
    const match = data.discrepancies.find((d) => d.discrepancy_id === deepLinkId)
    if (match) setSelected(match)
  }

  return (
    <div className="p-6 space-y-6 max-w-6xl">
      <h1 className="text-2xl font-semibold">Reconciliación cartola ↔ Laudus</h1>
      <p className="text-sm text-muted-foreground">
        Diferencias entre lo extraído de la cartola y lo registrado en Laudus, para revisar y resolver.
      </p>

      {data && (
        <div className="flex flex-wrap gap-2">
          <Chip label={`Todas: ${data.summary.total}`} active={stateFilter === null}
                onClick={() => setStateFilter(null)} />
          {Object.entries(data.summary.by_state).map(([st, n]) => (
            <Chip key={st} label={`${st}: ${n}`} active={stateFilter === st}
                  onClick={() => setStateFilter(st)} />
          ))}
        </div>
      )}

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error && <p className="text-sm text-destructive">{(error as Error).message}</p>}
      {data && data.discrepancies.length === 0 && (
        <Card className="p-6"><p className="text-sm text-muted-foreground">No hay diferencias para revisar. 🎉</p></Card>
      )}

      {data && data.discrepancies.length > 0 && (
        <Card className="p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="p-2">Fecha</th><th className="p-2">Estado</th>
                <th className="p-2 text-right">Cartola</th><th className="p-2 text-right">Laudus</th>
                <th className="p-2">Descripción</th><th className="p-2">FX dev%</th><th className="p-2" />
              </tr>
            </thead>
            <tbody>
              {data.discrepancies.map((d) => (
                <tr key={d.discrepancy_id} className="border-b hover:bg-accent/40">
                  <td className="p-2">{d.cartola?.date ?? d.laudus?.date ?? '—'}</td>
                  <td className="p-2"><StateBadge state={d.state} /></td>
                  <td className="p-2 text-right font-mono">{fmt(d.cartola?.amount, d.cartola?.currency)}</td>
                  <td className="p-2 text-right font-mono">{fmt(d.laudus?.amount)}</td>
                  <td className="p-2">{d.cartola?.description ?? d.laudus?.description ?? '—'}</td>
                  <td className="p-2">{d.fx.deviation_pct != null ? `${d.fx.deviation_pct}%` : '—'}</td>
                  <td className="p-2"><Button size="sm" variant="outline" onClick={() => setSelected(d)}>Revisar</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {selected && (
        <DrillDown
          discrepancy={selected}
          onClose={() => setSelected(null)}
          onResolved={() => {
            setSelected(null)
            qc.invalidateQueries({ queryKey: ['reconciliation'] })
            qc.invalidateQueries({ queryKey: ['reconciliation-count'] })
          }}
        />
      )}
    </div>
  )
}

function StateBadge({ state }: { state: string }) {
  const blocking = state === 'value-mismatch' || state === 'fx-out-of-tolerance'
  return (
    <span className={`px-2 py-0.5 rounded-sm text-xs ${blocking ? 'bg-red-50 text-red-600' : 'bg-amber-50 text-amber-600'}`}>
      {state}
    </span>
  )
}

function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={`px-3 py-1 rounded-full text-xs border ${active ? 'bg-primary text-primary-foreground' : 'bg-background'}`}>
      {label}
    </button>
  )
}

function DrillDown({ discrepancy, onClose, onResolved }: {
  discrepancy: Discrepancy; onClose: () => void; onResolved: () => void
}) {
  const actions = ACTIONS_BY_STATE[discrepancy.state] ?? ['escalate']
  const [action, setAction] = useState(actions[0])
  const [justification, setJustification] = useState('')

  const mutation = useMutation({
    mutationFn: () => resolveDiscrepancy(discrepancy.discrepancy_id, {
      action, justification: action === 'escalate' ? null : justification,
    }),
    onSuccess: onResolved,
  })

  const needsJustification = action !== 'escalate'
  const canConfirm = !mutation.isPending && (!needsJustification || justification.trim().length >= 10)

  return (
    <Card className="p-6 space-y-4 fixed right-4 top-4 bottom-4 w-[420px] overflow-y-auto shadow-xl z-50 bg-card">
      <div className="flex justify-between items-start">
        <h2 className="text-lg font-semibold">Detalle</h2>
        <Button size="sm" variant="ghost" onClick={onClose}>✕</Button>
      </div>
      <StateBadge state={discrepancy.state} />

      <Section title="Cartola" obj={discrepancy.cartola} />
      <Section title="Laudus" obj={discrepancy.laudus} />
      {discrepancy.fx.implied != null && (
        <div className="text-sm">
          <p className="font-medium">FX</p>
          <p>implícita: {discrepancy.fx.implied} · BCCh: {discrepancy.fx.bcch ?? '—'} · dev: {discrepancy.fx.deviation_pct ?? '—'}%</p>
        </div>
      )}

      <div className="space-y-2">
        <label className="block text-sm font-medium">Acción</label>
        <select value={action} onChange={(e) => setAction(e.target.value)}
          className="w-full border rounded-md px-3 py-2 bg-background text-sm">
          {actions.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        {needsJustification && (
          <textarea value={justification} onChange={(e) => setJustification(e.target.value)} rows={3}
            placeholder="Justificación (≥10 caracteres)"
            className="w-full border rounded-md px-3 py-2 bg-background text-sm" />
        )}
        {mutation.error && <p className="text-sm text-destructive">{(mutation.error as Error).message}</p>}
        <Button onClick={() => mutation.mutate()} disabled={!canConfirm}>
          {mutation.isPending ? 'Confirmando…' : 'Confirmar acción'}
        </Button>
      </div>
    </Card>
  )
}

function Section({ title, obj }: { title: string; obj: Record<string, unknown> | null }) {
  if (!obj) return <div className="text-sm"><p className="font-medium">{title}</p><p className="text-muted-foreground">—</p></div>
  return (
    <div className="text-sm">
      <p className="font-medium">{title}</p>
      <dl className="grid grid-cols-2 gap-x-2">
        {Object.entries(obj).map(([k, v]) => (
          <div key={k} className="contents"><dt className="text-muted-foreground">{k}</dt><dd className="font-mono">{String(v)}</dd></div>
        ))}
      </dl>
    </div>
  )
}
