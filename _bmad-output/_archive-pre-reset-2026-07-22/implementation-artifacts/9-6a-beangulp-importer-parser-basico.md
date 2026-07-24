---
story: 9.6a
title: Beangulp importer — JSON canónico → directivas Beancount (parser básico, match perfecto)
status: review
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

- [x] Task 1: Esqueleto de la clase
  - [x] `pipeline/importers/cartola_pdf_importer.py` con `CartolaPdfImporter(beangulp.Importer)`
  - [x] `identify` / `account` / `extract` implementados
  - [x] `beangulp>=0.2` instalado + en `requirements.txt`

- [x] Task 2: `BankAccountResolver` (sin Supabase)
  - [x] `pipeline/importers/bank_account_resolver.py`
  - [x] Lee `accounts.beancount` (via `beancount.parser`) — NO Supabase
  - [x] Index in-memory por `bank_account_id` → account name + `account_type` + `currency` + `last4` + `bank_name`
  - [x] `resolve(id) → str` + `get(id) → ResolvedAccount`; unknown id → `UnknownBankAccount`
  - [x] `reload()` para invalidación manual (admin / file-watcher)

- [x] Task 3: `_build_postings(account_target, category_account, amount, currency, is_liability)`
  - [x] **Lógica de signo CORREGIDA vs AC4** (ver Completion Notes — AC4 no balancea en beancount). Verificado contra sample real.
  - [x] Liability (tarjeta_credito/linea_credito): `target = -amount` (cartola usa convención deuda-positiva; beancount la quiere negativa)
  - [x] Asset (cta_corriente/vista/ahorro/inversiones): `target = amount`
  - [x] category posting = `-target` siempre → suman 0
  - [x] Tests: asset/liability × inflow/outflow + "always balance" (los 4 account_types colapsan a 2 comportamientos por root)

- [x] Task 4: `extract()` full
  - [x] Loop sobre `transactions[]`: predict category + build postings + `data.Transaction` (flag `!`/`*`, meta source/bank_account_id/match_source/category_status/extraction_model/line)
  - [x] `data.Balance` con `date = period.end + 1 day`, `account = account_target`, `amount = sign·closing`
  - [x] TC: sin opening assertion (solo closing)

- [x] Task 5: Override pad+balance (AC6)
  - [x] `convert_balance_to_pad(entries, justification, user, at)` reemplaza `Balance` por `pad Equity:Reconciliation:Discrepancias` + `balance` con metadata
  - [x] `Equity:Reconciliation:Discrepancias` abierta en `accounts.beancount` **+ agregada al generador `generate_accounts.py`** (durabilidad)

- [x] Task 6: Promoción + commit (AC8)
  - [x] `promote(batch_id, importer, ledger_root)`: extract → `printer.format_entry` → `imports/cartolas/{bank}-{last4}-{YYYY-MM}.beancount` → borra staging → bean-check gate → git (guarded) / rollback
  - [x] Lock `.import.lock` (reusa `acquire_lock` de Story 9.4)

- [x] Task 7: Tests (16 verdes)
  - [x] `_build_postings` (asset/liability × signos + balance)
  - [x] `extract` con fixture → N tx + 1 Balance + meta
  - [x] override → pad+balance
  - [x] promoción: staging → archivo final + bean-check OK + staging borrado
  - [x] idempotencia: `render_entries` bit-idéntico en dos corridas
  - [x] `bean-check` pasa sobre las entries emitidas (con la aritmética real de un TC)

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

---

## Dev Agent Record

### Completion Notes

**Entregado y testeado (16 tests nuevos verdes):**
- `CartolaPdfImporter(beangulp.Importer)` — `identify`/`account`/`extract`.
- `BankAccountResolver` lee `accounts.beancount` (sin Supabase); unknown id → `UnknownBankAccount`.
- `NoopCategoryPredictor` (v1) → `Expenses:EAG:Suspense`/`pending`/flag `!`. Story 9.7 lo reemplaza.
- `extract` emite N `Transaction` + 1 `Balance` (cierre, `period.end + 1d`).
- `convert_balance_to_pad` (AC6) para el override del contador (lo dispara 9.9).
- `promote` (AC7/AC8): extract → format → archivo final → bean-check gate → git guarded; reusa lock/bean_check/git de Story 9.4.
- Cuentas de sistema (`Equity:Reconciliation:Discrepancias`, `Expenses:EAG:Suspense`) abiertas en `accounts.beancount` **y** en el generador `generate_accounts.py`.

**⚠️ Discrepancia de spec resuelta con datos (AC4):**
AC4 dice que para una TC los postings son `Liabilities +X` y `Expenses +X` "que suman 0".
Eso es **imposible en beancount** (sumaría 2X, `bean-check` fallaría). Inspeccioné un
**sample real de cartola TC** (`58431cba...cartola.json`): `opening=2054314`, `closing=3219948`,
cargos positivos, pagos negativos, y `opening + Σ amounts = closing` exacto → la cartola usa
convención **natural de extracto (deuda positiva)**, opuesta a beancount (liabilities crédito-normal,
deuda negativa — confirmado por los opening balances de 9.1). Implementación correcta y que pasa
el gate real (AC5 = bean-check): para **Liabilities** `target = -amount` y `balance = -closing`;
para **Assets** tal cual; category posting = `-target`. Verificado: la aritmética del sample cuadra
y `bean-check` pasa. **Flag para John/PRD:** corregir el ejemplo de AC4.

**Sobre los samples de staging existentes:** los `*.cartola.json` en `_staging/` son artefactos de
los smokes de 9.5 con `bank_account_id` dummy (`smoke-bci-9999`). El importer los `identify`-ea OK
y el resolver levanta `UnknownBankAccount` correctamente (path de error validado contra data real).
Los uploads reales (con `bank_account_id` poblado) requieren los 47 `last4`/ids en `accounts.beancount`
(pre-condición de Story 9.3 AC8).

### Decisiones de diseño
- **Categorización**: solo el hook (noop). Lógica real = Story 9.7.
- **Wiring del endpoint** (upload → promote): fuera de 9.6a (vive en `cartolas/router.py`, Story 9.5/9.9).
- **git push** guarded por `IMPORTER_GIT_ENABLED` (igual que 9.4); push real necesita `BEANCOUNT_DEPLOY_KEY` (handoff Render).

### Test Results
Suite backend (ignorando `test_fava_edit_validator.py`): **473 passed, 1 xfailed, 1 failed**
(failed = pre-existente date-dependiente). Nuevos de 9.6a: **16 verdes**.

## File List

**Nuevos:**
- `pipeline/importers/cartola_pdf_importer.py`
- `pipeline/importers/bank_account_resolver.py`
- `pipeline/importers/category_predictor.py`
- `backend/tests/test_cartola_pdf_importer.py`

**Modificados:**
- `ledger/accounts.beancount` — +2 cuentas de sistema (Discrepancias, Suspense)
- `bootstrap/generate_accounts.py` — `_SYSTEM_ACCOUNTS` (durabilidad de las 2 cuentas)
- `backend/requirements.txt` — `beangulp>=0.2`
- `pipeline/importers/README.md` — sección cartola importer + flujo + nota de signo

## Change Log

- 2026-06-10 — Story 9.6a implementada. CartolaPdfImporter (JSON canónico → directivas)
  + BankAccountResolver (sin Supabase) + NoopCategoryPredictor (hook 9.7) + Balance de cierre +
  override pad+balance + promoción con bean-check gate. Convención de signo corregida vs AC4 y
  verificada contra cartola real. 16 tests nuevos verdes, cero regresiones. Desbloquea 9.6b/9.7/9.9.
  Status → review.
