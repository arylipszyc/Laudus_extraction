import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useAuth } from '@/hooks/useAuth'
import { useHasRole } from '@/hooks/useHasRole'
import { listThreads, markThreadRead, replyThread, resolveThread, type Thread } from '@/services/ownerComments'
import { fmt } from '@/lib/format'

type StatusFilter = 'open' | 'resolved' | 'all'

/** Story 7.2 — inbox de hilos de comentario (contador: todos; owner: los suyos). */
export function CommentsInboxPage() {
  // 7.1b AC5: deep-link ?thread=<id> desde el drill-down. Se arranca en 'all' para que el hilo
  // esté en la lista aunque esté resuelto; si igual no aparece, la página carga normal (no rompe).
  const [searchParams] = useSearchParams()
  const deepLinkId = searchParams.get('thread')
  const [status, setStatus] = useState<StatusFilter>(deepLinkId ? 'all' : 'open')
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
        {visible.map((t) => (
          <ThreadCard key={t.thread_id} thread={t} highlight={t.thread_id === deepLinkId} />
        ))}
      </div>
    </div>
  )
}

const STATUS_LABEL: Record<StatusFilter, string> = {
  open: 'Abiertos',
  resolved: 'Resueltos',
  all: 'Todos',
}

function ThreadCard({ thread, highlight = false }: { thread: Thread; highlight?: boolean }) {
  // 7.4 AC6: los hilos arrancan COLAPSADOS (resumen de una línea); expandir = leer. El hilo
  // deep-linkeado (7.1b AC5) arranca expandido.
  const [expanded, setExpanded] = useState(highlight)
  const [body, setBody] = useState('')
  const qc = useQueryClient()
  const ctx = thread.tx_context
  const orphaned = thread.anchor_status === 'orphaned'
  const resolved = thread.resolution !== null
  // 7.1b AC5: el hilo deep-linkeado se trae a la vista (scrollIntoView no existe en jsdom → optional)
  const cardRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (highlight) cardRef.current?.scrollIntoView?.({ block: 'center' })
  }, [highlight])

  // 7.4 AC6: al expandir un hilo NO leído se marca leído UNA vez (solo si hace falta — cada
  // marcador es un commit al ledger, no spamear). El chip decrementa vía invalidación + poll.
  // El latch se libera si el POST falla (reintenta al re-expandir) y cuando `unread` vuelve a
  // false (actividad nueva mientras está expandido se re-marca).
  const markedRef = useRef(false)
  const readMutation = useMutation({
    mutationFn: () => markThreadRead(thread.thread_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['comments-count'] })
      qc.invalidateQueries({ queryKey: ['owner-comments'] })
    },
    onError: () => {
      markedRef.current = false
    },
  })
  const { unread } = thread
  const { mutate: markRead } = readMutation
  useEffect(() => {
    if (!unread) {
      markedRef.current = false
      return
    }
    if (expanded && !markedRef.current) {
      markedRef.current = true
      markRead()
    }
  }, [expanded, unread, markRead])

  const mutation = useMutation({
    mutationFn: () => replyThread(thread.thread_id, body),
    onSuccess: () => {
      setBody('')
      qc.invalidateQueries({ queryKey: ['owner-comments'] })
      qc.invalidateQueries({ queryKey: ['comment-threads'] })
    },
  })

  // 7.3 AC6: resolver el hilo — visible para ambos roles; al éxito el hilo sale de "Abiertos"
  // vía invalidación (la definición de resuelto vive en el backend, sin estado local).
  const resolveMutation = useMutation({
    mutationFn: () => resolveThread(thread.thread_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['owner-comments'] })
      qc.invalidateQueries({ queryKey: ['comment-threads'] })
      // resolver saca el hilo del conteo (los resueltos no notifican) → chip al día sin esperar el poll
      qc.invalidateQueries({ queryKey: ['comments-count'] })
    },
  })

  const canReply = !mutation.isPending && body.trim().length > 0

  return (
    <div ref={cardRef}>
    <Card className={`p-4 space-y-3 ${highlight ? 'ring-2 ring-primary' : ''}`}>
      {/* 7.4: resumen colapsado — una línea clickeable con lo esencial + indicador de no-leído */}
      <button
        onClick={() => setExpanded((p) => !p)}
        className="w-full text-left flex items-baseline gap-3 flex-wrap"
      >
        <span className="text-xs text-muted-foreground">{expanded ? '▾' : '▸'}</span>
        <span className="text-sm text-muted-foreground">{ctx.date ?? '—'}</span>
        <span className="text-sm font-mono">{fmt(ctx.amount, ctx.currency)}</span>
        <span className="text-sm flex-1 truncate">{ctx.narration || '—'}</span>
        {thread.replies.length > 0 && (
          <span className="text-xs text-muted-foreground">{thread.replies.length} resp.</span>
        )}
        {thread.unread && (
          <span
            title="Actividad nueva"
            className="px-1.5 py-0.5 rounded-full text-[10px] font-medium text-blue-600 bg-blue-50"
          >
            nuevo
          </span>
        )}
        {resolved && <span className="text-xs text-green-700">✓ Resuelto</span>}
      </button>

      {expanded && (<>
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
          placeholder="Escribe una respuesta…"
          className="w-full border rounded-md px-3 py-2 bg-background text-sm"
        />
        {mutation.error && (
          <p className="text-sm text-destructive">{(mutation.error as Error).message}</p>
        )}
        {resolveMutation.error && (
          <p className="text-sm text-destructive">{(resolveMutation.error as Error).message}</p>
        )}
        <div className="flex gap-2">
          <Button size="sm" onClick={() => mutation.mutate()} disabled={!canReply}>
            {mutation.isPending ? 'Enviando…' : 'Responder'}
          </Button>
          {!resolved && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => resolveMutation.mutate()}
              disabled={resolveMutation.isPending}
            >
              {resolveMutation.isPending ? 'Resolviendo…' : 'Marcar resuelto'}
            </Button>
          )}
        </div>
      </div>
      </>)}
    </Card>
    </div>
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
