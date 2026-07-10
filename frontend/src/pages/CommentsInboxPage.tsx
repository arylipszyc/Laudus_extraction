import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useAuth } from '@/hooks/useAuth'
import { useHasRole } from '@/hooks/useHasRole'
import { listThreads, replyThread, type Thread } from '@/services/ownerComments'
import { fmt } from '@/lib/format'

type StatusFilter = 'open' | 'resolved' | 'all'

/** Story 7.2 — inbox de hilos de comentario (contador: todos; owner: los suyos). */
export function CommentsInboxPage() {
  const [status, setStatus] = useState<StatusFilter>('open')
  const { data: user } = useAuth()
  const isContador = useHasRole(['contador', 'admin'])

  const { data: threads = [], isLoading, error } = useQuery({
    queryKey: ['owner-comments', status],
    queryFn: () => listThreads(status),
  })

  // AC4/AC6: el owner (family) solo ve sus propios hilos (filtro en el front por author_email).
  // El contador/admin ven todos. El backend NO filtra por rol (sirve la lista).
  const visible = useMemo(() => {
    if (isContador) return threads
    return threads.filter((t) => t.root.author_email === user?.email)
  }, [threads, isContador, user])

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <h1 className="text-2xl font-semibold">Comentarios</h1>
      <p className="text-sm text-muted-foreground">
        {isContador
          ? 'Hilos que el owner dejó sobre transacciones, con el movimiento a la vista para responder.'
          : 'Tus preguntas sobre transacciones y las respuestas del contador.'}
      </p>

      <div className="flex gap-2">
        {(['open', 'resolved', 'all'] as StatusFilter[]).map((s) => (
          <Chip key={s} label={STATUS_LABEL[s]} active={status === s} onClick={() => setStatus(s)} />
        ))}
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error && <p className="text-sm text-destructive">{(error as Error).message}</p>}
      {!isLoading && !error && visible.length === 0 && (
        <Card className="p-6">
          <p className="text-sm text-muted-foreground">
            {status === 'open' ? 'No hay comentarios abiertos. 🎉' : 'No hay comentarios para este filtro.'}
          </p>
        </Card>
      )}

      <div className="space-y-4">
        {visible.map((t) => <ThreadCard key={t.thread_id} thread={t} />)}
      </div>
    </div>
  )
}

const STATUS_LABEL: Record<StatusFilter, string> = {
  open: 'Abiertos',
  resolved: 'Resueltos',
  all: 'Todos',
}

function ThreadCard({ thread }: { thread: Thread }) {
  const [body, setBody] = useState('')
  const qc = useQueryClient()
  const ctx = thread.tx_context
  const orphaned = thread.anchor_status === 'orphaned'
  const resolved = thread.resolution !== null

  const mutation = useMutation({
    mutationFn: () => replyThread(thread.thread_id, body),
    onSuccess: () => {
      setBody('')
      qc.invalidateQueries({ queryKey: ['owner-comments'] })
    },
  })

  const canReply = !mutation.isPending && body.trim().length > 0

  return (
    <Card className="p-4 space-y-3">
      {/* Contexto de la transacción ancla (AC2) */}
      <div className="rounded-md bg-muted/40 px-3 py-2 text-sm">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-muted-foreground">{ctx.date ?? '—'}</span>
          <span className="font-mono">{fmt(ctx.amount, ctx.currency)}</span>
          <span className="text-xs text-muted-foreground">{ctx.account ?? '—'}</span>
        </div>
        <p className="mt-0.5">{ctx.narration || '—'}</p>
        {orphaned && (
          <p className="mt-1 text-xs text-amber-600">
            ⚠ Transacción ya no encontrada en el ledger actual — se muestra la copia guardada.
          </p>
        )}
        {resolved && (
          <p className="mt-1 text-xs text-green-700">✓ Resuelto</p>
        )}
      </div>

      {/* Comentario raíz + respuestas (AC6) */}
      <ol className="space-y-2">
        <CommentLine
          author={thread.root.author_email}
          role={thread.root.author_role}
          body={thread.root.body}
          ts={thread.root.ts}
        />
        {thread.replies.map((r) => (
          <CommentLine key={r.reply_id} author={r.author_email} role={r.author_role}
            body={r.body} ts={r.ts} />
        ))}
      </ol>

      {/* Responder (AC3) */}
      <div className="space-y-2">
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={2}
          placeholder="Escribí una respuesta…"
          className="w-full border rounded-md px-3 py-2 bg-background text-sm"
        />
        {mutation.error && (
          <p className="text-sm text-destructive">{(mutation.error as Error).message}</p>
        )}
        <Button size="sm" onClick={() => mutation.mutate()} disabled={!canReply}>
          {mutation.isPending ? 'Enviando…' : 'Responder'}
        </Button>
      </div>
    </Card>
  )
}

function CommentLine({ author, role, body, ts }: {
  author: string; role: string; body: string; ts: string
}) {
  return (
    <li className="text-sm">
      <div className="flex items-baseline gap-2">
        <span className="font-medium">{author}</span>
        <span className="text-xs text-muted-foreground">{role} · {ts.slice(0, 16).replace('T', ' ')}</span>
      </div>
      <p className="whitespace-pre-wrap">{body}</p>
    </li>
  )
}

function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={`px-3 py-1 rounded-full text-xs border ${active ? 'bg-primary text-primary-foreground' : 'bg-background'}`}>
      {label}
    </button>
  )
}
