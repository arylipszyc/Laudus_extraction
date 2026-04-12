import { useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { Skeleton } from '@/components/ui/skeleton'
import { useLedger } from '@/hooks/useLedger'
import type { LedgerEntryRecord } from '@/types'

// Bug 1 fix: use Categoria1 from PlanCuentas (reliable) before falling back to prefix guessing
function getLedgerCategory(
  accountNumber: unknown,
  categoria1: string = ''
): 'income' | 'expenses' | 'other' {
  if (categoria1) {
    const cat = categoria1.toLowerCase()
    if (cat.includes('ingreso') || cat.includes('revenue')) return 'income'
    if (cat.includes('gasto') || cat.includes('costo') || cat.includes('expense')) return 'expenses'
  }
  const s = String(accountNumber ?? '')
  if (s.startsWith('4')) return 'income'
  if (s.startsWith('5') || s.startsWith('6')) return 'expenses'
  return 'other'
}

function formatAmount(amount: number, currency: string = 'CLP'): string {
  const formatted = amount.toLocaleString('es-CL')
  return currency && currency !== 'CLP' ? `${formatted} ${currency}` : formatted
}

interface CategoryBreakdown {
  accountNumber: string
  accountName: string   // Bug 2 fix: real account name instead of number
  total: number
  currency: string
}

// Bug 2 fix: capture accountName from enriched ledger_final data
function buildBreakdown(records: LedgerEntryRecord[], type: 'income' | 'expenses'): CategoryBreakdown[] {
  const map = new Map<string, { total: number; currency: string; accountName: string }>()
  for (const r of records) {
    const cat = getLedgerCategory(r.accountnumber, r.Categoria1)
    if (cat !== type) continue
    const amount = type === 'income' ? r.credit - r.debit : r.debit - r.credit
    const existing = map.get(r.accountnumber)
    if (existing) {
      existing.total += amount
    } else {
      map.set(r.accountnumber, {
        total: amount,
        currency: r.currencycode || 'CLP',
        accountName: r.accountName || String(r.accountnumber),
      })
    }
  }
  return Array.from(map.entries())
    .map(([accountNumber, { total, currency, accountName }]) => ({
      accountNumber,
      accountName,
      total,
      currency,
    }))
    .sort((a, b) => b.total - a.total)
}

// Bug 3 fix: drill-down component — fetches individual transactions for a given account
function AccountDrilldown({ accountNumber }: { accountNumber: string }) {
  const { data, isLoading } = useLedger(accountNumber)

  if (isLoading) {
    return (
      <tr>
        <td colSpan={2} className="px-6 py-2 bg-muted/10">
          <Skeleton className="h-4 w-full" />
        </td>
      </tr>
    )
  }

  const entries = data?.data ?? []
  if (entries.length === 0) {
    return (
      <tr>
        <td colSpan={2} className="px-6 py-2 text-xs text-muted-foreground italic bg-muted/10">
          Sin movimientos en el período
        </td>
      </tr>
    )
  }

  return (
    <>
      {entries.map((e, i) => (
        <tr key={`${e.journalentryid}-${e.lineid}-${i}`} className="bg-muted/10 text-xs border-t border-dashed">
          <td className="px-6 py-1 text-muted-foreground">
            {e.date} — {e.description || '—'}
          </td>
          <td className="px-4 py-1 text-right font-mono">
            {e.debit > 0 ? (
              <span className="text-destructive">−{formatAmount(e.debit, e.currencycode || 'CLP')}</span>
            ) : (
              <span className="text-green-600">+{formatAmount(e.credit, e.currencycode || 'CLP')}</span>
            )}
          </td>
        </tr>
      ))}
    </>
  )
}

interface BreakdownTableProps {
  title: string
  items: CategoryBreakdown[]
  emptyMessage: string
  amountClass: string
  expandedAccount: string | null
  onToggle: (accountNumber: string) => void
}

function BreakdownTable({ title, items, emptyMessage, amountClass, expandedAccount, onToggle }: BreakdownTableProps) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
        {title}
      </h3>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{emptyMessage}</p>
      ) : (
        <div className="rounded-md border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Cuenta</th>
                <th className="text-right px-4 py-2 font-medium">Total</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <>
                  <tr
                    key={item.accountNumber}
                    className="border-t hover:bg-muted/30 transition-colors cursor-pointer select-none"
                    onClick={() => onToggle(item.accountNumber)}
                  >
                    <td className="px-4 py-2">
                      <span className="text-xs text-muted-foreground font-mono mr-2">{item.accountNumber}</span>
                      <span>{item.accountName}</span>
                      <span className="ml-2 text-xs text-muted-foreground">
                        {expandedAccount === item.accountNumber ? '▲' : '▼'}
                      </span>
                    </td>
                    <td className={`px-4 py-2 text-right font-medium ${amountClass}`}>
                      {formatAmount(item.total, item.currency)}
                    </td>
                  </tr>
                  {expandedAccount === item.accountNumber && (
                    <AccountDrilldown key={`drill-${item.accountNumber}`} accountNumber={item.accountNumber} />
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function IncomeExpensesPage() {
  const { data, isLoading, isError } = useLedger()
  const [expandedAccount, setExpandedAccount] = useState<string | null>(null)

  function toggleAccount(accountNumber: string) {
    setExpandedAccount((prev) => (prev === accountNumber ? null : accountNumber))
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-3/4" />
      </div>
    )
  }

  if (isError) {
    return <p className="text-destructive text-sm">Error al cargar datos.</p>
  }

  if (!data || data.data.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-muted-foreground">
        <p>No hay datos para el período seleccionado</p>
      </div>
    )
  }

  const records = data.data

  const totalIncome = records
    .filter((r) => getLedgerCategory(r.accountnumber, r.Categoria1) === 'income')
    .reduce((sum, r) => sum + (r.credit - r.debit), 0)

  const totalExpenses = records
    .filter((r) => getLedgerCategory(r.accountnumber, r.Categoria1) === 'expenses')
    .reduce((sum, r) => sum + (r.debit - r.credit), 0)

  const netResult = totalIncome - totalExpenses

  const incomeBreakdown = buildBreakdown(records, 'income')
  const expenseBreakdown = buildBreakdown(records, 'expenses')

  const chartData = [
    { name: 'Ingresos', value: totalIncome },
    { name: 'Gastos', value: totalExpenses },
  ]

  return (
    <div className="min-w-[1280px]">
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-1">Ingresos y Gastos</h2>
        {data.meta.last_sync && (
          <p className="text-xs text-muted-foreground">Último sync: {data.meta.last_sync}</p>
        )}
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground mb-1">Total Ingresos</p>
          <p className="text-2xl font-bold text-green-600">{formatAmount(totalIncome)}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground mb-1">Total Gastos</p>
          <p className="text-2xl font-bold text-destructive">{formatAmount(totalExpenses)}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground mb-1">Resultado Neto</p>
          <p className={`text-2xl font-bold ${netResult >= 0 ? 'text-green-600' : 'text-destructive'}`}>
            {formatAmount(netResult)}
          </p>
        </div>
      </div>

      {/* Recharts bar chart */}
      <div className="rounded-lg border bg-card p-6 mb-8">
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-4">
          Comparación del período
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
            <XAxis dataKey="name" />
            <YAxis tickFormatter={(v: number) => v.toLocaleString('es-CL')} />
            <Tooltip formatter={(v) => (typeof v === 'number' ? v.toLocaleString('es-CL') : v)} />
            <Bar dataKey="value">
              <Cell key="income" fill="#22c55e" />
              <Cell key="expenses" fill="#ef4444" />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Breakdown tables side by side — click a row to drill down */}
      <div className="grid grid-cols-2 gap-6">
        <BreakdownTable
          title="Detalle Ingresos"
          items={incomeBreakdown}
          emptyMessage="Sin registros de ingresos"
          amountClass="text-green-600"
          expandedAccount={expandedAccount}
          onToggle={toggleAccount}
        />
        <BreakdownTable
          title="Detalle Gastos"
          items={expenseBreakdown}
          emptyMessage="Sin registros de gastos"
          amountClass="text-destructive"
          expandedAccount={expandedAccount}
          onToggle={toggleAccount}
        />
      </div>
    </div>
  )
}
