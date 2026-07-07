---
title: 'Fase 3 batch 2 — Confirm de cartola como job 202+polling (D1)'
type: 'feature'
created: '2026-07-06'
status: 'done'
baseline_commit: '0798994'
context:
  - '{project-root}/_bmad-output/planning-artifacts/review-estabilidad-performance-2026-07-06.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Confirmar una cartola (`PATCH /cartolas/{batch_id}/validate-balance`) es un request sincrónico de 30-120s (matching + bean_check + git push + reload del ledger + cuadre TC dentro del HTTP request). El browser/proxy puede cortar antes de que termine, el usuario reintenta, y el click queda "pegado" — la queja principal de lentitud.

**Approach:** Mismo patrón que el upload ya usa: validaciones baratas sincrónicas (404/400 inmediatos), después 202 + job en el `_JobStore` existente; el trabajo pesado corre en background; el frontend pollea `GET /cartolas/{batch_id}` (el mismo poll de la extracción) hasta `confirmed`/`confirm_failed` y muestra el resultado con la misma semántica de errores de hoy.

## Boundaries & Constraints

**Always:** los errores baratos mantienen su shape/status actual EN el PATCH (404 NOT_FOUND staging, 400 JUSTIFICATION_TOO_SHORT, 400 VALIDATION_FAILED con diff/calculated/stated); los errores del camino pesado (BEAN_CHECK_FAILED, blocked+reason, fallas git) llegan vía polling con el mismo código/detalle que hoy; un solo confirm en vuelo por batch (re-PATCH mientras corre → 202 idempotente, sin segundo thread); `validate_balance()` (service) queda como función sincrónica reutilizable — el async es capa del router/job.

**Ask First:** cambiar la semántica de algún error tipado; tocar el flujo de extracción existente más allá de extender el union de status.

**Never:** jobs persistentes/DB (in-memory como el upload, mismo TTL); async para otros endpoints (categorización/promover = batch futuro); tocar `reconcile_cartola`/`correct_tc_cartola` (pipeline intacto); retry automático del confirm en frontend.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Confirm feliz (cta cte) | staging ok, balance cuadra | PATCH → 202 `{status:"confirming"}`; poll → `confirmed` + payload ValidateBalanceResult actual | — |
| Confirm feliz (TC) | staging TC ok | 202; background corre correct + `ledger.load()` + `compute_tc_cuadre`; poll → `confirmed` + TcCorrectionResponse con `cuadre` | cuadre falla → payload sin cuadre (como hoy, no bloquea) |
| Staging no existe | batch expirado | PATCH → 404 NOT_FOUND (sincrónico, como hoy) | — |
| Justificación corta | override < 20 chars | PATCH → 400 JUSTIFICATION_TOO_SHORT (sincrónico) | — |
| Balance no cuadra sin override | diff ≠ 0 | PATCH → 400 VALIDATION_FAILED + diff/calculated/stated (sincrónico — solo lee el staging, es barato) | — |
| bean_check falla en background | sibling roto | poll → `confirm_failed` + error `{code:"BEAN_CHECK_FAILED", detail}` (semántica del 422 actual) | job no queda colgado |
| TC blocked | fx fuera de tolerancia | poll → `confirmed` con `status:"blocked"` + reason (blocked es un RESULTADO, no un error — como hoy) | — |
| Double-submit | 2º PATCH con job `confirming` | 202 con el mismo batch_id, NO se lanza segundo background task | — |
| Excepción no tipada en background | git push muere, etc. | poll → `confirm_failed` + `{code:"INTERNAL_ERROR", message}` | logueada con traceback |
| Job expirado post-confirm | TTL 1h pasó | GET → 404 (comportamiento actual del store) | frontend ya lo maneja (batch muerto) |
| Usuario navega y vuelve | job `confirming` en curso | al volver, el poll retoma y muestra el resultado (batch_id ya persiste en sessionStorage) | — |

</frozen-after-approval>

## Code Map

- `backend/app/api/v1/cartolas/service.py:128-182` — `_JobStore`: agregar estados `confirming/confirmed/confirm_failed` + campo `result`; métodos `set_confirming/set_confirmed/set_confirm_failed`; `create` si el entry expiró pero el staging vive
- `backend/app/api/v1/cartolas/service.py:448-526` — `validate_balance()` queda igual (sync, reutilizable); nueva `run_confirm_job(batch_id, opening, closing, justification, user_email, ledger, gemini=None)` que ejecuta validate_balance + el post-proceso del router actual (ledger.load + cuadre TC) y setea el job
- `backend/app/api/v1/cartolas/router.py:159-219` — PATCH: cheap checks sincrónicos (leer staging: existencia, justificación, diff sin override) → 202 + `background_tasks.add_task(run_confirm_job, ...)`; el post-proceso TC se muda al job
- `backend/app/api/v1/cartolas/router.py:130-156` + `schemas.py` — `StatusResponse`: union de status extendido + `result` + `error` tipado
- `frontend/src/services/cartolas.ts:145` — `validateBalance` maneja 202 (devuelve marker) y mantiene el throw tipado para 400/404; `CartolaStatus` type extendido
- `frontend/src/hooks/useCartolaUpload.ts:34-37` — `refetchInterval` también pollea mientras `confirming`
- `frontend/src/components/BalanceValidationPanel.tsx:41-52` + `frontend/src/pages/CartolaUploadPage.tsx:259-381` — al 202: estado "Confirmando…" (botón disabled); el poll de la página detecta `confirmed` → `setValidated(result)` / `confirm_failed` → error card con el mismo copy de hoy
- Tests: `backend/tests/test_cartolas_router.py` (endpoint), `test_validate_balance.py` (service, sin cambios), `test_cartolas_service.py` (job store); frontend `src/pages/*.test.tsx` + tests nuevos del flujo

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/api/v1/cartolas/service.py` — estados/campos nuevos del `_JobStore` + `run_confirm_job` (mapea BeanCheckFailed→BEAN_CHECK_FAILED, StagingNotFound→NOT_FOUND, Exception→INTERNAL_ERROR con log; resultado corrected incluye cuadre)
- [x] `backend/app/api/v1/cartolas/router.py` + `schemas.py` — PATCH 202 con cheap-checks sincrónicos y guard de double-submit; GET expone status/result/error nuevos
- [x] `frontend/src/services/cartolas.ts` + `hooks/useCartolaUpload.ts` — 202 handling + poll durante `confirming` + types
- [x] `frontend/src/components/BalanceValidationPanel.tsx` + `pages/CartolaUploadPage.tsx` — estado Confirmando…, resultado desde el poll, errores tipados con el mismo copy actual
- [x] Tests: PATCH→202 + poll→confirmed (TestClient corre el background task); cheap errors siguen 404/400 sincrónicos; bean_check roto → confirm_failed BEAN_CHECK_FAILED; double-submit no relanza; frontend: servicio maneja 202, componente muestra confirmando/confirmed

**Acceptance Criteria:**
- Given una cartola staged válida, when el contador confirma, then el PATCH responde en <1s con 202 y el resultado (incl. cuadre TC) llega por el poll con el mismo contenido que la respuesta sincrónica actual
- Given un staging inexistente / justificación corta / balance sin override, when se confirma, then los 404/400 actuales llegan sincrónicos con el shape exacto de hoy
- Given un bean_check rojo en el camino pesado, when el poll consulta, then recibe `confirm_failed` con code BEAN_CHECK_FAILED y el detalle
- Given un confirm en vuelo, when se re-PATCHea el mismo batch, then no se lanza un segundo job
- Suites backend y frontend + tsc verdes, 0 regresiones

## Verification

**Commands:**
- `python -m pytest backend/tests -q` — expected: verde, 0 regresiones
- `cd frontend && npx vitest run && npx tsc --noEmit` — expected: verde

## Design Notes

Adjudicaciones del review de 3 capas (2026-07-06):

- **BeanCheckFailed está inerte desde 6.1** (el flujo TC real devuelve `status:blocked`, nunca lanza) — el mapping a `BEAN_CHECK_FAILED` se conserva como belt y quedó fijado con un test sintético.
- **Double-submit descarta parámetros cambiados**: el 202 idempotente ES el comportamiento congelado del spec; el botón deshabilitado del panel evita el caso en la práctica. Si algún día molesta: comparar payloads y devolver 409.
- **INTERNAL_ERROR es genérico** (patch del review): `str(exc)` de git puede traer URLs/paths del server; el detalle queda en los logs.
- **El payload del confirm hace round-trip por los modelos pydantic** (patch): mismos defaults/validación que la respuesta sincrónica vieja (incl. `git_commit_sha`, no `git_sha` — paridad exacta).
- **Hallazgos pre-existentes arreglados de pasada** (destapados por el Edge Hunter al trazar el contrato): `validate_balance` dropeaba `cuadre_bank_account_id` (C3 del cuadre corría sin scope desde 6.6) y `fx_source` (el banner de fx heredado de f100c8f nunca podía mostrarse desde este payload).

**Resultado final (2026-07-06):** backend **684 passed / 1 xfailed**, frontend **87 passed**, tsc limpio; 0 regresiones. Review 3 capas: Auditor — boundaries todas PASS, shapes de error byte-idénticos vs baseline; 2 claims de tests marcados sin existir (V1/V2) → cerrados con tests reales de precheck (ambos 400 end-to-end sin mocks), blocked-via-poll y BeanCheckFailed sintético. 10 patches aplicados (canonical backfill en revive, guards de transición del store, round-trip pydantic, retry sin re-upload tras confirm_failed, logs de no-op, diff en detail, mensaje genérico), 2 defer, resto dismiss/refutado (el store in-memory refuta el "confirming zombie" post-restart: un restart = 404 = cleanup existente).

## Suggested Review Order

**Contrato del job (backend)**

- Entry point: PATCH → cheap-checks sincrónicos + 202 + canonical al store
  [`router.py:159`](../../backend/app/api/v1/cartolas/router.py#L159)

- Estados nuevos del _JobStore: set_confirming (revive+backfill), guards de transición en set_ready/set_failed, logs de no-op
  [`service.py:151`](../../backend/app/api/v1/cartolas/service.py#L151)

- precheck_balance: los errores baratos, sincrónicos y byte-idénticos (devuelve el modelo parseado)
  [`service.py:564`](../../backend/app/api/v1/cartolas/service.py#L564)

- run_confirm_job: camino pesado + post-proceso TC + round-trip pydantic + mapeo de errores tipados
  [`service.py:610`](../../backend/app/api/v1/cartolas/service.py#L610)

- Fix pre-existente: cuadre_bank_account_id + fx_source ya viajan en el payload TC
  [`service.py:552`](../../backend/app/api/v1/cartolas/service.py#L552)

**Frontend (polling + estados)**

- validateBalance 202 + types del status union
  [`cartolas.ts:145`](../../frontend/src/services/cartolas.ts#L145)

- Poll durante confirming
  [`useCartolaUpload.ts:29`](../../frontend/src/hooks/useCartolaUpload.ts#L29)

- CartolaResult: confirming/confirmed/confirm_failed + retry sin re-upload (patch del review)
  [`CartolaUploadPage.tsx:196`](../../frontend/src/pages/CartolaUploadPage.tsx#L196)

**Tests**

- Backend: 202+poll, double-submit, blocked, BeanCheckFailed, INTERNAL_ERROR genérico
  [`test_cartolas_router.py:141`](../../backend/tests/test_cartolas_router.py#L141)

- Backend: los 400 sincrónicos ejercitando precheck REAL (sin mocks)
  [`test_validate_balance.py:200`](../../backend/tests/test_validate_balance.py#L200)

- Frontend: 202 parsing, shouldKeepPolling, cards por estado
  [`CartolaUploadPage.test.tsx:1`](../../frontend/src/pages/CartolaUploadPage.test.tsx#L1)
