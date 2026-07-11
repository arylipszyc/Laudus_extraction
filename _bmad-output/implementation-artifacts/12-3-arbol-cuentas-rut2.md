# Story 12.3: Pre-crear el árbol de cuentas de RUT2 con Equity de apertura

Status: done

## Story

As contador (usuario del sistema),
I want el plan de cuentas completo del Fondo Común pre-creado en el ledger según la clasificación firmada,
so that cualquier import posterior tenga destino correcto y nada caiga en cuentas de EAG ni en cuarentena masiva.

## Acceptance Criteria

1. **Given** el mapeo firmado en 12.1 (`clasificacion-contable-rut2-firmada-2026-07-11.md`) y el plan real (`rut2-plan-cuentas-laudus-2026-07-10.json`),
   **When** se genera el subárbol en `ledger/accounts.beancount`,
   **Then** existen las **309 hojas** (FR48 — OJO: el epic dice 308, el artefacto §6 fija 309 como autoritativo) bajo `{Root}:{Entidad}:{slug}-{código}` según su raíz (1=Assets/2=Liabilities/3=Income/4=Expenses para FFCC; 6=Assets/7=Income/8=Expenses para JAB), con slug = `bootstrap/account_mapping.slugify` (IMPORTAR la función, no copiarla),
   **And** las cuentas bancarias llevan `bank_account_id` (UUID minteado) en metadata,
   **And** las 48 cuentas intermedias del plan NO se crean (artefacto §8).

2. **Given** que el plan de RUT2 no tiene raíz de patrimonio,
   **When** se crea el subárbol,
   **Then** existen `Equity:FFCC:Apertura` y `Equity:JAB:Apertura` con la convención firmada en 12.1 §3 (FR49 — la letra del epic dice "una cuenta"; el artefacto firma DOS, una por sub-entidad, y SUPERSEDE al epic), con metadata del precedente TC:Real: `laudus_categoria1: "PATRIMONIO"`, `laudus_categoria2/3: ""`, code sintético único, sin `bank_account_id`.
   **Total de opens nuevos = 311** (309 hojas + 2 Equity).

3. **Given** el ledger con el subárbol nuevo,
   **When** corre la validación,
   **Then** `bean-check` sale en 0 (NFR21),
   **And** los reportes de EAG quedan idénticos peso-por-peso (NFR20) — gate 0-diffs estilo 11.1 (dump antes/después, fail-safe si el dump viene vacío),
   **And** la suite backend completa pasa sin regresiones.

## Tasks / Subtasks

- [x] Task 1: Script generador one-off (AC: 1, 2)
  - [x] Crear `bootstrap/generate_rut2_accounts.py` (patrón del retirado `generate_accounts.py`: one-off, disaster-recovery-only después de correrse; NO cron, NO endpoint). Lee el JSON del plan + implementa el artefacto §8.
  - [x] Por cada una de las 309 hojas: `{Root}:{Entidad}:{slugify(name)}-{accountNumber}` — `slugify` IMPORTADO de `bootstrap/account_mapping.py:86`. Metadata: `code`, `laudus_account_name` (nombre Laudus original), `laudus_categoria1` = nombre de la raíz (ej. "ACTIVO FFCC", "GASTOS JAB"), `laudus_categoria2` = nombre del ancestro de 2 dígitos, `laudus_categoria3` = nombre del ancestro de 3 dígitos (jerarquía por prefijo de accountNumber; si falta el nivel → `""`).
  - [x] `bank_account_id`: mintear `uuid4` SOLO para cuentas bancarias reales (criterio espejo EAG: hojas de raíces 1/6 cuyo nombre indica banco — "Banco *"; las Cajas NO llevan, ver `Assets:EAG:Caja-111001` sin UUID). Acompañar con `bank_name` / `bank_account_type: "cta_corriente"` / `bank_account_currency` derivados del nombre, espejo del bloque EAG (`accounts.beancount:25-67`).
  - [x] Las 2 Equity per convención firmada (artefacto §3): codes sintéticos con prefijo 9 (raíz 9 no existe en el libro → cero colisión bajo (entidad,code)); metadata precedente TC:Real (`accounts.beancount:2020-2046`).
  - [x] Defaults técnicos (auto-aprobados per project-context, documentar en Dev Agent Record): fecha open `2020-12-31` (espejo EAG); moneda `CLP` para todo, `CLP, USD` solo en bancos cuyo nombre marca US$ (espejo EAG `111011`).

- [x] Task 2: Append a `accounts.beancount` + bean-check (AC: 1, 2, 3)
  - [x] El bloque RUT2 se APPENDEA al final con comentario de sección (el archivo es SoT editable por append — header líneas 1-8; generate_accounts.py está retirado, NO re-correrlo)
  - [x] `bean-check` exit 0 sobre el ledger completo

- [x] Task 3: Gate 0-diffs reportes EAG (AC: 3)
  - [x] Dump de balance consolidado EAG + reporte de gastos ANTES y DESPUÉS del append → byte-idéntico (patrón del gate de 11.1, story `11-1-grupos-consolidacion-explicitos.md`; fail-safe: dump vacío = FAIL, lección 9.15)
  - [x] Verificar además que per-entity FFCC/JAB responde sano con árbol-sin-datos (11.2 ya testea el estado vacío)

- [x] Task 4: Tests y verificación (AC: 1, 2, 3)
  - [x] Test(s) que verifican sobre el ledger real: 311 opens nuevos con prefijos `:FFCC:`/`:JAB:`/`Equity:FFCC:`/`Equity:JAB:`; toda hoja RUT2 tiene metadata `code` (cierra el defer de 11.2 "cuenta sin code rompe drill-down"); ninguna cuenta nueva bajo namespace EAG
  - [x] Suite backend completa: 0 regresiones (784 passed/1 xfailed baseline)
  - [x] Commitear al cerrar (acuerdo retro)

## Dev Notes

### Autoridad y fuentes — NO re-derivar

**El artefacto firmado `_bmad-output/planning-artifacts/clasificacion-contable-rut2-firmada-2026-07-11.md` es LA autoridad** (su §8 lista exactamente qué consume esta story). Números verificados mecánicamente (re-ejecutable: `_bmad-output/planning-artifacts/_forense_verify_rut2_plan.py`): 357 cuentas, 309 hojas (26/1/9/63 FFCC + 12/2/196 JAB), 0 huérfanas, 0 duplicados. **El "308" del epic es deriva documentada — generar contra 309.**

### TRAPs conocidos (del code-review de 12.1)

1. **Slug**: usar `bootstrap/account_mapping.slugify` importado. Ej. verificado: `"Caja US$ - Fondo Común"` → `CajaUsFondoComn` (NO `CajaUs`). 131 hojas tienen caracteres no triviales. Regla del slugify: si el resultado no arranca en mayúscula, se antepone `X`.
2. **31 grupos de hojas comparten nombre** bajo el mismo (root, entidad) — el sufijo `-{código}` garantiza unicidad; el script debe assertar paths únicos post-generación.
3. **`Liabilities:JAB` NO existe** (JAB sin raíz 2). Combinaciones válidas: FFCC×{Assets,Liabilities,Income,Expenses}, JAB×{Assets,Income,Expenses}.
4. **bank_account_index fallback EAG** (`backend/app/integrations/bank_account_index.py:111`): NO arreglarlo aquí — es fix de 12.2 (deferred-work.md). Esta story solo mintea los UUIDs en metadata.
5. **Equity sin segmento de entidad = contaminación EAG** — los nombres firmados `Equity:FFCC:Apertura`/`Equity:JAB:Apertura` ya cumplen 11.1; no inventar variantes.

### Precedentes en el repo (mirar antes de codear)

- Formato de open + metadata: `ledger/accounts.beancount:11-67` (cuentas normales y bancarias EAG), `:2020-2046` (sintéticas TC:Real con cat2/3 vacías).
- Gate 0-diffs: story 11.1 lo implementó sobre 56 cuentas/19.989 filas del ledger real — reusar el approach.
- El plan JSON es UTF-8 limpio (0 mojibake real; el "ComÃºn" visible con encoding equivocado es artefacto de lectura — leer con `encoding="utf-8"`).

### Coordinación con 12.2 (corre EN PARALELO)

12.2 refactoriza el importador (pipeline/backend). **Esta story NO toca `pipeline/`, `backend/app/` (salvo tests nuevos propios) ni el importador.** Archivos de esta story: `bootstrap/generate_rut2_accounts.py` (nuevo), `ledger/accounts.beancount` (append), tests nuevos. Cero solape esperado con 12.2.

### Qué NO hacer (scope guard)

- NO importar datos de RUT2 — eso es 12.4
- NO tocar el importador / account_mapping (solo importar `slugify` de ahí) — eso es 12.2
- NO tocar `bank_account_index` — defer asignado a 12.2
- NO crear cuentas `TC:Real` para 871005/873005 (estado-1: hojas de gasto normales, artefacto §5)
- NO tocar cuentas EAG existentes ni el frontend

### References

- [Source: _bmad-output/planning-artifacts/clasificacion-contable-rut2-firmada-2026-07-11.md#8] — QUÉ consume esta story (autoridad)
- [Source: _bmad-output/planning-artifacts/rut2-plan-cuentas-laudus-2026-07-10.json] — las 357 cuentas reales
- [Source: bootstrap/account_mapping.py:86-103] — slugify canónico
- [Source: ledger/accounts.beancount:1-8] — política de edición por append; generate_accounts.py retirado
- [Source: _bmad-output/implementation-artifacts/11-1-grupos-consolidacion-explicitos.md] — patrón gate 0-diffs
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — defers de 11.2 que esta story cierra (code en toda cuenta) y el de bank_account_index que NO toca

## Dev Agent Record

### Agent Model Used

Claude Fable 5 (claude-fable-5) — dev-story workflow BMAD, worktree aislado (12.2 en paralelo).

### Debug Log References

- **Entorno verificado antes de confiar en la suite:** `backend.app.services.bql_queries.__file__` resuelve al WORKTREE (los tests importan `backend.app.*` por rootdir, no hay editable install en el venv del checkout principal). Scripts del gate corridos con `PYTHONPATH=<worktree>` + `PYTHONUTF8=1`.
- **Gate 0-diffs (Task 3):** dump ANTES = 56 cuentas balance consolidado EAG + 19.989 filas report_rows (idéntico al baseline de 11.1; no-vacío → fail-safe OK). Dump DESPUÉS del append: mismos conteos, `cmp` **byte-idéntico → PASS**. Script del gate en scratchpad de sesión (one-shot, no commiteado, patrón 11.1 Task 4).
- **Per-entity FFCC/JAB/FondoComun** sobre el ledger real post-append: `balance_sheet_via_beancount` responde sano con `data: []` (árbol sin datos, sin excepción) — consistente con el estado vacío que 11.2 ya testea.
- **bean-check:** `python -m beancount.scripts.check ledger/main.beancount` exit **0** (picklecaches borrados antes, lección del repo).
- **Suite completa:** `PYTHONUTF8=1 pytest backend/tests pipeline -q` → **792 passed, 1 xfailed** (baseline 784 + 8 tests nuevos de esta story, 0 regresiones, 0 rojos).

### Completion Notes List

- **Generador (Task 1):** `bootstrap/generate_rut2_accounts.py` one-off (patrón del retirado `generate_accounts.py`); ya corrido — el output quedó commiteado en `accounts.beancount` y el script se auto-protege con el marcador de sección (re-correr → ABORT). Importa `slugify` de `bootstrap.account_mapping` (no copiado). Asserts internos: 357 cuentas, 309 hojas, distribución §4 exacta, paths únicos post-slugify (TRAP 31 dupes), 311 opens, ningún path pre-existente en el archivo.
- **Append (Task 2):** bloque RUT2 al final de `accounts.beancount` con comentario de sección que documenta origen, convención, exclusión de intermedias, TC estado-1 y las reglas §3.4/§3.5 de las Equity. Nada de lo existente editado (append puro, verificable en el diff).
- **Resultado:** 311 opens — Assets:FFCC 26 · Liabilities:FFCC 1 · Income:FFCC 9 · Expenses:FFCC 63 · Assets:JAB 12 · Income:JAB 2 · Expenses:JAB 196 · Equity:FFCC:Apertura + Equity:JAB:Apertura. 6 `bank_account_id` (uuid4) minteados: 111005, 111007 (FFCC), 611004, 611005, 611006, 611007 (JAB); 611007 con `CLP, USD` + `bank_account_currency: "USD"`.
- **Decisiones técnicas (defaults auto-aprobados, documentadas):**
  1. Fecha open `2020-12-31` en las 311 (espejo EAG).
  2. Moneda `CLP` para todo; `CLP, USD` SOLO en bancos con marcador de dólar. **Desvío menor de la letra:** el único banco USD del plan (611007 "Banco BCI USD FGK 19681721") marca `USD` y no `US$` — tratado como el mismo marcador (espejo de intención del precedente EAG 111011). "Caja US$" y "Fondos por Rendir - US$" NO son bancos → quedan `CLP` (default literal de la story, mismo trato que `Assets:EAG:CajaUs`).
  3. Codes Equity sintéticos: `900001` (FFCC) / `900002` (JAB) — 9-prefix, únicos bajo (entidad, code).
  4. `bank_name` derivado del nombre espejo EAG: `Edwards` → `"Banco Chile"` (precedente `accounts.beancount:43`), `BCI` → `"BCI"`; los 6 bancos son `cta_corriente`.
  5. `laudus_categoria2/3` por ancestro ESTRICTO por prefijo (2/3 dígitos): la única hoja no-6-dígitos del plan, `13` "ACTIVOS NO CORRIENTES" (rama vacía), queda con cat2/cat3 `""` — lectura literal de "si falta el nivel → `""`"; su `code` queda `"13"` verbatim (espejo Laudus, sin normalizar a 130000).
- **Tests (Task 4):** `backend/tests/test_rut2_accounts_tree.py` — 8 tests sobre el LEDGER REAL: 311 opens; bijección path-completo hoja-del-plan ↔ open (recalcula la convención firmada con el slugify canónico); toda cuenta RUT2 con `code` y sufijo `-{code}` coherente (cierra el defer de 11.2); toda cuenta con cat1 no-vacía (guard 10.2); convención Equity §3 completa; bancos con uuid4 válido + metadata + unicidad GLOBAL de bank_account_id; distribución §4; ninguna cuenta nueva bajo namespace EAG (check por sección del archivo). **Hallazgo del dev:** el check "ninguna cuenta RUT2 bajo EAG" NO puede hacerse por par (code, nombre) — ambos libros Laudus comparten pares legítimos (ej. `115001` "Cuentas Corrientes del Personal" existe en EAG Y en RUT2); el test lo documenta.
- **Desvío de setup (documentado):** el worktree nació en `fc41836`, 5 commits detrás del main local que contiene los insumos de esta story (artefacto firmado 12.1, JSON del plan, 11.2). Se hizo `git merge --ff-only main` (fast-forward limpio, el branch no tenía commits propios) antes de empezar. El story file 12-3 estaba untracked en el checkout principal → copiado al worktree y commiteado aquí.
- **Scope guard respetado:** cero cambios en `pipeline/`, `backend/app/`, frontend, `bank_account_index` (fallback EAG queda para 12.2 per deferred-work), tests existentes, cuentas EAG. Ninguna TC:Real para 871005/873005 (estado-1).

### File List

- `bootstrap/generate_rut2_accounts.py` (nuevo — generador one-off, ya corrido, registro/disaster-recovery)
- `ledger/accounts.beancount` (APPEND del bloque RUT2: 311 opens + comentario de sección; nada existente tocado)
- `backend/tests/test_rut2_accounts_tree.py` (nuevo — 8 tests sobre el ledger real)
- `_bmad-output/implementation-artifacts/12-3-arbol-cuentas-rut2.md` (story file)

### Review Findings

Code review adversarial 3 capas (Blind Hunter / Edge Case Hunter / Acceptance Auditor), 2026-07-11. **AC1/AC2/AC3: PASS** — el Edge Hunter re-verificó mecánicamente TODOS los claims del Dev Record: 311 opens (309 hojas distribución §4 exacta + 2 Equity), append puro (+2217/−0, prefijo byte-exacto), bijección slug/path 309/309 con el slugify canónico, metadata de jerarquía 0 errores en las 309 (exhaustivo, no muestra), 6 UUIDs v4 únicos globalmente solo en "Banco *", Equity == precedente TC:Real, generador ABORT en re-run y reproduce el bloque byte-idéntico módulo UUIDs. Gates del orquestador: suite 836→842 passed / 1 xfailed, bean-check exit 0, 0-diffs EAG byte-idéntico (56 cuentas / 19.989 filas vs 013f0c8). Desvíos declarados (marcador USD, hoja "13", codes 9xxxxx) evaluados FIELES. Triage: 0 decision-needed / 1 patch / 3 defer / 5 dismiss.

**Patch aplicado:**
- [x] Endurecimiento de `test_rut2_accounts_tree.py` (el contenido estaba correcto; los tests no lo pinneaban): nuevo `test_metadata_de_hojas_fiel_al_plan` (laudus_account_name + cat1/2/3 de las 309 hojas contra la jerarquía del plan — el reporte de gastos agrupa por Categoria2 y un bug ahí era invisible), nuevo `test_fecha_y_monedas_de_los_opens` (2020-12-31 en las 311; CLP salvo 611007 CLP+USD), bancos pinneados (bank_name exacto Edwards→"Banco Chile"/BCI, currency por banco, uuid **version 4**), y `len(plan_leaves) == 309` ANTES del set (una colisión de paths ya no se auto-oculta). 8 → 10 tests, todos verdes.

**Defer (anotados en deferred-work.md § 12-3):**
- [x] Cuentas cash-US$ solo-CLP (111003/115007/613007) — herencia del espejo EAG, latente para el import 12.4.
- [x] Hoja code `"13"` verbatim vs normalización a 6 dígitos — mina latente para consumidores futuros que normalicen.
- [x] UUIDs no reproducibles en re-run disaster-recovery del generador — los commiteados son los canónicos.

**Dismiss (falsos positivos/adjudicados):** intermedias de 4-5 dígitos que perderían nombre (no existen: intermedias del plan son 1/2/3 dígitos, verificado); test espejo "semi-tautológico" (la convención firmada ES la autoridad; el patch ancla además nombres/categorías al plan); test de namespace frágil ante appends futuros (pin deliberado del estado — romperse ante un append legítimo es señal, no bug); bancos RUT2 planos sin segmento `Bancos:` (convención firmada §1; la detección canónica es por `bank_account_id`); contaminación pre-marcador no testeable (garantizada por el append-puro verificado en el diff + gate 0-diffs).

## Change Log

- 2026-07-11: Story 12.3 implementada completa (Tasks 1–4) — 311 opens RUT2 (309 hojas FFCC/JAB + 2 Equity de apertura) appendeados a `accounts.beancount` vía generador one-off; bean-check exit 0; gate 0-diffs EAG byte-idéntico (56 cuentas / 19.989 filas); suite 792 passed / 1 xfailed (0 regresiones). Status → review.
- 2026-07-11: Code review 3 capas → 1 patch de tests aplicado (10/10 verdes), 3 defers anotados, gates re-verificados por el revisor (suite 842/1, bean-check 0, 0-diffs byte-idéntico). Status → done.
