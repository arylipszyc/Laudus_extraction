import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from 'recharts'

export interface TimelinePeriodData {
  period: string
  label: string
  income: number
  expenses: number
}

interface Props {
  data: TimelinePeriodData[]
  selectedPeriods: string[]
  onBarClick: (period: string) => void
}

interface CustomTooltipProps {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-md border bg-background px-3 py-2 text-sm shadow-md">
      <p className="font-medium mb-1">{label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}: {p.value.toLocaleString('es-CL')}
        </p>
      ))}
    </div>
  )
}

export function TimelineBarChart({ data, selectedPeriods, onBarClick }: Props) {
  const hasSelection = selectedPeriods.length > 0

  return (
    <div>
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
        Evolución Mensual
      </h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart
          data={data}
          margin={{ top: 4, right: 16, left: 0, bottom: 4 }}
        >
          <XAxis dataKey="label" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={(v: number) => v.toLocaleString('es-CL')} tick={{ fontSize: 11 }} width={80} />
          <Tooltip content={<CustomTooltip />} />
          <Legend iconType="square" iconSize={10} formatter={(v) => <span className="text-xs">{v}</span>} />
          <Bar
            dataKey="income"
            name="Ingresos"
            fill="#22c55e"
            radius={[2, 2, 0, 0]}
            style={{ cursor: 'pointer' }}
            onClick={(barData) => {
              // Recharts v3: BarRectangleItem — original data is in .payload
              const period = (barData.payload as TimelinePeriodData)?.period
              if (period) onBarClick(period)
            }}
          >
            {data.map((entry, index) => {
              const isSelected = selectedPeriods.includes(entry.period)
              const dimmed = hasSelection && !isSelected
              return <Cell key={`inc-${index}`} fill="#22c55e" opacity={dimmed ? 0.35 : 1} />
            })}
          </Bar>
          <Bar
            dataKey="expenses"
            name="Gastos"
            fill="#ef4444"
            radius={[2, 2, 0, 0]}
            style={{ cursor: 'pointer' }}
            onClick={(barData) => {
              const period = (barData.payload as TimelinePeriodData)?.period
              if (period) onBarClick(period)
            }}
          >
            {data.map((entry, index) => {
              const isSelected = selectedPeriods.includes(entry.period)
              const dimmed = hasSelection && !isSelected
              return <Cell key={`exp-${index}`} fill="#ef4444" opacity={dimmed ? 0.35 : 1} />
            })}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
