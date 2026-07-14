# Story 13.1: Reporte del Fondo Común (FFCC / JAB) — gastos + distribuciones a hijos/nietos

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Ary (dueño),
I want un reporte del Fondo Común (RUT2) que muestre en qué gasta la rama JAB/FGK **y** cuánto retiró / cuánto debe (o tiene a favor) cada hijo/nieto,
so that responda las dos preguntas reales del fondo: *¿en qué se gasta?* y *¿cómo está la cuenta corriente de cada familiar con el fondo?*.

> **Única story del Epic 13** (cubre FR54, FR55 + la vista de distribuciones que Ary sumó al alcance el 2026-07-12). El reporte tiene **dos mitades**:
> 1. **Gastos** por encabezado numérico (mecánico, 8→81→811): FFCC `41`/`43`, JAB `81`/`83`/`85`/`87`.
> 2. **Distribuciones / cuentas por cobrar** por familiar (`115xxx` FFCC): retiros del período, repartos/abonos, y saldo al cierre.
>
> **Contexto de negocio (Ary, verificado en datos):** durante el año el FFCC hace **préstamos/adelantos** a cada hijo/nieto → quedan como **cuenta por cobrar**. A fin de año se hacen **repartos** que (idealmente) saldan la deuda. *Confirmado en el ledger: el ciclo cerró perfecto (saldo→0) en 2021 y 2022, pero desde 2023 los saldos se acumulan y no vuelven a cero* (ver Dev Notes §Distribuciones — hallazgo forense).
>
> **Precondición:** Epic 12 cerrado (`done`) — histórico RUT2 importado (12.4) y reconciliado peso-por-peso vs Laudus (12.5 PASS, 0 diffs / 237 cuentas @ 2026-06-30). Los saldos que muestre este reporte son fieles a Laudus.

## Acceptance Criteria

1. **[Gastos por encabezado — FR54]**
   **Given** los datos de RUT2 en el ledger (Epic 12 cerrado),
   **When** genero el reporte del **libro RUT2** para un período (start/end),
   **Then** obtengo una sección de **gastos con nivel 1 FFCC vs JAB**,
   **And** el **nivel 2 agrupa por encabezado numérico**: FFCC → `41` (GASTOS GENERALES), `43` (GASTOS FIJOS OFICINA); JAB → `81` (MANTENCION CASAS JAB), `83` (AVIONES), `85` (YATES), `87` (GASTOS PERSONALES),
   **And** dentro de cada encabezado se listan las cuentas hoja itemizadas (nombre + código), con subtotales/totales como **fórmulas Excel**,
   **And** la agrupación se deriva **mecánicamente** de los dígitos del código (nivel 1 = 1er dígito 4→FFCC / 8→JAB; nivel 2 = 2 primeros dígitos) y la etiqueta del encabezado sale de `laudus_categoria2` — **sin** lista hardcodeada de clasificación manual.

2. **[TC lumpeada — FR55]**
   **Given** las cuentas de TC de JAB/FGK **`871005`** (JAB - Mastercard/Visa/Amex) y **`873005`** (FGK - Mastercard/Visa/Amex),
   **When** aparecen bajo el encabezado `87` (GASTOS PERSONALES),
   **Then** se muestran lumpeadas con la limitación marcada **visiblemente en el cuerpo del reporte — NO en nota al pie** (pago mensual sin desglose, estado 1 igual que EAG).

3. **[Distribuciones / cuentas por cobrar por familiar — alcance sumado por Ary 2026-07-12]**
   **Given** las cuentas por cobrar del FFCC (`115xxx`, identificadas **mecánicamente** por `laudus_categoria3 == "CUENTAS POR COBRAR"` dentro del grupo `FondoComun` — sin lista de personas hardcodeada, respeta §7 "no acotar por rango"),
   **When** genero el reporte para un período,
   **Then** obtengo una sección de **distribuciones itemizada por cuenta** (nombre + código), cada una con: **Retiros del período** (débitos), **Repartos/abonos del período** (créditos), y **Saldo al cierre** (acumulado a la fecha `end`),
   **And** el **saldo al cierre es cumulativo** (todos los movimientos hasta `end`, no solo los del período) y cuadra con el balance reconciliado de esa cuenta,
   **And** el signo del saldo se etiqueta **"Debe al fondo"** (débito/+) vs **"A favor"** (crédito/−, = utilidad asignada no retirada) — **resuelto por Valentina 2026-07-12** (ver Dev Notes §Signo), el número es mecánico y fiel a Laudus,
   **And** las cuentas **familiares** (`Retiros*`, nombres propios) se muestran **separadas** de las **operativas** (`FondoFijo`, `FondosPorRendir`, `DeudoresVarios`, `ControlYLiquidacion` ~0) en bloques distintos — **resuelto por Valentina** (revierte el default "todas juntas"),
   **And** los **asientos wash** (+X/−X en la misma cuenta, neto 0 = reclasificaciones internas) se **netean** (se muestra el saldo neto, no el ruido bruto).

3b. **[Marca de limitación HONESTA — obligatoria, en el cuerpo — resuelto por Valentina 2026-07-12]**
   **Given** que el balance del FFCC está **incompleto** (no carga posiciones de inversión —Indumotora, Sade, Molco, Leo Partnership— ni propiedades/aviones/yates; la "caja total" es artificial por `LeoPartnershipLimited-111012` −3.096M mal clasificada en disponible),
   **When** el reporte muestra la sección de distribuciones,
   **Then** incluye una **marca de limitación visible en el cuerpo** (estilo TC, NO nota al pie) con texto honesto: *"El patrimonio real del fondo no es determinable desde Laudus — no están cargadas las inversiones ni los activos reales; estas cuentas reflejan la cuenta corriente de cada socio, no su posición neta. La caja total del fondo no es usable como 'lo que tiene'."*,
   **And** el reporte **NO afirma** ni respaldo ni des-respaldo de los saldos a favor,
   **And** la estructura del reporte deja **slots preparados para posiciones de inversión y cuentas offshore** (secciones/columnas que hoy quedan vacías o marcadas "pendiente de carga") — **decisión Ary 2026-07-13: construir as-if tendremos esa data**, de modo que poblar los saldos después reduzca la limitación sin rehacer el reporte.

4. **[0 regresión EAG — NFR20]**
   **Given** el reporte de gastos de **EAG existente** (`GET /reportes/gastos` → `report_builder.build_report`),
   **When** se introduce el reporte parametrizado de RUT2,
   **Then** el reporte de EAG queda **byte-idéntico** para el mismo período/datos, y `report_rows_via_beancount()` sin `group` sigue devolviendo el grupo EAG,
   **And** el reporte de RUT2 **solo** contiene cuentas del grupo `FondoComun` ({FFCC, JAB}); ninguna cuenta de EAG aparece y ninguna de RUT2 se filtra al reporte de EAG.

5. **[Read-only + verificación]**
   **Given** que esta story **solo lee** del ledger (genera xlsx, no escribe asientos),
   **When** termina,
   **Then** `git status ledger/` queda limpio (0 escrituras), `bean-check` sale en 0 (NFR21),
   **And** la suite backend pasa sin regresiones (re-baseline vs Task 0 — al cierre de 12.5 era **861 passed / 1 xfailed**),
   **And** el frontend `npm run typecheck` (`tsc -b`) + `npm run test` pasan en verde (project-context §Comandos — **NUNCA** `tsc --noEmit`).

## Tasks / Subtasks

- [x] Task 0: Prerequisitos y baseline (AC: todos)
  - [x] Confirmar histórico RUT2 en el checkout (`ledger/imports/laudus-rut2/` incluido en `main.beancount` [:34-36]).
  - [x] Borrar `ledger/.main.beancount.picklecache` antes de cualquier `bean-check`.
  - [x] Baseline de tests ANTES de codear: `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q` (~861/1). Anotar el número exacto.
  - [x] Confirmar la sonda de datos (reproducible): existen `Expenses:FFCC:*` (4xxxxx: 41/43), `Expenses:JAB:*` (8xxxxx: 81/83/85/87) y `Assets:FFCC:*-115xxx` con `categoria3="CUENTAS POR COBRAR"`.

- [x] Task 1: Parametrizar el origen de filas por grupo (AC: 1, 3, 4)
  - [x] [backend/app/services/bql_queries.py:260] `report_rows_via_beancount` hoy hardcodea `_group_pattern(..., "EAG")` [:281]. Agregar `group: str = "EAG"` (default → 0 regresión EAG, AC4) y pasar `group="FondoComun"` desde el endpoint RUT2.
  - [x] Emitir en cada fila el **path completo** `account` (como `balance_sheet_via_beancount`) además de `accountnumber` — así el builder deriva entidad del 2º segmento (FFCC/JAB) de forma robusta, sin depender solo del 1er dígito. Mantener las claves existentes (0 regresión EAG).
  - [x] Test: `group="FondoComun"` trae solo FFCC/JAB, ninguna EAG; default idéntico a hoy.

- [x] Task 2: Constructor del reporte RUT2 — NUEVO módulo (AC: 1, 2, 3)
  - [x] Crear `backend/app/api/v1/reportes/report_builder_rut2.py`. **NO** reusar/extender `build_report` (EAG-específico: `template_order.json`, prefijos `411/413/415/430`, `DAUGHTERS`). Reusar SOLO los helpers de openpyxl (`write`, `month_header`, fórmulas `=SUM`, fills, `MONEY`) — extraerlos a un módulo común SIN cambiar el output de EAG.
  - [x] **Sección A — GASTOS** (solo cuentas de gasto: code 4xxxxx FFCC / 8xxxxx JAB):
    - Nivel 1 FFCC / JAB (por entidad del path o 1er dígito).
    - Nivel 2 = 2 primeros dígitos del code; etiqueta = `laudus_categoria2`.
    - Nivel 3 = hojas itemizadas `nombre · código` (NUNCA por slug/nombre sin código — 31 nombres duplicados, ver Dev Notes).
    - Subtotales por encabezado + Total FFCC + Total JAB + TOTAL GASTOS RUT2 (fórmulas).
    - Marca TC en `871005`/`873005` en el cuerpo (AC2).
  - [x] **Sección B — DISTRIBUCIONES / CUENTAS POR COBRAR** (cuentas `categoria3="CUENTAS POR COBRAR"` del grupo FondoComun):
    - Una fila por cuenta: `nombre · código` | **Saldo inicial** (acumulado a `start-1`, opcional pero recomendado) | **Retiros del período** (Σ débitos en [start,end]) | **Repartos/abonos** (Σ créditos en [start,end]) | **Saldo al cierre** (acumulado a `end`).
    - **El saldo al cierre es CUMULATIVO** (movimientos hasta `end`), NO el neto del período — computarlo aparte (BQL `sum(position) WHERE account ~ ... AND date <= end`, o reutilizar `balance_sheet_via_beancount("FondoComun", date_to=end)` filtrando a estas cuentas). Los retiros/repartos del período sí salen de `report_rows` en el rango.
    - **Separar en dos bloques** (resuelto Valentina): (1) **Familiares** (`Retiros*` + nombres propios), ordenados por |saldo| desc; (2) **Operativas** (`FondoFijo`, `FondosPorRendir`, `DeudoresVarios`, `ControlYLiquidacion` ~0) al final. NO hay flag mecánico "es persona" → discriminar por cuenta: las 4 operativas son un set chico y estable (nombrarlas explícito es aceptable acá; NO es allowlist de personas, es exclusión de las 4 cuentas de sistema).
    - **Netear asientos wash** (+X/−X en la misma cuenta, neto 0 = reclasificaciones internas): mostrar el saldo neto, no el bruto con el ruido.
    - Etiquetar el signo: **"Debe al fondo"** (+) / **"A favor"** (−), resuelto por Valentina (ver Dev Notes §Signo).
    - **Marca de limitación honesta en el cuerpo** (AC3b) + **slots as-if** para inversiones/offshore (secciones/columnas vacías marcadas "pendiente de carga", decisión Ary 2026-07-13).

- [x] Task 3: Endpoint RUT2 (AC: 1, 3, 4)
  - [x] Endpoint nuevo en [router.py] — recomendado `GET /reportes/fondo-comun` — `require_role(["contador","admin"])`, valida `start<=end` (422), llama `report_rows_via_beancount(ledger, start, end, group="FondoComun")` + el saldo cumulativo + el nuevo builder → `StreamingResponse` xlsx. **NO** ramificar el endpoint `/gastos` de EAG (AC4).
  - [x] Filename `reporte_fondo_comun_{start}_{end}.xlsx`.
  - [x] Tests: 200 + xlsx; `start>end` → 422; RBAC (rol `family`/owner sin acceso).

- [x] Task 4: Frontend — selector de libro en ReportesPage (AC: 1, 3)
  - [x] [frontend/src/pages/ReportesPage.tsx]: selector "Libro" = "EAG" (default) / "Fondo Común (FFCC/JAB)". Fondo Común → llama al endpoint nuevo.
  - [x] [frontend/src/services/reportes.ts]: `downloadReporteFondoComun(start, end)` (clon con URL/filename distintos, `timeoutMs` 120s).
  - [x] `cd frontend && npm run typecheck` (`tsc -b`) + `npm run test` verdes; actualizar tests de componente si existen.

- [x] Task 5: Verificación end-to-end + gates (AC: 1-5)
  - [x] Generar el reporte RUT2 real (ej. `2025-01-01`..`2026-06-30`): confirmar Sección A (encabezados 41/43 · 81/83/85/87, itemización, TC marcada) y Sección B (retiros/repartos/saldo por familiar; el saldo de una cuenta grande, ej. `RetirosAag-115021`, debe coincidir con el balance reconciliado de 12.5 a esa fecha).
  - [x] Cross-check: el saldo al cierre de cada cuenta 115xxx = su balance en `balance_sheet_via_beancount("FondoComun", date_to=end)` (misma fuente reconciliada 0 diffs @ 2026-06-30).
  - [x] Gate 0-regresión EAG (AC4): reporte de EAG mismo período **byte-idéntico** pre/post; `report_rows_via_beancount()` sin `group` intacto.
  - [x] Gate read-only (AC5): `git status ledger/` limpio.
  - [x] `bean-check ledger/main.beancount` → exit 0 (picklecache borrado antes).
  - [x] Suite backend verde (re-baseline vs Task 0); frontend `tsc -b` + `vitest` verdes.

### Review Findings

_Code review 3 capas (Blind Hunter / Edge Case Hunter / Acceptance Auditor), 2026-07-13. Auditor: 0 violaciones de AC (AC1–AC5 + AC3b satisfechos). 1 patch, 5 defer, 4 dismiss._

- [x] [Review][Patch] Orden no-determinista de filas empatadas en distribuciones [backend/app/services/bql_queries.py:400] — `rows` se itera desde el `set` `accts` y el `sort` es estable; empates (mismo bucket `operational` + igual `|saldo_cierre|`, ej. varias operativas ~0) quedan en el orden de iteración del set → cambia entre corridas (hash randomization de strings). **RESUELTO 2026-07-13:** desempate por `x["account"]` agregado al `sort`. Tests 19/19 verde.
- [x] [Review][Defer] Hoja de gastos hardcodea `("FFCC","JAB")` [backend/app/api/v1/reportes/report_builder_rut2.py:114] — inconsistente con Distribuciones (genérica). Hoy el `_group_pattern` restringe el universo a FFCC|JAB (no se pierde plata); si el grupo FondoComun creciera, esos gastos desaparecerían de la hoja y del TOTAL sin aviso. — deferred (latente, no gatilla con datos actuales)
- [x] [Review][Defer] Etiqueta `cat2` tomada del primer leaf del prefijo [backend/app/api/v1/reportes/report_builder_rut2.py:121] — verificado que 41/43/81/83/85/87 mapean a una sola `laudus_categoria2`; si un prefijo tuviera cat2 mixta, el encabezado/subtotal la etiquetaría mal (números correctos, etiqueta engañosa). — deferred (latente)
- [x] [Review][Defer] Redondeo por-columna independiente vs invariante mostrado [backend/app/api/v1/reportes/_xlsx.py:89] — inicial/retiros/repartos/cierre se redondean por separado; el invariante `inicial+retiros+repartos==cierre` podría diferir ±1 con datos fraccionarios. Hoy inocuo: todas las CxC son CLP enteros. — deferred (latente)
- [x] [Review][Defer] `code` vacío colapsa en bucket de prefijo en blanco [backend/app/api/v1/reportes/report_builder_rut2.py:119-121] — cuenta de gasto FFCC/JAB sin meta `code` → `prefix2=""` → encabezado `" · (sin categoría)"` mezclando cuentas. No pierde plata (suma igual) pero oculta la condición en vez de exponerla. — deferred (latente)
- [x] [Review][Defer] Posting USD en cuenta CxC desincronizaría saldo vs balance reconciliado [backend/app/services/bql_queries.py:374] — `distribution_rows` suma `float(p.units.number)` de toda moneda; el cross-check de balance es CLP-only. Hoy todas las CxC (incl. `FondosPorRendirUs`) son CLP-only → inocuo. — deferred (latente)

_Dismissed (falsos positivos verificados): (1) anclaje BQL `~` vs `re.match` — ambos usan `(?-i:^(...):(FFCC|JAB):)` delimitado por `:`, no hay leak; (2) `ControlYLiquidacin` "typo" — es el slug real del ledger; (3) `start>end` sin guard en el builder — el router (único caller) devuelve 422; (4) test cubre solo `871005` no `873005` — mismo set/ruta de código, gap de test menor no de comportamiento._

## Dev Notes

### Qué es esta story (y qué NO es)

Construcción de un **reporte nuevo, read-only**, con dos mitades (gastos + distribuciones). Todo el dato ya existe: histórico RUT2 importado (12.4) y reconciliado peso-por-peso vs Laudus (12.5, 0 diffs @ 2026-06-30). El motor de filas (`report_rows_via_beancount`), los grupos (`CONSOLIDATION_GROUPS["FondoComun"]`) y el toolkit xlsx (openpyxl) ya existen. **No** hay escritura al ledger, conciliación ni clasificación manual.

### El motor de EAG es EAG-específico — NO reusar `build_report`

[report_builder.py] está cableado a EAG: `template_order.json`, prefijos `411/413/415/430` [:74-78], `DAUGHTERS`/`LEVEL`/`ALIAS`, exclusividad Hijas-vs-EAG [:186-196]. Nada de eso aplica a RUT2. **Builder nuevo y chico** — protege AC4 (0 regresión). Compartir solo los helpers de openpyxl de bajo nivel (extraídos sin cambiar el comportamiento de EAG).

### Sección A — Gastos: agrupamiento 100% mecánico (verificado 2026-07-12)

2º dígito del código = encabezado; su `laudus_categoria2` da la etiqueta (sin hardcodear nombres):

```
FFCC (Expenses, root 4):        JAB (Expenses, root 8):
  41 → GASTOS GENERALES           81 → MANTENCION CASAS JAB
  43 → GASTOS FIJOS OFICINA       83 → AVIONES
                                  85 → YATES
                                  87 → GASTOS PERSONALES
```

Verificado que son los **únicos** prefijos de gasto en cada libro (no hay 45, 89, etc.). Nivel 1: FFCC=code 4xxxxx, JAB=8xxxxx (o 2º segmento del path). **Nota de Ary:** el FFCC casi no tiene gasto propio más allá de la administración del fondo (41/43); el grueso del gasto es JAB/FGK. Mostrar ambos, pero el peso está en JAB.

### Sección B — Distribuciones / cuentas por cobrar (HALLAZGO FORENSE, no re-derivar)

**Mecanismo confirmado en transacciones reales** ([_bmad-output/planning-artifacts/_forense_retiros_rut2.py] — persistir el script del sondeo junto a los otros `_forense_*`):
- Un **retiro** = el FFCC paga desde su banco por cuenta de una persona → **débito** (+) a su cuenta por cobrar `Assets:FFCC:Retiros<X>-115xxx`. *Verificado: tx real acredita banco `111005` −$X y debita `RetirosAag-115021` +$X.*
- Un **reparto/abono** = **crédito** (−) que baja la deuda.

**Comportamiento por año (datos reales del ledger, en millones CLP):**

| Cuenta | 2021 | 2022 | 2023 | 2024 | 2025 | Saldo 2026 |
|---|---|---|---|---|---|---|
| RetirosAag-115021 | →0 | →0 | ret 159 / rep 2.976 | | | **−4.451** |
| RetirosDag-115027 | →0 | →0 | | | | **−3.375** |
| RetirosEag-115023 | →0 | →0 | | | | **−3.588** |
| RetirosSag-115025 | →0 | →0 | ret 261 / rep 0 | 0 | 0 | **+261** |
| Israel-115041 | →0 | →0 | ret 4.6 | | | **+4.6** |

- **2021 y 2022: el ciclo préstamo→reparto cierra perfecto** (saldo→0 cada año) — el modelo de Ary tal cual.
- **Desde 2023 el ciclo se rompe**: los saldos se acumulan y son grandes.
- **La mayoría quedó en saldo ACREEDOR (negativo)** = repartos acumulados > retiros → *no deben, tienen saldo a favor / reparto sin retirar* (AAG, DAG, EAG, Zeldis, Alazraki, Borzutzky). Solo **SAG (+261M)** e **Israel (+4.6M)** están en deuda neta.
- Los saldos son **fieles a Laudus** (12.5 reconcilió 0 diffs @ 2026-06-30). El reporte NO inventa nada; solo presenta lo que Laudus tiene.

**Implicación de diseño:** el reporte debe mostrar el **saldo con signo** (deuda vs a favor), no asumir saldado anual. Retiros y repartos del período son flujos; el saldo al cierre es cumulativo (todos los movimientos hasta `end`).

**Identificación mecánica de las cuentas** (sin allowlist de personas, respeta §7): `laudus_categoria3 == "CUENTAS POR COBRAR"` bajo el grupo FondoComun. Esto incluye también cuentas operativas (FondoFijo-115003, FondosPorRendir-115005, DeudoresVarios-115019, ControlYLiquidacion-115099) — son de monto chico o rotan a 0; ordenar por |saldo| desc los deja al final y las personas dominan. NO hay flag mecánico "es persona"; mostrarlas todas es lo correcto y auditable (Ary puede pedir separarlas después). Verificado: los retiros de familiares viven en FFCC; confirmar en el dev que JAB no tiene cuentas por cobrar de personas (la sonda no encontró).

### §Signo — RESUELTO por Valentina (2026-07-12)

En beancount los Assets son naturales positivos (débito). Un saldo **débito (+) = la persona debe al fondo** → etiqueta **"Debe al fondo"**; un saldo **crédito (−) = utilidad del fondo ASIGNADA al socio y no retirada** (asiento anual de cierre, sin mover caja — NO es aporte del hijo) → etiqueta **"A favor"**. Mostrar el saldo con su signo natural + la etiqueta en columna clara.

**Veredicto contable de Valentina** (`valentina-cuentas-corriente-socios-ffcc-2026-07-12.md`): estas cuentas `115xxx` (cat3 "CUENTAS POR COBRAR") **NO son por cobrar → son cuenta corriente / patrimonio de socios**, mismo mislabel estructural que TC (pasivo→gasto) e inversiones EAG. Como Equity FFCC = 0, **son el patrimonio de facto del fondo**. El reporte las presenta como estado de cuenta corriente, no como "por cobrar". El quiebre 2023 (dejan de saldar a 0) = **bandera roja de auditoría diferida — NO corregir en el ledger** (requiere cruzar reparto asignado vs acordado + cargar posiciones reales; ver §Scope guard). El reporte solo REPORTA los saldos fieles a Laudus.

### Cálculo — flujos del período vs saldo cumulativo

- **Retiros/repartos del período**: de `report_rows_via_beancount(ledger, start, end, group="FondoComun")` filtrando a las cuentas `CUENTAS POR COBRAR`; `debit` (retiro) / `credit` (reparto) ya vienen split por signo [:303-304].
- **Saldo al cierre (cumulativo)**: NO sale de `report_rows` (que está acotado al rango). Computar con un `sum(position) WHERE account ~ "<pattern FondoComun cuentas por cobrar>" AND date <= end GROUP BY account`, o reutilizar `balance_sheet_via_beancount("FondoComun", date_to=end)` [:131-161] y quedarte con las cuentas por cobrar. **Saldo inicial** (opcional) = mismo cálculo con `date <= start-1`; útil para el estado de cuenta (inicial + retiros − repartos = final).

### Unicidad — key por código, nunca por nombre/slug

[clasificacion-contable-rut2-firmada-2026-07-11.md] §Unicidad: **31 grupos de hojas comparten nombre** bajo el mismo (root, entidad). El sufijo `-{código}` es lo único único. Itemizar y key-ear por código; mostrar `nombre · código`.

### Aislamiento de libros (NFR20)

`report_rows_via_beancount` ya scopea con `_group_pattern` case-sensitive `(?-i:)` (patch 11.1). Pasar `group="FondoComun"` basta. NO usar los `load_account_index` globales last-wins (siguen rotos por code desnudo; ver [12-5 §TRAP #1]). Test: ninguna cuenta EAG entra al reporte RUT2 y viceversa.

### Hechos verificados del código (2026-07-12, no re-derivar)

- **Reporte EAG hoy:** `GET /reportes/gastos` → `report_rows_via_beancount(ledger, start, end)` (grupo EAG hardcodeado [:281]) → `build_report` [report_builder.py:156]. Auth `require_role(["contador","admin"])`.
- **Grupos:** `CONSOLIDATION_GROUPS = {"EAG": {...}, "FondoComun": {FFCC,JAB}}` [:37-40].
- **VALID_ENTITIES** ya incluye FFCC/JAB [dashboard/schemas.py:9] (11.2). Este reporte NO usa el selector de entidad; tiene su propia superficie por libro.
- **Row shape de `report_rows` hoy:** `{date, accountnumber(code), accountName, Categoria1..3, debit, credit}` — falta el path; Task 1 lo agrega.
- **Cuentas de gasto:** `Expenses:FFCC:*` (41/43), `Expenses:JAB:*` (81/83/85/87). Etiqueta = `laudus_categoria2`.
- **Cuentas por cobrar:** `Assets:FFCC:*-115xxx`, `laudus_categoria3="CUENTAS POR COBRAR"` (RetirosAag/Eag/Sag/Dag/Azba, JoseAlazraki, DeniseZeldis, MichelleZeldis, ArielBorzutzky, Israel, OtrosRetirosHijos, + operativas).
- **Balance reconciliado:** `balance_sheet_via_beancount(ledger, "FondoComun"|"FFCC"|"JAB", date_to=...)` ya rutea por grupo/entidad [:131-161].

### Decisiones con default documentado (auto-aprobadas per project-context; documentar desvíos)

1. **Endpoint separado** `GET /reportes/fondo-comun` (no ramificar `/gastos`). Protege AC4.
2. **Builder nuevo** `report_builder_rut2.py` (no parametrizar `build_report`).
3. **Etiqueta de encabezado = `laudus_categoria2`**; distribuciones identificadas por `laudus_categoria3="CUENTAS POR COBRAR"` — todo data-derived, sin allowlist.
4. **Distribuciones: SEPARAR familiares de operativas** (resuelto Valentina) — familiares ordenadas por |saldo|, operativas (FondoFijo/FondosPorRendir/DeudoresVarios/ControlYLiquidacion) en bloque aparte al final; **netear asientos wash**.
5. **Saldo con signo natural** + etiqueta **"Debe al fondo"/"A favor"** (resuelto Valentina); estas cuentas son cuenta corriente de socios, no CxC.
6. **Marca de limitación honesta obligatoria en el cuerpo** (AC3b): balance FFCC incompleto, patrimonio no determinable, caja total no usable, NO afirmar (des)respaldo.
7. **Slots as-if inversiones/offshore** (decisión Ary 2026-07-13): estructurar para acomodar esas posiciones cuando lleguen, sin hard-block hoy.
8. **Solo gastos + distribuciones**; INGRESOS del RUT2 y desglose de TC por cartola fuera de alcance.

### Qué NO hacer (scope guard)

- NO escribir asientos al ledger (gate `git status ledger/` limpio).
- NO tocar `report_builder.py` (EAG) salvo extraer helpers sin cambiar su output (AC4 byte-idéntico).
- NO ramificar el endpoint `/gastos` de EAG.
- NO hardcodear nombres de encabezado, lista de personas ni rango numérico (§7: membresía se deriva del plan / categoria3).
- NO agrupar por slug/nombre sin código (31 colisiones).
- NO desglosar TC por cartola (FR55 = lump estado 1).
- NO reusar los `load_account_index` globales last-wins.
- NO corregir ni anotar los saldos acreedores post-2022 en el ledger — esta story los REPORTA; cualquier corrección contable sería otra story (estilo auditoría de inversiones) y requiere a Valentina.
- NO validar con `tsc --noEmit` — usar `npm run typecheck` (`tsc -b`).

### Inteligencia de stories previas (12.4 / 12.5)

- **Suite:** `PYTHONUTF8=1` obligatorio en Windows. Baseline **861 passed / 1 xfailed** (el único FAILED ocasional `test_lock_stale...` es flaky de concurrencia, pasa aislado).
- **bean-check:** borrar `ledger/.main.beancount.picklecache` antes.
- **Backend Render clona el ledger al startup** — el reporte lee el clon local; refrescar en prod = redeploy o `/sync/trigger`.
- **Commit por story** (acuerdo de retro): commitear al cerrar; en `main` el commit lo confirma Ary.
- **Refresh RUT2 = manual** (decisión retro 12: no hay cron RUT2). Los datos del reporte son tan frescos como el último import manual.

### Project Structure Notes

- Backend: `backend/app/api/v1/reportes/` → `report_builder_rut2.py` (nuevo) + endpoint en `router.py`; query en `backend/app/services/bql_queries.py`.
- Frontend: `frontend/src/pages/ReportesPage.tsx` + `frontend/src/services/reportes.ts`.
- Tests: `backend/tests/test_reportes.py`, `test_report_rows_beancount.py` (patrón de fixtures ledger).
- Script forense a persistir: `_bmad-output/planning-artifacts/_forense_retiros_rut2.py` (sondeo retiros/repartos/saldo por año — evidencia reproducible del hallazgo).

### References

- [Source: _bmad-output/planning-artifacts/epics-segundo-rut.md#Story 13.1] — FR54/FR55, gastos dos niveles, TC en cuerpo, 0 regresión EAG
- [Source: _bmad-output/planning-artifacts/clasificacion-contable-rut2-firmada-2026-07-11.md#5,#7,#D5,#Unicidad] — TC lump (871005/873005), distribuciones §7 (retiros por persona, "no acotar por rango"), key por código
- [Source: backend/app/api/v1/reportes/report_builder.py] — patrón de estilos/fórmulas openpyxl (reusar helpers; NO la estructura EAG)
- [Source: backend/app/api/v1/reportes/router.py:23-42] — endpoint `/gastos` (patrón a clonar)
- [Source: backend/app/services/bql_queries.py:37-40,131-161,260-306] — `CONSOLIDATION_GROUPS`, `balance_sheet_via_beancount` (saldo cumulativo), `report_rows_via_beancount` (parametrizar `group`)
- [Source: ledger/accounts.beancount] — `Expenses:FFCC:*` (41/43), `Expenses:JAB:*` (81/83/85/87), `Assets:FFCC:*-115xxx` (CUENTAS POR COBRAR), TC 871005/873005
- [Source: _bmad-output/implementation-artifacts/12-5-reconciliacion-ancla-validacion.md] — estado del ledger RUT2, baseline, TRAP #1, gotchas Windows/bean-check
- [Source: frontend/src/pages/ReportesPage.tsx / services/reportes.ts] — superficie a extender
- [Source: _bmad-output/project-context.md#Comandos de verificación] — `tsc -b`, pytest PYTHONUTF8=1; cierre de épica = gate de Ary

## Questions — RESUELTAS por Valentina (2026-07-12)

> Detalle en `_bmad-output/planning-artifacts/valentina-cuentas-corriente-socios-ffcc-2026-07-12.md`.

1. **Signo de los saldos `115xxx`:** ✅ RESUELTO. Crédito (−) = **utilidad del fondo asignada al socio, no retirada** → etiqueta **"A favor"**; débito (+) → **"Debe al fondo"**. Mecánicamente correcto. Pero son **cuenta corriente / patrimonio de socios**, no "por cobrar" (mislabel estructural).
2. **Ciclo roto desde 2023:** ✅ RESUELTO como **auditoría diferida** (bandera roja, NO bloquea el reporte, NO corregir en el ledger). Como Equity=0 estas cuentas son el patrimonio de facto. Watchlist Fondo Común: cruzar reparto asignado 2023-25 vs acordado + cargar posiciones reales.
3. **Presentación:** ✅ RESUELTO. **Separar** familiares de operativas (revierte el default "todas juntas") + **netear asientos wash** + **marca de limitación honesta obligatoria** (balance incompleto, patrimonio no determinable). Decisión Ary 2026-07-13: **slots as-if** para inversiones/offshore.

## Dev Agent Record

### Agent Model Used

Amelia (dev-story) — Opus 4.8 (1M context), 2026-07-13.

### Debug Log References

- Baseline pre-dev: **861 passed / 1 xfailed** (== cierre 12.5).
- Suite final: **872 passed / 1 xfailed** (+11 tests, 0 regresiones).
- Frontend: `tsc -b` verde; `vitest` 126 passed / 19 files.
- bean-check `ledger/main.beancount` exit 0; `git status ledger/` limpio (read-only).
- Verificación e2e real (2025-01-01..2026-06-30): saldos == forense (AAG −4.420,5M, EAG
  −3.556,9M, DAG −3.344,5M, SAG +260,9M, Israel +4,6M); cross-check vs balance_sheet
  FondoComun = **0 mismatches**; invariante inicial+retiros+repartos==cierre OK.

### Completion Notes List

- **Task 1** — `report_rows_via_beancount` parametrizada con `group="EAG"` (default, 0
  regresión) + key aditiva `account` (path completo). `build_report` de EAG no la lee →
  output byte-idéntico (AC4). Nueva `distribution_rows_via_beancount` para la Sección B.
- **Neteo wash (desvío documentado):** la Sección B itera asientos directamente (no
  `report_rows`) porque el neteo de asientos wash (+X/−X a la misma cuenta en un asiento;
  **265 en el ledger**) exige agrupar por (asiento, cuenta). El saldo cumulativo sale de
  la misma pasada. Invariante `inicial+retiros+repartos==cierre` verificado.
- **Hallazgo Task 0 (ajuste al spec):** el filtro mecánico `categoria3="CUENTAS POR
  COBRAR"` + grupo FondoComun también trae **JAB `613xxx` (6 operativas)** — el spec
  asumía "JAB no tiene CxC". Todas operativas → bloque operativas. La regla familiares vs
  operativas se implementó excluyendo por **stem de nombre operacional**
  (`_OPERATIONAL_STEMS`, set chico y estable, NO allowlist de personas); todo lo demás en
  el universo CxC del grupo = familiar (default correcto para cuentas de persona nuevas).
- **Layout:** dos hojas — "Gastos FFCC-JAB" (mensual, encabezados 41/43 · 81/83/85/87,
  TC 871005/873005 marcada en el cuerpo, AC2) y "Distribuciones" (columnas inicial/
  retiros/repartos/cierre, familiares vs operativas, marca de limitación honesta AC3b,
  slots as-if inversiones/offshore por decisión Ary 2026-07-13). Toolkit `_xlsx.py`
  reutilizable; EAG NO se migró (garantiza byte-idéntico).
- **Fuera de alcance (confirmado):** INGRESOS RUT2, desglose de TC por cartola, corrección
  contable de los saldos acreedores post-2022 (auditoría diferida — watchlist Valentina).

### File List

- `backend/app/services/bql_queries.py` (mod) — `group` param + key `account` en
  `report_rows_via_beancount`; nueva `distribution_rows_via_beancount` + constantes CxC.
- `backend/app/api/v1/reportes/_xlsx.py` (nuevo) — toolkit openpyxl `ReportSheet` + estilos.
- `backend/app/api/v1/reportes/report_builder_rut2.py` (nuevo) — builder del Fondo Común.
- `backend/app/api/v1/reportes/router.py` (mod) — endpoint `GET /reportes/fondo-comun`.
- `backend/tests/test_report_fondo_comun.py` (nuevo) — 11 tests (distribuciones, builder, endpoint).
- `backend/tests/test_report_rows_beancount.py` (mod) — test del `group` param + key `account`.
- `frontend/src/services/reportes.ts` (mod) — `downloadReporteFondoComun` + helper `downloadXlsx`.
- `frontend/src/pages/ReportesPage.tsx` (mod) — selector "Libro" (EAG / Fondo Común) + texto.

## Change Log

- 2026-07-13 — Story 13.1 implementada: reporte del Fondo Común (RUT2 · FFCC/JAB) con
  hoja de gastos por encabezado + hoja de distribuciones (cuenta corriente de socios).
  Spec actualizado con resoluciones Valentina (Q1/Q2/Q3, marca de limitación) y steer
  Ary (as-if inversiones/offshore). 872 passed/1 xfailed backend, frontend verde,
  read-only, bean-check 0, saldos == forense. Status → review.
