# Review completo de la app — Estabilidad y Performance

**Fecha:** 2026-07-06
**Solicitado por:** Ary — "cuando lo uso se cae muchas veces o se demora demasiado en correr procesos"
**Metodología:** 4 reviews paralelos e independientes (backend, pipeline, frontend, infra/deploy) + verificación cruzada sobre el código real. Todos los hallazgos tienen `path:line` verificado.
**Estado:** Concluido. Plan de remediación abajo (§6), en ejecución.

---

## 1. Veredicto ejecutivo

**Por qué se cae (en lenguaje simple):** cada vez que algo escribe al ledger (importar una cartola, categorizar, el sync nocturno), el backend re-lee y re-procesa el ledger COMPLETO (~60.000 líneas) de una forma que congela el servidor entero por decenas de segundos. Render (el hosting) interpreta ese congelamiento como "el servicio murió" y lo reinicia. Como los trabajos en curso viven solo en la memoria del proceso, cada reinicio mata los uploads en curso — eso es el "staging muerto 404" que ya venía apareciendo. Sospechoso secundario: la instancia tiene poca memoria (512MB presumido) y los picos del proceso pueden gatillar un kill por out-of-memory con síntomas idénticos.

**Por qué es lento:** cada click de escritura (confirmar cartola, categorizar, aprobar diferencia) ejecuta **dentro del request HTTP** 2–3 parseos completos del ledger + una sincronización git contra GitHub por red sin timeout, todo serializado por un lock de archivo. Y la llamada a Gemini (extracción del PDF) no tiene timeout: si se cuelga, el proceso queda "processing" para siempre.

**Lo más grave del review no es performance:** aparecieron 4 bugs de **pérdida/corrupción de datos** latentes (§4) que conviene arreglar antes que cualquier optimización.

---

## 2. Cadena causal de las caídas

| # | Hallazgo | Dónde | Severidad |
|---|----------|-------|-----------|
| C1 | El file-watcher recarga el ledger completo **sincrónicamente sobre el event loop** del único worker de uvicorn. Mientras parsea, el proceso no responde nada — incluido `/api/v1/health` → Render falla el health check → **reinicia el servicio**. Un `git reset --hard` reescribe 92 archivos → varias tandas de reload seguidas. | `backend/app/services/ledger_service.py:142-145` | **CRÍTICA** |
| C2 | El picklecache de beancount se borra a propósito en cada `load()` (workaround legítimo: los includes por glob no invalidan el cache), así que **cada** reload paga el parse completo desde cero. Amplifica C1 y D1. Encima beancount reescribe el cache que se va a volver a borrar (~2.9MB de I/O inútil por reload). | `ledger_service.py:64-75` | ALTA |
| C3 | El watcher recarga **a mitad de escritura** (no coordina con `.import.lock`): parsea un árbol a medio escribir → errores de parse → **toda la API devuelve 503 LEDGER_UNAVAILABLE** hasta el próximo reload limpio. Para el usuario: "se cayó". | `ledger_service.py:132-145` + `middleware.py:79-90` | ALTA |
| C4 | Riesgo de OOM: `render.yaml` no declara `plan:` (presumido Starter 512MB). Ledger en RAM ~100-250MB, ×2 transitorio durante reload; el upload lee el PDF completo a memoria **antes** de validar el límite de 20MB; Gemini re-serializa el PDF en base64 (~27MB) hasta 3 veces. Un OOM-kill de Render se ve exactamente como un crash aleatorio. | `cartolas/router.py:84`, `gemini_client.py:329-340`, `render.yaml` | ALTA |
| C5 | Todo el estado de jobs/staging es memoria de proceso + filesystem efímero → **cada reinicio convierte un upload en curso en falla visible** (amplificador de C1/C4). | `cartolas/service.py:128-178`, `sync/service.py:60-68` | MEDIA |
| C6 | Frontend: un 502/503 del cold-start es indistinguible de un 401 → **bota al usuario al login** con sesión válida. Y no existe ningún error boundary → cualquier excepción de render = pantalla blanca permanente (ya ocurrió: React error #31). | `frontend/src/services/auth.ts:8-10`, `frontend/src/main.tsx:16-22` | ALTA (percepción) |

## 3. Causas de la lentitud

| # | Hallazgo | Dónde | Severidad |
|---|----------|-------|-----------|
| D1 | Cada endpoint de escritura ejecuta en el request: rewrite del archivo → `bean_check` (**parse completo #1**) → `git add/commit/fetch/rebase/push` por SSH **sin timeout** → `ledger.load()` (**parse completo #2**) → y el watcher dispara el **#3**. Aplica a categorizar, bulk, promover cuenta, bank-accounts y validate-balance. 5–20s por click en la instancia chica, serializado entre usuarios por el lock (waiters duermen de a 5s). | `transactions/router.py:57,73,92`, `cartolas/router.py:207`, `laudus_run.py:82-149` | **ALTA** |
| D2 | Gemini sin timeout (default ilimitado del SDK) × 3 reintentos seriales → un cuelgue de red = job "processing" eterno; el usuario ve un proceso que nunca termina. | `gemini_client.py:331-340`, `cartolas/service.py:339` | **CRÍTICA** |
| D3 | Matcher O(n×m) que recalcula `SequenceMatcher.ratio()` 2–3 veces por par sin memoizar → decenas de miles de corridas por reconciliación, CPU puro dentro del request. | `matching_engine.py:99-169` | ALTA |
| D4 | Cada reconciliación parsea los **68 meses** de Laudus para quedarse con uno (los archivos se llaman `YYYY-MM.beancount` pero el glob parsea todo); el sync incremental los parsea **dos veces**. | `matching_engine.py:60-96`, `beancount_writer.py:152-181,240` | ALTA |
| D5 | `append_discrepancy` relee y re-parsea el JSONL completo **por cada discrepancia** del loop (cuadrático, y el archivo es append-only sin compactación → empeora cada mes). | `reconcile.py:443-445`, `discrepancy_writer.py:58-92` | ALTA |
| D6 | Un commit+push+bean_check **por cada discrepancia resuelta** — aprobar 20 diffs = 20 parseos + 20 pushes serializados. | `reconciliation/service.py:215-233` | MEDIA |
| D7 | Vista de cuadre TC: ~6 escaneos del ledger completo por (tarjeta × mes) por request; crece linealmente cada mes. + `BankAccountResolver` re-parsea `accounts.beancount` en cada request. | `tc_reconciliation/service.py:67-107`, `tc_cuadre.py:96-193` | MEDIA |
| D8 | Refetch BCCh: hasta 7 días lookback × 3 intentos × (15s timeout + sleeps) ≈ minutos bloqueando un thread del pool en un request admin. | `fx_bcch_eom.py:144-160` | MEDIA |
| D9 | Frontend: ningún fetch tiene timeout/AbortController → skeletons infinitos sobre backend colgado; polls sin backoff + refetch-on-focus martillan al backend justo cuando arranca; dashboard trae el año completo y re-agrega sin `useMemo` en cada render. | `frontend/src/services/api.ts`, `useSyncStatus.ts`, `IncomeExpensesPage.tsx:66-89` | MEDIA |

## 4. Bugs de datos (los más graves del review — independientes de performance)

| # | Hallazgo | Dónde | Severidad |
|---|----------|-------|-----------|
| B1 | **`bean_check` puede validar contra cache viejo**: no borra el picklecache, así que un archivo nuevo entrado por glob-include es invisible → el gate de seguridad aprueba basura → se commitea y pushea → el próximo reload real ve los errores → 503 en toda la API. Es la misma clase de bug del fixture que ya mordió al proyecto (commit d71f0fe), pero en producción. | `laudus_run.py:82-89` | **CRÍTICA** |
| B2 | **Fetch parcial de Laudus tratado como éxito**: si falla una página a mitad de la paginación, devuelve lo acumulado como si fuera todo. En modo backfill con `replace=True` eso **borra silenciosamente los asientos faltantes del mes** y bean_check pasa igual (el ledger queda internamente consistente). | `pipeline/services/laudus_service.py:113-123` | **CRÍTICA** |
| B3 | **Re-import fallido destruye la cartola anterior**: sobrescribe el archivo bueno con el mismo slug y, si bean_check falla, hace `unlink` en vez de restaurar el contenido previo (reconcile.py sí lo hace bien con snapshot/restore). Un mes entero de TC desaparece del ledger hasta un git restore manual. | `tc_correction.py:683-688`, `cartola_pdf_importer.py:251-257` | **CRÍTICA** |
| B4 | **Dedup key de discrepancias incluye `batch_id`** (cada upload mina uno nuevo) → re-subir la misma cartola duplica todas las discrepancias abiertas; los counts de `/periods` se inflan. | `discrepancy_writer.py:19-21` | ALTA |
| B5 | Lock de import no atómico (TOCTOU `exists()`→`write_text()`) + stale-timeout de 300s más corto que operaciones reales → robo de lock con el holder vivo = dos escritores concurrentes. Y `_refresh_ledger_clone` corre el `reset --hard` **fuera** del lock. | `laudus_run.py:52-76`, `sync/service.py:141-146` | ALTA |
| B6 | Saldos USD invisibles: `_clp()` extrae solo la pata CLP → cuenta denominada en USD muestra 0 en el balance; `ledger_entries` hardcodea `paritytomaincurrency: 1.0`. | `bql_queries.py:46-53,150-164` | MEDIA |
| B7 | Frontend: `Intl.NumberFormat` con currency no-ISO tira `RangeError` → pantalla blanca. Ya parchado en ReconciliationPage/TcReconciliationPage; **quedaron sin el patch** CartolaUploadPage y BalanceValidationPanel (justo el flujo más usado). | `CartolaUploadPage.tsx:18-22`, `BalanceValidationPanel.tsx:13-14` | ALTA |
| B8 | Laudus fetch: paginación `while True` sin tope de páginas → loop infinito posible sosteniendo el lock. `login()` traga todas las excepciones y devuelve None. | `laudus_service.py:23-31,93-111` | MEDIA |

## 5. Hallazgos de infra/config

- **Build filter del dashboard de Render está mal**: observa solo `backend/`, pero la imagen también copia `pipeline/` y `bootstrap/` (`backend/Dockerfile:19-22`) → cambios ahí **no deployan** (trampa silenciosa activa hoy).
- Clone completo del monorepo (sin `--depth 1`) en cada arranque + primer request paga el parse frío → deploys lentos y primer uso post-restart pegajoso (`backend/entrypoint.sh:16`).
- Config drift: plan, cron, build filter y varios env vars viven solo en el dashboard, no en `render.yaml`.
- Puerto 8000 hardcodeado en vez de `$PORT` (frágil).
- Catch-all handler devuelve `str(exc)` al cliente (filtra paths/stderr de git) — `middleware.py:107-119`.

## 6. Plan de remediación (priorizado impacto/esfuerzo)

### Fase 1 — Quick wins de estabilidad (código, en ejecución)
1. **Watcher off-loop + debounce**: `await asyncio.to_thread(self.load)` + coalescer tandas de cambios (2-3s) en `watch_and_reload`. Elimina el ciclo congelamiento → health-check → reinicio. *(Por qué en simple: la recarga del ledger deja de congelar el servidor.)*
2. **Timeouts en todo lo externo**: cliente Gemini (`HttpOptions(timeout=120s)` + deadline total en los reintentos) y `timeout=60` en cada `subprocess.run` de git. *(Nada puede quedarse colgado para siempre.)*
3. **B1**: borrar el picklecache dentro de `bean_check` (reusar la lógica de `LedgerService`).
4. **B2**: raise-on-partial en `get_info_API` — nunca devolver una acumulación parcial como éxito.
5. **B3**: snapshot/restore en `correct_tc_cartola` y `cartola_pdf_importer` (copiar el patrón de `commit_reconciliation`).
6. **Frontend resiliente**: ErrorBoundary global, `getMe` distinguiendo 5xx de 401 (con retry), y `fmt` validado compartido en CartolaUploadPage/BalanceValidationPanel.

### Fase 2 — Infra (config, mayormente dashboard)
7. ⚠️ **GATE Ary (costo recurrente)**: subir el plan del backend a Standard 2GB (~USD 25/mes) y codificar `plan:` en render.yaml. Es la mitigación más barata del OOM.
8. Corregir el build filter: `backend/** + pipeline/** + bootstrap/**`.
9. `git clone --depth 1 --single-branch` en el entrypoint; evaluar disco persistente para el clon + staging (los reinicios pasan a ser invisibles). ⚠️ El disco también tiene costo → gate Ary.

### Fase 3 — Estructural (stories futuras)
10. Confirm/categorización como jobs 202+polling (patrón ya existe en el upload); reusar el parse de bean_check; push git en background batcheado.
11. Lock atómico (`O_CREAT|O_EXCL`) + heartbeat; `reset --hard` dentro del lock; B4 (dedup key sin batch_id); B8 (tope de páginas).
12. Optimizaciones del pipeline: matcher con bucketing por monto + memoización (D3), filtrar meses Laudus por nombre de archivo (D4), hoist del dedup JSONL (D5), batch-resolve de discrepancias (D6), single-pass del cuadre TC (D7).
13. Frontend: wrapper `apiFetch` con timeout + retry 5xx, backoff en polls, `useMemo` en agregaciones del dashboard.
14. B6 (saldos USD) — coordinar con Valentina el tratamiento de conversión antes de tocar el balance.

## 7. Decisiones que requieren aprobación de Ary (gates de project-context)

| Decisión | Costo | Recomendación |
|----------|-------|---------------|
| Plan Render Standard 2GB para el backend | ~USD 25/mes recurrente | **Sí** — mitigación más efectiva del OOM; hoy el plan no está ni versionado en render.yaml |
| Disco persistente para clon del ledger + staging | ~USD 1-7/mes según tamaño | Sí, barato y hace los reinicios invisibles |
| Todo lo demás (Fases 1-3) | Sin costo recurrente | Decisión técnica — auto-aprobada per project-context |

## 8. Referencias

- Reviews fuente: 4 agentes paralelos 2026-07-06 (backend 26 hallazgos, pipeline 26, frontend 12, infra 11) — consolidados y deduplicados en este doc.
- Relacionados: `deferred-work.md` (varios hallazgos coinciden con defers ya anotados: lock durante push, JSONL O(n), TOCTOU staging), `epic-6-retro-2026-06-25.md`, memoria `project_epic6_reconciliacion_next`.
