# Story 7.4: Notificaciones in-app (chips en el Header) para ambos roles — parte in-app de FR37/FR41

Status: draft

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

- [ ] **Task 1 — Conteo por rol + marcador de leído** (AC1, AC2, AC4, AC5)
  - [ ] `GET /comments/count` en `owner_comments/router.py` (RBAC family/contador/admin, `user` del JWT). Service `unread_count(user_email, user_role, path)`: `read_threads` → por hilo abierto, determina el último evento "relevante para este rol" (para contador: root/reply del owner; para family: reply del contador), compara con el último `read_at` del usuario; excluye eventos propios (AC5).
  - [ ] `POST /comments/{thread_id}/read` → `append_read_marker(thread_id, reader_email, read_at)` (nueva línea `type="read"` en el writer 7.0) → `persist_and_commit`.
  - [ ] Schema `CommentsCountResponse{total, unread}` (patrón `CountResponse` de reconciliación, `models.py`).

- [ ] **Task 2 — Chip en el Header** (AC3, AC6)
  - [ ] `frontend/src/components/layout/CommentsChip.tsx` (molde `PendingReconciliationBadge.tsx`): `useQuery` sobre `getCommentsCount`, `errorAwareInterval`, link a `/comments`. **`useHasRole(['family','contador','admin'])`** (incluye family — a diferencia de los otros chips). Oculto si `unread===0`; neutro en error-sin-dato.
  - [ ] Montarlo en `Header.tsx` junto a los otros dos (líneas 23-24).
  - [ ] `ownerComments.ts`: `getCommentsCount()`, `markThreadRead(thread_id)`. `CommentsInboxPage` (7.2) llama `markThreadRead` al expandir un hilo.

- [ ] **Task 3 — Tests** (AC7)
  - [ ] `backend/tests/test_owner_comments_count.py`: count por rol, propio evento no cuenta, resuelto no cuenta, `read` baja el unread. Frontend component test del `CommentsChip`.

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

## Decisiones de diseño para Ary (abiertas)

1. **¿Marcar leído al expandir el hilo, o un botón explícito "marcar leído"?** Recomendado: **al expandir** (menos fricción; abrir = leer). Default = al expandir.
2. **Polling del chip:** ¿60s (como categorización) o 5min (como reconciliación)? Recomendado: **60s** — la conversación quiere sentirse más viva que la reconciliación batch. Default = 60s.
3. **¿Un solo chip de comentarios o separar "sin responder" vs "sin leer"?** Recomendado: **uno** (`unread` según rol). Default = uno.

## Dev Agent Record

### Agent Model Used

_(pendiente)_

### Completion Notes List

_(pendiente)_

### File List

_(pendiente)_
