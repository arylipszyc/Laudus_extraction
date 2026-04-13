import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer, type PieLabelRenderProps } from 'recharts'
import { buildPieDataByCat2, buildPieDataByCat3 } from '@/utils/ledgerAnalytics'
import type { LedgerEntryRecord } from '@/types'

const COLORS = [
  '#6366f1', '#f59e0b', '#10b981', '#ef4444', '#3b82f6',
  '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#84cc16',
]

interface CustomTooltipProps {
  active?: boolean
  payload?: Array<{ name: string; value: number }>
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload?.length) return null
  const { name, value } = payload[0]
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

interface Props {
  title: string
  records: LedgerEntryRecord[]
  type: 'income' | 'expenses'
  /** Cat2 currently drilled into (null = top level). Controlled by parent. */
  drillCat2: string | null
  /** Cat3 currently selected (null = none). Controlled by parent. */
  drillCat3: string | null
  onDrillCat2: (cat2: string | null) => void
  onDrillCat3: (cat3: string | null) => void
}

export function CompositionPieChart({
  title, records, type, drillCat2, drillCat3, onDrillCat2, onDrillCat3,
}: Props) {
  const data = drillCat2
    ? buildPieDataByCat3(records, type, drillCat2)
    : buildPieDataByCat2(records, type)

  const hasSelection = drillCat2 !== null && drillCat3 !== null

  function handleClick(name: string) {
    if (drillCat2 === null) {
      // At Cat2 level — drill into Cat3 for this Cat2
      onDrillCat2(name)
    } else {
      // At Cat3 level — toggle Cat3 filter
      onDrillCat3(drillCat3 === name ? null : name)
    }
  }

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
      <div className="flex items-center gap-2 mb-2 min-h-[1.5rem]">
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide truncate">
          {drillCat2 ? `${title} › ${drillCat2}` : title}
        </h3>
        {drillCat2 && (
          <button
            onClick={() => { onDrillCat2(null); onDrillCat3(null) }}
            className="shrink-0 text-xs text-primary underline hover:text-primary/70 transition-colors"
          >
            Volver
          </button>
        )}
      </div>
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
            onClick={(entry) => handleClick(entry.name as string)}
            style={{ cursor: 'pointer' }}
            labelLine={false}
            label={renderPercentLabel}
          >
            {data.map((entry, index) => {
              const isSelected = drillCat3 === entry.name
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
