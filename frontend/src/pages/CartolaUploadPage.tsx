import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { listBankAccounts } from '@/services/bankAccounts'
import {
  useCartolaUploadMutation,
  useCartolaStatus,
} from '@/hooks/useCartolaUpload'
import type { CartolaError, CartolaCanonical, ValidateBalanceResult, TcCuadre } from '@/services/cartolas'
import { BalanceValidationPanel } from '@/components/BalanceValidationPanel'

const MAX_PDF_BYTES = 20 * 1024 * 1024

function formatAmount(value: string, currency: string): string {
  const n = Number.parseFloat(value)
  if (Number.isNaN(n)) return value
  return new Intl.NumberFormat('es-CL', { style: 'currency', currency }).format(n)
}

export function CartolaUploadPage() {
  const [bankAccountId, setBankAccountId] = useState('')
  const [pdfFile, setPdfFile] = useState<File | null>(null)
  const [batchId, setBatchId] = useState<string | null>(null)
  const [clientError, setClientError] = useState<string | null>(null)

  const accountsQuery = useQuery({
    queryKey: ['bankAccounts'],
    queryFn: listBankAccounts,
  })

  const uploadMutation = useCartolaUploadMutation()
  const statusQuery = useCartolaStatus(batchId)

  const canSubmit =
    bankAccountId !== '' &&
    pdfFile !== null &&
    !uploadMutation.isPending &&
    batchId === null

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    setClientError(null)
    const f = e.target.files?.[0] ?? null
    if (f && f.size > MAX_PDF_BYTES) {
      setClientError(`El archivo excede 20MB (${(f.size / 1024 / 1024).toFixed(1)}MB)`)
      setPdfFile(null)
      return
    }
    if (f && f.type && f.type !== 'application/pdf') {
      setClientError('El archivo debe ser PDF')
      setPdfFile(null)
      return
    }
    setPdfFile(f)
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!pdfFile || !bankAccountId) return
    setClientError(null)
    uploadMutation.mutate(
      { pdfFile, bankAccountId },
      {
        onSuccess: (data) => setBatchId(data.batch_id),
      },
    )
  }

  function reset() {
    setBatchId(null)
    setPdfFile(null)
    setBankAccountId('')
    setClientError(null)
    uploadMutation.reset()
  }

  const uploadError = uploadMutation.error as CartolaError | null

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <h1 className="text-2xl font-semibold">Cargar Cartola</h1>

      {batchId === null && (
        <Card className="p-6">
          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Cuenta bancaria</label>
              {accountsQuery.isLoading ? (
                <Skeleton className="h-10 w-full" />
              ) : accountsQuery.error ? (
                <p className="text-sm text-destructive">
                  Error cargando cuentas bancarias.
                </p>
              ) : (
                <select
                  value={bankAccountId}
                  onChange={(e) => setBankAccountId(e.target.value)}
                  className="w-full border rounded-md px-3 py-2 bg-background"
                >
                  <option value="">— Seleccionar cuenta —</option>
                  {(accountsQuery.data ?? [])
                    .filter((a) => a.active)
                    .map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.bank_name ?? '(sin banco)'} — {a.account_name ?? a.account_number} ({a.account_currency})
                      </option>
                    ))}
                </select>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Archivo PDF (≤ 20MB)</label>
              <input
                type="file"
                accept="application/pdf"
                onChange={onFileChange}
                className="w-full text-sm"
              />
              {pdfFile && (
                <p className="text-xs text-muted-foreground mt-1">
                  {pdfFile.name} ({(pdfFile.size / 1024).toFixed(0)} KB)
                </p>
              )}
            </div>

            {clientError && (
              <p className="text-sm text-destructive">{clientError}</p>
            )}

            {uploadError && (
              <p className="text-sm text-destructive">
                <strong>{uploadError.code}:</strong> {uploadError.message}
              </p>
            )}

            <Button type="submit" disabled={!canSubmit}>
              {uploadMutation.isPending ? 'Subiendo…' : 'Subir'}
            </Button>
          </form>
        </Card>
      )}

      {batchId !== null && (
        <CartolaResult batchId={batchId} statusQuery={statusQuery} onReset={reset} />
      )}
    </div>
  )
}

function CartolaResult({
  batchId,
  statusQuery,
  onReset,
}: {
  batchId: string
  statusQuery: ReturnType<typeof useCartolaStatus>
  onReset: () => void
}) {
  const { data, error } = statusQuery

  if (error) {
    return (
      <Card className="p-6 space-y-3">
        <p className="text-sm text-destructive">
          <strong>Error:</strong> {error.message}
        </p>
        <Button variant="outline" onClick={onReset}>
          Volver
        </Button>
      </Card>
    )
  }

  if (!data || data.status === 'processing') {
    return (
      <Card className="p-6 space-y-3">
        <p className="text-sm">Procesando cartola… (batch_id: {batchId})</p>
        <Skeleton className="h-32 w-full" />
      </Card>
    )
  }

  if (data.status === 'failed') {
    return (
      <Card className="p-6 space-y-3">
        <p className="text-sm text-destructive">
          <strong>Extracción falló</strong>
          {data.error && (
            <span>
              {' '}
              ({data.error.code}: {data.error.message})
            </span>
          )}
        </p>
        <Button variant="outline" onClick={onReset}>
          Reintentar
        </Button>
      </Card>
    )
  }

  // status === 'ready'
  const c = data.canonical!
  return <CartolaReady c={c} batchId={batchId} onReset={onReset} alreadyImported={!!data.already_imported} />
}

function CartolaReady({
  c,
  batchId,
  onReset,
  alreadyImported,
}: {
  c: CartolaCanonical | null
  batchId: string
  onReset: () => void
  alreadyImported: boolean
}) {
  const [validated, setValidated] = useState<ValidateBalanceResult | null>(null)
  if (!c) return null

  if (validated) {
    const pending = c.transactions.length  // todas pendientes de categorizar en v1 (Noop predictor)
    return (
      <Card className="p-6 space-y-3">
        <p className="text-sm text-green-600">
          ✅ Cartola importada — {c.transactions.length} transacciones, {pending} pendientes de categorizar
          {validated.override && ' · (override con justificación registrado en git)'}
        </p>
        {validated.cuadre && <CuadrePanel q={validated.cuadre} currency={c.currency} />}
        <Button variant="outline" onClick={onReset}>Subir otra</Button>
      </Card>
    )
  }

  return (
    <Card className="p-6 space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-xl font-semibold">
          Cartola extraída — {c.source.account_label}
        </h2>
        <Button variant="outline" size="sm" onClick={onReset}>
          Subir otra
        </Button>
      </div>

      {alreadyImported && (
        <div className="rounded-md border border-amber-400 bg-amber-50 p-3 text-sm text-amber-800">
          ⚠ <strong>Esta cartola ya fue importada</strong> ({c.source.account_label} · {c.period.end.slice(0, 7)}).
          Volver a confirmarla <strong>sobrescribe</strong> el archivo y <strong>resetea las categorizaciones</strong>
          que hayas hecho de este mes. Si no querés eso, apretá "Subir otra".
        </div>
      )}

      <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
        <dt className="text-muted-foreground">Banco</dt>
        <dd>{c.source.bank_name}</dd>
        <dt className="text-muted-foreground">Período</dt>
        <dd>
          {c.period.start} → {c.period.end}
        </dd>
        <dt className="text-muted-foreground">Saldo apertura</dt>
        <dd>{formatAmount(c.balances.opening, c.currency)}</dd>
        <dt className="text-muted-foreground">Saldo cierre</dt>
        <dd>{formatAmount(c.balances.closing, c.currency)}</dd>
        <dt className="text-muted-foreground">Transacciones</dt>
        <dd>{c.transactions.length}</dd>
      </dl>

      {c.extraction.warnings.length > 0 && (
        <div>
          <h3 className="text-sm font-medium mb-2">
            Warnings ({c.extraction.warnings.length})
          </h3>
          <ul className="space-y-1 text-xs">
            {c.extraction.warnings.map((w, i) => (
              <li
                key={i}
                className="px-2 py-1 rounded-sm bg-amber-50 border border-amber-200"
              >
                <span className="font-mono font-semibold">{w.code}</span>
                {w.line_no !== null && <span> · línea {w.line_no}</span>}
                <span> · {w.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <details className="text-xs">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
          Transacciones ({c.transactions.length})
        </summary>
        <table className="mt-2 w-full text-left">
          <thead>
            <tr className="border-b">
              <th className="py-1 pr-2">#</th>
              <th className="py-1 pr-2">Fecha</th>
              <th className="py-1 pr-2">Descripción</th>
              <th className="py-1 pr-2 text-right">Monto</th>
            </tr>
          </thead>
          <tbody>
            {c.transactions.map((tx) => (
              <tr key={tx.line_no} className="border-b">
                <td className="py-1 pr-2 text-muted-foreground">{tx.line_no}</td>
                <td className="py-1 pr-2">{tx.date}</td>
                <td className="py-1 pr-2">{tx.description}</td>
                <td className="py-1 pr-2 text-right font-mono">
                  {formatAmount(tx.amount, tx.currency)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>

      <BalanceValidationPanel canonical={c} batchId={batchId} onValidated={setValidated}
        alreadyImported={alreadyImported} />

      <p className="text-xs text-muted-foreground">
        batch_id: <code className="font-mono">{batchId}</code> · staging:{' '}
        <code className="font-mono">ledger/imports/cartolas/_staging/</code>
      </p>
    </Card>
  )
}

/**
 * Cuadre de la cartola contra la contabilidad (post-confirmación) — C1–C5 (Story 6.6, diseño Valentina).
 * C1 (🔴) TC:Real al cierre == −cierre; C2 (🟡) apertura == cierre anterior; C3 (🔴) integridad del
 * asiento; C4 (🟡) pago vs Laudus; C5 (🟡) lump residual. C1/C3 son críticos (rojos).
 */
function CuadrePanel({ q, currency }: { q: TcCuadre; currency: string }) {
  const [open, setOpen] = useState(false)
  const dot = (ok: boolean, critical: boolean) => (ok ? '🟢' : critical ? '🔴' : '🟡')
  const check = (code: string, label: string, ok: boolean, critical: boolean) => (
    <>
      <span className="w-6 text-center">{dot(ok, critical)}</span>
      <span className="text-muted-foreground"><span className="font-mono">{code}</span> · {label}</span>
    </>
  )
  return (
    <div className="border-t pt-3 space-y-2 text-sm">
      <h3 className="font-medium">Cuadre con la contabilidad</h3>
      <div className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 items-baseline">
        {check('C1', `deuda TC:Real ${formatAmount(String(q.currency === 'CLP' ? q.tc_real_balance : q.tc_real_native), q.currency)} == −cierre ${formatAmount(String(q.closing), q.currency)}`, q.c1_ok, true)}
        {check('C2', q.c2_ok ? 'apertura == cierre del mes anterior' : (q.c2_reason ?? 'apertura ≠ cierre anterior'), q.c2_ok, false)}
        {check('C3', q.c3_ok ? 'todos los asientos conservan su pata de deuda' : `${q.c3_corrupted_count} asiento(s) sin pata TC:Real`, q.c3_ok, true)}
        {check('C4', `pago cartola ${formatAmount(String(q.pago_cartola), 'CLP')} == pago Laudus ${formatAmount(String(q.laudus_payment_total), 'CLP')}`, q.pago_ok, false)}
        {check('C5', q.c5_ok ? 'lump del mes neteado (≈0)' : `lump con residual ${formatAmount(String(q.c5_residual), 'CLP')}`, q.c5_ok, false)}
      </div>

      {q.laudus_payments.length > 0 && (
        <button type="button" onClick={() => setOpen(!open)}
          className="text-xs text-muted-foreground underline hover:text-foreground">
          {open ? 'ocultar' : 'ver'} asiento{q.laudus_payments.length > 1 ? 's' : ''} de Laudus
        </button>
      )}
      {open && q.laudus_payments.map((p, i) => (
        <div key={i} className="text-xs bg-muted rounded p-2">
          <span className="font-mono">{p.date}</span> · {p.narration} ·{' '}
          <span className="font-mono">{formatAmount(String(p.amount), currency)}</span>
          {p.bank_account && <span className="text-muted-foreground"> · {p.bank_account}</span>}
        </div>
      ))}

      {q.status === 'red' && (
        <p className="text-xs text-red-600">
          🔴 Hay un descuadre CRÍTICO entre la cartola y la contabilidad (C1/C3). Las herramientas para
          ajustarlo vienen en la próxima versión — por ahora, quedó registrado para revisar.
        </p>
      )}
      {q.status === 'yellow' && (
        <p className="text-xs text-amber-600">
          🟡 La deuda cuadra, pero hay un chequeo secundario en amarillo (C2/C4/C5) — revisá el detalle.
        </p>
      )}
      {q.status === 'green' && (
        <p className="text-xs text-green-600">✓ La cartola cuadra con la contabilidad.</p>
      )}
    </div>
  )
}
