# Story 7.2: Inbox unificado del contador + vista de leer del owner + respuesta con contexto inline — FR38, FR39

Status: done

<!-- Depende de 7.0 (resolvedor de ancla + writer) y 7.1 (creación de comentarios, DONE).
     Reforzada 2026-07-09 (create-story, decisión Ary): esta story es la UI de LEER hilos para
     AMBOS roles (inbox del contador + vista del owner filtrada a sus hilos). La superficie de
     CREAR del owner (drill-down + tx_id) es 7.1b-reframed, que va DESPUÉS de esta. Ver 7-1b. -->

## Story

As a **contador del family office (y también el owner, en modo lectura de sus hilos)**,
I want **un inbox que junte todos los hilos de comentario abiertos que el owner dejó sobre transacciones, cada uno mostrando la transacción ancla en contexto, y poder responder desde ahí**,
so that **el contador vea de un vistazo todo lo que el owner preguntó y le conteste sin cazar transacción por transacción — con el movimiento a la vista para no responder de memoria — y el owner pueda releer sus hilos y las respuestas**.

## Contexto

7.1 dejó al owner creando hilos raíz sobre transacciones (`POST /api/v1/comments`, DONE, backend). Esta story cierra el lazo de **lectura**: **(FR38)** un inbox unificado de hilos abiertos y **(FR39)** responder con el contexto de la transacción inline. Es el análogo de `ReconciliationPage` (lista de pendientes + acción), aplicado a hilos de comentario. La **resolución** del hilo (cerrarlo) es 7.3; el **chip de notificación** es 7.4; la superficie de **crear** del owner en el drill-down es 7.1b. Acá solo se **listan**, se **leen** y se **responden**.

El punto crítico que 7.0 habilita y esta story ejerce: al **listar**, cada hilo pasa por `resolve_anchor` (7.0), así que un comentario cuyo `tx_id` cambió por un re-import **igual** aparece pegado a la transacción correcta (`re-anchored`), y uno cuya tx desapareció aparece como "histórico" con su snapshot (`orphaned`) — nunca se pierde. Este es exactamente el escenario que el spike 7.0 blindó.

> **Alcance de lectura para AMBOS roles (decisión Ary 2026-07-09).** El mismo `GET /comments` sirve al contador (todos los hilos abiertos) y al owner (sus hilos). La misma página `CommentsInboxPage` los renderiza, filtrando por rol en el front. **Ojo de routing:** hoy el nav de contador y las rutas de esa familia se gatean con `RequireContador` / `useHasRole(['contador','admin'])` — esta ruta **NO** puede ir bajo `RequireContador`, o el owner (`family`) no la ve. Ver Dev Notes → "Routing para ambos roles".

## Acceptance Criteria

1. **AC1 — Inbox unificado de hilos abiertos (FR38).**
   Given hilos en `owner-comments.jsonl`,
   When un usuario llama `GET /api/v1/comments` (opcional `?status=open|resolved|all`, default `open`),
   Then devuelve la lista de hilos plegados (`read_threads`, 7.0), cada uno con: `thread_id`, `root` (comentario del owner: `author_email`, `author_role`, `body`, `ts`), `replies[]`, `resolution|None`, el **estado de ancla** (`anchor_status ∈ {resolved, re-anchored, orphaned}`) y el **contexto de la transacción** (`tx_context`: la tx viva si resolvió/re-ancló, o el `tx_snapshot` congelado si está huérfana). Orden: **última actividad** primero (respuesta o raíz más nueva arriba).

2. **AC2 — Contexto de la transacción inline (FR39, parte 1).**
   Given un hilo,
   Then su `tx_context` trae lo suficiente para entender de qué transacción se habla sin salir del inbox: `date`, `amount`, `currency`, `account`, `narration`, y `anchor_status`. Si `anchor_status="orphaned"`, `tx_context` viene del `tx_snapshot` y el hilo se marca visualmente como "transacción ya no encontrada en el ledger actual" (degradado, no roto).

3. **AC3 — Responder un hilo (FR39, parte 2).**
   Given un hilo abierto,
   When un usuario llama `POST /api/v1/comments/{thread_id}/reply` con `{body}` (no vacío, `max_length` defensivo como en 7.1),
   Then se appendea una línea de respuesta (`append_reply`, 7.0) con autor = `email`/`role` del JWT, se commitea+pushea (`persist_and_commit`), y devuelve `{comment_id, created_at}` (201). El hilo **NO** se cierra (eso es 7.3).

4. **AC4 — RBAC del inbox y la respuesta (ambos roles).**
   Given los endpoints,
   Then `GET /comments` y `POST /comments/{id}/reply` usan `require_role(["family","contador","admin"])` — **ambos roles participan del hilo**: el contador responde preguntas del owner y el owner puede responder de vuelta. Un JWT sin auth válida → 401 (comportamiento de `get_current_user`; el "403" es inalcanzable acá igual que en 7.1, la allowlist son los 3 roles válidos). El **filtrado** owner-ve-solo-sus-hilos es responsabilidad del front (defensa: el back no filtra por rol en el `GET`, sirve la lista; el owner solo tiene sus propios hilos de interés — documentar que un `family` técnicamente puede pedir el `GET` completo, aceptable en el MVP porque los comentarios no son secretos entre owner y contador del mismo family office).

5. **AC5 — Responder un `thread_id` inexistente o ya resuelto.**
   Given un `thread_id` que no existe → 404 (nada se escribe). Given un `thread_id` ya resuelto (tiene línea de resolución) → **se permite** responder igual (append puro; un comentario post-resolución es válido para auditoría, no reabre — el estado `resolved` lo maneja 7.3/el front). Default de esta story: **permitir**.

6. **AC6 — Vista frontend: inbox del contador + lectura del owner (FR38/FR39).**
   Given el inbox,
   Then una página nueva `CommentsInboxPage` (patrón `ReconciliationPage`): lista de hilos ordenada por última actividad, cada uno expandible mostrando el comentario raíz + respuestas en orden + la transacción ancla en contexto (fecha/monto/cuenta/glosa). Los `orphaned` marcados como degradados. Input de respuesta por hilo (sin toasts, estilo Cards/badges). **La ruta `/comments` es accesible para `family`, `contador` y `admin`** (bajo `RequireAuth`, NO `RequireContador`); el contador ve todos los hilos abiertos, el owner ve los suyos (filtrado en el front por `author_email` del root vs el usuario del JWT). Nav item visible para los tres roles.

7. **AC7 — Tests + sin regresiones.**
   Backend: `GET /comments` pliega hilos y adjunta `anchor_status` + `tx_context` (incluir un hilo `re-anchored` tras simular re-import y uno `orphaned`); orden por última actividad; `reply` appendea + no cierra; `thread_id` inexistente → 404 sin escritura; body vacío → 422; sin-auth → 401. Frontend: component test del inbox (un hilo con ancla resuelta y uno huérfano; input de respuesta; que el owner solo vea sus hilos). `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` + `npx tsc --noEmit` + `vitest` verdes, 0 regresiones nuevas.

## Tasks / Subtasks

- [x] **Task 1 — Endpoint de inbox `GET /comments`** (AC1, AC2, AC4)
  - [x] Agregar `GET ""` a `backend/app/api/v1/owner_comments/router.py` (junto al `POST ""` de 7.1), `require_role(["family","contador","admin"])`, `ledger: LedgerService = Depends(get_ledger_service)`, param `status: Literal["open","resolved","all"] = "open"`. Reusar el helper `_entries(ledger)` ya existente (maneja `LedgerUnavailableError → 503`).
  - [x] `service.list_threads(status, entries, ledger_root)`: `read_threads(default_jsonl_path(ledger_root))` → por hilo `resolve_anchor(root, entries)` → arma `anchor_status` (del `status` que devuelve `resolve_anchor`) + `tx_context`. `tx_context` de la tx viva (`resolved`/`re-anchored`, leído del `entry`: date/amount/currency/account/narration) o del `root["anchor"]["tx_snapshot"]` (`orphaned`). Filtrar por `status` (open = `resolution is None`; resolved = `resolution is not None`; all = ambos). Ordenar por última actividad (max `ts` entre root y replies), desc.
  - [x] Schema `ThreadView{thread_id, root, replies, resolution, anchor_status, tx_context}` en `schemas.py`. `tx_context` = `TxContext{date, amount, currency, account, narration, anchor_status}`. `response_model=list[ThreadView]`.

- [x] **Task 2 — Endpoint de respuesta `POST /comments/{thread_id}/reply`** (AC3, AC5)
  - [x] `POST "/{thread_id}/reply"` en el router (`require_role(["family","contador","admin"])`). Service `reply(thread_id, body, user_email, user_role, ledger_root)`: valida que el hilo exista vía `read_threads(path, thread_id=thread_id)` (vacío → levantar error → router mapea a **404**); construye `{author_email, author_role, body, ts}` → `persist_and_commit(lambda p: append_reply(thread_id, reply, p), msg, ledger_root)`. Reusar el mapeo de errores de persistencia del `POST` de 7.1 (`CalledProcessError`/`TimeoutExpired`/`RuntimeError` → 500 con detalle `COMMENT_PERSIST_FAILED`).
  - [x] Schema `ReplyRequest{body}` (`StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)` — mismo tope defensivo que 7.1, evita el `field_validator` que rompe el serializador de pydantic v2) / `ReplyResponse{comment_id, created_at}`.

- [x] **Task 3 — Servicio frontend + página del inbox** (AC6)
  - [x] `frontend/src/services/ownerComments.ts` (NUEVO — no existe aún; 7.1 difirió el frontend): `listThreads(status?)`, `replyThread(thread_id, body)`. Patrón `fetch` + `credentials:'include'` + `apiFetch` de `services/reconciliation.ts`.
  - [x] `frontend/src/pages/CommentsInboxPage.tsx` (patrón `ReconciliationPage.tsx`): lista de hilos expandibles, `tx_context` inline (fecha/monto/cuenta/glosa), `orphaned` marcado, input de respuesta por hilo. Filtrado owner: si `useHasRole(['family'])` y no es contador/admin → mostrar solo hilos cuyo `root.author_email` == usuario del JWT (`useAuth`).
  - [x] Routing (AC6): agregar ruta `/comments` en `App.tsx` bajo `RequireAuth` (**NO** `RequireContador`). Nav: agregar el item para los tres roles (ver Dev Notes → Routing; no meterlo solo en `contadorNavItems`, que se gatea con `useHasRole(['contador','admin'])` en `Sidebar.tsx:43`).

- [x] **Task 4 — Tests** (AC7)
  - [x] `backend/tests/test_owner_comments_inbox.py`: plegado + `anchor_status`/`tx_context` (casos resolved / re-anchored / orphaned — simular re-import = mismo `parse_string` con distinto `filename`/`lineno` para forzar `tx_id` distinto pero mismo `anchor_key`); orden por última actividad; `reply` appendea + no cierra; `thread_id` inexistente → 404 sin escritura; body vacío → 422; sin-auth → 401. Fixture de ledger inline (`parse_string`) + `monkeypatch.delenv("IMPORTER_GIT_ENABLED")` (git no-op). Reusar el patrón de `test_owner_comments_api.py` (7.1).
  - [x] Frontend `CommentsInboxPage.test.tsx` (vitest): un hilo ancla-resuelta y uno huérfano; input de respuesta llama `replyThread`; el owner solo ve sus hilos.

### Review Findings

<!-- code-review 2026-07-09 (3 capas: blind / edge-case / acceptance-auditor) -->

- [x] [Review][Patch] Enforcar scoping por-owner en el backend — `GET /comments` filtra por `author_email` cuando el rol es `family`; `reply` devuelve 403 (`NotParticipant`) si un `family` no es participante del hilo (era decisión, Ary eligió parchar el back 2026-07-09). APLICADO + 2 tests (`test_inbox_family_solo_ve_sus_hilos`, `test_reply_family_no_participante_403_sin_escritura`) [backend/app/api/v1/owner_comments/router.py:70-82,99-101 + service.py:63-64,146-154]
- [x] [Review][Patch] `replyThread` muestra "[object Object]" cuando el back responde 422 con `detail` lista (body >10k; el textarea no topea) — APLICADO: normaliza `detail` array→`detail[0].msg` [frontend/src/services/ownerComments.ts:58-71]
- [x] [Review][Defer] `_last_activity` ignora el timestamp de resolución → orden de las vistas resolved/all no refleja la última acción [backend/app/api/v1/owner_comments/service.py:88-94] — deferred, no observable hasta que exista resolución (7.3)
- [x] [Review][Defer] El guard de 404 de `reply()` trata un hilo sin raíz (JSONL parcial: línea reply/resolution sin comment root) como existente → appendea en vez de 404 [backend/app/api/v1/owner_comments/service.py:143] — deferred, solo bajo datos corruptos, low
- [x] [Review][Defer] El working tree mezcla parches sin commitear del code-review de 7.1 (writer `splitlines→split("\n")`, asserts + test unicode en `test_owner_comments_api.py`) con 7.2 — cambios correctos, commit equivocado [pipeline/importers/owner_comments_writer.py:249] — deferred, higiene de commit: separar el commit de 7.1

## Dev Notes

### Piezas de 7.0/7.1 que esta story consume (NO reimplementar) — verificadas 2026-07-09

| Pieza | De dónde | Uso |
|---|---|---|
| `read_threads(path, thread_id=None)` | `pipeline/importers/owner_comments_writer.py:236` | plegar líneas → `{thread_id, root, replies[], resolution|None}` |
| `resolve_anchor(comment, entries)` | `owner_comments_writer.py:92` | re-resolver el ancla al listar; devuelve `{status ∈ resolved|re-anchored|orphaned, tx_id, entry}` |
| `append_reply(thread_id, reply, path)` | `owner_comments_writer.py:208` | appendea línea `type="reply"` (inyecta `reply_id` uuid4 si falta) |
| `persist_and_commit(mutate, msg, ledger_root)` | `owner_comments_writer.py:285` | lock → mutate(append) → git (sin bean-check) |
| `default_jsonl_path(ledger_root)` | `owner_comments_writer.py:171` | `<ledger>/_meta/owner-comments.jsonl` |
| módulo API `owner_comments/` | 7.1 (`router.py`, `service.py`, `schemas.py`) | ya montado con `POST ""`; esta story agrega `GET ""` y `POST "/{id}/reply"` |
| helper `_entries(ledger)` | `owner_comments/router.py:26` | `ledger.entries()` con `LedgerUnavailableError → 503` — reusar |

### Molde de lista/resolución (verificado)

- **Backend:** `backend/app/api/v1/reconciliation/router.py` — `GET /discrepancies` (filtrable, `:41`), `GET /count` (`:61`), `POST /discrepancies/{id}/resolve` (`:75`), todos con `require_role` + `response_model`. El inbox de comentarios es el mismo patrón (salvo el RBAC, que acá incluye `family`).
- **Frontend:** `frontend/src/pages/ReconciliationPage.tsx` (lista + acción + expandible, sin toasts). `CommentsInboxPage` lo espeja. Servicio: `frontend/src/services/reconciliation.ts` (patrón `apiFetch` + `credentials:'include'`).

### Routing para ambos roles (CRÍTICO — no romper el owner)

- Hoy (`frontend/src/App.tsx`): las rutas de contador (`/cartolas`, `/reportes`, `/reconciliation`, `/categorizacion`) van bajo `RequireAuth > RequireContador`. Las de dashboard (`/`, `/balance-sheet`, `/income-expenses`) van solo bajo `RequireAuth`.
- `/comments` debe ir bajo `RequireAuth` **sin** `RequireContador` (el owner `family` la necesita).
- `frontend/src/components/layout/Sidebar.tsx:43`: `canSeeContadorItems = useHasRole(['contador','admin'])` gatea `contadorNavItems`. El item de comentarios **no** va ahí (o no lo vería el owner). Opciones: agregarlo a `dashboardNavItems` (visible a todos), o un item propio renderizado para los tres roles. Recomendado: item propio "Comentarios" visible para todo autenticado.
- Precedente del patrón "elemento del Header/nav para el owner": 7.4 lo documenta para el `CommentsChip` ("primer elemento del Header pensado para el owner"). Coherente.

### El corazón de FR39: contexto inline vía re-resolución del ancla

El contador no debería responder de memoria. `list_threads` **no** guarda una copia del contexto en el JSONL — **re-resuelve** el ancla contra el ledger vivo en cada lectura (`resolve_anchor`), así el contexto refleja la transacción **actual** (con su categoría corregida, etc.), no una foto vieja. La foto vieja (`tx_snapshot`, congelada por `build_anchor` en 7.1) solo se usa como fallback cuando la tx ya no existe (`orphaned`). Un re-import entre el comentario del owner y la respuesta del contador **no** rompe el contexto — es el valor central del spike 7.0.

### Intelligence de 7.1 (previous story) — aplicar

- **Validación de body:** usar `StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)` en el schema, **no** un `field_validator` que levante `ValueError` — este último mete el objeto excepción en el `ctx` del error de pydantic v2 y **rompe el serializador JSON** del middleware de errores (bug real visto en 7.1). El `max_length` es el tope defensivo que el review de 7.1 pidió (el body se commitea a git irreversible).
- **Separadores Unicode:** `read_threads` ya usa `.split("\n")` (no `.splitlines()`) — un body con U+2028/U+2029/U+0085 no se pierde (regresión arreglada en 7.1). No re-romperlo.
- **Mapeo de errores de persistencia:** el `POST` de 7.1 mapea `CalledProcessError`/`TimeoutExpired`/`RuntimeError` → `HTTPException(500, "COMMENT_PERSIST_FAILED: ...")` y saca `_entries()` fuera del `try` para que su 503 no se re-envuelva. El `POST /reply` debe seguir el mismo patrón (`router.py:40-53`).
- **"403" inalcanzable:** como en 7.1, la allowlist son los 3 roles válidos y `get_current_user` ya rechaza (401) cualquier otro rol → la rama 403 de `require_role` no dispara acá. Testear el **401** real (sin cookie / rol desconocido), no un 403 inexistente. El 403 de `require_role` ya está cubierto en `test_rbac.py`.

### Anti-alcance (explícito)

- **No** cierra hilos (7.3). El inbox `?status=open` deja de mostrar un hilo solo cuando 7.3 le appendea una `resolution`.
- **No** notifica ni chip (7.4). El conteo del chip lo agrega 7.4 sobre este mismo JSONL (`GET /comments/count` + `POST /{id}/read`).
- **No** la superficie de **crear** del owner en el drill-down (7.1b-reframed). Acá el owner solo **lee/responde**; crear un hilo raíz nuevo sobre una tx todavía pasa por el drill-down de 7.1b. (El `POST /comments` de crear ya existe desde 7.1; le falta la UI de disparo, que es 7.1b.)
- **No** edita/borra comentarios (append-only).

### Testing standards

- `pytest` en `backend/tests/`, `PYTHONUTF8=1`, venv `./venv/Scripts/python.exe`. Fixtures de ledger inline (`parse_string`). Simular re-import = mismo `parse_string` con distinto `filename`/`lineno` para forzar `tx_id` distinto y verificar `re-anchored`. `monkeypatch.delenv("IMPORTER_GIT_ENABLED")` → git no-op.
- Frontend `vitest` + `npx tsc --noEmit` verde. Component test con el patrón de `CategorizacionPage.test.tsx` / los tests de `ReconciliationPage`.

### Project Structure Notes

- Backend: se **extiende** el módulo `owner_comments/` de 7.1 (router/service/schemas) — no se crea módulo nuevo. Alineado con el patrón `reconciliation`/`transactions`/`tc_reconciliation`.
- Frontend: `ownerComments.ts` es NUEVO (7.1 difirió todo el frontend). `CommentsInboxPage.tsx` es NUEVA. Ruta + nav son las únicas ediciones a archivos existentes (`App.tsx`, `Sidebar.tsx`).
- Sin conflictos de estructura detectados. El JSONL vive en `<ledger>/_meta/owner-comments.jsonl` (fuera del repo de la app, en el clon del ledger) — igual que 7.0/7.1.

### References

- [Source: _bmad-output/implementation-artifacts/7-0-spike-ancla-persistencia-comentarios.md] — `resolve_anchor`, `read_threads`, `append_reply`, `persist_and_commit`, RBAC family-write.
- [Source: _bmad-output/implementation-artifacts/7-1-owner-crea-comentario.md] — módulo API `owner_comments/`, learnings de validación/errores/RBAC.
- [Source: pipeline/importers/owner_comments_writer.py#L92] — `resolve_anchor` (3 capas).
- [Source: pipeline/importers/owner_comments_writer.py#L236] — `read_threads` (plegado a hilos).
- [Source: backend/app/api/v1/owner_comments/router.py] — router de 7.1 a extender (helper `_entries`, mapeo de errores).
- [Source: backend/app/api/v1/reconciliation/router.py#L41] — molde de lista/resolución.
- [Source: frontend/src/pages/ReconciliationPage.tsx] — molde de la página.
- [Source: frontend/src/App.tsx#L38] — `RequireContador` (NO usar en `/comments`).
- [Source: frontend/src/components/layout/Sidebar.tsx#L43] — `canSeeContadorItems` (el nav de comentarios va fuera).
- [Source: _bmad-output/planning-artifacts/epics.md] — FR38, FR39 (Epic 7).

## Decisiones de diseño para Ary (RESUELTAS con default 2026-07-09)

1. **¿Una página para ambos roles o dos vistas?** → **Una** `CommentsInboxPage`; el mismo `GET /comments` sirve a los dos, el front filtra "mis hilos" cuando el rol es `family`. (Default de la story, confirmado por la decisión de decomposición: 7.2 = leer para ambos roles.)
2. **¿Responder un hilo ya resuelto lo reabre, lo bloquea (409), o solo appendea?** → **Appendea sin reabrir** (auditoría). Si más adelante se quiere "reabrir al responder", es un cambio chico en 7.3 (el estado se deriva de la última línea).
3. **Orden del inbox:** → **Última actividad** (respuesta más nueva primero), lo que espera un inbox.

> Estas quedaron con default en la story para no bloquear el dev-story. Si Ary quiere cambiar la #2 (bloquear respuesta a resueltos con 409) o la #4-latente (que el backend filtre los hilos del owner en vez del front), avisar antes de arrancar — son cambios acotados.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Amelia / bmad-dev-story)

### Debug Log References

- Suite backend completa: 749 passed / 1 xfailed (110s). +10 tests nuevos (inbox), 0 regresiones.
- Suite frontend completa: 107 passed (15 files). +3 tests nuevos, 0 regresiones.
- `npx tsc --noEmit` limpio; `eslint` sobre los 4 archivos frontend tocados → 0 warnings.

### Completion Notes List

- **Backend (extiende el módulo `owner_comments/` de 7.1, no crea uno nuevo):**
  - `GET /api/v1/comments?status=open|resolved|all` (default `open`) → `list_threads`: `read_threads` pliega el JSONL, `resolve_anchor` re-resuelve el ancla EN CALIENTE por hilo (el corazón de FR39: el contexto refleja la tx viva, no una foto vieja), `_tx_context` arma el contexto (tx viva si `resolved`/`re-anchored`, `tx_snapshot` si `orphaned`), filtro por status, orden por última actividad (`_last_activity` = max `ts` root+replies, ISO lexicográfico).
  - `POST /api/v1/comments/{thread_id}/reply` → `reply`: valida existencia (`read_threads(thread_id=…)` vacío → `ThreadNotFound` → 404 sin escritura), appendea vía `persist_and_commit(append_reply)`, NO cierra el hilo. Mapeo de errores de persistencia idéntico al `POST` de 7.1.
  - Schemas nuevos: `TxContext`, `ThreadView`, `ReplyRequest` (reusa `CommentBody` de 7.1 → `StringConstraints`, no `field_validator`), `ReplyResponse`.
  - RBAC `require_role(["family","contador","admin"])` en ambos endpoints (ambos roles participan del hilo). El back NO filtra por rol (AC4): sirve la lista, el front acota los del owner.
- **Frontend:**
  - `ownerComments.ts` (NUEVO): `listThreads(status?)` + `replyThread(id, body)` con `apiFetch` + `credentials:'include'`.
  - `CommentsInboxPage.tsx` (NUEVA, molde `ReconciliationPage`): hilos en Cards con `tx_context` inline (fecha/monto/cuenta/glosa), `orphaned` marcado como degradado, input de respuesta por hilo, filtros de status. Filtrado owner en el front (si no `useHasRole(['contador','admin'])` → solo `root.author_email == user.email`).
  - Routing: `/comments` bajo `RequireAuth` SIN `RequireContador` (riesgo crítico de la story evitado — el owner `family` la necesita). Nav `sharedNavItems` en `Sidebar` fuera de `contadorNavItems`, visible a los tres roles.
- **Decisiones de la story (defaults) honradas:** una página para ambos roles; responder a resuelto appendea sin reabrir (AC5, con test); orden por última actividad. Ninguna requirió consulta a Ary.
- **Anti-alcance respetado:** no cierra hilos (7.3), no notifica/chip (7.4), no expone la superficie de CREAR del owner en el drill-down (7.1b).

### File List

- `backend/app/api/v1/owner_comments/schemas.py` (modificado — `TxContext`, `ThreadView`, `ReplyRequest`, `ReplyResponse`)
- `backend/app/api/v1/owner_comments/service.py` (modificado — `list_threads`, `reply`, `ThreadNotFound`, `_tx_context`, `_last_activity`)
- `backend/app/api/v1/owner_comments/router.py` (modificado — `GET ""` + `POST "/{thread_id}/reply"`)
- `backend/tests/test_owner_comments_inbox.py` (NUEVO — 10 tests)
- `frontend/src/services/ownerComments.ts` (NUEVO)
- `frontend/src/pages/CommentsInboxPage.tsx` (NUEVO)
- `frontend/src/pages/CommentsInboxPage.test.tsx` (NUEVO — 3 tests)
- `frontend/src/App.tsx` (modificado — ruta `/comments`)
- `frontend/src/components/layout/Sidebar.tsx` (modificado — `sharedNavItems`)

## Change Log

- 2026-07-09 — dev-story: implementada → review. Backend `GET /comments` (inbox, re-resolución de ancla en caliente, contexto inline, filtro status, orden por última actividad) + `POST /comments/{id}/reply` (appendea sin cerrar, 404 sin escritura, 422). Frontend `ownerComments.ts` + `CommentsInboxPage` (molde ReconciliationPage) + ruta `/comments` bajo `RequireAuth` (no RequireContador) + nav para los 3 roles. 10 tests backend + 3 frontend. Suites: backend 749 passed/1 xfailed, frontend 107 passed; tsc + eslint limpios; 0 regresiones. SIN COMMIT.
- 2026-07-09 — create-story: story reforzada a ready-for-dev. Absorbe la vista de LEER del owner (decisión Ary: "bundle con leer, ambos roles"). 3 decisiones abiertas resueltas con default. Infra de 7.0/7.1 verificada contra el código (file:line). Learnings de 7.1 (validación pydantic, separadores Unicode, mapeo de errores, 403-inalcanzable) incorporados. Routing para `family` documentado como riesgo crítico. La superficie de CREAR del owner queda en 7.1b-reframed (posterior).
