---
story: 9.6a
title: Beangulp importer — JSON canónico → directivas Beancount (parser básico, match perfecto)
status: ready-for-dev
epic: 9
depends_on: [9.5]
blocks: [9.6b, 9.7, 9.9]
---

# Story 9.6a — Beangulp importer JSON → directivas (parser básico)

## User Story

As the system,
I want a beangulp `Importer` class that consumes the canonical JSON from Story 9.5, transforms each transaction into Beancount directives, emits a `Balance` directive at period.end to enforce closing-balance validation, and writes a single `.beancount` file per cartola,
So that PDF cartolas become first-class citizens of the ledger with native double-entry validation — without yet doing cross-source reconciliation against Laudus (that's 9.6b).

## Context

**Esta story es el split del 9.6 original (split decidido 2026-05-05):**
- **9.6a (esta story):** parser básico cartola JSON → directivas. Todo lo que es **mecánica idempotente** del path "match perfecto" del estado de matching (Q4 cierre). Sin lógica de reconciliación cross-source.
- **9.6b (story siguiente):** motor de matching cartola ↔ Laudus + emisión de discrepancias a JSONL + manejo de los 6 estados de discrepancia. Depende de 9.6a done.

Story 4.1b reformulada bajo c4. Esquema completo en `architecture-c4.md` §4.2. Esta story crea la clase `CartolaPdfImporter(beangulp.Importer)` que consume `ledger/imports/cartolas/_staging/{batch_id}.cartola.json` (output de 9.5) y produce un archivo `ledger/imports/cartolas/{slug}.beancount`.

Decisiones cerradas que aplican a 9.6a:
- TC como `Liabilities:{Entity}:TC:...` (Q7 — corrige bug semántico actual). `PRD-update needed` #2.
- `Balance` directive al cierre del período → `bean-check` valida automáticamente FR22-25.
- Override con justificación → convierte la `Balance` en `pad`+`balance` con metadata `override_justification` (idiomático Beancount).
- Cuenta destino del pad: `Equity:Reconciliation:Discrepancias` (Ary confirmó naming 2026-04-30).
- Categorización integrada en este pipeline via Story 9.7 (NO separada). En esta story: dejar el hook abierto (CategorizationService inyectado), pero la implementación full está en 9.7.

**Lo que NO está en 9.6a (queda para 9.6b):**
- Motor de matching cartola ↔ Laudus (estados: match perfecto / distinto valor / faltante en Laudus / faltante en cartola / distinta fecha / distinta descripción / distinta categoría)
- Cálculo de `fx_implied = CLP_laudus / USD_cartola` por línea
- Cross-check con BCCh end-of-month, threshold 5%
- Emisión de discrepancias a `ledger/_meta/cartola-discrepancies.jsonl`
- Comportamiento por estado (importa con flag, no importa, etc.)
- Storage de FX en metadata Beancount (`fx_source`, `fx_implied`, `fx_bcch`, `fx_deviation_pct`) + `@@` notation USD-CLP

**9.6a asume todas las líneas son "match perfecto"** — emite directamente Transactions CLP-only (o USD-only si así viene en la cartola, pero sin reconciliación).

## Acceptance Criteria

**AC1 — Clase `CartolaPdfImporter`**

**Given** `pipeline/importers/cartola_pdf_importer.py` existe
**When** se inicializa `CartolaPdfImporter(bank_account_resolver, category_predictor)`
**Then** la clase implementa `beangulp.Importer` con métodos `identify(file)`, `account(file)`, `extract(file, existing_entries=None)`
**And** `identify(file)` retorna `True` solo si: nombre termina en `.cartola.json` Y JSON parse OK Y `schema_version` empieza con `"1."`

---

**AC2 — `account(file)` resuelve cuenta destino vía `accounts.beancount`**

**Given** un archivo de staging `{batch_id}.cartola.json`
**When** `account()` se invoca
**Then** lee `source.bank_account_id` y resuelve la cuenta Beancount correspondiente vía `bank_account_resolver.resolve(bank_account_id)`
**And** el resolver lee la metadata `bank_account_id` de `accounts.beancount` (parseado al boot, cached in-memory) — **NO consulta Supabase ni ningún registry separado**
**And** la cuenta sigue patrón §2.1 (`Assets:{Entity}:Bancos:Slug-N` o `Liabilities:{Entity}:TC:Slug-N` según `account_type` que también vive en metadata de `accounts.beancount`)

---

**AC3 — `extract(file)` emite Transactions**

**Given** un JSON canónico válido con N transactions (asumido "match perfecto" — sin lógica de reconciliación en 9.6a)
**When** `extract()` se invoca
**Then** retorna una lista de N `data.Transaction` + 1 `data.Balance` (closing assertion)
**And** cada Transaction tiene:
  - `flag = "*"` (categorización confirmada por threshold) o `flag = "!"` (pendiente review — coordinar con Story 9.7)
  - `narration` = `tx.description` (o `f"line {tx.line_no}"` si description vacía)
  - `payee = None` (no usado por ahora)
  - `tags` y `links` vacíos
  - `meta`: `source: "cartola-pdf"`, `bank_account_id`, `match_source` (`historical|gemini|pending`), `category_status` (`suggested|pending`), `extraction_model`, `line` = `tx.line_no`
  - 2 postings: cuenta destino (resuelta por `account()`) + categoría (de `CategorizationService.predict`)

---

**AC4 — Postings con sign convention correcto según account_type**

**Given** una transaction con `amount = -45000` (outflow) en una TC (`tarjeta_credito`)
**When** `_build_postings(...)` se invoca
**Then** emite postings tales que:
  - `Liabilities:EAG:TC:VisaInfinityEduardo-XXXXX` con `+45000 CLP` (deuda crece)
  - `Expenses:EAG:{Categoria}` con `+45000 CLP` (gasto crece)
**And** los dos postings suman 0 entre roots (Liabilities + Expenses) — Beancount double-entry OK

**And given** la misma transaction sobre una `cta_corriente` (Asset)
**When** se construye
**Then** emite:
  - `Assets:EAG:Bancos:BancoBci-NNN` con `-45000 CLP` (asset baja)
  - `Expenses:EAG:{Categoria}` con `+45000 CLP`

---

**AC5 — `Balance` directive al cierre (FR22-25 reemplazo)**

**Given** el período es `2026-03-01` a `2026-03-31` con `closing = 95000.00`
**When** `extract()` termina las transactions
**Then** appendea un `data.Balance` al `account_target` con `date = 2026-04-01` (= period.end + 1 day) y `amount = 95000.00 CLP`
**And** Beancount nativo valida: si `opening + Σ tx ≠ closing` → `bean-check` falla en esta directiva (cumple FR22-FR24)

---

**AC6 — Override con justificación (FR25)**

**Given** la `Balance` directive falla porque `opening + Σ tx ≠ closing` (extraction error de Gemini, o transacción ausente)
**When** el contador override desde el frontend (Story 9.9) con justificación
**Then** la importación se re-ejecuta convirtiendo la `Balance` en una pareja `pad ... Equity:Reconciliation:Discrepancias` + `balance` con metadata:
```beancount
2026-04-01 pad Liabilities:EAG:TC:... Equity:Reconciliation:Discrepancias
  override_justification: "Cartola PDF estuvo cortada — falta una página"
  override_user: "contador@ammy.cl"
  override_at: "2026-05-01T10:30:00Z"
2026-04-01 balance Liabilities:EAG:TC:... 95000.00 CLP
```
**And** `bean-check` ahora pasa
**And** la cuenta `Equity:Reconciliation:Discrepancias` se abre en `accounts.beancount` si no existe (Story 9.1 + bootstrap deben preverla)

---

**AC7 — Idempotencia: re-procesar mismo staging file produce mismo output**

**Given** un staging file procesado una vez
**When** se procesa de nuevo (caso recovery)
**Then** el archivo `imports/cartolas/{slug}.beancount` resultante es bit-idéntico
**And** ningún side-effect persistente (no append a categorization log, no commit duplicado)

---

**AC8 — Promoción del staging a archivo definitivo**

**Given** `extract()` completó OK + `bean-check` pasó (Story 9.9 gate)
**When** la promoción se dispara
**Then** se escribe `ledger/imports/cartolas/{bank_slug}-{account_last4}-{YYYY-MM}.beancount` con todas las directivas
**And** se borra el staging file `_staging/{batch_id}.cartola.json`
**And** se commitea + pusheó al repo con mensaje `[importer-cartola] {bank_slug} {YYYY-MM}: +N tx`

---

**AC9 — Hook con CategorizationService (DEP 9.7)**

**Given** la inyección `category_predictor` puede ser un mock noop (v1) o el `CategorizationService` real (post-9.7)
**When** `extract()` corre
**Then** llama a `category_predictor.predict(description, amount, bank_account_id) → (category_account, match_source)`
**And** si predictor es noop: retorna `("Expenses:EAG:Suspense", "pending")` para todas las tx → flag `!` en cada Transaction
**And** si predictor es real (post-9.7): retorna categorías reales con flag `*` o `!` según threshold

---

## Tasks / Subtasks

- [ ] Task 1: Esqueleto de la clase
  - [ ] Crear `pipeline/importers/cartola_pdf_importer.py` con clase `CartolaPdfImporter(beangulp.Importer)`
  - [ ] Métodos vacíos: `identify`, `account`, `extract` con docstrings
  - [ ] Verificar que `pip install beangulp` instala correctamente

- [ ] Task 2: `BankAccountResolver` (sin Supabase)
  - [ ] Crear `pipeline/importers/bank_account_resolver.py`
  - [ ] Constructor lee `accounts.beancount` (via `beancount.loader`) — NO Supabase
  - [ ] Index in-memory por metadata `bank_account_id` (string) → account name Beancount completo + `account_type` + `currency`
  - [ ] Método `resolve(bank_account_id) → str` retorna el account name Beancount completo
  - [ ] Cache invalidation: el index se reconstruye cuando cambia `accounts.beancount` (signal del file watcher de Story 9.2 — endpoint admin para invalidar manual también es válido)

- [ ] Task 3: `_build_postings(account_target, category_account, amount, currency, account_type)`
  - [ ] Lógica de signo por tipo (AC4)
  - [ ] Para `tarjeta_credito` (Liability) outflow → `+|amount|` Liability, `+|amount|` Expense
  - [ ] Para `linea_credito` (Liability) outflow → mismo patrón
  - [ ] Para `cta_corriente` (Asset) outflow → `-|amount|` Asset, `+|amount|` Expense
  - [ ] Para `cta_corriente` (Asset) inflow → `+amount` Asset, `+amount` Income (resolución de Income vs Expense por signo)
  - [ ] Para `cta_inversiones` (Asset): mismo patrón que cta_corriente; el contador después reconcilia el detalle
  - [ ] Tests unitarios para los 4 tipos × 2 signos = 8 casos

- [ ] Task 4: `extract()` full
  - [ ] Loop sobre `transactions[]`
  - [ ] Para cada tx: predict category + build postings + crear `data.Transaction`
  - [ ] Al final: agregar `data.Balance` con `date = period.end + 1 day`, `account = account_target`, `amount = closing`
  - [ ] Manejar TC: skip opening balance assertion (TC opening es deuda preexistente; trust prior batch); solo emitir closing

- [ ] Task 5: Override pad+balance (AC6)
  - [ ] Función `convert_balance_to_pad(entries, override_justification, override_user)` que toma las entries originales y reemplaza la `Balance` por `pad`+`balance` con metadata
  - [ ] Esta función la invoca Story 9.9 desde el endpoint `/validate-balance/{batch_id}` cuando el contador override
  - [ ] La cuenta `Equity:Reconciliation:Discrepancias` debe estar abierta en `accounts.beancount` (agregar al bootstrap de 9.1 si no está)

- [ ] Task 6: Promoción + commit (AC8)
  - [ ] Función `promote(batch_id) → file_path` que:
    1. Lee staging JSON
    2. Llama `extract` para obtener entries
    3. Serializa a Beancount con `beancount.parser.printer.format_entry`
    4. Escribe a `imports/cartolas/{slug}.beancount` (slug = `{bank}-{last4}-{YYYY-MM}`)
    5. Borra staging
    6. `bean-check ledger/main.beancount` (gate)
    7. Si OK: `git add + commit + push`. Si KO: revertir, log error
  - [ ] Lock file `.import.lock` (mismo patrón que Story 9.4)

- [ ] Task 7: Tests
  - [ ] Unit: `_build_postings` (8 casos)
  - [ ] Unit: `extract` con fixture JSON canónico → entries esperadas
  - [ ] Unit: `Balance` directive con override → conversión a pad+balance
  - [ ] Integration: staging file → promoción → archivo final + bean-check OK
  - [ ] Idempotencia: ejecutar `promote` 2 veces seguidas (la segunda debería detectar que ya se commiteó y skip — TBD el mecanismo)

---

## Dev Notes

### Input autoritativo

`architecture-c4.md` §4.2 — esqueleto de la clase + decisiones de signo + override pad+balance. **El esqueleto del artifact es ilustrativo; el código real lo escribe el dev tras esta story.**

### Sign convention table (Beancount)

| Account root | Outflow (compra/cargo) | Inflow (pago/devolución) |
|---|---|---|
| `Assets` (cta_corriente, cta_inversiones) | posting negativo | posting positivo |
| `Liabilities` (TC, linea_credito) | posting positivo (deuda crece) | posting negativo (pago = deuda baja) |
| `Expenses` (categoría) | posting positivo (siempre) | n/a |
| `Income` (categoría) | n/a | posting negativo (Income con signo invertido en Beancount) |

Nota Beancount: Income tiene signo invertido por convención. `1000 CLP` en Income = "se ingresó 1000 CLP" (positivo desde la perspectiva del titular, pero el posting es negativo).

### Balance directive — sintaxis exacta

```beancount
2026-04-01 balance Liabilities:EAG:TC:VisaInfinityEduardo-2150  95000.00 CLP
```

Beancount valida la suma del account a la fecha (start of day → 2026-04-01 inclusive de transactions del 2026-03-31).

### Categorización en v1

Esta story expone el hook (`category_predictor` injectable) pero NO implementa la lógica de smart_importer. Eso es Story 9.7. En v1 puede correr con un noop predictor que devuelve siempre `Suspense` + flag `!` (=pendiente).

### Sin Supabase — el resolver lee de `accounts.beancount`

Bajo decisión 2026-05-05 (eliminar Supabase del diseño c4), el `BankAccountResolver` parsea `accounts.beancount` al boot via `beancount.loader.load_file` y construye un index in-memory sobre metadata `bank_account_id`. Cache LRU innecesario — el archivo entero se carga una vez (~340 directivas, milisegundos) y se mantiene en memoria.

### `PRD-update needed`

Ver flags #2 (TC como Liabilities) y, indirectamente, #3 (categorización). NO bloquean. John actualiza PRD en sesión separada.

### Project structure

```
pipeline/importers/
  cartola_pdf_importer.py                  # NEW
  bank_account_resolver.py                 # NEW (lee accounts.beancount, no Supabase)
  category_predictor.py                    # NEW (interface; noop impl en v1, real en 9.7)
  README.md                                # NEW (runbook + diagrama de flujo)
ledger/imports/cartolas/
  _staging/                                # gitignored
  {bank}-{last4}-{YYYY-MM}.beancount       # output final
```

### Dependencies

Agregar a `backend/requirements.txt`:
```
beangulp>=0.2
```

### References

- [Source: architecture-c4.md §4.2 — Story 4.1b — JSON canónico → directivas]
- [Source: architecture-c4.md §2.1 + §2.5 — Naming convention + bank_accounts mapping]
- [Source: bob-x-moishe-epic9-2026-04-30.md — Q7 (TC como Liabilities) + ítem #9 sin-Supabase]
- [Source: 9-5-pdf-upload-gemini-json-canonico.md — staging contract]
- [Source: 9-6b-matching-cartola-laudus-discrepancias.md — story siguiente, motor matching]
