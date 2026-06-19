import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import {
  validateBalance,
  type CartolaCanonical,
  type BalanceDiscrepancyError,
  type ValidateBalanceResult,
} from '@/services/cartolas'

const MIN_JUSTIFICATION = 20

const fmt = (n: number, currency: string) =>
  new Intl.NumberFormat('es-CL', { style: 'currency', currency }).format(n)

/**
 * Story 9.9 — panel de validación de balance.
 * discrepancia = closing - opening - Σ transactions (AC2). Confirmar habilitado solo si
 * discrepancia=0, o si hay override con justificación ≥20 chars (AC4).
 */
export function BalanceValidationPanel({
  canonical,
  batchId,
  onValidated,
}: {
  canonical: CartolaCanonical
  batchId: string
  onValidated: (r: ValidateBalanceResult) => void
}) {
  const currency = canonical.currency
  const [opening, setOpening] = useState(canonical.balances.opening)
  const [closing, setClosing] = useState(canonical.balances.closing)
  const [overrideMode, setOverrideMode] = useState(false)
  const [justification, setJustification] = useState('')

  const sumTx = canonical.transactions.reduce((acc, t) => acc + Number.parseFloat(t.amount || '0'), 0)
  const discrepancy = Number.parseFloat(closing || '0') - Number.parseFloat(opening || '0') - sumTx
  const balanced = Math.abs(discrepancy) < 0.5

  const mutation = useMutation({
    mutationFn: () =>
      validateBalance(batchId, {
        opening,
        closing,
        override_justification: overrideMode ? justification.trim() : null,
      }),
    onSuccess: onValidated,
  })

  const canConfirm =
    !mutation.isPending &&
    (balanced || (overrideMode && justification.trim().length >= MIN_JUSTIFICATION))

  const err = mutation.error as BalanceDiscrepancyError | null

  return (
    <div className="space-y-4 border-t pt-4">
      <h3 className="text-sm font-medium">Validación de balance</h3>

      <div className="grid grid-cols-3 gap-3">
        <Field label="Saldo apertura" value={opening} onChange={setOpening} />
        <div>
          <label className="block text-sm font-medium mb-1">Σ Transacciones</label>
          <div className="px-3 py-2 rounded-md bg-muted text-sm font-mono">{fmt(sumTx, currency)}</div>
        </div>
        <Field label="Saldo cierre" value={closing} onChange={setClosing} />
      </div>

      <p className={`text-sm font-medium ${balanced ? 'text-green-600' : 'text-destructive'}`}>
        Discrepancia: {fmt(discrepancy, currency)} {balanced ? '✓ cuadra' : '✗ no cuadra'}
      </p>

      {!balanced && (
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={overrideMode} onChange={(e) => setOverrideMode(e.target.checked)} />
            No puedo cuadrar — override con justificación
          </label>
          {overrideMode && (
            <div>
              <textarea
                value={justification}
                onChange={(e) => setJustification(e.target.value)}
                rows={3}
                placeholder="Justificación (mínimo 20 caracteres) — queda en el audit trail de git"
                className="w-full border rounded-md px-3 py-2 bg-background text-sm"
              />
              <p className="text-xs text-muted-foreground">
                {justification.trim().length}/{MIN_JUSTIFICATION} caracteres
              </p>
            </div>
          )}
        </div>
      )}

      {err && (
        <p className="text-sm text-destructive">
          <strong>{err.code}:</strong> {err.message}
          {err.diff !== undefined && <span> (diff {fmt(err.diff, currency)})</span>}
        </p>
      )}

      <Button onClick={() => mutation.mutate()} disabled={!canConfirm}>
        {mutation.isPending
          ? 'Confirmando…'
          : overrideMode && !balanced
            ? 'Confirmar override'
            : 'Confirmar validación'}
      </Button>
    </div>
  )
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1">{label}</label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full border rounded-md px-3 py-2 bg-background text-sm font-mono"
      />
    </div>
  )
}
