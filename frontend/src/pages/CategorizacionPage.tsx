import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { bulkCategorize, getPendingCategorization, type PendingTx } from '@/services/categorizacion'
import { CategoryAutocomplete } from '@/components/CategoryAutocomplete'

// Las compras caen a Suspense hasta que el contador les pone cuenta. El batch confirma
// justo las que ya salieron de Suspense (§tc_correction.SUSPENSE_ACCOUNT).
const SUSPENSE = 'Expenses:EAG:Suspense'

const fmt = (n: number | null) =>
  n == null ? '—' : new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(n)

// Goal B (§10.2): señal de color de la recomendación, para que el contador vea de un vistazo
// dónde fijarse. El color es advisory — el contador confirma SIEMPRE; nada se auto-confirma.
type Color = 'green' | 'yellow' | 'red'

const COLOR_RANK: Record<Color, number> = { red: 0, yellow: 1, green: 2 }

const COLOR_STYLE: Record<Color, { dot: string; label: string }> = {
  green: { dot: 'bg-emerald-500', label: 'text-emerald-700' },
  yellow: { dot: 'bg-amber-500', label: 'text-amber-700' },
  red: { dot: 'bg-red-500', label: 'text-red-700' },
}

// Valida contra el set conocido (no solo null): un color inesperado de la meta (editada a mano, o
// un color futuro) cae a 'red' en vez de reventar el render con COLOR_STYLE[undefined].
const colorOf = (tx: PendingTx): Color => {
  const c = tx.current_color
  return c === 'green' || c === 'yellow' || c === 'red' ? c : 'red'
}

function ColorBadge({ color }: { color: Color }) {
  const s = COLOR_STYLE[color]
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${s.label}`} data-testid="color-badge" data-color={color}>
      <span className={`inline-block h-2.5 w-2.5 rounded-full ${s.dot}`} />
    </span>
  )
}

/**
 * Story 9.8 — revisión inline de categorías pendientes (subsume 5.2). Lista las tx con
 * categoría sugerida/pendiente y permite al contador confirmar/corregir (PATCH de 9.7).
 * Goal B (§10.2): badge de color por ítem + rojos arriba (advisory; el contador confirma SIEMPRE).
 */
export function CategorizacionPage() {
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['categorization-pending'],
    queryFn: getPendingCategorization,
  })

  // Categoría por fila, editable; la sube el consumidor para que el botón batch sepa cuáles
  // ya se categorizaron. Los ítems en Suspense arrancan EN BLANCO (estar acá ya implica Suspense);
  // una sugerencia real (no-Suspense) sí se muestra para confirmarla.
  const [cats, setCats] = useState<Record<string, string>>({})
  const catOf = (tx: PendingTx) => {
    if (tx.tx_id in cats) return cats[tx.tx_id]
    const cur = tx.current_category ?? ''
    return cur === SUSPENSE ? '' : cur
  }

  // Rojos arriba (lo que el contador debe decidir él); empate → mantiene el orden del backend.
  const sorted = data && [...data].sort((a, b) => COLOR_RANK[colorOf(a)] - COLOR_RANK[colorOf(b)])

  // Las ya categorizadas (fuera de Suspense) son las que el botón confirma en un solo commit.
  const toConfirm = (sorted ?? []).filter((tx) => {
    const c = catOf(tx).trim()
    return c !== '' && c !== SUSPENSE
  })

  const bulk = useMutation({
    mutationFn: () =>
      bulkCategorize(toConfirm.map((tx) => ({ tx_id: tx.tx_id, category_account: catOf(tx).trim() }))),
    onSuccess: () => {
      setCats({})
      qc.invalidateQueries({ queryKey: ['categorization-pending'] })
    },
  })

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Categorías pendientes</h1>
        {toConfirm.length > 0 && (
          <Button onClick={() => bulk.mutate()} disabled={bulk.isPending}>
            {bulk.isPending ? 'Confirmando…' : `Confirmar categorizadas (${toConfirm.length})`}
          </Button>
        )}
      </div>
      <p className="text-sm text-muted-foreground">
        Transacciones con categoría sugerida automáticamente. Confirmá la sugerida o corregí la cuenta.
        Los <span className="text-red-700 font-medium">rojos</span> son los que conviene revisar primero.
        El botón <span className="font-medium">Confirmar categorizadas</span> confirma en un solo commit
        las que ya sacaste de Suspense.
      </p>

      {bulk.error && <p className="text-sm text-destructive">{(bulk.error as Error).message}</p>}
      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error && <p className="text-sm text-destructive">{(error as Error).message}</p>}
      {data && data.length === 0 && (
        <Card className="p-6"><p className="text-sm text-muted-foreground">Nada pendiente. 🎉</p></Card>
      )}

      {sorted?.map((tx) => (
        <PendingRow key={tx.tx_id} tx={tx} value={catOf(tx)}
          onChange={(v) => setCats((prev) => ({ ...prev, [tx.tx_id]: v }))} />
      ))}
    </div>
  )
}

function PendingRow({ tx, value, onChange }: {
  tx: PendingTx
  value: string
  onChange: (v: string) => void
}) {
  return (
    <Card className="p-4 flex flex-wrap items-end gap-3">
      <div className="flex-1 min-w-[200px]">
        <p className="font-medium flex items-center gap-2">
          <ColorBadge color={colorOf(tx)} />
          {tx.narration || '(sin descripción)'}
        </p>
        <p className="text-sm text-muted-foreground">
          {tx.date} · {fmt(tx.amount)} ·{' '}
          <span className="text-amber-600">⚠ {tx.current_match_source ?? 'pendiente'}</span>
        </p>
      </div>
      <div className="flex-1 min-w-[240px]">
        <label className="block text-xs text-muted-foreground mb-1">Cuenta de categoría</label>
        <CategoryAutocomplete value={value} onChange={onChange} />
      </div>
    </Card>
  )
}
