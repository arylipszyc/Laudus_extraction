# Story 7.1b: Superficie del owner en el drill-down — leer hilo + crear comentario sobre una transacción

Status: draft

<!-- REFRAMED 2026-07-09 (decisión Ary, dos preguntas en create-story):
     (1) "Bundle con la UI de leer hilos (7.2/7.4)" en vez de crear-suelto.
     (2) Decomposición: 7.2 primero (backend de hilos + inbox contador + LEER del owner) →
         LUEGO esta 7.1b reframeada = la superficie de CREAR del owner, en el drill-down de
         Ingresos/Gastos (Opción A), que ahora se diseña con la de leer ya construida → sin rework.
     DEPENDE de 7.2 (backend GET /comments + list_threads + resolve_anchor ya montados).
     La antigua versión "crear-suelto, vista por decidir" quedó obsoleta: la decisión de vista ya
     está tomada (Opción A: drill-down) y el gap de tx_id se resuelve exponiéndolo en /ledger-entries. -->

## Story

As a **owner del family office (rol `family`)**,
I want **ver, sobre cada fila de transacción del drill-down de Ingresos/Gastos, si ya hay un hilo de comentario y poder abrir uno nuevo ("¿qué es este cargo?") ahí mismo**,
so that **pueda preguntarle al contador sobre un movimiento sin salir de la vista donde lo estoy mirando — y el comentario queda pegado a esa transacción (backend de 7.1, ya entregado)**.

## Contexto — por qué se reframeó (gap de `tx_id`, ya con decisión)

El backend de 7.1 (`POST /api/v1/comments`, DONE) ancla por el **`tx_id` de beancount**
(`compute_tx_id(filename, lineno, narration, amount)`). Al implementar la UI se destapó que **ninguna
vista del owner expone ese `tx_id`** (verificado 2026-07-09):

- **`/reportes` (`ReportesPage`)** es solo un botón de **descarga** de Excel — **no** hay filas de tx
  (`frontend/src/pages/ReportesPage.tsx`, verificado). La "decisión resuelta" que 7.1 anotó ("botón
  en la fila del reporte de gastos") era **infeasible** por esto.
- El **drill-down de Ingresos/Gastos** (`IncomeExpensesDrilldown` → `TransactionRows`, la única tabla
  de tx que el owner ve) identifica cada fila por `journalentryid`/`lineid`, que además vienen
  **`None`** desde el engine Beancount: `ledger_entries_via_beancount` hace
  `SELECT date, account, narration, number, currency` y **no** computa `tx_id`
  (`backend/app/services/bql_queries.py:115`).
- El `tx_id` de beancount solo se expone hoy en `CategorizacionPage` → endpoint `transactions`
  (`list_pending`, contador/admin, y **solo trae pendientes**, no todas las tx).

**Decisión tomada (Ary 2026-07-09): Opción A — exponer `tx_id` en el drill-down.** Esta story:
1. Agrega `tx_id` por fila al endpoint `/ledger-entries` (path del dashboard).
2. Pone la superficie de leer-hilo + crear-comentario del owner en el drill-down.

Se hace **después de 7.2** (que trae el backend de leer hilos `GET /comments` + `list_threads` +
`resolve_anchor` y la vista de leer del owner), así el "crear" se diseña con el "leer" ya existente.

## Alcance (cuando se retome, post-7.2)

### Backend — `tx_id` por fila en el drill-down (Opción A)
- Exponer el `tx_id` de beancount en `ledger_entries_via_beancount` / `LedgerEntryRecord`.
  **Sutileza a resolver:** `compute_tx_id` usa el `filename` + `lineno` + `narration` + monto de la
  **primera pata** de la transacción; el BQL actual itera **por posting** y muestra el monto de la
  pata de esa cuenta. Para emitir el `tx_id` correcto por fila hay que resolver el `tx_id` **a nivel
  de transacción padre** (no de posting) — probablemente iterando `ledger.entries()` con
  `compute_tx_id`/`_tx_id_of` (como hace `transactions/service.py`) en vez de vía BQL puro, o
  enriqueciendo las filas del BQL con el `tx_id` de su tx. Decidir en dev-story.

### Frontend — superficie owner en el drill-down
- `frontend/src/services/ownerComments.ts` — `createComment(tx_id, body)` contra `POST /api/v1/comments`
  (lo crea 7.2; acá se reusa/extiende). Patrón `fetch` + `credentials:'include'` de `reconciliation.ts`.
- En `TransactionRows` (`IncomeExpensesDrilldown.tsx`): por fila, affordance "comentar / ver hilo"
  visible para `family`. Al crear → `POST /comments` con el `tx_id` de esa fila; confirmación inline
  (estilo Cards/badges, sin toast); error legible. Mostrar si la fila ya tiene hilo (reusar el
  `GET /comments` de 7.2 filtrado por `tx_id`/`thread`).
- Component test (vitest) del affordance: submit → llama `createComment`, muestra confirmación.

## Anti-alcance
- **No** inbox del contador (7.2). **No** notificaciones/chip (7.4). **No** resolución (7.3).
- **No** line-item (diferido en 7.0).

## References

- [Source: 7-1-owner-crea-comentario.md] — backend `POST /comments` entregado (endpoint + ancla + tests).
- [Source: 7-2-inbox-contador-respuesta.md] — backend de leer hilos + `ownerComments.ts` (dependencia).
- [Source: backend/app/services/bql_queries.py#L115] — `ledger_entries_via_beancount` (donde agregar `tx_id`).
- [Source: backend/app/api/v1/transactions/service.py#L31] — `compute_tx_id` / `_tx_id_of` (a reusar).
- [Source: frontend/src/components/charts/IncomeExpensesDrilldown.tsx] — `TransactionRows` (superficie del owner).
- [Source: frontend/src/pages/CategorizacionPage.tsx] — única vista con `tx_id` hoy (contador/admin).
