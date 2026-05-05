---
story: 9.6b
title: Motor matching cartola ↔ Laudus + emisión de discrepancias a JSONL
status: ready-for-dev
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

- [ ] Task 1: `MatchingEngine` core (AC1)
  - [ ] Crear `pipeline/importers/matching_engine.py`
  - [ ] Función `match(cartola_lines, laudus_entries) → list[MatchResult]`
  - [ ] Algoritmo: matching greedy con scoring (date ± 3 días, amount tolerance, description similarity)
  - [ ] Tests con 6 fixtures (uno por estado): cada fixture tiene cartola JSON + laudus entries esperados + expected MatchResults

- [ ] Task 2: FX calculation + BCCh validation (AC2 + AC3)
  - [ ] Función `calculate_fx(cartola_line_usd, laudus_entry_clp, bcch_table) → FXResult`
  - [ ] FXResult: `implied`, `bcch`, `deviation_pct`, `out_of_tolerance` (bool)
  - [ ] Lookup BCCh: leer `ledger/_meta/fx-bcch-eom.jsonl` (populated por 9.10), encontrar entry para `period.year_month` de la cartola
  - [ ] Tests: 5 casos (in-tolerance, out-of-tolerance, BCCh missing, USD=0 edge, FX implausible >2000)

- [ ] Task 3: Behavior por estado (AC4)
  - [ ] Función `process_match_result(match_result, fx_result) → (transaction_or_none, discrepancy_or_none)`
  - [ ] Switch sobre `state` con la tabla de comportamiento
  - [ ] Tests: 7 casos (uno por estado) + edge cases (FX out-of-tolerance combinado con date-mismatch, etc.)

- [ ] Task 4: JSONL emission + dedup (AC5 + AC7)
  - [ ] Función `append_discrepancy(discrepancy, jsonl_path)` con dedup por `(batch_id, cartola_line_no, laudus_je_id)`
  - [ ] Schema versioning: `schema_version: "1.0"` en cada entrada (futureproofing)
  - [ ] Tests: append + idempotencia (re-correr no duplica)

- [ ] Task 5: Storage FX en Transaction (AC8)
  - [ ] Modificar `_build_postings` de 9.6a para soportar el caso USD con `@@` notation
  - [ ] Inyección de metadata FX (`fx_source`, `fx_implied`, etc.) cuando el state lo amerita
  - [ ] Tests: 3 casos (TC USD perfect, TC USD out-of-tolerance, cta_corriente USD)

- [ ] Task 6: Re-emit post-resolución (AC6)
  - [ ] Función `re_emit_after_resolution(discrepancy_id) → file_path`
  - [ ] Lee la cadena de discrepancies (original + resolución), determina nuevo estado del file
  - [ ] Re-genera `imports/cartolas/{slug}.beancount` write-and-replace
  - [ ] `bean-check` + git commit + push (mismo patrón que 9.4)
  - [ ] Lock file (mismo `.import.lock`)

- [ ] Task 7: Pre-2026 CLP-only (AC9)
  - [ ] Branch lógico en `MatchingEngine.match`: si `period.start < 2026-01-01` → skip lógica FX
  - [ ] Tests: cartola 2024 (full CLP) → no aparecen entradas FX en discrepancies, no `@@` notation en directivas

- [ ] Task 8: Integration tests con `cartola_pdf_importer` (9.6a)
  - [ ] Fixture: cartola JSON de TC USD con 5 líneas (mix de estados)
  - [ ] Run pipeline: 9.6a parser → 9.6b matching → output `.beancount` + JSONL
  - [ ] Verificar bean-check OK, JSONL bien formado, transactions con metadata correcta

- [ ] Task 9: Documentación
  - [ ] Update `pipeline/importers/README.md` con sección "Matching engine + reconciliation"
  - [ ] Diagrama de flujo: cartola JSON → MatchingEngine → MatchResults → process_match_result → (Transactions + Discrepancies)
  - [ ] Tabla de los 7 estados con ejemplos
  - [ ] Runbook para resolver discrepancias manualmente desde 9.12

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
