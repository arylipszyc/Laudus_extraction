import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { useLedger } from '@/hooks/useLedger'
import { groupByCategoria1 } from '@/utils/ledgerAnalytics'
import type { LedgerEntryRecord } from '@/types'
import type { AccountSummary, Categoria1Group, Categoria2Group, Categoria3Group } from '@/utils/ledgerAnalytics'

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatAmount(amount: number, currency = 'CLP'): string {
  const formatted = amount.toLocaleString('es-CL')
  return currency !== 'CLP' ? `${formatted} ${currency}` : formatted
}

function formatDate(isoDate: string): string {
  if (!isoDate || isoDate.length < 10) return isoDate
  const [y, m, d] = isoDate.slice(0, 10).split('-')
  return `${d}/${m}/${y}`
}

// ── Transaction detail (lazy-loaded per account) ──────────────────────────────

function TransactionRows({ accountNumber, type }: { accountNumber: string; type: 'income' | 'expenses' }) {
  const { data, isLoading } = useLedger(accountNumber)

  if (isLoading) {
    return (
      <tr>
        <td colSpan={4} className="px-10 py-2 bg-muted/10">
          <Skeleton className="h-3 w-full" />
        </td>
      </tr>
    )
  }

  const entries = [...(data?.data ?? [])].sort((a, b) => b.date.localeCompare(a.date))

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
      {entries.map((e, i) => {
        const amount = type === 'income' ? e.credit - e.debit : e.debit - e.credit
        return (
          <tr key={`${e.journalentryid}-${e.lineid}-${i}`} className="bg-muted/10 text-xs border-t border-dashed">
            <td className="px-10 py-1 font-mono text-muted-foreground whitespace-nowrap">{formatDate(e.date)}</td>
            <td className="px-3 py-1 text-muted-foreground" colSpan={2}>{e.description || '—'}</td>
            <td className={`px-4 py-1 text-right font-mono ${amount >= 0 ? 'text-green-600' : 'text-destructive'}`}>
              {formatAmount(amount, e.currencycode || 'CLP')}
            </td>
          </tr>
        )
      })}
    </>
  )
}

// ── Account row (level 4) ─────────────────────────────────────────────────────

function AccountRow({ account, type, amountClass }: { account: AccountSummary; type: 'income' | 'expenses'; amountClass: string }) {
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
      {expanded && <TransactionRows accountNumber={account.accountNumber} type={type} />}
    </>
  )
}

// ── Categoria3 row (level 3) ──────────────────────────────────────────────────

function Cat3Section({ group, type, amountClass }: { group: Categoria3Group; type: 'income' | 'expenses'; amountClass: string }) {
  const [expanded, setExpanded] = useState(false)
  // Collapse this level if there's only one account and it has the same name — avoids redundant nesting
  const isPassthrough = group.accounts.length === 1 && group.label === 'Sin subcategoría'

  if (isPassthrough) {
    return <AccountRow account={group.accounts[0]} type={type} amountClass={amountClass} />
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
        <AccountRow key={a.accountNumber} account={a} type={type} amountClass={amountClass} />
      ))}
    </>
  )
}

// ── Categoria2 row (level 2) ──────────────────────────────────────────────────

function Cat2Section({ group, type, amountClass }: { group: Categoria2Group; type: 'income' | 'expenses'; amountClass: string }) {
  const [expanded, setExpanded] = useState(false)
  const isPassthrough = group.cat3Groups.length === 1 && group.label === 'Sin subcategoría'

  if (isPassthrough) {
    return <Cat3Section group={group.cat3Groups[0]} type={type} amountClass={amountClass} />
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
        <Cat3Section key={g.label} group={g} type={type} amountClass={amountClass} />
      ))}
    </>
  )
}

// ── Categoria1 section (level 1) ──────────────────────────────────────────────

function Cat1Section({ group, type, amountClass }: { group: Categoria1Group; type: 'income' | 'expenses'; amountClass: string }) {
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
        <Cat2Section key={g.label} group={g} type={type} amountClass={amountClass} />
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
              <th className="text-left px-4 py-2 font-medium">Categoría / Cuenta</th>
              <th /><th />
              <th className="text-right px-4 py-2 font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {groups.map(g => (
              <Cat1Section key={g.label} group={g} type={type} amountClass={amountClass} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
