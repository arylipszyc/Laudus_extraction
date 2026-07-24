# Story 6.5: Cierre de período de reconciliación (FR35)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **contador del family office**,
I want que **el dashboard muestre, por cuenta y mes, si ese período de reconciliación está completo (cartola conciliada y sin diferencias abiertas) o todavía tiene diferencias por resolver**,
so that **pueda saber de un vistazo qué períodos ya cerraron y cuáles me faltan, sin tener que adivinar si "0 diferencias" significa "todo cuadró" o "nunca subí la cartola"**.

> **Contexto:** cierra Epic 6 (FR35). El motor (9.6b), el wiring del promote (6.1, modelo A), la anotación-on-aprobación (6.3) y el dashboard (6.4) ya están done. Esta story agrega el **estado de período**: marcar un (cuenta, mes) como reconciliado-completo cuando corrió una reconciliación Y no quedan diferencias abiertas.

> **⚠️ Depende de 6.5b (hacer 6.5b primero).** 6.5b persiste el campo `year_month` (período del estado de cuenta) en cada discrepancia, distinto de la fecha de la tx. 6.5 usa ese período para cruzar el run-record (keyed por `model.period.end`) con las discrepancias abiertas (AC5). Sin 6.5b, el conteo de abiertas se bucketea por fecha de tx y NO cuadra con el run-record. Ver `6-5b-reconciliacion-period-aware.md`.

## Decisión de alcance (resuelta con Ary 2026-06-24)

**Opción B — run-record + derivación.** El epic dejó abierta la pregunta "derivar del JSONL vs. marcador persistido". Se eligió B por un hecho del código:

🔑 **El JSONL de discrepancias NO basta para derivar "período completo".** Hoy `reconcile_cartola` (6.1) **no persiste ningún registro de que una reconciliación corrió**, y una cartola **perfecta** (0 diferencias) no escribe **nada** al JSONL ([reconcile.py:347](pipeline/importers/reconcile.py#L347) — *"`perfect` no genera diferencia"*). Por lo tanto estos tres casos se ven **idénticos** (0 filas en el JSONL para ese período):
1. Cartola conciliada y perfecta (0 diferencias) — el período MÁS completo.
2. Todas las diferencias resueltas (0 abiertas).
3. Cartola **nunca subida** para ese período.

Derivar solo del JSONL (Opción A) no puede distinguir #1/#2 de #3, y deja invisible al #1. Por eso `reconcile_cartola` debe dejar un **run-record** por (cuenta, mes); "completo" = corrió un run **Y** 0 diferencias abiertas.

**Descartado — Opción C (cierre explícito con botón de sign-off):** más trabajo (acción UI + persistencia + RBAC) y no es necesario para responder la pregunta del contador. Si más adelante se quiere un sign-off auditado, es una story aparte. **No re-litigar sin una necesidad nueva.**

## Acceptance Criteria

1. **AC1 — Run-record al reconciliar.** Cuando `reconcile_cartola` (cuenta corriente, modelo A) procesa una cartola, appendea un registro a `ledger/_meta/reconciliation-runs.jsonl` con `{schema_version, bank_account_id, year_month, reconciled_at, matched, differences, blocking, batch_id}`. Se escribe **siempre que la reconciliación corre**, incluso con 0 diferencias (caso cartola perfecta).
2. **AC2 — El run-record sobrevive el refresh del backend.** El archivo `reconciliation-runs.jsonl` se commitea por git en el mismo flujo (gateado por `IMPORTER_GIT_ENABLED`), **incluso cuando no hubo discrepancias nuevas** (el backend hace `git reset --hard` en cada refresh → sin commit el run se perdería). Hoy el commit del JSONL de discrepancias está gateado `if new:` — el run-record NO debe heredar ese gate.
3. **AC3 — Endpoint de estado de períodos.** `GET /api/v1/reconciliation/periods` devuelve, por cada (bank_account_id, year_month) con run-record, `{bank_account_id, year_month, reconciled_at, matched, differences, open, status}` donde `open` = nº de discrepancias **originales sin resolver** de ese período y `status` = `"complete"` si `open == 0`, `"pending"` si `open > 0`. RBAC: `contador`/`admin`.
4. **AC4 — Último run gana.** Si una cartola se re-sube/re-reconcilia (varios run-records para el mismo (cuenta, mes)), el endpoint reporta el **más reciente** por `reconciled_at` (append-only, sin reescribir líneas — consistente con el patrón del JSONL).
5. **AC5 — `open` se deriva en vivo del JSONL de discrepancias, por período de estado de cuenta.** El conteo de abiertas reusa `read_discrepancies(bank_account_id, year_month).summary.total` (ya excluye resueltas y `escalate`). **El `year_month` aquí es el período persistido por 6.5b** (no la fecha de la tx) → cuadra con el `reconciled_at`/período del run-record. Resolver la última diferencia de un período lo pasa a `complete` sin tocar el run-record.
6. **AC6 — Indicador en el dashboard.** `ReconciliationPage` muestra los períodos reconciliados con su estado (✓ completo / "N pendientes"), cuenta (nombre, no UUID) y fecha de reconciliación. Consistente con el estilo de 6.4 (Cards/badges, sin toasts). Los períodos `complete` se distinguen visualmente de los `pending`.
7. **AC7 — Tests.** Backend: el run-record se escribe (incl. caso perfecto con 0 diferencias y commit), `list_periods` da `complete`/`pending` correctamente, último-run-gana, `open` cae a 0 al resolver. Frontend: component test del indicador (al menos un período `complete` y uno `pending`). `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` → 0 regresiones nuevas.

### Fuera de scope (explícito)

- **Cierre explícito / sign-off con botón** (Opción C). Diferido a story propia si aparece la necesidad.
- **Períodos de TARJETA DE CRÉDITO.** La TC va por `correct_tc_cartola` (postea la corrección, NO usa el JSONL de discrepancias modelo-A), así que el concepto "0 diferencias abiertas" no aplica igual. Ver **Pregunta para Ary #1** abajo. Default de esta story: el run-record y el estado de período cubren **cuenta corriente** (`reconcile_cartola`); TC queda fuera salvo que Ary decida incluirla.
- **"Período nunca subido" como fila explícita.** El endpoint lista solo períodos con run-record; no enumera meses faltantes (eso requeriría un calendario de cuentas×meses esperados, otra story).

## Tasks / Subtasks

- [x] **Task 1 — Writer del run-record** (AC1, AC4)
  - [x] `append_run(run, jsonl_path)` en [discrepancy_writer.py](pipeline/importers/discrepancy_writer.py) — append-only, sin dedup, crea el parent. + `build_run(*, bank_account_id, year_month, reconciled_at, matched, differences, blocking, batch_id)` con el shape de AC1 y `SCHEMA_VERSION`.

- [x] **Task 2 — Escribir + commitear el run en `reconcile_cartola`** (AC1, AC2)
  - [x] En [reconcile.py](pipeline/importers/reconcile.py) `reconcile_cartola`, dentro del lock tras appendear las discrepancias: `append_run(build_run(...), runs_path)` con los campos de `result`.
  - [x] **AC2:** el commit ahora corre SIEMPRE (no más `if new:`). `commit_paths = [runs_path] + (disc_path si new)`; `git_commit_push` es no-op idempotente sin git habilitado → tests siguen verdes y no hay commits espurios en local.
  - [x] Helper `_runs_path(ledger_root)` espejo de `_discrepancies_path` (override `LEDGER_RECONCILIATION_RUNS`). Mismo `_rel(p)` para el `git add`.

- [x] **Task 3 — Lectura: `list_periods()` + endpoint** (AC3, AC4, AC5)
  - [x] [reconciliation/service.py](backend/app/api/v1/reconciliation/service.py): `_runs_path()` (espejo de `_jsonl_path()`). `list_periods(path=None, runs_path=None)`: agrupa runs por `(bank_account_id, year_month)` tomando el `reconciled_at` máximo (AC4); `open = read_discrepancies(bank_account_id, year_month).summary.total` (AC5, keyed por el `year_month` persistido de 6.5b); `status`. Orden mes desc, cuenta asc.
  - [x] [reconciliation/router.py](backend/app/api/v1/reconciliation/router.py): `GET /periods` con `require_role(["contador","admin"])` + `response_model=list[PeriodStatus]`. Modelo `PeriodStatus` en [models.py](backend/app/api/v1/reconciliation/models.py).

- [x] **Task 4 — Indicador en el dashboard** (AC6)
  - [x] [reconciliation.ts](frontend/src/services/reconciliation.ts): `getPeriods()` + tipo `PeriodStatus` (mismo patrón `fetch`+`credentials:'include'`).
  - [x] [ReconciliationPage.tsx](frontend/src/pages/ReconciliationPage.tsx): Card "Períodos reconciliados" (arriba de los filtros) con React Query; cada fila = cuenta (`bankNameById`), mes, fecha de reconciliación (recortada YYYY-MM-DD) y `PeriodBadge` (✓ Completo verde / "N pendientes" amber). Sin toasts. Click en un período `pending` → setea `bankFilter`/`monthFilter`.

- [x] **Task 5 — Tests + verificación** (AC7)
  - [x] Backend (`backend/tests/test_period_status.py`, 7 tests): `append_run` escribe; cartola **perfecta** (0 diferencias) deja run-record; `list_periods` → `complete` (open 0) y `pending` (open>0); último-run-gana; `open` baja a 0 al resolver. Fixtures mirror de `test_reconcile_cartola.py`.
  - [x] Frontend (vitest): component test del indicador (un `complete` + un `pending`, cuenta como nombre no UUID).
  - [x] `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` → **587 passed, 1 xfailed, 2 failed** (los 2 rojos `test_fava_edit_validator` PRE-EXISTENTES, no tocados; 0 regresiones nuevas) + `npx tsc --noEmit` verde + 4/4 component tests.

## Dev Notes

### Estado actual de los archivos que se tocan (leídos para esta story)

- **[pipeline/importers/reconcile.py](pipeline/importers/reconcile.py) — `reconcile_cartola` (línea 330)** — modelo A: concila, appendea discrepancias al JSONL, **descarta** las entries beancount (no postea), consume el staging. Ya calcula `matched`/`differences`/`blocking`/`year_month`/`bank_account_id`/`batch_id` en `result`. El `git_commit_push` está gateado `if new:` (líneas ~410-413) — **este es el punto a ajustar para AC2** (el run debe commitearse aun con 0 diferencias). `_discrepancies_path` (línea 317) es el patrón a espejar para `_runs_path`. Helper `_rel(p)` para el `git add` relativo.
- **[backend/app/api/v1/reconciliation/service.py](backend/app/api/v1/reconciliation/service.py)** — `_jsonl_path()` (override `LEDGER_DISCREPANCIES` → `LEDGER_DIR` → default), `_iter_lines`, `_year_month`, `_resolved_ids` (excluye `escalate`), `read_discrepancies(state, year_month, bank_account_id, ...)` (ya filtra por cuenta+mes y excluye resueltas → reusar para `open`, AC5). Espejar para `_runs_path()`/`list_periods()`.
- **[backend/app/api/v1/reconciliation/router.py](backend/app/api/v1/reconciliation/router.py)** — patrón de endpoints con `require_role(["contador","admin"])` + `response_model`. Agregar `GET /periods`.
- **[backend/app/api/v1/reconciliation/models.py](backend/app/api/v1/reconciliation/models.py)** — Pydantic schemas (`CountResponse`, etc.). Agregar `PeriodStatus`.
- **[pipeline/importers/discrepancy_writer.py](pipeline/importers/discrepancy_writer.py)** — `append_discrepancy` (con dedup), `append_resolution` (sin dedup, append-only). `append_run` sigue el patrón de `append_resolution` (append simple, sin dedup). `SCHEMA_VERSION = "1.0"`.
- **[backend/app/api/v1/cartolas/service.py](backend/app/api/v1/cartolas/service.py) `validate_balance` (línea ~410)** — es quien llama `reconcile_cartola` (línea 478) y `correct_tc_cartola` para TC (línea 471). **No hace falta tocarlo** para esta story: el run-record se escribe dentro de `reconcile_cartola`. Confirmar que el `res` que retorna no necesita el run (no lo necesita; el run vive en el JSONL).
- **[frontend/src/pages/ReconciliationPage.tsx](frontend/src/pages/ReconciliationPage.tsx)** — reescrita en 6.4: `fmt` (ahora valida moneda 3-letras), `bankNameById` (join con `/bank-accounts/`), filtros `monthFilter`/`bankFilter`, Cards/badges. Reusar para el indicador. `StateBadge`/`Chip` como referencia de estilo.
- **[frontend/src/services/reconciliation.ts](frontend/src/services/reconciliation.ts)** — `getDiscrepancies`/`getHistory`/`getReconciliationCount`/`resolveDiscrepancy` (todos `fetch`+`credentials:'include'`, `${api.baseUrl}/api/v1/reconciliation/...`). Agregar `getPeriods` con el mismo patrón.

### Piezas a reusar (NO reescribir)

- `read_discrepancies(bank_account_id, year_month)` para el conteo de abiertas (ya excluye resueltas/escaladas). **No** reimplementar el filtro de "abiertas".
- `_iter_lines` para leer el runs JSONL.
- `git_commit_push` / `acquire_lock` / `IMPORTER_GIT_ENABLED` — la infra de commit ya existe en `reconcile_cartola`; solo cambia el gate y los paths.
- `bankNameById` + `getBankAccounts` en el front para el label de cuenta (ya cargado).

### Anti-regresión

- **No cambiar la semántica del commit de discrepancias.** Hoy `if new:` evita commits vacíos cuando no hay discrepancias nuevas. Al agregar el run-record, el commit ahora corre también con `new==0` — verificar que esto NO rompe los tests de 6.1 (`test_reconcile_cartola.py`) ni produce commits espurios cuando `IMPORTER_GIT_ENABLED` está off (debe seguir siendo no-op en local/tests).
- **Append-only.** El runs JSONL nunca reescribe líneas (igual que discrepancias/resoluciones). El "último gana" es responsabilidad del **lector** (`list_periods`), no de un read-modify-write (que reintroduciría el bug de lost-update concurrente ya deferido en 6.3).
- **No tocar `correct_tc_cartola`** salvo que se resuelva incluir TC (Pregunta #1).

### Testing standards

- Backend: pytest en `backend/tests/`, `PYTHONUTF8=1` + `venv/Scripts/python.exe` (gotcha Windows, ver memoria del proyecto). Fixtures de reconcile en `test_reconcile_cartola.py` (cartola staged + Laudus reales + `ledger_root` temp). El gate de git en tests = `IMPORTER_GIT_ENABLED` off (no-op), así que para testear AC2 verificar que el run-record se **escribe** al archivo (el commit se cubre por que la rama corra, no por un push real).
- Frontend: vitest + testing-library, patrón de `ReconciliationPage.test.tsx` (mock de los `fetch` del service).

### Project Structure Notes

- Backend nuevo: solo agrega a módulos existentes (`reconciliation/service.py`, `router.py`, `models.py`, `discrepancy_writer.py`). Sin módulo nuevo.
- Nuevo archivo de datos: `ledger/_meta/reconciliation-runs.jsonl` (junto a `cartola-discrepancies.jsonl` y `fx-bcch-eom.jsonl`). Mismo patrón `_meta/` + commit por git.
- Frontend: cambios acotados a `ReconciliationPage.tsx` + `reconciliation.ts`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic-6] — Story 6.5 (líneas 1082-1083): "Marcar un período como reconciliado completo cuando no quedan discrepancias abiertas. Probablemente derivable... evaluar si requiere un marcador explícito persistido. **Definir alcance al crear la story.**" + FR35 mapping (línea 1106) + Goal modelo A (línea 1028).
- [Source: pipeline/importers/reconcile.py#reconcile_cartola] — el productor del run-record; `perfect` no genera diferencia (línea 347); commit gateado `if new` (líneas 410-413); `_discrepancies_path` (línea 317).
- [Source: backend/app/api/v1/reconciliation/service.py] — `read_discrepancies`/`_resolved_ids`/`_jsonl_path`/`_iter_lines` a reusar/espejar.
- [Source: pipeline/importers/discrepancy_writer.py] — patrón append-only (`append_resolution`) para `append_run`.
- [Source: _bmad-output/implementation-artifacts/6-1-wiring-promote-reconcile.md] — modelo A, "JSONL commiteado para sobrevivir el git reset", decisión D1 (gate todo-o-nada).
- [Source: _bmad-output/implementation-artifacts/6-4-completar-dashboard-reconciliacion.md] — estilo del dashboard (Cards/badges, sin toasts), `fmt`/`bankNameById`, patrón de component tests.
- [Source: _bmad-output/planning-artifacts/adr-001-plan-de-cuentas-beancount-source-of-truth.md] — Beancount fuente única; el estado de período se deriva del ledger/_meta, no de SQL.

## Preguntas para Ary (resolver antes o durante el dev)

1. **¿Incluir períodos de TARJETA DE CRÉDITO?** La TC va por `correct_tc_cartola` (postea la corrección; no genera discrepancias modelo-A), así que "0 abiertas" no aplica igual — un período de TC estaría "completo" apenas se importa (no hay diferencias que resolver). Opciones: (a) **default de la story:** TC fuera de scope, el indicador cubre solo cuenta corriente; (b) TC también deja run-record y se muestra siempre `complete` (informativo: "TC May importada"); (c) diferir TC a otra story. *Recomendación: (a) para mantener la story chica; sumar TC cuando el flujo de TC esté validado en prod (hoy tiene handoff de prod pendiente, ver memoria de 6.2).*
2. **¿El indicador debe enumerar meses faltantes** (períodos esperados sin cartola subida)? Hoy NO (solo lista lo reconciliado). Enumerar faltantes requeriría un calendario de cuentas×meses esperados → otra story. *Recomendación: dejarlo fuera; el contador sabe qué cuentas maneja.*

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Opus 4.8)

### Debug Log References

- `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests/test_period_status.py backend/tests/test_reconcile_cartola.py backend/tests/test_reconcile_period_aware.py -q` → 20 passed.
- `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` → 587 passed, 1 xfailed, 2 failed (`test_fava_edit_validator` PRE-EXISTENTES).
- `npx vitest run src/pages/ReconciliationPage.test.tsx` → 4 passed. `npx tsc --noEmit` → limpio.

### Completion Notes List

- **Run-record (AC1/AC4):** `build_run`/`append_run` en `discrepancy_writer.py` (cohesión con `append_resolution`, append-only sin dedup). `reconcile_cartola` lo escribe dentro del lock con los campos que ya calculaba (`matched`/`differences`/`blocking`/`year_month`/`bank_account_id`/`batch_id`/`ts`). El "último gana" vive en el LECTOR (`list_periods`), no en un read-modify-write (evita el lost-update deferido en 6.3).
- **Commit siempre (AC2):** se eliminó el gate `if new:` para el commit. Ahora `commit_paths = [runs_path] + (disc_path si new)` y `git_commit_push` corre siempre — el run-record sobrevive el `git reset --hard` del refresh aunque la cartola sea perfecta (0 diferencias). Verificado anti-regresión: `git_commit_push` es no-op idempotente cuando `IMPORTER_GIT_ENABLED` está off → los tests de 6.1 siguen verdes y no hay commits espurios en local.
- **Lectura (AC3/AC5):** `list_periods` reusa `read_discrepancies(bank_account_id, year_month).summary.total` para `open` — que ya excluye resueltas/escaladas y, **gracias a 6.5b, filtra por el `year_month` persistido** (no la fecha de la tx) → el conteo de abiertas cuadra con el período del run-record. Resolver la última diferencia pasa a `complete` sin tocar el run.
- **Frontend (AC6):** Card "Períodos reconciliados" con `PeriodBadge` (✓ Completo / N pendientes), cuenta por nombre vía `bankNameById`, fecha recortada a YYYY-MM-DD; click en `pending` setea los filtros mes/cuenta. Sin toasts (estilo 6.4).
- **Scope (decisiones de la story):** TC fuera de scope (cuenta corriente solo — la TC postea vía `correct_tc_cartola`, no genera discrepancias modelo-A); no se enumeran meses faltantes (solo lista lo reconciliado). `correct_tc_cartola` NO tocado.

### File List

- `pipeline/importers/discrepancy_writer.py` (MODIFICADO — `build_run` + `append_run`)
- `pipeline/importers/reconcile.py` (MODIFICADO — `_runs_path`; `reconcile_cartola` escribe el run + commit siempre con ambos paths)
- `backend/app/api/v1/reconciliation/service.py` (MODIFICADO — `_runs_path()` + `list_periods()`)
- `backend/app/api/v1/reconciliation/models.py` (MODIFICADO — `PeriodStatus`)
- `backend/app/api/v1/reconciliation/router.py` (MODIFICADO — `GET /periods`)
- `backend/tests/test_period_status.py` (NUEVO — 7 tests)
- `frontend/src/services/reconciliation.ts` (MODIFICADO — `getPeriods` + tipo `PeriodStatus`)
- `frontend/src/pages/ReconciliationPage.tsx` (MODIFICADO — `PeriodsCard` + `PeriodBadge`)
- `frontend/src/pages/ReconciliationPage.test.tsx` (MODIFICADO — mock `getPeriods` + test AC6)

### Change Log

- 2026-06-25: Story 6.5 implementada (dev-story). Run-record por (cuenta, mes) en `_meta/reconciliation-runs.jsonl` (`build_run`/`append_run`), escrito y commiteado SIEMPRE por `reconcile_cartola` (se quitó el gate `if new:` para que la cartola perfecta sobreviva el refresh). `GET /reconciliation/periods` (`list_periods`) cruza el último run-record × `read_discrepancies(...).summary.total` (keyed por el `year_month` persistido de 6.5b) → `complete`/`pending`. Indicador "Períodos reconciliados" en `ReconciliationPage`. TC y meses-faltantes fuera de scope. 7 tests backend + 1 frontend; 587 passed/1 xfailed/2 rojos PRE-EXISTENTES, 0 regresiones nuevas. Status → review. Cierra Epic 6 (FR35).
- 2026-06-24: Story 6.5 creada (bmad-create-story). Alcance B (run-record + derivación) resuelto con Ary: `reconcile_cartola` deja run-record en `_meta/reconciliation-runs.jsonl` (commiteado aun con 0 diferencias), endpoint `GET /reconciliation/periods` cruza runs × discrepancias-abiertas, indicador en el dashboard. TC y enumeración de meses faltantes fuera de scope (2 preguntas para Ary). FR35 / cierre de Epic 6.

## Review Findings

Code-review (3 capas: Blind Hunter + Edge Case Hunter + Acceptance Auditor) del working tree completo (6.5 + 6.5b/6.4 sin commitear), 2026-06-25. Acceptance Auditor: **AC1–AC7 PASS (7/7)**. 0 decision-needed, 0 patch, 2 defer nuevos, 13 dismiss. Los hallazgos que resurgieron de 6.5b (padding-contaminación = limitación documentada aceptada por Ary; `year_month=period.end` multi-mes = defer ya registrado) y de 6.4 (`fmt`/`closeSelected`) ya fueron adjudicados en sus propios reviews — no re-litigados.

- [x] [Review][Defer] `reconciled_at` lexicográfico asume formato ISO consistente [backend/app/api/v1/reconciliation/service.py:161] — deferred, hardening low-pri (hoy `ts` sale de un único code path ISO, el "último gana" es correcto incl. en empate via orden de append; frágil solo si el formato de `ts` se diversifica).
- [x] [Review][Defer] runs JSONL append-only sin compactación + lectura O(n) por request de `/periods` [pipeline/importers/reconcile.py:459, backend/app/api/v1/reconciliation/service.py:155] — deferred, pre-existing class (mismo patrón que `cartola-discrepancies.jsonl`; cada re-reconciliación appendea un run nuevo, `list_periods` los escanea todos. Sin daño en el volumen actual; compactar/snapshot si el archivo crece).
