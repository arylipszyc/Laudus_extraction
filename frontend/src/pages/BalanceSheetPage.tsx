import { Skeleton } from '@/components/ui/skeleton'
import { useBalanceSheet } from '@/hooks/useBalanceSheet'
import type { BalanceSheetRecord } from '@/types'

function getCategory(accountNumber: unknown): 'assets' | 'liabilities' | 'equity' | 'other' {
  const s = String(accountNumber ?? '')
  if (s.startsWith('1')) return 'assets'
  if (s.startsWith('2')) return 'liabilities'
  if (s.startsWith('3')) return 'equity'
  return 'other'
}

function formatAmount(amount: number): string {
  return amount.toLocaleString('es-CL')
}

interface GroupedRecords {
  assets: BalanceSheetRecord[]
  liabilities: BalanceSheetRecord[]
  equity: BalanceSheetRecord[]
  other: BalanceSheetRecord[]
}

function groupRecords(records: BalanceSheetRecord[]): GroupedRecords {
  const groups: GroupedRecords = { assets: [], liabilities: [], equity: [], other: [] }
  for (const r of records) {
    groups[getCategory(r.account_number)].push(r)
  }
  return groups
}

function netPosition(r: BalanceSheetRecord): number {
  return r.debit_balance - r.credit_balance
}

function RecordTable({ records, title }: { records: BalanceSheetRecord[]; title: string }) {
  if (records.length === 0) return null
  return (
    <div className="mb-6">
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">{title}</h3>
      <div className="rounded-md border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="text-left px-4 py-2 font-medium">Cuenta</th>
              <th className="text-left px-4 py-2 font-medium">Nombre</th>
              <th className="text-right px-4 py-2 font-medium">Debe</th>
              <th className="text-right px-4 py-2 font-medium">Haber</th>
              <th className="text-right px-4 py-2 font-medium">Saldo</th>
            </tr>
          </thead>
          <tbody>
            {records.map((r, i) => {
              const net = netPosition(r)
              return (
                <tr key={`${r.account_number}-${i}`} className="border-t hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-2 font-mono text-xs text-muted-foreground">{r.account_number}</td>
                  <td className="px-4 py-2">{r.account_name}</td>
                  <td className="px-4 py-2 text-right">{formatAmount(r.debit_balance)}</td>
                  <td className="px-4 py-2 text-right">{formatAmount(r.credit_balance)}</td>
                  <td className={`px-4 py-2 text-right font-medium ${net >= 0 ? 'text-foreground' : 'text-destructive'}`}>
                    {formatAmount(net)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function BalanceSheetPage() {
  const { data, isLoading, isError } = useBalanceSheet()

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

  const groups = groupRecords(data.data)

  const totalAssets = groups.assets.reduce((sum, r) => sum + netPosition(r), 0)
  const totalLiabilities = groups.liabilities.reduce((sum, r) => sum + (r.credit_balance - r.debit_balance), 0)
  const netPatrimony = totalAssets - totalLiabilities

  return (
    <div className="min-w-[1280px]">
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-1">Balance: Activos y Pasivos</h2>
        {data.meta.last_sync && (
          <p className="text-xs text-muted-foreground">Último sync: {data.meta.last_sync}</p>
        )}
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground mb-1">Total Activos</p>
          <p className="text-2xl font-bold text-foreground">{formatAmount(totalAssets)}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground mb-1">Total Pasivos</p>
          <p className="text-2xl font-bold text-foreground">{formatAmount(totalLiabilities)}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground mb-1">Patrimonio Neto</p>
          <p className={`text-2xl font-bold ${netPatrimony >= 0 ? 'text-green-600' : 'text-destructive'}`}>
            {formatAmount(netPatrimony)}
          </p>
        </div>
      </div>

      {/* Grouped tables */}
      <RecordTable records={groups.assets} title="Activos" />
      <RecordTable records={groups.liabilities} title="Pasivos" />
      <RecordTable records={groups.equity} title="Patrimonio" />
      {groups.other.length > 0 && <RecordTable records={groups.other} title="Otros" />}
    </div>
  )
}
