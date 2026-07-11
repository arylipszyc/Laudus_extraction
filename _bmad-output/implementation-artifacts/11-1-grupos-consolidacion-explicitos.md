# Story 11.1: Grupos de consolidación explícitos en el motor de reportes

Status: review

## Story

As Ary (dueño),
I want que los reportes consolidados de EAG se deriven de un grupo explícito de entidades en vez del supuesto "EAG = todas las cuentas",
so that agregar el Fondo Común (o cualquier entidad futura) al ledger jamás contamine mis números de EAG.

## Acceptance Criteria

1. **Regresión cero (NFR20/NFR21):** Given el ledger actual (EAG + Jocelyn, Jeannette, Johanna, Jael), When se genera cualquier reporte, balance o dashboard consolidado de EAG tras reemplazar `_CONSOLIDATED_ENTITY` por `CONSOLIDATION_GROUPS`, Then el resultado es idéntico peso-por-peso al comportamiento previo (0 diffs de regresión), And la suite de tests y bean-check pasan en verde.
2. **Aislamiento (FR45):** Given una cuenta de prueba bajo un namespace ajeno al grupo EAG (ej. `Assets:FFCC:Test`), When se genera el reporte consolidado de EAG (balance-sheet **y** reporte de gastos), Then esa cuenta no aparece ni altera ningún total.
3. **Grupo RUT2 (FR46):** Given la definición `CONSOLIDATION_GROUPS`, When se consulta el grupo del libro RUT2, Then resuelve explícitamente a [FFCC, JAB], separado del grupo EAG, And las consultas por entidad individual (ej. Jocelyn) siguen funcionando sin cambios.

## Tasks / Subtasks

- [x] Task 1: `CONSOLIDATION_GROUPS` en `backend/app/services/bql_queries.py` (AC: 1, 3)
  - [x] Reemplazar `_CONSOLIDATED_ENTITY = "EAG"` (línea 34) por el mapa de grupos explícitos (ver Dev Notes — diseño recomendado), preservando el comentario-rationale existente sobre hijas/consolidado.
  - [x] Helper que construya el patrón regex de un grupo: entidades del grupo como 2º segmento + los namespaces de Equity **sin** segmento de entidad asignados al grupo EAG (`Equity:Apertura`, `Equity:Reconciliation`) — ver TRAP #1.
  - [x] Unit test: el grupo RUT2 resuelve exactamente a `{FFCC, JAB}` y es disjunto del grupo EAG (AC3).
- [x] Task 2: `balance_sheet_via_beancount` consulta por grupo (AC: 1, 2, 3)
  - [x] La rama `if entity == _CONSOLIDATED_ENTITY` (línea 86) pasa a lookup: si `entity` es clave de grupo → patrón del grupo; si no → patrón por entidad individual (sin cambios, cubre Jocelyn/Jeannette/Johanna/Jael).
  - [x] Test: mini-ledger con cuenta `Assets:FFCC:Test-410001` + tx → `balance_sheet_via_beancount(ledger, "EAG")` no la incluye y ningún total cambia (AC2).
  - [x] Test guard TRAP #1: mini-ledger con `Equity:Apertura:TarjetasSinDetalle` y `Equity:Reconciliation:Discrepancias` con saldo → SIGUEN apareciendo en el consolidado de EAG.
  - [x] Test: consolidado del grupo RUT2 sobre mini-ledger con cuentas FFCC+JAB+EAG → devuelve FFCC+JAB y excluye EAG (AC3).
- [x] Task 3: `report_rows_via_beancount` acotado al grupo EAG (AC: 1, 2)
  - [x] Hoy NO filtra (devuelve TODAS las entidades — línea 199-223); acotarlo al patrón del grupo EAG (roots `Assets|Liabilities|Equity|Income|Expenses` + Equity sin entidad). Sobre el ledger de hoy es el mismo conjunto exacto de cuentas → 0 diffs.
  - [x] Actualizar `test_includes_all_entities_no_entity_filter` en `backend/tests/test_report_rows_beancount.py` (línea 67): la semántica pasa de "todas las entidades" a "todo el grupo EAG"; el assert existente (EAG + Jocelyn presentes) sigue válido — actualizar nombre/docstring y agregar el caso de exclusión FFCC.
  - [x] NO tocar `ledger_entries_via_beancount`: su semántica per-entity (EAG = solo EAG, sin hijas) es comportamiento vigente correcto — cambiarla violaría AC1.
- [x] Task 4: Gate de 0 diffs contra el ledger REAL (AC: 1)
  - [x] Antes del cambio (en main): dumpear a JSON `balance_sheet_via_beancount(ledger, "EAG")` y `report_rows_via_beancount(ledger, "2021-01-01", <hoy>)` contra el ledger real (`ledger/main.beancount`). Después del cambio: re-dumpear y diffear — debe ser byte-idéntico.
  - [x] FAIL-SAFE del gate (lección 9.15): si cualquiera de los dumps sale vacío, el gate FALLA — un diff de conjuntos vacíos es falso GO, no PASS.
  - [x] Script de comparación en scratch o `_bmad-output/`, NO commitearlo al repo (es verificación one-shot).
- [x] Task 5: Suite completa + bean-check (AC: 1)
  - [x] `python -m pytest backend/tests -q` desde la raíz del repo — verde, 0 regresiones (baseline actual ~771 passed; los rojos date-dependientes pre-existentes documentados no cuentan como regresión).
  - [x] `bean-check ledger/main.beancount` exit 0 (esta story no escribe al ledger — debe ser trivialmente verde; correrlo igual como evidencia NFR21).

## Dev Notes

### Contexto: por qué esta story es la precondición de todo el Segundo RUT

Verificado con sonda 2026-06-30: hoy "EAG" en el consolidado significa **todo el ledger**. En cuanto un asiento de RUT2 entre al ledger, se sumaría en silencio al balance y al reporte de gastos de EAG — sin pasar por cuarentena. Este es el guardrail; HACER ANTES de meter cualquier dato de RUT2 (12.x depende de esto).

Los DOS supuestos "EAG = todo" a eliminar, ambos en `backend/app/services/bql_queries.py`:

1. **`balance_sheet_via_beancount`** ([bql_queries.py:86-88](backend/app/services/bql_queries.py#L86-L88)): cuando `entity == "EAG"` usa patrón roots-only `^(Assets|Liabilities|Equity):` → matchea TODAS las entidades. Consumidor: `dashboard/service.py` → `GET /api/v1/dashboard/balance-sheets`.
2. **`report_rows_via_beancount`** ([bql_queries.py:199-223](backend/app/services/bql_queries.py#L199-L223)): BQL `SELECT date, account, number, currency` **sin filtro de cuenta** → todas las entidades. Consumidor: `reportes/router.py` → `GET /reportes/gastos` (xlsx del contador). Peligro concreto: `report_builder.py` bucketea por prefijo de código — `EAG_EXPENSE_PREFIX` 411/413/415/430 y `EXPENSE_FIRST_DIGITS = "46789"` ([report_builder.py:74-79](backend/app/api/v1/reportes/report_builder.py#L74-L79)). Los códigos de FFCC (raíz 4: 41 Gastos Generales, 43 Gastos Fijos Oficina) y JAB (raíz 8: 81/83/85/87) colisionan de lleno con esos prefijos → los gastos del Fondo Común caerían DENTRO del reporte de EAG.

### ⚠️ TRAP #1 — Cuentas de Equity SIN segmento de entidad (rompe el 0-diffs si se ignora)

Verificado contra `ledger/accounts.beancount`: existen cuentas cuyo 2º segmento NO es una entidad:

- `Equity:Apertura` / `Equity:Apertura:TarjetasSinDetalle` ([accounts.beancount:2076](ledger/accounts.beancount#L2076))
- `Equity:Reconciliation:Discrepancias` ([accounts.beancount:2002](ledger/accounts.beancount#L2002))

El patrón roots-only actual las incluye en el consolidado de EAG. Un patrón ingenuo `^(Assets|Liabilities|Equity):(EAG|Jocelyn|...):` las DEJARÍA AFUERA → el balance consolidado cambia → AC1 falla. Estos namespaces pertenecen al libro EAG y deben asignarse explícitamente al grupo EAG. Todos los demás roots del ledger real llevan entidad como 2º segmento (verificado por conteo: Assets/Liabilities/Income/Expenses × {EAG, Jocelyn, Jeannette, Johanna, Jael} — solo Equity tiene los 2 namespaces huérfanos).

Recomendación aguas abajo (dejar como nota en el código): las cuentas de Equity del libro RUT2 (story 12.3, FR49) DEBEN llevar segmento de entidad (ej. `Equity:FFCC:Apertura`) para que la asignación a grupo siga siendo mecánica — la lista de namespaces sin entidad queda congelada como legacy del libro EAG.

### Diseño recomendado (decisión técnica, auto-aprobada per project-context)

```python
# Grupos de consolidación explícitos (Story 11.1, FR45/FR46). Clave = entidad
# consultable que resuelve a un consolidado; el resto de VALID_ENTITIES sigue
# el path per-entity. "FondoComun" es label PROPUESTO — 11.2 fija los definitivos.
CONSOLIDATION_GROUPS: dict[str, frozenset[str]] = {
    "EAG": frozenset({"EAG", "Jocelyn", "Jeannette", "Johanna", "Jael"}),
    "FondoComun": frozenset({"FFCC", "JAB"}),
}
# Namespaces de Equity sin segmento de entidad — legacy del libro EAG (congelado;
# las entidades nuevas llevan entidad en el path, ej. Equity:FFCC:Apertura).
_ENTITYLESS_EQUITY_PREFIXES = ("Equity:Apertura", "Equity:Reconciliation")  # → grupo EAG
```

Patrón de grupo para el balance (EAG): alternancia de (a) `^(Assets|Liabilities|Equity):(EAG|Jocelyn|Jeannette|Johanna|Jael):` y (b) `^Equity:(Apertura|Reconciliation)(:|$)`. Para `report_rows` el mismo esquema con los 5 roots. Mantener `functools.lru_cache` para los patterns compilados (patrón existente línea 50). El lookup en `balance_sheet_via_beancount`: `members = CONSOLIDATION_GROUPS.get(entity)` → `if members: <patrón de grupo> else: <patrón per-entity actual>`. Con esto "EAG" sigue siendo a la vez entidad y clave de grupo — exactamente el comportamiento actual del selector.

Notas de borde:

- **Labels FFCC/JAB/FondoComun son PROPUESTOS** — la decisión de Ary sobre nombres definitivos se toma en 11.2 (epics-segundo-rut.md, Story 11.2 AC1). Si cambian, es un rename de constante: no bloquea esta story.
- El grupo RUT2 NO entra a `VALID_ENTITIES` acá — eso es 11.2 (FR47). En 11.1 el grupo es consultable a nivel servicio/tests; el router sigue rechazando entidades fuera de `VALID_ENTITIES` ([dashboard/schemas.py:7](backend/app/api/v1/dashboard/schemas.py#L7)).
- Ningún cruce de grupos: no existe (ni se construye) vista combinada EAG+RUT2 — fuera de alcance explícito (epics doc, Additional Requirements).

### Qué NO tocar

- **`ledger_entries_via_beancount`** ([bql_queries.py:124](backend/app/services/bql_queries.py#L124)): per-entity puro (EAG = solo cuentas de EAG, sin hijas) — comportamiento vigente del drill-down; consolidarlo sería regresión de AC1. Cero cambios.
- **Frontend**: nada. FilterContext/selector es 11.2.
- **`scripts/draft_balance_sheet.py`**: script one-shot de handoff al contador con el mismo supuesto roots-only — fuera de scope (no es superficie de producto); no "arreglarlo" de pasada.
- Defer conocido de 6.4 (`list_accounts` startswith no segmentado en el autocompletado de categorías): adyacente pero NO es de esta story; ya está en deferred-work.
- No refactorizar el `import functools` a mitad de archivo (línea 42) ni otros detalles adyacentes — cambios quirúrgicos solamente.

### Testing

- Patrón de fixtures existente: mini-ledger inline como string → `tmp_path / "main.beancount"` → `LedgerService(str(main))`. Copiar de [test_report_rows_beancount.py:18-57](backend/tests/test_report_rows_beancount.py#L18-L57) o [test_bql_queries.py](backend/tests/test_bql_queries.py). Las cuentas de prueba FFCC/JAB necesitan su `open` en el mini-ledger (beancount valida cuentas usadas).
- Tests existentes que ejercen el consolidado (deben seguir verdes sin tocar sus asserts): `test_bql_queries.py`, `test_beancount_parity.py`, `test_cuentas_pendientes.py` (líneas 280, 308 usan `report_rows_via_beancount`), `test_report_rows_beancount.py` (salvo el rename documentado en Task 3), `test_owner_comments_inbox.py:308`.
- Suite: `python -m pytest backend/tests -q` desde la raíz. Gotcha Windows para scripts de smoke/dump: `PYTHONUTF8=1`.
- El gate real de la story es Task 4 (0 diffs contra el ledger de producción) — la suite sola no basta porque los fixtures no contienen los namespaces de Equity huérfanos del ledger real.

### Lecciones de trabajo previo aplicables

- **9.15 (gate de parity):** un gate que compara conjuntos vacíos da falso GO — fail-safe explícito si el dump sale vacío (aplicado en Task 4).
- **D7 (2026-07-08):** una sola pasada sobre `entries` / sin scans redundantes — no agregar segundas pasadas al armar el patrón de grupo.
- **Retro Epic 6:** commitear al cerrar la story (no acumular working tree).

### Project Structure Notes

- Todo el cambio de producto vive en `backend/app/services/bql_queries.py`; tests en `backend/tests/`. Sin archivos nuevos de producto, sin migraciones, sin cambios de deploy (Render redeploya del mismo repo; esta story no toca `ledger/` ni env vars).
- Alineado con architecture-c4 (Beancount fuente única, dashboards leen BQL); ningún conflicto detectado.

### References

- [Source: _bmad-output/planning-artifacts/epics-segundo-rut.md#Story 11.1] — story y ACs canónicos; Additional Requirements (ítem #1 del work breakdown: `CONSOLIDATION_GROUPS` antes de cualquier dato RUT2).
- [Source: _bmad-output/planning-artifacts/implementation-readiness-report-2026-07-10.md] — READY; FR45/FR46 → 11.1 AC2/AC3.
- [Source: _bmad-output/planning-artifacts/discovery-segundo-rut-intake-2026-06-30.md] — sonda: mismo login Laudus + swap companyVATId; "EAG=todo" verificado.
- [Source: _bmad-output/planning-artifacts/valentina-clasificacion-rut2-fondo-comun-2026-06-30.md] — sub-entidades FFCC (raíces 1-4) / JAB (raíces 6-8); colisiones de código con EAG.
- [Source: backend/app/services/bql_queries.py] — código a modificar (leído completo; estado actual documentado arriba).
- [Source: backend/app/api/v1/reportes/report_builder.py#L74-L79] — prefijos EAG que colisionan con códigos FFCC/JAB.
- [Source: ledger/accounts.beancount#L2002,L2076] — cuentas Equity sin entidad (TRAP #1).

## Dev Agent Record

### Agent Model Used

Claude Fable 5 (claude-fable-5) — dev-story workflow BMAD.

### Debug Log References

- Gate 0-diffs (Task 4): baseline pre-cambio con el ledger real = 56 cuentas balance + 19.989 filas report_rows (no-vacío → fail-safe OK); re-dump post-cambio **byte-idéntico** (`cmp` PASS). Script one-shot en scratchpad de sesión (no commiteado, per Task 4).
- Suite completa: `776 passed, 1 xfailed` (baseline ~771 + 5 tests nuevos de esta story, 0 regresiones, 0 rojos).
- `bean-check ledger/main.beancount` exit 0 (vía `python -m beancount.scripts.check`, venv del repo).

### Completion Notes List

- **Task 1:** `CONSOLIDATION_GROUPS` reemplaza `_CONSOLIDATED_ENTITY` en `bql_queries.py` siguiendo el diseño recomendado de Dev Notes (dict → frozenset; EAG={EAG,Jocelyn,Jeannette,Johanna,Jael}, FondoComun={FFCC,JAB} con labels PROPUESTOS, 11.2 fija definitivos). Rationale de hijas/consolidado preservado en el comentario. Helper `_group_pattern(roots, group)` con `functools.lru_cache` (mismo patrón del módulo): alternancia `^(roots):(miembros):` + rama legacy `^Equity:(Apertura|Reconciliation)(:|$)` SOLO para el grupo EAG (TRAP #1).
- **Task 2:** `balance_sheet_via_beancount` pasa de `entity == _CONSOLIDATED_ENTITY` a lookup `entity in CONSOLIDATION_GROUPS` → patrón de grupo; el path per-entity (hijas) quedó intacto. El grupo RUT2 ("FondoComun") es consultable a nivel servicio; el router sigue gateado por `VALID_ENTITIES` (11.2).
- **Task 3:** `report_rows_via_beancount` acotado al patrón del grupo EAG (5 roots + Equity legacy) — antes sin filtro de cuenta (todo el ledger). Sobre el ledger actual es el mismo conjunto exacto (verificado por el gate byte-idéntico). `ledger_entries_via_beancount` NO tocado.
- **Tests (TDD red-green):** 4 nuevos en `test_bql_queries.py` (miembros/disjunción RUT2 AC3; aislamiento EAG vs libro RUT2 AC2 — igualdad de resultado con/sin bloque RUT2; guard TRAP #1 Equity sin entidad; consolidado FondoComun AC3) + 1 nuevo y 1 renombrado en `test_report_rows_beancount.py` (`test_includes_whole_eag_group` + exclusión FFCC con guard de Equity legacy). RED verificado antes de implementar (ImportError/exclusión), GREEN después: 31/31 en los dos módulos.
- **AC1 (regresión cero):** gate de 0 diffs contra el ledger REAL byte-idéntico + suite verde + bean-check exit 0. **AC2 (aislamiento):** tests de exclusión FFCC en balance Y reporte de gastos. **AC3 (grupo RUT2):** resuelve a {FFCC, JAB}, disjunto de EAG, consolidable; per-entity (Jocelyn et al.) sin cambios (tests existentes verdes sin tocar asserts).

### File List

- `backend/app/services/bql_queries.py` (modificado — único cambio de producto)
- `backend/tests/test_bql_queries.py` (modificado — import + 4 tests nuevos + 2 fixtures de bloque)
- `backend/tests/test_report_rows_beancount.py` (modificado — docstring módulo, rename `test_includes_all_entities_no_entity_filter`→`test_includes_whole_eag_group`, test nuevo de exclusión FFCC)
- `_bmad-output/implementation-artifacts/11-1-grupos-consolidacion-explicitos.md` (story file)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (tracking)

## Change Log

- 2026-07-10: Story 11.1 implementada completa (Tasks 1–5) — grupos de consolidación explícitos en `bql_queries.py`, gate 0-diffs byte-idéntico vs ledger real, suite 776 passed/1 xfailed, bean-check exit 0. Status → review.
