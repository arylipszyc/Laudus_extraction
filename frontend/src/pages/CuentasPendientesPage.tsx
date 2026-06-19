import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  listCuentasPendientes,
  promoverCuenta,
  type PendingAccount,
} from '@/services/cuentasPendientes'
import { triggerSync } from '@/services/sync'

// Re-resolución de las JEs históricas: el importer backfillea desde su fecha-piso.
const BACKFILL_FROM = '2021-01-01'

const clp = (n: number) => n.toLocaleString('es-CL', { maximumFractionDigits: 0 })

export function CuentasPendientesPage() {
  const qc = useQueryClient()
  const { data: pendientes, isLoading, error } = useQuery({
    queryKey: ['cuentas-pendientes'],
    queryFn: listCuentasPendientes,
  })

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <h1 className="text-2xl font-semibold">Cuentas Pendientes de Categorizar</h1>
      <p className="text-sm text-muted-foreground">
        Cuentas que el importer detectó en Laudus pero que aún no están en el plan de cuentas.
        Asigná las categorías y confirmá: la cuenta se incorpora al plan (fuente única Beancount)
        y deja de aparecer como "sin categorizar" en el reporte.
      </p>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error && <p className="text-sm text-destructive">{(error as Error).message}</p>}
      {pendientes && pendientes.length === 0 && (
        <Card className="p-6">
          <p className="text-sm text-muted-foreground">No hay cuentas pendientes. 🎉</p>
        </Card>
      )}

      {pendientes?.map((p) => (
        <PendingRow key={p.code} pending={p} onDone={() => qc.invalidateQueries({ queryKey: ['cuentas-pendientes'] })} />
      ))}
    </div>
  )
}

function PendingRow({ pending, onDone }: { pending: PendingAccount; onDone: () => void }) {
  const [cat1, setCat1] = useState(pending.suggestion.categoria1)
  const [cat2, setCat2] = useState(pending.suggestion.categoria2)
  const [cat3, setCat3] = useState('')
  const [name, setName] = useState(pending.laudus_account_name ?? '')
  const [backfillDone, setBackfillDone] = useState(false)

  const promote = useMutation({
    mutationFn: () =>
      promoverCuenta(pending.code, {
        categoria1: cat1,
        categoria2: cat2,
        categoria3: cat3,
        laudus_account_name: name,
      }),
  })

  const backfill = useMutation({
    mutationFn: () => triggerSync('backfill', BACKFILL_FROM),
    onSuccess: () => setBackfillDone(true),
  })

  const promoted = promote.isSuccess

  return (
    <Card className="p-6 space-y-4">
      <div className="flex justify-between items-start">
        <div>
          <p className="font-medium">
            {pending.laudus_account_name || 'Cuenta nueva'} · <span className="font-mono">{pending.code}</span>
          </p>
          <p className="text-sm text-muted-foreground">
            Monto acumulado: <strong>${clp(pending.monto_acumulado)}</strong>
          </p>
        </div>
      </div>

      {!promoted ? (
        <>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Categoría 1 (sugerida)" value={cat1} onChange={setCat1} />
            <Field label="Categoría 2 (sugerida)" value={cat2} onChange={setCat2} />
            <Field label="Categoría 3 (obligatoria)" value={cat3} onChange={setCat3} required />
          </div>
          <Field label="Nombre de la cuenta (Laudus)" value={name} onChange={setName} />

          {promote.isError && <p className="text-sm text-destructive">{(promote.error as Error).message}</p>}

          <Button
            onClick={() => promote.mutate()}
            disabled={promote.isPending || !cat3.trim()}
          >
            {promote.isPending ? 'Promoviendo…' : 'Confirmar y promover'}
          </Button>
        </>
      ) : promote.data?.git_commit_sha ? (
        <div className="space-y-3">
          <p className="text-sm text-green-600">
            ✅ Cuenta promovida ({promote.data?.account}). Las JEs históricas se re-apuntan al correr el backfill.
          </p>
          {!backfillDone ? (
            <Button variant="outline" onClick={() => backfill.mutate()} disabled={backfill.isPending}>
              {backfill.isPending ? 'Iniciando backfill…' : 'Correr backfill ahora'}
            </Button>
          ) : (
            <p className="text-sm text-muted-foreground">
              Backfill iniciado. Cuando termine, refrescá la lista.
            </p>
          )}
          {backfill.isError && (
            <p className="text-sm text-destructive">{(backfill.error as Error).message}</p>
          )}
          <div>
            <Button variant="ghost" size="sm" onClick={onDone}>Actualizar lista</Button>
          </div>
        </div>
      ) : (
        // Push a git falló (HTTP 200 con git_commit_sha=null): la escritura local persiste pero
        // NO está respaldada. Correr el backfill acá la descartaría (refresh = reset --hard). No
        // ofrecer backfill; mostrar la advertencia del backend y permitir reintentar.
        <div className="space-y-3">
          <p className="text-sm text-amber-600">⚠️ {promote.data?.message}</p>
          <Button variant="outline" onClick={() => promote.mutate()} disabled={promote.isPending}>
            {promote.isPending ? 'Reintentando…' : 'Reintentar promoción'}
          </Button>
          <div>
            <Button variant="ghost" size="sm" onClick={onDone}>Actualizar lista</Button>
          </div>
        </div>
      )}
    </Card>
  )
}

function Field({
  label,
  value,
  onChange,
  required,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  required?: boolean
}) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1">
        {label} {required && <span className="text-destructive">*</span>}
      </label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full border rounded-md px-3 py-2 bg-background"
      />
    </div>
  )
}
