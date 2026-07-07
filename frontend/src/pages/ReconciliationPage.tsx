import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  ACTIONS_BY_STATE,
  getDiscrepancies,
  getHistory,
  getPeriods,
  resolveDiscrepancy,
  ResolveHttpError,
  type Discrepancy,
  type HistoryEntry,
  type PeriodStatus,
} from '@/services/reconciliation'
import { listBankAccounts, type BankAccount } from '@/services/bankAccounts'
import { CategoryAutocomplete as AccountCombobox } from '@/components/CategoryAutocomplete'
import { fmt } from '@/lib/format'

const bankLabel = (b: BankAccount) => b.account_name || b.bank_name || b.account_number || b.id

/** Story 9.12 + 6.4 — dashboard de reconciliación cartola ↔ Laudus. */
export function ReconciliationPage() {
  const [searchParams] = useSearchParams()
  const deepLinkId = searchParams.get('discrepancy_id')
  const [stateFilter, setStateFilter] = useState<string | null>(null)
  const [monthFilter, setMonthFilter] = useState('')
  const [bankFilter, setBankFilter] = useState('')
  const [manualSelected, setManualSelected] = useState<Discrepancy | null>(null)
  const [deepLinkDismissed, setDeepLinkDismissed] = useState(false)
  const qc = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['reconciliation', stateFilter, monthFilter, bankFilter, deepLinkId],
    queryFn: () => getDiscrepancies({
      state: stateFilter ?? undefined,
      year_month: monthFilter || undefined,
      bank_account_id: bankFilter || undefined,
      discrepancy_id: deepLinkId ?? undefined,
    }),
  })

  const { data: bankAccounts = [] } = useQuery({ queryKey: ['bank-accounts'], queryFn: listBankAccounts })
  const bankNameById = useMemo(
    () => Object.fromEntries(bankAccounts.map((b) => [b.id, bankLabel(b)])),
    [bankAccounts],
  )

  // Deep-link: el drill-down se DERIVA del estado (sin effect ni ref → no reabre al resolver, AC4).
  // El bug viejo usaba `!selected` en el render, que reabría porque el backend sigue devolviendo el
  // item por el branch de `discrepancy_id`. Acá, al cerrar/resolver se marca `deepLinkDismissed` y no
  // vuelve a abrirse; una selección manual siempre tiene prioridad.
  const deepLinkMatch = deepLinkId && !deepLinkDismissed
    ? data?.discrepancies.find((d) => d.discrepancy_id === deepLinkId) ?? null
    : null
  const selected = manualSelected ?? deepLinkMatch
  // Cierra lo que está abierto. Solo descarta el deep-link si lo que se cierra/resuelve ES el item
  // del deep-link (así no se reabre, AC4) — cerrar OTRA fila no debe matar un deep-link no tocado.
  const closeSelected = () => {
    if (selected && selected.discrepancy_id === deepLinkId) setDeepLinkDismissed(true)
    setManualSelected(null)
  }

  const hasFilters = stateFilter !== null || monthFilter !== '' || bankFilter !== ''
  const clearFilters = () => { setStateFilter(null); setMonthFilter(''); setBankFilter('') }

  return (
    <div className="p-6 space-y-6 max-w-6xl">
      <h1 className="text-2xl font-semibold">Reconciliación cartola ↔ Laudus</h1>
      <p className="text-sm text-muted-foreground">
        Diferencias entre lo extraído de la cartola y lo registrado en Laudus, para revisar y resolver.
      </p>

      {/* Períodos reconciliados (Story 6.5 AC6) */}
      <PeriodsCard
        bankNameById={bankNameById}
        onPick={(bankId, month) => { setBankFilter(bankId); setMonthFilter(month) }}
      />

      {/* Filtros (AC3) */}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-1">
          <span className="text-xs text-muted-foreground">Mes</span>
          <input type="month" value={monthFilter} onChange={(e) => setMonthFilter(e.target.value)}
            className="border rounded-md px-2 py-1 bg-background text-sm" />
        </label>
        <label className="flex items-center gap-1">
          <span className="text-xs text-muted-foreground">Cuenta</span>
          <select value={bankFilter} onChange={(e) => setBankFilter(e.target.value)}
            className="border rounded-md px-2 py-1 bg-background text-sm">
            <option value="">Todas las cuentas</option>
            {bankAccounts.map((b) => <option key={b.id} value={b.id}>{bankLabel(b)}</option>)}
          </select>
        </label>
        {hasFilters && (
          <button onClick={clearFilters} className="text-xs text-muted-foreground underline">Limpiar filtros</button>
        )}
      </div>

      {/* Chips de estado */}
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
        <Card className="p-6 space-y-3">
          <p className="text-sm text-muted-foreground">
            {hasFilters ? 'No hay diferencias para este filtro.' : 'No hay diferencias para revisar. 🎉'}
          </p>
          {hasFilters && <Button size="sm" variant="outline" onClick={clearFilters}>Limpiar filtros</Button>}
        </Card>
      )}

      {data && data.discrepancies.length > 0 && (
        <Card className="p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="p-2">Fecha</th><th className="p-2">Estado</th><th className="p-2">Cuenta</th>
                <th className="p-2 text-right">Cartola</th><th className="p-2 text-right">Laudus</th>
                <th className="p-2">Descripción</th><th className="p-2">FX dev%</th><th className="p-2" />
              </tr>
            </thead>
            <tbody>
              {data.discrepancies.map((d) => (
                <tr key={d.discrepancy_id} className="border-b hover:bg-accent/40">
                  <td className="p-2">{d.cartola?.date ?? d.laudus?.date ?? '—'}</td>
                  <td className="p-2"><StateBadge state={d.state} /></td>
                  <td className="p-2 text-xs">{d.bank_account_id ? (bankNameById[d.bank_account_id] ?? d.bank_account_id) : '—'}</td>
                  <td className="p-2 text-right font-mono">{fmt(d.cartola?.amount, d.cartola?.currency)}</td>
                  <td className="p-2 text-right font-mono">{fmt(d.laudus?.amount, d.laudus?.currency)}</td>
                  <td className="p-2">{d.cartola?.description ?? d.laudus?.description ?? '—'}</td>
                  <td className="p-2">{d.fx.deviation_pct != null ? `${d.fx.deviation_pct}%` : '—'}</td>
                  <td className="p-2"><Button size="sm" variant="outline" onClick={() => setManualSelected(d)}>Revisar</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {selected && (
        <DrillDown
          discrepancy={selected}
          accountLabel={selected.bank_account_id ? (bankNameById[selected.bank_account_id] ?? null) : null}
          onClose={closeSelected}
          onResolved={() => {
            closeSelected()
            qc.invalidateQueries({ queryKey: ['reconciliation'] })
            qc.invalidateQueries({ queryKey: ['reconciliation-count'] })
          }}
        />
      )}
    </div>
  )
}

/** Story 6.5 — indicador de períodos reconciliados (cuenta, mes, fecha, estado). */
function PeriodsCard({ bankNameById, onPick }: {
  bankNameById: Record<string, string>
  onPick: (bankId: string, month: string) => void
}) {
  const { data: periods = [], isLoading } = useQuery({
    queryKey: ['reconciliation-periods'],
    queryFn: getPeriods,
  })

  if (isLoading) return <Skeleton className="h-20 w-full" />
  if (periods.length === 0) return null

  return (
    <Card className="p-4 space-y-2">
      <p className="text-sm font-medium">Períodos reconciliados</p>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="p-1.5">Cuenta</th><th className="p-1.5">Mes</th>
            <th className="p-1.5">Reconciliado</th><th className="p-1.5">Estado</th>
          </tr>
        </thead>
        <tbody>
          {periods.map((p: PeriodStatus) => {
            const pickable = p.status === 'pending' && p.bank_account_id != null
            return (
              <tr key={`${p.bank_account_id}-${p.year_month}`}
                className={`border-b last:border-0 ${pickable ? 'cursor-pointer hover:bg-accent/40' : ''}`}
                onClick={pickable ? () => onPick(p.bank_account_id!, p.year_month) : undefined}>
                <td className="p-1.5">{p.bank_account_id ? (bankNameById[p.bank_account_id] ?? p.bank_account_id) : '—'}</td>
                <td className="p-1.5">{p.year_month}</td>
                <td className="p-1.5 text-muted-foreground">{p.reconciled_at ? p.reconciled_at.slice(0, 10) : '—'}</td>
                <td className="p-1.5"><PeriodBadge status={p.status} open={p.open} /></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </Card>
  )
}

function PeriodBadge({ status, open }: { status: string; open: number }) {
  if (status === 'complete') {
    return <span className="px-2 py-0.5 rounded-sm text-xs bg-green-50 text-green-700">✓ Completo</span>
  }
  return (
    <span className="px-2 py-0.5 rounded-sm text-xs bg-amber-50 text-amber-600">
      {open} pendiente{open === 1 ? '' : 's'}
    </span>
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

const ACTION_LABEL: Record<string, string> = {
  'confirm-cartola-only': 'Confirmada como gasto',
  'confirm-laudus-only': 'Confirmada (Laudus)',
  escalate: 'Escalada',
}
const actionLabel = (a: string) => ACTION_LABEL[a] ?? a

function DrillDown({ discrepancy, accountLabel, onClose, onResolved }: {
  discrepancy: Discrepancy; accountLabel: string | null; onClose: () => void; onResolved: () => void
}) {
  const actions = ACTIONS_BY_STATE[discrepancy.state] ?? ['escalate']
  const [action, setAction] = useState(actions[0])
  const [justification, setJustification] = useState('')
  const [category, setCategory] = useState('')
  const [success, setSuccess] = useState<string | null>(null)

  const annotates = discrepancy.state === 'missing-in-laudus' && action === 'confirm-cartola-only'

  const mutation = useMutation({
    mutationFn: () => resolveDiscrepancy(discrepancy.discrepancy_id, {
      action,
      justification: action === 'escalate' ? null : justification,
      category_account: annotates ? (category.trim() || null) : undefined,
    }),
    onSuccess: (res) => {
      setSuccess(res.git_commit_sha
        ? `✓ Gasto anotado en el ledger (${res.git_commit_sha.slice(0, 7)}).`
        : '✓ Diferencia resuelta.')
      setTimeout(onResolved, 1500)
    },
  })

  const needsJustification = action !== 'escalate'
  const canConfirm = !mutation.isPending && !success && (!needsJustification || justification.trim().length >= 10)

  const err = mutation.error
  const is422 = err instanceof ResolveHttpError && err.status === 422

  return (
    <Card className="p-6 space-y-4 fixed right-4 top-4 bottom-4 w-[420px] overflow-y-auto shadow-xl z-50 bg-card">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-lg font-semibold">Detalle</h2>
          {accountLabel && <p className="text-xs text-muted-foreground">{accountLabel} · {discrepancy.year_month}</p>}
        </div>
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

        {annotates && <CategoryAutocomplete value={category} onChange={setCategory} />}

        {needsJustification && (
          <textarea value={justification} onChange={(e) => setJustification(e.target.value)} rows={3}
            placeholder="Justificación (≥10 caracteres)"
            className="w-full border rounded-md px-3 py-2 bg-background text-sm" />
        )}

        {success && <p className="text-sm rounded-md px-3 py-2 bg-green-50 text-green-700">{success}</p>}
        {err && !success && (
          <div className="text-sm rounded-md px-3 py-2 bg-red-50 text-red-600">
            <p>{(err as Error).message}</p>
            {is422 && <p className="font-medium mt-1">La diferencia sigue ABIERTA — no se contabilizó.</p>}
          </div>
        )}

        {!success && (
          <Button onClick={() => mutation.mutate()} disabled={!canConfirm}>
            {mutation.isPending ? (annotates ? 'Anotando…' : 'Confirmando…') : 'Confirmar acción'}
          </Button>
        )}
      </div>

      <HistoryPanel discrepancyId={discrepancy.discrepancy_id} createdTs={discrepancy.ts} state={discrepancy.state} />
    </Card>
  )
}

/** Autocompletado de cuenta de categoría (Expenses) para confirm-cartola-only (AC1). */
function CategoryAutocomplete({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1">Categoría del gasto (opcional)</label>
      <AccountCombobox value={value} onChange={onChange} />
      <p className="text-xs text-muted-foreground mt-1">
        Si lo dejás vacío, el gasto entra como pendiente y lo categorizás después en Categorización.
      </p>
    </div>
  )
}

/** Historial de la discrepancia: original + resoluciones (AC2). */
function HistoryPanel({ discrepancyId, createdTs, state }: { discrepancyId: string; createdTs: string; state: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['reconciliation-history', discrepancyId],
    queryFn: () => getHistory(discrepancyId),
  })

  const resolutions = (data?.entries ?? []).filter((e: HistoryEntry) => e.ref_discrepancy_id && e.resolution)

  return (
    <div className="border-t pt-4 space-y-2">
      <p className="text-sm font-medium">Historial</p>
      {isLoading && <Skeleton className="h-16 w-full" />}
      {!isLoading && (
        <ol className="space-y-3 text-xs">
          <li className="flex gap-2">
            <span className="mt-1 h-2 w-2 rounded-full bg-muted-foreground shrink-0" />
            <div><p>Detectada · estado <span className="font-mono">{state}</span></p>
              <p className="text-muted-foreground">{createdTs}</p></div>
          </li>
          {resolutions.map((e: HistoryEntry, i: number) => {
            const r = e.resolution!
            const escalated = r.action === 'escalate'
            return (
              <li key={i} className="flex gap-2">
                <span className={`mt-1 h-2 w-2 rounded-full shrink-0 ${escalated ? 'bg-amber-500' : 'bg-green-500'}`} />
                <div>
                  <p className="font-medium">{actionLabel(r.action)}</p>
                  <p className="text-muted-foreground">{r.resolved_by ?? '—'} · {r.resolved_at ?? r.escalated_at ?? ''}</p>
                  {r.justification && <p className="italic line-clamp-2">{r.justification}</p>}
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </div>
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
