# Story 6.5b: Reconciliación period-aware (el período es un campo, no la fecha de la tx)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **contador del family office**,
I want que **la reconciliación trate el período del estado de cuenta como un dato propio (distinto de la fecha de cada transacción) y que el matching no genere diferencias falsas en el borde del período**,
so that **las reconciliaciones cuadren aunque un movimiento tenga fecha de un período pero aparezca en la cartola de otro (corte/facturación), y para que el estado por período (6.5) se calcule sobre el período correcto**.

> **Contexto:** destapado al diseñar 6.5. El motor de reconciliación bucketea hoy por la **fecha de la transacción**, no por el **período del estado de cuenta** — son distintos (una compra del 28-abr puede caer en el estado de mayo por la fecha de cierre). Sin un campo de período explícito, la reconciliación usa la fecha y no cuadra. Esta story hace la reconciliación **period-aware de punta a punta**. 6.5 (estado de período) depende de ella.

## Problema (con evidencia del código)

El **período del estado de cuenta YA existe** a nivel de cartola (`model.period.start`/`model.period.end` en el schema canónico), pero **no se propaga** a la reconciliación, que cae en la fecha de la transacción:

1. **Discrepancias sin período.** `build_discrepancy` ([discrepancy_writer.py:23](pipeline/importers/discrepancy_writer.py#L23)) NO guarda período. El servicio deriva el mes con `_year_month(entry)` = primeros 7 chars de `cartola.date`/`laudus.date` ([service.py:59](backend/app/api/v1/reconciliation/service.py#L59)) → **fecha de la tx**, no período del estado.
2. **Ventana de carga exacta = falsos `missing-in-laudus` en el borde.** `load_laudus_entries` en `reconcile_cartola` carga Laudus con fecha en `[period_start, period_end]` **exacto** ([reconcile.py:385](pipeline/importers/reconcile.py#L385)), pero `match()` tolera ±3 días ([matching_engine.py:159](pipeline/importers/matching_engine.py#L159)). Un asiento Laudus fechado 1-2 días fuera de la ventana **nunca se carga**, así que la tolerancia no lo alcanza → la línea de cartola del borde queda `missing-in-laudus` aunque sí exista en Laudus. (Es el "boundary slop" residual del Epic 9.)
3. **TC: compras posteadas sin período.** `correct_tc_cartola` postea las compras itemizadas con `date=tx.date` (fecha de compra) y meta `{operation_type, batch_id, bank_account_id}` — **sin período** ([tc_correction.py:95](pipeline/importers/tc_correction.py#L95)). Una compra del 28-abr en el estado de mayo queda bucketeada en abril. (La TC **no** hace matching por línea — postea; su ventana de pago ya es ±75d. Así que el problema de TC NO es el matching, es la **metadata de período** en los asientos.)

## Acceptance Criteria

1. **AC1 — Campo de período en cada discrepancia.** `build_discrepancy` acepta y persiste `year_month` (string `YYYY-MM`). `reconcile_cartola`/`reconcile_and_build` lo setean = `model.period.end` (el cierre del estado). El campo es el **período del estado de cuenta**, distinto de `cartola.date`/`laudus.date`.
2. **AC2 — El servicio agrupa/filtra por el período persistido.** `_year_month(entry)` prefiere `entry["year_month"]` si está; si no (discrepancias viejas), cae al derivado de la fecha (backward-compat). `read_discrepancies(year_month=...)` y el summary quedan keyed por período de estado → el filtro de mes del dashboard (6.4) ahora filtra por período, no por fecha de tx.
3. **AC3 — Ventana de matching cuenta corriente padeada.** En `reconcile_cartola`, `load_laudus_entries` carga `[period_start − DATE_TOLERANCE_DAYS, period_end + DATE_TOLERANCE_DAYS]` para que la tolerancia ±3d del matcher alcance los asientos del borde. Una línea de cartola del borde con su asiento Laudus 1-2 días fuera del período ahora **matchea** (no es `missing-in-laudus` falso).
4. **AC4 — `missing-in-cartola` acotado al período core.** Padear la ventana NO debe crear `missing-in-cartola` falsos del estado siguiente. Las discrepancias `missing-in-cartola` solo se emiten para asientos Laudus con fecha dentro de `[period_start, period_end]` (período core); los asientos del padding sin línea de cartola se descartan (pertenecen a estados adyacentes).
5. **AC5 — TC: metadata de período en los asientos posteados.** `build_tc_correction_entries`/`_meta` agregan `period: YYYY-MM` (= `model.period.end`) a la meta de cada asiento de corrección de TC (compras, pago, apertura), distinta de `date`. Así un asiento dated 28-abr del estado de mayo queda asociable a mayo.
6. **AC6 — Sin regresiones.** Los 6 tests de `test_reconcile_cartola.py` (6.1) y los de TC (6.2) siguen verdes: cartola perfecta = 0 diferencias, `value-mismatch`/`missing-in-cartola` bloqueantes intactos, dedup intacto, TC postea igual (solo suma la meta `period`).
7. **AC7 — Tests del comportamiento de borde.** Backend: (a) línea de cartola en `period_start` con Laudus en `period_start−2` → matchea (sin la fix era `missing-in-laudus`); (b) Laudus en `period_end+2` sin línea de cartola → NO se emite `missing-in-cartola` (acotado); (c) Laudus dentro del core sin línea → SÍ `missing-in-cartola`; (d) la discrepancia lleva `year_month` = período del estado y el servicio agrupa por él aunque la fecha de la tx sea otro mes; (e) asiento de corrección TC lleva meta `period`. `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` → 0 regresiones nuevas.

### Fuera de scope (explícito)

- **Estado de período / run-record / endpoint `/periods` / indicador** → eso es 6.5 (depende de esta story).
- **Reconciliación de TC por línea contra Laudus.** No existe (TC postea). El ciclo de facturación de TC no pasa por el matching; esta story solo le agrega la metadata de período a los asientos posteados.
- **Cambiar la tolerancia ±3d o la lógica de `match()`.** Solo se padea la *ventana de carga* y se acota `missing-in-cartola`; el clasificador no cambia.
- **Re-bucketear discrepancias viejas.** Las ya escritas sin `year_month` caen al derivado de la fecha (AC2 backward-compat); no se reescribe el JSONL histórico.

## Tasks / Subtasks

- [x] **Task 1 — Campo `year_month` en la discrepancia** (AC1, AC2)
  - [x] [discrepancy_writer.py](pipeline/importers/discrepancy_writer.py) `build_discrepancy`: agregado param `year_month: str | None = None`, persistido en el dict. `_dedup_key` intacto.
  - [x] [reconcile.py](pipeline/importers/reconcile.py) `process_match_result`: + param `year_month`, pasado en `_disc` → `build_discrepancy`. `reconcile_and_build` lo pasa a `process_match_result`.
  - [x] [service.py](backend/app/api/v1/reconciliation/service.py) `_year_month(entry)`: prefiere `entry["year_month"]`, fallback a la fecha (backward-compat). `read_discrepancies`/`pending_count` sin cambios.

- [x] **Task 2 — Ventana de matching padeada + `missing-in-cartola` acotado** (AC3, AC4)
  - [x] [reconcile.py](pipeline/importers/reconcile.py) `reconcile_cartola`: importado `DATE_TOLERANCE_DAYS` + `timedelta`; `load_laudus_entries` ahora carga `[period.start − tol, period.end + tol]`. `period_start` a `reconcile_and_build` sin cambios.
  - [x] Post-filtro `_in_core`: descarta las `missing-in-cartola` cuyo `laudus.date` cae fuera de `[period.start, period.end]`. Documentado el porqué.
  - [x] Verificado: `result["matched"]` no se afecta (las `missing-in-cartola` no tienen `cartola.line_no`, no entran a `diff_lines`).

- [x] **Task 3 — Metadata de período en los asientos de TC** (AC5)
  - [x] [tc_correction.py](pipeline/importers/tc_correction.py) `_meta(...)`: + `period` (= `model.period.end` `YYYY-MM`), pasado desde `build_tc_correction_entries` a los 3 call-sites (compra/abono, pago, apertura).

- [x] **Task 4 — Tests + verificación** (AC6, AC7)
  - [x] `backend/tests/test_reconcile_period_aware.py` (7 tests): (a) padding matchea el asiento del borde (date-mismatch, no missing-in-laudus); (b) padding NO crea missing-in-cartola del estado siguiente; (c) missing-in-cartola dentro del core SÍ se emite; (d) la discrepancia persiste `year_month` = período del estado + el servicio agrupa por él (no por la fecha) + fallback para discrepancias viejas; (e) el asiento de corrección TC lleva meta `period` distinta de `date`.
  - [x] `PYTHONUTF8=1 ... pytest backend/tests -q` → **581 passed, 1 xfailed, 2 failed** (los 2 rojos = `test_fava_edit_validator` PRE-EXISTENTES, no tocados; 0 regresiones nuevas). Sin cambios de front → tsc no aplica.

## Dev Notes

### Estado actual de los archivos que se tocan (leídos para esta story)

- **[pipeline/importers/reconcile.py](pipeline/importers/reconcile.py)** — `process_match_result` (línea 61) llama `build_discrepancy` vía `_disc` (no recibe `year_month` hoy → agregárselo). `reconcile_and_build` (línea 102) recibe `year_month` (línea 112) y llama `process_match_result` en la línea ~145. `reconcile_cartola` (línea 330) hace el `load_laudus_entries` exacto (línea 385) y appendea las discrepancias (línea 397-399); `year_month = model.period.end.strftime("%Y-%m")` ya se calcula (línea 371). Tiene `model.period.start`/`.end` para el core.
- **[pipeline/importers/matching_engine.py](pipeline/importers/matching_engine.py)** — `DATE_TOLERANCE_DAYS = 3` (línea 19). `load_laudus_entries(target_dir, account, period_start, period_end)` filtra por `period_start <= e.date <= period_end` (línea 81). `match()` usa `abs((cl.date - le.date).days) <= DATE_TOLERANCE_DAYS` (línea 159) y emite `missing-in-cartola` para Laudus no usados (línea 171-174). **No tocar `match()`/`_classify`/tolerancia.**
- **[pipeline/importers/discrepancy_writer.py](pipeline/importers/discrepancy_writer.py)** — `build_discrepancy` (línea 23, shape del record). `_dedup_key` = `(batch_id, line_no, je_id, state)` (línea 19) — el período NO entra al dedup.
- **[backend/app/api/v1/reconciliation/service.py](backend/app/api/v1/reconciliation/service.py)** — `_year_month` (línea 59, el punto a cambiar a "prefiere persistido"); `read_discrepancies` (línea 81) y `pending_count` lo consumen.
- **[pipeline/importers/tc_correction.py](pipeline/importers/tc_correction.py)** — `_meta` (línea 95, agregar `period`); `build_tc_correction_entries` (línea 109, tiene `model` → pasar `model.period.end`). Story 6.2, done — cambio surgical (solo suma meta).

### Piezas a reusar (NO reescribir)

- `DATE_TOLERANCE_DAYS` de `matching_engine` (no hardcodear el 3 en `reconcile.py`).
- `load_laudus_entries` tal cual (ya acepta rango de fechas; solo cambia el rango que le pasa el caller).
- `_year_month` como único punto de derivación del período (cambiar ahí, no en cada caller).

### Anti-regresión

- **No cambiar el clasificador ni la tolerancia.** Solo la ventana de carga + el acotado de `missing-in-cartola`. Los estados/tolerancias de 9.6b quedan idénticos.
- **El padding sin el acotado de AC4 ROMPE `missing-in-cartola`** (mete asientos del estado siguiente). AC3 y AC4 van juntas — no implementar una sin la otra.
- **Dedup intacto:** `year_month` no entra a `_dedup_key`; re-correr el matching no debe duplicar ni cambiar el comportamiento de dedup de 6.1.
- **Backward-compat del servicio:** discrepancias viejas (sin `year_month`) deben seguir agrupándose por la fecha (fallback), no romper el dashboard.
- **TC:** agregar `period` a la meta no debe cambiar los montos ni el bean-check (es metadata); los tests de `test_tc_correction.py` siguen verdes.

### Testing standards

- Backend: pytest en `backend/tests/`, `PYTHONUTF8=1` + `venv/Scripts/python.exe` (gotcha Windows). Fixtures de reconcile en `test_reconcile_cartola.py` (cartola staged + Laudus `.beancount` reales + `ledger_root` temp). Para los casos de borde, controlar las fechas de los asientos Laudus respecto de `model.period.start/end`.

### Project Structure Notes

- Todo en módulos existentes (`reconcile.py`, `discrepancy_writer.py`, `matching_engine.py` solo lectura de la constante, `tc_correction.py`, `reconciliation/service.py`). Sin archivos nuevos. Sin cambios de schema persistido salvo el campo `year_month` que se suma al record JSONL (additive).

### References

- [Source: _bmad-output/implementation-artifacts/6-5-cierre-periodo-reconciliacion.md] — la story que destapó esto; 6.5 (estado de período) **depende** de AC1/AC2 de acá (campo período en la discrepancia).
- [Source: pipeline/importers/reconcile.py#reconcile_cartola] — ventana de carga exacta (línea 385), `year_month` ya calculado (línea 371), threading de discrepancias.
- [Source: pipeline/importers/matching_engine.py] — `DATE_TOLERANCE_DAYS`, `load_laudus_entries`, `match()` (missing-in-cartola en línea 171).
- [Source: pipeline/importers/tc_correction.py] — flujo TC postea (no matchea); ventana de pago ±75d; `_meta` sin período.
- [Source: backend/app/api/v1/reconciliation/service.py#_year_month] — derivación actual por fecha de tx.
- [Source: _bmad-output/implementation-artifacts/6-1-wiring-promote-reconcile.md] — modelo A, estados, dedup.

### Review Findings (code-review 2026-06-24 — Blind + Edge + Auditor)

- [x] [Review][Decision → ACEPTADO] **Aceptado como limitación documentada (Ary, 2026-06-25):** el spec acotó a conciencia la dirección peligrosa (`missing-in-cartola`); endurecer el residual lado-cartola choca con AC3 (que exige matchear el contraparte out-of-core del borde). Sin cambio de código. — El padding de la ventana contamina el matcher más allá de `missing-in-cartola` — `_in_core` ([reconcile.py:412-425](pipeline/importers/reconcile.py#L412-L425)) solo acota `missing-in-cartola`. La ventana padeada ±tol también carga asientos Laudus de estados ADYACENTES en `match()`; una línea de cartola del borde puede consumir uno de esos (vía `_acceptable` = amount-match **o** desc≥0.85, [matching_engine.py:122-128](pipeline/importers/matching_engine.py#L122)) y producir `date-mismatch`/`value-mismatch`/`description-mismatch` atribuido al período actual, o degradar un `missing-in-laudus` real a un mismatch blando. Tensión con AC3 (que SÍ requiere matchear el contraparte out-of-core del borde, test (a)): no se puede distinguir "contraparte legítima del borde" de "vecino que coincide por descripción" sin decidir la semántica. La dirección peligrosa (`missing-in-cartola`, que crea bloqueantes/plata) YA está acotada; el residual es lado-cartola y auto-surfacing (la cartola es fuente de verdad, todo lo revisa el contador). Tests (B2/B8): ningún test cubre el caso colisión-de-descripción/monto con un asiento adyacente en el borde de la tolerancia. Fuentes: blind+edge.
- [x] [Review][Defer] Statement multi-mes colapsa a `year_month = period.end` [pipeline/importers/reconcile.py:384] — deferred, pre-existing (cartolas son mensuales; ver deferred-work.md)

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Opus 4.8, 1M context)

### Debug Log References

- `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` → 581 passed, 1 xfailed, 2 failed (`test_fava_edit_validator` PRE-EXISTENTES, no tocados).
- Tests nuevos: `pytest backend/tests/test_reconcile_period_aware.py -q` → 7 passed.

### Completion Notes List

- **Threading del período (AC1/AC2):** el campo `year_month` se persiste en `build_discrepancy`; se threadea `reconcile_and_build → process_match_result → _disc → build_discrepancy` (= `model.period.end`, que `reconcile_cartola` ya calculaba). El servicio `_year_month` prefiere el persistido y cae a la fecha de la tx para discrepancias viejas (backward-compat verificado en test).
- **Ventana padeada + acotado (AC3/AC4):** `reconcile_cartola` carga Laudus en `[period.start − DATE_TOLERANCE_DAYS, period.end + DATE_TOLERANCE_DAYS]` para que el match del borde alcance su contraparte. Post-filtro `_in_core` descarta las `missing-in-cartola` fuera del período core (los asientos del padding sin línea de cartola pertenecen a estados adyacentes). `matched` no se ve afectado (las `missing-in-cartola` no aportan `cartola.line_no`).
- **Matiz observado:** una línea del borde que antes era `missing-in-laudus` falso ahora matchea como `date-mismatch` (soft, las fechas exactas difieren 1-2d), NO como `perfect` — porque `_classify` exige fecha exacta. Es el comportamiento correcto (matcheó su contraparte, queda una diferencia blanda revisable), no un falso faltante. El test (a) lo refleja.
- **TC (AC5):** metadata `period` agregada a los 3 tipos de asiento de corrección, distinta de `date` (una compra del 28-abr lleva `period: 2026-03` si el estado cierra en marzo). Cambio surgical en `_meta` + un cómputo de `year_month` en `build_tc_correction_entries`.
- **Sin regresiones (AC6):** los 6 tests de `test_reconcile_cartola.py` (6.1) y los de `test_tc_correction.py` (6.2) verdes.
- **Sin commit aún** (working tree, branch `main`).

### File List

- `pipeline/importers/discrepancy_writer.py` (MODIFICADO — `build_discrepancy` + param/campo `year_month`)
- `pipeline/importers/reconcile.py` (MODIFICADO — imports `timedelta`/`DATE_TOLERANCE_DAYS`; `process_match_result` + `year_month`; `reconcile_and_build` threadea `year_month`; `reconcile_cartola` ventana padeada + filtro `_in_core`)
- `pipeline/importers/tc_correction.py` (MODIFICADO — `_meta` + `period`; `build_tc_correction_entries` computa `year_month` y lo pasa a los 3 call-sites)
- `backend/app/api/v1/reconciliation/service.py` (MODIFICADO — `_year_month` prefiere el período persistido)
- `backend/tests/test_reconcile_period_aware.py` (NUEVO — 7 tests, casos a-e de AC7)

### Change Log

- 2026-06-24: Story 6.5b implementada (dev-story). Campo `year_month` en discrepancias (period.end) + servicio agrupa por período persistido (fallback a fecha); ventana de matching cuenta corriente padeada ±DATE_TOLERANCE_DAYS + `missing-in-cartola` acotado al período core; metadata `period` en los asientos de corrección de TC. 7 tests nuevos; 581 passed/1 xfailed/2 rojos PRE-EXISTENTES (fava_edit_validator), 0 regresiones nuevas. Status → review. Sin commit aún.
- 2026-06-24: Story 6.5b creada (bmad-create-story). Destapada al diseñar 6.5: el motor bucketea por fecha de tx, no por período del estado. Scope (decisión Ary, dividir): campo `year_month` en discrepancias (period.end), servicio agrupa por período persistido (fallback a fecha), ventana de carga cuenta corriente padeada ±3d + `missing-in-cartola` acotado al core, metadata `period` en los asientos de TC. 6.5 (estado de período) depende de esta. Hallazgo clave: la TC postea (no matchea por línea), así que su problema de período es metadata, no matching.
