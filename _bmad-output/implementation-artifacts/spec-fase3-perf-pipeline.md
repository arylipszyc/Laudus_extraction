---
title: 'Fase 3 batch 1 — Performance del pipeline de reconciliación (D3/D4/D5)'
type: 'refactor'
created: '2026-07-06'
status: 'done'
baseline_commit: 'e319872'
context:
  - '{project-root}/_bmad-output/planning-artifacts/review-estabilidad-performance-2026-07-06.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Cada confirm/reconciliación de cartola desperdicia CPU e I/O: parsea los ~68 archivos mensuales de Laudus para usar un período (D4), el sync incremental los parsea DOS veces (D4b), el matcher recalcula `SequenceMatcher.ratio()` 2-3 veces por par re-normalizando strings en cada llamada (D3), y el dedup de discrepancias relee y re-parsea el JSONL completo por CADA discrepancia del loop (D5, cuadrático y crece cada mes).

**Approach:** Eliminar el trabajo redundante sin cambiar NINGÚN resultado: filtrar por nombre de archivo antes de parsear, parsear una sola vez bajo el lock, computar la similitud una vez por par, y leer las claves de dedup una vez por corrida. Refactor de performance puro.

## Boundaries & Constraints

**Always:** resultados bit-idénticos a hoy (mismos matches, mismos estados, mismo orden de desempate del matcher, mismo dedup); suite completa verde, 0 regresiones; el parse de JEs existentes ocurre DENTRO del lock (hoy `_incremental_from_date` parsea fuera — corregir el TOCTOU al unificar).

**Ask First:** cualquier cambio observable en resultados de matching o en el formato del JSONL; tocar la semántica del padding ±3d de 6.5b.

**Never:** cambiar el algoritmo greedy ni las tolerancias del matcher; compactar/reescribir el JSONL (sigue append-only); optimizaciones de otros hallazgos (D6 batch-resolve, D7 cuadre TC, jobs 202); tocar frontend.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Reconciliación de un mes | 68 archivos `YYYY-MM.beancount`, período abril | Solo se parsean los meses que intersectan `[start−3d, end+3d]` (típicamente 1-2 archivos); mismos LaudusEntry que hoy | — |
| Período cruza mes (padding) | período 2026-04-01..30, padding alcanza 2026-03-29 | Se parsean 2026-03 Y 2026-04 | — |
| Archivo con nombre no-`YYYY-MM` | `laudus.beancount` (fixture) en el dir | Se parsea igual (fallback conservador: solo se filtran stems que matchean `^\d{4}-\d{2}$`) | — |
| Sync incremental | JEs previos en disco | UN solo `_parse_existing_jes`, dentro del lock; `from_date` y el merge de `write_jes` salen del mismo dict | — |
| Matcher con N líneas × M entries | descripciones repetidas | `ratio()` se computa ≤1 vez por par (strings normalizados una vez por línea/entry); si hay candidatos con monto exacto, la similitud de los demás candidatos ni se computa (el score de un amount-match ≥97 > máx 10 de un no-match) | — |
| 100 discrepancias contra JSONL de 10k líneas | loop de `reconcile_cartola` | UNA lectura del JSONL (set de keys), un append bufferizado con las nuevas; `new` cuenta igual que hoy; re-corrida no duplica | — |
| Otro caller de `append_discrepancy` | API pública existente | Sigue funcionando (se mantiene; el batch usa una función nueva `append_discrepancies`) | — |

</frozen-after-approval>

## Code Map

- `pipeline/importers/matching_engine.py:60-96` — `load_laudus_entries`: filtrar `target_dir.glob` por stem `YYYY-MM` dentro de `[month(start), month(end)]` antes de `parser.parse_file` (D4a; sirve a reconcile.py:416 y tc_correction.py:589)
- `pipeline/importers/matching_engine.py:99-176` — `_similarity/_acceptable/_score/_classify/match`: normalizar descripciones una vez, memoizar sim por par, rankear primero el subset amount-match (D3). `match()` mantiene contrato público; los helpers privados pueden cambiar de firma (verificar usos en `backend/tests/test_matching_engine.py`, 11 tests)
- `pipeline/importers/laudus_run.py:199-212,269-300` — mover el cómputo de `from_date` incremental DENTRO del lock, parsear existing_jes UNA vez y pasarlos a `write_jes` (D4b + fix TOCTOU); `result["from_date"]` se completa al computarlo
- `pipeline/writers/beancount_writer.py:216-244` — `write_jes(..., existing_jes: dict | None = None)`: si viene, no re-parsea (backfill sigue `{}`)
- `pipeline/importers/discrepancy_writer.py:58-93` — nueva `append_discrepancies(list, path) -> int`: lee `_existing_dedup_keys` UNA vez, dedup también intra-batch, un solo write append; `append_discrepancy` queda (API pública)
- `pipeline/importers/reconcile.py:442-445` — usar `append_discrepancies` en vez del loop
- Tests: `backend/tests/test_matching_engine.py`, `test_beancount_writer.py`, `test_reconcile_cartola.py`, `test_laudus_run.py`, `test_tc_correction.py` (suites que fijan el comportamiento actual)

## Tasks & Acceptance

**Execution:**
- [x] `pipeline/importers/matching_engine.py` — filtro por filename en `load_laudus_entries` (stems `YYYY-MM` fuera del rango de meses del período → skip; stems no conformes → parse) + test: archivo de mes lejano con contenido INVÁLIDO no rompe (prueba que no se parseó) y uno adyacente sí entra
- [x] `pipeline/importers/matching_engine.py` — sim memoizada por par + normalización única + ranking en subset amount-match; los 11 tests existentes deben pasar SIN cambios + test nuevo: contador de llamadas a `SequenceMatcher` (monkeypatch) ≤ 1 por par
- [x] `pipeline/writers/beancount_writer.py` + `pipeline/importers/laudus_run.py` — parse único de existing JEs dentro del lock, threading a `write_jes`; test: `_parse_existing_jes` se llama exactamente 1 vez en un run incremental (monkeypatch contador) y `from_date` no cambia vs hoy
- [x] `pipeline/importers/discrepancy_writer.py` + `pipeline/importers/reconcile.py` — `append_discrepancies` batch (una lectura, dedup intra-batch + vs disco, un write) + tests: mismo `new` que el loop actual, re-corrida no duplica, lectura del archivo 1 vez (monkeypatch `_existing_dedup_keys`)

**Acceptance Criteria:**
- Given un ledger con 68 meses y una cartola de abril, when se reconcilia, then solo se parsean los archivos de los meses que intersectan el período padeado y el resultado del matching es idéntico al actual
- Given un run incremental, when importa, then los JEs existentes se parsean UNA vez, dentro del lock, y el archivo resultante es bit-idéntico al de hoy
- Given una corrida con K discrepancias y un JSONL de N líneas, when se persisten, then el archivo se lee una sola vez y el dedup (incluida la re-corrida del mismo batch) se comporta igual que hoy
- Suite backend completa verde (672+ passed), 0 regresiones

## Design Notes

Desviaciones aceptadas del "bit-idéntico" (todas metadata/edge, adjudicadas en el review de 3 capas 2026-07-06 — Auditor PASS en todos los AC):

- **`from_date: null` en el import-log en paths de fallo** (LockTimeout / parse roto): inherente a mover el parse dentro del lock (lo que el spec exige). Único consumidor (`/sync/status`) lee solo `timestamp`. Bonus: un parse roto ahora deja registro `success=false` en vez de propagar sin log.
- **Tx manualmente movida al archivo de otro mes queda invisible al matcher**: el filtro por filename ES el comportamiento que el spec congela (I/O row 1); `write_jes` garantiza el bucketing por mes para todo lo generado. Documentado en el comentario de `load_laudus_entries`.
- **El atajo del ranking exige `100 − DATE_TOLERANCE_DAYS > 10`**: pineado con un `assert` a nivel de módulo (falla el import si alguien agranda la tolerancia hacia ≥90).
- El test de D4a usa una tx VÁLIDA en-período plantada en un mes lejano (más fuerte que el "contenido inválido" del task: el parser de beancount no lanza con contenido inválido, así que esa versión era casi vacua).

## Verification

**Commands:**
- `python -m pytest backend/tests -q` — expected: verde, 0 regresiones
- `python -m pytest backend/tests/test_matching_engine.py backend/tests/test_reconcile_cartola.py backend/tests/test_beancount_writer.py -q` — expected: los tests que fijan comportamiento actual pasan sin modificar sus asserts

**Resultado final (2026-07-06):** backend **678 passed / 1 xfailed** (0 regresiones; +6 tests nuevos vs baseline). Review 3 capas: Auditor **PASS** en AC1-AC3 y todas las boundaries (equivalencia del ranking verificada como SOUND; Edge Hunter verificó USD, cruce de año, callers de helpers eliminados y colisión posicional — todo limpio). 10 patches aplicados post-review (bono +100 restaurado para aritmética float bit-idéntica, guard de batch vacío, assert del bound de tolerancia, `_similarity` muerto eliminado, contador exacto + ganadores en el test del matcher, test de cruce de año, write línea-por-línea, regex ASCII precompilada, docstring del contrato de lock, fix assert truthiness). 2 defer nuevos en deferred-work.md, resto dismiss.

## Suggested Review Order

**D4a — filtro por filename (el mayor ahorro por reconciliación)**

- Entry point: filtro por stem `YYYY-MM` + comentario del invariante del writer
  [`matching_engine.py:76`](../../pipeline/importers/matching_engine.py#L76)

- Tests: mes lejano no se parsea (tx "COLADA" invisible), cruce de año, stem no conforme
  [`test_matching_engine.py:110`](../../backend/tests/test_matching_engine.py#L110)

**D3 — matcher sin similitudes redundantes**

- match() reestructurado: norm única, memo por par, subset amount-match, bono +100 restaurado (patch del review: aritmética float bit-idéntica)
  [`matching_engine.py:150`](../../pipeline/importers/matching_engine.py#L150)

- Guard del atajo: `assert 100 − DATE_TOLERANCE_DAYS > 10` a nivel módulo
  [`matching_engine.py:20`](../../pipeline/importers/matching_engine.py#L20)

- Test: exactamente 3 corridas de SequenceMatcher + ganadores por línea asserted
  [`test_matching_engine.py:159`](../../backend/tests/test_matching_engine.py#L159)

**D4b — parse único dentro del lock**

- from_date incremental computado bajo el lock, dict threaded a write_jes (fix TOCTOU incluido)
  [`laudus_run.py:293`](../../pipeline/importers/laudus_run.py#L293)

- write_jes acepta existing_jes (backfill sigue `{}`)
  [`beancount_writer.py:216`](../../pipeline/writers/beancount_writer.py#L216)

**D5 — dedup batch de discrepancias**

- append_discrepancies: una lectura, dedup intra-batch, guard de batch vacío, contrato de lock documentado
  [`discrepancy_writer.py:98`](../../pipeline/importers/discrepancy_writer.py#L98)

- reconcile.py usa el batch
  [`reconcile.py:442`](../../pipeline/importers/reconcile.py#L442)

**Periféricos**

- Tests D4b/D5 (contadores por monkeypatch)
  [`test_laudus_run.py:411`](../../backend/tests/test_laudus_run.py#L411)

- Defers del review (2, pre-existentes/paridad)
  [`deferred-work.md:3`](deferred-work.md#L3)
