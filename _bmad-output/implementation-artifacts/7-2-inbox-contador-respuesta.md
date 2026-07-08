# Story 7.2: Inbox unificado del contador + respuesta con contexto inline — FR38, FR39

Status: draft

<!-- Depende de 7.0 (resolvedor de ancla + writer) y 7.1 (creación de comentarios). -->

## Story

As a **contador del family office**,
I want **un inbox que junte todos los hilos de comentario abiertos que el owner dejó sobre transacciones, cada uno mostrando la transacción ancla en contexto, y poder responder desde ahí**,
so that **pueda ver de un vistazo todo lo que el owner me preguntó y contestarle sin ir a cazar transacción por transacción — con el movimiento a la vista para no responder de memoria**.

## Contexto

7.1 dejó al owner creando hilos raíz sobre transacciones. Esta story cierra el lazo del lado del contador: **(FR38)** un inbox unificado de hilos abiertos y **(FR39)** responder con el contexto de la transacción inline. Es el análogo de `ReconciliationPage` (lista de pendientes + acción de resolución), aplicado a hilos de comentario. La **resolución** del hilo (cerrarlo) es 7.3; acá solo se **listan** y se **responde**.

El punto crítico que 7.0 habilita y esta story ejerce: al **listar**, cada hilo pasa por `resolve_anchor` (7.0 AC3), así que un comentario cuyo `tx_id` cambió por un re-import **igual** aparece pegado a la transacción correcta (estado `re-anchored`), y uno cuya tx desapareció aparece como "histórico" con su snapshot (estado `orphaned`) — nunca se pierde.

## Acceptance Criteria

1. **AC1 — Inbox unificado de hilos abiertos (FR38).**
   Given hilos en `owner-comments.jsonl`,
   When el contador llama `GET /api/v1/comments` (opcional `?status=open|resolved|all`, default `open`),
   Then devuelve la lista de hilos plegados (`read_threads`, 7.0 AC1), cada uno con: `thread_id`, `root` (comentario del owner: autor, body, ts), `replies[]`, `resolution|None`, y el **estado de ancla** (`anchor_status ∈ {resolved, re-anchored, orphaned}`) más el **contexto de la transacción** (`tx_context`: la tx viva si resolvió/re-ancló, o el `tx_snapshot` congelado si está huérfana). Orden: más recientes o con actividad más nueva arriba.

2. **AC2 — Contexto de la transacción inline (FR39, parte 1).**
   Given un hilo,
   Then su `tx_context` trae lo suficiente para que el contador entienda de qué transacción se habla sin salir del inbox: `date`, `amount`, `currency`, `account`, `narration`, y `anchor_status`. Si `anchor_status="orphaned"`, `tx_context` viene del `tx_snapshot` y el hilo se marca visualmente como "transacción ya no encontrada en el ledger actual" (degradado, no roto).

3. **AC3 — Responder un hilo (FR39, parte 2).**
   Given un hilo abierto,
   When el contador llama `POST /api/v1/comments/{thread_id}/reply` con `{body}` (no vacío),
   Then se appendea una línea de respuesta (`append_reply`, 7.0 AC1) con autor = email/rol del JWT, se commitea+pushea (`persist_and_commit`), y devuelve `{comment_id, created_at}` (201). El hilo NO se cierra (eso es 7.3).

4. **AC4 — RBAC del inbox y la respuesta.**
   Given los endpoints,
   Then `GET /comments` y `POST /comments/{id}/reply` usan `require_role(["family","contador","admin"])` — **ambos roles participan del hilo**: el contador responde preguntas del owner y el owner puede responder de vuelta. (El "inbox" es conceptualmente del contador, pero el mismo `GET` sirve la vista del owner filtrando por sus hilos en el front; no se duplica endpoint.) Rol inválido → 403.

5. **AC5 — Responder un `thread_id` inexistente o ya resuelto.**
   Given un `thread_id` que no existe → 404. Given un `thread_id` ya resuelto (tiene línea de resolución) → se permite responder igual (reabrir la conversación no es el default, pero un comentario post-resolución es válido para auditoría) **o** 409 si Ary prefiere bloquear (ver decisión abierta). Default de esta story: **permitir** responder aunque esté resuelto (append puro; el estado `resolved` lo maneja 7.3/el front).

6. **AC6 — Vista frontend del inbox (FR38/FR39).**
   Given el inbox,
   Then una página nueva (patrón `ReconciliationPage`): lista de hilos, cada uno expandible mostrando el comentario raíz + respuestas en orden + la transacción ancla en contexto (fecha/monto/cuenta/glosa). Los `orphaned` marcados. Input de respuesta por hilo. Sin toasts (estilo Cards/badges). Ruta + nav RBAC `contador`/`admin`. La misma página (o una gemela) sirve al owner filtrando sus hilos — decisión de reuso abajo.

7. **AC7 — Tests + sin regresiones.**
   Backend: `GET /comments` pliega hilos y adjunta `anchor_status` + `tx_context` (incl. un hilo `re-anchored` tras simular re-import y uno `orphaned`); `reply` appendea + no cierra; `thread_id` inexistente → 404; RBAC 403. Frontend: component test del inbox (un hilo resuelto-ancla y uno huérfano; input de respuesta). Suites verdes, 0 regresiones nuevas.

## Tasks / Subtasks

- [ ] **Task 1 — Endpoint de inbox** (AC1, AC2, AC4)
  - [ ] `GET /comments` en `backend/app/api/v1/owner_comments/router.py` (RBAC family/contador/admin, `?status`). Service `list_threads(status, entries)`: `read_threads` → por hilo `resolve_anchor(root, entries)` → arma `anchor_status` + `tx_context` (tx viva o `tx_snapshot`). Filtra por `status` (open = sin `resolution`).
  - [ ] Schema `ThreadView{thread_id, root, replies[], resolution, anchor_status, tx_context}`.

- [ ] **Task 2 — Endpoint de respuesta** (AC3, AC5)
  - [ ] `POST /comments/{thread_id}/reply` (RBAC family/contador/admin). Service `reply(thread_id, body, user_email, user_role, ledger_root)`: valida que el hilo exista (404 si no) → `append_reply` → `persist_and_commit`. Idempotencia N/A (respuestas son eventos únicos).
  - [ ] Schema `ReplyRequest{body}` (no vacío) / `ReplyResponse{comment_id, created_at}`.

- [ ] **Task 3 — Vista frontend del inbox** (AC6)
  - [ ] `frontend/src/services/ownerComments.ts`: `listThreads(status)`, `replyThread(thread_id, body)`.
  - [ ] `frontend/src/pages/CommentsInboxPage.tsx` (patrón `ReconciliationPage`): lista de hilos expandibles, contexto de tx inline, `orphaned` marcado, input de respuesta. Ruta + nav (`contadorNavItems`/`RequireContador`, patrón de 9.12/6.4). Reuso para el owner: ver decisión abierta.

- [ ] **Task 4 — Tests** (AC7)
  - [ ] `backend/tests/test_owner_comments_inbox.py`: plegado + `anchor_status`/`tx_context` (resolved/re-anchored/orphaned), reply appendea sin cerrar, 404, RBAC. Frontend component test del inbox.

## Dev Notes

### Piezas de 7.0/7.1 que esta story consume

| Pieza | De dónde | Uso |
|---|---|---|
| `read_threads(path, thread_id=None)` | `owner_comments_writer` (7.0 AC1) | plegar líneas → hilos |
| `resolve_anchor(comment, entries)` | `owner_comments` (7.0 AC3) | re-resolver el ancla al listar (el valor central del spike) |
| `append_reply` + `persist_and_commit` | 7.0 AC1/AC6 | escribir la respuesta bajo lock+git |
| módulo API `owner_comments/` | 7.1 | ya montado; esta story agrega `GET /comments` y `POST /{id}/reply` |

### Molde de lista/resolución (verificado)

- Backend: `backend/app/api/v1/reconciliation/router.py` (`GET /discrepancies` filtrable + `POST /{id}/resolve`, `require_role`, `response_model`). El inbox de comentarios es el mismo patrón.
- Frontend: `frontend/src/pages/ReconciliationPage.tsx` (lista + acción + expandible, sin toasts). `CommentsInboxPage` lo espeja.

### El corazón de FR39: contexto inline vía re-resolución del ancla

El contador no debería responder de memoria. Por eso `list_threads` **no** guarda una copia del contexto en el JSONL de respuesta — **re-resuelve** el ancla contra el ledger vivo en cada lectura (`resolve_anchor`), así el contexto refleja la transacción **actual** (con su categoría corregida, etc.) y no una foto vieja. La foto vieja (`tx_snapshot`) solo se usa como fallback cuando la tx ya no existe (`orphaned`). Este es exactamente el escenario que el spike 7.0 blindó: un re-import entre el comentario del owner y la respuesta del contador **no** rompe el contexto.

### Anti-alcance

- **No** cierra hilos (7.3). El inbox `?status=open` deja de mostrar un hilo solo cuando 7.3 le appendea una resolución.
- **No** notifica (7.4). El conteo para el chip lo agrega 7.4 sobre este mismo JSONL.
- **No** edita/borra comentarios (append-only).

### Testing standards

- `pytest` `backend/tests/`, `PYTHONUTF8=1`, venv local. Fixtures de ledger inline; simular re-import = mismo `parse_string` con distinto `filename`/`lineno` para forzar `tx_id` distinto y verificar `re-anchored`. `monkeypatch.delenv("IMPORTER_GIT_ENABLED")`.
- Frontend `vitest` + `npx tsc --noEmit`.

### References

- [Source: _bmad-output/implementation-artifacts/7-0-spike-ancla-persistencia-comentarios.md] — `resolve_anchor`, `read_threads`, RBAC.
- [Source: _bmad-output/implementation-artifacts/7-1-owner-crea-comentario.md] — creación del hilo raíz + módulo API.
- [Source: backend/app/api/v1/reconciliation/router.py] — molde de lista/resolución.
- [Source: frontend/src/pages/ReconciliationPage.tsx] — molde de la página.
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 7] — FR38, FR39.

## Decisiones de diseño para Ary (abiertas)

1. **¿Una página para ambos roles o dos vistas?** Recomendado: **una** `CommentsInboxPage`, el mismo `GET /comments` sirve a los dos; el front filtra "mis hilos" cuando el rol es `family` (los que el owner abrió) vs "todos los abiertos" para el contador. Alternativa: una vista dedicada del owner en su dashboard. Default = una página, filtrado en el front por rol.
2. **¿Responder un hilo ya resuelto lo reabre, lo bloquea (409), o solo appendea?** Default de la story: **appendea sin reabrir** (auditoría). Si Ary quiere "reabrir al responder", es un cambio chico en 7.3 (el estado se deriva de la última línea). Confirmar.
3. **Orden del inbox:** ¿por fecha de creación del hilo, o por "última actividad" (respuesta más nueva primero)? Recomendado: **última actividad** (lo que espera un inbox). Default = última actividad.

## Dev Agent Record

### Agent Model Used

_(pendiente)_

### Completion Notes List

_(pendiente)_

### File List

_(pendiente)_
