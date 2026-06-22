# Story 6.1: Wiring del promote a `reconcile_and_build` (el SEAM)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **contador del family office**,
I want que **validar una cartola bancaria la concilie contra Laudus/Beancount y me muestre solo las diferencias** (líneas que no coinciden con lo que ya cargó el contador),
so that **pueda revisarlas en el dashboard y aprobar cuáles anotar en Beancount, sin que el sistema re-contabilice automáticamente lo que Laudus ya tiene** (Laudus sigue siendo la fuente contabilizada y validada peso-por-peso vs el contador).

> **Modelo A (decisión Ary 2026-06-22):** la cartola **NO re-contabiliza**. El promote corre el matching cartola↔Laudus y registra las DIFERENCIAS en el JSONL que el dashboard 9.12 consume; no postea transacciones al ledger (eso duplicaría las cuentas de banco/TC que Laudus ya tiene y rompería el cuadre). La anotación en Beancount de una diferencia **aprobada** es el flujo de resolución del dashboard (**próxima story**, no 6.1). Ver sección "BLOCKER → RESUELTO" más abajo.

## Contexto (por qué esta story)

El motor de reconciliación **ya existe y está testeado** (Epic 9: Stories 9.6b + 9.10 + 9.12). Lo único que falta es **wirearlo al flujo de upload real**. Hoy, al promover una cartola, el código llama `importer.extract()` — la ruta "match perfecto" de 9.6a, **sin reconciliación**. Ningún código de producción invoca `reconcile_and_build` (confirmado por grep: solo aparece en tests). Esta story reemplaza ese SEAM.

> Cita del dev de 9.6b: *"No flipeé el `promote` de 9.6a para no cambiar su comportamiento ni romper sus tests — el cuándo corre la reconciliación es decisión del flujo de upload. Engine + loader + orquestador ya listos y testeados para wirear."*
> [Source: epics.md#Epic-6 → "Nota sobre el SEAM"]

**Decisión de diseño D1 — CERRADA (Ary 2026-06-20): Opción A, gate estricto, todo-o-nada, mismo flujo para TC y cuenta corriente.** Una cartola con **cualquier** discrepancia bloqueante NO se promueve al ledger hasta que el contador resuelva todas vía el dashboard 9.12. O no se contabiliza nada (cartola bloqueada) o se contabiliza todo (cartola limpia). [Source: epics.md#Epic-6 → "Decisión de diseño D1"]

## Acceptance Criteria (modelo A — reconciliar sin postear)

**AC1 — Validar una cartola la concilia contra Laudus (reemplaza el promote que posteaba). ✅**
Given una cartola staged (`{batch_id}.cartola.json`) lista para validar,
When se llama `PATCH /api/v1/cartolas/{batch_id}/validate-balance`,
Then el flujo arma `CartolaLine[]` desde el canónico staged, carga `load_laudus_entries()` para el período/cuenta, corre `reconcile_and_build()` (matching + FX vía `_meta/fx-bcch-eom.jsonl`) y se queda con las **discrepancias** (las entries beancount que el motor arma se **descartan** — modelo A no postea).
And NO se invoca `importer.extract()` ni se escribe ningún `.beancount` de cartola al ledger.

**AC2 — Las diferencias se registran (y se commitean) al JSONL. ✅**
Given el resultado del matching,
Then todas las discrepancias se appendean a `ledger/_meta/cartola-discrepancies.jsonl` (vía `append_discrepancy`, con dedup) y, si hubo ≥1, se commitea el JSONL (gateado por `IMPORTER_GIT_ENABLED`) — necesario porque el backend hace `git reset --hard` en cada refresh y sin commit las diferencias se perderían y el dashboard no las vería.

**AC3 — No se postea nada al ledger; se reporta el resumen. ✅**
Given el matching,
Then el endpoint devuelve `{status: "reconciled", differences: N, blocking: B, matched: M, ...}` (200 OK). `perfect` no genera diferencia (coincide con Laudus); `value-mismatch`/`missing-in-cartola` cuentan como `blocking`. El staging se consume (extraído + reconciliado). NO se crea `imports/cartolas/*.beancount`.

**AC4 — El cuadre de extracción (9.9) se preserva como QA. ✅**
Given que `validate_balance` chequea `closing == opening + Σtx` (consistencia interna de la extracción de Gemini),
Then una discrepancia sin `override_justification` → 400 (la cartola no suma → reconciliar daría ruido); con `override_justification` (≥20 chars) → procede a conciliar igual. Bajo modelo A el override ya NO escribe `pad+balance` (no se postea) — solo habilita proceder.

**AC5 — `perfect` no se reporta; las diferencias sí. ✅**
Given una línea de cartola que coincide con un asiento Laudus (mismo monto/fecha/desc),
Then NO genera diferencia (Laudus ya la tiene contabilizada, no hay nada que revisar).
Given una diferencia (`value-mismatch`, `missing-in-laudus`, `missing-in-cartola`, `date/description/category-mismatch`, estados FX),
Then se registra en el JSONL para que el contador la revise en el dashboard 9.12.

**AC6 — Pre-2026 y USD igual que en el motor testeado (AC9 de 9.6b). ✅**
Given `period.start < 2026-01-01` → CLP-only (sin FX). Given USD con/ sin BCCh → el motor ya decide (FX implícita / `fx-bcch-missing`). Esta story solo wirea el motor para detección, no reimplementa su lógica.

**AC7 — Tests + sin regresiones. ✅**
Given el wiring, hay tests que cubren: perfect → 0 diferencias + no postea + staging consumido; `value-mismatch` y `missing-in-cartola` → bloqueantes; `missing-in-laudus` → no bloqueante; dedup al re-conciliar; integración por `validate_balance`. Suite completa sin regresiones nuevas (los 2 rojos de `test_fava_edit_validator` son pre-existentes — fallan en `HEAD` limpio, ajenos a este cambio).

### Fuera de scope de 6.1 (próxima story)

- **Aprobar una diferencia → anotarla en Beancount.** En el dashboard, aprobar (ej. un `missing-in-laudus` que el contador confirma como gasto real) debe escribir esa transacción en Beancount (vía `commit_reconciliation`/un writer + bean-check + git). El dashboard 9.12 ya tiene la UI de resolución + justificación; falta que la acción aprobada efectivamente anote en el ledger. **Esto es lo que Ary pidió como segunda mitad ("pida aprobación para anotarlas") y es la próxima story de Epic 6.**

## Tasks / Subtasks

- [x] **Task 1 — `reconcile_cartola()` (detección, sin postear)** (AC1, AC2, AC3, AC5)
  - [x] Nueva función `reconcile_cartola(batch_id, importer, ledger_root, *, ts)` en `pipeline/importers/reconcile.py`. NO modifica `promote()`/`extract()` de 9.6a (quedan como código vivo de sus tests; ahora sin consumidor en prod — ver Completion Notes).
  - [x] Dentro del lock: lee el canónico staged, resuelve `account_target` + `is_liability`, arma `CartolaLine[]` (`suggested_category=""` → evita `category-mismatch` espurio con Noop), carga `load_laudus_entries(root/imports/laudus, account, period.start, period.end)`.
  - [x] Corre `reconcile_and_build(...)` y **descarta las entries** (modelo A); se queda con `discrepancies`. `category_for=lambda cl: SUSPENSE_ACCOUNT` (las entries no se usan).
  - [x] Appendea las discrepancias al JSONL vía `append_discrepancy` (dedup) + commitea el JSONL si hubo ≥1 (gateado `IMPORTER_GIT_ENABLED`). Ruta vía `_discrepancies_path()` (replica el resolvedor del dashboard: `LEDGER_DISCREPANCIES` → `<root>/_meta/...`; no importa la capa API para no invertir la dependencia pipeline→backend).
  - [x] Consume el staging y devuelve `{status: "reconciled", differences, blocking, matched, new, git_commit_sha}`.

- [x] **Task 2 — Wirear `validate_balance` a `reconcile_cartola`** (AC1, AC3, AC4)
  - [x] En `cartolas/service.py`: conserva el cuadre de extracción (update opening/closing, `diff`, `BalanceDiscrepancy` 400 sin override, `OverrideJustificationTooShort`). Reemplaza la llamada a `promote(...)` por `reconcile_cartola(...)` (`ts = now_iso or now()`). Devuelve el resumen de reconciliación.
  - [x] Docstring actualizado. Bajo modelo A el override ya no escribe pad — solo habilita proceder pese al descuadre de extracción.

- [x] **Task 3 — Response schema + endpoint** (AC3)
  - [x] `ValidateBalanceResponse` → `status: Literal["reconciled"]` + `differences`, `blocking`, `matched`, `git_sha?`, `override`, `batch_id?`. El endpoint `validate_balance_endpoint` ya devuelve `ValidateBalanceResponse(**result)` → 200. (Handler de `BeanCheckFailed` queda inerte — ver Completion Notes.)

- [x] **Task 4 — Tests** (AC7)
  - [x] `backend/tests/test_reconcile_cartola.py` (6 tests): perfect→0 diferencias+no postea+staging consumido; `value-mismatch` bloqueante; `missing-in-cartola` bloqueante; `missing-in-laudus` no-bloqueante; dedup; integración por `validate_balance`.
  - [x] `backend/tests/test_validate_balance.py` actualizado a modelo A (cuadra→`reconciled`+no archivo; override→`reconciled` sin pad; removido `test_fallo_no_balance_no_se_misclasifica` — la ruta `BeanCheckFailed` ya no existe en este flujo).
  - [x] Suite completa: 537 passed, 1 xfailed, 2 fallos PRE-EXISTENTES (`test_fava_edit_validator`, fallan en `HEAD` limpio, ajenos). 0 regresiones nuevas.

## Dev Notes

### Arquitectura del flujo (estado actual → objetivo)

**Hoy (path de promote):**
```
PATCH /cartolas/{id}/validate-balance
  → service.validate_balance()           [cartolas/service.py:407]
      → update opening/closing en staging
      → diff = closing − (opening + Σtx)  [cuadre de EXTRACCIÓN]
      → promote(batch_id, importer, root, override)   [cartola_pdf_importer.py:216]
          → importer.extract()            ← SOLO parser "match perfecto", SIN reconciliación
          → render → bean-check → git commit
```

**Objetivo (6.1):**
```
  → validate_balance() [pasos 1-4 intactos]
      → reconcile_promote(batch_id, importer, root, ts=, override=)   [NUEVO en reconcile.py]
          → build CartolaLine[] desde staged
          → load_laudus_entries(imports/laudus, account, period.start, period.end)
          → reconcile_and_build(...) → entries, discrepancies
          → append_discrepancy(... ) SIEMPRE   → _meta/cartola-discrepancies.jsonl
          → si bloqueante (value-mismatch / missing-in-cartola): NO escribir, staging intacto, status "blocked"
          → si no: append Balance → render → bean-check → git commit → status "validated"
```

### Piezas existentes — REUSAR, no reescribir

| Pieza | Ubicación | Uso en 6.1 |
|---|---|---|
| `reconcile_and_build(...)` | [reconcile.py:101](pipeline/importers/reconcile.py#L101) | el orquestador; llamar tal cual |
| `process_match_result` (estados, `_BLOCKING`) | [reconcile.py:23,60](pipeline/importers/reconcile.py#L23) | ya define `_BLOCKING = {"value-mismatch","missing-in-cartola"}` |
| `load_laudus_entries(target_dir, account, start, end)` | [matching_engine.py:59](pipeline/importers/matching_engine.py#L59) | cargar asientos Laudus del período |
| `CartolaLine` dataclass | [matching_engine.py:29](pipeline/importers/matching_engine.py#L29) | construir desde `model.transactions` |
| `append_discrepancy(disc, path)` (dedup) | [discrepancy_writer.py:75](pipeline/importers/discrepancy_writer.py#L75) | appendear al JSONL |
| `promote()` (estructura lock/render/bean-check/git) | [cartola_pdf_importer.py:216](pipeline/importers/cartola_pdf_importer.py#L216) | **patrón a espejar**, NO modificar |
| `convert_balance_to_pad(...)` | [cartola_pdf_importer.py:177](pipeline/importers/cartola_pdf_importer.py#L177) | override 9.9 (pad+balance) |
| `render_entries`, `_slug`, `_build_postings` | [cartola_pdf_importer.py](pipeline/importers/cartola_pdf_importer.py) | render + nombre de archivo |
| `acquire_lock`, `bean_check`, `git_commit_push` | `pipeline/importers/laudus_run.py` | infra de promoción |
| `_ledger_root()` (resuelve `LEDGER_DIR`) | [laudus_run.py:37](pipeline/importers/laudus_run.py#L37) | raíz del ledger |

### Construcción de `CartolaLine`

`CartolaTransaction` (canónico) → `CartolaLine` (matching):
```python
CartolaLine(
    line_no=tx.line_no,
    date=tx.date,
    amount=tx.amount,        # firmado, en tx.currency
    currency=tx.currency,
    description=tx.description,
    suggested_category="",   # ← vacío con Noop; ver "Trampa" abajo
)
```
`category_for` se deriva del predictor: `category_for = lambda cl: importer.category_predictor.predict(cl.description, cl.amount, model.source.bank_account_id)[0]`. Con `NoopCategoryPredictor` esto devuelve `Expenses:EAG:Suspense`.

### 🚨 Trampa: `category-mismatch` espurio con Noop

`_classify` ([matching_engine.py:115](pipeline/importers/matching_engine.py#L115)) dispara `category-mismatch` cuando `cl.suggested_category and le.category_account and cl.suggested_category != le.category_account`. Si poblás `CartolaLine.suggested_category = "Expenses:EAG:Suspense"` (lo que devuelve Noop) **TODAS** las líneas matcheadas darían `category-mismatch` vs la categoría real de Laudus → inundación de discrepancias. **Solución:** dejar `suggested_category=""` mientras el predictor sea Noop (sin confianza). El posting real igual usa la categoría del predictor vía `category_for`. Cuando se wiree el categorizador real (futuro, fuera de scope), poblar `suggested_category` solo en predicciones confiables.

### 🚨 Anti-regresión #1: metadata de categorización (AC5)

`extract()` estampa en cada tx: `source`, `bank_account_id`, `batch_id`, `match_source`, `category_status`, `extraction_model`, `line` ([cartola_pdf_importer.py:138-147](pipeline/importers/cartola_pdf_importer.py#L138-L147)). En cambio `reconcile_and_build` estampa solo `source`, `bank_account_id`, `line` (+ `suggested_category`/FX) ([reconcile.py:155](pipeline/importers/reconcile.py#L155)). **Consumidores que se rompen sin la metadata completa:**
- `list_pending` → filtra `category_status ∈ (suggested, pending)` → sin él, **ninguna** cartola reconciliada aparece en `/categorizacion`.
- `bulk_confirm` → filtra `match_source != pending` y `batch_id` → sin ellos, no opera por batch.
- `current_match_source` / `current_category_status` en la respuesta de pending.

`compute_tx_id` (filename+lineno+narration+amount) y `update_category` (usa `meta["filename"]`/`bank_account_id` que beancount/reconcile sí setean) funcionan igual. **Acción:** estampar `category_status`, `match_source`, `batch_id`, `extraction_model` en las tx reconciliadas (Task 2).

> **Nota sobre el `flag`:** `reconcile_and_build` setea el flag por estado de matching (`*` perfect, `!` cualquier mismatch/FX). `extract()` lo setea por confianza de categoría. Son ejes distintos. `list_pending` filtra por `category_status` (NO por flag) → preservar `category_status` es suficiente para que la lista funcione. Documentar esta semántica en Completion Notes; no intentar reconciliar ambos flags en esta story.

### Paths del ledger (consistencia)

- **Discrepancias JSONL (Decisión 3):** reusar `_jsonl_path()` de [reconciliation/service.py:33-39](backend/app/api/v1/reconciliation/service.py#L33-L39) (`LEDGER_DISCREPANCIES` override → `LEDGER_DIR`/_meta → repo) en vez de hardcodear, así 6.1 escribe SIEMPRE donde el dashboard 9.12 lee.
- Resto de paths derivados del `root` que ya calcula `validate_balance` (`_ledger_root()`):
  - FX JSONL: `root/"_meta"/"fx-bcch-eom.jsonl"` (escrito por 9.10, [fx_bcch_eom.py:31](pipeline/importers/fx_bcch_eom.py#L31)).
  - Laudus dir: `root/"imports"/"laudus"` (escrito por el importer 9.4; el glob `*.beancount` ignora `_*`).

### Convención de signo (heredada de 9.6a, NO tocar)

Cuentas `Liabilities` (TC): se niega el signo (`target = -amount`, `Balance = -closing`); `Assets` tal cual. `_build_postings`/`build_usd_postings` ya lo manejan. El `is_liability` se deriva de `account_target.startswith("Liabilities")`. [Source: cartola_pdf_importer.py:7-18 docstring]

### TC = pasivo, dos estados (contexto, no acción)

Las TC son **pasivo**, no gasto, en el modelo de dos estados. Estado 1 (sin desglose de cartola de TC) = el reporte deja las TC como lump de Laudus (correcto hoy). La corrección plena estado 2 (desglose de cartola de TC, diseño de Valentina) está **DIFERIDA** y fuera de scope de 6.1. [Source: memoria `project_tc_pasivo_dos_estados`] — Para 6.1: una cartola de TC se reconcilia con el mismo flujo unificado que cuenta corriente (D1). Que el balance de TC quede negativo es esperado.

### Scope excluido (NO hacer en 6.1)

- Polish del dashboard 9.12 (historial, filtros UI, moneda, action-sets FX) → **Story 6.2**.
- Cierre de período "reconciliado completo" → **Story 6.3**.
- Cron de reconciliación programada / runner batch standalone → fuera de c4 (el trigger es el upload).
- Reconciliación de cartolas de inversión/custodios → diferida (invariantes no-aritméticos).
- Integración real de smart_importer/Gemini en el categorizador → seam de 9.7, sigue pendiente.
- Reconciliar el `flag` de matching con el `flag` de categorización.
[Source: epics.md#Epic-6 → "Scope excluido"]

### Testing standards

- Tests backend en `backend/tests/`, pytest. Correr con `PYTHONUTF8=1` en Windows (gotcha del proyecto). Ejemplo: `PYTHONUTF8=1 python -m pytest backend/tests/test_reconcile_integration.py -q`.
- Inyección: `validate_balance` acepta `ledger_root`, `importer`, `now_iso` para tests deterministas. `reconcile_promote` debe aceptar `ledger_root` y `ts` inyectables igual.
- bean-check real sobre el render (cargar con `beancount.loader`) es el gate de verdad para postings/balance — ver [test_reconcile_integration.py:30-33,89](backend/tests/test_reconcile_integration.py#L30-L33).
- `monkeypatch.delenv("IMPORTER_GIT_ENABLED", raising=False)` para que el commit sea no-op local.

### Project Structure Notes

- Motor de reconciliación: `pipeline/importers/` (reconcile, matching_engine, fx_calculator, discrepancy_writer, cartola_pdf_importer). **Recomendado** poner `reconcile_promote` en `reconcile.py` (cohesión con el orquestador).
- API: `backend/app/api/v1/cartolas/` (router, service, schemas). `validate_balance` vive en `service.py`.
- Dashboard que consume el JSONL: `backend/app/api/v1/reconciliation/` + `ReconciliationPage` (frontend) — NO se toca en 6.1 (es 6.2).
- Sin Supabase, sin Sheets, sin feature flags (cleanup c4 9.16). Beancount es la fuente única.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic-6-Reconciliación-Mensual] — goal, D1 cerrada, flujo resultante 6.1, scope, FR mapping (FR32/FR33), NFR4.
- [Source: _bmad-output/coordination/epic6-reconciliacion-kickoff-2026-06-20.md] — handoff, "verificar el SEAM como primer paso".
- [Source: pipeline/importers/reconcile.py] — `reconcile_and_build`, `process_match_result`, `_BLOCKING`, `commit_reconciliation`.
- [Source: pipeline/importers/matching_engine.py] — `match`, `load_laudus_entries`, `CartolaLine`, `LaudusEntry`, 7 estados, tolerancias (±3 días, sim ≥0.85), `USD_FX_EPOCH`.
- [Source: pipeline/importers/cartola_pdf_importer.py] — `promote` (patrón), `extract` (metadata a preservar), `convert_balance_to_pad`, `_build_postings`, `render_entries`, `_slug`, convención de signo.
- [Source: backend/app/api/v1/cartolas/service.py#validate_balance] — flujo de promoción + override 9.9.
- [Source: backend/app/api/v1/reconciliation/service.py] — `_jsonl_path`, `BLOCKING_STATES`, `ACTIONS_BY_STATE` (cómo 9.12 lee/resuelve).
- [Source: backend/app/api/v1/transactions/service.py#list_pending] — contrato de metadata de categorización (anti-regresión AC5).
- [Source: backend/tests/test_reconcile_integration.py] — patrón de test del motor + ledger root mínimo.
- [Source: memoria project_tc_pasivo_dos_estados, project_epic6_reconciliacion_next] — TC pasivo, D1 Opción A.

## Decisiones (resueltas 2026-06-22, Ary)

1. **Shape de respuesta `blocked`** ✅ — `{status: "blocked", blocking: N, discrepancies: M, batch_id}` con **200 OK** (resultado válido, no error). En 6.1 solo se devuelve el shape; el render "cartola bloqueada, N por resolver" + deep-link al dashboard es 6.2.
2. **Metadata `match_source`/`category_status` (AC5)** ✅ — **post-procesar en `reconcile_promote`**, NO enriquecer `reconcile_and_build` (mantiene intactos los tests de 9.6b). Tras `reconcile_and_build`, recorrer las `Transaction` emitidas y, por cada una, re-derivar `(category_account, match_source, flag)` con `importer.category_predictor.predict(...)` keyed por `line` (= `cl.line_no`), y estampar en `meta`: `match_source`, `category_status` (mismo mapeo que `extract`: `pending` si `match_source=="pending"`, `confirmed` si `flag=="*"`, si no `suggested`), `batch_id`, `extraction_model` (= `model.extraction.model`). El `flag` de la tx lo deja el motor (eje de matching); `category_status` es el que consume `list_pending` (ver "Nota sobre el flag").
3. **`LEDGER_DISCREPANCIES` / ruta del JSONL** ✅ — **reusar el resolvedor de la reconciliation service** (`backend/app/api/v1/reconciliation/service.py` → `_jsonl_path()`) en vez de hardcodear `root/_meta/...`, para escribir SIEMPRE donde el dashboard 9.12 lee, respete o no `LEDGER_DISCREPANCIES`/`LEDGER_DIR` en Render. Importarlo (o factorizar un helper compartido si el import cruzado incomoda). Misma lógica aplica al FX JSONL: si hay duda, derivar de la misma raíz que resuelve la reconciliation service.
4. **Validación end-to-end** ✅ — 6.1 cierra con **tests + un fixture de cartola real** (canónico staged de muestra). La corrida en vivo con una cartola subida por el contador es la aceptación a nivel epic (dependencia ya anotada) y queda como handoff a Ary post-merge, NO bloquea el DONE de la story.

## ✅ BLOCKER RESUELTO (2026-06-22) — Ary eligió Opción A (reconciliar sin postear)

**Decisión de Ary:** *"La A. Que muestre solo las diferencias y pida aprobación para anotarlas en Beancount."* → la cartola NO re-contabiliza; concilia y reporta diferencias. La anotación-on-aprobación es la próxima story. La implementación de 6.1 quedó bajo este modelo (ver ACs reescritos arriba). El detalle del problema original se conserva abajo para contexto histórico.

---

**Síntoma (original):** wirear `reconcile_and_build` al promote tal cual lo describe el epic produciría **doble conteo** de la cuenta de banco/TC y rompería la directiva `Balance` de cierre en bean-check.

**Evidencia verificada contra el ledger vivo:**
- `ledger/main.beancount` incluye **simultáneamente** `imports/laudus/*.beancount` **y** `imports/cartolas/*.beancount`.
- `imports/laudus/` tiene los JEs mensuales reales (2021→hoy); Laudus **postea a las cuentas de banco/TC** (ej. `Liabilities:EAG:TC:VisaInfinity-430005`).
- `imports/cartolas/` está **vacío** (`.gitkeep` + `_init`): **ninguna cartola se promovió nunca a prod** → el SEAM jamás corrió end-to-end → el doble conteo nunca se manifestó.
- `reconcile_and_build` emite una `Transaction` por cada línea de cartola **matcheada** (estado `perfect`, `date-mismatch`, etc., `emit=True`). Esa tx postea al MISMO account que el JE Laudus ya presente en `imports/laudus/`.

**Por qué rompe:** `data.Balance` asierta el saldo TOTAL del account (todos los archivos incluidos). Con Laudus + cartola posteando al mismo account, el saldo = `laudus + cartola` ≠ `sign·closing` → bean-check rojo. El análisis de D1 ("Σtx emitidas = closing − opening → Balance válida") solo contempla el cuadre INTERNO de la cartola, no que `imports/laudus` también alimenta el account. **El mismo latente existe en el `promote()`/`extract()` de 9.6a — nunca se ejecutó en prod, por eso no se vio.**

**Choca con la base del proyecto:** beancount (derivado de Laudus) ya está validado peso-por-peso vs el contador. Re-postear las líneas de cartola encima **corrompería** ese cuadre (y es justo el tipo de doble conteo que la auditoría de Valentina está investigando).

**Opciones (necesito tu decisión, Ary):**
- **(A) Cartola NO re-contabiliza; solo reconcilia (recomendada).** El promote corre el matching y **appendea solo discrepancias** al JSONL; NO postea transacciones de cartola al ledger ni asierta `Balance` de cartola (Laudus sigue siendo el contabilizado y validado). Gate D1 se mantiene a nivel de "hay discrepancias bloqueantes → cartola marcada como no-conciliada". Cero doble conteo, no toca el cuadre validado. **Contradice el texto literal del epic** ("las líneas limpias se contabilizan") → habría que reformular el epic.
- **(B) Cartola supersede a Laudus para ese account+período.** Al promover, remover/comentar los JEs Laudus matcheados de `imports/laudus/` y postear la cartola. Mantiene el `Balance`. **Costoso y riesgoso:** muta archivos Laudus, rompe el audit trail Laudus↔Beancount, toca el cuadre validado.
- **(C) Cuentas cartola separadas de Laudus** (subcuenta/marcador) para que no colisionen. Cambio de modelo de cuentas grande; probablemente sobredimensionado.

**Mi recomendación: (A).** Es coherente con "Laudus es la fuente contabilizada y validada"; el valor de la cartola es *detectar discrepancias*, no re-postear. Implica reformular el goal de Epic 6 (reconciliación = detección, no re-contabilización) — decisión de PM/Ary, no de dev.

**Estado del código (escrito, NO mergeado, depende de la decisión):** `reconcile_promote` + `_stamp_category_metadata` + `_discrepancies_path` en `reconcile.py`; wiring en `validate_balance`; schema `blocked` en `schemas.py`. Si la decisión es (A), `reconcile_promote` se simplifica fuerte (no render, no Balance, no commit de `.beancount`; solo discrepancias + estado). Tests aún no escritos (esperando la decisión para no testear el comportamiento equivocado).

### Review Findings (code-review 2026-06-22, 3 capas adversariales)

Revisión: Blind Hunter + Edge Case Hunter + Acceptance Auditor. Núcleo de modelo A correcto y testeado (AC1-AC7 verificados); sin violaciones CRITICAL/HIGH del intent "reconciliar sin postear". Triage: 3 patch, 4 defer, 7 dismiss.

- [x] [Review][Patch] `matched` cuenta de más / puede ser negativo cuando una línea genera 2+ discrepancias [pipeline/importers/reconcile.py:303-304] — un soft-mismatch (date/description-mismatch) sobre una línea USD que además dispara estado FX (`fx-out-of-tolerance`/`fx-bcch-missing`/`fx-implausible`) appendea 2 discrepancias, ambas con el mismo `cartola.line_no` (reconcile.py:88,94). La fórmula `len(transactions) − len(discrepancias con line_no)` resta esa línea dos veces → `matched` subestimado, posible negativo, retornado tal cual a la API. APLICADO: dedup por `line_no` (set) antes de restar.
- [x] [Review][Patch] El commit del JSONL usa `if discrepancies:` en vez de `if new:` [pipeline/importers/reconcile.py:306] — al re-reconciliar un batch cuyas discrepancias ya estaban escritas, `append_discrepancy` dedup deja `new==0` pero `discrepancies` no vacío → entra al `git_commit_push` igual. APLICADO: `if new:`.
- [x] [Review][Patch] Falta test de regresión para la trampa `category-mismatch` espurio [backend/tests/test_reconcile_cartola.py] — APLICADO: `test_match_con_categoria_laudus_distinta_no_genera_category_mismatch` (línea matcheada con categoría Laudus distinta → 0 diferencias).
- [x] [Review][Defer] TOCTOU: el staging se lee fuera del lock en `reconcile_cartola` [pipeline/importers/reconcile.py:266] — deferred, concurrencia poco probable. Dos `validate_balance` casi-simultáneos del mismo batch: el 1º hace `unlink`, el 2º ya pasó el `staging.exists()` de validate_balance pero llega al `read_text` con el archivo borrado → `FileNotFoundError` → 500 en vez de 404.
- [x] [Review][Defer] Lock retenido durante el `git push` [pipeline/importers/reconcile.py:285-313] — deferred, patrón pre-existente (igual que `promote`/`commit_reconciliation`). Un push lento/colgado bloquea otros importers hasta el timeout del lock. El lock se libera en `finally` (sin leak permanente).
- [x] [Review][Defer] Si `LEDGER_DISCREPANCIES` apunta fuera de `root.parent`, `_rel` devuelve solo el basename [pipeline/importers/reconcile.py:276] — deferred, edge de config (el override no se usa en prod). `git add <basename>` no stagea el archivo real → discrepancias nunca commiteadas → se pierden en el `git reset --hard`. Con el override sin setear (caso prod), `disc_path` cae bajo `root.parent` y `_rel` funciona.
- [x] [Review][Defer] Cartola con `transactions=[]` y Laudus con asientos → muro de `missing-in-cartola` bloqueantes [pipeline/importers/reconcile.py] — deferred, comportamiento de diseño modelo A. Una extracción vacía (página sin movimientos) produce una pared de discrepancias bloqueantes en vez de rechazarse upfront. No crashea.

**Dismissed (7):** import `Decimal` "sin uso" (falso positivo — se usa en service.py:440,446); `new` no surfaceado en la respuesta (correcto — `differences`=total es la semántica correcta para "esta cartola tiene N diferencias"); staging orphan si `reconcile_and_build` lanza (aceptable — preserva para retry); drift semántico del flag `override` (consistente bajo modelo A); test `test_fallo_no_balance_no_se_misclasifica` borrado (correcto — la ruta bean-check ya no existe en este flujo); divergencia `_discrepancies_path` vs `_jsonl_path` por la rama `LEDGER_DIR` (correcto-por-diseño — la función recibe `ledger_root` como parámetro, el dashboard no; en prod ambos resuelven al mismo archivo vía `_ledger_root()`); `staging.unlink` corre siempre en perfect (intencional — cartola consumida).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m]

### Debug Log References

- 2026-06-22: investigación del SEAM → BLOCKER de doble conteo. Verificado contra el ledger vivo: `main.beancount` incluye laudus+cartolas a la vez; `imports/cartolas/` vacío; el promote/extract nunca corrió en prod (por eso el latente nunca se vio). HALT → Ary eligió Opción A.
- 2026-06-22: implementado modelo A. Tests `test_reconcile_cartola.py` (6) + `test_validate_balance.py` (actualizado) verdes. Suite: 537 passed / 1 xfailed / 2 fallos pre-existentes (`test_fava_edit_validator::test_invalid_edit_is_reverted_and_logged` + `::test_atomic_restore_uses_snapshot_bytes`) — confirmados pre-existentes corriendo en `HEAD` (90c085d) con mis cambios stasheados.

### Completion Notes List

- **Modelo A:** `reconcile_cartola()` (nuevo en `reconcile.py`) concilia cartola↔Laudus y registra diferencias en el JSONL; NO postea al ledger. `validate_balance` lo llama tras el cuadre de extracción (9.9, conservado como QA). Las entries que `reconcile_and_build` arma se descartan (no se contabilizan). `perfect` no genera diferencia; `value-mismatch`/`missing-in-cartola` cuentan como `blocking`.
- **JSONL commiteado** en `reconcile_cartola` (no solo escrito a disco): el backend hace `git reset --hard` en cada refresh → sin commit las diferencias se perderían y el dashboard 9.12 no las vería. Gateado por `IMPORTER_GIT_ENABLED` (no-op en local/tests).
- **`category-mismatch` espurio evitado:** `CartolaLine.suggested_category=""` (con `NoopCategoryPredictor` toda categoría es `Suspense`; poblar suggested_category dispararía category-mismatch vs la categoría real de Laudus en cada línea).
- **AC5 de metadata de categorización (de la versión posteadora) quedó MOOT:** bajo modelo A no se postean transacciones de cartola → no hay nada que categorizar desde cartolas → `/categorizacion` no se toca. Se descartó `_stamp_category_metadata`.
- **Código que quedó sin consumidor en prod (NO borrado — surgical):** `cartola_pdf_importer.promote()` + `convert_balance_to_pad()` + `CartolaPdfImporter.extract()` ya no los llama ningún flujo de producción (modelo A no postea cartolas). Sus tests (`test_cartola_pdf_importer.py`) siguen verdes. Igual el handler `except BeanCheckFailed` del router y la excepción `BeanCheckFailed` (ya no se levanta desde `validate_balance`). Candidatos a limpieza en una story de cleanup, fuera de scope acá.
- **PRÓXIMA STORY (lo segundo que pidió Ary):** "aprobar una diferencia → anotarla en Beancount" — wirear la resolución del dashboard 9.12 (`resolve()` + `commit_reconciliation`/writer) para que aprobar un `missing-in-laudus` (gasto real que falta) escriba esa transacción al ledger. El epic 6 debería reformular su goal ("reconciliación = detección + anotación-on-aprobación", no "re-contabilización automática").
- **Validación end-to-end con cartola real:** handoff a Ary post-merge (Decisión 4). Los tests usan fixtures sintéticos; la convención de signo cartola↔Laudus real se valida ahí.

### File List

- `pipeline/importers/reconcile.py` (MODIFICADO — `reconcile_cartola`, `_discrepancies_path`, `import os`)
- `backend/app/api/v1/cartolas/service.py` (MODIFICADO — `validate_balance` llama `reconcile_cartola`; docstring)
- `backend/app/api/v1/cartolas/schemas.py` (MODIFICADO — `ValidateBalanceResponse` → `reconciled` + differences/blocking/matched)
- `backend/tests/test_reconcile_cartola.py` (NUEVO — 6 tests de detección)
- `backend/tests/test_validate_balance.py` (MODIFICADO — actualizado a modelo A; removido un test de la ruta bean-check ya inexistente)

## Change Log

| Fecha | Cambio |
|---|---|
| 2026-06-22 | Story creada (bmad-create-story) bajo el supuesto posteador del epic. |
| 2026-06-22 | dev-story: detectado doble conteo cartola vs `imports/laudus/*` (HALT). Ary eligió Opción A (reconciliar sin postear). Reescrito a modelo A: `reconcile_cartola` (detección, sin postear, JSONL commiteado), `validate_balance` rewired, schema `reconciled`. 6 tests nuevos + 9.9 tests actualizados. 537 passed, 0 regresiones nuevas (2 rojos pre-existentes en fava_edit_validator). Status → review. Próxima story: aprobar diferencia → anotar en Beancount. |
