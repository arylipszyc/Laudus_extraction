import { useFilters, type DatePreset } from '@/contexts/FilterContext'

const PRESETS: { label: string; value: Exclude<DatePreset, 'custom'> }[] = [
  { label: 'Mes', value: 'month' },
  { label: 'Trimestre', value: 'quarter' },
  { label: 'Año', value: 'year' },
]

export function DateRangeFilter() {
  const { datePreset, dateFrom, dateTo, setPreset, setCustomRange } = useFilters()

  return (
    <div className="flex items-center gap-2">
      <label className="text-sm font-medium text-muted-foreground whitespace-nowrap">Período:</label>
      <div className="flex gap-1">
        {PRESETS.map(({ label, value }) => (
          <button
            key={value}
            type="button"
            onClick={() => setPreset(value)}
            className={`text-sm px-3 py-1 rounded-md border transition-colors ${
              datePreset === value
                ? 'bg-primary text-primary-foreground border-primary'
                : 'bg-background text-muted-foreground border-input hover:bg-accent hover:text-accent-foreground'
            }`}
          >
            {label}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setCustomRange(dateFrom, dateTo)}
          className={`text-sm px-3 py-1 rounded-md border transition-colors ${
            datePreset === 'custom'
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-background text-muted-foreground border-input hover:bg-accent hover:text-accent-foreground'
          }`}
        >
          Personalizado
        </button>
      </div>
      {datePreset === 'custom' && (
        <div className="flex items-center gap-1">
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setCustomRange(e.target.value, dateTo)}
            className="text-sm border rounded-md px-2 py-1 bg-background focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <span className="text-muted-foreground text-sm">—</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setCustomRange(dateFrom, e.target.value)}
            className="text-sm border rounded-md px-2 py-1 bg-background focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      )}
    </div>
  )
}
