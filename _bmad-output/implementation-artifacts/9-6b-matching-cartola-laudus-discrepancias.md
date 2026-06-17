---
story: 9.6b
title: Motor matching cartola ↔ Laudus + emisión de discrepancias a JSONL
status: review
epic: 9
depends_on: [9.6a, 9.4, 9.10]
blocks: [9.7, 9.12]
---

# Story 9.6b — Motor matching cartola ↔ Laudus + discrepancias

## User Story

As the system,
I want a reconciliation engine that, on cartola import, cross-checks each PDF line against the corresponding Laudus journal entry — classifies the line into one of 7 matching states (perfect / value-mismatch / missing-in-laudus / missing-in-cartola / date-mismatch / description-mismatch / category-mismatch), computes implied FX for USD lines, validates against BCCh end-of-month within 5% threshold, and emits flagged transactions plus an append-only JSONL log of discrepancies,
So that the contador and Ary can resolve discrepancies manually via Story 9.12 dashboard, FX is derivable from real source data (Q4 cierre Opción D), and the ledger has a permanent audit trail of every reconciliation decision.

## Context

**Esta story es el split del 9.6 original (split decidido 2026-05-05).** 9.6a hace el parser básico (path "match perfecto"); 9.6b agrega la **semántica de reconciliación** que cierre Q4 (2026-05-05, Opción D — FX cartola-derivada) introdujo.

**Q4 cerrada — recap:**
- Laudus no preserva `currencyCode` ni `parityToMainCurrency` originales para JEs USD (verificación empírica `_bmad-output/spike-beancount/probe-fx.py`).
- Solución: cartola PDF como source de USD original + Laudus como source de CLP del contador. Matching línea-por-línea.
- FX implícita = `CLP_laudus / USD_cartola` por línea.
- Variable de control: BCCh end-of-month (Story 9.10) con threshold 5% desviación. Out-of-tolerance → flag (no abort).
- Cartola siempre manda excepto en estado "faltante en cartolas".

**Storage de discrepancias:** append-only JSONL en `ledger/_meta/cartola-discrepancies.jsonl`. **NO hay mirror Supabase** (decisión 2026-05-05 eliminar Supabase del diseño). Story 9.12 dashboard lee directo del JSONL via backend (parser simple).

**Dependencias:**
- **9.6a done** — el parser básico que esta story extiende con lógica de matching.
- **9.4 done** — el importer Laudus produce los archivos `imports/laudus/YYYY-MM.beancount` que esta story consulta para hacer el matching.
- **9.10 done** — la tabla `_meta/fx-bcch-eom.jsonl` existe y se popula mensualmente para validación FX.

## Estados de matching (Q4 cierre)

| Estado | Comportamiento | Sistema de verdad | Importa? | Flag |
|---|---|---|---|---|
| `perfect` | Cartola y Laudus coinciden | Ambos | Sí (limpio) | `*` |
| `value-mismatch` | Distinto monto | — | **NO** (bloqueante) | n/a |
| `missing-in-laudus` | Cartola tiene la línea, Laudus no | Cartola | Sí (con flag) | `!` |
| `missing-in-cartola` | Laudus tiene la línea, cartola no | Laudus (CLP-only, sin USD original) | Sí (con flag) | `!` |
| `date-mismatch` | Fechas distintas | Cartola | Sí (con flag, cartola manda fecha) | `!` |
| `description-mismatch` | Descripciones distintas | Cartola | Sí (con flag, cartola manda descripción) | `!` |
| `category-mismatch` | Categorización distinta | Cartola sugiere; smart_importer revisa | Sí (con flag) | `!` |

## Acceptance Criteria

**AC1 — Motor de matching `MatchingEngine`**

**Given** `pipeline/importers/matching_engine.py` existe
**When** se invoca `engine.match(cartola_lines, laudus_entries_for_period) → list[MatchResult]`
**Then** cada `MatchResult` tiene: `state` (∈ los 7 estados), `cartola_line` (o None), `laudus_entry` (o None), `confidence` (0-1), `notes` (str)
**And** el matching usa: (date ± 3 días tolerancia) + (amount exacto si CLP, o amount con FX implícita si USD) + (description similarity ≥ 0.85 vía levenshtein o fuzzywuzzy)
**And** se emite un MatchResult por **cada línea de cartola** (incluyendo las que matchean Laudus). Las líneas Laudus que sobran (no matcharon ninguna cartola) emiten MatchResult adicional con state `missing-in-cartola`.

---

**AC2 — Cálculo de FX implícita por línea USD**

**Given** una `MatchResult` con `state ∈ {perfect, date-mismatch, description-mismatch}` Y la línea de cartola está en USD
**When** se calcula `fx_implied = CLP_laudus / USD_cartola`
**Then** el resultado se guarda en metadata Beancount de la Transaction emitida:
  ```beancount
  fx_source: "derived-cartola-{bank_slug}-{YYYY-MM}"
  fx_implied: "950.45"
  fx_bcch: "948.20"
  fx_deviation_pct: "0.24"
  ```
**And** los postings usan `@@` notation: `Liabilities:EAG:TC:Citi    -100.00 USD @@ 95045.00 CLP`
**And** el plugin `implicit_prices` deriva price directives automáticamente — `prices.beancount` queda como placeholder vacío en el repo

---

**AC3 — Validación BCCh threshold 5%**

**Given** una línea con `fx_implied` calculada
**When** se compara con `fx_bcch` del mes correspondiente (lookup en `ledger/_meta/fx-bcch-eom.jsonl` populated por Story 9.10)
**Then** se calcula `fx_deviation_pct = |fx_implied - fx_bcch| / fx_bcch * 100`
**And** si `fx_deviation_pct > 5%` → la Transaction se emite con flag `!` Y entrada en discrepancies JSONL con `state: "fx-out-of-tolerance"`
**And** si `fx_deviation_pct ≤ 5%` → flag normal (`*` o `!` según otros criterios)
**And** si BCCh no tiene data para ese mes (Story 9.10 no corrió todavía o data ausente) → flag `!` con `state: "fx-bcch-missing"` y `fx_deviation_pct: null`

---

**AC4 — Comportamiento por estado**

**Given** una `MatchResult` con state X
**When** se procesa para emisión
**Then** el comportamiento es:
  - `perfect` → emitir Transaction con flag `*`, sin entrada en discrepancies
  - `value-mismatch` → **NO emitir Transaction**. Solo entrada en discrepancies. Bloqueante hasta resolución manual via 9.12.
  - `missing-in-laudus` → emitir Transaction desde cartola con flag `!`. Entrada en discrepancies con `source: "cartola"`.
  - `missing-in-cartola` → emitir Transaction desde Laudus CLP-only con flag `!` (sin USD original ni FX). Entrada en discrepancies con `source: "laudus"`.
  - `date-mismatch` → emitir Transaction con flag `!`, **fecha de cartola manda**. Entrada en discrepancies con ambas fechas.
  - `description-mismatch` → emitir Transaction con flag `!`, **descripción de cartola manda**. Entrada en discrepancies con ambas descripciones.
  - `category-mismatch` → emitir Transaction con flag `!`, sugerencia de cartola se preserva en `suggested_category` metadata. Entrada en discrepancies. (`smart_importer` revisa y puede confirmar/corregir post-import.)

---

**AC5 — Emisión a `cartola-discrepancies.jsonl`**

**Given** una `MatchResult` con `state ∉ {perfect}`
**When** se procesa
**Then** se appendea una línea a `ledger/_meta/cartola-discrepancies.jsonl` con shape:
  ```json
  {
    "discrepancy_id": "uuid-v4",
    "ts": "2026-05-05T14:30:00Z",
    "batch_id": "...",
    "bank_account_id": "...",
    "state": "value-mismatch",
    "cartola": {
      "line_no": 12,
      "date": "2026-04-15",
      "amount": -45000,
      "currency": "CLP",
      "description": "JUMBO"
    },
    "laudus": {
      "journal_entry_id": "12345",
      "date": "2026-04-15",
      "amount": -47000,
      "description": "Jumbo Costanera"
    },
    "fx": {
      "implied": null,
      "bcch": null,
      "deviation_pct": null
    },
    "resolution": null
  }
  ```
**And** el JSONL es append-only — nunca se reescriben líneas. La resolución se appendea como nueva línea con `discrepancy_id` referenciando la original (audit trail full).
**And** cuando una discrepancia se resuelve via 9.12 dashboard, se appendea entrada con `resolution: {action, resolved_by, resolved_at, justification}`.

---

**AC6 — Re-emit del archivo `.beancount` post-resolución**

**Given** una discrepancia se resuelve via 9.12 dashboard (Story 9.12 invoca a esta story)
**When** la resolución se commitea
**Then** el archivo `imports/cartolas/{slug}.beancount` correspondiente se **re-genera** (write-and-replace) con la directiva ajustada según la acción de resolución
**And** `bean-check ledger/main.beancount` pasa post-re-emit
**And** se commitea con mensaje `[reconciliation] resolve {discrepancy_id}: {action}` y push

---

**AC7 — Idempotencia del matching**

**Given** un staging file procesado una vez con matching engine
**When** se re-procesa (mismo cartola JSON + mismo estado de Laudus)
**Then** los `MatchResult` son bit-idénticos (mismo state por cada línea, mismas fechas/amounts)
**And** no se duplican entradas en `cartola-discrepancies.jsonl` (dedup por `(batch_id, cartola_line_no, laudus_je_id)`)

---

**AC8 — Storage FX en Transaction (USD)**

**Given** una línea USD con matching exitoso
**When** se emite la Transaction
**Then** la directiva tiene metadata `fx_source`, `fx_implied`, `fx_bcch`, `fx_deviation_pct` (todos como strings — convención Beancount)
**And** los postings llevan `@@` notation USD-CLP:
  ```beancount
  2026-04-15 * "Amazon"
    fx_source: "derived-cartola-citi-202604"
    fx_implied: "950.45"
    fx_bcch: "948.20"
    fx_deviation_pct: "0.24"
    Liabilities:EAG:TC:Citi    -100.00 USD @@ 95045.00 CLP
    Expenses:EAG:OnlinePurchases  95045.00 CLP
  ```
**And** plugin `implicit_prices` deriva la price directive `2026-04-15 price USD 950.45 CLP` automáticamente

---

**AC9 — Pre-2026 sigue siendo CLP-only**

**Given** una cartola con `period.start < 2026-01-01`
**When** el matching engine corre
**Then** todas las líneas se procesan CLP-only sin lógica FX (mismo comportamiento que importer Laudus en 9.4)
**And** no se calcula `fx_implied` ni se appendea entrada FX a discrepancies
**And** el matching solo verifica date + amount + description (sin USD)

---

## Tasks / Subtasks

- [x] Task 1: `MatchingEngine` core (AC1) — `pipeline/importers/matching_engine.py`: `match()` greedy con scoring (fecha ±3, monto exacto CLP, desc ≥0.85), 7 estados + `missing-in-cartola` para sobrantes. + `load_laudus_entries()` (carga asientos del período desde imports/laudus/*.beancount). 11 tests.

- [x] Task 2: FX calculation + BCCh validation (AC2 + AC3) — `fx_calculator.py`: `calculate_fx()` + `lookup_bcch()`. FXResult con estados ok/out-of-tolerance/bcch-missing/implausible. 7 tests (incl. USD=0, >2000).

- [x] Task 3: Behavior por estado (AC4) — `reconcile.process_match_result()` → `ProcessDecision(emit, flag, discrepancies)`. Overlay FX (AC3) fuerza `!` + discrepancia FX incluso sobre `perfect`.

- [x] Task 4: JSONL emission + dedup (AC5 + AC7) — `discrepancy_writer.py`: `build_discrepancy` (shape AC5, `schema_version 1.0`) + `append_discrepancy` (dedup por `(batch_id, line_no, je_id)`) + `append_resolution` (append-only). 8 tests con reconcile.

- [x] Task 5: Storage FX en Transaction (AC8) — `cartola_pdf_importer.build_usd_postings()` (price per-unit CLP; `implicit_prices` deriva la price) + `fx_metadata()`. Verificado vía bean-check sobre el render.

- [x] Task 6: Re-emit post-resolución (AC6) — `reconcile.commit_reconciliation(file, new_content, id, action, root)`: write-and-replace + bean-check (rollback si rojo) + git commit `[reconciliation] resolve {id}: {action}` + lock. La derivación de `new_content` desde la acción la provee Story 9.12. 2 tests (verde + rollback).

- [x] Task 7: Pre-2026 CLP-only (AC9) — `USD_FX_EPOCH` en el engine; `period_start < 2026-01-01` → sin lógica FX. Test pre-2026.

- [x] Task 8: Integration — `reconcile.reconcile_and_build()` ata matching→FX→behavior→(entries beancount + discrepancias). Tests: fixture multi-estado (perfect/value-mismatch/USD+FX/missing) → render + load (bean-check verde), pre-2026 CLP-only. **SEAM pendiente:** flipear el `promote()` del upload real (9.6a) para llamar `reconcile_and_build` (con `load_laudus_entries`) en vez del extract perfecto — ver Completion Notes.

- [x] Task 9: Documentación — sección "Matching engine + reconciliación" en `pipeline/importers/README.md` (diagrama de flujo, tabla 7 estados, FX, runbook de resolución manual).

---

## Dev Notes

### Input autoritativo

`q4-fx-decision-2026-05-05.md` — decisión Opción D + tabla de estados + storage FX. `architecture-c4.md §2.4` — versión actualizada con Q4. `bob-x-moishe-epic9-2026-04-30.md` — ítem #5 (scope ampliado) + ítem #9 (sin Supabase).

### Sin Supabase mirror

Storage de discrepancias = **single source JSONL** (`ledger/_meta/cartola-discrepancies.jsonl`). No hay tabla `cartola_reconciliation` en Supabase. 9.12 dashboard lee directo del JSONL via backend.

Razón: bajo c4 puro Beancount + archivos en git es la única SoT. Supabase quedaba como mirror duplicado sin valor (decisión 2026-05-05).

Performance: 9.12 dashboard maneja cientos/miles de líneas sin problema (lectura de JSONL line-by-line + filtros in-memory). Para millones de líneas habría que indexar — caso no aplicable al volumen real del proyecto.

### Decisiones de tolerancia/threshold

- **Date matching:** ± 3 días (cartola y Laudus pueden diferir por timing de processing)
- **Description similarity:** ≥ 0.85 (levenshtein normalizado o fuzzywuzzy.ratio)
- **FX BCCh threshold:** 5% (Q4 cierre)
- **Amount matching exacto** para CLP. Para USD: tolerance via FX implied (no comparación directa).

### Re-emit transactional

Cuando una discrepancia se resuelve, NO se edita el archivo `.beancount` line-by-line. Se **regenera** el archivo entero del cartola (write-and-replace). Razón: simpler, idempotente, fácil de auditar via git diff. Costo: re-generar un archivo de cartola es trivial (tens of lines).

### Project structure

```
pipeline/importers/
  matching_engine.py                       # NEW (esta story)
  fx_calculator.py                         # NEW (esta story)
  discrepancy_writer.py                    # NEW (esta story)
ledger/_meta/
  cartola-discrepancies.jsonl              # NEW (vacío en bootstrap, populated por esta story)
```

### Out of scope

- Dashboard UI (Story 9.12)
- Endpoint backend que sirve el JSONL (Story 9.12 lo agrega)
- Re-categorización de líneas con `category-mismatch` (eso lo hace `smart_importer` post-import en 9.7)

### References

- [Source: q4-fx-decision-2026-05-05.md — Opción D, tabla estados, storage FX]
- [Source: architecture-c4.md §2.4 — versión Q4]
- [Source: bob-x-moishe-epic9-2026-04-30.md — ítem #5 scope ampliado, ítem #9 sin-Supabase]
- [Source: 9-6a-beangulp-importer-parser-basico.md — parser que esta story extiende]
- [Source: 9-10-cron-prices-clp-usd.md — fuente BCCh end-of-month]
- [Source: 9-12-dashboard-reconciliacion.md — consumidor del JSONL]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Amelia / dev-story)

### Debug Log References

- Tests nuevos 9.6b: `test_matching_engine.py` (11), `test_fx_calculator.py` (7),
  `test_reconcile.py` (8), `test_reconcile_integration.py` (5) = **31 passed**.
- Suite backend completa: **563 passed / 1 xfailed / 1 failed**. El rojo es el pre-existente
  date-dependiente `test_sync.py::test_run_backfill_calls_upsert_for_both_sheets` (sin relación).
- Balance de los postings (CLP y USD `@`) + derivación de price verificados cargando el render
  con `loader.load_string` (equivalente a bean-check), no solo por aritmética.

### Completion Notes List

- **4 módulos puros + 1 orquestador** (testeables sin red): `matching_engine.py` (estados +
  `load_laudus_entries`), `fx_calculator.py` (FX + BCCh), `discrepancy_writer.py` (JSONL
  append-only + dedup), `reconcile.py` (`process_match_result` + `reconcile_and_build` +
  `commit_reconciliation`).
- **USD `@@` → `@` per-unit:** beancount serializa price per-unit; usé price per-unit =
  `fx_implied` (equivalente, balancea, `implicit_prices` deriva la price — verificado por bean-check).
- **`value-mismatch` NO emite** Transaction (bloqueante hasta 9.12); `missing-in-cartola` emite
  desde Laudus CLP-only; el resto emite con flag `!`.
- **SEAM de integración (lo único que falta para correr en prod):** el upload real sigue usando el
  `promote()` perfect-path de 9.6a. Para activar la reconciliación en vivo: en el flujo de upload,
  reemplazar el `extract` por `reconcile_and_build(...)` alimentado con `load_laudus_entries(...)` +
  appendear las discrepancias retornadas. No flipeé el `promote` de 9.6a para no cambiar su
  comportamiento ni romper sus tests — el *cuándo* corre la reconciliación es decisión del flujo de
  upload. Engine + loader + orquestador ya listos y testeados para wirear.
- **AC6 (re-emit)** lo invoca Story 9.12: `commit_reconciliation` hace el mecanismo (write-replace +
  bean-check + git + lock); 9.12 deriva el `new_content` desde la acción de resolución.

### File List

**Nuevos (pipeline):**
- `pipeline/importers/matching_engine.py` — `match()` + 7 estados + `load_laudus_entries()`
- `pipeline/importers/fx_calculator.py` — `calculate_fx()` + `lookup_bcch()`
- `pipeline/importers/discrepancy_writer.py` — JSONL append-only + dedup + `append_resolution`
- `pipeline/importers/reconcile.py` — behavior + orquestador + re-emit

**Modificados (pipeline):**
- `pipeline/importers/cartola_pdf_importer.py` — `build_usd_postings()` + `fx_metadata()` (AC8)
- `pipeline/importers/README.md` — sección matching/reconciliación (Task 9)

**Nuevos (tests):**
- `backend/tests/test_matching_engine.py`, `test_fx_calculator.py`, `test_reconcile.py`,
  `test_reconcile_integration.py` — 31 tests

## Change Log

| Fecha | Cambio |
|---|---|
| 2026-06-17 | 9.6b: motor de reconciliación cartola↔Laudus (7 estados + FX implícita + BCCh 5% + JSONL append-only + re-emit) en 4 módulos + orquestador. 31 tests. Seam: wiring del promote de upload pendiente. Status → review. |
