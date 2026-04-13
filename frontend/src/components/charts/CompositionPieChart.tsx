import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer, type PieLabelRenderProps } from 'recharts'

const COLORS = [
  '#6366f1', '#f59e0b', '#10b981', '#ef4444', '#3b82f6',
  '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#84cc16',
]

interface PieSlice {
  name: string
  value: number
}

interface Props {
  title: string
  data: PieSlice[]
  selectedItems: string[]
  onSliceClick: (name: string) => void
}

interface CustomTooltipProps {
  active?: boolean
  payload?: Array<{ name: string; value: number; payload: PieSlice }>
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload?.length) return null
  const { name, value } = payload[0]
  const total = payload[0].payload
  // Calculate percentage from siblings (approximation; recharts passes full data via context)
  void total // used implicitly
  return (
    <div className="rounded-md border bg-background px-3 py-2 text-sm shadow-md">
      <p className="font-medium">{name}</p>
      <p className="text-muted-foreground">{value.toLocaleString('es-CL')}</p>
    </div>
  )
}

function renderPercentLabel(props: PieLabelRenderProps) {
  const { cx, cy, midAngle, innerRadius, outerRadius, percent } = props
  if ((percent ?? 0) < 0.05) return null
  const RADIAN = Math.PI / 180
  const cxNum = Number(cx ?? 0)
  const cyNum = Number(cy ?? 0)
  const irNum = Number(innerRadius ?? 0)
  const orNum = Number(outerRadius ?? 0)
  const angle = Number(midAngle ?? 0)
  const radius = irNum + (orNum - irNum) * 0.5
  const x = cxNum + radius * Math.cos(-angle * RADIAN)
  const y = cyNum + radius * Math.sin(-angle * RADIAN)
  return (
    <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central" fontSize={11} fontWeight={600}>
      {`${((percent ?? 0) * 100).toFixed(0)}%`}
    </text>
  )
}

export function CompositionPieChart({ title, data, selectedItems, onSliceClick }: Props) {
  const hasSelection = selectedItems.length > 0

  if (data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64">
        <p className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-4">{title}</p>
        <p className="text-sm text-muted-foreground">Sin datos</p>
      </div>
    )
  }

  return (
    <div>
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">{title}</h3>
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="45%"
            innerRadius={50}
            outerRadius={85}
            paddingAngle={2}
            onClick={(entry) => onSliceClick(entry.name as string)}
            style={{ cursor: 'pointer' }}
            labelLine={false}
            label={renderPercentLabel}
          >
            {data.map((entry, index) => {
              const isSelected = selectedItems.includes(entry.name)
              const dimmed = hasSelection && !isSelected
              return (
                <Cell
                  key={`cell-${index}`}
                  fill={COLORS[index % COLORS.length]}
                  opacity={dimmed ? 0.35 : 1}
                  stroke={isSelected ? '#fff' : 'transparent'}
                  strokeWidth={isSelected ? 2 : 0}
                />
              )
            })}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
          <Legend
            iconType="circle"
            iconSize={8}
            formatter={(value) => (
              <span className="text-xs text-foreground">{value}</span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
