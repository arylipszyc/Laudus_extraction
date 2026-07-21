import { Fragment, useMemo, useState } from 'react'
import { fmtNum } from '@/lib/format'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, ExternalLink, MessageSquare, MessageSquarePlus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useHasRole } from '@/hooks/useHasRole'
import { favaEditorUrl } from '@/lib/fava'
import { useLedger } from '@/hooks/useLedger'
import { listThreads, createComment } from '@/services/ownerComments'
import { groupByCategoria1 } from '@/utils/ledgerAnalytics'
import type { LedgerEntryRecord } from '@/types'
import type { AccountSummary, Categoria1Group, Categoria2Group, Categoria3Group } from '@/utils/ledgerAnalytics'

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatAmount(amount: number, currency = 'CLP'): string {
  const formatted = fmtNum(amount, currency)
  return currency !== 'CLP' ? `${formatted} ${currency}` : formatted
}

function formatDate(isoDate: string): string {
  if (!isoDate || isoDate.length < 10) return isoDate
  const [y, m, d] = isoDate.slice(0, 10).split('-')
  return `${d}/${m}/${y}`
}

function openFava(url: string) {
  window.open(url, '_blank', 'noopener,noreferrer')
}

// ── Transaction detail (lazy-loaded per account) ──────────────────────────────

// 7.1b AC3: form inline de "comentar" bajo la fila (una <tr> extra, sin toasts).
function CommentFormRow({ txId, onClose }: { txId: string; onClose: () => void }) {
  const [body, setBody] = useState('')
  const [sent, setSent] = useState(false)
  const qc = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => createComment(txId, body),
    onSuccess: () => {
      setSent(true)
      // la fila pasa a badge "ver hilo" sin recargar (AC3/AC4)
      qc.invalidateQueries({ queryKey: ['comment-threads'] })
      setTimeout(onClose, 3000)
    },
  })
  const canSend = !mutation.isPending && body.trim().length > 0

  return (
    <tr className="bg-muted/10 border-t border-dashed">
      <td colSpan={4} className="px-10 py-2">
        {sent ? (
          <div className="flex items-center justify-between text-xs text-green-700">
            <span>✓ Comentario enviado — el contador lo verá en Comentarios.</span>
            <button
              onClick={onClose}
              className="text-xs text-muted-foreground hover:text-foreground font-medium underline ml-2"
            >
              Cerrar
            </button>
          </div>
        ) : (
          <div className="space-y-1.5">
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={2}
              maxLength={10_000}
              placeholder="¿Qué quieres preguntar sobre este movimiento?"
              disabled={mutation.isPending}
              className="w-full border rounded-md px-3 py-2 bg-background text-xs"
            />
            {mutation.error && (
              <p className="text-xs text-destructive">{(mutation.error as Error).message}</p>
            )}
            <div className="flex gap-2">
              <Button size="sm" onClick={() => mutation.mutate()} disabled={!canSend}>
                {mutation.isPending ? 'Enviando…' : 'Enviar'}
              </Button>
              <Button size="sm" variant="ghost" onClick={onClose} disabled={mutation.isPending}>
                Cancelar
              </Button>
            </div>
          </div>
        )}
      </td>
    </tr>
  )
}

export function TransactionRows({ accountNumber, type, selectedPeriods }: { accountNumber: string; type: 'income' | 'expenses'; selectedPeriods: string[] }) {
  const { data, isLoading } = useLedger(accountNumber)
  const navigate = useNavigate()
  // Deep-link a Fava = solo contador/admin (Fava es contador-only, basic-auth; la familia no entra).
  const canUseFava = useHasRole(['contador', 'admin'])
  // 7.1b AC4: hilos cargados UNA vez para todo el drill-down — la queryKey compartida
  // dedupea entre todas las cuentas expandidas; para `family` el back ya acota a los suyos.
  const { data: threads, error: threadsError } = useQuery({
    queryKey: ['comment-threads'],
    queryFn: () => listThreads('all'),
    staleTime: 60_000,
  })
  const threadByTx = useMemo(() => {
    const map = new Map<string, string>()
    for (const t of threads ?? []) if (t.tx_id) map.set(t.tx_id, t.thread_id)
    return map
  }, [threads])
  const [openFormKey, setOpenFormKey] = useState<string | null>(null)

  if (isLoading) {
    return (
      <tr>
        <td colSpan={4} className="px-10 py-2 bg-muted/10">
          <Skeleton className="h-3 w-full" />
        </td>
      </tr>
    )
  }

  const allEntries = data?.data ?? []
  const filtered = selectedPeriods.length > 0
    ? allEntries.filter(e => e.date && selectedPeriods.includes(e.date.slice(0, 7)))
    : allEntries
  const entries = [...filtered].sort((a, b) => b.date.localeCompare(a.date))

  if (entries.length === 0) {
    return (
      <tr>
        <td colSpan={4} className="px-10 py-2 text-xs text-muted-foreground italic bg-muted/10">
          Sin movimientos en el período
        </td>
      </tr>
    )
  }

  return (
    <>
      {threadsError && (
        <tr>
          <td colSpan={4} className="px-10 py-1 text-[10px] text-destructive bg-destructive/10 border-t border-dashed">
            ⚠ No se pudieron cargar los hilos de comentarios. Las acciones de comentarios no están disponibles.
          </td>
        </tr>
      )}
      {entries.map((e) => {
        const amount = type === 'income' ? e.credit - e.debit : e.debit - e.credit
        const unfilteredIndex = allEntries.indexOf(e)
        const key = e.tx_id
          ? `${e.tx_id}-${unfilteredIndex}`
          : `${e.journalentryid}-${e.lineid}-${unfilteredIndex}`
        const threadId = e.tx_id ? threadByTx.get(e.tx_id) : undefined
        // Fail-safe: sin ubicación (datos viejos/sintéticos) o sin config de Fava → sin affordance.
        const favaUrl = canUseFava ? favaEditorUrl(e.filename, e.lineno) : null
        const favaTitle = e.source === 'laudus-erp'
          ? 'Ver en Fava (asiento de Laudus — no editar en el lugar; corregir con asiento de ajuste)'
          : 'Ver asiento completo en Fava'
        return (
          <Fragment key={key}>
            <tr
              className="bg-muted/10 text-xs border-t border-dashed"
              onDoubleClick={favaUrl ? () => openFava(favaUrl) : undefined}
            >
              <td className="px-10 py-1 font-mono text-muted-foreground whitespace-nowrap">{formatDate(e.date)}</td>
              <td className="px-3 py-1 text-muted-foreground" colSpan={2}>
                {e.description || '—'}
                {/* Deep-link al asiento completo en Fava (contador/admin; oculto sin ubicación/config) */}
                {favaUrl && (
                  <button
                    title={favaTitle}
                    aria-label={favaTitle}
                    onClick={() => openFava(favaUrl)}
                    className="ml-2 align-middle text-muted-foreground hover:text-primary"
                  >
                    <ExternalLink className="inline w-3.5 h-3.5" />
                  </button>
                )}
                {/* 7.1b: sin tx_id (datos viejos cacheados) o si falló la carga → sin affordance (fail-safe AC3) */}
                {!threadsError && e.tx_id && (threadId ? (
                  <button
                    title="Ver hilo de comentarios"
                    aria-label="Ver hilo de comentarios"
                    onClick={() => navigate(`/comments?thread=${threadId}`)}
                    className="ml-2 align-middle text-primary hover:opacity-70"
                  >
                    <MessageSquare className="inline w-3.5 h-3.5" />
                  </button>
                ) : (
                  <button
                    title="Comentar esta transacción"
                    aria-label="Comentar esta transacción"
                    onClick={() => setOpenFormKey(k => (k === key ? null : key))}
                    className="ml-2 align-middle text-muted-foreground hover:text-primary"
                  >
                    <MessageSquarePlus className="inline w-3.5 h-3.5" />
                  </button>
                ))}
              </td>
              <td className={`px-4 py-1 text-right font-mono ${amount >= 0 ? 'text-green-600' : 'text-destructive'}`}>
                {formatAmount(amount, e.currencycode || 'CLP')}
              </td>
            </tr>
            {openFormKey === key && e.tx_id && (
              <CommentFormRow txId={e.tx_id} onClose={() => setOpenFormKey(null)} />
            )}
          </Fragment>
        )
      })}
    </>
  )
}

// ── Account row (level 4) ─────────────────────────────────────────────────────

function AccountRow({ account, type, amountClass, selectedPeriods }: { account: AccountSummary; type: 'income' | 'expenses'; amountClass: string; selectedPeriods: string[] }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <>
      <tr
        className="border-t hover:bg-muted/20 transition-colors cursor-pointer select-none"
        onClick={() => setExpanded(p => !p)}
      >
        <td className="pl-10 pr-4 py-2">
          {expanded ? <ChevronDown className="inline w-3 h-3 mr-1 text-muted-foreground" /> : <ChevronRight className="inline w-3 h-3 mr-1 text-muted-foreground" />}
          <span className="text-xs text-muted-foreground font-mono mr-2">{account.accountNumber}</span>
          <span className="text-sm">{account.accountName}</span>
        </td>
        <td /><td />
        <td className={`px-4 py-2 text-right text-sm font-medium ${amountClass}`}>
          {formatAmount(account.total, account.currency)}
        </td>
      </tr>
      {expanded && <TransactionRows accountNumber={account.accountNumber} type={type} selectedPeriods={selectedPeriods} />}
    </>
  )
}

// ── Categoria3 row (level 3) ──────────────────────────────────────────────────

function Cat3Section({ group, type, amountClass, selectedPeriods }: { group: Categoria3Group; type: 'income' | 'expenses'; amountClass: string; selectedPeriods: string[] }) {
  const [expanded, setExpanded] = useState(false)
  // Collapse this level if there's only one account and it has the same name — avoids redundant nesting
  const isPassthrough = group.accounts.length === 1 && group.label === 'Sin subcategoría'

  if (isPassthrough) {
    return <AccountRow account={group.accounts[0]} type={type} amountClass={amountClass} selectedPeriods={selectedPeriods} />
  }

  return (
    <>
      <tr
        className="border-t hover:bg-muted/10 transition-colors cursor-pointer select-none bg-muted/5"
        onClick={() => setExpanded(p => !p)}
      >
        <td className="pl-7 pr-4 py-1.5 text-sm text-muted-foreground" colSpan={3}>
          {expanded ? <ChevronDown className="inline w-3 h-3 mr-1" /> : <ChevronRight className="inline w-3 h-3 mr-1" />}
          {group.label}
        </td>
        <td className={`px-4 py-1.5 text-right text-sm ${amountClass}`}>
          {formatAmount(group.subtotal)}
        </td>
      </tr>
      {expanded && group.accounts.map(a => (
        <AccountRow key={a.accountNumber} account={a} type={type} amountClass={amountClass} selectedPeriods={selectedPeriods} />
      ))}
    </>
  )
}

// ── Categoria2 row (level 2) ──────────────────────────────────────────────────

function Cat2Section({ group, type, amountClass, selectedPeriods }: { group: Categoria2Group; type: 'income' | 'expenses'; amountClass: string; selectedPeriods: string[] }) {
  const [expanded, setExpanded] = useState(false)
  const isPassthrough = group.cat3Groups.length === 1 && group.label === 'Sin subcategoría'

  if (isPassthrough) {
    return <Cat3Section group={group.cat3Groups[0]} type={type} amountClass={amountClass} selectedPeriods={selectedPeriods} />
  }

  return (
    <>
      <tr
        className="border-t hover:bg-muted/20 transition-colors cursor-pointer select-none"
        onClick={() => setExpanded(p => !p)}
      >
        <td className="pl-5 pr-4 py-2 text-sm font-medium" colSpan={3}>
          {expanded ? <ChevronDown className="inline w-3 h-3 mr-1" /> : <ChevronRight className="inline w-3 h-3 mr-1" />}
          {group.label}
        </td>
        <td className={`px-4 py-2 text-right text-sm font-medium ${amountClass}`}>
          {formatAmount(group.subtotal)}
        </td>
      </tr>
      {expanded && group.cat3Groups.map(g => (
        <Cat3Section key={g.label} group={g} type={type} amountClass={amountClass} selectedPeriods={selectedPeriods} />
      ))}
    </>
  )
}

// ── Categoria1 section (level 1) ──────────────────────────────────────────────

function Cat1Section({ group, type, amountClass, selectedPeriods }: { group: Categoria1Group; type: 'income' | 'expenses'; amountClass: string; selectedPeriods: string[] }) {
  const [expanded, setExpanded] = useState(true)
  return (
    <>
      <tr
        className="bg-muted/40 border-t cursor-pointer select-none hover:bg-muted/60 transition-colors"
        onClick={() => setExpanded(p => !p)}
      >
        <td className="px-4 py-2 font-semibold text-sm" colSpan={3}>
          {expanded ? <ChevronDown className="inline w-4 h-4 mr-1" /> : <ChevronRight className="inline w-4 h-4 mr-1" />}
          {group.label}
        </td>
        <td className={`px-4 py-2 text-right font-bold text-sm ${amountClass}`}>
          {formatAmount(group.subtotal)}
        </td>
      </tr>
      {expanded && group.cat2Groups.map(g => (
        <Cat2Section key={g.label} group={g} type={type} amountClass={amountClass} selectedPeriods={selectedPeriods} />
      ))}
    </>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  records: LedgerEntryRecord[]
  type: 'income' | 'expenses'
  title: string
  selectedPeriods?: string[]
}

export function IncomeExpensesDrilldown({ records, type, title, selectedPeriods = [] }: Props) {
  // F7: agrupación pesada — solo recomputa cuando cambian los records o el tipo.
  const groups = useMemo(() => groupByCategoria1(records, type), [records, type])
  const amountClass = type === 'income' ? 'text-green-600' : 'text-destructive'

  if (groups.length === 0) {
    return (
      <div>
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">{title}</h3>
        <p className="text-sm text-muted-foreground">Sin registros</p>
      </div>
    )
  }

  return (
    <div>
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">{title}</h3>
      <div className="rounded-md border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="text-left px-4 py-2 font-medium">Categoría / Cuenta</th>
              <th /><th />
              <th className="text-right px-4 py-2 font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {groups.map(g => (
              <Cat1Section key={g.label} group={g} type={type} amountClass={amountClass} selectedPeriods={selectedPeriods} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
