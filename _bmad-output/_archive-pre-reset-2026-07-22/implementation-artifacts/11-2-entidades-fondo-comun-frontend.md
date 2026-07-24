# Story 11.2: Entidades del Fondo Común seleccionables en el frontend

Status: done

## Story

As usuario (owner o contador),
I want ver y seleccionar las entidades del Fondo Común (FFCC, JAB) en el selector de entidad existente,
so that cuando sus datos entren al ledger pueda navegarlos desde la misma UI de siempre.

## Acceptance Criteria

1. **Labels definitivos (gate Ary):** Given la decisión de Ary sobre los nombres cortos definitivos de las entidades (propuesta actual: FFCC y JAB), When se ejecuta esta story, Then los labels quedan fijados aquí — para rutas de cuenta, `VALID_ENTITIES` y selector — y las stories posteriores (12.3 árbol de cuentas, 12.4 import) los usan sin cambios.
2. **Selector (FR47):** Given las entidades nuevas registradas en `VALID_ENTITIES` y `FilterContext`, When abro el selector de entidad en cualquier dashboard, Then FFCC y JAB aparecen como opciones válidas, And EAG sigue siendo la entidad por defecto.
3. **Estado vacío limpio:** Given que FFCC/JAB aún no tienen datos en el ledger, When selecciono una de ellas, Then el dashboard muestra un estado vacío limpio (sin errores, sin números de otras entidades).

## Tasks / Subtasks

- [x] Task 0: Fijar labels definitivos con Ary (AC: 1) — **GATE de negocio, resolver ANTES de codear**
  - [x] Confirmar con Ary los 3 labels: entidad 1 (propuesta `FFCC`), entidad 2 (propuesta `JAB`), clave del grupo consolidado (propuesta `FondoComun`, hoy solo a nivel servicio). Si la sesión ya trae la decisión registrada (ver Dev Notes → "Decisión de labels"), usarla sin re-preguntar. → **Decisión registrada usada sin re-preguntar**: Ary ratificó FFCC/JAB/FondoComun el 2026-07-11 vía Excel de clasificación devuelto (357/357 filas "sub-entidad confirmada SI", cero correcciones) — `valentina-contexto-fondo-comun-jab-2026-07-11.md` §6.
  - [x] Validar los labels elegidos contra las restricciones duras (ver Dev Notes → "Restricciones de labels" — vienen del defer del code-review 11.1): alfanuméricos, sin metacaracteres de regex ni comillas, case-sensitive distintos de {EAG, Jocelyn, Jeannette, Johanna, Jael} y no case-variantes entre sí. → PASS (FFCC/JAB alfanuméricos puros, sin colisión case-insensitive con miembros EAG ni entre sí).
  - [x] Si difieren de la propuesta: rename en `CONSOLIDATION_GROUPS` ([bql_queries.py:37-40](backend/app/services/bql_queries.py#L37-L40)) + el test `test_bql_queries.py:286` + comentarios. Si coinciden: solo quitar la palabra "PROPUESTOS" de los comentarios en [bql_queries.py:30-36](backend/app/services/bql_queries.py#L30-L36) (los labels quedan fijados por esta story). → Coinciden: comentario actualizado a "labels DEFINITIVOS, fijados por la story 11.2".
- [x] Task 1: Backend — registrar FFCC/JAB en `VALID_ENTITIES` (AC: 2, 3)
  - [x] `VALID_ENTITIES` en [schemas.py:7](backend/app/api/v1/dashboard/schemas.py#L7): agregar `"FFCC", "JAB"` al frozenset. El grupo (`FondoComun`) NO entra — ver Dev Notes → "Decisión: el grupo no entra al selector".
  - [x] Actualizar las `description` de los Query params en [router.py:64,82](backend/app/api/v1/dashboard/router.py#L64) ("Entity name: EAG | Jocelyn | ... | FFCC | JAB") — el mensaje 422 usa `sorted(VALID_ENTITIES)` y se actualiza solo.
  - [x] Tests en `backend/tests/test_dashboard.py` (patrón `_make_app` existente, líneas 28-39): (a) `GET /balance-sheets?entity=FFCC` → 200 con `data == []` sobre el MINI_LEDGER (sin cuentas FFCC); (b) `GET /ledger-entries?entity=JAB` → 200 con `data == []`; (c) entidad inválida (ej. `Pepito`) sigue devolviendo 422. → RED confirmado antes del cambio (4 fails), GREEN después; parametrize de entidades válidas extendido a 7.
- [x] Task 2: Frontend — `FilterContext` (AC: 2)
  - [x] [FilterContext.tsx:3-6](frontend/src/contexts/FilterContext.tsx#L3-L6): extender el union `Entity` con `'FFCC' | 'JAB'` y el array `ENTITIES` (orden sugerido: al final, después de Jael). `EntityFilter` mapea `ENTITIES` → no necesita cambios.
  - [x] Exportar la lista de entidades del libro RUT2 (ej. `export const RUT2_ENTITIES = ['FFCC', 'JAB'] as const` + helper `isRut2Entity(e)`) — la consumen Task 3 y, a futuro, cualquier superficie que deba distinguir libro. → `isRut2Entity(e: string)` acepta string para servir también a `filterByEntity`.
  - [x] El default NO cambia: `useState<Entity>('EAG')` ([FilterContext.tsx:46](frontend/src/contexts/FilterContext.tsx#L46)) queda intacto (AC2). → Verificado intacto + cubierto por test de EntityFilter.
- [x] Task 3: Frontend — ruteo de datos por libro en `useLedger` + `filterByEntity` (AC: 3) — **el corazón de la story, ver TRAP #1**
  - [x] [useLedger.ts](frontend/src/hooks/useLedger.ts): hoy SIEMPRE pide `entity=EAG` al API (`SHEET_ENTITY`, línea 8) y el filtrado por entidad es client-side. Cambiar a: `const apiEntity = isRut2Entity(entity) ? entity : 'EAG'` (leyendo `entity` de `useFilters()`), y pedir `apiEntity` al API.
  - [x] **CRÍTICO:** agregar `apiEntity` al `queryKey` ([useLedger.ts:13](frontend/src/hooks/useLedger.ts#L13)) — hoy el key es `['ledger-entries', dateFrom, dateTo, accountNumber]` sin entidad; sin este cambio react-query sirve el cache de EAG al seleccionar FFCC (números de otra entidad = viola AC3). → Hecho + test conductual (EAG→FFCC refetchea, no sirve cache).
  - [x] [IncomeExpensesPage.tsx:52](frontend/src/pages/IncomeExpensesPage.tsx#L52): el filtro client-side `filterByEntity(records, entity)` NO aplica a entidades RUT2 (su heurística busca nombres de hijas en `Categoria1` — filtraría TODO cuando lleguen datos reales). Para RUT2: pass-through (`isRut2Entity(entity) ? records : filterByEntity(records, entity)`), o el early-return equivalente donde el dev prefiera. La semántica EAG/hijas queda byte-idéntica. → Early-return DENTRO de `filterByEntity` (cubre cualquier call-site presente/futuro y es unit-testeable); la page no cambió; semántica EAG/hijas intacta (tests existentes pasan sin tocar).
  - [x] `IncomeExpensesDrilldown` ([IncomeExpensesDrilldown.tsx:87](frontend/src/components/charts/IncomeExpensesDrilldown.tsx#L87)) usa `useLedger(accountNumber)` → hereda el fix solo; verificar que no tenga otro filtrado por entidad propio. → Verificado: `filterByEntity` solo se usa en IncomeExpensesPage y el util; el drill-down no filtra por entidad.
- [x] Task 4: Estado vacío limpio en ambas páginas (AC: 3)
  - [x] `BalanceSheetPage`: con FFCC/JAB el backend per-entity devuelve `data=[]` → ya cae en el empty state existente "No hay datos para el período seleccionado" ([BalanceSheetPage.tsx:101-107](frontend/src/pages/BalanceSheetPage.tsx#L101-L107)). Verificar, no reescribir. → Verificado: `useBalanceSheet` pasa `entity` directo al API y ya lleva la entidad en su queryKey; cero cambios.
  - [x] `IncomeExpensesPage`: tras Task 3, con FFCC/JAB el fetch devuelve `data.data=[]` → dispara el mismo empty state ([IncomeExpensesPage.tsx:108-114](frontend/src/pages/IncomeExpensesPage.tsx#L108-L114)). Sin Task 3 este AC es falso-verde: el fetch de EAG trae data no-vacía y la página renderiza tarjetas en 0 con el `last_sync` de EAG. → Verificado tras Task 3 (fetch per-entity real → `data=[]` → empty state).
  - [x] No tocar el texto del empty state ("período seleccionado" vs "entidad" es cosmético — cambio quirúrgico solamente). → No tocado.
- [x] Task 5: Tests frontend + suites completas (AC: 1, 2, 3)
  - [x] Vitest: (a) `ledgerAnalytics.test.ts` ya existe — agregar caso pass-through RUT2 si el pass-through vive ahí, o testear el punto donde viva; (b) test del ruteo de `useLedger` (FFCC → fetch con `entity=FFCC` y queryKey distinto; EAG/Jocelyn → fetch con `entity=EAG`) — mock de `getLedgerEntries` estilo tests existentes; (c) render de `EntityFilter` con las 7 opciones y default EAG (patrón de [Sidebar.test.tsx](frontend/src/components/layout/Sidebar.test.tsx)). → 6 tests nuevos: 1 pass-through + 3 ruteo useLedger (`useLedger.test.tsx` nuevo) + 1 EntityFilter (`EntityFilter.test.tsx` nuevo); vitest 126/126.
  - [x] `npx tsc --noEmit` verde (el union `Entity` propaga solo). → Verde.
  - [x] Backend: `python -m pytest backend/tests -q` desde la raíz — baseline 777 passed/1 xfailed, 0 regresiones. → 782 passed/1 xfailed (+5 tests nuevos, 0 regresiones).
  - [x] Commitear al cerrar la story (retro Epic 6 — no acumular working tree). → Commit al cierre de esta sesión dev.

### Review Findings

Code review 2026-07-11 (3 capas: Blind Hunter, Edge Case Hunter, Acceptance Auditor). Auditor: **AC1/AC2/AC3 PASS** — todas las afirmaciones del Dev Agent Record verificadas ciertas (suites reproducidas: vitest 126/126, tsc limpio, test_dashboard 22/22). 0 decision-needed, 1 patch, 3 defer, 6 dismiss.

- [x] [Review][Patch] Falta el caso positivo per-entity con datos: los tests del router prueban FFCC/JAB solo contra ledger vacío (200 + `data==[]`) — una entidad registrada pero mal wireada daría el mismo resultado. 11.1 ya cubre aislamiento EAG y consolidado del grupo CON datos (`_multilibro_ledger`, test_bql_queries.py:278-317), pero nadie prueba que `entity=FFCC` devuelve el slice FFCC ni `ledger-entries` JAB con datos. Fix: +2 tests reusando el RUT2_BLOCK/multilibro existente. [backend/tests/test_dashboard.py:154] — **APLICADO**: `test_balance_sheets_ffcc_with_data_returns_only_ffcc_slice` + `test_ledger_entries_jab_with_data_returns_only_jab_postings` (ledger `MINI_LEDGER + RUT2_BLOCK`; slice propio, excluye EAG y la otra entidad RUT2). Suite backend 784 passed/1 xfailed, 0 regresiones.
- [x] [Review][Defer] `_entity_pattern` sin `(?-i:)`: el balance-sheet per-entity (BQL, re.IGNORECASE) matchearía una cuenta mal-caseada (`Assets:Jab:...`) que ledger-entries (Python re, case-sensitive) y el consolidado del grupo (`(?-i:)` de 11.1) excluyen → vistas inconsistentes en silencio. Pre-existente del motor (defer conocido de 11.1, "cero cambios de motor" en esta story); mitigado porque 12.3 genera el árbol con los labels exactos. Hardening candidato para 12.3. [backend/app/services/bql_queries.py:56-58] — deferred, pre-existing
- [x] [Review][Defer] `getLedgerCategory` está calibrado al plan EAG/Laudus (prefijo 4→ingreso, 5|6→gasto, else `other`): registros RUT2 sin keywords ingreso/gasto en Categoria1/2 (ej. código 810001, o cuentas abiertas sin `laudus_categoria1`) caerían en `other` y desaparecen de totales/pies/timeline sin indicación. No actionable hasta que 12.3/12.4 fijen la metadata/categorías del libro RUT2 — **anotar en esas stories**. [frontend/src/utils/ledgerAnalytics.ts:48-52] — deferred, pre-existing (reachable recién con datos post-Epic 12)
- [x] [Review][Defer] Cuenta RUT2 sin metadata `code` → backend emite `accountnumber:""` → expandir esa fila del drill-down llama `useLedger('')`, el param se omite por falsy y la API devuelve TODO el ledger de la entidad como si fuera una cuenta. Guardia natural: 12.3 debe emitir `code` en toda cuenta del árbol RUT2. [frontend/src/services/dashboard.ts:29 + frontend/src/components/charts/IncomeExpensesDrilldown.tsx:86] — deferred, pre-existing (contingente a la disciplina de metadata de 12.3)

Dismissed (6, verificados falsos o decididos): useBalanceSheet "sin ruteo" (falso — ya lleva `entity` en queryKey y lo pasa directo al API); pass-through de `filterByEntity` "devuelve cross-entity" (por diseño — el único call path RUT2 recibe data ya filtrada server-side, contrato documentado); authz RUT2 (decisión Ary 2026-06-30: entidad hermana, sin auth nueva); layering util→context (nit, la spec lo permitió); redundancia de tests backend (nit, el parametrize cubre la asimetría); `isRut2Entity(string)` (deliberado per Task 2).

## Dev Notes

### Decisión de labels (AC1 — el único gate de negocio)

El epics doc lo dice explícito: "Ary: label corto definitivo de las entidades — se fija al ejecutar la story 11.2". La propuesta vigente (usada por 11.1 en `CONSOLIDATION_GROUPS` y por toda la documentación de planning) es:

| Concepto | Label propuesto | Dónde vive hoy |
|---|---|---|
| Sub-entidad Fondo Común (raíces 1-4) | `FFCC` | `CONSOLIDATION_GROUPS["FondoComun"]` |
| Sub-entidad rama JAB/FGK (raíces 6-8) | `JAB` | `CONSOLIDATION_GROUPS["FondoComun"]` |
| Clave del grupo consolidado del libro | `FondoComun` | clave del dict, solo nivel servicio |

Si Ary confirma la propuesta, Task 0 se reduce a quitar "PROPUESTOS" de los comentarios. Consecuencia de fijarlos: 12.3 crea las 308 hojas como `{Root}:FFCC:...` / `{Root}:JAB:...` y `Equity:FFCC:Apertura` — un rename posterior sería re-generar el árbol entero. Por eso el gate va PRIMERO.

### Restricciones de labels (defer del code-review 11.1 — obligatorias)

- **Alfanuméricos, sin metacaracteres de regex ni comillas**: los labels van crudos a `_group_pattern` → BQL `account ~ "..."` ([bql_queries.py:67-79](backend/app/services/bql_queries.py#L67-L79)); un `.` o `|` rompería el aislamiento en silencio.
- **No case-variantes** de {EAG, Jocelyn, Jeannette, Johanna, Jael} ni entre sí: el patch `(?-i:)` de 11.1 hace el matching case-sensitive — `jael` vs `Jael` serían entidades distintas para el motor y un typo de label sería indetectable.
- **No renombrar "EAG"**: `report_rows_via_beancount` hardcodea la clave `"EAG"` ([bql_queries.py:247](backend/app/services/bql_queries.py#L247)) — un rename daría `KeyError` 500 en runtime. Fuera de alcance tocarlo (defer conocido de 11.1); solo aplica si Ary quisiera renombrar EAG, que no está sobre la mesa.

### ⚠️ TRAP #1 — `useLedger` pide EAG SIEMPRE y filtra client-side (rompe AC3 y el end-to-end si se ignora)

Verificado en código: [useLedger.ts:8](frontend/src/hooks/useLedger.ts#L8) hardcodea `SHEET_ENTITY = 'EAG'` (legacy Sheets: "los datos de las hijas viven dentro de EAG, filtrar por `Categoria1`") y [ledgerAnalytics.ts:11-18](frontend/src/utils/ledgerAnalytics.ts#L11-L18) filtra por substring del nombre de la hija en `Categoria1`. Consecuencias si solo se agregan FFCC/JAB al selector sin Task 3:

1. **AC3 falso-verde hoy**: seleccionar FFCC fetchea la data de EAG (no vacía) → el empty check `data.data.length === 0` no dispara → página con tarjetas en $0, pies vacíos y el `last_sync` de EAG. No es "estado vacío limpio".
2. **Roto end-to-end mañana**: cuando Epic 12 importe los datos del Fondo Común, `filterByEntity(records, 'FFCC')` buscaría "FFCC" dentro de `Categoria1` de registros de EAG → FFCC mostraría $0 para siempre. La story debe dejar el sistema funcionando cuando lleguen los datos, no solo cumplir el AC literal.
3. **Cache stale**: el `queryKey` de useLedger no incluye entidad — al cambiar el ruteo es OBLIGATORIO agregarla o react-query cruza caches entre entidades.

Diseño recomendado (decisión técnica, auto-aprobada per project-context): las entidades del libro RUT2 se filtran **server-side** (per-entity real del backend: `^(roots):FFCC:` ya funciona vía `_entity_pattern`, 11.1 no lo tocó); las del libro EAG conservan su semántica client-side **byte-idéntica** (pasar `Jocelyn` al API cambiaría qué registros ve — regresión). El discriminador es `RUT2_ENTITIES`/`isRut2Entity` exportado de FilterContext (Task 2).

### Decisión: el grupo consolidado NO entra al selector (alcance mínimo)

FR47 dice "FFCC, JAB **y/o** su grupo consolidado" y el AC de la story solo exige FFCC y JAB. Agregar `FondoComun` al selector hoy: (a) no lo pide el AC, (b) en Ingresos y Gastos devolvería vacío incluso con datos (per-entity `^(roots):FondoComun:` no matchea nada — el consolidado por grupo solo existe en `balance_sheet_via_beancount`), o exigiría wirear el ruteo por grupo en `ledger_entries` = scope creep. Queda a nivel servicio (como lo dejó 11.1); agregarlo después es trivial cuando haya datos y se pida. Si Ary lo quiere ahora, es cambio de alcance → repreguntar.

### Estado actual de cada archivo a tocar (leídos completos 2026-07-10)

| Archivo | Hoy | Cambio 11.2 | Preservar |
|---|---|---|---|
| [schemas.py:7](backend/app/api/v1/dashboard/schemas.py#L7) | `VALID_ENTITIES` = 5 entidades EAG | `+ FFCC, JAB` | resto del archivo intacto |
| [router.py:24-31](backend/app/api/v1/dashboard/router.py#L24-L31) | `_validate_entity` → 422 con `sorted(VALID_ENTITIES)` | solo descriptions | validación de fechas, RBAC |
| [FilterContext.tsx](frontend/src/contexts/FilterContext.tsx) | `Entity` union + `ENTITIES` + default `'EAG'` | union/array + export RUT2 | default EAG, date presets |
| [useLedger.ts](frontend/src/hooks/useLedger.ts) | `SHEET_ENTITY='EAG'` fijo, queryKey sin entidad | ruteo por libro + queryKey | staleTime, firma `accountNumber` |
| [ledgerAnalytics.ts:11-18](frontend/src/utils/ledgerAnalytics.ts#L11-L18) | `filterByEntity` heurística Categoria1 | pass-through RUT2 (aquí o en la page) | semántica EAG/hijas intacta |
| [IncomeExpensesPage.tsx:52](frontend/src/pages/IncomeExpensesPage.tsx#L52) | `filterByEntity(records, entity)` incondicional | condicionar por libro | cadena de memos, empty/error states |
| [bql_queries.py:30-40](backend/app/services/bql_queries.py#L30-L40) | labels "PROPUESTOS" en comentarios | fijar (o rename si Ary cambia) | `_group_pattern`, `(?-i:)`, lru_cache |

`EntityFilter.tsx`, `useBalanceSheet.ts`, `BalanceSheetPage.tsx`, `dashboard/service.py`: **cero cambios** — mapean/propagan y ya se comportan bien con la entidad nueva (verificado: `useBalanceSheet` pasa `entity` directo al API; `BalanceSheetPage` tiene empty state).

### Qué NO tocar

- **`ledger_entries_via_beancount` / `balance_sheet_via_beancount`**: el backend ya resuelve FFCC/JAB per-entity correcto (patrón `^(roots):FFCC:` → vacío hoy, datos reales post-Epic 12). Cero cambios de motor.
- **`filterByEntity` para EAG/hijas**: no "modernizar" a server-side de pasada — cambiaría qué registros ve el filtro de hijas (regresión funcional). Solo el pass-through RUT2.
- **Página de reportes** (`/reportes`): oculta los filtros de entidad ([DashboardLayout.tsx:11](frontend/src/components/layout/DashboardLayout.tsx#L11)) y el reporte RUT2 es Epic 13. Nada aquí.
- **Texto/UX del empty state y del selector `<select>` nativo**: quirúrgico, sin rediseños.
- **`report_rows_via_beancount`** y su hardcode `"EAG"`: defer conocido de 11.1, no aplica mientras EAG no se renombre.

### Testing

- Frontend: vitest (`cd frontend && npx vitest run`), patrón de mocks de services en tests existentes ([CategorizacionPage.test.tsx](frontend/src/pages/CategorizacionPage.test.tsx), [IncomeExpensesDrilldown.test.tsx](frontend/src/components/charts/IncomeExpensesDrilldown.test.tsx)); baseline ~120 tests verdes. `npx tsc --noEmit` obligatorio.
- Backend: patrón `_make_app(tmp_path)` + `MINI_LEDGER` importado de `test_bql_queries` ([test_dashboard.py:28-39](backend/tests/test_dashboard.py#L28-L39)); cookies `access_token` con `_family()`/`_contador()`. Baseline 777 passed/1 xfailed (el rojo date-dependiente pre-existente documentado no cuenta como regresión). Gotcha Windows: `PYTHONUTF8=1` para scripts de smoke.
- Esta story NO escribe al ledger → bean-check no aplica como gate (correrlo si se quiere evidencia, será trivialmente verde).

### Lecciones de trabajo previo aplicables

- **11.1 (story previa, done)**: los labels van crudos a regex/BQL → restricciones duras arriba; el aislamiento es case-sensitive por el patch `(?-i:)`; el grupo quedó consultable a nivel servicio y el router gateado por `VALID_ENTITIES` — esta story abre exactamente esa compuerta.
- **9.15/11.1 (gates)**: un chequeo que compara vacíos da falso GO — el AC3 de esta story tiene la versión frontend de esa trampa (TRAP #1.1: página con ceros ≠ estado vacío).
- **Retro Epic 6**: commitear al cerrar la story.
- **PR #18 (fix "Otros")**: el frontend agrupa el balance por la raíz del path beancount (`account`), no por primer dígito del código — las cuentas JAB (raíz 6 = Assets) se agruparán bien cuando existan, sin cambios.

### Project Structure Notes

- Frontend: contexts/hooks/pages/utils bajo `frontend/src/` — los cambios respetan la estructura existente, sin archivos nuevos de producto (a lo sumo un test nuevo junto a sus pares `*.test.tsx`).
- Backend: solo `schemas.py` (+descriptions en `router.py`) bajo `backend/app/api/v1/dashboard/`. Sin migraciones, sin env vars, sin cambios de deploy (Render redeploya del mismo repo; frontend static se rebuildeá igual).
- Alineado con architecture-c4 (Beancount fuente única; frontend thin API). Sin conflictos detectados.

### References

- [Source: _bmad-output/planning-artifacts/epics-segundo-rut.md#Story 11.2] — story y ACs canónicos; FR47; "Ary: label corto definitivo — se fija al ejecutar la story 11.2".
- [Source: _bmad-output/implementation-artifacts/11-1-grupos-consolidacion-explicitos.md#Review Findings] — defer "Notas para 11.2": hardcode `"EAG"`, labels alfanuméricos sin metacaracteres.
- [Source: _bmad-output/planning-artifacts/implementation-readiness-report-2026-07-10.md] — FR47 → Story 11.2, READY.
- [Source: backend/app/services/bql_queries.py#L30-L79] — `CONSOLIDATION_GROUPS` + `_group_pattern` (estado post-11.1, leído completo).
- [Source: frontend/src/hooks/useLedger.ts; frontend/src/utils/ledgerAnalytics.ts#L11-L18] — TRAP #1 verificado en código.
- [Source: backend/tests/test_dashboard.py#L28-L39] — patrón de test del router con mini-ledger.

## Dev Agent Record

### Agent Model Used

Claude Fable 5 (claude-fable-5) — dev-story workflow BMAD, 2026-07-11.

### Debug Log References

- Ciclo red-green backend: los 4 tests nuevos de FFCC/JAB fallaron primero (422, entidades no registradas) → GREEN tras agregar al frozenset. Suite dashboard 22/22.
- Suite backend completa: 782 passed / 1 xfailed en 140s (baseline 777+1; +5 = 3 tests nuevos + 2 casos nuevos del parametrize). 0 regresiones.
- Frontend: vitest 126/126 (19 archivos; +6 tests nuevos), `npx tsc --noEmit` limpio.

### Completion Notes List

- **AC1 (gate labels):** resuelto sin re-preguntar — la decisión ya estaba registrada: Ary devolvió el Excel de clasificación el 2026-07-11 con 357/357 filas confirmadas, ratificando FFCC / JAB / FondoComun (`valentina-contexto-fondo-comun-jab-2026-07-11.md` §6). Restricciones duras validadas (alfanuméricos, sin metacaracteres, no case-variantes de miembros EAG ni entre sí). Comentario "PROPUESTOS" → "DEFINITIVOS" en `bql_queries.py`; `CONSOLIDATION_GROUPS` y su test quedaron intactos (los labels coincidieron con la propuesta). Las stories 12.3/12.4 pueden usar `{Root}:FFCC:...` / `{Root}:JAB:...` / `Equity:FFCC:Apertura` sin cambios.
- **AC2 (selector):** `VALID_ENTITIES` = 7 entidades (backend) + union `Entity`/`ENTITIES` extendidos (frontend). `EntityFilter` mapea `ENTITIES` → mostró FFCC/JAB sin cambios propios. Default EAG intacto (test lo cubre). El grupo `FondoComun` NO entró al selector (decisión de alcance de la story; sigue solo a nivel servicio).
- **AC3 (estado vacío limpio) — TRAP #1 neutralizado:** `useLedger` ahora rutea por libro (`apiEntity = isRut2Entity(entity) ? entity : 'EAG'`) y lleva `apiEntity` en la queryKey — sin esto react-query servía el cache de EAG al seleccionar FFCC. Test conductual: EAG→FFCC refetchea en vez de servir cache. El pass-through RUT2 se implementó como early-return dentro de `filterByEntity` (decisión técnica auto-aprobada: cubre todo call-site y es unit-testeable desde `ledgerAnalytics.test.ts`); la semántica EAG/hijas quedó byte-idéntica (los 6 tests existentes de `filterByEntity` pasan sin modificación). Con datos reales post-Epic 12, FFCC/JAB mostrarán su slice server-side (`^(roots):FFCC:` ya funciona desde 11.1).
- **Cero cambios** en `EntityFilter.tsx`, `useBalanceSheet.ts`, `BalanceSheetPage.tsx`, `IncomeExpensesPage.tsx`, `dashboard/service.py`, motores BQL — verificados, no reescritos (el pass-through vive en el util, no en la page).
- `isRut2Entity` acepta `string` (no solo `Entity`) para servir a `filterByEntity` sin casts.

### File List

- `backend/app/api/v1/dashboard/schemas.py` — VALID_ENTITIES + FFCC/JAB (con comentario de alcance)
- `backend/app/api/v1/dashboard/router.py` — descriptions de los Query params (×2)
- `backend/app/services/bql_queries.py` — comentario labels PROPUESTOS → DEFINITIVOS (Task 0)
- `backend/tests/test_dashboard.py` — 3 tests nuevos RUT2 + parametrize extendido a 7 entidades
- `frontend/src/contexts/FilterContext.tsx` — union `Entity` + `ENTITIES` + `RUT2_ENTITIES`/`isRut2Entity`
- `frontend/src/hooks/useLedger.ts` — ruteo por libro + entidad en queryKey
- `frontend/src/utils/ledgerAnalytics.ts` — early-return pass-through RUT2 en `filterByEntity`
- `frontend/src/utils/ledgerAnalytics.test.ts` — test pass-through RUT2
- `frontend/src/hooks/useLedger.test.tsx` — NUEVO: 3 tests de ruteo/queryKey
- `frontend/src/components/filters/EntityFilter.test.tsx` — NUEVO: 7 opciones + default EAG
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — 11-2 → in-progress → review

## Change Log

- 2026-07-11 — Story 11.2 implementada (dev-story, Claude Fable 5): labels FFCC/JAB/FondoComun fijados como definitivos (ratificación Ary vía Excel 357/357); FFCC/JAB registradas en `VALID_ENTITIES` y en el selector de entidad; `useLedger` rutea por libro con entidad en la queryKey (fix TRAP #1: cache cruzado + falso-verde del empty state); pass-through RUT2 en `filterByEntity`. +5 tests backend (782 passed/1 xfailed), +6 tests frontend (126/126), tsc verde. Status → review.
