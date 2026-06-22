# Story 6.3: Aprobar una diferencia → anotarla en Beancount

<!-- Renumerada de 6.2 → 6.3 (2026-06-22): la story de desglose TC USD pasó a 6.2 (prioridad) porque
     ~50% de las cartolas reales son estados internacionales en USD que hoy no se reconcilian. Esta
     story (anotación CLP) sigue válida, una posición después. -->

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **contador del family office**,
I want que **al aprobar una diferencia de reconciliación en el dashboard (una línea de cartola que confirmo como gasto real ausente de Laudus), el sistema escriba esa transacción en Beancount**,
so that **la diferencia aprobada quede contabilizada en el ledger (la fuente única) y desaparezca del dashboard, sin que yo tenga que editar archivos `.beancount` a mano**.

> **Modelo A (heredado de 6.1):** la cartola **NO** re-contabiliza al validarse — solo detecta diferencias. Esta story cierra el lazo: **aprobar una diferencia la anota**. Es la 2da mitad literal de lo que pidió Ary: *"Que muestre solo las diferencias y pida aprobación para anotarlas en Beancount."*

## Contexto (por qué esta story)

6.1 entregó la **detección**: validar una cartola corre el matching cartola↔Laudus y appendea las diferencias a `cartola-discrepancies.jsonl`. El dashboard 9.12 ya las muestra y ya tiene la UI de resolución (acción + justificación). **Pero `resolve()` hoy solo appendea una línea de resolución al JSONL** (audit trail) — la discrepancia desaparece del dashboard pero **nada se escribe al ledger**. El re-emit al `.beancount` quedó explícitamente como SEAM pendiente:

> Cita de 9.12 Completion Notes: *"Re-emit .beancount sigue siendo seam de 9.6b (se activa con el wiring del upload)."*
> Cita de `reconciliation/service.py:resolve()` docstring: *"El re-emit del .beancount por acción se apoya en el seam de 9.6b (`commit_reconciliation`), que se activa con el wiring del upload de cartolas."*

Esta story conecta ese seam **para el caso de anotación real**: `missing-in-laudus` aprobado como gasto genuino.

## Scope — qué acción anota, y por qué solo esa

Bajo modelo A, Laudus (`imports/laudus/*`) ya está en el ledger. El significado de "aprobar" depende del estado:

| Estado | Acción de aprobación | ¿Escribe al ledger? | En scope 6.2 |
|---|---|---|---|
| `missing-in-laudus` (cartola tiene la línea, Laudus no) | `confirm-cartola-only` | **SÍ** — gasto real que falta → anotar nueva tx | ✅ **CORE** |
| `missing-in-cartola` (Laudus tiene, cartola no) | `confirm-laudus-only` | NO — Laudus ya está posteado, solo se cierra | ✅ (cierra sin write, comportamiento actual) |
| `value-mismatch` | `accept-cartola` | requeriría **editar** el asiento Laudus existente | ❌ **DIFERIDO** (mutar `imports/laudus/*`, riesgoso) |
| `date/description/category-mismatch` | `accept-cartola-*` | requeriría **editar** el campo del asiento Laudus | ❌ **DIFERIDO** |
| cualquiera | `escalate` | NO — no cierra, queda pendiente | ✅ (comportamiento actual) |
| cualquiera | `accept-laudus*` / variantes que mantienen Laudus | NO — Laudus ya está, solo se cierra | ✅ (comportamiento actual) |

**Por qué solo `missing-in-laudus`/`confirm-cartola-only` escribe:** es el único caso donde aprobar significa *agregar* una transacción nueva (append puro, sin tocar lo existente). Las acciones `accept-cartola*` sobre estados de mismatch implican **modificar un asiento Laudus ya posteado** (cambiar monto/fecha/desc/categoría) — un mecanismo distinto (mutar `imports/laudus/*` o emitir un ajuste compensatorio), más riesgoso para el cuadre validado vs el contador, y merece su propia story. Mantener 6.2 enfocada = el valor que Ary pidió, sin abrir la caja de Pandora de editar Laudus.

## Acceptance Criteria

**AC1 — Aprobar un `missing-in-laudus` con `confirm-cartola-only` escribe la transacción al ledger.**
Given una discrepancia `missing-in-laudus` abierta (línea de cartola sin contraparte Laudus),
When el contador llama `POST /api/v1/reconciliation/discrepancies/{id}/resolve` con `action="confirm-cartola-only"` (+ la categoría destino, ver AC5) y justificación ≥10 chars,
Then el sistema renderiza una `Transaction` beancount desde los datos de la cartola de esa discrepancia (`date`, `amount`, `currency`, `description`, signo según el tipo de cuenta) y la **escribe a la zona `manual/`** (incluida en `main.beancount`), pasa `bean-check`, y commitea+pushea (gateado por `IMPORTER_GIT_ENABLED`).

**AC2 — Atomicidad: si bean-check falla, la discrepancia NO se marca resuelta.**
Given la escritura de la tx,
Then el orden es: **escribir + bean-check + commit PRIMERO**; solo si `success` → appendear la línea de resolución al JSONL. Si bean-check da rojo (rollback automático vía `commit_reconciliation`), el endpoint devuelve 422/400 con el detalle y la discrepancia **sigue abierta** (no se appendea resolución). Nunca queda una discrepancia "resuelta" sin su tx en el ledger, ni una tx en el ledger sin cerrar la discrepancia.

**AC3 — Las demás acciones de cierre NO escriben al ledger (comportamiento actual preservado).**
Given `confirm-laudus-only` / `accept-laudus*` / cualquier acción que mantiene Laudus, o `escalate`,
Then `resolve()` se comporta como hoy: appendea la resolución (o escala) al JSONL, sin tocar el ledger. Cero regresión en `test_reconciliation.py`.

**AC4 — La tx anotada lleva la metadata para trazarla y categorizarla.**
Given la tx escrita,
Then su `meta` incluye al menos `source: "reconciliation"`, `bank_account_id`, `ref_discrepancy_id` (link a la discrepancia origen para audit), y la `line` de la cartola. El `flag` y `category_status` deben dejar la tx en un estado consistente con `/categorizacion` (si la categoría queda en `Suspense`, que aparezca como pendiente; si el contador fijó una categoría real, `confirmed`). **Anti-regresión:** no romper `list_pending` (ver Dev Notes → "Anti-regresión").

**AC5 — La categoría destino del gasto la decide el contador (no queda en Suspense silenciosamente).**
Given un `missing-in-laudus` confirmado como gasto real,
Then la acción acepta una **cuenta de categoría destino** (`Expenses:...`) — porque el predictor es Noop (todo cae en `Suspense`) y un gasto real necesita su cuenta. (Mecanismo exacto = decisión de diseño abajo: campo nuevo en `ResolveRequest` vs default Suspense + categorizar luego en 9.7.)

**AC6 — Idempotencia / doble aprobación bloqueada.**
Given una discrepancia ya resuelta,
Then `resolve()` la rechaza (ya existe: `"discrepancy_id ya fue resuelta"`) → no se puede escribir la tx dos veces. Verificar que el guard corre **antes** de la escritura al ledger.

**AC7 — Tests + sin regresiones.**
Tests que cubren: `missing-in-laudus`+`confirm-cartola-only` → tx en `manual/`, bean-check verde, discrepancia cerrada; bean-check rojo → 422 + discrepancia sigue abierta + sin línea de resolución (atomicidad); `confirm-laudus-only` → cierra sin write; `escalate` → no cierra, no write; doble aprobación → rechazada. Suite completa sin regresiones nuevas (los 2 rojos de `test_fava_edit_validator` son pre-existentes).

### Fuera de scope de 6.2

- **Editar asientos Laudus existentes** (`value-mismatch`/`accept-cartola`, soft-mismatch `accept-cartola-*`) → story futura.
- Polish del dashboard 9.12 (historial, filtros UI, moneda, FX action-sets) → **Story 6.3** (ex-6.2).
- Cierre de período "reconciliado completo" → **Story 6.4** (ex-6.3).
- Reconciliación de cartolas de inversión/custodios → diferida.

## Tasks / Subtasks

- [ ] **Task 1 — Writer de anotación (renderizar tx + escribir vía `commit_reconciliation`)** (AC1, AC2, AC4)
  - [ ] Nueva función en `pipeline/importers/reconcile.py` (cohesión con `commit_reconciliation`/`reconcile_cartola`), p.ej. `annotate_discrepancy(discrepancy, *, category_account, importer, ledger_root, user_email, ts)`.
  - [ ] Resolver `account_target` desde `discrepancy["bank_account_id"]` (`importer.resolver.resolve(...)`), `is_liability = account_target.startswith(_LIABILITY_ROOT)`. Construir las postings con `_build_postings(account_target, category_account, amount, currency, is_liability)` (reusar — NO reimplementar el signo). Para USD, ver AC6 de 6.1 / `build_usd_postings` (decidir si USD entra en scope o se difiere — la mayoría de `missing-in-laudus` serán CLP).
  - [ ] Renderizar la `Transaction` con `render_entries`/el mismo formato que `cartola_pdf_importer`. `meta`: `source="reconciliation"`, `bank_account_id`, `ref_discrepancy_id=discrepancy_id`, `line`. Narration = `discrepancy["cartola"]["description"]`; fecha = `cartola.date`.
  - [ ] Destino = archivo en la zona `manual/` (incluida por `main.beancount:37` → `manual/*.beancount`). Nombre estable por cuenta+mes, p.ej. `manual/reconciliation-{bank_slug}-{year_month}.beancount`. **Append, no replace:** leer el contenido existente (si el archivo existe), concatenar la nueva entry, pasar el contenido COMPLETO como `new_content` a `commit_reconciliation` (que hace write-and-replace + bean-check + rollback + git). Verificar que el glob `manual/*.beancount` es plano (no recursivo) → archivos directos en `manual/`, no subcarpetas.
  - [ ] Devolver `{success, git_commit_sha, error_msg, file}` (mismo shape que `commit_reconciliation`).

- [ ] **Task 2 — Wirear `resolve()` para anotar antes de cerrar** (AC1, AC2, AC3, AC6)
  - [ ] En `reconciliation/service.py:resolve()`: detectar la acción anotadora (`state=="missing-in-laudus"` y `action=="confirm-cartola-only"`). Para ese caso, **después** del guard de "ya resuelta" (AC6) y la validación de acción/justificación, llamar `annotate_discrepancy(...)` **antes** de `append_resolution`.
  - [ ] Si `annotate_discrepancy` falla (`success==False`) → `raise` un error nuevo (mapear a 422 en el router) con `error_msg`; **no** appendear resolución. Si OK → `append_resolution` + incluir `git_commit_sha` en la respuesta.
  - [ ] Todas las demás acciones: ruta actual intacta (solo `append_resolution`, sin tocar el ledger).
  - [ ] `resolve()` necesita el `ledger_root` + `importer` + `category_account`. Inyectables para tests (igual que 6.1: `path`, `now_iso`; agregar `ledger_root=None`, `importer=None`, default a `_ledger_root()` / `_build_importer`). OJO: `reconciliation/service.py` no construye importer hoy — ver cómo lo arma `cartolas/service.py` (`_build_importer(root)`), reusar.

- [ ] **Task 3 — Endpoint + schema** (AC5)
  - [ ] `ResolveRequest` (`reconciliation/models.py`): agregar `category_account: str | None = None`. Validar que es obligatorio cuando `action=="confirm-cartola-only"` (400 si falta).
  - [ ] `ResolveResponse`: agregar `git_commit_sha: str | None = None` (None para acciones que no escriben).
  - [ ] Router `resolve_discrepancy`: pasar `category_account`; mapear el error de anotación a 422 (distinto del 400 de `ResolveError` de validación).

- [ ] **Task 4 — Frontend (input de categoría para confirm-cartola-only)** (AC5)
  - [ ] `ReconciliationPage`: cuando la acción seleccionada es `confirm-cartola-only`, mostrar un input/dropdown de cuenta de categoría (`Expenses:...`). Reusar el patrón de `CuentasPendientesPage`/`CategorizacionPage` (que ya cargan cuentas del plan). Enviar `category_account` en el body del resolve.
  - [ ] Mostrar el resultado (commit sha / éxito) y refrescar la lista + el badge.

- [ ] **Task 5 — Tests** (AC7)
  - [ ] `backend/tests/test_reconciliation_annotate.py` (o extender `test_reconciliation.py`): los 5 casos de AC7. Reusar el patrón de ledger fixture + bean-check real de `test_reconcile_integration.py` / `test_reconcile_cartola.py` (ledger root mínimo con `accounts.beancount`, `manual/`, `main.beancount`).
  - [ ] `monkeypatch.delenv("IMPORTER_GIT_ENABLED")` para no-op git en local.

## Dev Notes

### Flujo objetivo (estado actual → objetivo)

**Hoy (`resolve()`):**
```
POST /reconciliation/discrepancies/{id}/resolve
  → resolve()  [reconciliation/service.py:124]
      → buscar original + guard "ya resuelta" + validar acción/justificación
      → append_resolution(id, resolution, jsonl)   ← SOLO audit trail, NADA al ledger
      → return {status: resolved/escalated}
```

**Objetivo (6.2):**
```
  → resolve()
      → buscar original + guard "ya resuelta" (AC6) + validar acción/justificación + category_account (AC5)
      → IF state=="missing-in-laudus" AND action=="confirm-cartola-only":
            res = annotate_discrepancy(...)            ← NUEVO: render tx → manual/ → bean-check → git
            IF not res.success: raise AnnotationFailed (422)   ← AC2: no cierra
      → append_resolution(...)                          ← solo si la anotación (si hubo) salió OK
      → return {status: resolved, git_commit_sha}
```

### Piezas existentes — REUSAR, no reescribir

| Pieza | Ubicación | Uso en 6.2 |
|---|---|---|
| `commit_reconciliation(file_path, new_content, discrepancy_id, action, ledger_root)` | [reconcile.py:179](pipeline/importers/reconcile.py#L179) | write-and-replace + bean-check + rollback + git, bajo lock. **El motor de escritura.** Pasarle `new_content` = contenido completo del archivo `manual/` con la nueva entry appendeada. |
| `_build_postings(account_target, category, amount, currency, is_liability)` | [cartola_pdf_importer.py](pipeline/importers/cartola_pdf_importer.py) | construir las 2 postings con el signo correcto (Liabilities niega, Assets tal cual). NO reimplementar. |
| `build_usd_postings` / `fx_metadata` | cartola_pdf_importer.py | solo si USD entra en scope (decisión abajo). |
| `render_entries` / `_slug` | cartola_pdf_importer.py | formatear la `Transaction` a texto beancount + nombre de archivo. |
| `importer.resolver.resolve(bank_account_id)` | `bank_account_resolver.py` | bank_account_id → `account_target`. |
| `_LIABILITY_ROOT` | cartola_pdf_importer.py | derivar `is_liability`. |
| `_build_importer(root)` | [cartolas/service.py](backend/app/api/v1/cartolas/service.py) | construir el `CartolaPdfImporter` (reusar; `reconciliation/service.py` no lo hace hoy). |
| `_ledger_root()` | [laudus_run.py:37](pipeline/importers/laudus_run.py#L37) | raíz del ledger (honra `LEDGER_DIR`). |
| `append_resolution(id, resolution, path)` | [discrepancy_writer.py:90](pipeline/importers/discrepancy_writer.py#L90) | el cierre de la discrepancia (audit). Ya existe; solo cambia el ORDEN (después de la anotación). |
| `read_discrepancies(discrepancy_id=...)` / `_iter_lines` | [reconciliation/service.py](backend/app/api/v1/reconciliation/service.py) | obtener el `cartola` dict de la discrepancia (date/amount/currency/description/line_no). |

### Estructura del JSONL de discrepancia (lo que `annotate` consume)

Una discrepancia `missing-in-laudus` tiene (de `build_discrepancy`):
```json
{"discrepancy_id": "...", "batch_id": "...", "bank_account_id": "...", "state": "missing-in-laudus",
 "source": "cartola", "cartola": {"line_no": N, "date": "2026-03-15", "amount": -45000.0,
 "currency": "CLP", "description": "..."}, "laudus": null, "fx": {...}, "resolution": null}
```
→ `annotate` usa `cartola.{date, amount, currency, description, line_no}` + `bank_account_id`. (Nota: `amount` quedó como `float` vía `_num()` al escribirse — castear a `Decimal(str(amount))` para construir postings, evitar float en beancount.)

### Dónde se incluye `manual/` (verificado)

`ledger/main.beancount` incluye (líneas 31-37): `accounts.beancount`, `opening-2021`, `prices`, `imports/laudus/*`, `imports/cartolas/*`, `imports/_new-accounts-pending`, **`manual/*.beancount`**. → escribir en `manual/reconciliation-{bank}-{ym}.beancount` queda incluido sin tocar `main.beancount`. El glob `manual/*.beancount` NO es recursivo → archivos planos directos en `manual/`.

### 🚨 Anti-regresión: `list_pending` (categorización)

`list_pending` ([transactions/service.py](backend/app/api/v1/transactions/service.py)) filtra tx por `category_status ∈ (suggested, pending)`. Una tx anotada con categoría real (la que fijó el contador) debe quedar `category_status="confirmed"` para NO aparecer como pendiente. Si se decide dejarla en `Suspense` (default), entonces `category_status` debe ser `pending`/`suggested` para que `/categorizacion` la levante. Definir `category_status` coherente con la decisión de AC5. (Mismo eje que la nota de 6.1 sobre flag vs category_status.)

### Orden write-vs-resolution (la decisión de correctitud central — AC2)

`commit_reconciliation` ya hace rollback del archivo si bean-check falla. La clave es: **NO appendear la línea de resolución al JSONL si la anotación falló**. Si se appendeara primero y la anotación fallara, la discrepancia desaparecería del dashboard (se vería "resuelta") sin estar en el ledger → plata perdida silenciosa, justo el tipo de fuga que 10.2 tapó. Por eso: anotar → si OK → resolver.

### Convención de signo (heredada, NO tocar)

`Liabilities` (TC): `target=-amount`, categoría tal cual; `Assets`: tal cual. `_build_postings` ya lo maneja vía `is_liability`. [Source: cartola_pdf_importer docstring]

### Testing standards

- pytest en `backend/tests/`, correr con `PYTHONUTF8=1` (gotcha Windows). venv en `./venv/Scripts/python.exe`.
- bean-check real sobre el render (cargar con `beancount.loader`) es el gate de verdad — patrón en [test_reconcile_integration.py:30-33](backend/tests/test_reconcile_integration.py#L30-L33) y `test_reconcile_cartola.py`.
- Ledger fixture mínimo: `accounts.beancount` (con la cuenta de banco + Expenses + Suspense), `manual/`, `main.beancount` que incluya `manual/*.beancount`.
- Inyección: `resolve()` debe aceptar `ledger_root`, `importer`, `now_iso`, `path` para tests deterministas.
- `monkeypatch.delenv("IMPORTER_GIT_ENABLED")` → commit no-op local.

### Project Structure Notes

- Motor/writer: `pipeline/importers/reconcile.py` (cohesión con `commit_reconciliation` + `reconcile_cartola` de 6.1).
- API: `backend/app/api/v1/reconciliation/` (router, service, models). `resolve()` vive en `service.py`.
- Frontend: `frontend/src/pages/ReconciliationPage.tsx` + su service.
- Sin Supabase, sin Sheets, sin flags (cleanup c4 9.16). Beancount = fuente única.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic-6] — Goal reformulado (modelo A), 6.2 en el scope, FR mapping.
- [Source: _bmad-output/implementation-artifacts/6-1-wiring-promote-reconcile.md] — modelo A, BLOCKER resuelto, `reconcile_cartola`, "PRÓXIMA STORY".
- [Source: pipeline/importers/reconcile.py] — `commit_reconciliation` (el writer a reusar), `reconcile_cartola`, `_BLOCKING`.
- [Source: backend/app/api/v1/reconciliation/service.py] — `resolve()`, `ACTIONS_BY_STATE`, `_resolved_ids`, `read_discrepancies`.
- [Source: pipeline/importers/discrepancy_writer.py] — `append_resolution`, shape de la discrepancia.
- [Source: pipeline/importers/cartola_pdf_importer.py] — `_build_postings`, `build_usd_postings`, `render_entries`, `_LIABILITY_ROOT`, convención de signo.
- [Source: backend/app/api/v1/cartolas/service.py] — `_build_importer`, patrón de inyección.
- [Source: backend/app/api/v1/transactions/service.py#list_pending] — anti-regresión de `category_status`.
- [Source: ledger/main.beancount] — includes (`manual/*.beancount` línea 37).
- [Source: memoria project_epic6_reconciliacion_next, project_tc_pasivo_dos_estados] — modelo A, TC pasivo.

## Preguntas de diseño para Ary (resolver antes/durante el dev)

1. **Zona de escritura de la tx anotada.** Recomendado: `manual/reconciliation-{bank}-{ym}.beancount` (ya incluido por `main.beancount`, sin tocar includes). Alternativa: agregar una zona dedicada `imports/reconciliation/*.beancount` (más explícita, requiere editar `main.beancount`). ¿`manual/` o zona nueva?

2. **Categoría destino (AC5).** Recomendado: agregar `category_account` a `ResolveRequest`, obligatorio para `confirm-cartola-only`, el contador la elige en el dashboard (dropdown Expenses). Alternativa: escribir con `Suspense` y dejar que `/categorizacion` (9.7) la categorice después (menos clicks ahora, pero la tx entra "sin clasificar"). ¿Cuál?

3. **¿Qué acciones anotan en esta story?** Propuesta: SOLO `missing-in-laudus`/`confirm-cartola-only` (append puro). Las que editan un asiento Laudus existente (`value-mismatch`/`accept-cartola`, soft-mismatch `accept-cartola-*`) → story aparte. ¿De acuerdo, o querés incluir alguna más ahora?

4. **USD en scope?** La mayoría de `missing-in-laudus` serán CLP. ¿Incluyo el render USD (price per-unit + FX, reusando `build_usd_postings`) en 6.2, o lo difiero a la story de edición (los casos USD suelen venir con estados FX, no missing puro)?

5. **Frontend en 6.2 o handoff a Sally?** El input de categoría para `confirm-cartola-only` es chico, pero toca UX. ¿Lo hago en 6.2 (end-to-end) o el backend en 6.2 + el polish de la UI se junta con el dashboard 6.3 (ex-6.2)?

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
