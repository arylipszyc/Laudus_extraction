import { Skeleton } from '@/components/ui/skeleton'
import { useLedger } from '@/hooks/useLedger'
import { useChartFilters } from '@/hooks/useChartFilters'
import { useFilters } from '@/contexts/FilterContext'
import { getLedgerCategory, buildPieData, buildTimeline, filterByEntity } from '@/utils/ledgerAnalytics'
import { CompositionPieChart } from '@/components/charts/CompositionPieChart'
import { TimelineBarChart } from '@/components/charts/TimelineBarChart'
import { IncomeExpensesDrilldown } from '@/components/charts/IncomeExpensesDrilldown'

function formatAmount(amount: number): string {
  return amount.toLocaleString('es-CL')
}

export function IncomeExpensesPage() {
  const { entity } = useFilters()
  const { data, isLoading, isError } = useLedger()
  const filters = useChartFilters()

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

  // Apply entity filter client-side (all data is in EAG sheet; entity name appears in Categoria1)
  const allRecords = filterByEntity(data.data, entity)

  // ── Totals (always from unfiltered records) ─────────────────────────────────

  const totalIncome = allRecords
    .filter(r => getLedgerCategory(r.accountnumber, r.Categoria1) === 'income')
    .reduce((s, r) => s + (r.credit - r.debit), 0)

  const totalExpenses = allRecords
    .filter(r => getLedgerCategory(r.accountnumber, r.Categoria1) === 'expenses')
    .reduce((s, r) => s + (r.debit - r.credit), 0)

  const netResult = totalIncome - totalExpenses

  // ── Chart data (from unfiltered records) ────────────────────────────────────

  const expensePieData = buildPieData(allRecords, 'expenses')
  const incomePieData = buildPieData(allRecords, 'income')
  const timelineData = buildTimeline(allRecords)

  // ── Filtered records for drill-down table ───────────────────────────────────

  const filteredRecords = filters.applyFilters(allRecords)

  // ── Active filter chips ─────────────────────────────────────────────────────

  const activeChips = [
    ...filters.selectedCategories.map(c => ({ label: c, onRemove: () => filters.toggleCategory(c) })),
    ...filters.selectedPeriods.map(p => ({
      label: timelineData.find(t => t.period === p)?.label ?? p,
      onRemove: () => filters.togglePeriod(p),
    })),
  ]

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
          data={expensePieData}
          selectedItems={filters.selectedCategories}
          onSliceClick={filters.toggleCategory}
        />
        <CompositionPieChart
          title="Composición Ingresos"
          data={incomePieData}
          selectedItems={filters.selectedCategories}
          onSliceClick={filters.toggleCategory}
        />
        <TimelineBarChart
          data={timelineData}
          selectedPeriods={filters.selectedPeriods}
          onBarClick={filters.togglePeriod}
        />
      </div>

      {/* Active filters + reset */}
      {filters.hasActiveFilters && (
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
            onClick={filters.resetFilters}
            className="ml-2 text-xs text-muted-foreground underline hover:text-foreground transition-colors"
          >
            Resetear filtros
          </button>
        </div>
      )}

      {/* Drill-down tables */}
      <div className="grid grid-cols-2 gap-6">
        <IncomeExpensesDrilldown
          records={filteredRecords}
          type="expenses"
          title="Detalle Gastos"
        />
        <IncomeExpensesDrilldown
          records={filteredRecords}
          type="income"
          title="Detalle Ingresos"
        />
      </div>
    </div>
  )
}
