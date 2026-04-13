import { useState } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { useLedger } from '@/hooks/useLedger'
import { useChartFilters } from '@/hooks/useChartFilters'
import { useFilters } from '@/contexts/FilterContext'
import { getLedgerCategory, buildTimeline, filterByEntity } from '@/utils/ledgerAnalytics'
import { CompositionPieChart } from '@/components/charts/CompositionPieChart'
import { TimelineBarChart } from '@/components/charts/TimelineBarChart'
import { IncomeExpensesDrilldown } from '@/components/charts/IncomeExpensesDrilldown'
import type { LedgerEntryRecord } from '@/types'

function formatAmount(amount: number): string {
  return amount.toLocaleString('es-CL')
}

function applyDrillFilter(
  records: LedgerEntryRecord[],
  cat2: string | null,
  cat3: string | null,
): LedgerEntryRecord[] {
  if (!cat2) return records
  return records.filter(r => {
    const recordCat2 = r.Categoria2 || r.Categoria1 || ''
    if (recordCat2 !== cat2) return false
    if (cat3 && (r.Categoria3 || 'Sin subcategoría') !== cat3) return false
    return true
  })
}

export function IncomeExpensesPage() {
  const { entity } = useFilters()
  const { data, isLoading, isError } = useLedger()
  const filters = useChartFilters()

  // Pie drill state — controlled here so parent can reset them
  const [expDrillCat2, setExpDrillCat2] = useState<string | null>(null)
  const [expDrillCat3, setExpDrillCat3] = useState<string | null>(null)
  const [incDrillCat2, setIncDrillCat2] = useState<string | null>(null)
  const [incDrillCat3, setIncDrillCat3] = useState<string | null>(null)

  // ── Loading / error / empty ─────────────────────────────────────────────────

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

  // Apply entity filter client-side
  const allRecords = filterByEntity(data.data, entity)

  // ── Totals (from all entity records, unfiltered) ────────────────────────────

  const totalIncome = allRecords
    .filter(r => getLedgerCategory(r.accountnumber, r.Categoria1, r.Categoria2) === 'income')
    .reduce((s, r) => s + (r.credit - r.debit), 0)

  const totalExpenses = allRecords
    .filter(r => getLedgerCategory(r.accountnumber, r.Categoria1, r.Categoria2) === 'expenses')
    .reduce((s, r) => s + (r.debit - r.credit), 0)

  const netResult = totalIncome - totalExpenses

  // ── Period-filtered records (for charts and drilldowns) ─────────────────────

  const periodFiltered = filters.applyFilters(allRecords)
  const timelineData = buildTimeline(allRecords)

  // Pie charts see period-filtered records and compute Cat2/Cat3 data internally
  // Drilldown tables are further filtered by pie drill state (per type)
  const expenseRecords = applyDrillFilter(periodFiltered, expDrillCat2, expDrillCat3)
  const incomeRecords  = applyDrillFilter(periodFiltered, incDrillCat2, incDrillCat3)

  // ── Active filter chips ─────────────────────────────────────────────────────

  const hasAnyFilter = filters.hasActiveFilters || expDrillCat2 !== null || incDrillCat2 !== null

  const periodChips = filters.selectedPeriods.map(p => ({
    label: timelineData.find(t => t.period === p)?.label ?? p,
    onRemove: () => filters.togglePeriod(p),
  }))

  const drillChips = [
    expDrillCat2 && { label: `Gastos: ${expDrillCat3 ?? expDrillCat2}`, onRemove: () => { setExpDrillCat2(null); setExpDrillCat3(null) } },
    incDrillCat2 && { label: `Ingresos: ${incDrillCat3 ?? incDrillCat2}`, onRemove: () => { setIncDrillCat2(null); setIncDrillCat3(null) } },
  ].filter(Boolean) as { label: string; onRemove: () => void }[]

  const activeChips = [...periodChips, ...drillChips]

  function resetAll() {
    filters.resetFilters()
    setExpDrillCat2(null); setExpDrillCat3(null)
    setIncDrillCat2(null); setIncDrillCat3(null)
  }

  return (
    <div className="min-w-[1280px] space-y-8">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold mb-1">Ingresos y Gastos</h2>
        {data.meta.last_sync && (
          <p className="text-xs text-muted-foreground">Último sync: {data.meta.last_sync}</p>
        )}
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
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

      {/* Charts row */}
      <div className="grid grid-cols-3 gap-6 rounded-lg border bg-card p-6">
        <CompositionPieChart
          title="Composición Gastos"
          records={periodFiltered}
          type="expenses"
          drillCat2={expDrillCat2}
          drillCat3={expDrillCat3}
          onDrillCat2={setExpDrillCat2}
          onDrillCat3={setExpDrillCat3}
        />
        <CompositionPieChart
          title="Composición Ingresos"
          records={periodFiltered}
          type="income"
          drillCat2={incDrillCat2}
          drillCat3={incDrillCat3}
          onDrillCat2={setIncDrillCat2}
          onDrillCat3={setIncDrillCat3}
        />
        <TimelineBarChart
          data={timelineData}
          selectedPeriods={filters.selectedPeriods}
          onBarClick={filters.togglePeriod}
        />
      </div>

      {/* Active filters + reset */}
      {hasAnyFilter && (
        <div className="flex items-center gap-2 flex-wrap">
          {activeChips.map((chip, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 rounded-full border bg-muted px-3 py-1 text-xs font-medium"
            >
              {chip.label}
              <button
                onClick={chip.onRemove}
                className="ml-1 rounded-full hover:bg-muted-foreground/20 p-0.5 leading-none"
                aria-label={`Quitar filtro ${chip.label}`}
              >
                ✕
              </button>
            </span>
          ))}
          <button
            onClick={resetAll}
            className="ml-2 text-xs text-muted-foreground underline hover:text-foreground transition-colors"
          >
            Resetear filtros
          </button>
        </div>
      )}

      {/* Drill-down tables */}
      <div className="grid grid-cols-2 gap-6">
        <IncomeExpensesDrilldown
          records={expenseRecords}
          type="expenses"
          title="Detalle Gastos"
        />
        <IncomeExpensesDrilldown
          records={incomeRecords}
          type="income"
          title="Detalle Ingresos"
        />
      </div>
    </div>
  )
}
