# Story 7.1b: Frontend — el owner crea un comentario desde la app (UI de AC6 de 7.1)

Status: draft

<!-- Desprendida de 7.1 (2026-07-09, decisión Ary). El backend `POST /api/v1/comments` ya está
     entregado y testeado en 7.1. Esta story es SOLO la UI de crear comentario, que se difirió por
     un gap de arquitectura (ver Contexto). Recomendado: hacerla JUNTO con 7.2 (inbox contador) y
     7.4 (notificaciones), que traen la UI de LEER/mostrar hilos — así la de crear se diseña con la
     de leer y no se construye algo que se rehace. -->

## Story

As a **owner del family office (rol `family`)**,
I want **un botón "Comentar" sobre una transacción en la app**,
so that **pueda crear el comentario raíz (que el backend de 7.1 ya sabe persistir) sin salir de la app**.

## Contexto — por qué se difirió (gap de `tx_id`)

El backend de 7.1 (`POST /api/v1/comments`) ancla el comentario por el **`tx_id` de beancount**
(`compute_tx_id(filename, lineno, narration, amount)`, `transactions/service.py`). Al implementar la
UI se descubrió que **ninguna vista del owner expone ese `tx_id`**:

- **`/reportes` (Reporte de Gastos)** es un botón de **descarga** de Excel — no muestra filas de tx.
- El **drill-down de Ingresos/Gastos** (`IncomeExpensesDrilldown` / `TransactionRows`, la única tabla
  de transacciones que el owner ve) identifica cada fila por `journalentryid`/`lineid`
  (`LedgerEntryRecord`, modelo Laudus/dashboard), **no** por el `tx_id` de beancount.
- El `tx_id` de beancount **solo** se expone hoy en `CategorizacionPage` → endpoint `transactions`
  (`list_pending`), que es **contador/admin** (el owner no lo ve).

Por eso enganchar el botón "Comentar" exige una decisión de vista + trabajo extra. Las 3 opciones que
se le presentaron a Ary (eligió **diferir**):

1. **Exponer el `tx_id` de beancount por fila en el drill-down de Ingresos/Gastos** y poner ahí el
   botón. Requiere que el endpoint del dashboard/ledger devuelva el `tx_id` de beancount por fila
   (o un mapeo `journalentryid` ↔ `tx_id`, que no es trivial: son dos representaciones distintas del
   mismo dato). Toca el path del dashboard (riesgo bajo-medio).
2. **Vista de transacciones del owner nueva** que consuma el endpoint `transactions` (que sí trae
   `tx_id`), con el botón por fila. Página nueva, no toca el dashboard.
3. Diferir (lo elegido) — resolver 1 vs 2 cuando se diseñe junto con la UI de leer hilos.

## Alcance (cuando se retome)

- `frontend/src/services/ownerComments.ts` — `createComment(tx_id, body)` (patrón `fetch` +
  `credentials:'include'` de `reconciliation.ts`), contra `POST /api/v1/comments`.
- Componente `TxCommentButton`/input embebible, **visible para `family`** (no filtrar por rol
  contador). Confirmación inline al éxito (estilo Cards/badges, sin toast), error legible al fallo.
- Cablearlo en la vista que se decida (opción 1 o 2 de arriba).
- Component test (vitest) del botón/input: submit → llama `createComment`, muestra confirmación.

## Decisión pendiente para retomar

- **Opción 1 (tx_id en el drill-down) vs Opción 2 (vista nueva de transacciones del owner).**
  Recomendado resolverlo junto con 7.2/7.4 (UI de leer hilos), porque la vista donde se leen los
  hilos es probablemente la misma donde conviene crear el comentario.

## References

- [Source: 7-1-owner-crea-comentario.md] — backend entregado (endpoint + ancla + tests).
- [Source: frontend/src/components/charts/IncomeExpensesDrilldown.tsx] — `TransactionRows` usa `journalentryid`/`lineid`.
- [Source: frontend/src/types/index.ts:58] — `LedgerEntryRecord` (sin `tx_id` de beancount).
- [Source: frontend/src/pages/CategorizacionPage.tsx] — única vista con `tx_id` (contador/admin).
