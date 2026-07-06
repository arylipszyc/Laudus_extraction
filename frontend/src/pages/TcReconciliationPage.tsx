import { Fragment, useMemo, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { getTcReconciliation, getTcCartolas, type TcReconciliationRow } from '@/services/tcReconciliation'
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
  const qc = useQueryClient()

  const { data: banks } = useQuery({ queryKey: ['bank-accounts'], queryFn: listBankAccounts })
  const tcCards = useMemo(
    () => (banks ?? []).filter((b) => b.account_type === 'tarjeta_credito'),
    [banks],
  )
  const selectedCard = card || tcCards[0]?.id || ''

  // Los datos cambian cuando el contador sube una cartola (fuera de esta página) → refetch en cada
  // visita y al volver el foco, y un botón manual. (El default global cachea 60s.)
  const { data, isLoading, error } = useQuery({
    queryKey: ['tc-reconciliation', selectedCard],
    queryFn: () => getTcReconciliation(selectedCard),
    enabled: !!selectedCard,
    staleTime: 0,
    refetchOnWindowFocus: true,
  })

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['tc-cartolas'] })
    qc.invalidateQueries({ queryKey: ['tc-reconciliation'] })
  }

  // Rojos arriba (spec §UI): ordena por status y, dentro, mes descendente (el backend ya viene desc).
  const rows = useMemo(
    () => [...(data ?? [])].sort((a, b) => (STATUS_WEIGHT[a.status] ?? 99) - (STATUS_WEIGHT[b.status] ?? 99)),
    [data],
  )

  return (
    <div className="p-6 space-y-4 max-w-5xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Cuadre de tarjetas de crédito</h1>
          <p className="text-sm text-muted-foreground">
            ¿La deuda de cada tarjeta en la contabilidad coincide con lo que dice la cartola? Un mes está
            🟢 cuando pasan los cinco chequeos. C1 y C3 (🔴) son críticos.
          </p>
        </div>
        <button
          onClick={refrescar}
          className="shrink-0 border rounded-md px-3 py-1 text-sm bg-background hover:bg-muted"
        >
          Actualizar
        </button>
      </div>

      <CoverageMatrix banks={banks} onSelect={(c) => { setCard(c); setExpanded(null) }} />

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
                {CHECKS.map((c) => (
                  <th key={c.code} className="px-2 py-2 font-medium" title={c.title}>{c.code}</th>
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

      <Card className="p-4 text-sm space-y-3">
        <p className="font-medium">Qué controla cada chequeo</p>
        {CHECKS.map((c) => (
          <div key={c.code}>
            <p>
              <span aria-hidden>{c.critical ? '🔴' : '🟡'}</span>{' '}
              <span className="font-mono">{c.code}</span> · {c.title}
            </p>
            <p className="text-muted-foreground pl-6">Compara {c.compara}</p>
            <p className="text-muted-foreground pl-6">
              <span aria-hidden>{c.critical ? '🔴' : '🟡'}</span> {c.color}
            </p>
          </div>
        ))}
        <p className="text-xs text-muted-foreground pt-1">
          🟢 pasa · 🟡 revisar el detalle (no crítico) · 🔴 crítico, parar y revisar. Un mes está verde cuando pasan los cinco.
        </p>
      </Card>
    </div>
  )
}

// Matriz de cobertura: tarjeta (fila) × mes (columna), estado por celda; vacío = falta subir.
function CoverageMatrix({ banks, onSelect }: {
  banks?: BankAccount[]; onSelect: (card: string) => void
}) {
  const { data } = useQuery({
    queryKey: ['tc-cartolas'], queryFn: getTcCartolas, staleTime: 0, refetchOnWindowFocus: true,
  })
  const cartolas = data ?? []
  if (cartolas.length === 0) return null
  const months = [...new Set(cartolas.map((c) => c.year_month))].sort()
  const cards = [...new Set(cartolas.map((c) => c.card))]
  const byKey = new Map(cartolas.map((c) => [`${c.card}|${c.year_month}`, c.status]))
  const label = (card: string) => {
    const b = banks?.find((x) => x.id === card)
    return b ? bankLabel(b) : card
  }
  const cell = (s?: string) => (s === 'green' ? '🟢' : s === 'yellow' ? '🟡' : s === 'red' ? '🔴' : '·')
  return (
    <div className="space-y-1">
      <p className="text-sm font-medium">Cartolas subidas</p>
      <Card className="overflow-x-auto">
        <table className="text-sm w-full">
          <thead className="bg-muted/50 text-muted-foreground">
            <tr>
              <th className="text-left px-3 py-2 font-medium">Tarjeta</th>
              {months.map((m) => <th key={m} className="px-2 py-2 font-medium font-mono">{m}</th>)}
            </tr>
          </thead>
          <tbody>
            {cards.map((card) => (
              <tr key={card} className="border-t cursor-pointer hover:bg-muted/30" onClick={() => onSelect(card)}>
                <td className="px-3 py-2">{label(card)}</td>
                {months.map((m) => (
                  <td key={m} className="text-center">{cell(byKey.get(`${card}|${m}`))}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <p className="text-xs text-muted-foreground">
        🟢 cuadra · 🟡 revisar · 🔴 descuadre crítico · · falta subir. Click en una tarjeta para ver el detalle.
      </p>
    </div>
  )
}

const CHECKS = [
  { code: 'C1', critical: true,
    title: 'Cuadre de la deuda — lo que la contabilidad dice que se debe vs. lo que dice el estado de cuenta.',
    compara: 'el saldo de la cuenta de la tarjeta en la contabilidad (acumulado al cierre del mes) con el saldo de cierre que trae la cartola.',
    color: 'no cuadran: una compra o un pago se cargó mal, o falta algo. Revisar.' },
  { code: 'C2', critical: false,
    title: 'Continuidad entre meses — que no falte ninguna cartola.',
    compara: 'la apertura de la cartola de este mes con el cierre de la del mes anterior (misma tarjeta).',
    color: 'no coinciden o falta el mes anterior: puede faltar una cartola. La primera siempre sale amarilla («sin cartola anterior»), es normal.' },
  { code: 'C3', critical: true,
    title: 'Compras con su deuda — que categorizar no borre la deuda de la tarjeta.',
    compara: 'los asientos de compra del mes en la contabilidad (que cada uno mantenga su registro de deuda).',
    color: 'a alguna compra se le borró la deuda: el saldo quedó más bajo que el real. Revisar.' },
  { code: 'C4', critical: false,
    title: 'Pago vs banco — que el pago de la cartola sea el que registró el banco.',
    compara: 'el pago que muestra la cartola con el pago que el banco registró en Laudus.',
    color: 'los montos no coinciden. Revisar el pago.' },
  { code: 'C5', critical: false,
    title: 'Gasto del mes saldado — que el gasto cargado en bloque se reemplace por las compras detalladas.',
    compara: 'el saldo que queda en la cuenta de gasto de la tarjeta del mes (debería quedar en ≈0).',
    color: 'todavía queda gasto sin detallar; mejora a medida que se categorizan las compras. Es informativo, no un descuadre.' },
] as const

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
          <td colSpan={8} className="px-4 py-3">
            <CheckDetail r={r} />
          </td>
        </tr>
      )}
    </>
  )
}

// Dólar / número plano (no moneda) — para mostrar el fx del estado (ej. "931,05").
const num = (n: number) => new Intl.NumberFormat('es-CL', { maximumFractionDigits: 2 }).format(n)

// Fila de comparación de dos lados + diferencia (deuda/monto en positivo, como lo lee un contador).
function TwoSided({ rows, diff, diffOk }: {
  rows: { label: string; value: string }[]; diff: string; diffOk: boolean
}) {
  return (
    <div className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-0.5 items-baseline">
      {rows.map((r, i) => (
        <Fragment key={i}>
          <span className="text-muted-foreground">{r.label}</span>
          <span className="font-mono text-right">{r.value}</span>
        </Fragment>
      ))}
      <span className="text-muted-foreground border-t pt-0.5">Diferencia</span>
      <span className={`font-mono text-right border-t pt-0.5 ${diffOk ? 'text-green-600' : 'text-red-600'}`}>
        {diff} {diffOk ? '✓' : '✗'}
      </span>
    </div>
  )
}

// Buckets de operation_type para la cascada de conciliación.
const COMPRA_OPS = ['compra', 'cuota']
const CARGO_OPS = ['impuesto', 'comision', 'interes', 'seguro', 'mantencion']
const ABONO_OPS = ['abono', 'nota_credito']
const PAGO_OPS = ['pago']

const prevMonth = (ym: string) => {
  const [y, m] = ym.split('-').map(Number)
  return m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, '0')}`
}

// Una fila de la cascada: signo · concepto (+ fecha/fuente) · monto.
function CascadeRow({ sign, label, note, amount, bad, total }: {
  sign?: string; label: string; note?: string; amount: string; bad?: boolean; total?: boolean
}) {
  return (
    <div className={`grid grid-cols-[1.1rem_1fr_auto] gap-x-2 items-baseline ${bad ? 'text-red-600' : total ? 'font-medium' : ''}`}>
      <span className="text-right text-muted-foreground">{sign ?? ''}</span>
      <span>{label}{note && <span className="text-muted-foreground text-[11px]"> · {note}</span>}</span>
      <span className={`font-mono text-right ${total ? '' : ''}`}>{amount}</span>
    </div>
  )
}

// Cascada de conciliación (diseño Valentina): la cadena de montos que ata mes a mes, en CLP.
// saldo_anterior = saldo contable − Σ movimientos (despejado → cierra por construcción, CLP y USD).
function Cascada({ r }: { r: TcReconciliationRow }) {
  const bucket = (ops: string[]) =>
    r.movements.filter((m) => ops.includes(m.operation_type)).reduce((s, m) => s + Math.abs(m.amount), 0)
  const compras = bucket(COMPRA_OPS)
  const cargos = bucket(CARGO_OPS)
  const abonos = bucket(ABONO_OPS)
  const pago = bucket(PAGO_OPS)
  const otros = r.movements
    .filter((m) => ![...COMPRA_OPS, ...CARGO_OPS, ...ABONO_OPS, ...PAGO_OPS].includes(m.operation_type))
    .reduce((s, m) => s + Math.abs(m.amount), 0)
  const movSum = r.movements.reduce((s, m) => s + m.amount, 0)         // signed
  const saldoAnterior = Math.abs(r.tc_real_balance - movSum)           // despejado
  const deuda = Math.abs(r.tc_real_balance)                            // saldo contable al cierre

  // Cartola vieja sin cierre persistido (import pre-6.6): no comparar contra 0.
  const sinCierre = r.closing_clp === 0 && deuda > 1
  const pagoBanco = r.laudus_payment_total
  const pagoDate = r.laudus_payments[0]?.date

  return (
    <div className="border rounded-md bg-background p-3 text-xs space-y-1">
      <p className="font-medium text-sm mb-1">Conciliación del mes</p>
      <CascadeRow label="Saldo del mes anterior" note={`al cierre de ${prevMonth(r.year_month)}`} amount={fmt(saldoAnterior)} />
      <CascadeRow sign="−" label="Pago del saldo" note={pagoDate ? `banco ${pagoDate}` : 'banco'} amount={fmt(pago)}
        bad={!r.pago_ok} />
      {!r.pago_ok && (
        <p className="text-amber-600 pl-[1.1rem]">
          ⚠ el banco registró {fmt(pagoBanco)} — no coincide con el pago de la cartola. Puede ser un pago
          consolidado de varias tarjetas, o falta el pago del mes.
        </p>
      )}
      <CascadeRow sign="+" label="Compras y cuotas del mes" note={r.year_month} amount={fmt(compras)} />
      <CascadeRow sign="+" label="Cargos (impuestos, comisiones)" note={r.year_month} amount={fmt(cargos)} />
      <CascadeRow sign="−" label="Abonos (devoluciones)" note={r.year_month} amount={fmt(abonos)} />
      {otros > 1 && <CascadeRow sign="+" label="Otros (avances, etc.)" note={r.year_month} amount={fmt(otros)} />}
      <div className="border-t my-1" />
      <CascadeRow label="Saldo en la contabilidad" note="al cierre" amount={fmt(deuda)} total />
      {sinCierre ? (
        <p className="text-amber-600 pt-1">
          🟡 Esta cartola se cargó antes de que se guardara el cierre — no puedo compararla. Re-importala
          para cuadrarla.
        </p>
      ) : (
        <CascadeRow
          label="Cierre según la cartola"
          note={r.currency !== 'CLP' ? `${fmt(r.closing, r.currency)} × ${num(r.fx)}` : undefined}
          amount={fmt(r.closing_clp)}
          bad={!r.c1_ok}
          total
        />
      )}
      {!sinCierre && !r.c1_ok && (
        <p className="text-red-600 pt-1">
          🔴 El saldo en la contabilidad no coincide con el cierre de la cartola (diferencia{' '}
          {fmt(Math.abs(deuda - r.closing_clp))}). Si las líneas de arriba están bien, revisá si a una
          compra se le borró la deuda (chequeo C3).
        </p>
      )}
    </div>
  )
}

// Panel abrible por chequeo (auto-abierto si falla): el contador ve QUÉ compara y los dos números.
function CheckPanel({ code, ok, critical, children }: {
  code: string; ok: boolean; critical: boolean; children: ReactNode
}) {
  const short = CHECKS.find((c) => c.code === code)?.title.split(' — ')[0] ?? code
  return (
    <details open={!ok} className="border rounded-md bg-background">
      <summary className="cursor-pointer select-none px-3 py-2 flex items-center gap-2">
        <span aria-hidden>{dot(ok, critical)}</span>
        <span className="font-mono">{code}</span>
        <span className="text-muted-foreground">· {short}</span>
      </summary>
      <div className="px-3 pb-3 pt-1 text-xs space-y-2">{children}</div>
    </details>
  )
}

function CheckDetail({ r }: { r: TcReconciliationRow }) {
  const cur = r.currency
  const isUsd = cur !== 'CLP'
  const compraCount = r.movements.filter((m) => m.operation_type === 'compra' || m.operation_type === 'cuota').length
  const deuda = Math.abs(r.tc_real_balance)
  return (
    <div className="space-y-3">
      <Cascada r={r} />
      <details className="border rounded-md bg-background">
        <summary className="cursor-pointer select-none px-3 py-2 text-muted-foreground">
          Detalle por chequeo (C1–C5)
        </summary>
        <div className="px-3 pb-3 pt-1 space-y-2">
      {/* C1 — cuadre de la deuda */}
      <CheckPanel code="C1" ok={r.c1_ok} critical>
        <TwoSided
          rows={[
            { label: 'Deuda en la contabilidad (al cierre del mes)', value: fmt(deuda) },
            {
              label: 'Deuda según la cartola (cierre del estado)',
              value: isUsd ? `${fmt(r.closing, cur)} × ${num(r.fx)} = ${fmt(r.closing_clp)}` : fmt(r.closing_clp),
            },
          ]}
          diff={fmt(deuda - r.closing_clp)}
          diffOk={r.c1_ok}
        />
        {!r.c1_ok && (
          <p className="text-red-600">
            La deuda registrada no coincide con el estado de cuenta. Causas típicas: una compra o un pago
            se cargó mal, o falta cargar una cartola de un mes anterior. Revisá y, si hace falta, rechazá y
            volvé a importar.
          </p>
        )}
      </CheckPanel>

      {/* C2 — continuidad */}
      <CheckPanel code="C2" ok={r.c2_ok} critical={false}>
        {r.c2_reason ? (
          <p className="text-muted-foreground">
            {r.c2_reason === 'sin cartola anterior'
              ? 'Es la primera cartola cargada de esta tarjeta; no hay mes anterior con qué comparar. Cargá los meses en orden.'
              : r.c2_reason}
          </p>
        ) : (
          <>
            <TwoSided
              rows={[
                { label: 'Apertura de esta cartola', value: fmt(r.opening, cur) },
                { label: 'Cierre de la cartola del mes anterior', value: fmt(r.c2_prior_closing, cur) },
              ]}
              diff={fmt((r.opening ?? 0) - (r.c2_prior_closing ?? 0), cur)}
              diffOk={r.c2_ok}
            />
            {!r.c2_ok && (
              <p className="text-amber-600">
                La apertura de este mes no coincide con el cierre del mes pasado — probablemente falte
                cargar una cartola entre medio.
              </p>
            )}
          </>
        )}
      </CheckPanel>

      {/* C3 — compras con su deuda */}
      <CheckPanel code="C3" ok={r.c3_ok} critical>
        {r.c3_ok ? (
          <p className="text-muted-foreground">Las {compraCount} compras del mes conservan su deuda.</p>
        ) : (
          <>
            <p className="text-red-600">
              {r.c3_corrupted_count} compra(s) perdieron su registro de deuda. Se categorizaron mal (se
              borró la deuda). Solución: rechazá y volvé a importar la cartola de este mes.
            </p>
            {r.c3_corrupted.map((m, i) => (
              <div key={i} className="grid grid-cols-[5rem_1fr_auto] gap-2">
                <span className="font-mono text-muted-foreground">{m.date}</span>
                <span className="truncate">{m.narration}</span>
                <span className="font-mono text-right">{fmt(m.amount)}</span>
              </div>
            ))}
          </>
        )}
      </CheckPanel>

      {/* C4 — pago vs banco */}
      <CheckPanel code="C4" ok={r.pago_ok} critical={false}>
        <TwoSided
          rows={[
            { label: 'Pago según la cartola', value: fmt(r.pago_cartola) },
            { label: 'Pago registrado por el banco (Laudus)', value: fmt(r.laudus_payment_total) },
          ]}
          diff={fmt(r.pago_cartola - r.laudus_payment_total)}
          diffOk={r.pago_ok}
        />
        {!r.pago_ok && (
          <p className="text-amber-600">
            El pago de la cartola no coincide con lo que registró el banco. Suele pasar cuando el banco
            paga varias tarjetas en un solo movimiento (pago consolidado), o si falta el pago del mes.
          </p>
        )}
        {r.laudus_payments.length > 0 && (
          <div className="pt-1">
            <p className="text-muted-foreground mb-0.5">Detalle del banco:</p>
            {r.laudus_payments.map((p, i) => (
              <div key={i} className="grid grid-cols-[5rem_1fr_auto] gap-2">
                <span className="font-mono text-muted-foreground">{p.date}</span>
                <span className="truncate">{p.narration}</span>
                <span className="font-mono text-right">{fmt(p.amount)}</span>
              </div>
            ))}
          </div>
        )}
      </CheckPanel>

      {/* C5 — gasto del mes saldado (informativo) */}
      <CheckPanel code="C5" ok={r.c5_ok} critical={false}>
        <div className="grid grid-cols-[1fr_auto] gap-x-4">
          <span className="text-muted-foreground">Gasto sin detallar todavía</span>
          <span className="font-mono text-right">{fmt(r.c5_residual)}</span>
        </div>
        <p className="text-muted-foreground">
          El banco carga el gasto de la tarjeta en bloque; a medida que se categorizan las compras, este
          saldo baja a $0. Es informativo, no un descuadre.
        </p>
      </CheckPanel>

      {/* Movimientos de la cartola (contexto) */}
      <details className="border rounded-md bg-background">
        <summary className="cursor-pointer select-none px-3 py-2 text-muted-foreground">
          Movimientos de la cartola (compras {fmt(r.sum_compras)} · pagos {fmt(r.sum_pagos)} · cargos {fmt(r.sum_cargos)})
        </summary>
        <div className="px-3 pb-3 pt-1 text-xs">
          {r.movements.length === 0 && <p className="text-muted-foreground">— sin movimientos —</p>}
          {r.movements.map((m, i) => (
            <div key={i} className="grid grid-cols-[5rem_1fr_auto] gap-2">
              <span className="font-mono text-muted-foreground">{m.date}</span>
              <span className="truncate">{m.operation_type} · {m.narration}</span>
              <span className="font-mono text-right">{fmt(m.amount)}</span>
            </div>
          ))}
        </div>
      </details>
        </div>
      </details>
    </div>
  )
}
