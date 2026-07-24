# Story 7.1b: Superficie del owner en el drill-down — crear comentario sobre una transacción (+ `tx_id` en `/ledger-entries`)

Status: done

<!-- REFRAMED 2026-07-09 (decisión Ary): bundle con la UI de leer + decomposición leer-primero (7.2 DONE).
     READY-FOR-DEV 2026-07-10 (create-story): 7.2 entregada y commiteada (d8a0dac) → esta story quedó
     desbloqueada. Toda la infra que consume (POST /comments de 7.1, GET /comments + inbox de 7.2,
     resolve_anchor de 7.0) está verificada contra el código a 2026-07-10. -->

## Story

As a **owner del family office (rol `family`)**,
I want **ver, sobre cada fila de transacción del drill-down de Ingresos/Gastos, si ya hay un hilo de comentario y poder abrir uno nuevo ("¿qué es este cargo?") ahí mismo**,
so that **pueda preguntarle al contador sobre un movimiento sin salir de la vista donde lo estoy mirando — y el comentario queda pegado a esa transacción (backend de 7.1, ya entregado)**.

## Contexto

7.1 dejó el `POST /api/v1/comments` funcionando (ancla por `tx_id` de beancount) y 7.2 dejó la lectura completa (`GET /comments` con re-resolución de ancla + `CommentsInboxPage` para ambos roles + `POST /{id}/reply`). Lo único que falta del lazo owner→contador es la **superficie de disparo**: el owner no tiene desde dónde crear un hilo, porque **ninguna vista suya expone el `tx_id`** (verificado 2026-07-09):

- `/reportes` es solo descarga de Excel — sin filas de tx.
- El **drill-down de Ingresos/Gastos** (`TransactionRows`, la única tabla de tx que el owner ve) sale de `GET /ledger-entries`, cuyas filas tienen `journalentryid`/`lineid` = `None` y **no** traen `tx_id` (`bql_queries.py:137-170`).
- El `tx_id` solo se expone hoy en el endpoint `transactions` (contador/admin, solo pendientes).

**Decisión Ary 2026-07-09 — Opción A:** exponer `tx_id` en el drill-down. Esta story: (1) agrega `tx_id` por fila a `/ledger-entries`, (2) pone la affordance de leer-hilo + crear-comentario en `TransactionRows`.

## Acceptance Criteria

1. **AC1 — `tx_id` por fila en `GET /ledger-entries` (backend).**
   Given el ledger cargado,
   When se llama `GET /api/v1/ledger-entries` (mismos params de hoy),
   Then cada fila incluye `tx_id`: el id **de la transacción padre** del posting (el mismo que computa `transactions/service.py::_tx_id_of` — `compute_tx_id(filename, lineno, narration, monto_primera_pata)`), de modo que un `POST /comments` con ese `tx_id` resuelve el ancla (`build_anchor` lo encuentra). El resto del shape de la respuesta (aliases Sheets, orden `date DESC`, `meta.last_sync`, filtros `entity`/`date_from`/`date_to`/`account_number`) queda **idéntico** — parity suite y tests existentes verdes sin modificarlos (salvo asserts nuevos).

2. **AC2 — `ThreadView` expone el `tx_id` resuelto (backend).**
   Given el inbox `GET /comments`,
   Then cada hilo incluye `tx_id`: el id **actual** de la tx ancla que devuelve `resolve_anchor` (el original si `resolved`, el **nuevo** si `re-anchored`, `null` si `orphaned`). Es lo que permite al frontend cruzar hilos ↔ filas del drill-down aun después de un re-import.

3. **AC3 — Crear comentario desde la fila (frontend, FR36).**
   Given el drill-down de Ingresos/Gastos con una cuenta expandida,
   When el usuario abre la affordance "comentar" de una fila y envía un texto no vacío,
   Then se llama `POST /api/v1/comments` con `{tx_id, body}` (servicio `createComment` en `ownerComments.ts`), se muestra confirmación **inline** (estilo Cards/badges, sin toasts) y la fila pasa a mostrar el badge de hilo existente (AC4) sin recargar la página (invalidación de la query de hilos). Errores legibles: body vacío no se envía (disable), 404/422/500 muestran el `detail` normalizado (mismo patrón que `replyThread`). Una fila sin `tx_id` (`null`) no muestra la affordance.

4. **AC4 — Badge "ver hilo" en filas con hilo existente (frontend).**
   Given hilos devueltos por `GET /comments` (para `family` el backend ya los acota a los suyos — scoping de 7.2),
   Then las filas del drill-down cuyo `tx_id` coincide con el `tx_id` resuelto de un hilo muestran un badge/ícono "ver hilo" en vez de "comentar", y al clickearlo navega a `/comments?thread=<thread_id>`. Los hilos se cargan **una vez** (react-query compartida entre todas las cuentas expandidas, no un fetch por fila).

5. **AC5 — Deep-link del inbox.**
   Given `/comments?thread=<thread_id>`,
   Then `CommentsInboxPage` expande ese hilo y lo trae a la vista (scroll), siguiendo el precedente de deep-link de `ReconciliationPage` (6.4). Si el `thread_id` no está en la lista (p.ej. filtro `open` y el hilo está resuelto), no rompe: la página carga normal.

6. **AC6 — Tests + sin regresiones.**
   Backend: `tx_id` presente y correcto por fila (== `_tx_id_of` de la tx padre); una tx con 2 patas visibles → ambas filas comparten `tx_id`; estable entre dos cargas del mismo ledger; `ThreadView.tx_id` en los 3 estados (`resolved`/`re-anchored` con el id nuevo/`orphaned`→`null`); filtros de `/ledger-entries` intactos. Frontend: component test del affordance (submit → `createComment` + confirmación; fila con hilo → badge y link); deep-link del inbox. `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` + `npx tsc --noEmit` + `vitest` verdes, 0 regresiones (ojo suites de parity: `test_bql_queries.py`, `test_beancount_parity.py`, `test_dashboard.py`).

## Tasks / Subtasks

- [x] **Task 1 — Backend: `tx_id` por fila en `ledger_entries_via_beancount`** (AC1)
  - [x] Reescribir el cuerpo de `ledger_entries_via_beancount` (`backend/app/services/bql_queries.py:115`) para iterar `ledger.entries()` directamente en vez de BQL: por cada `Transaction` del rango de fechas, por cada posting cuya cuenta matchee `^(Assets|Liabilities|Equity|Income|Expenses):{entity}:` (usar `re`), emitir la fila actual + `"tx_id": _tx_id_of(entry)` **de la tx padre** (la sutileza del draft: el BQL itera por posting y no da acceso a la tx padre — por eso el cambio de estrategia). Mantener: filtro `account_number` por `code` del Open-meta, split debit/credit por signo, `last_sync` = fecha máxima, orden **`date DESC`** (sort estable por fecha desc, preservando el orden de archivo dentro del mismo día). NO agregar scans extra (lección D7: single-pass).
  - [x] Importar el `_tx_id_of` canónico — **no crear una tercera copia** (ya hay 2: `backend/app/api/v1/transactions/service.py:40` y `pipeline/importers/owner_comments_writer.py`). Recomendado: `from backend.app.api.v1.transactions.service import _tx_id_of` (es la canónica que usan categorización y el ancla de comentarios; la de `owner_comments_writer` es copia declarada idéntica).
  - [x] `LedgerEntryRecord` (`backend/app/api/v1/dashboard/schemas.py:27`): agregar `tx_id: str | None = None` (sin alias — el response_model descarta campos no declarados, mismo gotcha del fix "Otros" PR #18).

- [x] **Task 2 — Backend: `tx_id` resuelto en `ThreadView`** (AC2)
  - [x] `list_threads` (`backend/app/api/v1/owner_comments/service.py:101`): agregar `"tx_id": resolved["tx_id"]` al dict de salida (ya está disponible — `resolve_anchor` devuelve `{status, tx_id, entry}`, `owner_comments_writer.py:113-120`).
  - [x] `ThreadView` (`backend/app/api/v1/owner_comments/schemas.py:43`): agregar `tx_id: str | None`.

- [x] **Task 3 — Frontend: servicio + types** (AC3, AC4)
  - [x] `frontend/src/services/ownerComments.ts`: agregar `createComment(tx_id, body)` → `POST ${api.baseUrl}/api/v1/comments` (`apiFetch` + `credentials:'include'`), devolviendo `{thread_id, comment_id, created_at}`. Reusar/extraer la normalización de `detail` (string | array-422) que ya tiene `replyThread` (`ownerComments.ts:58-69`) — no duplicarla. Agregar `tx_id: string | null` a la interfaz `Thread`.
  - [x] `frontend/src/types/index.ts:58`: agregar `tx_id?: string | null` a `LedgerEntryRecord` (comentario del archivo: los nombres espejan el JSON del backend — no renombrar).

- [x] **Task 4 — Frontend: affordance en `TransactionRows`** (AC3, AC4)
  - [x] En `TransactionRows` (`frontend/src/components/charts/IncomeExpensesDrilldown.tsx:24`): cargar hilos con una query compartida `useQuery({ queryKey: ['comment-threads'], queryFn: () => listThreads('all'), staleTime: 60_000 })` (una sola para todo el drill-down; para `family` el backend ya devuelve solo los suyos) y armar `Map<tx_id, thread_id>`.
  - [x] Por fila con `tx_id`: si hay hilo → ícono/badge "ver hilo" (lucide `MessageSquare`) que navega a `/comments?thread=<thread_id>`; si no → ícono "comentar" (`MessageSquarePlus`) que abre un form inline en una `<tr>` extra bajo la fila (textarea + Enviar/Cancelar; disabled si vacío; ≤10k chars — el tope del backend). Éxito → confirmación inline + `queryClient.invalidateQueries(['comment-threads'])` (la fila pasa a badge). Error → texto legible bajo el form (sin toasts). Sin `tx_id` → sin affordance (AC3).
  - [x] Estética: no romper el layout de 4 columnas (los íconos van dentro de la celda de descripción o al borde derecho de la fila; la `<tr>` del form usa `colSpan`). Estilo consistente con las filas actuales (`text-xs`, `bg-muted/10`).
  - [x] La affordance es visible para los 3 roles autenticados (default técnico, ver Decisiones): el RBAC real vive en el backend (`require_role(["family","contador","admin"])`), no gatear por rol en el front.

- [x] **Task 5 — Frontend: deep-link del inbox** (AC5)
  - [x] `CommentsInboxPage.tsx`: leer `?thread=` (`useSearchParams`), expandir ese hilo al cargar + `scrollIntoView`. Si el hilo no está en el filtro activo, intentar con `status='all'` o simplemente no expandir (no romper). Precedente: deep-link de `ReconciliationPage` (6.4, con el patch de `closeSelected` — no descartar el deep-link ajeno).

- [x] **Task 6 — Tests** (AC6)
  - [x] Backend `test_bql_queries.py` (extender): fila trae `tx_id` == `_tx_id_of` de la tx padre; tx con pata banco + pata gasto (ambas bajo EAG) → 2 filas, mismo `tx_id`; `tx_id` estable entre dos construcciones del mismo ledger; filtros `account_number`/fechas siguen funcionando. `test_owner_comments_inbox.py` (extender): `ThreadView.tx_id` en `resolved` / `re-anchored` (devuelve el id NUEVO — simular re-import con distinto `filename`/`lineno`) / `orphaned` (`null`).
  - [x] Integración corta: crear comentario vía `POST /comments` usando un `tx_id` sacado de `GET /ledger-entries` (round-trip del AC1 — es el contrato central de la story).
  - [x] Frontend (vitest): `TransactionRows`/drill-down con `listThreads` y `createComment` mockeados — fila con hilo muestra badge+link; fila sin hilo abre form, submit llama `createComment` y muestra confirmación; fila sin `tx_id` no muestra affordance. Deep-link: `CommentsInboxPage` con `?thread=` expande el hilo.
  - [x] Suites completas: backend `pytest` + `npx tsc --noEmit` + `vitest` — 0 regresiones. Atención especial a `test_beancount_parity.py` y `test_dashboard.py` (validan el shape de `/ledger-entries`).

### Review Findings

- [x] [Review][Patch] Violación de capas arquitectónicas en `bql_queries.py` [backend/app/services/bql_queries.py:56]
- [x] [Review][Patch] Violación de encapsulación al importar función privada `_tx_id_of` [backend/app/services/bql_queries.py:56]
- [x] [Review][Patch] Bucle ineficiente en `ledger_entries_via_beancount` [backend/app/services/bql_queries.py:120-123]
- [x] [Review][Patch] Falta de manejo de excepciones en `date.fromisoformat` [backend/app/services/bql_queries.py:87-88]
- [x] [Review][Patch] Riesgo de `ValidationError` en Pydantic por falta de valor por defecto en `ThreadView` [backend/app/api/v1/owner_comments/schemas.py:25]
- [x] [Review][Patch] Riesgo de `KeyError` al acceder a `resolved["tx_id"]` [backend/app/api/v1/owner_comments/service.py:39]
- [x] [Review][Patch] Rango inestable de keys de React en `TransactionRows` [frontend/src/components/charts/IncomeExpensesDrilldown.tsx:121]
- [x] [Review][Patch] Fila del formulario de comentarios queda abierta tras éxito sin botón de cerrar [frontend/src/components/charts/IncomeExpensesDrilldown.tsx:32-72]
- [x] [Review][Patch] Falta de manejo de error en la consulta `comment-threads` [frontend/src/components/charts/IncomeExpensesDrilldown.tsx:64-75]
- [x] [Review][Patch] Formulario editable y Cancelar activo durante envío [frontend/src/components/charts/IncomeExpensesDrilldown.tsx:35-53]
- [x] [Review][Patch] Inconsistencia de dialecto en placeholder (voseo) [frontend/src/components/charts/IncomeExpensesDrilldown.tsx:50]
- [x] [Review][Patch] Pérdida de contexto en formateador de errores de FastAPI [frontend/src/services/ownerComments.ts:46-53]
- [x] [Review][Patch] Desincronización de cache al responder desde el Inbox [frontend/src/pages/CommentsInboxPage.tsx:89-92]
- [x] [Review][Defer] Comentario contradictorio en `CommentsInboxPage.tsx` sobre filtrado en el backend [frontend/src/pages/CommentsInboxPage.tsx:28-29] — deferred, pre-existing

## Dev Notes

### Piezas existentes que esta story consume (NO reimplementar) — verificadas 2026-07-10

| Pieza | Dónde | Uso |
|---|---|---|
| `POST /api/v1/comments` (crea hilo raíz) | `owner_comments/router.py:46` (7.1, DONE) | la affordance solo lo **llama**; 404 si `tx_id` no resuelve |
| `GET /api/v1/comments` (hilos + scoping family) | `owner_comments/router.py:70` (7.2, DONE) | fuente del badge "ya tiene hilo"; para `family` ya viene filtrado por `author_email` en el back |
| `resolve_anchor` → `{status, tx_id, entry}` | `pipeline/importers/owner_comments_writer.py:92` | Task 2 solo **expone** su `tx_id` (ya se computa en cada `list_threads`) |
| `compute_tx_id` / `_tx_id_of` | `backend/app/api/v1/transactions/service.py:31,40` | la definición canónica del id; Task 1 la importa |
| `listThreads` / `replyThread` + normalización de errores | `frontend/src/services/ownerComments.ts` (7.2) | `createComment` se agrega al lado, reusando la normalización |
| `CommentsInboxPage` + ruta `/comments` (RequireAuth, 3 roles) | `frontend/src/pages/CommentsInboxPage.tsx`, `App.tsx` (7.2) | Task 5 solo agrega el deep-link |
| `useLedger(accountNumber)` → `GET /ledger-entries` | `frontend/src/hooks/useLedger.ts` | ya alimenta `TransactionRows`; con AC1 sus filas traen `tx_id` gratis |

### El corazón de la story: `tx_id` a nivel de TRANSACCIÓN, no de posting

`compute_tx_id` usa `filename` + `lineno` + `narration` + **monto de la primera pata** de la tx (`transactions/service.py:31-43`). El BQL actual de `ledger_entries_via_beancount` itera **por posting** y no da acceso a la tx padre → por eso Task 1 cambia a iterar `ledger.entries()` directamente (mismo patrón que `list_pending` en `transactions/service.py:46` y `report_rows_via_beancount` está cerca pero también es BQL). Consecuencias que hay que preservar/entender:

- **Una tx con varias patas visibles comparte `tx_id`** (p.ej. gasto + banco, ambas bajo `:EAG:`): el drill-down filtra por `account_number`, así que el usuario ve la pata de esa cuenta — pero el comentario ancla a la **transacción completa**. Correcto por diseño: el line-item quedó diferido en 7.0.
- **Equivalencia con el BQL saliente:** `WHERE account ~ pattern AND date >= from AND date <= to`, `SELECT date, account, narration, number, currency` por posting, `ORDER BY date DESC`. La iteración directa debe replicar exactamente eso (filtro de fecha sobre `e.date`, regex sobre `posting.account`, `number`/`currency` desde `posting.units`). Los tests de parity son el arnés — correrlos temprano.
- **`meta` de cuentas:** se sigue sacando del map de directivas `Open` (`_account_meta`), igual que hoy.
- **Perf:** una pasada por entries (~6k JE) = mismo orden de costo que el BQL. No agregar pasadas extra por fila (lección D7 2026-07-08: single-pass, los scans redundantes eran el problema).

### Learnings de 7.1/7.2 que aplican acá

- **Normalización del `detail`:** FastAPI 422 devuelve `detail` como lista de `{msg,...}` → sin normalizar se renderiza "[object Object]" (patch del review de 7.2, `ownerComments.ts:58-69`). `createComment` debe reusar esa lógica (extraerla a un helper local del módulo).
- **Response model descarta campos no declarados:** el fix "Otros" (PR #18) fue exactamente esto — agregar `tx_id` al dict del service **sin** declararlo en `LedgerEntryRecord`/`ThreadView` lo hace desaparecer en el wire. Declarar ambos.
- **Scoping family ya está en el back** (patch del review de 7.2, `router.py:82-83`): el badge del owner sale bien "gratis" — no re-filtrar en el front.
- **Sin toasts:** confirmaciones/errores inline estilo Cards/badges (patrón de toda la app: ReconciliationPage, CommentsInboxPage).
- **RBAC:** los 3 roles pueden crear/leer (decisión 7.0/7.1 — `family` es el primer rol con write). No inventar gates de rol en el front.

### Decisiones de diseño (defaults técnicos, auto-aprobados per project-context — cambiar solo si Ary objeta)

1. **Estrategia `tx_id` en `/ledger-entries`:** iteración directa de entries (no BQL+join). El join BQL↔entries por `(date, narration, monto)` es ambiguo con postings gemelos; la iteración directa es exacta y es el patrón ya usado en `transactions/service.py`. *Por qué (simple): en vez de preguntarle a la base dos veces y cruzar respuestas, se lee la lista original una vez y se saca todo junto.*
2. **Affordance visible para los 3 roles** (no solo `family`): el backend ya lo permite, gatear en el front agrega código y le esconde al contador una función inocua. El persona principal sigue siendo el owner.
3. **"Ver hilo" navega al inbox con deep-link** (no thread inline en el drill-down): reusa la UI de 7.2 en vez de duplicar el render de hilos; el drill-down solo señala y dispara.
4. **Fila sin `tx_id` → sin affordance** (fail-safe silencioso): solo pasaría con datos viejos cacheados o entradas anómalas.

### Anti-alcance (explícito)

- **No** resolución de hilos (7.3). **No** chip/notificaciones (7.4). **No** email (7.5, deferred).
- **No** comentarios por line-item (diferido en 7.0) — el ancla es la tx completa.
- **No** rediseño del drill-down ni de `CommentsInboxPage` (solo el deep-link).
- **No** tocar el path Sheets legacy: no existe más — `/ledger-entries` lee Beancount siempre (flip 2026-06-19).

### Testing standards

- Backend: `pytest` en `backend/tests/`, `PYTHONUTF8=1`, venv `./venv/Scripts/python.exe`. Fixtures de ledger inline (`parse_string`); simular re-import = mismo contenido con distinto `filename`/`lineno` (cambia `tx_id`, conserva `anchor_key`). `monkeypatch.delenv("IMPORTER_GIT_ENABLED")` → git no-op. Molde: `test_owner_comments_inbox.py`, `test_bql_queries.py`.
- Frontend: `vitest` + `npx tsc --noEmit`. Molde de component test: `CommentsInboxPage.test.tsx` (7.2). Mockear `ownerComments.ts` y `useLedger`.

### Project Structure Notes

- Backend: **cero archivos nuevos** — se editan `bql_queries.py`, `dashboard/schemas.py`, `owner_comments/service.py`, `owner_comments/schemas.py`. Alineado con la estructura existente.
- Frontend: **cero archivos nuevos** (salvo tests) — se editan `ownerComments.ts`, `types/index.ts`, `IncomeExpensesDrilldown.tsx`, `CommentsInboxPage.tsx`.
- El JSONL de comentarios sigue en `<ledger>/_meta/owner-comments.jsonl` — esta story no lo toca directamente (solo vía los endpoints de 7.1/7.2).

### References

- [Source: _bmad-output/implementation-artifacts/7-1-owner-crea-comentario.md] — `POST /comments`, ancla, learnings de validación/errores.
- [Source: _bmad-output/implementation-artifacts/7-2-inbox-contador-respuesta.md] — inbox, scoping family, `ownerComments.ts`, `CommentsInboxPage`.
- [Source: backend/app/services/bql_queries.py#L115] — `ledger_entries_via_beancount` (Task 1).
- [Source: backend/app/api/v1/transactions/service.py#L31] — `compute_tx_id`/`_tx_id_of` canónicos.
- [Source: backend/app/api/v1/dashboard/schemas.py#L27] — `LedgerEntryRecord` (agregar `tx_id`).
- [Source: backend/app/api/v1/owner_comments/service.py#L101] — `list_threads` (exponer `resolved["tx_id"]`).
- [Source: pipeline/importers/owner_comments_writer.py#L92] — `resolve_anchor` devuelve `{status, tx_id, entry}`.
- [Source: frontend/src/components/charts/IncomeExpensesDrilldown.tsx#L24] — `TransactionRows` (superficie).
- [Source: frontend/src/services/ownerComments.ts#L58] — normalización de `detail` a reusar.
- [Source: frontend/src/types/index.ts#L58] — `LedgerEntryRecord` frontend.
- [Source: frontend/src/hooks/useLedger.ts] — query del drill-down.
- [Source: _bmad-output/planning-artifacts/epics.md#L170] — FR36 (Epic 7).
- [Source: _bmad-output/planning-artifacts/adr-owner-comments-ancla-persistencia.md] — ADR del ancla (7.0).

## Dev Agent Record

### Agent Model Used

Claude Fable 5 (claude-fable-5) — Amelia (dev-story), 2026-07-10.

### Debug Log References

- RED confirmado antes de implementar: 8 tests nuevos fallando por lo esperado (`tx_id` ausente en shape + `_FakeLedger` sin `.connection()` → la iteración directa lo resuelve de paso: el service ya no depende de `connection()`).
- Único ajuste post-GREEN: el component test "fila sin tx_id" corría antes de que resolviera la query de hilos → `findAllByLabelText` en vez de `getAllByLabelText`.

### Completion Notes List

- **Task 1 (AC1):** `ledger_entries_via_beancount` reescrito a iteración directa de `ledger.entries()` (una sola pasada, lección D7): filtro de fechas sobre `entry.date`, regex `^(Assets|...|Expenses):{entity}:` sobre `posting.account`, `tx_id = _tx_id_of(entry)` computado UNA vez por tx y compartido entre sus patas. `_tx_id_of` importado del canónico (`transactions/service.py`) — no hay tercera copia. Orden `date DESC` con sort estable (orden de archivo intra-día preservado); `last_sync` solo considera filas emitidas (igual que el BQL saliente, que lo computaba post-filtro `account_number`). Shape idéntico + `tx_id`; parity suites (`test_bql_queries`/`test_beancount_parity`/`test_dashboard`) verdes — único cambio a tests existentes: `LEDGER_KEYS` suma `"tx_id"` (assert de shape).
- **Task 2 (AC2):** `list_threads` expone `resolved["tx_id"]` (ya se computaba en cada llamada — costo cero) + `ThreadView.tx_id: str | None` declarado (gotcha PR #18: el response_model descarta lo no declarado). Testeado en los 3 estados: resolved=id original, re-anchored=id NUEVO, orphaned=null.
- **Task 3 (AC3/AC4):** `createComment(tx_id, body)` en `ownerComments.ts`; la normalización del `detail` (string | array-422) se extrajo a un helper `errorMessage` compartido con `replyThread` (no duplicada). `Thread.tx_id` y `LedgerEntryRecord.tx_id?` (opcional: datos cacheados viejos no lo traen) agregados.
- **Task 4 (AC3/AC4):** en `TransactionRows`: query compartida `['comment-threads']` (`listThreads('all')`, staleTime 60s — react-query dedupea entre todas las cuentas expandidas = un solo fetch) → `Map<tx_id, thread_id>`. Fila con hilo → badge `MessageSquare` que navega a `/comments?thread=`; sin hilo → `MessageSquarePlus` abre form inline en `<tr>` extra (`colSpan=4`, textarea ≤10k, Enviar disabled si vacío, error legible bajo el form, sin toasts). Éxito → confirmación inline + invalidación de la query (la fila pasa a badge sin recargar). Sin `tx_id` → sin affordance. Visible para los 3 roles (RBAC en el back). Los íconos van en la celda de descripción — layout de 4 columnas intacto.
- **Task 5 (AC5):** `CommentsInboxPage` lee `?thread=` con `useSearchParams`; si hay deep-link arranca en filtro `all` (el hilo aparece aunque esté resuelto), la card destacada con ring + `scrollIntoView` (optional-call: jsdom no lo implementa). `thread_id` inexistente → página carga normal. Nota: los hilos del inbox no son colapsables (7.2 los renderiza completos) → "expandir" = destacar + traer a la vista.
- **Task 6 (AC6):** 5 tests backend nuevos + asserts de `tx_id` en 3 existentes + round-trip `GET /ledger-entries` → `POST /comments` (contrato central). Frontend: 3 component tests nuevos de `TransactionRows` (badge+link / form+submit+confirmación / sin tx_id sin affordance) + 2 de deep-link; `CommentsInboxPage.test.tsx` ahora envuelve en `MemoryRouter` (requerido por `useSearchParams`) y sus fixtures suman `tx_id`. Suites: backend **756 passed / 1 xfailed / 0 failed** (0 regresiones), vitest **112 passed** (16 files), `tsc --noEmit` limpio, eslint limpio sobre los archivos tocados (los 7 errores que reporta `eslint src` son pre-existentes en archivos NO tocados por esta story: Sidebar.test, button.tsx, FilterContext, CartolaUploadPage, IncomeExpensesPage).
- **Bonus estructural:** al eliminar el BQL, `ledger_entries_via_beancount` ya no usa `ledger.connection()` — solo `entries()` — lo que simplificó el round-trip test (el `_FakeLedger` de los tests de comments le sirve directo).

### File List

- backend/app/services/bql_queries.py (M — Task 1: iteración directa + tx_id)
- backend/app/api/v1/dashboard/schemas.py (M — Task 1: LedgerEntryRecord.tx_id)
- backend/app/api/v1/owner_comments/service.py (M — Task 2: list_threads expone tx_id)
- backend/app/api/v1/owner_comments/schemas.py (M — Task 2: ThreadView.tx_id)
- backend/tests/test_bql_queries.py (M — Task 6: 4 tests nuevos + LEDGER_KEYS)
- backend/tests/test_owner_comments_inbox.py (M — Task 6: asserts tx_id en 3 estados + round-trip)
- frontend/src/services/ownerComments.ts (M — Task 3: createComment + errorMessage helper + Thread.tx_id)
- frontend/src/types/index.ts (M — Task 3: LedgerEntryRecord.tx_id)
- frontend/src/components/charts/IncomeExpensesDrilldown.tsx (M — Task 4: affordance + CommentFormRow + query compartida)
- frontend/src/pages/CommentsInboxPage.tsx (M — Task 5: deep-link ?thread= + highlight + scroll)
- frontend/src/components/charts/IncomeExpensesDrilldown.test.tsx (NUEVO — Task 6: component tests)
- frontend/src/pages/CommentsInboxPage.test.tsx (M — Task 6: MemoryRouter + fixtures tx_id + 2 tests deep-link)
- _bmad-output/implementation-artifacts/sprint-status.yaml (M — tracking)
- _bmad-output/implementation-artifacts/7-1b-frontend-comentar-owner.md (M — este archivo)

## Change Log

- 2026-07-10 — dev-story (Amelia): implementación completa Tasks 1–6, AC1–AC6 MET. Backend: tx_id por fila en /ledger-entries (iteración directa de entries, sin BQL) + ThreadView.tx_id resuelto. Frontend: affordance comentar/ver-hilo en el drill-down + deep-link del inbox. Suites: 756 backend / 112 frontend / tsc / eslint verdes, 0 regresiones. Status → review.
- 2026-07-10 — create-story: draft → ready-for-dev. Alcance concretado post-7.2: la "sutileza a resolver" del draft (tx_id por posting vs por tx) queda resuelta con estrategia recomendada (iterar entries, no BQL); se agrega `ThreadView.tx_id` (necesario para el badge, no estaba en el draft) y el deep-link del inbox. 4 defaults técnicos documentados. Infra 7.0/7.1/7.2 verificada file:line contra el código.
