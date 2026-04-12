import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { Skeleton } from '@/components/ui/skeleton'
import { useLedger } from '@/hooks/useLedger'
import type { LedgerEntryRecord } from '@/types'

function getLedgerCategory(accountNumber: unknown): 'income' | 'expenses' | 'other' {
  const s = String(accountNumber ?? '')
  if (s.startsWith('4')) return 'income'
  if (s.startsWith('5') || s.startsWith('6')) return 'expenses'
  return 'other'
}

function formatAmount(amount: number, currency: string = 'CLP'): string {
  const formatted = amount.toLocaleString('es-CL')
  return currency !== 'CLP' ? `${formatted} ${currency}` : formatted
}

interface CategoryBreakdown {
  accountNumber: string
  description: string
  total: number
  currency: string
}

function buildBreakdown(records: LedgerEntryRecord[], type: 'income' | 'expenses'): CategoryBreakdown[] {
  const map = new Map<string, { total: number; currency: string }>()
  for (const r of records) {
    const cat = getLedgerCategory(r.accountnumber)
    if (cat !== type) continue
    const amount = type === 'income' ? r.credit - r.debit : r.debit - r.credit
    const existing = map.get(r.accountnumber)
    if (existing) {
      existing.total += amount
    } else {
      map.set(r.accountnumber, { total: amount, currency: r.currencycode })
    }
  }
  return Array.from(map.entries())
    .map(([accountNumber, { total, currency }]) => ({ accountNumber, description: accountNumber, total, currency }))
    .sort((a, b) => b.total - a.total)
}

export function IncomeExpensesPage() {
  const { data, isLoading, isError } = useLedger()

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
    .filter((r) => getLedgerCategory(r.accountnumber) === 'income')
    .reduce((sum, r) => sum + (r.credit - r.debit), 0)

  const totalExpenses = records
    .filter((r) => getLedgerCategory(r.accountnumber) === 'expenses')
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
            <Tooltip formatter={(v) => typeof v === 'number' ? v.toLocaleString('es-CL') : v} />
            <Bar dataKey="value">
              <Cell key="income" fill="#22c55e" />
              <Cell key="expenses" fill="#ef4444" />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Breakdown tables side by side */}
      <div className="grid grid-cols-2 gap-6">
        {/* Income breakdown */}
        <div>
          <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
            Detalle Ingresos
          </h3>
          {incomeBreakdown.length === 0 ? (
            <p className="text-sm text-muted-foreground">Sin registros de ingresos</p>
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
                  {incomeBreakdown.map((item) => (
                    <tr key={item.accountNumber} className="border-t hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-2 font-mono text-xs text-muted-foreground">{item.accountNumber}</td>
                      <td className="px-4 py-2 text-right font-medium text-green-600">
                        {formatAmount(item.total, item.currency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Expense breakdown */}
        <div>
          <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
            Detalle Gastos
          </h3>
          {expenseBreakdown.length === 0 ? (
            <p className="text-sm text-muted-foreground">Sin registros de gastos</p>
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
                  {expenseBreakdown.map((item) => (
                    <tr key={item.accountNumber} className="border-t hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-2 font-mono text-xs text-muted-foreground">{item.accountNumber}</td>
                      <td className="px-4 py-2 text-right font-medium text-destructive">
                        {formatAmount(item.total, item.currency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
