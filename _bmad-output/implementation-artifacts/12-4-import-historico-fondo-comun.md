# Story 12.4: Importar histórico y apertura del Fondo Común

Status: ready-for-dev

## Story

As contador (usuario del sistema),
I want el histórico contable del Fondo Común importado al ledger desde la fecha de corte descubierta en Laudus,
so that los números de FFCC/JAB existan en el sistema y sean navegables como los de EAG.

## Acceptance Criteria

1. **Given** el libro RUT2 en Laudus,
   **When** corre la sonda read-only sobre los primeros asientos del libro (Task 0 — decisión Ary 2026-07-10: no se le pide nada al contador),
   **Then** quedan documentados en el Dev Agent Record: la **fecha de corte** (primer asiento del libro) y la **forma de la apertura** (¿JE real con `journalentryid ≠ 0` — precedente EAG JE 140 — o filas sintéticas `id == 0` que el writer DROPEA?),
   **And** la sonda no escribe nada (ni ledger, ni git, ni import-log).

2. **Given** la fecha de corte y la forma de la apertura descubiertas,
   **When** corre la importación multi-libro contra el libro RUT2 (backfill desde esa fecha),
   **Then** los asientos quedan en cuentas de RUT2 (`imports/laudus-rut2/*.beancount`) y el asiento de apertura entra según la **convención firmada 12.1 §3** — mecanismo primario `Liabilities:FFCC:Apertura-211005` (espejo Laudus, ya pre-creado por 12.3); `Equity:FFCC:Apertura`/`Equity:JAB:Apertura` SOLO como respaldo/plug, y un plug **nunca cruza entidades** (FR53 con la letra supersedida por el artefacto §3 — NO re-litigar).

3. **Given** el ledger post-import,
   **When** se compara contra el estado pre-import,
   **Then** no existe ningún asiento nuevo bajo cuentas de EAG (NFR20): balance consolidado EAG + report_rows **byte-idénticos** pre/post (patrón gate 11.1/12.3; fail-safe: dump vacío = FAIL),
   **And** `bean-check` sale en 0 (NFR21),
   **And** la suite completa pasa sin regresiones (baseline **843 passed / 1 xfailed**).

4. **Given** cada corrida de import RUT2,
   **When** termina (éxito o falla),
   **Then** queda registrada en `_meta/import-log.jsonl` con timestamp, registros procesados y errores (NFR13, NFR10), con `importer="laudus-rut2"`,
   **And** el indicador de frescura de EAG ("Datos de Laudus al:") NO avanza (ya testeado en 12.2 — no romperlo).

5. **Given** el árbol de 12.3 con las 309 hojas pre-creadas,
   **When** termina el import,
   **Then** la cuarentena RUT2 es **≈ 0** (`_new-accounts-pending-rut2.beancount` sin codes, o con un puñado explicado). Pending masivo = señal de **error de ruteo**, no de cuentas faltantes → investigar, NO promover en masa.

6. **Given** los datos importados,
   **When** se consulta per-entity FFCC/JAB por los endpoints/dashboards existentes,
   **Then** responden con datos (balance y movimientos visibles) — verificación de humo, sin tocar el motor de reportes ni el frontend (el reporte con plantilla propia es 13.1; la reconciliación al peso es 12.5).

## Tasks / Subtasks

- [ ] Task 0: Sonda read-only sobre los primeros asientos del libro RUT2 (AC: 1)
  - [ ] Script `_forense_sonda_primeros_asientos_rut2.py` en `_bmad-output/planning-artifacts/` (patrón `_forense_*.py`, re-ejecutable). Read-only estricto: `login(book=RUT2)` + `verify_book_identity(book)` (reusar `pipeline/services/laudus_service.py` — ya asserta "ACTIVO FFCC") + GET `/accounting/ledger` de los primeros meses del libro. Requiere `LAUDUS_COMPANYVATID_RUT2` en el `.env` local (dotenv ya la carga; NFR8: nunca commitear el valor).
  - [ ] Responder y documentar en el Dev Agent Record: (a) **fecha del primer asiento** = fecha de corte; (b) **forma de la apertura**: ¿JE real (`journalentryid ≠ 0`) o filas sintéticas `id == 0`? — ver TRAP crítico en Dev Notes; (c) ¿la apertura usa la cuenta `211005`?; (d) ¿hay asientos con fecha **≤ 2020-12-31**? (los 311 opens RUT2 son `2020-12-31` → asiento anterior = bean-check "account not open"); (e) ¿la cuenta `13` (hoja rama-vacía) tiene movimientos? (`_min_account_number(RUT2)` = `"111001"` → `accountNumberFrom` la excluiría si la API compara numérico); (f) actividad USD en 111003/115007/613007 (informativo — ver Dev Notes, el writer es CLP-only).
  - [ ] GATE de la task: sin las respuestas (a) y (b) NO se corre ningún import.

- [ ] Task 1: Wiring previo al primer import — include + env (AC: 2, 3)
  - [ ] `render.yaml`: agregar `LAUDUS_COMPANYVATID_RUT2` con `sync: false` junto al bloque Laudus existente (`render.yaml:36-42`) — defer 12.2 #1.
  - [ ] Crear `ledger/imports/laudus-rut2/_init.beancount` (patrón exacto de `imports/laudus/_init.beancount`: comentario placeholder para que el glob matchee).
  - [ ] Crear `ledger/imports/_new-accounts-pending-rut2.beancount` con el header canónico del writer (`_PENDING_HEADER_TEMPLATE` de `beancount_writer.py:38-46` con `pending_file="_new-accounts-pending-rut2.beancount"`) — así la primera corrida lo regenera byte-idéntico si no hay pendings.
  - [ ] `ledger/main.beancount`: agregar `include "imports/laudus-rut2/*.beancount"` + `include "imports/_new-accounts-pending-rut2.beancount"` (después de los includes homólogos EAG, líneas 34-36).
  - [ ] `bean-check` exit 0 (trivial — archivos vacíos) y **commit de este wiring ANTES de la primera corrida**. Esto resuelve el GATE del include (defer 12.2 #3) por diseño: con el include activo desde antes, el `bean_check` interno de `run_import` ve los archivos RUT2 desde la corrida 1 y su rollback protege — ninguna corrida commitea datos que bean-check no vio. (Default documentado — ver Decisiones.)

- [ ] Task 2: Mecanismo de apertura según el veredicto de la sonda (AC: 2)
  - [ ] **Caso (a) — apertura es JE real (`id ≠ 0`, como EAG JE 140):** no hay trabajo extra — el importador la rutea solo (`211005` → `Liabilities:FFCC:Apertura-211005`, pre-creada por 12.3, self-balancing).
  - [ ] **Caso (b) — apertura sintética (`id == 0`, el writer la dropea):** generar un archivo de apertura one-off `ledger/opening-rut2.beancount` (+ su include en main.beancount, espejo de `opening-2021.beancount`) con los saldos de corte leídos de Laudus, contrapartida `Equity:FFCC:Apertura` para cuentas FFCC y `Equity:JAB:Apertura` para cuentas JAB — **el plug nunca cruza entidades** (§3.4). NO usar `bootstrap/generate_opening_balances` sin darle scoping por libro primero (defer 12.2 #4: su índice last-wins resuelve las 31 colisiones a RUT2 desde 12.3 — re-correrlo para EAG hoy corrompería; si se reusa, agregarle `book` como `load_account_index(path, book)` del writer). Default recomendado: script one-off nuevo, no rehabilitar el bootstrap.
  - [ ] Si la sonda encontró asientos ≤ 2020-12-31 (Task 0.d): adelantar la fecha de los 311 opens del bloque RUT2 en `accounts.beancount` (edit mecánico del bloque, re-correr bean-check + re-gate 0-diffs EAG). Ajustar también `test_fecha_y_monedas_de_los_opens` de `test_rut2_accounts_tree.py`, que pinnea `2020-12-31`.
  - [ ] Advertencia de Valentina (§3.5, obligatoria de propagar): el monto de las Equity puede ser un **plug grande** — es artefacto de "Laudus solo para gastos", NO patrimonio real. Dejarlo dicho en el Dev Record si aparece.

- [ ] Task 3: Corrida de import histórico (AC: 2, 4, 5)
  - [ ] Corrida local por CLI (no hay cron/endpoint RUT2 — ver Decisiones): `IMPORTER_BOOK=RUT2 IMPORTER_MODE=backfill IMPORTER_FROM_DATE=<fecha de corte Task 0> IMPORTER_GIT_ENABLED=true python -m pipeline.importers.laudus_run` (+ `PYTHONUTF8=1` en Windows). El pipeline 12.2 ya hace todo: verify identidad antes del primer read, índice scoped, subdir propio, bean-check con rollback, import-log, commit+push.
  - [ ] Verificar post-corrida: `import-log.jsonl` con `importer="laudus-rut2"`, `success=true`, conteos sanos; indicador EAG sin avanzar (AC4); `_new-accounts-pending-rut2.beancount` ≈ vacío (AC5 — si hay pendings masivos: STOP, es ruteo roto, rollback/investigar).
  - [ ] Verificar que el asiento de apertura quedó donde manda §3 (grep de `Apertura-211005` / `Equity:FFCC:Apertura` / `Equity:JAB:Apertura` en `imports/laudus-rut2/` y opening-rut2 si existe).

- [ ] Task 4: Gates anti-regresión (AC: 3, 6)
  - [ ] Gate 0-diffs EAG: dump de balance consolidado EAG + report_rows ANTES del primer commit de esta story y DESPUÉS del import → byte-idéntico (patrón 11.1/12.3: 56 cuentas / 19.989 filas de baseline; fail-safe dump vacío = FAIL; correr con `PYTHONPATH` correcto + `PYTHONUTF8=1`).
  - [ ] `bean-check` exit 0 sobre el ledger completo (borrar picklecaches antes — lección del repo).
  - [ ] Suite completa: `PYTHONUTF8=1 pytest backend/tests pipeline -q` → sin regresiones sobre 843/1.
  - [ ] Humo per-entity: `balance_sheet_via_beancount` / ledger-entries para FFCC y JAB devuelven datos reales (AC6). De paso, verificar el defer 11.2 de frontend: si `getLedgerCategory` (`frontend/src/utils/ledgerAnalytics.ts:48-52`) manda registros RUT2 a `other` y los agregados del dashboard los ocultan, DOCUMENTAR el hallazgo (queda para 13.1 / deferred-work) — NO tocar el frontend en esta story.

- [ ] Task 5: Tests y cierre (AC: 2, 3, 5)
  - [ ] Tests nuevos sobre el ledger real (patrón `test_rut2_accounts_tree.py`): main.beancount incluye los globs/archivos RUT2; si existe `opening-rut2.beancount`, cada transacción balancea y su contrapartida Equity no cruza entidades; ningún archivo de `imports/laudus-rut2/` referencia cuentas con 2º segmento fuera de {FFCC, JAB, sus PendingReview}.
  - [ ] Actualizar `deferred-work.md`: marcar cerrados los defers de 12-2/12-3 que esta story resuelve (env render.yaml, include+gate, y generate_opening_balances SOLO si se tocó); anotar los nuevos que queden.
  - [ ] Commitear al cerrar (acuerdo retro). Nota: el histórico en sí ya viaja en los commits del importador (Task 3).

## Dev Notes

### TRAP crítico — el writer DROPEA la apertura si viene con `journalentryid == 0`

`beancount_writer._rows_to_jes` (`pipeline/writers/beancount_writer.py:157-160`) descarta filas con `journalentryid in (0, "0", None)` — filtro defensivo contra los "Saldo anterior" sintéticos de Laudus. **Si la apertura de RUT2 viene como id==0, el import la descarta EN SILENCIO y FR53 no se cumple solo corriendo el importador** — de ahí la Task 0 y el mecanismo (b) de la Task 2. Precedente EAG verificado: la apertura entró como **JE real `id: "140"`** ("Saldo inicial", `ledger/imports/laudus/2021-01.beancount:1-16`) contra `Liabilities:EAG:Apertura-211005` — el filtro no la tocó. Lo más probable es que RUT2 se comporte igual (caso (a)), pero la sonda lo confirma, no se asume.

### La convención §3 SUPERSEDE la letra de FR53 — no re-litigar

El epic dice "apertura rutea a la cuenta de Equity de apertura". El artefacto firmado (`clasificacion-contable-rut2-firmada-2026-07-11.md` §3, adjudicación Valentina) manda otra cosa y es LA autoridad: primario = `Liabilities:FFCC:Apertura-211005` (espejo Laudus; existe en el plan y 12.3 la pre-creó — `accounts.beancount:2289`); las DOS Equity (`accounts.beancount:4286,4293`, codes 900001/900002) son solo respaldo/plug; plug nunca cruza entidades (§3.4). El sprint-status ya lo advierte en la línea de esta story.

### Hechos verificados del código (2026-07-11, no re-derivar)

- **Fundaciones 12.2 ya en main (e9e21a1):** `run_import("RUT2", ...)` funciona end-to-end — `BookConfig` RUT2 (`pipeline/config/laudus_config.py:75-90`): subdir `laudus-rut2`, pending propio, entidades {FFCC, JAB}, cuarentena por dígito de raíz (1-4→FFCC, 6-8→JAB); `verify_book_identity` asserta "ACTIVO FFCC" antes del primer read, con retry 401; índice scoped por libro; import-log con `importer="laudus-rut2"`; git add ya parameterizado por libro (`laudus_run.py:482-487`). **Esta story casi no escribe código de pipeline — es wiring + operación + verificación.**
- **`main.beancount` HOY no tiene los includes RUT2** (líneas 31-37: solo laudus/, cartolas/, pending EAG, manual/). `imports/laudus-rut2/` y el pending RUT2 **no existen en disco**. Un include de archivo inexistente / glob vacío rompe bean-check → patrón `_init.beancount` (Task 1).
- **`_min_account_number(book)`** (`laudus_run.py:323-327`): para RUT2 devuelve `"111001"` (min lexicográfico de los codes del libro, que incluyen `"13"` y `"900001"`) → se manda como `accountNumberFrom`. Si la API compara numérico, la cuenta `13` (hoja rama-vacía del plan) quedaría fuera del fetch — la sonda chequea si tiene movimientos (Task 0.e). Si los tiene: decidir ahí (probablemente forzar `accountNumberFrom="1"` para RUT2).
- **Writer CLP-only** (`_fmt_amount`, `beancount_writer.py:120-121`): toda JE se emite en CLP — el riesgo bean-check del defer 12.3 (cuentas cash-US$ 111003/115007/613007 abiertas solo-CLP) NO se dispara vía importador. Solo re-aparece si el archivo de apertura one-off (caso (b)) escribiera USD a mano — no hacerlo; la sonda releva la actividad USD como dato informativo (Task 0.f).
- **Backfill** (`run_import` mode="backfill"): regenera desde `from_date` con `replace=True` — usar la fecha de corte descubierta, NO el default `2021-01-01` (`_DEFAULT_FROM_DATE`, `laudus_run.py:33`).
- **Import-log freshness:** el lector de `/sync/status` filtra `importer == "laudus"` — RUT2 escribe `"laudus-rut2"` y no avanza el indicador (testeado en 12.2: `test_import_log_de_rut2_no_avanza_el_indicador_eag`). No romperlo.
- **Backend Render clona el ledger al startup** — tras el push del histórico, refrescar = redeploy o `/sync/trigger` (fetch+reset). Para el humo per-entity (Task 4) sirve el backend local contra el ledger local.

### Decisiones con default documentado (auto-aprobadas per project-context; el dev documenta desvíos en el Dev Record)

1. **Include ANTES del primer import** (Task 1): resuelve el gate del defer 12.2 #3 — el bean-check interno de `run_import` valida los archivos RUT2 desde la corrida 1, con rollback. La alternativa (importar primero, incluir después) deja una ventana donde se commitea data no validada — descartada.
2. **Apertura**: caso (a) sin trabajo; caso (b) archivo one-off nuevo, NO rehabilitar `generate_opening_balances` sin scoping por libro.
3. **Corrida local por CLI, sin cron RUT2**: no se crea cron ni endpoint para RUT2 en esta story — el histórico es una operación one-shot (backfill) y la frecuencia futura del libro es decisión de producto pendiente (¿el Fondo Común tiene movimiento vivo?). El defer 12.2 #5 (choque de rebase de import-log entre clones) recién aplica cuando exista un cron RUT2 — dejarlo diferido.
4. **Asientos ≤ 2020-12-31** (si la sonda los encuentra): adelantar la fecha de los 311 opens RUT2 (edit mecánico del bloque + re-gate). Alternativa de filtrar el histórico = mutilar datos, descartada.

### Qué NO hacer (scope guard)

- NO reconciliar contra el balance de Laudus — eso es 12.5 (criterio de cierre del epic, DoD).
- NO tocar el motor de reportes ni el frontend más allá de verificar que per-entity FFCC/JAB responde con datos (el hallazgo `getLedgerCategory` se documenta, no se arregla acá).
- NO cartolas ni TC (estado-1 firmado; 871005/873005 son hojas de gasto normales — §5 del artefacto).
- NO promover pendings en masa si la cuarentena no es ≈ 0 — es síntoma de ruteo roto.
- NO tocar cuentas/datos EAG; NO validar dígito verificador del RUT (placeholder por diseño).

### Inteligencia de stories previas (12.2/12.3)

- **Suite**: `PYTHONUTF8=1` obligatorio en Windows. Baseline actual **843 passed / 1 xfailed** (12.2 done post-ratificación).
- **bean-check**: borrar `*.picklecache` antes de validar (el cache por mtime no ve archivos nuevos que entran por glob — mismo workaround dentro de `bean_check()`).
- **Gate 0-diffs**: correr los scripts con `PYTHONPATH=<checkout>` explícito — los tests resuelven `backend.app.*` por rootdir, scripts sueltos no.
- **Si se trabaja en worktree**: fast-forwardear a main local ANTES de empezar (12.2 y 12.3 lo necesitaron; esta story depende de e9e21a1).
- **Patrón de verificación 12.3**: tests sobre el LEDGER REAL (no fixtures) para pinnear el estado del árbol — reusar para los includes/apertura.

### References

- [Source: _bmad-output/planning-artifacts/epics-segundo-rut.md#Story 12.4] — FR53, NFR20/21/13/10
- [Source: _bmad-output/planning-artifacts/clasificacion-contable-rut2-firmada-2026-07-11.md#3] — convención de apertura firmada (supersede FR53 literal); §3.5 advertencia plug
- [Source: _bmad-output/planning-artifacts/discovery-segundo-rut-intake-2026-06-30.md#F] — apertura = primeros asientos del libro (decisión Ary)
- [Source: _bmad-output/implementation-artifacts/deferred-work.md#12-2 / #12-3] — los 5 defers que esta story recoge
- [Source: pipeline/writers/beancount_writer.py:157-160] — filtro `journalentryid == 0` (el TRAP)
- [Source: pipeline/importers/laudus_run.py:323-327,363-521] — `_min_account_number`, `run_import`, CLI `IMPORTER_BOOK`
- [Source: pipeline/config/laudus_config.py:75-90,108-120] — BookConfig RUT2, `LAUDUS_COMPANYVATID_RUT2`
- [Source: ledger/main.beancount:31-37; ledger/imports/laudus/_init.beancount] — includes actuales + patrón placeholder
- [Source: ledger/imports/laudus/2021-01.beancount:1-16] — precedente apertura EAG (JE real id=140)
- [Source: render.yaml:36-42] — bloque env Laudus (sync: false)
- [Source: _bmad-output/implementation-artifacts/12-2-importador-multi-libro.md; 12-3-arbol-cuentas-rut2.md] — Dev Records con las fundaciones y gotchas

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
