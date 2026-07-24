---
title: 'Fase 1 — Quick wins de estabilidad (review 2026-07-06)'
type: 'bugfix'
created: '2026-07-06'
status: 'done'
baseline_commit: 'd17505c363e7a734a0f81104cd2a1117d3cc8287'
context:
  - '{project-root}/_bmad-output/planning-artifacts/review-estabilidad-performance-2026-07-06.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La app se cae seguido y los procesos se cuelgan. Causa raíz de las caídas: el file-watcher recarga el ledger completo sincrónicamente sobre el event loop → `/health` no responde → Render reinicia. Además: llamadas externas (Gemini, git) sin timeout que cuelgan procesos para siempre, y 3 bugs de datos críticos (bean_check valida contra picklecache viejo; fetch parcial de Laudus tratado como éxito puede borrar meses en backfill; re-import TC fallido destruye la cartola previa). En frontend, un 502 de cold-start bota al login y no hay error boundary (pantalla blanca).

**Approach:** 6 fixes quirúrgicos e independientes (batch de hardening), cada uno con test que reproduzca el defecto. Sin refactors, sin tocar comportamiento de negocio.

## Boundaries & Constraints

**Always:** cada fix con su test; suite backend (~641) y frontend (~66) en verde sin regresiones nuevas; cambios mínimos que tracen al review (C1, D2, B1, B2, B3, C6/B7); estilo/idioma de comentarios igual al existente.

**Ask First:** cualquier cambio de comportamiento visible más allá de lo especificado; tocar el lock de import (Fase 3); subir dependencias.

**Never:** optimizaciones de performance de Fase 2/3 (matcher, JSONL, plan Render); jobs 202 para confirm; refactor del LedgerService más allá del watcher; retry automático en POSTs del frontend.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Watcher detecta cambios | tanda de N archivos `.beancount` cambiados en ráfaga | UN solo `load()` ejecutado vía `asyncio.to_thread` (loop libre) tras debounce ~2s | excepción del load se loguea, watcher sigue vivo |
| git colgado | push/fetch no responde | `subprocess.run(..., timeout=60)` → TimeoutExpired propaga como fallo de la corrida | rollback existente aplica; lock se libera |
| Gemini colgado | `generate_content` sin respuesta | timeout HTTP 120s por intento → `GeminiExtractionError`/fallo del job (status `failed`) | job no queda `processing` eterno |
| bean_check post-import | archivo nuevo vía glob-include + picklecache viejo presente | picklecache borrado antes de `load_file` → valida el ledger REAL | — |
| Laudus falla a mitad de paginación | error en página k>1 (no-401, sin retry restante) | raise (la corrida se marca failed) — NUNCA devolver acumulación parcial como éxito | run_import reporta error_msg |
| Re-import TC/cartola con bean_check rojo | `out_file` ya existía con contenido bueno | contenido previo RESTAURADO (no unlink) | result reason/error como hoy |
| Frontend: backend 502/503 en `getMe` | Render arrancando | error tipado 5xx → retry (hasta 3, backoff) → pantalla "backend arrancando…", NO redirect a /login | 401 real sigue yendo a /login |
| Frontend: excepción de render | cualquier componente tira | ErrorBoundary global muestra mensaje + botón recargar (no pantalla blanca) | — |
| Frontend: currency malformada | `currency=''`/`'US$'` desde extracción | fmt compartido valida `^[A-Z]{3}$` → fallback CLP, no RangeError | — |

</frozen-after-approval>

## Code Map

- `backend/app/services/ledger_service.py:132-145` — `watch_and_reload` llama `self.load()` sync en el loop → fix 1 (to_thread + debounce)
- `pipeline/importers/laudus_run.py:82-89` — `bean_check` sin borrar picklecache → fix 3; `:106-149` `git_commit_push` subprocess sin timeout → fix 2b
- `backend/app/api/v1/sync/service.py:135-136` — fetch/reset sin timeout → fix 2b
- `backend/app/integrations/gemini_client.py:287-296,331-340` — `genai.Client` sin http_options → fix 2a
- `pipeline/services/laudus_service.py:93-123` — `get_info_API` devuelve parcial como éxito → fix 4
- `pipeline/importers/tc_correction.py:682-688` y `pipeline/importers/cartola_pdf_importer.py:246-258` — overwrite + unlink sin restore → fix 5 (patrón de `reconcile.py:209-217`)
- `frontend/src/services/auth.ts`, `hooks/useAuth.ts`, `App.tsx:17-22` — 5xx≡401 → fix 6a
- `frontend/src/main.tsx` — sin ErrorBoundary → fix 6b (nuevo `components/ErrorBoundary.tsx`)
- `frontend/src/pages/ReconciliationPage.tsx:21-25` — fmt validado a extraer → `lib/format.ts`; consumir en `pages/CartolaUploadPage.tsx:18-22` y `components/BalanceValidationPanel.tsx:13-14` → fix 6c
- Tests: `backend/tests/test_ledger_service.py`, `test_laudus_run.py`, `test_tc_correction.py`, `test_cartola_pdf_importer.py`, `test_gemini_client.py`, `test_sync.py`; frontend `src/**/*.test.tsx` (vitest)

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/services/ledger_service.py` — `watch_and_reload`: acumular tandas con debounce (~2s sin cambios nuevos) y ejecutar `await asyncio.to_thread(self.load)`; try/except que loguea y continúa — evita congelar el event loop (causa raíz de reinicios) *(implementado con `debounce=2000` de awatch, que agrupa la ráfaga en tandas)*
- [x] `backend/app/integrations/gemini_client.py` — `genai.Client(..., http_options=types.HttpOptions(timeout=120_000))` — un cuelgue HTTP no puede dejar el job en processing eterno
- [x] `pipeline/importers/laudus_run.py` — `timeout=60` en todos los `subprocess.run` de `git_commit_push` (y rev-parse); `bean_check` borra `.{main}.picklecache` antes de `load_file` — gate valida el ledger real
- [x] `backend/app/api/v1/sync/service.py` — `timeout=60` en fetch/reset de `_refresh_ledger_clone`
- [x] `pipeline/services/laudus_service.py` — `get_info_API`: en el except tras páginas parciales (`all_records` no vacío), raise en vez de return parcial; página 0 sin retry puede seguir devolviendo None (contrato actual)
- [x] `pipeline/importers/tc_correction.py` + `pipeline/importers/cartola_pdf_importer.py` — snapshot del contenido previo de `out_file` antes de `write_text`; en bean_check rojo restaurar (unlink solo si no existía)
- [x] `frontend/src/lib/format.ts` — nuevo: `fmt` validado (regex `^[A-Z]{3}$` + fallback CLP, patrón de ReconciliationPage); consumirlo en `ReconciliationPage`, `TcReconciliationPage`, `CartolaUploadPage.formatAmount`, `BalanceValidationPanel.fmt`
- [x] `frontend/src/services/auth.ts` + `frontend/src/hooks/useAuth.ts` + `frontend/src/App.tsx` — `getMe` lanza `ServerUnavailableError` para status ≥500/network; `useAuth` retry solo para ese error (3, backoff); `RequireAuth` muestra estado "backend arrancando" en vez de Navigate cuando el error es 5xx
- [x] `frontend/src/components/ErrorBoundary.tsx` + `frontend/src/main.tsx` — class component boundary con mensaje y botón recargar, envolviendo `<App />`
- [x] Tests nuevos por fix (matriz I/O): watcher usa to_thread/no bloquea + un load por tanda; bean_check ve archivo nuevo con cache viejo presente; get_info_API parcial → raise; re-import rojo restaura contenido previo; timeout wire-up de git (assert `timeout` kwarg); frontend: ErrorBoundary atrapa, getMe distingue 5xx/401 (unit), fmt fallback CLP

**Acceptance Criteria:**
- Given una tanda de cambios `.beancount`, when el watcher recarga, then el event loop queda libre (load corre en thread) y se ejecuta UNA recarga por tanda
- Given un picklecache stale y un archivo nuevo por glob, when corre `bean_check`, then el resultado refleja el contenido nuevo
- Given una paginación Laudus que falla a mitad, when `run_import` la consume, then la corrida termina failed y NO se escribe ningún month file
- Given un `out_file` bueno existente y un re-import cuyo bean_check falla, when termina la operación, then el archivo conserva el contenido previo
- Given backend devolviendo 503, when la app monta con sesión válida, then el usuario NO es redirigido a /login y ve el estado de espera
- Suites backend y frontend completas en verde (rojos pre-existentes documentados no cuentan)

## Verification

**Commands:**
- `python -m pytest backend/tests -q` — expected: todo verde salvo rojos pre-existentes conocidos (ninguno nuevo)
- `cd frontend && npx vitest run` — expected: todo verde
- `cd frontend && npx tsc --noEmit` — expected: sin errores

**Resultado final (2026-07-06):** backend 672 passed / 1 xfailed (0 regresiones; +31 tests nuevos vs baseline), frontend 78 passed, tsc limpio. Review 3 capas (Blind + Edge + Auditor): Auditor PASS en todos los AC; 12 patches aplicados post-review, 4 defer (en deferred-work.md), 6 dismiss.

## Suggested Review Order

**Fix 1 — watcher off-loop (la causa raíz de los reinicios)**

- Entry point: load en thread + debounce + watcher que sobrevive a load roto y a crash de awatch
  [`ledger_service.py:132`](../../backend/app/services/ledger_service.py#L132)

- Test clave: una tanda = UNA recarga, en thread distinto al loop, con wire-up de debounce asserted
  [`test_ledger_service.py:148`](../../backend/tests/test_ledger_service.py#L148)

**Fix 2 — timeouts (nada puede colgarse para siempre)**

- Constante y racional del tope de git
  [`laudus_run.py:79`](../../pipeline/importers/laudus_run.py#L79)

- Patch del review: TimeoutExpired en el rebase aborta antes de propagar (evita repo wedged)
  [`laudus_run.py:157`](../../pipeline/importers/laudus_run.py#L157)

- Timeout HTTP del cliente Gemini (120s)
  [`gemini_client.py:289`](../../backend/app/integrations/gemini_client.py#L289)

- fetch/reset del refresh del clon con tope
  [`sync/service.py:135`](../../backend/app/api/v1/sync/service.py#L135)

**Fix 3 — bean_check ve el ledger real**

- Borra el picklecache antes de validar + tolera PermissionError concurrente
  [`laudus_run.py:86`](../../pipeline/importers/laudus_run.py#L86)

- Test con control negativo: primero prueba que el cache stale oculta el archivo roto, después que bean_check lo ve
  [`test_laudus_run.py:300`](../../backend/tests/test_laudus_run.py#L300)

**Fix 4 — fetch parcial de Laudus nunca es éxito**

- raise-on-partial en el except + rama de formato-inesperado en página >1 (patch del review)
  [`laudus_service.py:104`](../../pipeline/services/laudus_service.py#L104)

- Suite nueva: parcial→raise, retry-completo, página-0→None, happy path
  [`test_laudus_service.py:1`](../../backend/tests/test_laudus_service.py#L1)

**Fix 5 — re-import fallido restaura en vez de borrar**

- Snapshot/restore en TC (patrón de commit_reconciliation)
  [`tc_correction.py:686`](../../pipeline/importers/tc_correction.py#L686)

- Ídem en promote de cartola cuenta corriente
  [`cartola_pdf_importer.py:254`](../../pipeline/importers/cartola_pdf_importer.py#L254)

- Tests no-vacuos (patch del review): el re-import trae contenido DISTINTO y se asserta que gana el viejo
  [`test_tc_correction.py:928`](../../backend/tests/test_tc_correction.py#L928)

**Fix 6 — frontend resiliente a cold-start**

- 5xx/red ≠ 401: clase de error dedicada en getMe
  [`auth.ts:5`](../../frontend/src/services/auth.ts#L5)

- Retry con backoff + sondeo cada 5s mientras el server no responde (patch del review: el cold-start dura más que los 3 retries)
  [`useAuth.ts:8`](../../frontend/src/hooks/useAuth.ts#L8)

- Pantalla "servidor arrancando" en vez de bota-al-login
  [`App.tsx:19`](../../frontend/src/App.tsx#L19)

- ErrorBoundary global (fin de las pantallas blancas)
  [`ErrorBoundary.tsx:1`](../../frontend/src/components/ErrorBoundary.tsx#L1)

- fmt compartido validado; 'usd' minúscula se normaliza en vez de re-etiquetar CLP (patch del review)
  [`format.ts:5`](../../frontend/src/lib/format.ts#L5)

**Periféricos**

- Tests de timeouts de git (remote sembrado para ejercitar la rama del rebase) + abort en timeout
  [`test_laudus_run.py:325`](../../backend/tests/test_laudus_run.py#L325)

- Tests frontend nuevos (format, ErrorBoundary, auth)
  [`format.test.ts:1`](../../frontend/src/lib/format.test.ts#L1)

- Defers del review (4, pre-existentes) anotados en
  [`deferred-work.md:3`](deferred-work.md#L3)
