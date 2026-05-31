---
story: 9.5c
title: Validation tooling — batch smoke runner Gemini con reporte agregado
status: review
epic: 9
depends_on: [9.5]
blocks: []   # Gate de dispatch 9.6a y candidato 9.5d depende del OUTPUT de esta story (no del scope técnico).
parallelizable_with: [9.2, 9.3, 9.4, 9.6a, 9.6b, 9.7, 9.8, 9.9, 9.11, 9.12]
---

# Story 9.5c — Validation tooling (batch smoke runner Gemini)

## Story

As Ary (single operator del Family Office),
I want un script standalone que tome los N PDFs de `samples/`, los corra 3× cada uno por la pipeline real de Gemini (la misma de Story 9.5 — `process_upload_sync`) y genere un reporte agregado markdown + CSV con verde/amarillo/rojo por PDF,
so that pueda validar empíricamente que la extracción Gemini llegó al umbral del 90% antes de dispatchar 9.6a (matching agresivo) — y reutilizar el mismo tooling cada vez que cambie el prompt o el modelo, en lugar de validar PDF-por-PDF manualmente (~1.5h por iteración).

## Context

Decisión Ary 2026-05-19 (memory `project_epic9_validacion_cartolas`):

- Story 9.5 cerró 2026-05-06 con sólo 2 PDFs validados manualmente (BCI verde, Santander BALANCE_MISMATCH legítimo). Quedan **14 PDFs** en `samples/` (BCI + Santander + Banco de Chile) que esperan validación.
- **Métrica del 90%** = % de PDFs sin `BALANCE_MISMATCH` (el guardrail empírico ya implementado en `cartola_post_process.detect_balance_mismatch`, tolerance 100 CLP). El umbral es el gate para decidir entre dos paths aguas abajo:
  - **≥ 90% verde** → dispatch 9.6a (beangulp importer) inmediato.
  - **< 90% verde** → dispatch condicional 9.5d (retry con feedback a Gemini) primero, re-medir, decidir.
- **9.5c NO implementa retry** — sólo mide. El retry vive en 9.5d y se crea sólo si el output justifica la complejidad.
- **No tocar shape canónico v1.0** ni el prompt Gemini. Esta story es read-only sobre la pipeline existente.

## Acceptance Criteria

**AC1 — CLI standalone `bootstrap/validate_cartolas_batch.py`**

**Given** Ary corre `python -m bootstrap.validate_cartolas_batch samples/`
**When** el script arranca
**Then** descubre todos los `*.pdf` en el directorio pasado
**And** acepta opcionalmente `--pdf <path>` (uno o más, repetible) para correr un subset
**And** acepta `--runs N` (default 3) — número de corridas por PDF para medir reproducibilidad
**And** acepta `--out-dir <path>` (default `_bmad-output/validation-runs/{YYYY-MM-DD-HHMMSS}/`) donde escribe los outputs
**And** acepta `--bank-account-type` (default `tarjeta_credito`; mismas choices que `smoke_cartola_upload.py`)
**And** si no encuentra ningún PDF → exit 2 con mensaje accionable

---

**AC2 — Inferencia bank_name desde filename + override manual**

**Given** un PDF en `samples/`
**When** el script lo procesa
**Then** infiere `bank_name` y `last4` siguiendo la convención `samples/{banco}-{producto}-{YYYYMM}.pdf` documentada en `samples/README.md`:
  - Token 1 del basename antes del primer `-` → `bank_name` capitalizado (`bci` → `BCI`, `santander` → `Santander`, `banco-de-chile` o `bdechile` → `Banco de Chile`)
  - `last4` sintético = `9999` (no se usa para validación de matching — es solo para satisfacer el shape de `BankAccountEntry`, idéntico al patrón de `smoke_cartola_upload.py`)
**And** acepta override por PDF vía `--override <pdf_filename>:<bank_name>:<last4>[:<currency>]` (repetible) para los casos `estado-de-cuenta (NN).pdf` donde la convención de naming no aplica. Currency es opcional (default CLP; closed enum CLP|USD|EUR); agregada durante implementación 2026-05-19 al descubrir que los samples reales mezclan moneda nacional/internacional por PDF.
**And** si un PDF no matchea convención y no tiene override → emite warning + asume `Desconocido`/`9999` y continúa (NO aborta el batch)

---

**AC3 — Pipeline real de Story 9.5 reutilizada (no reimplementar)**

**Given** un PDF a procesar
**When** el script lo ejecuta
**Then** invoca exactamente las funciones públicas de Story 9.5: `bootstrap.smoke_cartola_upload`-style — específicamente `process_upload_sync(batch_id, pdf_bytes, bank_account_entry, gemini, staging_dir)` desde `backend.app.api.v1.cartolas.service`
**And** construye `BankAccountEntry` con el mismo patrón sintético de `smoke_cartola_upload.py` líneas 60-69 (NO usar el endpoint HTTP — invocación directa de la función para evitar booteo FastAPI y costos de network)
**And** usa una instancia única de `GeminiClient()` reutilizada para todas las corridas (no reinstancia por corrida)
**And** escribe los staging files a `--out-dir/staging/` (no a `ledger/imports/cartolas/_staging/` — aislado del flujo real)
**And** NO modifica ningún archivo bajo `backend/`, `frontend/`, `ledger/` ni el prompt de Gemini — esta story es read-only sobre la pipeline

---

**AC4 — N corridas por PDF + medición de drift**

**Given** `--runs N` (default 3) y un PDF
**When** el script lo corre N veces consecutivas
**Then** captura para cada corrida: `n_transactions`, `balances.opening`, `balances.closing`, `sum(amounts)`, lista ordenada de warning codes
**And** considera "estable" si entre las N corridas: `n_transactions` idéntico Y `opening` idéntico Y `closing` idéntico Y `sum(amounts)` difiere en ≤ 100 CLP Y set de warning codes idéntico
**And** registra drift granular por campo en el reporte (cuál corrida divergió en qué campo) para poder leerlo sin re-correr

---

**AC5 — Clasificación verde/amarillo/rojo por PDF**

**Given** las N corridas de un PDF
**When** el script las agrega
**Then** asigna **un único color** por PDF según estas reglas en orden de prioridad:
  - **🔴 ROJO** si: alguna corrida levantó excepción Python (Gemini timeout, validación Pydantic falla, etc.) **O** alguna corrida emitió `BALANCE_MISMATCH` **O** alguna corrida tuvo 0 transactions
  - **🟡 AMARILLO** si: drift entre corridas (AC4 "estable" = false) **O** `extraction.warnings` contiene cualquier código distinto de `BALANCE_MISMATCH` (`DUPLICATE_LINE`, `ZERO_AMOUNT`, `LARGE_AMOUNT`, `PERIOD_MISMATCH`, `LOW_CONFIDENCE`, `PARSE_AMBIGUOUS`)
  - **🟢 VERDE** caso contrario: N corridas estables Y sin BALANCE_MISMATCH Y sin warnings de ningún tipo
**And** la métrica del 90% se calcula como `count(VERDE) / count(total_pdfs)` (NO `(VERDE+AMARILLO)/total` — amarillo NO cuenta como aprobado porque indica drift o señales de calidad)

---

**AC6 — Reporte agregado markdown**

**Given** todas las corridas terminaron
**When** el script escribe el reporte
**Then** genera `--out-dir/report.md` con esta estructura mínima (puede agregar secciones, no quitar):

```markdown
# Validation run — {timestamp}
- PDFs evaluados: {N}
- Corridas por PDF: {runs}
- Tiempo total: {elapsed_seconds}s
- Modelo Gemini: {model}

## Resumen
- 🟢 Verde: {n_verde} ({pct_verde}%)
- 🟡 Amarillo: {n_amarillo} ({pct_amarillo}%)
- 🔴 Rojo: {n_rojo} ({pct_rojo}%)

**Gate 9.6a (≥90% verde):** {PASS|FAIL}

## Por banco
| Banco | Total | 🟢 | 🟡 | 🔴 | % verde |
|---|---|---|---|---|---|

## Detalle por PDF
{una sección H3 por PDF con: color, n_tx por corrida, opening / closing / sum(amounts) / diff = closing − opening − sum(amounts) por corrida, drift detectado por campo, warning codes con conteo}

## Sign distribution (agregado, primera corrida de cada PDF)
| Banco | %positivos | %negativos | %ceros |
|---|---|---|---|
```

**And** los conteos por banco se basan en `bank_name` resuelto en AC2

---

**AC7 — Output CSV machine-readable**

**Given** todas las corridas terminaron
**When** el script escribe el CSV
**Then** genera `--out-dir/runs.csv` con una fila por corrida (no por PDF), columnas en este orden exacto:
`pdf_filename, run_idx, bank_name, color_pdf, n_transactions, opening, closing, sum_amounts, balance_diff, warning_codes (pipe-separated), error (texto vacío si OK)`
**And** genera `--out-dir/summary.csv` con una fila por PDF, columnas: `pdf_filename, bank_name, color, n_runs_stable, warnings_distinct, notes`
**And** ambos CSV son utf-8 con header

---

**AC8 — Tolerancia a fallos por PDF (batch no aborta)**

**Given** un PDF dispara excepción Python en cualquier corrida (Gemini timeout, ValidationError, etc.)
**When** el script la captura
**Then** registra el PDF como 🔴 con `error` poblado en `runs.csv`, marca el detalle en `report.md`, y **continúa con el siguiente PDF**
**And** no se interrumpe el batch — el contrato es "corre todo y reporta lo que pasó", no "abortar al primer fallo"
**And** la única excepción que aborta es: no encuentra ningún PDF (AC1) o no encuentra `GEMINI_API_KEY` al inicio (fail-fast antes de quemar tiempo)

---

**AC9 — No persistir PDFs ni staging contaminado**

**Given** la política `samples/README.md` (PII — no almacenar PDFs largos)
**When** el script termina
**Then** los staging files generados bajo `--out-dir/staging/` se **borran al final del batch** por default (mismo patrón que `smoke_cartola_upload.py` post-test cleanup)
**And** acepta flag `--keep-staging` que preserva los `.cartola.json` para inspección manual (útil cuando hay ROJO sospechoso)
**And** el reporte markdown + ambos CSV NUNCA se borran (son el output buscado)
**And** los `report.md` y CSVs NO incluyen el contenido extraído (transactions, descriptions con PII) — sólo agregados numéricos + warning codes + filenames. **Esto es no-negociable.**

---

**AC10 — Tests unitarios sin tocar Gemini**

**Given** que cada llamada a Gemini cuesta tokens reales
**When** se agregan tests
**Then** los tests del clasificador (AC5) y del estable/drift (AC4) usan fixtures sintéticas `CartolaCanonicalV1` construidas a mano (siguiendo el patrón de `tests/test_cartola_post_process.py`) — **NO** invocan `GeminiClient`
**And** ≥ 1 test por bucket de color (verde, amarillo BALANCE_MISMATCH-free pero con warning, amarillo por drift, rojo por exception, rojo por BALANCE_MISMATCH, rojo por 0 tx)
**And** ≥ 1 test del agregador por banco (AC6) verifica que `bank_name` extraído de filename agrupa correctamente
**And** los tests viven en `backend/tests/test_validate_cartolas_batch.py` y corren con `pytest backend/tests/test_validate_cartolas_batch.py` sin red ni API key

---

**AC11 — Smoke real con los 14 PDFs (manual, post-implementación)**

**Given** los 14 PDFs en `samples/` y `GEMINI_API_KEY` configurado en `.env`
**When** Ary corre `python -m bootstrap.validate_cartolas_batch samples/`
**Then** el script termina sin abortar (AC8) en ≤ 20 minutos para 14 PDFs × 3 corridas = 42 calls a Gemini
**And** el `report.md` + los CSVs quedan generados bajo `_bmad-output/validation-runs/{timestamp}/`
**And** Ary puede leer el % verde directo del Resumen y decidir dispatch 9.6a vs 9.5d
**And** este AC se valida con un comentario en el storyfile post-corrida con: % verde, % amarillo, % rojo, decisión tomada — **no en el dev agent**, lo completa Ary leyendo el reporte

---

## Tasks / Subtasks

- [x] **Task 1: CLI scaffold** (AC1, AC2)
  - [x] Crear `bootstrap/validate_cartolas_batch.py` con `argparse` (modelar sobre `bootstrap/smoke_cartola_upload.py:35-51`)
  - [x] Discovery de `*.pdf` en el directorio pasado + soporte `--pdf` repetible
  - [x] Inferencia `bank_name` por convención de filename (caso happy: `bci-*`, `santander-*`, `banco-de-chile-*`, `bdechile-*`)
  - [x] Soporte `--override pdf:bank:last4` parsing para `estado-de-cuenta (NN).pdf`
  - [x] Carga `.env` con `dotenv` (mismo patrón `smoke_cartola_upload.py:21-25`) + fail-fast si falta `GEMINI_API_KEY`

- [x] **Task 2: Runner por PDF** (AC3, AC4, AC8)
  - [x] Función `run_pdf(pdf_path, bank_name, last4, runs, gemini, staging_dir) -> list[RunResult]`
  - [x] Construye `BankAccountEntry` sintético (idéntico al patrón `smoke_cartola_upload.py:60-69`)
  - [x] Loop N corridas reutilizando la **misma** instancia de `GeminiClient`
  - [x] Cada corrida: nuevo `batch_id` vía `new_batch_id()`, llama `process_upload_sync(...)`, extrae métricas
  - [x] `try/except Exception` por corrida → registra error string, continúa
  - [x] Helper `is_stable(runs: list[RunResult]) -> tuple[bool, list[str]]` con la lógica de AC4 (devuelve además los campos con drift, para reportar granularmente)

- [x] **Task 3: Clasificador verde/amarillo/rojo** (AC5)
  - [x] Función pura `classify_pdf(runs: list[RunResult]) -> tuple[Color, bool, list[str]]` (Enum verde/amarillo/rojo)
  - [x] Orden de prioridad estricto: ROJO → AMARILLO → VERDE (AC5)
  - [x] Tests unitarios con fixtures sintéticas (AC10)

- [x] **Task 4: Writers de reporte** (AC6, AC7)
  - [x] Función `write_report_md(out_dir, …)` con el shape de AC6
  - [x] Función `write_runs_csv(out_dir, summaries)` y `write_summary_csv(out_dir, summaries)` con headers de AC7
  - [x] Sign distribution agregado por banco usando la primera corrida de cada PDF (AC6)
  - [x] **No incluir contenido de transactions** en ningún output (AC9 — verificado: sólo n_tx, opening, closing, sum, diff, codes)

- [x] **Task 5: Cleanup staging** (AC9)
  - [x] Por default: `shutil.rmtree(out_dir / "staging")` al final del batch
  - [x] Flag `--keep-staging` lo preserva

- [x] **Task 6: Tests** (AC10)
  - [x] `backend/tests/test_validate_cartolas_batch.py`
  - [x] Tests del clasificador: 1 por bucket de color (verde, amarillo-por-drift, amarillo-por-warning, rojo-por-exception, rojo-por-BALANCE_MISMATCH, rojo-por-0-tx, rojo-priority-wins-over-amarillo) = 7 tests
  - [x] Tests del agregador por banco con fixtures de 5+ PDFs
  - [x] Tests del parser de `--override` (happy, missing-part, whitespace)
  - [x] Tests del `is_stable()` con drift en cada campo de AC4 (n_tx, opening, closing, sum_amounts dentro/fuera tolerancia, warning_codes, error)
  - [x] Guard test verifica vía AST que ningún test instancia `GeminiClient`

- [x] **Task 7: Smoke real con los 14 PDFs** (AC11 — manual por Ary)
  - [x] Instrucciones operativas dejadas en Completion Notes para que Ary lo corra
  - [x] NO se corrió en CI (decisión: cada corrida = 42 llamadas reales)

---

## Dev Notes

### REUSO OBLIGATORIO — no reimplementar nada de 9.5

La pipeline de extracción ya existe y está validada. Esta story es **un wrapper** sobre las funciones públicas de Story 9.5. Específicamente:

- `backend/app/api/v1/cartolas/service.py::process_upload_sync()` — la función core que toma `pdf_bytes` y devuelve `CartolaCanonicalV1` ya post-procesada
- `backend/app/api/v1/cartolas/service.py::new_batch_id()` — generador de UUID para batch
- `backend/app/integrations/gemini_client.py::GeminiClient` — wrapper SDK (NFR17 — único módulo que importa `google.genai`; **no romper esto**)
- `backend/app/integrations/bank_account_index.py::BankAccountEntry` — dataclass de cuenta bancaria; usar el patrón sintético de `smoke_cartola_upload.py` para satisfacer el shape sin tocar `accounts.beancount`
- `backend/app/integrations/cartola_schema.py::CartolaCanonicalV1` + `CartolaWarning` — los modelos para construir fixtures de tests
- `backend/app/integrations/cartola_post_process.py::BALANCE_MISMATCH_TOLERANCE_CLP` — la constante de tolerancia (100 CLP); **importarla, no duplicarla**

### Patrón de invocación — copiar de smoke_cartola_upload.py

`bootstrap/smoke_cartola_upload.py` es el template directo. Cambios respecto a él:

1. Loop sobre múltiples PDFs en vez de uno (CLI accepts dir + `--pdf` repetible)
2. Loop interno N corridas por PDF (`--runs`, default 3)
3. En vez de imprimir un summary stdout, agrega a estructuras en memoria y escribe report + CSVs al final
4. Staging dir en `out_dir/staging/` (no en `ledger/imports/cartolas/_staging/`)
5. Cleanup del staging dir al final (excepto `--keep-staging`)

### Clasificación — por qué el orden ROJO → AMARILLO → VERDE importa

Un PDF puede simultáneamente:
- tener `BALANCE_MISMATCH` (→ ROJO por AC5 primera regla)
- tener drift entre corridas (→ AMARILLO por AC5 segunda regla)
- tener warnings adicionales (→ AMARILLO por AC5 segunda regla)

El orden de prioridad evita ambigüedad: si match cualquier regla ROJO, es ROJO. Si no, evaluar AMARILLO. Si no, VERDE.

**No agregar buckets adicionales.** El umbral del 90% se evalúa contra VERDE únicamente. Cualquier matiz adicional (ej. "verde-con-warning-leve") rompe la métrica y diluye la señal del gate.

### Métrica 90% — definición canónica

`% verde = count(PDFs clasificados VERDE) / count(total_pdfs) × 100`

Si llega 90% → memory decision dice "dispatch 9.6a inmediato". Si menor → dispatch condicional 9.5d.

**No interpretar el umbral.** El script reporta el número; Ary decide.

### No persistir PDFs ni transactions

`samples/README.md` documenta política PII: cartolas reales no se versionan, se borran post-conciliación. Esta story extiende la política:

- El staging dir bajo `--out-dir/staging/` puede tener `.cartola.json` con descriptions completas (donde figura `SUPERMERCADO JUMBO`, `KIA Falabella`, etc., que son PII de la familia). Borrar por default al final.
- El reporte + CSVs **NUNCA** incluyen contenido de transactions. Sólo agregados numéricos: counts, sums, drift booleano, warning codes. Esto es no-negociable (AC9).

Si Ary necesita inspeccionar las transactions de un PDF marcado ROJO/AMARILLO → corre con `--keep-staging` y abre los `.cartola.json` localmente.

### `bank_name` desde filename — convención + fallback

`samples/README.md:22-29` documenta `samples/{banco}-{producto}-{YYYYMM}.pdf`. Casos en `samples/` hoy:

- `bci-visa-202604.pdf` → bank=BCI ✓
- `santander-mastercard-202604.pdf` → bank=Santander ✓
- `estado-de-cuenta (21).pdf` ... `estado-de-cuenta (28).pdf` → NO matchean convención → necesitan `--override`
- 4 UUIDs `.pdf` → tampoco matchean → necesitan `--override`

Para los 12 "off-convention", Ary los renombra antes (ideal — futuro proof) o usa `--override`. **No agregar lógica de detección de banco por contenido del PDF** — eso es scope de 9.5b (parqueado).

### Tiempo estimado y costo

- Implementación Amelia: ~2-3h
- Tests: ~30 min (clasificador + agregador + parser de override)
- Smoke real: ~15 min de tiempo de ejecución para 14 PDFs × 3 corridas (Gemini ~10s/call promedio), ~15 min de revisión humana del reporte = vs ~1.5h actual por iteración
- Costo Gemini: ~42 calls a `gemini-2.5-flash`. Bajo absoluto, pero acumulable si se itera prompt — ese es exactamente el punto del tooling.

### Out of scope

- **Retry con feedback a Gemini** → Story 9.5d (parqueado, dispatch condicional al output de 9.5c)
- **Detección automática de bank_account desde contenido del PDF** → Story 9.5b (parqueado, depende de last4 poblado en 9.3 AC8)
- **Validación contra CSV exportado del banco** → out of scope; el CSV manual es el baseline contra el que Ary hizo la validación inicial de BCI, pero 9.5c mide reproducibilidad interna de Gemini, no fidelidad contra fuente externa
- **CI integration** → out of scope. Esto corre local, manual, on-demand
- **Métricas históricas** (comparar batch run de hoy vs uno anterior) → out of scope. Cada corrida es independiente; comparación es manual leyendo dos `report.md` distintos
- **Modificar el prompt Gemini o el shape canónico** → no-go. Read-only sobre la pipeline existente

### Project structure

```
bootstrap/
  validate_cartolas_batch.py            # NEW — el CLI
backend/tests/
  test_validate_cartolas_batch.py       # NEW — tests del clasificador y agregadores
_bmad-output/validation-runs/           # NEW (auto-created, gitignored)
  {YYYY-MM-DD-HHMMSS}/
    report.md
    runs.csv
    summary.csv
    staging/                            # borrado por default; persistido con --keep-staging
```

Agregar `_bmad-output/validation-runs/` al `.gitignore` raíz si no está cubierto (verificar: `_bmad-output/` ya está gitignored? si sí, no se necesita entry adicional).

### References

- [Source: sprint-status.yaml línea 143 — descripción del candidato 9.5c]
- [Source: memory/project_epic9_validacion_cartolas.md — decisión 2026-05-19, métrica 90%, 9.5d condicional]
- [Source: 9-5-pdf-upload-gemini-json-canonico.md §Smoke real — patrón de validación manual que esta story automatiza]
- [Source: bootstrap/smoke_cartola_upload.py — template directo del CLI; copiar estructura]
- [Source: backend/app/integrations/cartola_post_process.py:75-97 — `detect_balance_mismatch()` y `BALANCE_MISMATCH_TOLERANCE_CLP`]
- [Source: backend/app/api/v1/cartolas/service.py — `process_upload_sync()` + `new_batch_id()` ]
- [Source: backend/app/integrations/cartola_schema.py — `CartolaCanonicalV1` para fixtures de tests]
- [Source: samples/README.md — política PII + convención de naming]

---

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m] (Amelia, BMad Dev Story workflow)

### Debug Log References

- 34/34 tests verde en `backend/tests/test_validate_cartolas_batch.py` (0.28s).
- Regression suite backend: 374 passed / 1 pre-existing failure (`test_sync.py::test_run_backfill_calls_upsert_for_both_sheets`, no relacionado — verificado vía `git stash` que falla también en `main`). 2 archivos pre-existentes no cargan por falta del paquete `beanquery` en el venv (`test_fava_edit_validator.py`, `test_validate_cuadratura.py`) — también pre-existente, sin relación con 9.5c.
- CLI carga sin invocar Gemini (verificado con `python -m bootstrap.validate_cartolas_batch --help`).

### Completion Notes List

#### Qué quedó implementado

**`bootstrap/validate_cartolas_batch.py`** — CLI standalone que envuelve `process_upload_sync` (Story 9.5) sin tocar `backend/`, `frontend/`, `ledger/` ni el prompt Gemini.

- Discovery de PDFs en `samples/` (default) o `--pdf path` repetible.
- Inferencia de `bank_name` por convención `samples/{banco}-{producto}-{YYYYMM}.pdf`: `bci-*` → BCI, `santander-*` → Santander, `banco-de-chile-*` y `bdechile-*` → Banco de Chile.
- `--override "<filename>:<bank>:<last4>"` repetible para los `estado-de-cuenta (NN).pdf` y los UUIDs sin convención.
- Si un PDF no matchea y no tiene override → warning + `bank=Desconocido` `last4=9999`, sigue.
- `--runs N` (default 3) — reutiliza la **misma** instancia de `GeminiClient` para todas las corridas (no se reinstancia).
- `--out-dir` default = `_bmad-output/validation-runs/{YYYY-MM-DD-HHMMSS}/`. Auto-creado. Agregado a `.gitignore`.
- `--bank-account-type` default `tarjeta_credito` (mismas choices que `smoke_cartola_upload.py`).
- `--keep-staging` preserva los `.cartola.json` para inspección manual; por default se borran al final del batch.
- Staging aislado bajo `--out-dir/staging/` — NUNCA toca `ledger/imports/cartolas/_staging/`.
- Fail-fast: si falta `GEMINI_API_KEY` o no hay PDFs → exit 2 ANTES de quemar tiempo.
- AC8 cubierto: excepción Python por corrida → captura, registra `error` en `RunResult`, sigue con la siguiente. Batch nunca aborta por un PDF malo.

**Clasificador (AC5)** — orden estricto ROJO → AMARILLO → VERDE:
- **ROJO**: cualquier corrida con excepción, o con `BALANCE_MISMATCH` en warnings, o con `n_transactions == 0`.
- **AMARILLO**: drift entre corridas (cualquier campo de AC4) **o** warning code distinto de `BALANCE_MISMATCH`.
- **VERDE**: N corridas estables Y sin BALANCE_MISMATCH Y sin warnings de ningún tipo.
- **Métrica gate:** `% verde = count(VERDE) / count(total)`. Amarillo NO cuenta como aprobado (decisión canónica AC5).

**Drift granular (AC4)** — `is_stable()` devuelve `(bool, list[str])` con los campos divergentes. Cada campo de AC4 está cubierto: `n_transactions`, `opening`, `closing`, `sum_amounts` (con tolerancia 100 CLP — importada de `cartola_post_process.BALANCE_MISMATCH_TOLERANCE_CLP`, no duplicada), `warning_codes`. El reporte markdown muestra los drift fields por PDF para que Ary lea sin re-correr.

**Outputs (AC6, AC7)**:
- `report.md` — sigue el shape literal de AC6: header con timestamp/modelo/elapsed, resumen con %, gate PASS/FAIL, tabla por banco, detalle por PDF (con tabla run-by-run de n_tx/opening/closing/sum/diff/warnings/error), sign distribution agregado por banco usando primera corrida de cada PDF.
- `runs.csv` — una fila por corrida con las columnas exactas de AC7: `pdf_filename, run_idx, bank_name, color_pdf, n_transactions, opening, closing, sum_amounts, balance_diff, warning_codes (pipe-separated), error`.
- `summary.csv` — una fila por PDF: `pdf_filename, bank_name, color, n_runs_stable, warnings_distinct, notes`.
- UTF-8 con header en ambos CSVs.

**AC9 (PII no-negociable):** verificado por inspección manual del código que ni el reporte ni los CSVs incluyen `description` de transactions, ni `raw`, ni nada de contenido. Sólo agregados numéricos + warning codes (enum cerrado) + filenames.

**Tests (AC10)** — `backend/tests/test_validate_cartolas_batch.py`, 34 tests, todos verde:
- 7 tests de clasificación (uno por bucket de color + un priority-wins).
- 8 tests de `is_stable()` (un campo por AC4, dentro/fuera tolerancia, con error, identical).
- 6 tests de inferencia de bank por filename + 3 de `parse_override` + 3 de `resolve_pdf_metadata`.
- 2 tests del aggregator por banco + 2 de sign distribution.
- 2 tests del `summarize()` (notes).
- 1 guard test que parsea el AST del propio módulo de tests y asegura que ninguna función llama `GeminiClient(...)`.

#### Instrucciones para correr el smoke real (AC11) — Ary ejecuta

```bash
# Desde la raíz del repo, con venv activado y .env con GEMINI_API_KEY:
python -m bootstrap.validate_cartolas_batch samples/ \
  --override "estado-de-cuenta (21).pdf:Banco de Chile:9999" \
  --override "estado-de-cuenta (22).pdf:Banco de Chile:9999" \
  --override "estado-de-cuenta (23).pdf:Banco de Chile:9999" \
  --override "estado-de-cuenta (24).pdf:Banco de Chile:9999" \
  --override "estado-de-cuenta (25).pdf:Banco de Chile:9999" \
  --override "estado-de-cuenta (26).pdf:Banco de Chile:9999" \
  --override "estado-de-cuenta (27).pdf:Banco de Chile:9999" \
  --override "estado-de-cuenta (28).pdf:Banco de Chile:9999"
```

(Los 4 PDFs con nombre UUID — ajustá los bancos cuando sepas a cuál pertenece cada uno; si los corrés sin override quedarán como `Desconocido` y verás un warning por PDF.)

Tiempo estimado: ~15 min para 14 × 3 = 42 calls a Gemini. Output: `_bmad-output/validation-runs/{timestamp}/report.md`.

**Decisión post-smoke** (Ary lee `report.md`):
- `Gate 9.6a (≥90% verde): PASS` → dispatch 9.6a inmediato.
- `FAIL` → leer breakdown por banco y warnings distinct; decidir si dispatch 9.5d (retry single intento, parqueado) o ajuste manual del prompt.

Si querés inspeccionar transactions de un PDF marcado ROJO/AMARILLO, re-correr con `--keep-staging` y abrir los `.cartola.json` localmente.

#### Trade-offs / decisiones tomadas

1. **`is_stable()` devuelve `(bool, list[str])` en vez de solo `bool`.** La story decía `-> bool`, pero el reporte necesita los drift fields granulares (AC4: "registra drift granular por campo en el reporte (cuál corrida divergió en qué campo) para poder leerlo sin re-correr"). Refactor mínimo, una única función pura.
2. **`classify_pdf()` también devuelve `(color, stable, drift)`.** Misma razón — evita recalcular `is_stable()` en el caller.
3. **`infer_bank_from_filename()` es case-insensitive.** No estaba especificado pero protege contra `BCI-Visa-...` accidental.
4. **El guard test usa AST (no string match).** Primer intento con `assert "GeminiClient(" not in src` se auto-rompía porque el propio assert contenía la cadena. AST inspection es más limpio y robusto.
5. **`_bmad-output/validation-runs/` agregado a `.gitignore`** (`_bmad-output/` no estaba globalmente ignorado porque contiene los story files trackeables). Sólo se ignora la subcarpeta de runs.

#### Out of scope confirmado

- Retry con feedback a Gemini → Story 9.5d (parqueado, dispatch condicional al output de 9.5c).
- Detección automática de bank_account desde contenido PDF → Story 9.5b (parqueado).
- Validación contra CSV exportado del banco → fuera de scope.
- CI integration → corre local, manual, on-demand.

### File List

**Nuevos:**
- `bootstrap/validate_cartolas_batch.py` — CLI standalone batch runner (Story 9.5c).
- `backend/tests/test_validate_cartolas_batch.py` — 34 tests del clasificador, drift, aggregator, override parser, AST guard contra `GeminiClient`.

**Modificados:**
- `.gitignore` — agregada entrada `_bmad-output/validation-runs/`.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `9-5c-validation-tooling-extraccion-ml` movida de `ready-for-dev` → `in-progress` → `review` durante esta sesión; comentario de `last_updated` actualizado.
- `_bmad-output/implementation-artifacts/9-5c-validation-tooling-extraccion-ml.md` — Tasks/Subtasks marcados [x], Dev Agent Record + File List + Change Log poblados, status → review.

## Change Log

- **2026-05-19 (smoke real abortado + hallazgo crítico) — Ary + Amelia**: El smoke real con 14 PDFs fue cancelado por Ary a mitad de la 2da corrida (11 PDFs procesados completamente + 2 parciales) porque **0% verde sostenido** con patrón sistemático. Diagnóstico conjunto (memory `project_epic9_validacion_cartolas`):

  **Causa raíz identificada — NO es bug de Gemini, ni del wrapper 9.5c, ni de los overrides.** Es el **prompt elaborado de Story 9.5** que está degradando el output:
  - Gemini web sin prompt + mismo PDF + "extrae en CSV" → output limpio sin errores en 3s.
  - Pipeline 9.5 con prompt 3-5KB → ~60s/call + PARSE_AMBIGUOUS / BALANCE_MISMATCH / DUPLICATE_LINE masivos.

  Fuentes específicas de contaminación detectadas:
  1. Sign convention block (Liabilities Beancount) invierte signos sobre PDFs no-TC.
  2. Instrucción "asegurar que el balance cuadre" → Gemini **excluye transactions legítimas** (caso real: `estado-de-cuenta (26).pdf` excluyó `MONTO CANCELADO -$4.825.462`).
  3. Forzar `currency=CLP` sobre PDFs USD genera PARSE_AMBIGUOUS + signos invertidos.
  4. Schema JSON canónico forzado vía `response_mime_type=application/json` gasta ~40% del output en estructura, no en data.

  **El tooling 9.5c funcionó como debía:** detectó empíricamente que el prompt actual no es viable. Sin 9.5c hubiéramos saltado a 9.6a (importer) y cargado data manipulada a Beancount. **La métrica del 90% verde es válida, el dato que reportó (0% verde) es accionable.**

  **Próximos pasos definidos:**
  - 9.6a **BLOCKED** hasta arreglar prompt.
  - 9.5d (retry con feedback) **NO es la solución correcta** — el problema es el prompt, no la robustez de Gemini.
  - Propuesta: Story 9.5e (nueva) — rediseñar prompt para CSV liviano + wrapping server-side al canonical. Reusa el tooling 9.5c tal cual para re-validar.
  - Insight arquitectónico de Ary durante la sesión: mover complejidad de Gemini → Python (Gemini pide data simple, Python wrappea al canonical) es el patrón correcto.

  Capturas del smoke parcial (33 staging files en `_bmad-output/validation-runs/2026-05-19-135748/staging/`, NO se generó report.md porque cancelamos antes del writer):
  - 11 PDFs completos: 4 ROJO (BALANCE_MISMATCH) + 6 AMARILLO (PARSE_AMBIGUOUS/DUPLICATE_LINE/PERIOD_MISMATCH) + 0 VERDE.
  - 2 parciales (`estado-de-cuenta 25` con 2 runs, `27` con 1 run). El `27` con 0 warnings — único candidato a verde, casualmente el más chico (3 tx).

- **2026-05-19 (patch) — Amelia**: Extensión `--override` a 4 campos opcionales (currency). Descubierto durante el primer smoke real (cancelado a mitad por Ary): los samples mezclan TC en CLP y TC en USD para 2 bancos (BCI 9149 + Santander 8996, cada uno en CLP e internacional). Pasarle `currency=CLP` hardcoded a Gemini sobre cartolas USD generaba `PARSE_AMBIGUOUS` masivo + balances inflados (Gemini "ajustaba" excluyendo transactions para forzar cuadre). Currency es opcional con default CLP (backwards-compat con la sintaxis original de 3 campos). 37/37 tests verde (+3 nuevos: currency in 4-field, normalización uppercase, validación enum). `_build_bank_account_entry` ahora también recibe `currency` y lo propaga a `bank_account_id`, `account_label`, y `beancount_account`.
- **2026-05-19 — Amelia (claude-opus-4-7[1m])**: Implementación inicial Story 9.5c.
  - Nuevo: `bootstrap/validate_cartolas_batch.py` (CLI + clasificador + drift detection + writers report.md/runs.csv/summary.csv + cleanup staging).
  - Nuevo: `backend/tests/test_validate_cartolas_batch.py` (34 tests pure-logic; 0 invocaciones a Gemini, verificado por AST guard).
  - Modificado: `.gitignore` para excluir `_bmad-output/validation-runs/`.
  - Status: `ready-for-dev` → `in-progress` → `review`. Smoke real con los 14 PDFs queda pendiente para Ary (AC11 manual, instrucciones en Completion Notes).
