---
story: 9.7
title: Categorización con smart_importer + Patrón B (era 5.1)
status: ready-for-dev
epic: 9
depends_on: [9.6]
blocks: []
prd_update_needed: true
---

# Story 9.7 — Categorización con smart_importer + Patrón B

## User Story

As the system,
I want each PDF cartola transaction to be auto-categorized via `smart_importer` (machine-learned from history) with a confidence threshold of 0.85, falling back to historical exact-match and Gemini, and producing a Beancount flag (`*` confirmed vs `!` needs review) so the contador only reviews what the model is unsure about,
So that 80%+ of categorization is automated, the contador focuses on edge cases, and after 30 corrections of the same pattern the rule promotes to "supra" — overriding any ML prediction.

## Context

Decisión Q6 (Ary):
- **smart_importer** (Beancount community ML categorizer) corre sobre el history del ledger.
- **Patrón B**: confidence threshold = 0.85 → si el modelo predice con confianza ≥ 0.85, flag `*` (auto-asignada); abajo flag `!` (pendiente review).
- **Regla supra**: 30 correcciones consecutivas mismo destino → promueve a permanente, override sobre el modelo.

`PRD-update needed` #3: el threshold-30 del PRD original se reformula como "regla supra sobre ML", no como reemplazo. John actualiza PRD en sesión separada.

Esta story implementa el `CategorizationService` real que Story 9.6 inyecta como `category_predictor`.

## Acceptance Criteria

**AC1 — `CategorizationService.predict(description, amount, bank_account_id)`**

**Given** el servicio está instanciado
**When** se llama `predict("SUPERMERCADO JUMBO", -45000, "<uuid>")`
**Then** retorna una tupla `(category_account, match_source, confidence, flag)`:
  - `category_account`: string Beancount (ej: `"Expenses:EAG:Supermercado-413044"`)
  - `match_source` ∈ `{"historical-30+", "smart_importer", "historical", "gemini", "pending"}`
  - `confidence`: float [0, 1]
  - `flag` ∈ `{"*", "!"}` — `*` si el motor está confiado (≥ threshold o regla supra), `!` si no

---

**AC2 — Stage 1: regla supra (≥ 30 correcciones) — gana siempre**

**Given** el log `ledger/_meta/categorization-history.jsonl` tiene ≥ 30 entradas con misma `description_normalized` apuntando a la misma `corrected_category`
**When** `predict()` se llama con esa description
**Then** retorna esa categoría con `match_source = "historical-30+"`, `confidence = 1.0`, `flag = "*"` — independiente de lo que diga smart_importer
**And** este es el FR31 reformulado (regla supra sobre ML)

---

**AC3 — Stage 2: smart_importer con threshold 0.85**

**Given** la regla supra NO matchea (< 30 correcciones para esa description)
**When** `predict()` continúa con smart_importer
**Then** corre el modelo entrenado sobre el ledger history (Transactions con flag `*` y categoría asignada)
**And** si la confianza del modelo es ≥ 0.85 → retorna su predicción con `match_source = "smart_importer"`, `confidence = score_real`, `flag = "*"`
**And** si la confianza es < 0.85 → retorna su predicción con `flag = "!"` (sugerida pero sin confirmar)

---

**AC4 — Stage 3: historical exact-match con < 30 correcciones**

**Given** smart_importer NO retorna predicción (caso vacío) Y hay 1-29 correcciones consistentes históricas
**When** `predict()` continúa
**Then** retorna esa categoría con `match_source = "historical"`, `confidence = N/30` (proporción), `flag = "!"`

---

**AC5 — Stage 4: Gemini fallback con lista cerrada**

**Given** los stages 1-3 NO retornaron categoría
**When** `predict()` cae a Gemini
**Then** llama `GeminiClient.suggest_category(description, amount, allowed=expense_accounts_85)`
**And** la lista `allowed` es las 85 cuentas Expenses del plan_de_cuentas (Supabase)
**And** Gemini DEBE retornar una de esas — si retorna texto libre o nada → match_source = "pending"
**And** si Gemini retorna válido → `match_source = "gemini"`, `confidence = 0.5` (heurístico), `flag = "!"`

---

**AC6 — Stage 5: fallback final → Suspense**

**Given** ningún stage matchea
**When** `predict()` termina
**Then** retorna `("Expenses:EAG:Suspense", "pending", 0.0, "!")` — flag `!` siempre, requiere review explícita

---

**AC7 — Update via `PATCH /api/v1/transactions/{tx_id}/category`**

**Given** el contador corrige la categoría de una tx desde el frontend
**When** `PATCH /api/v1/transactions/{tx_id}/category` se llama con `{"category_account": "Expenses:EAG:..."}`
**Then** el endpoint:
  1. Busca la directiva en el archivo `imports/cartolas/{...}.beancount` correspondiente (vía metadata `tx_id` o el archivo + line)
  2. Modifica el posting de categoría al nuevo `category_account`
  3. Cambia `flag` de `!` a `*`
  4. Update `meta.category_status` a `"confirmed"`
  5. Appendea línea a `ledger/_meta/categorization-history.jsonl`:
     ```json
     {"ts": "2026-05-01T10:30:00Z", "description_normalized": "SUPERMERCADO JUMBO",
      "corrected_category": "Expenses:EAG:Supermercado-413044",
      "original_suggestion": "Expenses:EAG:RestaurantBares-413055",
      "user": "contador@ammy.cl"}
     ```
  6. `bean-check` pre-commit; si OK → commit + push, si KO → revert
**And** el cache LRU del CategorizationService se invalida para esa description

---

**AC8 — Update bulk: `POST /api/v1/transactions/bulk-confirm`**

**Given** el contador acepta todas las suggestions de un batch al mismo tiempo
**When** `POST /api/v1/transactions/bulk-confirm` se llama con `{"batch_id": "..."}`
**Then** todas las tx de ese batch con `flag = "!"` y `match_source != "pending"` se confirman: flag pasa a `*`, status `confirmed`
**And** las tx con `match_source = "pending"` (sin sugerencia) NO se confirman — siguen `!` (necesitan corrección manual)

---

**AC9 — `GET /api/v1/categorization/pending`**

**Given** el contador navega al panel de revisión
**When** `GET /api/v1/categorization/pending` se llama
**Then** retorna todas las Transactions del ledger con `meta.category_status IN ('suggested', 'pending')` agrupadas por `bank_account_id` → `period`
**And** cada tx incluye: tx_id (file + line), date, narration, amount, currency, current_category, current_flag, current_match_source, current_confidence

---

**AC10 — Description normalizer estable**

**Given** dos descripciones equivalentes (ej: "SUPERMERCADO JUMBO" vs "supermercado jumbo  " vs "SUPERMERCADO JUMBO 12345")
**When** `normalize(description)` corre
**Then** las 3 producen la misma key normalizada
**And** la normalización: uppercase + strip + remove trailing numerics + remove duplicate spaces + remove punctuation común
**And** documentado el algoritmo exacto en docstring + 10 casos de test (incluyendo bordes)

---

## Tasks / Subtasks

- [ ] Task 1: Description normalizer
  - [ ] Crear `pipeline/importers/categorization/normalizer.py`
  - [ ] Función pura `normalize(description: str) → str`
  - [ ] Reglas: uppercase + strip + remove punctuation comunes (`.,;:#`) + collapse whitespace + remove trailing digits si > 4 + remove "REF " prefix
  - [ ] Tests con 10+ casos incluyendo unicode, números embebidos, prefijos bancarios

- [ ] Task 2: `categorization-history.jsonl` reader/writer
  - [ ] `pipeline/importers/categorization/history.py`
  - [ ] Append-only writer + cached reader (loaded on startup, in-memory dict por `description_normalized`)
  - [ ] Función `count_for(description_normalized, category_account)` y `dominant_category(description_normalized) → (category, count)`

- [ ] Task 3: Integración smart_importer
  - [ ] Investigar la API de `smart_importer` (`pip install smart_importer`)
  - [ ] Decidir el classifier: `EntryPredictor` con `attributes=[narration]` o `PredictAccount` (o combinación)
  - [ ] Train sobre `ledger/main.beancount` (entries con `flag = "*"` y category asignada)
  - [ ] Wrapper `SmartImporterAdapter` que devuelve `(category, confidence)`
  - [ ] Cache del modelo entrenado: re-entrenar cada N días o cuando categorization-history.jsonl crece > X líneas

- [ ] Task 4: `CategorizationService` orquestador
  - [ ] Crear `pipeline/importers/categorization/service.py`
  - [ ] Implementar el pipeline 5-stages (AC2-AC6)
  - [ ] Constructor inyecta: `history`, `smart_importer_adapter`, `gemini_client`, `expense_accounts_list` (las 85)
  - [ ] Cache LRU para predicciones repetidas

- [ ] Task 5: Adapter para Story 9.6
  - [ ] La interface que 9.6 espera es `category_predictor.predict(description, amount, bank_account_id) → (category_account, match_source)` (sin confidence ni flag)
  - [ ] Adaptar el output de `CategorizationService` al shape de 9.6 → mapear flag a la decisión de 9.6 sobre `Transaction.flag`
  - [ ] **Decisión:** la flag (`*` vs `!`) la decide ESTE servicio y 9.6 la propaga al data.Transaction

- [ ] Task 6: Endpoint `PATCH /api/v1/transactions/{tx_id}/category` (AC7)
  - [ ] Crear `backend/app/api/v1/transactions/router.py`
  - [ ] Resolver tx_id → (file_path, line_number) — necesita tx_id stable. **Decisión:** tx_id = SHA256 hash de `(file_path, line, narration, amount)` truncado a 12 chars. Documentar.
  - [ ] Edit del archivo: leer + parsear con beancount.parser, modificar el posting, reemitir, atomic rename
  - [ ] Categorization-history append + bean-check pre-commit + git commit/push
  - [ ] RBAC: `require_role(["contador"])`

- [ ] Task 7: Endpoint `POST /api/v1/transactions/bulk-confirm` (AC8)
  - [ ] Loop sobre tx del batch con flag `!` y match_source válido
  - [ ] Misma lógica que AC7 pero en bulk
  - [ ] Single commit con todas las correcciones agrupadas

- [ ] Task 8: Endpoint `GET /api/v1/categorization/pending` (AC9)
  - [ ] BQL query: tx con `meta.category_status IN ('suggested','pending')`
  - [ ] Group by `bank_account_id` → `period`
  - [ ] Response paginated si > 100 entries

- [ ] Task 9: Tests
  - [ ] Unit normalizer (Task 1)
  - [ ] Unit history (Task 2): count_for, dominant_category con fixtures de jsonl
  - [ ] Unit pipeline 5-stages: cada stage activado en aislamiento
  - [ ] Integration smart_importer: train sobre fixture ledger → predict en test set
  - [ ] Integration endpoint PATCH: edit válido → flag pasa a `*`, history appended, bean-check OK; edit inválido → 400, ledger intocado

---

## Dev Notes

### Input autoritativo

`architecture-c4.md` §4.3 — Categorización con feedback loop. `bob-x-moishe-epic9-2026-04-30.md` cierre Q6 — decisión Patrón B + threshold 0.85 + regla supra.

### Diferencia con Story 5.1 original

Story 5.1 corría sobre Supabase `cartola_transactions` con stages 1 (historical) + 2 (Gemini). Esta story corre sobre el ledger Beancount con stages 1-supra + 2-smart_importer + 3-historical + 4-gemini + 5-suspense. **Más sofisticada y empotrada en el pipeline de import** (no es una pasada separada).

### `PRD-update needed` #3

PRD original define FR31 como "30 correcciones cambian la categoría primaria". Q6 reformula: smart_importer asistente + threshold-30 como regla supra. John resuelve el wording. NO bloquea esta story.

### smart_importer — referencia

- Repo: `https://github.com/beancount/smart_importer` (asumido — verificar)
- Provee `EntryPredictor`/`PredictAccount` que se acoplan a beangulp Importers
- Train data: histórico de entries del propio ledger
- Output: prediction con score (probabilidad)

### tx_id stability

Crítico: tx_id debe ser stable entre commits del mismo file (no cambiar si re-formatea). Hash sobre `(file, line, narration, amount, account_target)` es robusto si beancount no re-numera lines en re-format. Documentar caveat en código.

### Project structure

```
pipeline/importers/categorization/
  normalizer.py                            # Task 1
  history.py                               # Task 2
  smart_importer_adapter.py                # Task 3
  service.py                               # Task 4
  README.md
backend/app/api/v1/
  transactions/
    router.py                              # Task 6 + 7
    service.py
    schemas.py
  categorization/
    router.py                              # Task 8
    service.py
ledger/_meta/
  categorization-history.jsonl             # append-only
  categorization-model.pkl                 # cached trained model (gitignored)
```

### Dependencies

```
smart_importer>=0.5
```

### References

- [Source: architecture-c4.md §4.3 — Categorización con feedback loop]
- [Source: bob-x-moishe-epic9-2026-04-30.md — Q6 (Patrón B + 0.85 + regla supra)]
- [Source: epics.md Story 5.1 original — partes preservadas conceptualmente]
- [External: https://github.com/beancount/smart_importer]
