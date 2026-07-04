import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { getTcReconciliation, type TcReconciliationRow } from '@/services/tcReconciliation'
import { listBankAccounts, type BankAccount } from '@/services/bankAccounts'

const fmt = (n: number | null | undefined, c?: string | null) => {
  if (n == null) return '—'
  const cur = c && /^[A-Z]{3}$/.test(c) ? c : 'CLP'
  return new Intl.NumberFormat('es-CL', { style: 'currency', currency: cur }).format(n)
}

const bankLabel = (b: BankAccount) => b.account_name || b.bank_name || b.account_number || b.id

// Semáforo de un chequeo: verde si pasa; si falla, rojo (crítico C1/C3) o amarillo (C2/C4/C5).
const dot = (ok: boolean, critical: boolean) => (ok ? '🟢' : critical ? '🔴' : '🟡')
const STATUS_WEIGHT: Record<string, number> = { red: 0, yellow: 1, green: 2 }

/** Story 6.6 — vista de cuadre TC (C1–C5) por tarjeta × mes. Read-only. */
export function TcReconciliationPage() {
  const [card, setCard] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)

  const { data: banks } = useQuery({ queryKey: ['bank-accounts'], queryFn: listBankAccounts })
  const tcCards = useMemo(
    () => (banks ?? []).filter((b) => b.account_type === 'tarjeta_credito'),
    [banks],
  )
  const selectedCard = card || tcCards[0]?.id || ''

  const { data, isLoading, error } = useQuery({
    queryKey: ['tc-reconciliation', selectedCard],
    queryFn: () => getTcReconciliation(selectedCard),
    enabled: !!selectedCard,
  })

  // Rojos arriba (spec §UI): ordena por status y, dentro, mes descendente (el backend ya viene desc).
  const rows = useMemo(
    () => [...(data ?? [])].sort((a, b) => (STATUS_WEIGHT[a.status] ?? 99) - (STATUS_WEIGHT[b.status] ?? 99)),
    [data],
  )

  return (
    <div className="p-6 space-y-4 max-w-5xl">
      <div>
        <h1 className="text-xl font-semibold">Cuadre de tarjetas de crédito</h1>
        <p className="text-sm text-muted-foreground">
          ¿La deuda de cada tarjeta en la contabilidad coincide con lo que dice la cartola? Un mes está
          🟢 cuando pasan los cinco chequeos. C1 y C3 (🔴) son críticos.
        </p>
      </div>

      <div className="flex items-center gap-2">
        <label htmlFor="tc-card" className="text-sm text-muted-foreground">Tarjeta</label>
        <select
          id="tc-card"
          className="border rounded-md px-2 py-1 text-sm bg-background"
          value={selectedCard}
          onChange={(e) => { setCard(e.target.value); setExpanded(null) }}
        >
          {tcCards.length === 0 && <option value="">— sin tarjetas —</option>}
          {tcCards.map((b) => (
            <option key={b.id} value={b.id}>{bankLabel(b)}</option>
          ))}
        </select>
      </div>

      {isLoading && <Skeleton className="h-40 w-full" />}
      {error && <p className="text-sm text-red-600">Error cargando el cuadre.</p>}
      {data && rows.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Esta tarjeta no tiene cartolas importadas todavía.
        </p>
      )}

      {rows.length > 0 && (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Mes</th>
                {['C1', 'C2', 'C3', 'C4', 'C5'].map((c) => (
                  <th key={c} className="px-2 py-2 font-medium" title={CHECK_TITLES[c]}>{c}</th>
                ))}
                <th className="text-right px-3 py-2 font-medium">Deuda TC:Real</th>
                <th className="text-right px-3 py-2 font-medium">Cierre cartola</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <TcRow
                  key={r.year_month}
                  r={r}
                  open={expanded === r.year_month}
                  onToggle={() => setExpanded(expanded === r.year_month ? null : r.year_month)}
                />
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}

const CHECK_TITLES: Record<string, string> = {
  C1: 'Invariante de cierre: TC:Real al cierre == −cierre de la cartola',
  C2: 'Contigüidad: apertura del mes == cierre del mes anterior',
  C3: 'Integridad del asiento: toda compra/cuota conserva su pata de deuda TC:Real',
  C4: 'Pago vs Laudus: el pago de la cartola concilia con el banco',
  C5: 'Lump residual: el gasto lumpeado del mes quedó neteado (≈0)',
}

function TcRow({ r, open, onToggle }: { r: TcReconciliationRow; open: boolean; onToggle: () => void }) {
  return (
    <>
      <tr className="border-t cursor-pointer hover:bg-muted/30" onClick={onToggle}>
        <td className="px-3 py-2 font-mono">{r.year_month}</td>
        <td className="text-center">{dot(r.c1_ok, true)}</td>
        <td className="text-center">{dot(r.c2_ok, false)}</td>
        <td className="text-center">{dot(r.c3_ok, true)}</td>
        <td className="text-center">{dot(r.pago_ok, false)}</td>
        <td className="text-center">{dot(r.c5_ok, false)}</td>
        <td className="px-3 py-2 text-right font-mono">{fmt(r.tc_real_balance)}</td>
        <td className="px-3 py-2 text-right font-mono">
          {fmt(r.closing, r.currency)}
          {r.currency !== 'CLP' && (
            <span className="text-muted-foreground"> ({fmt(r.closing_clp)})</span>
          )}
        </td>
      </tr>
      {open && (
        <tr className="bg-muted/20">
          <td colSpan={8} className="px-4 py-3 space-y-3">
            {!r.c1_ok && (
              <p className="text-xs text-red-600">
                🔴 C1: la deuda TC:Real ({fmt(r.tc_real_balance)}) no coincide con −cierre
                ({fmt(-r.closing_clp)}). La cartola no está bien materializada.
              </p>
            )}
            {!r.c3_ok && (
              <p className="text-xs text-red-600">
                🔴 C3: {r.c3_corrupted_count} asiento(s) de compra/cuota sin su pata de deuda TC:Real
                (posible corrupción de categorización).
              </p>
            )}
            {!r.c2_ok && (
              <p className="text-xs text-amber-600">
                🟡 C2: {r.c2_reason ?? `apertura ${fmt(r.opening, r.currency)} ≠ cierre anterior ${fmt(r.c2_prior_closing, r.currency)}`}.
              </p>
            )}
            {!r.c5_ok && (
              <p className="text-xs text-amber-600">
                🟡 C5: el lump del mes quedó con residual {fmt(r.c5_residual)} (gasto sin desglosar).
              </p>
            )}

            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">
                Movimientos de la cartola (compras {fmt(r.sum_compras)} · pagos {fmt(r.sum_pagos)} · cargos {fmt(r.sum_cargos)})
              </p>
              {r.movements.length === 0 && <p className="text-xs text-muted-foreground">— sin movimientos —</p>}
              {r.movements.map((m, i) => (
                <div key={i} className="text-xs grid grid-cols-[5rem_1fr_auto] gap-2">
                  <span className="font-mono text-muted-foreground">{m.date}</span>
                  <span className="truncate">{m.operation_type} · {m.narration}</span>
                  <span className="font-mono text-right">{fmt(m.amount)}</span>
                </div>
              ))}
            </div>

            {r.laudus_payments.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">Pago(s) registrado(s) por Laudus</p>
                {r.laudus_payments.map((p, i) => (
                  <div key={i} className="text-xs bg-muted rounded p-2">
                    <span className="font-mono">{p.date}</span> · {p.narration} ·{' '}
                    <span className="font-mono">{fmt(p.amount)}</span>
                    {p.bank_account && <span className="text-muted-foreground"> · {p.bank_account}</span>}
                  </div>
                ))}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}
