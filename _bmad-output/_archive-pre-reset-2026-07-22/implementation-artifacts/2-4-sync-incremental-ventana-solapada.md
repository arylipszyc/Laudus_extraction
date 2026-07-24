# Story 2.4: Sync incremental Laudus→Sheets — ventana solapada para asientos posteados-tarde + rebuild que no falla en silencio

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **contador**,
I want **que el sync incremental Laudus→Sheets re-pida en cada corrida una ventana hacia atrás (no solo `[última fecha+1 .. hoy]`) y que un fallo del rebuild de `ledger_final` deje de tragarse en silencio**,
so that **los asientos que el contador postea/ajusta semanas después con fecha backdateada aparezcan en el reporte, y una corrida a medias sea visible y re-intentable en vez de dejar la fuente congelada sin aviso**.

## Contexto del defecto (verificado con datos — 2026-06-15)

El reporte de gastos (Epic 10) reproduce a Laudus al peso donde hay datos, pero su fuente `ledger_final` (Google Sheets) sub-extrae los meses recientes. Dos bugs concatenados, ya diagnosticados en `investigations/reporte-egresos-datos-incompletos-investigation.md`:

- **Bug #1 — rebuild silencioso (causa raíz reparada por separado).** El crash `_eomonth` con fechas ISO "T" ya se arregló (`pipeline/models.py:122`, commit `9e75957`) y se deployó. Lo que **queda** es el **patrón**: `sync_api()` envuelve todo en un `try/except` global (`pipeline/sync.py:250`) que se traga cualquier excepción → `date_range` avanza y `ledger` crece mientras `ledger_final` queda congelado, sin que el job se marque `failed`.
- **Bug #2 — under-fetch por watermark forward-only (PENDIENTE, esta story).** `get_date_range` pide `[dateTo+1 .. hoy]` y avanza `dateTo` a hoy. Un asiento con fecha contable detrás del watermark cuando aparece en Laudus **no se re-pide jamás**. Medido (gasto capturado vs API Laudus): ene/feb 100%, mar 41%, abr 11%, may 9%. Ej: Casa Sur cta 413900 mayo = $120.871.410 en Laudus vs $0 en `ledger`.

La data 2026 ya se reparó manualmente con un backfill idempotente (1.503 filas re-fetch → +545 asientos). **Esta story hace durable ese parche** para que no haya que re-correr el backfill como remiendo recurrente.

> **Ubicación (decidida):** se coloca en **Epic 2 como Story 2.4 (reapertura)** por su linaje técnico — es una **regresión de Story 2.2 "incremental-sync-deduplicación-y-confiabilidad"** (`pipeline/sync.py`). El consumidor del valor es el reporte de Epic 10, pero el código y la causa raíz viven en el pipeline de sync de Epic 2. Epic 2 vuelve a `in-progress` mientras esta story está abierta.

## Acceptance Criteria

1. **Ventana solapada hacia atrás.** El sync re-pide en cada corrida una ventana que cubre **el año fiscal en curso + margen para backdating de cierre del año anterior (≈ últimos 13 meses)**, configurable por env var. Operacionalización: `get_date_range` cambia de `date_from = dateTo+1` a `date_from = min(dateTo+1, inicio_de_ventana_solapada)`; `date_to = hoy`. Un asiento posteado-tarde/backdateado cuya fecha contable caiga **dentro de la ventana** se recupera en la corrida siguiente.
2. **Idempotencia preservada.** El upsert sigue deduplicando por clave `journalentryid_lineid` (`upsert_to_sheet`, ya existente). Re-pedir la ventana no duplica ni borra filas ya presentes. **Test:** dos corridas seguidas sobre el mismo input dejan `ledger` con el mismo conjunto de filas (sin crecimiento espurio).
3. **Test de regresión del Bug #2.** Un asiento con fecha contable en un mes pasado-pero-dentro-de-ventana, que se ingresa a Laudus **después** de que el watermark (`date_range.dateTo`) ya pasó ese mes, **aparece** en `ledger` tras el sync. (Hoy, con forward-only, no aparece — el test debe fallar contra el código actual y pasar con el fix.)
4. **El fallo del rebuild deja de ser silencioso.** Si el rebuild de `ledger_final` lanza, **o** si tras una corrida con datos `len(ledger_final) != len(ledger)`, se loguea error/alerta **y** el job se marca `failed` con `error` poblado, reflejado en `GET /sync/status`. (Invariante verificada: `enrich_ledger_row` mapea 1:1 — una fila de `ledger` → una de `ledger_final`, sin colapso; ver Dev Notes. El dev debe confirmar empíricamente y, solo si encuentra un colapso real y documentado, introducir una tolerancia con su justificación; por defecto la igualdad es exacta.)
5. **El watermark no avanza en una corrida a medias.** `date_range.dateTo` no se actualiza a un valor nuevo salvo que la corrida completa — **incluido el rebuild de `ledger_final`** — haya tenido éxito. Una corrida que falla a mitad es re-intentable (la siguiente vuelve a cubrir el mismo rango). Hoy `date_range` se upsertea (`sync.py:202`) **antes** del rebuild (`sync.py:213-226`) → invertir/condicionar ese orden.
6. **Documentación operacional.** Se documenta (en `pipeline/importers/README.md` o el README del pipeline de Sheets que aplique) el tamaño de ventana elegido, la env var que lo controla, el tradeoff de costo (cada corrida re-fetch ~13 meses, absorbido por el upsert idempotente), y que **el backfill manual deja de ser necesario como parche recurrente**.

## Tasks / Subtasks

- [x] **Task 1 — Ventana solapada en `get_date_range` (AC: 1)**
  - [x] `get_date_range` ahora acepta `today`/`overlap_months` (testeable sin monkeypatch de `now`) y calcula `date_from = min(watermark+1, hoy - overlap_months)`, `date_to = hoy`.
  - [x] Ventana por env `SYNC_OVERLAP_WINDOW_MONTHS` (default 13) vía `_overlap_window_months()` con fallback robusto ante valor no numérico/negativo.
  - [x] Borde confirmado: con la ventana `date_from <= date_to` casi siempre → el fetch corre cada corrida (re-fetch del rango). Es lo deseado.
  - [x] 4 tests unitarios de `get_date_range` (watermark reciente → ventana; watermark viejo → watermark+1; date_to == hoy; env var controla ventana).

- [x] **Task 2 — No avanzar el watermark en corrida parcial (AC: 5)**
  - [x] El upsert de `date_range` se movió al final (paso 5), gateado por `if ledger_synced and rebuild_ok`. Solo avanza tras un rebuild exitoso.
  - [x] Si el rebuild lanza, la excepción propaga antes del paso 5 → `date_range` queda intacto (re-intentable). Cubierto por test.

- [x] **Task 3 — De-silenciar el fallo del rebuild (AC: 4)**
  - [x] El `except` global de `sync_api()` ahora **re-raisea** tras loguear → `_run_sync` lo captura y marca `job_status=failed`. (Verificado: ningún test llama al `sync_api()` real, así que el re-raise no rompe nada existente.)
  - [x] Chequeo de conteo implementado como **read-back real** post-write: re-lee `ledger_final` y `ledger` del sheet y compara; si difieren → `RuntimeError`. (Más significativo que el `len(enriched)==len(source)` que sería tautológico por la comprensión 1:1; ver Completion Notes.)
  - [x] El error llega a `_current_job["error"]` vía la cadena `sync_api raise → _run_sync except` (ya cubierta por `test_run_sync_sets_failed_state_on_sync_error` + `test_sync_status_reflects_failed_job_with_error`).

- [x] **Task 4 — Tests (AC: 2, 3, 4, 5)**
  - [x] **Regresión Bug #2 (AC3):** `test_sync_recovers_backdated_entry_within_window` — watermark en hoy + asiento backdateado 2 meses → aparece en `ledger`. (Con forward-only, `date_from=hoy+1 > hoy` se saltaba el fetch.)
  - [x] **Idempotencia (AC2):** `test_sync_idempotent_two_runs_same_ledger` — dos corridas → 2 filas, sin duplicar.
  - [x] **Rebuild falla → propaga (AC4):** `test_sync_api_raises_when_rebuild_fails_and_watermark_not_advanced`. La cadena a `job_status=failed` ya está cubierta por `test_run_sync_sets_failed_state_on_sync_error`; el gap que cerré es que `sync_api` ahora *sí* lanza.
  - [x] **Mismatch de conteo → fallo (AC4):** `test_sync_api_raises_on_ledger_final_count_mismatch` (rebuild parcial escribe una fila menos a `ledger_final`).
  - [x] **Watermark no avanza en fallo (AC5):** asserts en los dos tests de fallo (`date_range` sigue en el valor previo).
  - [x] Suite backend completa: **487 passed, 1 xfailed**, 1 failed pre-existente sin relación (ver Dev Notes). Cero regresiones nuevas.

- [x] **Task 5 — Documentación (AC: 6)**
  - [x] Env var + tamaño de ventana + tradeoff de costo + "reemplaza el backfill manual" documentados en `.env.example` (sección "Sync incremental — ventana solapada"). Racionalización técnica en el docstring de `get_date_range`. (No se creó README del pipeline Sheets: no existe uno y Epic 9.11 deprecará ese pipeline.)

## Dev Notes

### Arquitectura del flujo (estado actual — leído, no asumido)

- **Trigger:** `POST /sync/trigger` → `trigger_sync` (`backend/app/api/v1/sync/service.py:92`) lanza un thread daemon → `_run_sync` (`:158`). Si `USE_BEANCOUNT_ENGINE_LEDGER=true`, `_run_sync` despacha al importer Beancount (`_run_laudus_import`) y **NO** toca el path de Sheets — esta story es **solo el path legacy de Sheets** (flag off). Confirmar que los cambios viven detrás de ese camino y no afectan el path c4.
- **`_run_sync` (`:163-203`):** snapshot de conteos antes/después, llama `sync_api()`, y en el `except` marca `status=failed`, `error=str(exc)`. **Hoy `sync_api()` nunca lanza** (try/except global propio en `sync.py:76-251`), así que este `except` jamás se activa por un fallo de rebuild. Ese es el agujero de AC4.
- **`sync_api()` (`pipeline/sync.py:72`):** orden actual de operaciones:
  1. Balance sheet (`:91-143`) — fuera de alcance de esta story salvo que comparta el swallow.
  2. Ledger incremental (`:145-208`): lee `date_range.dateTo` → `get_date_range` → `fetch_ledger` → `upsert_to_sheet("ledger", pk=journalentryid_lineid)` → **upsert `date_range` (`:202`)**.
  3. Rebuild `ledger_final` (`:210-226`): `enrich_ledger_row` sobre `merged_ledger` (o re-lee `ledger` si no hubo datos nuevos) → `replace_sheet("ledger_final", ...)`.
  4. Copia a hojas por entidad `ledger_{entity}` (`:228-246`).
  - **El orden 2→3 es el bug de AC5:** `date_range` (paso 2) avanza antes del rebuild (paso 3). Hay que condicionar el avance al éxito del rebuild.

### Punto de cambio AC1 — `get_date_range`

Firma actual (`pipeline/utils/dates.py:5-13`): `get_date_range(date_str) -> (date_from, date_to)` con `date_from = last_date + 1 día`. El cambio: `date_from = min(last_date + 1 día, inicio_ventana)`, donde `inicio_ventana = hoy - SYNC_OVERLAP_WINDOW_MONTHS` (usar `relativedelta(months=...)`, ya importado). El `min` garantiza que si el watermark va **atrasado** respecto a la ventana, no se pierda histórico (se sigue pidiendo desde `dateTo+1`); si va **adelantado** (caso normal), se retrocede al inicio de ventana para recuperar backdated.

### Punto de cambio AC4 — invariante de conteo `ledger` vs `ledger_final`

`enrich_ledger_row` (`pipeline/models.py:144-165`) es un map **1:1**: cada fila de `ledger` produce exactamente una fila de `ledger_final` (no agrupa, no filtra). `get_all_records()` de gspread descarta filas totalmente vacías en ambas hojas por igual. Por lo tanto, con un rebuild exitoso, **`len(ledger_final) == len(ledger)` exacto**. El brief menciona un posible "colapso conocido de Saldo anterior journalEntryId=0" como hedge — **el código actual no muestra tal colapso**; el dev debe confirmarlo empíricamente y, solo si aparece una reducción real (p.ej. filtrado de filas), documentar la tolerancia exacta. Por defecto: comparación de igualdad estricta.

### Restricciones críticas (no romper)

- **Solo path Sheets (flag `USE_BEANCOUNT_ENGINE_LEDGER` off).** No tocar `_run_laudus_import` ni el importer c4.
- **No cambiar la clave de dedup** `journalentryid_lineid` — es la garantía de idempotencia (AC2) y ya está validada.
- **`safe_write`/`replace_sheet` ya protegen contra pérdida por clear()+update fallido** (`pipeline/utils/gspread_utils.py:15-30`). No reimplementar ese restore; apoyarse en él.
- **Side finding documentado (no resolver aquí salvo que estorbe):** `accountNumberFrom = min(account_numbers)` como **string** (`sync.py:179`) es frágil con códigos de distinto largo. Fuera de alcance; mencionar si se topa con ello.
- El **fix `_eomonth`** (ISO "T") ya está aplicado y deployado — **no** re-tocarlo. Está fuera de alcance.

### Costo / tradeoff (AC6)

Re-fetch de ~13 meses en cada corrida aumenta el volumen pedido a Laudus y el tamaño del upsert, pero el `upsert_to_sheet` es idempotente y carga todo en memoria una sola vez. El sync corre semanal/on-demand, no en caliente — el costo es aceptable y elimina el backfill manual recurrente. Documentar este razonamiento.

### Fuera de alcance

- Migración al motor Beancount (Epic 9) — esto es el pipeline legacy de Sheets.
- Deltas por reclasificación manual del contador (divergencia esperada app-ERP vs planilla del contador; ver investigación, "Residual esperado").
- El fix `_eomonth` (ya deployado) y los 3 códigos de `template_order.json` lado INGRESOS (Bug #3, ya deployado).
- Cursor por `modifiedAt`: **no es viable** — `/accounting/ledger` no expone timestamp de creación (solo `date`, editable); se probó y `/journalEntries` da 404. Por eso la solución es ventana solapada, no cambio de cursor.

### Project Structure Notes

- Cambios concentrados en `pipeline/` (`utils/dates.py`, `sync.py`) + posible ajuste en `backend/app/api/v1/sync/service.py` (`_run_sync`) para que el fallo del rebuild marque el job. Tests en `backend/tests/test_sync.py` (ya existe, con factories `make_sync_test_app`/`make_mock_repo`/`reset_job_state` reutilizables). Sin cambios de routing, schema ni frontend. Nueva env var documentada en `.env.example` (sección "Google Sheets (existing pipeline)").

### Testing standards

- Framework: `pytest` + `unittest.mock` + FastAPI `TestClient`. Patrones ya establecidos en `backend/tests/test_sync.py`: mock del repo por nombre de hoja, `patch("pipeline.sync.sync_api")` / `patch("backend.app.api.v1.sync.service._run_sync")`, `reset_job_state()` entre tests que tocan `_current_job`.
- **Rojo pre-existente conocido (NO introducido por esta story):** `test_sync.py::test_run_backfill_calls_upsert_for_both_sheets` figura rojo date-dependiente en el entorno local desde antes (ver Story 10.2 Debug Log). No confundir con regresión.

### References

- [Source: _bmad-output/implementation-artifacts/story-brief-sync-incremental-robusto.md] — brief origen (AC + puntos de cambio).
- [Source: _bmad-output/implementation-artifacts/investigations/reporte-egresos-datos-incompletos-investigation.md#Follow-up:-2026-06-15] — diagnóstico de los dos bugs, medición del under-fetch, backfill ejecutado.
- [Source: pipeline/utils/dates.py#L5-L13] — `get_date_range` (cambio AC1).
- [Source: pipeline/sync.py#L145-L226] — ledger incremental + rebuild `ledger_final` + orden date_range/rebuild (cambios AC4/AC5).
- [Source: pipeline/sync.py#L250] — `except` global que se traga el error (AC4).
- [Source: pipeline/utils/gspread_utils.py#L33-L112] — `upsert_to_sheet` (idempotencia AC2) + `replace_sheet`/`safe_write`.
- [Source: pipeline/models.py#L144-L165] — `enrich_ledger_row` 1:1 (invariante de conteo AC4).
- [Source: backend/app/api/v1/sync/service.py#L158-L203] — `_run_sync` (donde el fallo del rebuild debe marcar el job).
- [Source: backend/tests/test_sync.py] — patrones de test + rojo pre-existente.
- [Source: _bmad-output/implementation-artifacts/sprint-status.yaml] — epic-2 (reapertura, Story 2.4).
- [Source: _bmad-output/implementation-artifacts/2-2-*.md] — Story 2.2 (linaje técnico: incremental-sync-deduplicación-y-confiabilidad).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Amelia / dev-story)

### Debug Log References

- `pytest backend/tests/test_sync.py -q` → 46 passed, 1 failed (pre-existente). Los 9 tests nuevos de 2.4 verdes.
- Suite completa (venv): `pytest backend/tests -q --ignore=backend/tests/test_fava_edit_validator.py` → **487 passed, 1 xfailed, 1 failed**.
  - El failed = `test_run_backfill_calls_upsert_for_both_sheets`, date-dependiente, ya rojo en el baseline pre-cambio (no relacionado: vive en `backfill.py`, esta story no lo toca).
  - `test_fava_edit_validator.py` se excluye de la colección por dep `fava` ausente en el venv local (misma limitación documentada en Story 10.2). No tocada por esta story.

### Completion Notes List

- **Bug #2 (under-fetch) cerrado durablemente:** `get_date_range` ahora re-pide una **ventana solapada hacia atrás** (`min(watermark+1, hoy - SYNC_OVERLAP_WINDOW_MONTHS)`, default 13 meses). Un asiento posteado-tarde/backdateado dentro de la ventana se recupera en la corrida siguiente — el backfill manual deja de ser necesario como parche recurrente.
- **El fallo del rebuild deja de ser silencioso:** el `except` global de `sync_api()` ahora **re-raisea** tras loguear, de modo que `_run_sync` marca el job `failed` y el error se ve en `GET /sync/status`. (Ningún test ejercitaba el `sync_api()` real, así que el re-raise no introduce regresiones.)
- **Watermark transaccional (AC5):** el upsert de `date_range` se movió al final y se gatea con `ledger_synced and rebuild_ok`. Una corrida que falla a medias deja `date_range` intacto → re-intentable. El orden previo (avanzar antes del rebuild) era la raíz de que el watermark se adelantara sobre un `ledger_final` congelado.
- **Decisión sobre el chequeo de conteo (AC4):** el brief pedía comparar `len(ledger_final)` vs `len(ledger)`. La comprensión `enrich_ledger_row` es **1:1**, así que `len(enriched)==len(source)` sería un chequeo tautológico (siempre verdadero). Lo implementé como **read-back real**: tras escribir, re-leo ambas hojas del spreadsheet y comparo — eso sí captura el síntoma real de la investigación (ledger_final que no aterrizó / quedó congelado mientras ledger creció). Cuesta 2 reads extra por corrida (sync es semanal/on-demand → despreciable). Confirmé que el "colapso de Saldo anterior journalEntryId=0" que el brief mencionaba como hedge **no existe** en el código → igualdad estricta.
- **Alcance respetado:** solo el path Sheets legacy (flag `USE_BEANCOUNT_ENGINE_LEDGER` off); no se tocó `_run_laudus_import` ni el importer c4. No se cambió la clave de dedup `journalentryid_lineid`. Side finding `accountNumberFrom = min(...)` como string (`sync.py:179`) sigue presente, fuera de alcance (no estorbó).

### File List

- `pipeline/utils/dates.py` (modificado — `get_date_range` ventana solapada + `_overlap_window_months` + `DEFAULT_OVERLAP_WINDOW_MONTHS`, import `os`)
- `pipeline/sync.py` (modificado — rebuild gatea el avance del watermark, read-back de conteo, `except` global re-raisea)
- `backend/tests/test_sync.py` (modificado — sección Story 2.4: `_FakeSpreadsheet`/`_FakeWorksheet` + 9 tests)
- `.env.example` (modificado — `SYNC_OVERLAP_WINDOW_MONTHS` documentada)

## Change Log

- 2026-06-15 — Story 2.4 implementada (Amelia / dev-story). Fix durable del under-fetch del sync incremental: ventana solapada hacia atrás en `get_date_range` (env `SYNC_OVERLAP_WINDOW_MONTHS`, default 13) + rebuild de `ledger_final` que ya no falla en silencio (re-raise → job `failed`, read-back de conteo) + watermark que solo avanza tras corrida completa exitosa. 9 tests nuevos en `test_sync.py` (fake spreadsheet en memoria). 487 passed / 1 xfailed / 1 failed pre-existente sin relación. Reapertura de Epic 2. Status → review.
