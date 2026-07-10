# Story 7.4: Notificaciones in-app (chips en el Header) para ambos roles — parte in-app de FR37/FR41

Status: review

<!-- Depende de 7.1/7.2/7.3 (hilos crean/responden/resuelven). Cubre la parte IN-APP de FR37/FR41.
     La parte por EMAIL de FR37/FR41 es la story 7.5 (deferida). -->

## Story

As a **owner o contador del family office**,
I want **ver un chip en el Header que me avise cuántos hilos de comentario tienen actividad nueva para mí (el contador: preguntas del owner sin responder; el owner: respuestas del contador que no leí)**,
so that **me entere de que hay algo esperando mi atención sin tener que abrir el inbox a cada rato — el equivalente in-app de la notificación**.

## Contexto

7.1–7.3 dejaron el ciclo de vida del hilo completo (crear/responder/resolver), pero **nadie se entera** de que hay actividad salvo que abra el inbox. Esta story agrega el chip en el Header — el mismo patrón probado de `PendingCategorizationChip` y `PendingReconciliationBadge` (montados en `Header.tsx:23-24`, alimentados por `GET /reconciliation/count`). Cubre la **parte in-app** de FR37 (notificar al contador de un comentario nuevo) y FR41 (notificar al owner de una respuesta).

**Diferencia notable con los chips existentes:** los de categorización/reconciliación se **ocultan para el rol `family`** (son tareas del contador). El chip de comentarios debe mostrarse **también para `family`** — es el primer elemento del Header dirigido al owner. Requiere un marcador de "leído" por usuario para poder contar "actividad nueva **para mí**".

## Acceptance Criteria

1. **AC1 — Conteo de actividad no leída por rol (FR37/FR41 in-app).**
   Given `owner-comments.jsonl`,
   When un usuario llama `GET /api/v1/comments/count`,
   Then devuelve `{total, unread}` calculado **según el rol/usuario del JWT**: para un `contador`/`admin`, `unread` = hilos abiertos con actividad (comentario raíz o respuesta del owner) posterior a su último "leído"; para un `family`, `unread` = hilos abiertos con una respuesta del contador posterior a su último "leído". Solo cuenta hilos **abiertos** (los resueltos no notifican).

2. **AC2 — Marcador de "leído" por usuario.**
   Given un usuario que abre un hilo,
   When llama `POST /api/v1/comments/{thread_id}/read`,
   Then se appendea un marcador de lectura (`{type: "read", thread_id, reader_email, read_at}`) a `owner-comments.jsonl` vía `persist_and_commit`; el hilo deja de contar como "no leído" para ese usuario en `count`. `require_role(["family","contador","admin"])` — **marcar leído es un write de `family`** (cubierto por la postura RBAC de 7.0).

3. **AC3 — Chip en el Header para ambos roles.**
   Given `unread > 0`,
   Then aparece un chip en el Header (patrón `PendingReconciliationBadge`) que muestra el conteo y linkea al inbox de comentarios (`/comments`). **Se muestra para `family` también** (no se oculta como los otros chips). Si `unread == 0` → oculto. Polling con `errorAwareInterval` (patrón existente). Error de carga sin dato previo → chip neutro "no se pudo cargar" (patrón de `PendingReconciliationBadge` líneas 26-36), no se oculta.

4. **AC4 — "No leído" se deriva de timestamps, sin estado mutable.**
   Given el JSONL append-only,
   Then `unread` se computa comparando el `ts` del último evento relevante del hilo contra el `read_at` más reciente de ese usuario para ese hilo (ambos leídos del JSONL). Sin flags mutables, sin borrar líneas — consistente con el modelo append-only del proyecto. Un hilo sin marcador de lectura del usuario → cuenta como no leído (si tiene actividad relevante).

5. **AC5 — No auto-notificarse la propia actividad.**
   Given un usuario que comenta/responde,
   Then su propio evento **no** cuenta como "no leído para él" (el que escribe ya lo vio). Ej.: el contador responde un hilo → su respuesta no le suma a su propio `unread`; sí al del owner.

6. **AC6 — Marcar leído desde la UI.**
   Given el inbox (7.2),
   When el usuario abre/expande un hilo,
   Then el front llama `POST /comments/{id}/read` (una vez), y el chip del Header decrementa en el próximo poll. (Simple: marcar leído al expandir el hilo.)

7. **AC7 — Tests + sin regresiones.**
   Backend: `count` por rol (contador ve preguntas sin leer; owner ve respuestas sin leer; propio evento no cuenta — AC5; resuelto no cuenta — AC1); `read` appendea marcador y baja el `unread` de ese usuario. Frontend: component test del chip (visible para family, oculto si 0, neutro en error). Suites verdes, 0 regresiones nuevas.

## Tasks / Subtasks

- [x] **Task 1 — Conteo por rol + marcador de leído** (AC1, AC2, AC4, AC5)
  - [x] `GET /comments/count` en `owner_comments/router.py` (RBAC family/contador/admin, `user` del JWT). Service `comments_count(user_email, user_role, ledger_root)`: `read_threads` → por hilo abierto, determina el último evento "relevante para este rol" (para contador: root/reply del owner; para family: reply del contador), compara con el último `read_at` del usuario; excluye eventos propios (AC5).
  - [x] `POST /comments/{thread_id}/read` → `append_read_marker(thread_id, reader_email, read_at)` (nueva línea `type="read"` en el writer 7.0) → `persist_and_commit`.
  - [x] Schema `CommentsCountResponse{total, unread}` (patrón `CountResponse` de reconciliación, `models.py`).

- [x] **Task 2 — Chip en el Header** (AC3, AC6)
  - [x] `frontend/src/components/layout/CommentsChip.tsx` (molde `PendingReconciliationBadge.tsx`): `useQuery` sobre `getCommentsCount`, `errorAwareInterval`, link a `/comments`. **`useHasRole(['family','contador','admin'])`** (incluye family — a diferencia de los otros chips). Oculto si `unread===0`; neutro en error-sin-dato.
  - [x] Montarlo en `Header.tsx` junto a los otros dos (líneas 23-24).
  - [x] `ownerComments.ts`: `getCommentsCount()`, `markThreadRead(thread_id)`. `CommentsInboxPage` (7.2) llama `markThreadRead` al expandir un hilo.

- [x] **Task 3 — Tests** (AC7)
  - [x] `backend/tests/test_owner_comments_count.py`: count por rol, propio evento no cuenta, resuelto no cuenta, `read` baja el unread. Frontend component test del `CommentsChip`.

## Dev Notes

### Molde exacto de los chips (verificado)

- `frontend/src/components/layout/PendingReconciliationBadge.tsx` — `useQuery` + `errorAwareInterval` + `useHasRole` + `navigate` + chip neutro en error-sin-dato (líneas 26-36) + oculto si `total===0`. **Copiar la estructura**, cambiando el `useHasRole` para **incluir `family`** y el color/label.
- `frontend/src/components/layout/PendingCategorizationChip.tsx` — versión mínima (siempre amber, oculto si 0). Referencia de la variante simple.
- `frontend/src/components/layout/Header.tsx:23-24` — punto de montaje de los chips.
- `GET /reconciliation/count` → `CountResponse` (`reconciliation/router.py:57`) + `getReconciliationCount` (`services/reconciliation.ts`) — molde del endpoint de conteo y su servicio.

### Por qué "no leído" y no solo "conteo de abiertos"

Los chips existentes cuentan **trabajo pendiente objetivo** (categorías sin confirmar, discrepancias abiertas) — igual para todos los contadores. Un hilo de comentario es **conversación**: "pendiente" depende de **quién lo mira** (el contador debe responder; el owner debe leer la respuesta). Por eso hace falta el marcador de "leído" por usuario — sin él, el chip mostraría el mismo número a todos y no bajaría al leer. El marcador append-only (`type="read"`) mantiene el modelo del proyecto (sin estado mutable, sin DB).

### Cambio de UI para `family` (documentar)

Este es el **primer** elemento del Header pensado para el owner. Los otros chips hacen `useHasRole(['contador','admin'])` y retornan `null` para family. `CommentsChip` hace `useHasRole(['family','contador','admin'])`. Verificar que el layout del Header no asume "family no ve chips".

### Cobertura parcial de FR37/FR41 (importante)

FR37 ("notificar al contador de un comentario nuevo") y FR41 ("notificar al owner de una respuesta") tienen **dos canales**: in-app y email. Esta story cubre **solo el in-app** (el chip). **El email es la story 7.5, que está diferida.** Hasta que 7.5 se haga, FR37/FR41 quedan **PARCIALMENTE cubiertos**: el chip in-app cubre el flujo cuando el usuario está en la app; no hay aviso si está fuera de la app. Documentado como decisión consciente (el owner/contador entran a la app regularmente; el email es mejora, no bloqueante).

### Anti-alcance

- **No** email (7.5).
- **No** notificaciones push del browser / websockets — solo polling del chip (patrón existente).
- **No** "marcar todo como leído" masivo (mejora futura; el MVP marca al abrir cada hilo).

### Testing standards

- `pytest` `backend/tests/`, `PYTHONUTF8=1`, venv local, `monkeypatch.delenv("IMPORTER_GIT_ENABLED")`. Frontend `vitest` + `tsc`.

### References

- [Source: _bmad-output/implementation-artifacts/7-0-spike-ancla-persistencia-comentarios.md] — writer (agregar `type="read"`), `persist_and_commit`, RBAC family-write.
- [Source: _bmad-output/implementation-artifacts/7-2-inbox-contador-respuesta.md] — inbox al que linkea el chip + marcar leído al expandir.
- [Source: frontend/src/components/layout/PendingReconciliationBadge.tsx] — molde del chip (incl. error-sin-dato).
- [Source: frontend/src/components/layout/Header.tsx:23-24] — montaje.
- [Source: backend/app/api/v1/reconciliation/router.py:57] — `GET /count` molde.
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 7] — FR37, FR41 (parte in-app).

## Decisiones de diseño (resueltas con los defaults — mandato Ary 2026-07-10 "para preguntas técnicas sigue tu recomendación")

1. **Marcar leído AL EXPANDIR el hilo** (menos fricción; abrir = leer). Consecuencia de UX: los hilos del inbox ahora arrancan **colapsados** (resumen de una línea: fecha, monto, glosa, nº respuestas, badge "nuevo", ✓ resuelto) — antes de 7.4 se renderizaban completos y "expandir" no existía. El hilo deep-linkeado (7.1b) arranca expandido. El mark-read solo se dispara si el hilo está `unread` para el usuario (cada marcador es un commit al ledger — no spamear) y UNA vez por montaje.
2. **Polling del chip = 60s** (`errorAwareInterval`, patrón existente).
3. **Un solo chip** (`unread` según rol), azul 💬, oculto si 0, neutro en error-sin-dato.
4. **[Agregada en dev] `ThreadView.unread` por usuario en `GET /comments`**: permite el badge "nuevo" en el resumen colapsado y el mark-read selectivo (sin él, el front marcaría leído cada expand = commits redundantes). `list_threads` recibe `user_email`/`user_role` opcionales (default `""` → `unread=False`, backward-compatible).
5. **[Agregada en dev] `family` solo marca leído hilos donde participa** (403) — misma postura que reply (7.2) y resolve (7.3), helper `_require_participant` compartido. El count del family solo considera SUS hilos (espeja el scoping del inbox).

## Dev Agent Record

### Agent Model Used

Claude Fable 5 (claude-fable-5) — Amelia (dev-story), 2026-07-10.

### Completion Notes List

- Ciclo red-green: 8 tests backend nuevos escritos primero (8 rojos), luego implementación.
- **Writer (7.0):** `append_read_marker` (línea `type="read"` = `{thread_id, reader_email, read_at}`) + `read_threads` pliega los marcadores en `thread["reads"]` (los consumidores existentes ignoran la clave extra). Sin flags mutables: "no leído" se DERIVA comparando el `ts` del último evento relevante vs el `read_at` máximo del usuario (AC4, ISO lexicográfico como `_last_activity`).
- **Service:** `_is_unread(thread, user_email, user_role)` — relevante = eventos de LA OTRA PARTE (contador/admin ven actividad de rol `family`; family ve actividad de contador/admin), propio email excluido (AC5 doblemente guardado). `comments_count` = `{total, unread}` sobre hilos abiertos scoped por rol. `mark_read` con guards 404/403 antes de escribir. `list_threads` ahora estampa `unread` por hilo.
- **Router:** `GET /comments/count` (no toca `entries` → inmune al 503 de ledger) + `POST /{thread_id}/read` (mismo mapeo de errores que reply/resolve).
- **Frontend:** `CommentsChip` (molde `PendingReconciliationBadge`; diferencia clave: `useHasRole(['family','contador','admin'])` — primer elemento del Header dirigido al owner; azul; oculto si `unread=0`; neutro en error-sin-dato; poll 60s) montado en `Header`. `getCommentsCount`/`markThreadRead` en `ownerComments.ts`. `CommentsInboxPage`: hilos colapsados con resumen de una línea + badge "nuevo"; expandir un hilo `unread` llama `markThreadRead` una vez e invalida `['comments-count']` + `['owner-comments']` (el chip decrementa sin esperar el poll).
- **Tests:** backend 8 nuevos (`test_owner_comments_count.py`: count por rol y AC5, read baja solo el unread del lector, actividad nueva post-read vuelve a contar, resuelto no cuenta, scoping family + 403 ajeno, 404/401, `ThreadView.unread` end-to-end); frontend 3 del chip (`CommentsChip.test.tsx`) + 3 del inbox (expand marca una vez / ya-leído no marca / badge "nuevo") + tests existentes adaptados al colapsado (expandir antes de asertar detalles; `vi.clearAllMocks` en `beforeEach` para no arrastrar conteos). Suites: backend **771 passed / 1 xfailed**, frontend **120 passed** (17 files), tsc + eslint (tocados) limpios, 0 regresiones.
- **Cobertura FR37/FR41: PARCIAL por diseño** — esta story cubre el canal in-app; el email es 7.5 (deferred).

### File List

- pipeline/importers/owner_comments_writer.py (M — append_read_marker + reads en read_threads)
- backend/app/api/v1/owner_comments/service.py (M — _is_unread + comments_count + mark_read + unread en list_threads)
- backend/app/api/v1/owner_comments/schemas.py (M — CommentsCountResponse, MarkReadResponse, ThreadView.unread)
- backend/app/api/v1/owner_comments/router.py (M — GET /count + POST /{id}/read)
- backend/tests/test_owner_comments_count.py (NUEVO — 8 tests)
- frontend/src/components/layout/CommentsChip.tsx (NUEVO — chip del Header)
- frontend/src/components/layout/CommentsChip.test.tsx (NUEVO — 3 tests)
- frontend/src/components/layout/Header.tsx (M — monta CommentsChip)
- frontend/src/services/ownerComments.ts (M — getCommentsCount + markThreadRead + Thread.unread)
- frontend/src/pages/CommentsInboxPage.tsx (M — hilos colapsables + mark-read al expandir)
- frontend/src/pages/CommentsInboxPage.test.tsx (M — tests adaptados + 3 nuevos)
- _bmad-output/implementation-artifacts/sprint-status.yaml (M — tracking)
- _bmad-output/implementation-artifacts/7-4-notificaciones-in-app.md (M — este archivo)

## Change Log

- 2026-07-10 — dev-story (Amelia): implementación completa Tasks 1–3, AC1–AC7 MET con los defaults técnicos auto-aprobados + ThreadView.unread + guard de participante (postura 7.2/7.3). Inbox pasa a hilos colapsados (consecuencia de "leer = expandir"). Suites 771/120/tsc/eslint verdes, 0 regresiones. Status → review.
