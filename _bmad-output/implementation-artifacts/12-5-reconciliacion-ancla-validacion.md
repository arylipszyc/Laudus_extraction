# Story 12.5: Reconciliación peso-por-peso contra el ancla de validación

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Ary (dueño),
I want los saldos importados del Fondo Común (FFCC/JAB) reconciliados peso-por-peso contra el balance de Laudus a fin de mes,
so that tenga la garantía de que el sistema es espejo fiel de Laudus antes de cerrar el Epic 12 (la cuadratura contra el mundo real —cartolas/saldos bancarios— viene después, como fase posterior).

> **Ancla = balance de Laudus a fin de mes** (decisión Ary 2026-07-10: Laudus se asume correcto; este libro no maneja tarjetas de crédito a conciliar). La cuadratura contra cartolas/saldos reales queda **diferida al final**, fuera de este epic. **Esta story es el criterio de cierre (DoD) del Epic 12.**

## Acceptance Criteria

1. **Given** el balance de Laudus del libro RUT2 a fin de mes (vía API `GET /accounting/balanceSheet/totals?dateTo=<fin-de-mes>`, con login del libro RUT2 — mismo mecanismo de paridad CLP↔CLP usado con EAG en `bootstrap/validate_cuadratura.py`),
   **When** se reconcilian los saldos importados de RUT2 a esa fecha de corte,
   **Then** cuadran **al peso** (diff exacto 0 CLP por cuenta), **o** cada discrepancia queda **documentada con explicación aceptada** en el artefacto de reconciliación (FR56),
   **And** la reconciliación está **scopeada al libro RUT2** (solo cuentas cuyo 2º segmento de path ∈ {FFCC, JAB}) — ninguna cuenta de EAG entra en la comparación, y ningún saldo de Laudus-RUT2 se mapea a una cuenta de EAG (TRAP del índice last-wins, ver Dev Notes).

2. **Given** los dashboards existentes,
   **When** filtro por FFCC o JAB en el selector de entidad,
   **Then** los saldos de balance mostrados **coinciden** con lo reconciliado (a la fecha de corte),
   **And** el drill-down a transacciones individuales de una cuenta FFCC/JAB funciona (abre el detalle real, no el ledger entero de la entidad).

3. **Given** el resultado de la reconciliación,
   **When** se presenta para el cierre del epic,
   **Then** queda un artefacto versionado con el veredicto (PASS peso-por-peso o discrepancias aceptadas) + el reporte por cuenta,
   **And** el Epic 12 solo se declara cerrado con la reconciliación en PASS — **el flip de `epic-12` a `done` es un gate de Ary** (cierre de épica, ver project-context §Gates STOP): esta story entrega la evidencia, **no** cierra el epic por su cuenta.

4. **Given** la operación de esta story (que solo LEE de Laudus y del ledger),
   **When** termina,
   **Then** no se escribe ningún asiento nuevo al ledger (esta story valida, no importa ni corrige): balance consolidado EAG + report_rows **byte-idénticos** pre/post (patrón gate 11.1/12.3/12.4; fail-safe: dump vacío = FAIL),
   **And** `bean-check` sale en 0 (NFR21),
   **And** la suite completa pasa sin regresiones (baseline **851 passed / 1 xfailed** — el de 12.4 ya mergeado).

## Tasks / Subtasks

- [x] Task 0: Prerequisitos y estado del ledger (AC: 1, 4)
  - [x] `LAUDUS_COMPANYVATID_RUT2` confirmada presente en `.env` raíz Y `pipeline/.env`.
  - [x] Histórico RUT2 de 12.4 en el checkout: `ledger/imports/laudus-rut2/` con 68 archivos, commit `d73ce81` (+10.530 JE). No hizo falta reset.
  - [x] Picklecache borrado antes de cada carga (`rm -f ledger/.main.beancount.picklecache`).
  - [x] **Corte primario = `2026-06-30`** (default técnico auto-aprobado). Cortes anuales NO agregados (TRAP #2: el cierre/apertura anual de Laudus contamina un corte de fin de año; el fin de mes intermedio es suficiente para el DoD).

- [x] Task 1: Reconciliador RUT2-scoped (AC: 1)
  - [x] Creado `bootstrap/reconcile_rut2.py` (hermano de `validate_cuadratura.py`, mismo patrón `fetch_*`/`compare`/`write_report`/`run_reconciliation`; reusa `signed_balance` + convención de signos + patrón CSV). NO reusa `validate_cuadratura` tal cual.
  - [x] Fetch Laudus RUT2 vía `verify_book_identity(get_book("RUT2"))` ("ACTIVO FFCC") + `get_info_API(BALANCE_SHEET_URL, {"dateTo": cutoff}, book=get_book("RUT2"))`.
  - [x] Índice scopeado por entidad ({FFCC, JAB}) parseando `accounts.beancount` con regex `(?-i:^(Assets|...):(FFCC|JAB):)`. NO reusa los `load_account_index` globales last-wins (TRAP #1). Code normalizado a 6 dígitos en ambos lados (simetría hoja "13", TRAP #3).
  - [x] Saldos Beancount scopeados con el BQL `(?-i:)` case-sensitive.
  - [x] `compare` cuenta-por-cuenta: `amount_mismatch` + `account_not_in_rut2_tree` (ruteo roto, solo si saldo≠0) + `beancount_only`. Escribe `report-reconciliacion-rut2-<cutoff>.csv`.
  - [x] Test offline `backend/tests/test_reconcile_rut2.py`: 9 tests (cuadre 0, mismatch, ruteo-roto, fila-0-ignorada, beancount_only, scoping por entidad excluye EAG, code EAG-only no mapea, hoja "13" simétrica, BQL excluye EAG). **9 passed.**

- [x] Task 2: Corrida de reconciliación (AC: 1, 3)
  - [x] `PYTHONUTF8=1 PYTHONPATH=. venv/Scripts/python -m bootstrap.reconcile_rut2 --cutoff 2026-06-30` → **[OK] 0 diferencias sobre 237 cuentas con saldo** (Laudus reportó 243). CSV guardado (solo header).
  - [x] **Triage: N/A** — 0 diffs, no hay discrepancias que clasificar.
  - [x] Corte primario `2026-06-30` = **PASS limpio**. 237 cuentas RUT2 con saldo reconciliadas al peso.

- [x] Task 3: Verificación de dashboards FFCC/JAB (AC: 2)
  - [x] `balance_sheet_via_beancount(ledger, "FFCC"|"JAB", date_to="2026-06-30")`: **0 mismatches** vs la reconciliación (por entidad; las "extra" del dashboard son cuentas en saldo 0.0). FFCC 24 filas / JAB 9 filas, `last_sync=2026-06-30`.
  - [x] Drill-down: FFCC 14.116 filas (100% con `code`, 74 codes) / JAB 24.294 filas (100% con `code`, 169 codes); filtro por cuenta trae solo esa cuenta. Defer 11.2 NO se activa (0 cuentas RUT2 sin `code`).
  - [x] Smoke de 12.4 cerrado formalmente contra los números reconciliados. Motor de reportes y frontend NO tocados.

- [x] Task 4: Artefacto de cierre + gate de épica (AC: 3)
  - [x] Escrito `_bmad-output/planning-artifacts/reconciliacion-rut2-vs-laudus-2026-07-11.md`: corte, veredicto PASS peso-por-peso, tabla resumen, dashboards, gates, y el CSV como evidencia.
  - [x] `epic-12` NO flipeado a `done`. `12-5` queda en `review`; el cierre de épica es gate de Ary con el artefacto de PASS a la vista (ver Completion Notes).

- [x] Task 5: Gates anti-regresión y cierre (AC: 4)
  - [x] Gate 0-diffs EAG: `git status ledger/` limpio (0 escrituras — prueba definitiva) + dump EAG = **56 cuentas / 19.989 filas** (= baseline 12.4), `last_sync=2026-07-08` intacto, fail-safe no-vacío OK.
  - [x] `bean-check ledger/main.beancount` → **exit 0** (picklecache borrado antes).
  - [x] Suite completa `pytest backend/tests pipeline` → **860 passed / 1 xfailed** (baseline 851/1 + 9 tests nuevos, 0 regresiones).
  - [x] `deferred-work.md` actualizado: defer de frescura cross-libro de 12.4 anotado como NO materializado (12.5 es read-only, no postea; sigue latente para una eventual corrección con asiento).
  - [ ] Commitear al cerrar — pendiente (ver nota abajo: la story queda en review, el commit lo confirma Ary junto al gate de cierre; los artefactos están en el working tree).

## Dev Notes

### Qué es esta story (y qué NO es)

Es una story de **validación y evidencia**, no de construcción de features. Casi todo el motor ya existe:
- El histórico RUT2 ya está importado y en origin (12.4).
- El fetch multi-libro de Laudus ya funciona (`login(book)`, `get_info_API(..., book)`, `verify_book_identity` — 12.2).
- El mecanismo de comparación CLP↔CLP contra el balance de Laudus ya está probado con EAG (`bootstrap/validate_cuadratura.py`, 186/186 al peso).

El trabajo real es: **scopear ese mecanismo al libro RUT2**, correrlo a fin de mes, y **producir el artefacto de PASS** que habilita el cierre del epic. La escritura de código es un script + su test; el resto es operación + documentación.

### TRAP #1 — el índice de cuentas last-wins (defer 12-2, ahora relevante en la otra dirección)

`bootstrap/generate_opening_balances.load_account_index` y `validate_cuadratura.load_account_index_with_padded_codes` indexan `accounts.beancount` COMPLETO por `code` desnudo, **last-wins**. Desde el merge de 12.3 las 31 colisiones de code (111005, 115001, 310001, …) resuelven a la cuenta RUT2 (el bloque FFCC/JAB está al final del archivo). Para RUT2 esto "acierta por casualidad", pero es frágil y el índice sigue conteniendo cuentas EAG. **La fuente de verdad para scopear es el 2º segmento del path** (`get_book("RUT2").entities` = {FFCC, JAB}), no el code. Construir el índice filtrando por entidad, no reusar los helpers globales. (Ver [_bmad-output/implementation-artifacts/deferred-work.md#12-2] — el mismo helper también está roto para EAG hoy; scopearlo por libro sería el hardening durable, opcional en esta story.)

### TRAP #2 — cortes de fin de AÑO tienen el asiento de cierre de Laudus de por medio

La sonda de 12.4 encontró que Laudus postea "Comprobante de cierre/apertura" ANUALES (±402.430.179 sobre 211005) cada fin/inicio de año, y el importador los espejó verbatim al ledger. En un corte `YYYY-12-31` el balance puede quedar antes o después del asiento de cierre según cómo Laudus lo fecha → ambigüedad. **Por eso el ancla primaria es `2026-06-30`** (fin de mes intermedio, sin cierre de por medio). Si se agregan cortes anuales como hardening, esperar diffs en las cuentas de resultado/patrimonio alrededor del cierre y tratarlos como "explicación aceptada TRAP #2", no como error de import.

### TRAP #3 — la hoja code "13" (rama-vacía) y la normalización

`Assets:FFCC:ActivosNoCorrientes-13` tiene `code: "13"` **verbatim** (no padded a 6 dígitos — única cuenta no-6-dígitos del árbol RUT2, 12.3). Si el reconciliador normaliza la `accountNumber` del lado Laudus con `normalize_account_number("13") → "130000"` pero el índice guarda `"13"`, no matchean. La sonda 12.4 verificó que la cuenta 13 tiene **0 movimientos** → no aparecerá con saldo en el balance de Laudus, así que hoy no muerde. Aun así: **no normalizar el code al construir el índice scopeado** (usar el `code:` tal cual del `open`), y si se normaliza el lado Laudus, normalizar AMBOS lados igual. Documentar si aparece.

### Convención de signos (ya probada, no re-derivar)

Laudus `balanceSheet/totals` → `signed = debitBalance - creditBalance`. Beancount nativo: Assets/Expenses positivo, Liabilities/Income/Equity negativo. Coinciden. `bootstrap/validate_cuadratura.compare` ya implementa exactamente esto y cuadró 186/186 con EAG — copiar la lógica, cambiar solo el fetch (libro RUT2) y el scoping (por entidad).

### Frescura cross-libro (defer de 12.4, guardar al aterrizar acá)

El code-review de 12.4 dejó un defer LATENTE: `_max_transaction_date`/`_freshness_pattern` ([backend/app/services/bql_queries.py:102,73-74]) cuenta un JE si ALGUNA pata matchea el patrón del grupo, sin exigir que TODAS sean del mismo grupo; y los namespaces `Equity:Apertura`/`Equity:Reconciliation` **sin entidad** caen en el grupo EAG por diseño. **Esta story NO postea reconciliación al ledger** (solo lee y reporta), así que el riesgo no se materializa. PERO si en el triage se decidiera anotar una discrepancia aceptada CON un asiento (no es el plan — eso sería una corrección estilo TC, otra story), NUNCA usar `Equity:Reconciliation` entityless para RUT2: usar `Equity:FFCC:Reconciliation` / `Equity:JAB:Reconciliation` o filtraría la frescura a EAG. Ver [deferred-work.md#code review of 12-4].

### Hechos verificados del código (2026-07-11, no re-derivar)

- **Fetch multi-libro listo:** `login(get_book("RUT2"))` usa `LAUDUS_COMPANYVATID_RUT2`; `get_info_API(url, params, book=get_book("RUT2"))` pagina y cachea token por libro; `verify_book_identity` asserta "ACTIVO FFCC" ([pipeline/services/laudus_service.py:36-99]; [pipeline/config/laudus_config.py:75-91]).
- **Endpoint de balance:** `BALANCE_SHEET_URL = "https://api.laudus.cl/accounting/balanceSheet/totals"`, param `{"dateTo": <cutoff>}` ([pipeline/config/laudus_config.py:14,130-133]). Mismo endpoint que `fetch_opening_balances` (que hoy lo llama con login EAG).
- **Árbol RUT2 en el ledger:** paths `Assets:FFCC:*`, `Liabilities:FFCC:Apertura-211005`, `Assets:JAB:*`, `Equity:FFCC:Apertura` (code 900001), `Equity:JAB:Apertura` (code 900002) ([ledger/accounts.beancount:2099-2289,4286,4293]). 2º segmento ∈ {FFCC, JAB} = el discriminador de libro.
- **Includes RUT2 activos** en `main.beancount` (`imports/laudus-rut2/*.beancount` + pending RUT2) desde 12.4 ([ledger/main.beancount:34-36]).
- **Balance por entidad/grupo:** `balance_sheet_via_beancount(ledger, "FFCC"|"JAB", date_to=...)` ya rutea per-entity ([backend/app/services/bql_queries.py:131-161]); `"FondoComun"` resuelve el grupo pero NO está en `VALID_ENTITIES` ni en el selector (decisión 11.1) — para AC2 se usan FFCC y JAB, que sí están en el selector (11.2).
- **Sonda 12.4 (datos duros del libro):** corte real 2021-01-01; libro vivo hasta 2026-07-10; 100% CLP (0 filas no-CLP); apertura = JE real id=1 self-balancing vía 211005; cuarentena 0/243 codes; sumas por sub-entidad FFCC −14.822.194.074 / JAB +14.822.194.074 (flujo inter-entidad DENTRO de JEs, cada uno balancea).

### Decisiones con default documentado (auto-aprobadas per project-context; el dev documenta desvíos)

1. **Home del reconciliador**: `bootstrap/reconcile_rut2.py` (hermano de `validate_cuadratura.py`, con test offline), no un `_forense_*.py` suelto — es una verificación repetible con test, no un one-off de investigación. Default recomendado.
2. **Corte primario = `2026-06-30`** (último fin de mes completo). Cortes anuales = hardening opcional con el caveat del TRAP #2. El dev elige y documenta.
3. **Esta story no corrige nada**: si hay discrepancias reales que impliquen tocar datos (improbable — 12.4 cuadró la cuarentena en 0 y el libro es espejo verbatim), NO se corrigen acá; se documentan y se levanta una story de corrección (estilo auditoría de inversiones / TC). El objetivo es el veredicto, no la mutación.

### Qué NO hacer (scope guard)

- NO escribir asientos al ledger (esta story LEE y reporta; el gate 0-diffs EAG lo verifica).
- NO reconciliar contra cartolas/saldos bancarios reales — eso es la fase posterior, fuera del epic (decisión Ary 2026-07-10).
- NO flipear `epic-12` a `done` — es gate de Ary (cierre de épica).
- NO tocar el motor de reportes ni el frontend (solo verificar que FFCC/JAB responden con datos coincidentes; hallazgos como `getLedgerCategory` se documentan para 13.1, no se arreglan).
- NO reusar los `load_account_index` globales sin scoping por libro (TRAP #1).
- NO validar dígito verificador del RUT (placeholder por diseño).

### Inteligencia de stories previas (12.4)

- **Suite**: `PYTHONUTF8=1` obligatorio en Windows. Baseline **851 passed / 1 xfailed**.
- **Env local:** `LAUDUS_COMPANYVATID_RUT2` va en `.env` Y `pipeline/.env` (ambos gitignoreados); `load_dotenv()` desde `pipeline/config/` toma `pipeline/.env` primero.
- **bean-check**: borrar `*.picklecache` antes (cache por mtime no ve archivos por glob).
- **Gate 0-diffs**: correr los scripts con `PYTHONPATH=<checkout>` explícito.
- **Backend Render clona el ledger al startup** — el humo per-entity (AC2) se hace contra el ledger local; en prod, refrescar = redeploy o `/sync/trigger`.

### References

- [Source: _bmad-output/planning-artifacts/epics-segundo-rut.md#Story 12.5] — FR56; ancla = balance Laudus fin de mes; DoD del epic
- [Source: bootstrap/validate_cuadratura.py] — mecanismo de paridad CLP↔CLP vs Laudus (a scopear por libro); `compare`, `signed_balance`, reporte CSV
- [Source: bootstrap/generate_opening_balances.py:51-102] — `fetch_opening_balances` (login sin libro = EAG, NO reusar tal cual), `signed_balance`, `load_account_index` (last-wins, TRAP #1)
- [Source: pipeline/config/laudus_config.py:36-133] — `BookConfig` RUT2, `login_payload`, `BALANCE_SHEET_URL`, `get_endpoints`
- [Source: pipeline/services/laudus_service.py:36-99,144-223] — `login(book)`, `verify_book_identity`, `get_info_API(..., book)`
- [Source: backend/app/services/bql_queries.py:56-161] — `_entity_pattern`/`_group_pattern` (`(?-i:)`), `balance_sheet_via_beancount`, `_clp`
- [Source: ledger/accounts.beancount:2099-2289,4286,4293] — árbol RUT2 (2º segmento FFCC/JAB, Equity apertura, 211005)
- [Source: ledger/main.beancount:34-36] — includes RUT2 activos
- [Source: _bmad-output/implementation-artifacts/12-4-import-historico-fondo-comun.md] — sonda (datos del libro), gotchas, baseline
- [Source: _bmad-output/implementation-artifacts/deferred-work.md#12-2 / #code review of 12-4] — TRAP #1 (índice last-wins) y frescura cross-libro
- [Source: _bmad-output/planning-artifacts/clasificacion-contable-rut2-firmada-2026-07-11.md] — clasificación firmada del árbol RUT2
- [Source: _bmad-output/project-context.md#Gates que requieren mi aprobación] — cierre de épica = gate de Ary; comandos de verificación

## Review Findings

> Code review adversarial 3 capas (Blind Hunter / Edge Case Hunter / Acceptance Auditor), 2026-07-11.
> Veredicto del Auditor: **CONFORMANT** — AC1/AC3/AC4 PASS, TRAPs #1–#3 neutralizados, read-only estructuralmente garantizado.
> Verificado empíricamente: **0 colisiones** de code normalizado sobre 311 opens FFCC/JAB (el PASS peso-por-peso NO es suerte del last-wins); venv = Python **3.14.2**.

- [x] [Review][Patch] TRAP #3 sin test end-to-end: agregado `test_trap3_code_13_matches_symmetrically_end_to_end` — fila Laudus `"13"` por `compare()` cuadra a `"130000"`, no cae a `account_not_in_rut2_tree` [backend/tests/test_reconcile_rut2.py]
- [x] [Review][Patch] `load_rut2_account_index` last-wins silencioso → guard que levanta `RuntimeError` ante code normalizado duplicado (0 colisiones hoy, seguro del gate) [bootstrap/reconcile_rut2.py:99]
- [x] [Review][Patch] `--cutoff` sin validación → `_cli` ahora exige `\d{4}-\d{2}-\d{2}` (regex) + fecha real (strptime) → `parser.error` exit 2; verificado que rechaza `2026-6-30` y `2026-13-01` [bootstrap/reconcile_rut2.py:259]

**Verificación de patches:** `pytest backend/tests/test_reconcile_rut2.py` → **10 passed** (+1). Suite completa `pytest backend/tests pipeline` → **861 passed / 1 xfailed** (baseline 860+1; el único FAILED `test_lock_stale_robado_por_uno_solo` es flaky de concurrencia ajeno al cambio — pasa 3/3 en aislamiento).

**Descartados con evidencia (8):** doble-conteo por filas Laudus duplicadas y rollup-rows con saldo (endpoint devuelve hojas; live 0-diffs + hermano EAG `validate_cuadratura` probado 186/186); igualdad float en pesos (exacto para CLP entero < 2^53, dirección segura, el spec pide exacto-0); `(?-i:)` requiere 3.11+ (venv=3.14, ya en prod bql_queries); multi-moneda ignorada (`_extract_clp_amount` CLP-only por diseño, sonda 12.4 = 100% CLP); crash por keys Laudus faltantes/null (crash ruidoso aceptable en validador manual, hermano prueba el shape); `str(accountNumber)` numérico JSON (Laudus devuelve strings); semántica de `n_accounts` (cosmético, exacto en el caso PASS).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (dev-story workflow, 2026-07-11)

### Debug Log References

- Corrida live: `PYTHONUTF8=1 PYTHONPATH=. venv/Scripts/python -m bootstrap.reconcile_rut2 --cutoff 2026-06-30` → `[OK] 0 diferencias sobre 237 cuentas con saldo` (Laudus reportó 243).
- Test: `pytest backend/tests/test_reconcile_rut2.py -q` → 9 passed.
- Gate 0-diffs EAG: dump = 56 cuentas / 19.989 filas, `last_sync=2026-07-08`; `git status ledger/` limpio.
- `bean-check ledger/main.beancount` → exit 0.
- Suite: `pytest backend/tests pipeline -q` → 860 passed / 1 xfailed (160.9s).

### Completion Notes List

- **Veredicto: PASS peso-por-peso.** El libro RUT2 (FFCC/JAB) cuadra al peso con el balance de Laudus al corte `2026-06-30`: 0 discrepancias sobre 237 cuentas con saldo, diff exacto 0 CLP por cuenta. No hubo triage porque no hubo diffs.
- **Story read-only, verificado:** `git status ledger/` quedó completamente limpio (0 escrituras) y el dump EAG salió byte-idéntico al baseline (56/19.989, frescura EAG intacta en 2026-07-08). Esta story valida, no importa ni corrige.
- **3 TRAPs neutralizados:** #1 índice scopeado por entidad (no reusa los `load_account_index` last-wins); #2 corte de fin de mes intermedio (evita el cierre anual de Laudus); #3 hoja "13" normalizada simétricamente en ambos lados (0 movimientos, no muerde).
- **AC2 dashboards:** FFCC/JAB coinciden peso-por-peso con lo reconciliado (0 mismatches por entidad); drill-down 100% con `code` → el defer 11.2 no se activa para RUT2.
- **Epic 12 listo para cierre, PENDIENTE GATE DE ARY.** Esta story entrega la evidencia de PASS (artefacto `reconciliacion-rut2-vs-laudus-2026-07-11.md`) pero NO flipea `epic-12 → done`: el cierre de épica es gate de Ary (project-context §Gates STOP). Queda en `review`.
- **Commit pendiente de confirmación de Ary.** El acuerdo de retro pide commitear al cerrar (script + test + artefacto + CSV), pero estamos en `main` y el gate global es cauteloso con commits directos a la rama default. Los artefactos están en el working tree listos; Ary confirma el commit junto al gate de cierre del epic.

### File List

- `bootstrap/reconcile_rut2.py` (nuevo) — reconciliador RUT2-scoped
- `backend/tests/test_reconcile_rut2.py` (nuevo) — 9 tests offline
- `bootstrap/report-reconciliacion-rut2-2026-06-30.csv` (nuevo) — evidencia (0 diffs, solo header)
- `_bmad-output/planning-artifacts/reconciliacion-rut2-vs-laudus-2026-07-11.md` (nuevo) — artefacto de cierre
- `_bmad-output/implementation-artifacts/deferred-work.md` (modificado) — defer frescura cross-libro anotado NO-materializado
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modificado) — 12-5 → in-progress → review
- `_bmad-output/implementation-artifacts/12-5-reconciliacion-ancla-validacion.md` (modificado) — este story file

### Change Log

- 2026-07-11: Story 12.5 implementada (Tasks 0–5). Reconciliador RUT2-scoped + 9 tests; corrida live corte 2026-06-30 = PASS peso-por-peso (0 diffs / 237 cuentas). Dashboards FFCC/JAB verificados (0 mismatches). Gates: 0-diffs EAG byte-idéntico, bean-check 0, suite 860/1 (0 regresiones). Artefacto de cierre generado. Status → review. Cierre del Epic 12 = gate de Ary.
