# Story 12.4: Importar histórico y apertura del Fondo Común

Status: review

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

- [x] Task 0: Sonda read-only sobre los primeros asientos del libro RUT2 (AC: 1)
  - [x] Script `_forense_sonda_primeros_asientos_rut2.py` en `_bmad-output/planning-artifacts/` (patrón `_forense_*.py`, re-ejecutable). Read-only estricto: `login(book=RUT2)` + `verify_book_identity(book)` (reusar `pipeline/services/laudus_service.py` — ya asserta "ACTIVO FFCC") + GET `/accounting/ledger` de los primeros meses del libro. Requiere `LAUDUS_COMPANYVATID_RUT2` en el `.env` local (dotenv ya la carga; NFR8: nunca commitear el valor).
  - [x] Responder y documentar en el Dev Agent Record: (a) **fecha del primer asiento** = fecha de corte; (b) **forma de la apertura**: ¿JE real (`journalentryid ≠ 0`) o filas sintéticas `id == 0`? — ver TRAP crítico en Dev Notes; (c) ¿la apertura usa la cuenta `211005`?; (d) ¿hay asientos con fecha **≤ 2020-12-31**? (los 311 opens RUT2 son `2020-12-31` → asiento anterior = bean-check "account not open"); (e) ¿la cuenta `13` (hoja rama-vacía) tiene movimientos? (`_min_account_number(RUT2)` = `"111001"` → `accountNumberFrom` la excluiría si la API compara numérico); (f) actividad USD en 111003/115007/613007 (informativo — ver Dev Notes, el writer es CLP-only).
  - [x] GATE de la task: sin las respuestas (a) y (b) NO se corre ningún import.

- [x] Task 1: Wiring previo al primer import — include + env (AC: 2, 3)
  - [x] `render.yaml`: agregar `LAUDUS_COMPANYVATID_RUT2` con `sync: false` junto al bloque Laudus existente (`render.yaml:36-42`) — defer 12.2 #1.
  - [x] Crear `ledger/imports/laudus-rut2/_init.beancount` (patrón exacto de `imports/laudus/_init.beancount`: comentario placeholder para que el glob matchee).
  - [x] Crear `ledger/imports/_new-accounts-pending-rut2.beancount` con el header canónico del writer (`_PENDING_HEADER_TEMPLATE` de `beancount_writer.py:38-46` con `pending_file="_new-accounts-pending-rut2.beancount"`) — así la primera corrida lo regenera byte-idéntico si no hay pendings.
  - [x] `ledger/main.beancount`: agregar `include "imports/laudus-rut2/*.beancount"` + `include "imports/_new-accounts-pending-rut2.beancount"` (después de los includes homólogos EAG, líneas 34-36).
  - [x] `bean-check` exit 0 (trivial — archivos vacíos) y **commit de este wiring ANTES de la primera corrida**. Esto resuelve el GATE del include (defer 12.2 #3) por diseño: con el include activo desde antes, el `bean_check` interno de `run_import` ve los archivos RUT2 desde la corrida 1 y su rollback protege — ninguna corrida commitea datos que bean-check no vio. (Default documentado — ver Decisiones.)

- [x] Task 2: Mecanismo de apertura según el veredicto de la sonda (AC: 2)
  - [x] **Caso (a) — apertura es JE real (`id ≠ 0`, como EAG JE 140):** no hay trabajo extra — el importador la rutea solo (`211005` → `Liabilities:FFCC:Apertura-211005`, pre-creada por 12.3, self-balancing).
  - [x] **Caso (b) — apertura sintética (`id == 0`, el writer la dropea):** generar un archivo de apertura one-off `ledger/opening-rut2.beancount` (+ su include en main.beancount, espejo de `opening-2021.beancount`) con los saldos de corte leídos de Laudus, contrapartida `Equity:FFCC:Apertura` para cuentas FFCC y `Equity:JAB:Apertura` para cuentas JAB — **el plug nunca cruza entidades** (§3.4). NO usar `bootstrap/generate_opening_balances` sin darle scoping por libro primero (defer 12.2 #4: su índice last-wins resuelve las 31 colisiones a RUT2 desde 12.3 — re-correrlo para EAG hoy corrompería; si se reusa, agregarle `book` como `load_account_index(path, book)` del writer). Default recomendado: script one-off nuevo, no rehabilitar el bootstrap.
  - [x] Si la sonda encontró asientos ≤ 2020-12-31 (Task 0.d): adelantar la fecha de los 311 opens del bloque RUT2 en `accounts.beancount` (edit mecánico del bloque, re-correr bean-check + re-gate 0-diffs EAG). Ajustar también `test_fecha_y_monedas_de_los_opens` de `test_rut2_accounts_tree.py`, que pinnea `2020-12-31`.
  - [x] Advertencia de Valentina (§3.5, obligatoria de propagar): el monto de las Equity puede ser un **plug grande** — es artefacto de "Laudus solo para gastos", NO patrimonio real. Dejarlo dicho en el Dev Record si aparece.

- [x] Task 3: Corrida de import histórico (AC: 2, 4, 5)
  - [x] Corrida local por CLI (no hay cron/endpoint RUT2 — ver Decisiones): `IMPORTER_BOOK=RUT2 IMPORTER_MODE=backfill IMPORTER_FROM_DATE=<fecha de corte Task 0> IMPORTER_GIT_ENABLED=true python -m pipeline.importers.laudus_run` (+ `PYTHONUTF8=1` en Windows). El pipeline 12.2 ya hace todo: verify identidad antes del primer read, índice scoped, subdir propio, bean-check con rollback, import-log, commit+push.
  - [x] Verificar post-corrida: `import-log.jsonl` con `importer="laudus-rut2"`, `success=true`, conteos sanos; indicador EAG sin avanzar (AC4); `_new-accounts-pending-rut2.beancount` ≈ vacío (AC5 — si hay pendings masivos: STOP, es ruteo roto, rollback/investigar).
  - [x] Verificar que el asiento de apertura quedó donde manda §3 (grep de `Apertura-211005` / `Equity:FFCC:Apertura` / `Equity:JAB:Apertura` en `imports/laudus-rut2/` y opening-rut2 si existe).

- [x] Task 4: Gates anti-regresión (AC: 3, 6)
  - [x] Gate 0-diffs EAG: dump de balance consolidado EAG + report_rows ANTES del primer commit de esta story y DESPUÉS del import → byte-idéntico (patrón 11.1/12.3: 56 cuentas / 19.989 filas de baseline; fail-safe dump vacío = FAIL; correr con `PYTHONPATH` correcto + `PYTHONUTF8=1`).
  - [x] `bean-check` exit 0 sobre el ledger completo (borrar picklecaches antes — lección del repo).
  - [x] Suite completa: `PYTHONUTF8=1 pytest backend/tests pipeline -q` → sin regresiones sobre 843/1.
  - [x] Humo per-entity: `balance_sheet_via_beancount` / ledger-entries para FFCC y JAB devuelven datos reales (AC6). De paso, verificar el defer 11.2 de frontend: si `getLedgerCategory` (`frontend/src/utils/ledgerAnalytics.ts:48-52`) manda registros RUT2 a `other` y los agregados del dashboard los ocultan, DOCUMENTAR el hallazgo (queda para 13.1 / deferred-work) — NO tocar el frontend en esta story.

- [x] Task 5: Tests y cierre (AC: 2, 3, 5)
  - [x] Tests nuevos sobre el ledger real (patrón `test_rut2_accounts_tree.py`): main.beancount incluye los globs/archivos RUT2; si existe `opening-rut2.beancount`, cada transacción balancea y su contrapartida Equity no cruza entidades; ningún archivo de `imports/laudus-rut2/` referencia cuentas con 2º segmento fuera de {FFCC, JAB, sus PendingReview}.
  - [x] Actualizar `deferred-work.md`: marcar cerrados los defers de 12-2/12-3 que esta story resuelve (env render.yaml, include+gate, y generate_opening_balances SOLO si se tocó); anotar los nuevos que queden.
  - [x] Commitear al cerrar (acuerdo retro). Nota: el histórico en sí ya viaja en los commits del importador (Task 3).

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

claude-fable-5 (Amelia, dev-story BMAD) — 2026-07-11, checkout principal (main).

### Debug Log References

- **Env local:** `LAUDUS_COMPANYVATID_RUT2` agregada a `.env` Y a `pipeline/.env` (ambos gitignoreados). Gotcha destapado: `load_dotenv()` en `laudus_config.py` camina hacia arriba desde `pipeline/config/` y encuentra **`pipeline/.env` PRIMERO** — el `.env` de la raíz nunca se lee cuando se corre un script (solo en modo interactivo/-c, que usa cwd). El valor es el placeholder documentado en el intake 1-bis ítem A (así se creó la empresa en Laudus; no es secreto, pero NFR8 se respeta: no commiteado).
- **Sonda (Task 0)** — `PYTHONUTF8=1 PYTHONPATH=. venv/Scripts/python _bmad-output/planning-artifacts/_forense_sonda_primeros_asientos_rut2.py`, identidad "ACTIVO FFCC" verificada, 38.510 filas [2000-01-01..2030-12-31]. **Veredicto completo:**
  - (a) **Fecha de corte = 2021-01-01** (igual que EAG); último asiento **2026-07-10** — el libro está VIVO (contabilidad al día). Filas/año: 2021:9009 · 2022:8836 · 2023:5977 · 2024:5792 · 2025:6071 · 2026:2825. 10.530 JEs.
  - (b) **Apertura = JE REAL `id=1` "Saldo Inicial"** (16 patas, suma 0). **0 filas sintéticas id==0 en TODO el libro** → el TRAP del writer no aplica; **caso (a)**, cero trabajo extra.
  - (c) 211005 usada por la apertura (−402.430.179) y por los "Comprobante de cierre/apertura" ANUALES de Laudus (±402.430.179 cada fin/inicio de año) — se espejan tal cual (espejo fiel).
  - (d) 0 asientos ≤ 2020-12-31 → los opens de 12.3 no se tocan.
  - (e) Cuenta "13": 0 movimientos → `accountNumberFrom="111001"` de `_min_account_number` es seguro.
  - (f) **100% CLP** (38.510/38.510); 0 filas no-CLP en 111003/115007/613007 → defer 12.3 resuelto con evidencia.
  - (+) Dry-run cuarentena: **0 de 243 codes** sin cuenta en el índice scoped → predijo pending=0 (se cumplió).
  - (+) Sumas por sub-entidad (filas reales): FFCC −14.822.194.074 / JAB +14.822.194.074 — flujo inter-entidad DENTRO de JEs (el fondo financia a la rama JAB), NO requiere plug (cada JE balancea). Las Equity de respaldo quedaron sin uso; advertencia §3.5 documentada: si algo les postea en el futuro, no es patrimonio real.
- **Corrida 1 (fallida, dato a salvo):** `git add` explotó porque `.gitignore:44` ignoraba `ledger/_meta/import-log.jsonl` — **bug del fix 5fec3b4** (2026-07-09, indicador de sync): agregó el path al commit del importer pero no lo des-ignoró; un path ignorado+untracked = `git add` exit 1 → TODA corrida (cron EAG incluido) fallaría en el commit. Ningún import de prod corrió aún con ese fix deployado (último commit importer en origin: 2026-07-09 16:08 UTC, anterior al fix 18:34 UTC) — 12.4 lo pisó primero. Arreglado en `e136393` (des-ignorar + nota). La línea failed quedó en el log con el error exacto (NFR10 ✓).
- **Corrida 2 (fallida en rebase):** working tree sucio (sprint-status.yaml modificado) — `git rebase` se niega con unstaged changes; en prod el clon está limpio, es un artefacto de correr desde el checkout de dev. El commit de datos `d73ce81` quedó local. Se commitearon los archivos de la story y la **corrida 3 cerró el ciclo canónico**: writer regeneró byte-idéntico (0 diffs de datos = prueba de idempotencia en vivo), solo import-log diffeó, commit `c8f4123` + **push `e9e21a1..c8f4123`**. Log final: línea failed (rebase) corregida + línea success=true.
- **Gate 0-diffs (Task 4):** dump ANTES (pre-wiring) = 56 cuentas balance consolidado EAG + 19.989 filas report_rows (fail-safe no-vacío OK). Dump DESPUÉS del import: **DIFF REAL detectado** — `query_date`/`meta.last_sync` del balance EAG avanzó 2026-07-08 → 2026-07-10 (montos idénticos, report_rows byte-igual). Causa: `balance_sheet_via_beancount` derivaba la fecha de `_max_transaction_date(entries)` sobre TODO el ledger → el asiento más fresco de RUT2 contaminaba la fecha "al" de EAG (clase NFR20/FR45). **Fix quirúrgico** (RED→GREEN): `_freshness_pattern(entity)` = la frescura se mide sobre el grupo de consolidación de la entidad (EAG+hijas → libro EAG, idéntico al máximo global pre-12.4; FFCC/JAB/FondoComun → libro RUT2), roots completos (`_ALL_ROOTS`, un asiento solo-P&L también cuenta). 3 tests nuevos (2 RED confirmados antes del fix). Re-gate: **byte-idéntico PASS** (incluye meta.last_sync → AC4 verificado también por esta vía).
- **bean-check:** exit 0 explícito post-import (picklecache borrado antes); además corrió DENTRO de cada corrida (gate interno de run_import).
- **Suite completa:** `PYTHONUTF8=1 pytest backend/tests pipeline -q` → **851 passed / 1 xfailed** (baseline 843/1 + 8 tests nuevos, 0 regresiones).
- **Humo per-entity (Task 4/AC6):** FFCC balance 24 cuentas / JAB 9 cuentas, last_sync 2026-07-10; ledger 2026: FFCC 1.075 filas / JAB 1.750 filas — con datos reales ✓. Hallazgos documentados en deferred-work (no tocados, scope guard): `FondoComun` en ledger_entries da 0 filas (grupos no soportados ahí; no alcanzable desde la UI — no está en VALID_ENTITIES); `getLedgerCategory` verificado con datos: activos JAB (prefijo 6, cat1 "ACTIVO - JAB") clasifican 'expenses' por el fallback → las patas banco pueden cancelar los totales de gasto JAB en los charts; activos FFCC y el pasivo 211005 → 'other'. Fix natural en 13.1.

### Completion Notes List

- **Veredicto de la sonda = caso (a):** la apertura de RUT2 es un JE real (id=1 "Saldo Inicial") self-balancing vía `Liabilities:FFCC:Apertura-211005` — exactamente el precedente EAG (JE 140). El importador la ruteó solo; las Equity de respaldo (`Equity:FFCC:Apertura`/`Equity:JAB:Apertura`) quedaron **sin uso** (test pin `test_equity_de_respaldo_sin_uso`). FR53 cumplido per convención firmada §3.
- **Histórico completo en el ledger y en origin:** 10.530 JEs / 66 archivos mensuales (2021-01 → 2026-07) en `imports/laudus-rut2/`, cuarentena **0** (AC5 exacto), push `e9e21a1..c8f4123`. El libro está vivo: la frecuencia de refresco futuro (¿cron RUT2?) queda como decisión de producto — documentado, no construido (Decisión 3 de la story).
- **2 bugs reales destapados y arreglados fuera del guión** (ambos dentro del espíritu de los ACs):
  1. `.gitignore` vs fix 5fec3b4: el import-log ignorado hacía fallar el commit de TODA corrida — habría roto el próximo cron EAG en prod. Fix e136393.
  2. Leak de frescura cross-libro en `balance_sheet_via_beancount` (NFR20, cazado por el gate 0-diffs haciendo su trabajo): la fecha "al" de EAG avanzaba con datos RUT2. Fix `_freshness_pattern` por grupo de consolidación, con RED→GREEN y comportamiento pre-12.4 preservado para EAG+hijas.
- **Defers cerrados/resueltos:** 12.2 #1 (env render.yaml), 12.2 #3 (include+gate, patrón include-antes-del-primer-import), 12.3 cash-US$ (evidencia: libro 100% CLP). El defer `generate_opening_balances` sin scoping NO se tocó (no hizo falta: caso (a) — sigue diferido al próximo uso del bootstrap). Nuevos hallazgos anotados en deferred-work §12-4.
- **Tests nuevos (8):** 3 de frescura por grupo en `test_bql_queries.py` (leak RED→GREEN + hija hereda frescura del grupo + FFCC/FondoComun miden su libro) y 5 sobre el ledger real en `test_rut2_import_historico.py` (includes activos; 10.530+ asientos solo bajo FFCC/JAB; apertura JE real vía 211005 sin Equity; Equity sin uso; cuarentena vacía).
- **Env pendiente de Ary en Render:** `LAUDUS_COMPANYVATID_RUT2` está declarada en render.yaml (sync:false) — hay que cargar el valor en el dashboard de Render cuando se quiera correr RUT2 desde el backend/cron (hoy no hay entry point de prod que lo haga; la corrida fue local por CLI, como manda la story).

### File List

- `render.yaml` — env `LAUDUS_COMPANYVATID_RUT2` (sync: false)
- `ledger/main.beancount` — 2 includes nuevos (imports/laudus-rut2/*.beancount + pending RUT2)
- `ledger/imports/laudus-rut2/_init.beancount` — NUEVO (placeholder del glob)
- `ledger/imports/laudus-rut2/2021-01.beancount` … `2026-07.beancount` — NUEVOS (66 archivos, 10.530 JEs, generados por el importer)
- `ledger/imports/_new-accounts-pending-rut2.beancount` — NUEVO (header canónico, 0 pendings)
- `ledger/_meta/import-log.jsonl` — ahora TRACKED (corridas RUT2 registradas; ver fix .gitignore)
- `.gitignore` — des-ignorado el import-log (completa el fix 5fec3b4)
- `backend/app/services/bql_queries.py` — `_max_transaction_date(entries, pattern)` + `_freshness_pattern` + `_ALL_ROOTS`; `balance_sheet_via_beancount` mide frescura por grupo (fix NFR20)
- `backend/tests/test_bql_queries.py` — 3 tests nuevos (frescura por grupo/libro)
- `backend/tests/test_rut2_import_historico.py` — NUEVO (5 tests sobre el ledger real)
- `_bmad-output/planning-artifacts/_forense_sonda_primeros_asientos_rut2.py` — NUEVO (sonda read-only persistida, re-ejecutable)
- `_bmad-output/implementation-artifacts/deferred-work.md` — 2 defers cerrados, 1 resuelto con evidencia, sección §12-4 nueva
- `_bmad-output/implementation-artifacts/12-4-import-historico-fondo-comun.md` — este story file
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — estado de la story
- (local, no commiteado) `.env` y `pipeline/.env` — `LAUDUS_COMPANYVATID_RUT2`

## Change Log

- 2026-07-11: Story 12.4 implementada completa (Tasks 0–5) — sonda read-only decidió fecha de corte 2021-01-01 y apertura caso (a) (JE real vía 211005); wiring includes+env commiteado ANTES de la primera corrida; backfill RUT2 importado y pusheado (10.530 JEs, 66 meses, cuarentena 0, `e9e21a1..c8f4123`). 2 bugs reales arreglados de paso: .gitignore rompía el commit del import-log de toda corrida (completa 5fec3b4) y la frescura del balance EAG se contaminaba con datos RUT2 (fix `_freshness_pattern` por grupo, cazado por el gate 0-diffs). Gates: 0-diffs EAG byte-idéntico PASS, bean-check exit 0, suite 851 passed / 1 xfailed (baseline 843/1, +8 tests, 0 regresiones), per-entity FFCC/JAB con datos. Status → review.
