import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { useLedger } from '@/hooks/useLedger'
import { groupByCategoria1 } from '@/utils/ledgerAnalytics'
import type { LedgerEntryRecord } from '@/types'
import type { AccountSummary, Categoria1Group } from '@/utils/ledgerAnalytics'

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatAmount(amount: number, currency = 'CLP'): string {
  const formatted = amount.toLocaleString('es-CL')
  return currency !== 'CLP' ? `${formatted} ${currency}` : formatted
}

function formatDate(isoDate: string): string {
  // "2026-03-15" → "15/03/2026"
  if (!isoDate || isoDate.length < 10) return isoDate
  const [y, m, d] = isoDate.slice(0, 10).split('-')
  return `${d}/${m}/${y}`
}

// ── Transaction detail (lazy-loaded per account) ──────────────────────────────

function TransactionRows({
  accountNumber,
  type,
}: {
  accountNumber: string
  type: 'income' | 'expenses'
}) {
  const { data, isLoading } = useLedger(accountNumber)

  if (isLoading) {
    return (
      <tr>
        <td colSpan={4} className="px-8 py-2 bg-muted/10">
          <Skeleton className="h-3 w-full" />
        </td>
      </tr>
    )
  }

  const entries = data?.data ?? []
  if (entries.length === 0) {
    return (
      <tr>
        <td colSpan={4} className="px-8 py-2 text-xs text-muted-foreground italic bg-muted/10">
          Sin movimientos en el período
        </td>
      </tr>
    )
  }

  // Sort date descending
  const sorted = [...entries].sort((a, b) => b.date.localeCompare(a.date))

  return (
    <>
      {sorted.map((e, i) => {
        const amount = type === 'income' ? e.credit - e.debit : e.debit - e.credit
        return (
          <tr
            key={`${e.journalentryid}-${e.lineid}-${i}`}
            className="bg-muted/10 text-xs border-t border-dashed"
          >
            <td className="px-8 py-1 font-mono text-muted-foreground whitespace-nowrap">
              {formatDate(e.date)}
            </td>
            <td className="px-3 py-1 text-muted-foreground" colSpan={2}>
              {e.description || '—'}
            </td>
            <td className={`px-4 py-1 text-right font-mono ${amount >= 0 ? 'text-green-600' : 'text-destructive'}`}>
              {formatAmount(amount, e.currencycode || 'CLP')}
            </td>
          </tr>
        )
      })}
    </>
  )
}

// ── Account row ───────────────────────────────────────────────────────────────

function AccountRow({
  account,
  type,
  amountClass,
}: {
  account: AccountSummary
  type: 'income' | 'expenses'
  amountClass: string
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <>
      <tr
        className="border-t hover:bg-muted/20 transition-colors cursor-pointer select-none"
        onClick={() => setExpanded(p => !p)}
      >
        <td className="px-6 py-2">
          {expanded ? (
            <ChevronDown className="inline w-3 h-3 mr-1 text-muted-foreground" />
          ) : (
            <ChevronRight className="inline w-3 h-3 mr-1 text-muted-foreground" />
          )}
          <span className="text-xs text-muted-foreground font-mono mr-2">{account.accountNumber}</span>
          <span className="text-sm">{account.accountName}</span>
        </td>
        <td />
        <td />
        <td className={`px-4 py-2 text-right text-sm font-medium ${amountClass}`}>
          {formatAmount(account.total, account.currency)}
        </td>
      </tr>
      {expanded && (
        <TransactionRows accountNumber={account.accountNumber} type={type} />
      )}
    </>
  )
}

// ── Categoria1 section ────────────────────────────────────────────────────────

function Categoria1Section({
  group,
  type,
  amountClass,
}: {
  group: Categoria1Group
  type: 'income' | 'expenses'
  amountClass: string
}) {
  const [expanded, setExpanded] = useState(true)

  return (
    <>
      <tr
        className="bg-muted/40 border-t cursor-pointer select-none hover:bg-muted/60 transition-colors"
        onClick={() => setExpanded(p => !p)}
      >
        <td className="px-4 py-2 font-semibold text-sm" colSpan={3}>
          {expanded ? (
            <ChevronDown className="inline w-4 h-4 mr-1" />
          ) : (
            <ChevronRight className="inline w-4 h-4 mr-1" />
          )}
          {group.categoria1}
        </td>
        <td className={`px-4 py-2 text-right font-bold text-sm ${amountClass}`}>
          {formatAmount(group.subtotal)}
        </td>
      </tr>
      {expanded &&
        group.accounts.map(acct => (
          <AccountRow
            key={acct.accountNumber}
            account={acct}
            type={type}
            amountClass={amountClass}
          />
        ))}
    </>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  records: LedgerEntryRecord[]
  type: 'income' | 'expenses'
  title: string
}

export function IncomeExpensesDrilldown({ records, type, title }: Props) {
  const groups = groupByCategoria1(records, type)
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
              <th className="text-left px-4 py-2 font-medium">Cuenta</th>
              <th />
              <th />
              <th className="text-right px-4 py-2 font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {groups.map(group => (
              <Categoria1Section
                key={group.categoria1}
                group={group}
                type={type}
                amountClass={amountClass}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
