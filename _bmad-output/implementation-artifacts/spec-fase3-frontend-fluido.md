---
title: 'Fase 3 batch 4 — Frontend resiliente y fluido (D9/F4/F7/F8)'
type: 'refactor'
created: '2026-07-07'
status: 'done'
baseline_commit: '5399bde'
context:
  - '{project-root}/_bmad-output/planning-artifacts/review-estabilidad-performance-2026-07-06.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Tres fugas de fluidez en el frontend: (F4) ningún fetch tiene timeout — un backend colgado deja skeletons/"Generando…" infinitos sin feedback; (F8) los tres polls permanentes (sync 5s/60s en el Header, chip de categorización 60s, badge de reconciliación 5min) martillan a cadencia plena a un backend caído/reiniciando, justo cuando está más débil; (F7) el dashboard de Ingresos/Gastos re-corre toda la cadena de agregación (filtros, timeline, drill, totales, `groupByCategoria1` ×2) en CADA render sin `useMemo` — cada click en un chip o pie se siente pesado con el año completo cargado.

**Approach:** Un `apiFetch` drop-in (fetch + `AbortSignal.timeout` + error tipado de red/timeout) adoptado mecánicamente por los services SIN cambiar su manejo de errores; `refetchInterval` error-aware en los tres polls (backoff ×4 con tope en error, cadencia normal al primer éxito); `useMemo` en la cadena de agregación del dashboard sin cambiar ningún número visible.

## Boundaries & Constraints

**Always:** cero cambios de comportamiento visible salvo los deseados (timeout tipado en vez de cuelgue; polls más lentos SOLO en error); el shape de error que cada service lanza hoy se preserva (apiFetch solo agrega la capa red/timeout); los agregados del dashboard son bit-idénticos; suite frontend + tsc verdes, 0 regresiones.

**Ask First:** cambiar cadencias base de los polls; tocar `refetchOnWindowFocus` global; paginación/virtualización de tablas (F7 profundo, otro batch).

**Never:** retry automático en mutaciones (POST/PATCH); tocar backend; tocar el flujo auth (ya tiene su manejo 5xx de Fase 1); endpoint de agregación server-side.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| GET normal | backend sano | idéntico a hoy (apiFetch es transparente) | — |
| Backend colgado (acepta TCP, no responde) | request supera el timeout (30s default) | el fetch aborta → error tipado `TIMEOUT`/mensaje claro → cada service lo propaga por su camino de error actual → la UI muestra su error state en vez de spinner eterno | — |
| Upload PDF / generar reporte | operaciones legítimamente lentas | timeout override (120s) en esas llamadas puntuales | — |
| Red caída | fetch rechaza | mismo error tipado de red (mensaje distinguible de un 4xx/5xx del backend) | — |
| Poll con backend caído | useSyncStatus / chip / badge en error | intervalo se estira (×4, tope 10min) mientras la query esté en error; al primer éxito vuelve la cadencia normal | — |
| Poll de sync corriendo | job running | cadencia rápida actual (5s) intacta en éxito | — |
| Dashboard: click en chip/pie/drill | mismos data+filters | agregados idénticos, computados UNA vez por cambio real de inputs (useMemo) | — |
| Dashboard: cambian data o filtros | nueva data/filtros | los memos recomputan (deps correctas — no stale) | — |
| Polls de la página de confirm/extracción | useCartolaStatus | NO se tocan (cadencia y semántica del batch 2 intactas) | — |

</frozen-after-approval>

## Code Map

- `frontend/src/services/api.ts` — hoy solo `baseUrl`; agregar `apiFetch(url, init?, {timeoutMs}?)`: merge de `AbortSignal.timeout` (si el caller ya pasa signal, combinarlas con `AbortSignal.any`), reject de red/timeout → `Error` tipado con mensaje claro ("El servidor no respondió en Xs" / "Sin conexión")
- `frontend/src/services/*.ts` (cartolas, dashboard, sync, reconciliation, tcReconciliation, categorizacion, cuentasPendientes, bankAccounts, accounts, reportes) — reemplazo mecánico `fetch(` → `apiFetch(`; upload/reporte con `{timeoutMs: 120_000}`; `auth.ts` NO se toca (Fase 1)
- `frontend/src/hooks/useSyncStatus.ts:9-13` — refetchInterval error-aware (query.state.status === 'error' → intervalo ×4 con tope 600_000)
- `frontend/src/components/layout/PendingCategorizationChip.tsx:17` y `PendingReconciliationBadge.tsx:17` — ídem (helper compartido `errorAwareInterval(baseMs)` en `lib/`)
- `frontend/src/pages/IncomeExpensesPage.tsx:66-89` — cadena filterByEntity/applyFilters/buildTimeline/drill/totales → `useMemo` con deps [data, entity, filters, drill]
- `frontend/src/components/charts/IncomeExpensesDrilldown.tsx:194` — `groupByCategoria1` memoizado por [entries, ...props que lo afectan]
- Tests: `frontend/src/services/*.test.ts` (apiFetch), `lib` helper test, `utils/ledgerAnalytics.test.ts` ya fija los agregados (los memos no cambian resultados)

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/services/api.ts` — `apiFetch` + tests: timeout dispara y produce el error tipado; passthrough de respuestas OK y no-OK (un 400 del backend NO se convierte en error de red); signal del caller respetada
- [x] `frontend/src/services/*.ts` — migración mecánica a apiFetch (timeouts override en upload/reporte); los tests existentes de services siguen verdes SIN tocar sus asserts
- [x] `frontend/src/lib/` + los 3 polls — helper `errorAwareInterval` + adopción; test del helper (error → ×4 con tope; éxito → base; función compatible con la firma de refetchInterval de react-query)
- [x] `frontend/src/pages/IncomeExpensesPage.tsx` + `components/charts/IncomeExpensesDrilldown.tsx` — useMemo en la cadena de agregación; test o assert de igualdad de agregados pre/post (reusar fixtures de ledgerAnalytics.test.ts)

**Acceptance Criteria:**
- Given un backend que no responde, when una vista carga datos, then el usuario ve el error state de esa vista en ≤35s (no spinner eterno) con un mensaje que distingue timeout de error del backend
- Given el backend caído, when los polls permanentes corren, then su cadencia baja (×4, tope 10min) y vuelve a la normal al primer éxito
- Given el dashboard con el año completo, when el usuario interactúa (chips, pie, drill), then los agregados mostrados son idénticos a los de hoy y la cadena pesada solo recomputa cuando cambian data/filtros/drill
- Suite frontend completa + tsc verdes, 0 regresiones

## Verification

**Commands:**
- `cd frontend && npx vitest run` — expected: verde, 0 regresiones
- `cd frontend && npx tsc --noEmit` — expected: sin errores

## Design Notes

Adjudicaciones del review de 3 capas (2026-07-07):

- **apiFetch reescrito a AbortController+setTimeout** (patch central del review): mata tres hallazgos de una — (a) Safari <16 rompía TODA la app con `AbortSignal.timeout` sin feature-detection; (b) el timeout ya NO gobierna la lectura del body (`res.json`/`res.blob`) — un `TimeoutError` crudo escapaba del contrato tipado en payloads lentos; (c) la clasificación timeout-vs-red es por IDENTIDAD del reason (race-free), con `cause` preservado y `code` ('TIMEOUT'/'NETWORK') para las UIs que castean.
- **Backoff del sync usa la base idle en error**: el dato stale 'running' dejaba el poll de outage en 20s (3× más agresivo que el idle sano); ahora 240s.
- **retry global no reintenta ApiTimeoutError** (main.tsx): el hung-backend llegaba al error state en 61s (30+retry+30); ahora ≤35s como pide el AC1.
- **El mensaje tipado llega a las vistas**: IncomeExpenses/BalanceSheet mostraban "Error al cargar datos." pelado; ahora anexan el detalle de timeout/red.
- **Poll de cartola con blip transitorio ya no ofrece el "Volver" destructivo** mientras el status conocido siga siendo processing/confirming (cierra el defer F5 de Fase 1).
- **Verificado por Edge Hunter contra node_modules**: react-query v5 flipea `status` a 'error' incluso en background refetch y resetea `fetchFailureCount` al iniciar fetch → el helper de backoff se recupera a cadencia base al primer éxito. Los 22 call-sites migrados conservaron method/credentials/headers/body.
- **Stretch también en first-load con fallos** (`fetchFailureCount > 0` en pending): deliberado — un cold start ya no es martillado.

**Resultado final (2026-07-07):** frontend **100 passed (14 files)**, tsc limpio; 0 regresiones (backend sin tocar). Review 3 capas: Auditor 9/9 filas PASS + boundaries limpias; AC1 tenía 2 misses (61s + mensaje tragado) → cerrados con patches; el HIGH del Blind sobre `applyFilters` fue refutado con el repo (useCallback([selectedPeriods])). 8 patches aplicados, 2 defer (auth.ts con fetch crudo — bloqueado por el Never del spec, renegociar; timeout de upload por tamaño), resto dismiss.

## Suggested Review Order

**apiFetch (la pieza central)**

- Entry point: wrapper AbortController+setTimeout, clasificación por identidad, errores tipados con code/cause
  [`api.ts:1`](../../frontend/src/services/api.ts#L1)

- Migración mecánica de los 10 services (error shapes intactos; upload/reporte 120s)
  [`cartolas.ts:84`](../../frontend/src/services/cartolas.ts#L84)

- retry global exceptúa timeouts
  [`main.tsx:7`](../../frontend/src/main.tsx#L7)

**Polls con backoff**

- Helper errorAwareInterval (×4, tope 10min, tipos v5)
  [`pollInterval.ts:1`](../../frontend/src/lib/pollInterval.ts#L1)

- useSyncStatus compone base dinámica × stretch (base idle en error)
  [`useSyncStatus.ts:9`](../../frontend/src/hooks/useSyncStatus.ts#L9)

**Dashboard memoizado**

- Cadena de agregación en useMemo (movida sobre los early returns por rules-of-hooks)
  [`IncomeExpensesPage.tsx:51`](../../frontend/src/pages/IncomeExpensesPage.tsx#L51)

- groupByCategoria1 memoizado
  [`IncomeExpensesDrilldown.tsx:17`](../../frontend/src/components/charts/IncomeExpensesDrilldown.tsx#L17)

**UX de errores**

- Mensaje tipado en las vistas + blip transitorio del poll sin card destructiva
  [`CartolaUploadPage.tsx:193`](../../frontend/src/pages/CartolaUploadPage.tsx#L193)

**Tests**

- apiFetch (timeout tipado con cause, rama combinada caller-signal+timeout, aborts crudos)
  [`api.test.ts:1`](../../frontend/src/services/api.test.ts#L1)

- Backoff + P5
  [`pollInterval.test.ts:1`](../../frontend/src/lib/pollInterval.test.ts#L1)
