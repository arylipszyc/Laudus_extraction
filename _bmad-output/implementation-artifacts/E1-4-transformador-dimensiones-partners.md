# Story E1.4: Transformador de dimensiones analíticas + partners

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **contadora**,
I want **las 6 dimensiones analíticas y los partners poblados según la tabla de mapeo y la lista cerrada de partners**,
so that **los cortes (socio, propiedad, offshore…) salen nativos y el saldo por socio/persona cuadra sin armar Excel a mano**.

## Contexto (qué construye E1.4 y qué NO)

Quinta story de Epic E1 — el **tercer transformador de la cadena** (`collapse → sincerar → dimensionar`), Python puro, Tier A, SIN Odoo. E1.3 dejó las patas de ingreso sinceradas con metadata auditable (`sinc_*`) y el verificador componible (`run_tier_a(route=..., excluded_je_ids=...)`). **E1.4 agrega el "quién" y el "sobre qué": partners y dimensiones analíticas como METADATA por línea** — no cambia cuentas, no cambia montos, no excluye moves:

1. **Partners (`res.partner`)** — el "quién", 2 mecanismos según winston §5.2: **partición** (socio-dueño sobre 115xxx — el partner ledger debe cuadrar al peso, ES el "Resumen Retiros" que hoy se arma a mano) y **disperso** (deudores, donaciones/clubes, beneficiarios — agrupa, no se le exige cuadrar).
2. **Dimensiones analíticas (6 planes, dispersos)** — propiedad/área/offshore/por-cuenta-de/socio-uso/entidad, estampadas por línea desde las columnas del CSV (nivel cuenta) + reglas por glosa acotadas (alias YAML, sección `personas`). NUNCA se exige que una dimensión sume 100% (AC3).
3. **Reporte de cobertura de glosa (FR10 versión E1.4)** — sin-match contados y listados; el cierre exige **sign-off** (AC5).

**La paridad es doblemente invariante en esta story:** E1.4 no toca `odoo_account` ni `amount` ni el set de moves → `run_tier_a` corre con el MISMO `route`/`excluded_je_ids` que produjo E1.3 y tiene que dar idéntico. El gate NUEVO de E1.4 es la **partición**: Σ(líneas por partner sobre 115xxx) == saldo Laudus de esas cuentas, al peso.

> **Arquitectura aprobada** (winston §5, resumen ejecutivo §0 aprobado 2026-07-24). Detalle técnico auto-aprobado según `project-context.md`. **Precondición de datos CERRADA:** lista de partners (`valentina-lista-partners-2026-07-23.md`, 39 partners / 4 categorías / 6 dudosos).

## Acceptance Criteria

Copiadas del epic (`epics.md` → Story E1.4), formato Given/When/Then:

**AC1 — Partners canónicos, Deutsch separadas, nombre completo**
**Given** la lista de partners (4 categorías),
**When** corre el transformador,
**Then** socios/deudores/donaciones/beneficiarios mapean a `res.partner` canónico; **Jacqueline y Patricia Deutsch son partners SEPARADOS**; el mapeo por glosa **exige nombre completo** (nunca substring "deutsch"/"gloria"/"israel").

**AC2 — Partición socio-dueño cuadra al peso**
**Given** socio-dueño (partición, cuentas 115xxx),
**When** se asigna partner sobre "Cuentas corriente socios",
**Then** el **partner ledger cuadra al peso** con el saldo de las cuentas 115xxx (la única partición que reconcilia); **Israel se resuelve por la cuenta 115041**, no por glosa.

**AC3 — Dimensiones dispersas sin exigencia de 100%**
**Given** las dimensiones dispersas (propiedad/área/offshore/por-cuenta-de/socio-uso),
**When** se asignan vía `analytic_distribution`,
**Then** NO se exige que sumen 100% de ninguna cuenta.

**AC4 — Buckets dudosos como placeholder, nunca fusión a ciegas**
**Given** los buckets dudosos (Deudores Varios, Otros hijos, CIS),
**When** se procesan,
**Then** quedan como placeholder marcado "revisar con contadoras", no se fusionan a ciegas.

**AC5 — Cobertura de glosa con sign-off**
**Given** el reporte de cobertura de glosa (FR10),
**When** una línea no matchea ningún alias,
**Then** queda marcada Y entra al reporte; el AC de cierre exige **sign-off** de los sin-match (contados y revisados, no solo marcados).

## Alcance — qué SÍ y qué NO hace E1.4

**SÍ (deliverables):**
- `pipeline/odoo_migration/dimensionar.py` — tercer transformador: `dimensionar(moves, mapping, aliases) -> DimensionadoResult` (moves con partner+dims estampados como metadata, reporte de cobertura). Función pura, mismo patrón de `sincerar`.
- Tabla de **canonicalización de partners versionada en código**: valor de la columna `partner`/`benef` del CSV → (partner canónico, categoría, flag). El CSV trae **48 valores distintos; la lista cerrada tiene 39** — la diferencia está resuelta pinneada abajo (Dev Notes, "Data real verificada").
- Campos nuevos de metadata en `OdooLineRecord` (patrón `sinc_*` de E1.3, defaults vacíos): partner + regla que decidió + dims + flag.
- **Gate de partición Tier A**: Σ por partner canónico sobre los códigos 115xxx == Σ del mirror para esos códigos, al peso — con los saldos de la lista de Valentina como anchors independientes pinneados en el full-mirror.
- Reglas por glosa SOLO vía alias YAML sección `personas` (nombre completo, word-boundary, `excluir_homonimos` vetan) — Raquel por glosa en gasto, socio-uso, Jhonny.
- Reporte de cobertura FR10 (sin-match con glosa+cuenta+monto, conteos por dimensión/partner) + pins al corte + sign-off.
- README del paquete: sección E1.4 (cadena `collapse → sincerar → dimensionar`, contrato de regresión sin cambios de firma).

**NO (es de otra story / decisión):**
- Crear `res.partner` / `account.analytic.account` REALES en Odoo, `analytic_distribution` json, `partner_id` → **E1.5** (loader). E1.4 emite la metadata que el loader consume; los 6 `account.analytic.plan` contenedores YA existen (E1.1).
- Verificación lado-Odoo del partner ledger + muestreo dirigido (cuenta+partner+dimensión) → **E1.6**.
- Desglose del bucket "Deudores Varios" EAG (2.175M) por glosa en partners nominables → **pregunta a Valentina**, story futura si lo confirma. Hoy = placeholder por entidad (AC4).
- Resolver CIS ↔ C.I. Santiago ↔ C.I. Sefaradí (3 partners separados hasta que contadoras confirmen — lista regla 5).
- Rendiciones P-7 (115001–115007 Personal/Fondo Fijo/Fondos por Rendir): **fuera del scope E1** (inventario §1.4) — solo placeholder verbatim, sin partición, sin desglose.
- D-1 del review E1.3 (residual Latinoamericana) — pendiente Valentina, NO la toca esta story.

## Tasks / Subtasks

- [x] **Task 1 — Canonicalización de partners (AC1, AC4)**
  - [x] `dimensionar.py`: tabla `PARTNER_CANONICO` versionada en código: valor CSV → `(canonico, categoria, flag)`. Categorías: `socio-particion`, `socio-disperso` (columna `socio`: FGK/AAG/EAG/SAG/DAG — entra a la tabla desde ESA columna, no desde `partner`), `deudor`, `rendicion-p7`, `donacion`, `club`, `beneficiario`, `bucket`. Cubre los **48 valores reales de `partner`** + los 5 de `socio` + los 4 de `benef` (test de completitud contra la tabla cargada: ningún valor de `partner`/`socio`/`benef` sin entrada — población cerrada, patrón E1.3).
  - [x] Colapsos de la lista (regla 1 y 4): `"Cta Cte DAG - Autos"` → **DAG**; `"Denise Zeldis - Autos"` → **Denise Zeldis**; `"Donaciones, Regalos"` (FFCC 437055) y `"Donaciones"` (430092/415055) y `"Otras Instituciones"` (878099) → bucket **"Donaciones varias"** con flag revisar; Keren Hayesod / WIZO / Fundación Mar de Chile / Gloria Jiménez colapsan cross-entidad a UN canónico (ya vienen con el mismo string en el CSV — assertearlo, no re-mapear).
  - [x] Dudosos de la lista (6) + CIS: `Israel`, `Otros hijos`, `Deudores Varios`, `Jhonny Guerra`, `CIS`/`C.I. Santiago`/`C.I. Sefaradi` (TRES partners separados), buckets genéricos → flag `revisar con contadoras`. **Jacqueline Deutsch ≠ Patricia Deutsch: dos canónicos, test explícito.**
  - [x] Asignación por CUENTA (fuente primaria): toda línea cuya fila CSV trae `partner` o `benef` no-vacío recibe el partner canónico. `Deudores Varios` = placeholder **por entidad** (`Deudores Varios (EAG)`, `(FFCC)`, `(Jocelyn)`, …— lista cat 2).
  - [x] Asignación por `(entity, code)` pinneada: `(EAG,310045)` y `(EAG,310047)` → **Jhonny Guerra** (un solo partner + revisar; el CSV trae `partner` vacío en esas filas — la lista cat 2 es la autoridad; ¿"hijo" separado? → pregunta Valentina, hoy uno).
- [x] **Task 2 — Partición socio-dueño (AC2)**
  - [x] Los 11 partners de partición (lista cat 1) por cuenta 115xxx FFCC: AAG/EAG/SAG/DAG(+115028)/AZBA/José Alazraki/Denise Zeldis(+115034)/Michelle Zeldis/Ariel Borzutzky/Israel(115041, NUNCA por glosa)/Otros hijos(115039). **FGK NO es partición** (socio-dimensión por prefijo en gastos JAB 873xxx — columna `socio`).
  - [x] **Gate de partición Tier A**: para cada partner de partición, Σ(amount de líneas CLP estampadas con ese partner sobre sus códigos 115xxx) == Σ del MIRROR para esos códigos (expectativa derivada del mirror crudo, sin pasar por el transformador — patrón E1.3). Los códigos con destino distinto en la tabla (115028 → `Cuentas por cobrar`) IGUAL cuadran por partner: la partición se verifica por PARTNER, no por cuenta destino.
  - [x] **Anchors independientes pinneados (full-mirror, corte 2026-07-23)** — los saldos de la lista de Valentina §cat 1: AAG **−4.438.135.788**, EAG **−3.587.647.995**, SAG **+260.889.862**, DAG **−3.362.663.937** (115027+115028), AZBA **−493.043.375**, José Alazraki **−482.345.420**, Denise Zeldis **−485.461.560** (115033+115034), Michelle Zeldis **−494.335.026**, Ariel Borzutzky **−534.603.111**, Israel **+4.639.535**, Otros hijos **0**. Si algún saldo difiere al derivar (lista vs mirror al corte), pinnear lo que DÉ el mirror y documentar la diferencia en Completion Notes (la lista es el cross-check, el mirror manda — mismo criterio E1.2/E1.3).
- [x] **Task 3 — Dimensiones analíticas + personas dispersas (AC3)**
  - [x] **Pin de mecanismo (los 6 planes de E1.1 están CONGELADOS — no inventar un 7º):** los planes existentes son propiedad_objeto / area_centro / offshore_vehiculo / por_cuenta_de / socio_uso / entidad. Las columnas de PERSONAS (`socio`, `benef`) NO van a un plan analítico: van como **partner disperso** (winston §5.2 "personas = partner"; los analíticos no dan saldo y acá agrupan P&L). El plan `socio_uso` queda reservado para el socio-USO por glosa (c).
  - [x] Estampar por línea desde las columnas del CSV (nivel cuenta): `prop` (130 filas) → plan propiedad_objeto; `area` (190) → area_centro; `offshore` (34) → offshore_vehiculo; **`socio` (20 filas: FGK 11 en JAB 873xxx + AAG/EAG/SAG/DAG en FFCC 413xxx impuestos y JAB 877xxx regalos + `(FFCC,411004)` "EAG - Complemento") → partner disperso** (mismo partner canónico que la partición — "no crear duplicado", lista cat 1 nota; categoría `socio-disperso`, NO entra al gate de partición); **`benef` (6) → partner disperso categoría `beneficiario`** (solo P&L, sin posición de balance — winston §5.2; NO hay "plan beneficiario"). Entidad = `line.entity` (ya viaja en la línea — NO duplicar el dato; E1.5 la convierte en analítica).
  - [x] `area` incluye el valor `por-cuenta-de` (8 filas) → ese valor alimenta el plan **por_cuenta_de** (winston §5.1), no area_centro. Separarlo en el estampado.
  - [x] Regla por glosa acotada (SOLO alias `personas` del YAML, nombre completo + word-boundary + homónimos vetan): (a) **Raquel por glosa** en cuentas de gasto SIN `benef` en CSV (lista cat 4: "todo 'raquel' es ella", Salud/Vehículos/Regalos) → partner Raquel Ventura (disperso); (b) **socio-uso por glosa** en retiros de uso (winston §5.1: "Vuelo X Hrs→RetirosDag") → plan socio_uso, solo si el alias resuelve inequívoco. Cualquier duda → sin estampar + reporte (NUNCA fuzzy, NUNCA substring).
  - [x] **Pin `(EAG, 430019)` T/C Raquel Ventura:** el CSV trae `partner`/`benef` vacíos (flag `TC-especial`, mapea a Liabilities:TC) pero la lista cat 4 dice "el beneficiario sigue siendo Raquel" → asignar **partner Raquel Ventura por `(entity, code)`** (paralelo exacto al caso Jhonny: la lista completa lo que el CSV deja vacío). Solo metadata — la cuenta destino no se toca.
  - [x] NO exigir 100%: ningún check de completitud sobre dims dispersas (AC3 explícito). La métrica es visibilidad (reporte), no cobertura total (winston §6·B.4, regla 80/20).
- [x] **Task 4 — Reporte de cobertura + regresión (AC5, invariantes)**
  - [x] `DimensionadoResult.report`: conteos por partner-categoría y por plan; líneas candidatas-a-glosa sin match (con glosa+cuenta+monto, patrón `LineRef` E1.3); pins al corte en el full-mirror (conteos exactos, patrón `test_cobertura_pinneada`).
  - [x] **Sign-off AC5**: el reporte imprime/expone los sin-match contados; Completion Notes registra el conteo y queda el gate humano: Ary/Valentina revisan el listado al cerrar la story (dejar pregunta guardada si hay sorpresas). "Contados y revisados, no solo marcados".
  - [x] `run_tier_a` tras `dimensionar` == verde con los MISMOS `route_sincerado`/`excluded_je_ids` de E1.3 (E1.4 no toca cuentas ni excluye — 0 diffs, golden slice y full-mirror). Test de que `dimensionar` NO altera `odoo_account`/`amount`/`len(moves)` (invariante estructural explícita).
  - [x] Tests de mutación (el gate DEBE poder fallar): partner equivocado en una 115xxx → gate de partición acusa; colapso Autos roto (115028 sin partner DAG) → partición DAG descuadra vs anchor; "Patricia Deutsch" matcheada por substring "deutsch" → test de que NO matchea; saldo pinneado alterado → falla.
  - [x] Suite completa `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q`: baseline **373 passed / 7 skipped** + los nuevos, 0 regresiones. `bean-check` verde (solo lectura).
  - [x] README sección E1.4.

### Review Findings

Code review adversarial 2026-07-25 (3 capas: Blind Hunter / Edge Case Hunter / Acceptance Auditor; 35 hallazgos crudos → 2 decision / 8 patch / 3 defer / 13 descartados tras verificación).

- [x] [Review][Decision] **Menciones tipo `deudor`/`apellido_azba` invisibles para el reporte AC5** — `dimensionar` solo consulta los tipos `beneficiario` y `socio` del YAML; una glosa "abono préstamo Jhonny" (220 ocurrencias de "jhonny") o "Zeldis"/"Alazraki" fuera de las cuentas pinneadas no estampa (correcto) pero TAMPOCO entra a `sin_match` — el sign-off no las ve. El Alcance lista "Jhonny" entre las reglas por glosa, pero Task 1 / Dev Notes 3 mandan pin-only. **RESUELTO (decisión Ary 2026-07-25): anotar el scope como está** — Jhonny/AZBA se cubren por cuenta fija/pin; sus menciones en glosa no se listan. Scope pinneado en el docstring de `dimensionar.py`.
- [x] [Review][Decision] **Bucket "Donaciones varias" ÚNICO contradice la lista regla 3 (placeholder POR ENTIDAD)** — la lista de Valentina dice buckets genéricos por entidad; la story Task 1 pinnea UN bucket (`por_entidad=False`). **RESUELTO (decisión Ary 2026-07-25): dejarlo único + pregunta guardada 6 a Valentina** (agregada abajo).
- [x] [Review][Patch] **`_BENEF_ALIAS_A_CANONICO[name]` revienta con KeyError pelado si el YAML gana un 5º beneficiario** — fail-loud con contexto + tests de completitud YAML↔mapa y del raise [pipeline/odoo_migration/dimensionar.py:334] — aplicado
- [x] [Review][Patch] **`dim_socio_uso` estampa el nombre YAML verbatim sin validar población cerrada** — validado contra `_SOCIO_USO_VALIDOS` (= `SOCIO_CANONICO ∪ {AZBA}`) + test [pipeline/odoo_migration/dimensionar.py:351] — aplicado
- [x] [Review][Patch] **Semántica nueva del veto por spans sin pin para la sección `vehiculos`** — pinneada en `test_veto_por_spans_pinneado_para_vehiculos` (homónimo dentro de alias no veta; suelto sí) [pipeline/odoo_migration/sincerar.py:237] — aplicado
- [x] [Review][Patch] **Los dos `raise ValueError` de `_partner_por_cuenta` (partner/socio desconocido) no tienen test** — tests agregados [pipeline/odoo_migration/dimensionar.py:263] — aplicado
- [x] [Review][Patch] **`load_alias_table` acepta alias/homónimos que normalizan a `""`** — guard fail-loud al cargar + test [pipeline/odoo_migration/sincerar.py:170] — aplicado
- [x] [Review][Patch] **`test_mutacion_partner_equivocado_acusa` sin `else: pytest.fail(...)`** — agregado [pipeline/odoo_migration/tests/test_dimensionado_full_mirror.py:145] — aplicado
- [x] [Review][Patch] **Invariante estructural del full-mirror más débil que la del golden** — agregados `currency` + `laudus_code` [pipeline/odoo_migration/tests/test_dimensionado_full_mirror.py:68] — aplicado
- [x] [Review][Patch] **Docstring de `resolve_alias`: `candidata` puede ser True aunque SÍ resolvió** — semántica aclarada (mirarla solo cuando `nombre` es None) [pipeline/odoo_migration/sincerar.py:212] — aplicado
- [x] [Review][Defer] **`otype` sin población cerrada: un typo (`expenses`/vacío) apaga la regla beneficiario en silencio** [pipeline/odoo_migration/dimensionar.py:329] — deferred: la validación de `otype` ya está diferida a E1.5 (defer E1.2 vigente); los conteos pinneados (796 beneficiario / 35 sin-match) guardan el CSV actual
- [x] [Review][Defer] **Claves duplicadas en el YAML se pisan en silencio (`yaml.safe_load` conserva la última)** [pipeline/odoo_migration/sincerar.py:155] — deferred, pre-existing (comportamiento de `load_alias_table` desde E1.3)
- [x] [Review][Defer] **Fixture session-scoped con estado mutable compartido entre módulos, protegido solo por docstring** [pipeline/odoo_migration/tests/conftest.py:34] — deferred: higiene de tests; los tests de mutación ya trabajan sobre corridas frescas, riesgo = un test futuro que mute en sitio

## Dev Notes

### Decisiones ya tomadas — NO re-litigar

- **Personas = partner; propiedad/área/objeto = analítica** (winston §5, mapa §2). Partición → partner ledger sobre balance; disperso → plan analítico sobre P&L sin exigencia de 100%. Meter una dispersa donde va partición descuadra reportes (SPEC §5.1).
- **Socio-dueño ≠ socio-uso** (winston §5.2): dueño = partición/partner/115xxx/cuadra; uso = disperso/analítica/glosa/no cuadra. No mezclar. EAG-socio (persona) ≠ EAG (compañía/libro).
- **Key `(entity, code)`** en todo; company SIEMPRE derivada de entity (E1.2). **External IDs congelados** (E1.0) — E1.4 no emite xmlids (eso es E1.5).
- **La tabla CSV es la fuente; el generador de Valentina NO se toca.** Los 6 planes analíticos contenedores YA existen (E1.1, XML noupdate). NO fuzzy matching como decisor; alias YAML es data versionada (si falta un alias se agrega AL YAML, no al código).
- **Universo `source: "laudus-erp"`** y cadena de transformadores sobre `OdooMoveRecord`/`OdooLineRecord` (E1.2/E1.3). Metadata nueva = campos con default vacío en el dataclass (patrón `sinc_*`, no romper constructores existentes).

### Data real verificada (2026-07-25, contra el CSV y el código — leer antes de codear)

1. **El CSV trae 48 valores distintos en `partner` (+4 en `benef`); la lista cerrada nombra 39 canónicos.** La diferencia, resuelta pinneada:
   - `Cta Cte DAG - Autos` y `Denise Zeldis - Autos` → colapsan al padre (lista regla 1).
   - `Cuentas Corrientes del Personal`, `Fondo Fijo`, `Fondos por Rendir`, `Fondos por Rendir - US$` (115001–115007) → **rendiciones P-7, fuera de scope E1**: placeholder verbatim, categoría `rendicion-p7`, sin partición.
   - `Inmobiliaria Inv. Pirihueico SPA` (115015), `Grupo Gastronómico S.A.` (115017), `Tierra y Huertos SpA` (115018) → **deudores nominables por cuenta** (EAG, destino `Cuentas por cobrar`); la lista cat 2 no los enumeró → partners reales categoría `deudor` + nota a Valentina (pregunta guardada).
   - `Donaciones` / `Donaciones, Regalos` / `Otras Instituciones` → bucket "Donaciones varias" + revisar (lista regla 3; FFCC 437055 mezcla donaciones+regalos).
   - `CIS`, `C.I. Santiago`, `C.I. Sefaradi` → tres partners separados + revisar (lista regla 5).
2. **115028 (`Cta Cte DAG - Autos`) mapea a `Cuentas por cobrar` en la tabla, NO a `Cuentas corriente socios`** (a diferencia de 115034 Denise-Autos que sí va a socios). E1.4 NO re-rutea (la tabla manda, E1.2); la partición DAG igual cuadra porque se verifica por PARTNER sobre los códigos {115027, 115028}, no por cuenta destino. Anotar en Completion Notes si Valentina quiere homogeneizarlo (cambio de tabla, no de código).
3. **Las filas Jhonny (310045/310047) traen `partner` VACÍO en el CSV** — la asignación es por `(entity, code)` pinneada (lista cat 2). E1.3 ya re-ruteó esas patas a `Assets:EAG:PrestamoJhonnyGuerra`; E1.4 les estampa el partner encima. Grafía canónica **"Jhonny"** (NO "Johnny" — el alias YAML lo exige).
4. **El YAML de alias tiene sección `personas` (15 entradas)**: EAG/AAG/DAG/SAG/AZBA/FGK/RaquelVentura/JacquelineDeutsch/PatriciaDeutsch/GloriaJimenez/Alazraki/Zeldis/… — cargar con `load_alias_table` existente (ya normaliza + respeta `excluir_homonimos`; `resolve_vehiculo` tiene la mecánica de match — generalizarla a sección parametrizable, p.ej. `resolve_alias(glosa, table, section)`, refactor quirúrgico sin duplicar).
5. **Columna `socio` = 20 filas** (FGK 11 en JAB 873xxx; AAG/EAG/SAG/DAG en FFCC 413xxx impuestos + JAB 877xxx regalos; **+ `(FFCC,411004)` "EAG - Complemento"** — no calza en los 3 grupos, contarla) — personas a nivel CUENTA (cluster 4) → partner disperso (Task 3, pin de mecanismo). El socio-USO por glosa es un enriquecimiento aparte y acotado (Task 3c) que sí usa el plan `socio_uso`.
6. **Los saldos de la lista cat 1 son los anchors de partición** (independientes: Valentina los derivó de Laudus). El corte es el mismo del inventario (2026-07-23) → reusar el `CUTOFF`/fixture module-scoped de `test_sinceramiento_full_mirror.py` (o factorizarlo a un conftest — decisión del dev; NO cargar el ledger 2 veces por módulo).

### Cómo encaja con E1.2/E1.3 (el contrato)

- **Input de `dimensionar` = output de `sincerar`** (`SinceramientoResult.moves`). La cadena completa en tests: `collapse(cut, table) → sincerar(moves, table, alias_table) → dimensionar(result.moves, table, alias_table)`.
- `run_tier_a(entries, moves_dimensionados, table, route=route_sincerado(table, aliases), excluded_je_ids=result_sincerar.excluded_je_ids)` — **misma llamada que E1.3** (E1.4 no agrega exclusiones ni cambia ruteo). Si E1.4 la rompe, tocó algo que no debía.
- Guards heredados que te afectan: `collapse` fail-louds en duplicados y moves vacíos; `verify_counts` ahora también acusa identidades duplicadas/vacías del mirror (review E1.3 P-2); `load_alias_table` exige sección `vehiculos` (P-2) — si agregás validación de `personas`, mismo patrón.
- **Learnings del review E1.3 (aplicar de entrada):** (a) chequeos por glosa van con word-boundary SIEMPRE (P-3 pescó `a\s+cta` y `_RE_PRESTAMO` sin boundary); (b) nunca acuñar destinos/valores fuera de una allowlist (P-4); (c) toda tabla-seed del CSV se pinnea en snapshot versionado (P-9, `NATURALEZA_SNAPSHOT` — hacer lo mismo con la de partners); (d) pins con literales derivados una vez, no expectativas re-derivadas del propio transformador (P-10); (e) los tests de mutación no son opcionales.
- **Defers vigentes que NO cierra esta story:** `posting.price` (E1.5), `otype` (E1.5), ParityError diffs programáticos (opcional si tocás la excepción), neteo por-par (W-3: E1.4 NO declara exclusiones nuevas → no lo toca), D-1 Latam (Valentina).

### El fixture golden y los casos de test

El fixture golden (E1.0) está curado para naturalezas, no para partners — las 115xxx **no están** en el golden slice, y **ningún código del slice tiene columnas `prop`/`area`/`partner`/`benef` pobladas en el CSV** (verificado 2026-07-25: los `prop` de JAB son 811xxx Vía Gris, fuera del slice; los 7xxxxx del slice son hijas). NO buscar cobertura golden que no existe. Estrategia de test en dos niveles:
- **Unit (casos sintéticos, sin fixture)**: canonicalización (48+5+4 valores→canónicos, Deutsch separadas, Autos colapsan, CIS×3), reglas por glosa directas (`classify`-style). Sobre el golden: solo la invariante estructural (cuentas/montos/moves intactos post-`dimensionar`) y `run_tier_a` verde con la cadena de 3.
- **Full-mirror**: gate de partición con los 11 anchors pinneados + conteos de cobertura pinneados + `run_tier_a` verde end-to-end de la cadena de 3 transformadores.

### Project Structure Notes

- Código nuevo: `pipeline/odoo_migration/dimensionar.py` (hermano de transform/sincerar/parity). Modificación quirúrgica de `transform.py` (campos metadata con default, patrón E1.3) y opcionalmente `sincerar.py` (generalizar `resolve_vehiculo` → `resolve_alias(section=...)` — sin duplicar la mecánica de match).
- Tests nuevos: `pipeline/odoo_migration/tests/test_dimensionado.py` + `test_dimensionado_full_mirror.py` (o extender el full-mirror existente con la cadena de 3 — decisión del dev; cuidar UNA sola carga del ledger por módulo). Todo Tier A, NADA `@pytest.mark.odoo`.
- README del paquete: sección E1.4.

### Testing Requirements

- **Comando real (NO inventar otro):** `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q` (suite completa) / `… -m pytest pipeline/odoo_migration -q` (iterar). [Source: project-context.md]
- Baseline actual: **373 passed / 7 skipped** (post-review E1.3, commit c64f20b). 0 regresiones.
- `bean-check` del mirror (picklecache borrado antes) — E1.4 solo LEE el ledger.
- Tests de mutación obligatorios (Task 4) — un gate que no puede fallar es `tsc --noEmit`.

### References

- [Source: _bmad-output/planning-artifacts/odoo-migracion/epics.md#Story-E1.4] — ACs.
- [Source: _bmad-output/planning-artifacts/odoo-migracion/valentina-lista-partners-2026-07-23.md] — 39 partners, 4 categorías, saldos 115xxx (anchors), reglas 1–5 para los ACs.
- [Source: _bmad-output/planning-artifacts/odoo-migracion/winston-arquitectura-e1-odoo-2026-07-23.md#5] — 6 planes + partners, partición vs disperso, socio-dueño ≠ socio-uso; [#6·B] — alias/normalización/no-fuzzy/cobertura; [#8] — verify E1.4.
- [Source: _bmad-output/planning-artifacts/odoo-migracion/valentina-tabla-mapeo-odoo-2026-07-23.csv] — columnas `prop/socio/benef/area/offshore/partner` (la fuente del estampado por cuenta).
- [Source: _bmad-output/planning-artifacts/odoo-migracion/valentina-tabla-alias-2026-07-23.yaml] — sección `personas` (15), homónimos, word-boundary.
- [Source: _bmad-output/implementation-artifacts/E1-3-transformador-sinceramiento-naturalezas.md] — patrón de transformador + review findings (learnings a–e) + D-1.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — defers vigentes (qué NO cierra E1.4).
- [Source: pipeline/odoo_migration/{transform,sincerar,parity,mapping}.py] — la cadena existente (post-review, commit c64f20b).

### Preguntas guardadas para Ary / Valentina (no bloquean el dev)

1. **Deudores nominables fuera de la lista:** Pirihueico SPA / Grupo Gastronómico / Tierra y Huertos (115015/17/18) entran como partners reales categoría deudor — ¿confirmás? (La lista cat 2 no los enumeró.)
2. **Jhonny "hijo" (310047):** ¿partner separado del padre o mismo grupo? Hoy = un solo partner + revisar (lista cat 2).
3. **115028 DAG-Autos → `Cuentas por cobrar`** en la tabla (vs 115034 Denise-Autos → socios): ¿homogeneizar? Es cambio de tabla (generador), no de código; la partición cuadra igual.
4. **Sign-off AC5:** al cerrar la story queda el listado de sin-match para revisión de ustedes (conteo pinneado en Completion Notes).
5. **Desglose Deudores Varios EAG (2.175M)** por glosa en partners reales — story futura si la querés.
6. **Bucket "Donaciones varias" ÚNICO vs lista regla 3 (por entidad)** — (review 2026-07-25) la lista dice buckets genéricos POR ENTIDAD, la story pinneó UN bucket cross-entidad (FFCC 437055 + EAG 430092/415055 + JAB 878099, flag revisar). Decisión Ary: dejarlo único; ¿lo quieres separado por entidad como Deudores Varios? Es cambio de tabla canónica + pins, no de mecánica.

## Dev Agent Record

### Agent Model Used

Claude Fable 5 (claude-fable-5) — dev-story workflow, 2026-07-25.

### Implementation Plan

- `dimensionar.py` = tercer transformador, mismo patrón de `sincerar` (función pura, `dataclasses.replace` por línea/move — P-6). Metadata nueva en `OdooLineRecord`: `partner`/`partner_categoria`/`partner_regla`/`partner_flag` + `dim_propiedad`/`dim_area`/`dim_offshore`/`dim_por_cuenta_de`/`dim_socio_uso` (defaults vacíos, patrón `sinc_*`).
- Precedencia de partner: columna `partner` (tabla `PARTNER_CANONICO`, 48 valores) → pin `(entity, code)` (`PARTNER_PIN`: Jhonny ×2, Raquel 430019) → columna `socio` (`SOCIO_CANONICO`, disperso) → glosa (solo `personas` del YAML).
- Las columnas de dims viajan en `MappingRow` (6 campos nuevos + entran a `REQUIRED_COLUMNS` — sin ellas el estampado quedaría vacío en silencio, mismo modo de falla que el header renombrado).
- `resolve_vehiculo` generalizado a `resolve_alias(glosa, table, section, tipo=)` en `sincerar.py` sin duplicar la mecánica; `resolve_vehiculo` queda como wrapper (API E1.3 intacta).
- Gate `verify_particion(entries, moves)`: esperado derivado del MIRROR crudo (sin pasar por el transformador), actual = Σ patas `socio-particion` por (partner, moneda). Fixture full-mirror factorizado a `conftest.full_mirror_chain` (session-scoped, UNA carga del ledger compartida con E1.3).

### Debug Log References

- RED→GREEN 1: el homónimo `deutsch` vetaba también al nombre completo `jacqueline deutsch` (el excluir matchea DENTRO del alias). Fix: veto por spans — el homónimo veta solo si aparece FUERA de un match de alias; el nombre completo gana sobre su propio substring. Semántica E1.3 (`leo hernandez por leo limited` → veta) preservada, 52/52 verde.
- RED→GREEN 2: `KeyError: 'AZBA'` en socio-uso — el alias tipo `socio` incluye AZBA, que no existe en la columna `socio` del CSV. Fix: `dim_socio_uso = name` (los nombres de entrada tipo socio del YAML ya son el canónico).
- RED→GREEN 3: mutación "colapso Autos roto" no acusaba — hallazgo real: **115028 netea a 0.00 al corte (9 patas que se cancelan) y 115034 no tiene movimientos**; romper el colapso completo es invisible para un gate de sumas. El test rompe UNA pata individual no-cero (la señal real).
- `test_bom_de_excel_se_tolera` actualizado: su CSV sintético no tenía las 6 columnas nuevas de `REQUIRED_COLUMNS` (consecuencia directa del guard).

### Completion Notes List

- **AC2 cumplido al peso, cross-check independiente perfecto:** los 11 saldos de partición derivados del mirror al corte 2026-07-23 dieron **EXACTOS contra la lista de Valentina (cat 1), 0 diferencias** — no hubo que ejercer la instrucción "pinnear lo que dé el mirror y documentar". `Otros hijos` (115039): saldo 0 y sin movimientos al corte.
- **AC5 — sign-off pendiente de Ary/Valentina (gate humano):** 67 patas mencionadas-sin-resolver, contadas y listadas en `report.sin_match` (35 beneficiario + 32 socio-uso, pinneadas en `test_cobertura_pinneada`). Son casos genuinamente ambiguos: glosas multi-socio ("El Mercurio - Aviso defuncion SAG de AAG", "Eluchans - EAG/SAG"), homónimos vetados ("Gloria Amollao", "deutsch" bare). Además 264 patas con partner placeholder/dudoso en `report.revisar`.
- Cobertura estampada al corte: partners = 5.657 partición + 1.254 socio-disperso + 796 beneficiario + 769 rendición-P7 + 169 bucket + 84 donación + 65 deudor + 30 club; planes = 12.654 propiedad + 10.092 área + 2.725 por-cuenta-de + 2.428 socio-uso + 233 offshore.
- **Decisión (documentada en código):** `dim_por_cuenta_de` estampa el marcador verbatim `por-cuenta-de` (8 filas Control y Liquidación) — el "por cuenta de QUIÉN" por línea no es derivable a nivel cuenta; refinar es de una story futura con Valentina.
- **Decisión:** la regla por glosa de beneficiarios matchea contra las 4 entradas tipo `beneficiario` del YAML (no solo Raquel): las otras 3 exigen nombre completo + homónimo veta, mismo mecanismo conservador; Raquel es el caso con volumen ("todo raquel es ella").
- **Decisión:** scope de la regla beneficiario = `otype == "expense"` de la CUENTA (la columna `odoo` del CSV no usa prefijo `Expenses:` — los gastos son `Gasto:…`, `Regalos`, …).
- Hallazgo para Valentina (suma a la pregunta 3 de la story): 115028/115034 ("Autos") no aportan saldo al corte — la partición DAG/Denise cuadra hoy incluso sin el colapso; el colapso importa para historia futura post-corte.
- Invariantes verificadas: `run_tier_a` verde tras `dimensionar` con los MISMOS `route_sincerado`/`excluded_je_ids` de E1.3 (golden + full-mirror); invariante estructural explícita (cuentas/montos/moves intactos); función pura (input no mutado).
- Suite completa: **405 passed / 7 skipped** (baseline 373/7 + 32 tests nuevos, 0 regresiones). `bean-check` verde (picklecache borrado antes). Las preguntas guardadas de la story (deudores nominables, Jhonny hijo, 115028, desglose Deudores Varios EAG) siguen abiertas — ninguna bloqueó.

### File List

- `pipeline/odoo_migration/dimensionar.py` (nuevo — transformador + `verify_particion` + tablas canónicas)
- `pipeline/odoo_migration/transform.py` (mod — 9 campos de metadata E1.4 en `OdooLineRecord`, defaults vacíos)
- `pipeline/odoo_migration/mapping.py` (mod — 6 columnas de dims en `MappingRow` + `REQUIRED_COLUMNS`)
- `pipeline/odoo_migration/sincerar.py` (mod — `resolve_alias` generalizado con veto por spans, `AliasEntry.tipo`, guard sección `personas`)
- `pipeline/odoo_migration/README.md` (mod — sección E1.4)
- `pipeline/odoo_migration/tests/conftest.py` (mod — `full_mirror_chain` session-scoped compartido)
- `pipeline/odoo_migration/tests/test_dimensionado.py` (nuevo — unit + golden, snapshot P-9 de 89 filas)
- `pipeline/odoo_migration/tests/test_dimensionado_full_mirror.py` (nuevo — gate partición + anchors + cobertura + mutación)
- `pipeline/odoo_migration/tests/test_sinceramiento_full_mirror.py` (mod — consume el fixture compartido)
- `pipeline/odoo_migration/tests/test_mapping_table.py` (mod — header completo en el CSV sintético del test de BOM)

## Change Log

- 2026-07-25 — E1.4 implementada completa (Tasks 1–4): transformador `dimensionar` (partners canónicos + 5 planes dispersos + reglas por glosa acotadas), gate de partición al peso (11 anchors exactos vs lista Valentina), reporte de cobertura FR10 con 67 sin-match listados para sign-off, 32 tests nuevos (405/7 total, 0 regresiones). Status → review.
- 2026-07-25 — Code review adversarial (3 capas): AC1–AC5 verificados contra spec/lista/arquitectura, anchors dígito a dígito. 2 decisiones Ary (scope reporte AC5 anotado; Donaciones varias único + pregunta 6 a Valentina), 10 patches aplicados (fail-louds con contexto, poblaciones cerradas socio_uso/beneficiario-YAML, veto de vehículos pinneado, guard alias vacío, invariante full-mirror reforzada), 3 defers a deferred-work.md, 13 descartados verificados. Suite 412/7 (+7 tests), bean-check verde. Conteos pinneados intactos (67 sin-match / 264 revisar / anchors). Sign-off AC5 de Ary/Valentina sigue pendiente como gate humano. Status → done.
