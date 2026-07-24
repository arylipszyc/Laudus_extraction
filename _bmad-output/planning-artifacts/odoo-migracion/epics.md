---
stepsCompleted: ["step-01-validate-prerequisites", "step-02-design-epics", "step-03-create-stories", "step-04-final-validation"]
inputDocuments:
  - "valentina-product-brief-migracion-odoo-2026-07-23.md"
  - "valentina-spec-estructura-odoo-2026-07-23.md"
  - "valentina-mapa-normalizacion-odoo-2026-07-23.md"
  - "valentina-tabla-mapeo-resumen-2026-07-23.md"
  - "valentina-tabla-mapeo-odoo-2026-07-23.csv"
  - "valentina-tabla-mapeo-generador-2026-07-23.py"
  - "winston-arquitectura-e1-odoo-2026-07-23.md"
  - "valentina-tabla-alias-2026-07-23.yaml"
---

# Migración Laudus → Odoo - Epic Breakdown

## Overview

Este documento desglosa la **Fase 1** de la migración de la contabilidad familiar de Laudus a Odoo
(**Epic E1** — espejo corregido y estructurado) en stories implementables. Los requerimientos se derivan
del product brief y el SPEC de Valentina (que hacen de PRD para este track) y de la arquitectura de Winston.

**Alcance de este desglose: SOLO Epic E1.** Las Fases 2 (reportería operativa + conciliación TC) y 3
(valuación de inversiones, IAS 21) son epics posteriores (E2/E3), listados abajo pero **no desglosados aquí**.

## Requirements Inventory

### Functional Requirements

FR1: Cargar toda la historia Laudus (2021→hoy) en Odoo para las 2 entidades (EAG+hijas Jocelyn/Jeannette/Johanna/Jael; RUT2 = FFCC+JAB), preservando cada asiento.
FR2: Construir el plan de cuentas Odoo "Laudus puro" (sin `l10n_cl`), colapsando las 569 cuentas Laudus → ~336 cuentas Odoo según la tabla de mapeo.
FR3: Aplicar el sinceramiento determinístico por naturaleza: sacar del ingreso los ~46B de traspasos/retiros/aportes mal ubicados → activos de origen (provisionales) o gasto (Molco), dejando el ingreso operativo real (~7B).
FR4a: Crear las cuentas de activo de ORIGEN provisionales (Tecnión, Nuevo Ciclo, MBI, JB…) que reciben los retiros sincerados. Quedan negativas/provisionales (se valúan en Fase 3). Son destino del sinceramiento → dentro del espejo (E1).
FR4b: [MOVIDO A Epic E1B] Crear cuentas de activo de PATRIMONIO (yate/avión/casas) a costo, con participación por socio, contra `Equity:Apertura`. Sin código Laudus → fuera del gate de paridad.
FR5: Estampar en cada `account.move.line` los campos `x_laudus_account_code`, `x_laudus_je_id`, `x_laudus_entity` (trazabilidad al origen y llave de paridad).
FR6: Poblar las dimensiones analíticas (propiedad/objeto, área/centro, offshore/vehículo, por-cuenta-de, socio-uso, entidad) y los partners (socio-dueño partición, deudores/préstamos, donaciones/clubes, beneficiarios) según la tabla de mapeo.
FR7: Resolver las glosas inconsistentes con tabla de alias + normalización (§6·B); toda línea sin match queda en su lugar + marcada "sin clasificar", nunca descartada en silencio.
FR8: Verificar la **paridad de ORIGEN** al peso: `Σ(líneas Odoo por x_laudus_account_code, por moneda) == saldo cuenta Laudus`; 0 diffs en los 569 códigos × moneda, ambas compañías, toda la historia. **NECESARIA pero NO suficiente** (ver FR12).
FR9: [MOVIDO A Epic E1B] Producir el reporte de patrimonio v1: activos (inversiones, yate, avión, casas) al balance a costo, con participación por socio.
FR10: Emitir en cada corrida el reporte de cobertura de glosa (líneas no-matcheadas + histograma por-glosa de las cuentas MIXTO) como insumo del loop de convergencia. La glosa sin-match no basta con marcarla: **se cuenta, se revisa y se firma (sign-off)**.
FR11: Idempotencia: re-correr el loader hace upsert vía external IDs determinísticos (`acc_<cía>_<code>`, `mv_<cía>_<je_id>`, `aml_<cía>_<je_id>_<n>`), sin duplicar. **Probada**: correr 2× → estado idéntico; correr / borrar mitad / re-correr → converge.
FR12: Verificar la **paridad de DESTINO y la clasificación** (2º gate, de la mesa redonda — necesario porque FR8 es invariante a errores de clasificación): (a) Σ por cuenta Odoo destino == Σ de sus códigos origen mapeados; (b) conteo de líneas y asientos preservado (no fusiones/particiones silenciosas); (c) el sinceramiento aterrizó donde debía — el ingreso bajó ~46B, los activos de origen subieron ese monto, Molco recibió lo suyo como gasto; (d) muestreo dirigido (N mayores + N aleatorios) revisado a mano contra Laudus: cuenta + partner + dimensión; (e) washes excluidos por criterio semántico (no solo monto-opuesto) + log auditable con conteo esperado.

### NonFunctional Requirements

NFR1: **Determinismo** — mismo input, mismo output; nada a mano; cada re-clasificación lleva metadata (`sinceramiento`, `origen_provisional`) auditable y reversible.
NFR2: **Paridad al peso (0 diffs)** es el gate de aceptación, misma disciplina del proyecto (cf. RUT2 story 12.5: 0 diffs / 237 cuentas).
NFR3: **Separación transformador / loader** — el transformador es Python puro testeable con `pytest` SIN Odoo levantado; solo el loader toca Odoo. El 90% de la lógica se testea sin infra.
NFR4: **Performance** — el verificador agrupa ~100k+ líneas de 5 años; `x_laudus_account_code` indexado (query más caliente del sistema).
NFR5: **Costo** — cero licencia (Odoo Community); corre en el VPS Hetzner ya provisto para el spike. Sin costo recurrente nuevo.
NFR6: **Conservador** — en Fase 1 el resultado subestima la ganancia (los retiros bajan activos aún no valuados), nunca la sobreestima.

### Additional Requirements

- **Stack (pineado del spike):** Odoo 18 Community + Postgres 16 en Docker (VPS Hetzner del runbook); OCA `account-financial-reporting` 18.0 para reportes.
- **Módulo Odoo propio `x_laudus_migration`** (versionado en git, no Studio): campos custom (FR5), 6 planes analíticos seed, diarios, opcional acción de paridad.
- **2 `res.company`:** EAG (RUT1, +hijas) y RUT2 (FFCC+JAB); entidad interna = dimensión, no compañía. Plan de cuentas por compañía.
- **Compañías creadas sin localización fiscal** (no instalar `l10n_cl`); si un módulo exige CoA, `l10n_generic_coa` con cuentas archivadas.
- **Loader vía `odoo shell` / XML-RPC** (no import CSV por UI) con external IDs idempotentes.
- **El transformador EXTIENDE el generador existente** (`valentina-tabla-mapeo-generador-2026-07-23.py`) — no se reescriben las reglas.
- **Multi-moneda:** líneas USD con `currency_id`+`amount_currency`; paridad verificada por moneda. IAS 21/revalúo = Fase 3.
- **Consolidación no nativa en Community** → se resuelve en capa de reporte (dimensión Entidad + reportería existente). No bloquea Fase 1.
- **Scaffold (story E1.0, bloqueante):** venv + harness pytest (`PYTHONUTF8=1`), `docker-compose` del Odoo para tests del loader, **fixture golden** (slice pinneado del espejo, una entidad, pocos meses, **con caso USD obligatorio** + casos-borde de sinceramiento: traspaso/retiro/aporte/ambiguo), y el helper de external IDs como función testeada.
- **Dos tiers de verificación:** Tier A = paridad-transformador (Python puro vs Beancount, golden slice) corre en CI en cada push = **el gate real**; Tier B = full load + query Odoo, gate de release en contenedor, NO por-commit (lección `tsc --noEmit`: el gate tiene que ser el comando real).
- **Verificador continuo, no terminal:** la paridad es invariante al colapso/sinceramiento → se corre como regresión **después de cada transformador** (nace en E1.2), no solo al final.
- **Patrimonio (yate/avión/casas)** = **Epic E1B propio**, con gate reproducible propio (Σ costo×participación, Equity cuadra), fuera del gate de paridad de E1. **Sacado de E1 para que el gate quede inmaculado** (decisión Ary, mesa redonda 2026-07-23).
- **Blockers de datos antes de escribir ACs (Valentina):** (1) cerrar el **inventario de naturalezas** (barrido de aportes-disfrazados tipo Sade + P-7 rendiciones) → precondición de E1.3; (2) cerrar la **lista de instituciones/partners** (donaciones/deudores) → precondición de E1.4. JB/AZBA/valuación NO bloquean el espejo.

### UX Design Requirements

N/A — E1 es un pipeline de datos backend (transformador + loader + verificador) + configuración de Odoo. La UI la aporta Odoo nativo (Community + OCA). No hay UX spec para este epic.

### FR Coverage Map

FR1: Epic E1 — Carga de toda la historia Laudus (2 entidades) en Odoo.
FR2: Epic E1 — Plan Laudus puro + colapso 569→336.
FR3: Epic E1 — Sinceramiento determinístico por naturaleza.
FR4a: Epic E1 — Cuentas de activo de origen (destino del sinceramiento).
FR4b: **Epic E1B** — Cuentas de activo de patrimonio (yate/avión/casas).
FR5: Epic E1 — Campos custom de trazabilidad/paridad en la línea.
FR6: Epic E1 — Dimensiones analíticas + partners.
FR7: Epic E1 — Tabla de alias para glosas + fallback a revisión.
FR8: Epic E1 — Paridad de ORIGEN al peso (gate 0 diffs, necesaria-no-suficiente).
FR9: **Epic E1B** — Reporte de patrimonio v1.
FR10: Epic E1 — Reporte de cobertura de glosa + sign-off de sin-match.
FR11: Epic E1 — Idempotencia del loader probada (upsert por external ID).
FR12: Epic E1 — Paridad de DESTINO + clasificación (2º gate).

(FR1–FR3, FR4a, FR5–FR8, FR10–FR12 = Epic E1, el espejo. FR4b + FR9 = Epic E1B, patrimonio.
E2/E3 tendrán su propia extracción de FRs cuando se desglosen.)

## Epic List

### Epic E1: Espejo Laudus corregido y reconciliado en Odoo (Fase 1a)
Cargar toda la historia de Laudus (2021→hoy, EAG+hijas y RUT2=FFCC/JAB) en Odoo 18 Community — colapsada a un
plan Laudus-puro, con el P&L sincerado (los ~46B de traspasos/retiros/aportes salen del ingreso a activos de
origen o gasto), las dimensiones analíticas y partners poblados. Entregable: **el espejo fiel de Laudus,
reestructurado pero reconciliado al peso**, que las contadoras pueden evaluar.
**FRs covered:** FR1, FR2, FR3, FR4a, FR5, FR6, FR7, FR8, FR10, FR11, FR12.
**Sello del epic:** un único criterio de verdad = la paridad al peso por código origen (gate 0 diffs) +
el 2º gate de destino/clasificación (FR12). Todo lo que entra es reconciliación, no valuación.
**Nota de estructura (revisada en mesa redonda 2026-07-23):** un solo epic con stories ordenadas, PERO:
(a) se agrega **E1.0** (scaffold + fixture golden con caso USD + helper de external IDs) como story-0 bloqueante;
(b) el **verificador nace en E1.2 y corre continuo** (regresión tras cada transformador), no es un hito terminal;
(c) el **patrimonio salió del epic** (→ E1B) para que el gate quede inmaculado;
(d) **E1.3 (sinceramiento)** es el transformador de mayor riesgo contable → doble cobertura + ACs de destino (FR12);
(e) **precondiciones de datos**: cerrar el inventario de naturalezas antes de E1.3 y la lista de instituciones antes de E1.4.

---

### Epic E1B: Patrimonio v1 a costo (Fase 1b) — hermano de E1, NO desglosado aquí todavía
Poner en el balance los activos hoy invisibles (yate Keiki Kai, avión, casas) a **costo**, con **participación
por socio** (⅓, sin doble-conteo), contra `Equity:Apertura`, y producir el **reporte de patrimonio v1**.
**FRs covered:** FR4b, FR9.
**Por qué es epic aparte (decisión Ary):** estos activos NO tienen código Laudus → el gate de paridad no los
puede validar (no hay contra qué reconciliar). Su verdad es una *valuación a costo*, no una reconciliación, y
arrastra la pregunta abierta AZBA (P-6: yate a costo vs CxC de socios). Mantenerlo fuera de E1 deja el gate del
espejo 100% limpio. Tiene **gate propio reproducible** (Σ costo×participación == esperado; Equity cuadra).
Sigue siendo Fase 1 conceptualmente (la "zanahoria temprana" del brief) y puede desglosarse apenas cierre E1.

---

### Epic E2: Reportería operativa (Fase 2) — NO desglosado aquí
Conciliación de tarjetas de crédito (reusar la máquina de Epic 6) + dashboards/reportes (gastos, cashflow,
patrimonio) sobre la base cargada en E1. **Fuera de alcance de este desglose.**

### Epic E3: Análisis y valuación de inversiones (Fase 3) — NO desglosado aquí
Valuación de orígenes (Leo/Tauro/Sade/JB) contra la posición del custodio; reconocer ganancia/pérdida no
registrada (IAS 21); patrimonio a valor de mercado. **Fuera de alcance de este desglose.**

---

## Epic E1: Espejo Laudus corregido y reconciliado en Odoo

**Goal:** cargar toda la historia de Laudus (2021→hoy, EAG+hijas y RUT2=FFCC/JAB) en Odoo 18 Community, colapsada
a un plan Laudus-puro, con el P&L sincerado y las dimensiones/partners poblados — reconciliada al peso contra
Laudus por un doble gate (origen + destino/clasificación). **Precondiciones de datos cerradas** (2026-07-23):
inventario de naturalezas (`valentina-inventario-naturalezas-2026-07-23.md`, naturalezas 0/A–H) y lista de
partners (`valentina-lista-partners-2026-07-23.md`, 39 partners / 4 categorías).

**Secuencia:** E1.0 (scaffold) → E1.1 (módulo Odoo) → E1.2 (colapso + verificador) → E1.3 (sinceramiento) →
E1.4 (dims+partners) → E1.5 (loader) → E1.6 (verificación lado-Odoo). El verificador nace en E1.2 y corre como
regresión tras cada transformador.

### Story E1.0: Scaffold del pipeline de migración + fixture golden

As a equipo de desarrollo del family office,
I want un scaffold testeable (harness pytest + Odoo en Docker + fixture golden con caso USD + helper de external IDs),
So that toda story posterior se construye y verifica sin re-armar infra y sin descubrir bugs de moneda recién en el full load.

**Acceptance Criteria:**

**Given** el repo del proyecto,
**When** corro `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest <ruta-pipeline-migración>`,
**Then** el harness del pipeline de migración corre en verde y queda integrado al comando de verificación del proyecto (no un comando inventado).

**Given** el espejo Beancount,
**When** se construye el fixture golden,
**Then** es un slice pinneado (1 entidad, pocos meses) que incluye **obligatoriamente** ≥1 asiento USD (con `currency_id`+`amount_currency`) y ≥1 caso-borde de cada naturaleza de sinceramiento (traspaso, retiro, aporte, wash apertura/cierre, ambiguo).

**Given** el helper de external IDs,
**When** se le pasa `(compañía, code)` / `(compañía, je_id)` / `(je_id, n)`,
**Then** devuelve determinísticamente `acc_<cía>_<code>` / `mv_<cía>_<jeid>` / `aml_<cía>_<jeid>_<n>`, cubierto por test unitario.

**Given** el `docker-compose` del spike,
**When** se levanta para los tests del loader,
**Then** Odoo 18 Community + Postgres 16 responde y el módulo `x_laudus_migration` se puede instalar.

### Story E1.1: Módulo Odoo x_laudus_migration + 2 compañías sin l10n_cl

As a family office,
I want un módulo Odoo propio con los campos custom, planes analíticos, diarios y las 2 compañías creadas sin plan chileno,
So that la estructura receptora existe con trazabilidad al origen y sin el árbol del SII contaminando el plan.

**Acceptance Criteria:**

**Given** una instancia Odoo 18 Community limpia,
**When** se instala el módulo `x_laudus_migration`,
**Then** instala sin error y declara en `account.move.line` los campos `x_laudus_account_code`, `x_laudus_je_id`, `x_laudus_entity` (los tres **indexados**), `x_laudus_group` en `account.account` y `x_laudus_je_id` en `account.move`.

**Given** el módulo instalado,
**When** se ejecuta su seed,
**Then** crea los 6 planes analíticos (propiedad/objeto, área/centro, offshore/vehículo, por-cuenta-de, socio-uso, entidad) y un diario por compañía.

**Given** la creación de compañías,
**When** se crean `EAG` (RUT1) y `RUT2` (FFCC+JAB),
**Then** ninguna tiene `l10n_cl` instalado; si algún módulo exige un CoA para operar, se usa `l10n_generic_coa` con sus cuentas **archivadas**.

**Given** el campo `x_laudus_account_code`,
**When** se inspecciona el esquema de la base,
**Then** tiene índice de base de datos (es la query más caliente del verificador).

### Story E1.2: Transformador de colapso del plan + verificador de paridad-origen (Tier A)

As a contadora,
I want el plan Laudus colapsado a Odoo (569→336) con cada línea estampada con su código origen, y el verificador de paridad naciendo en esta story,
So that el plan queda limpio y puedo medir la paridad al peso desde el primer transformador, no recién al final tras un load lento.

**Acceptance Criteria:**

**Given** el espejo Beancount + la tabla de mapeo,
**When** corre el transformador de colapso,
**Then** cada cuenta Laudus mapea a su cuenta Odoo destino según la tabla y **cada línea lleva `x_laudus_account_code` = código origen** (aunque N códigos colapsen a 1 cuenta).

**Given** el output del transformador,
**When** corre el verificador **Tier A** (Python puro contra `beancount.loader`, SIN Odoo),
**Then** `Σ(líneas por x_laudus_account_code, por moneda) == saldo Laudus` con **0 diffs** sobre el golden slice.

**Given** el verificador Tier A,
**When** se agrega cualquier transformador posterior (E1.3, E1.4),
**Then** corre como **test de regresión reusable** tras cada uno (no es un hito único de E1.6).

**Given** el colapso a nivel destino (FR12a/b),
**When** se verifica,
**Then** `Σ por cuenta Odoo destino == Σ de sus códigos origen mapeados`, y el **conteo de líneas y asientos se preserva** (ninguna fusión/partición silenciosa).

### Story E1.3: Transformador de sinceramiento (naturalezas 0/A–H) + gate de destino

> **Precondición (CERRADA 2026-07-23):** inventario de naturalezas — `valentina-inventario-naturalezas-2026-07-23.md`.

As a contadora,
I want la regla determinística que reclasifica cada pata de ingreso según su naturaleza (tabla-madre 0/A–H) y verifica que aterrizó en el destino correcto,
So that el P&L queda sincerado (los ~46B salen del ingreso) y sé que cada peso fue al lugar que corresponde, no solo que no se perdió.

**Acceptance Criteria:**

**Given** la tabla-madre de naturalezas (0/A–H, cerrada en el inventario),
**When** corre el sinceramiento,
**Then** cada pata de ingreso matchea **exactamente una** naturaleza por (código, glosa) y se rutea a su destino (queda-ingreso / activo-origen / activo-aporte Sade / disposición / gasto-Molco / contra-gasto / mixto-por-glosa / H devolución-préstamo).

**Given** los washes de apertura/cierre,
**When** se excluyen,
**Then** se identifican por criterio **semántico** (cuenta+fecha de corte, no solo monto-opuesto), con **log auditable** de cada par excluido y conteo esperado; si excluye más de lo esperado → falla con alarma. (Caso de test: Latinoamericana ±423,6M que netea a 0.)

**Given** el gate de destino (FR12c),
**When** termina el sinceramiento,
**Then** el ingreso total bajó **exactamente la cifra esperada del inventario de naturalezas** (el monto exacto, NO el redondeo "~46B" — el test assertea el número que produce el inventario, no una aproximación), los activos de origen subieron **exactamente ese monto por vehículo**, y Molco recibió su financiamiento como gasto — cada aserción contra la expectativa del inventario.

**Given** la paridad-origen,
**When** corre el verificador Tier A tras el sinceramiento,
**Then** sigue en **0 diffs** (invariante: el código origen se preserva aunque cambie la cuenta destino).

**Given** una pata sin match, o el +32M "dividendo" dudoso de Nuevo Ciclo (H),
**When** no matchea con confianza,
**Then** queda en Income + marcada "sin clasificar" / "revisar con contadoras" (nunca descartada) y aparece en el reporte de cobertura.

### Story E1.4: Transformador de dimensiones analíticas + partners

> **Precondición (CERRADA 2026-07-23):** lista de partners — `valentina-lista-partners-2026-07-23.md` (39 partners / 4 categorías).

As a contadora,
I want las 6 dimensiones analíticas y los partners poblados según la tabla de mapeo y la lista cerrada de partners,
So that los cortes (socio, propiedad, offshore…) salen nativos y el saldo por socio/persona cuadra sin armar Excel a mano.

**Acceptance Criteria:**

**Given** la lista de partners (4 categorías),
**When** corre el transformador,
**Then** socios/deudores/donaciones/beneficiarios mapean a `res.partner` canónico; **Jacqueline y Patricia Deutsch son partners SEPARADOS**; el mapeo por glosa **exige nombre completo** (nunca substring "deutsch"/"gloria"/"israel").

**Given** socio-dueño (partición, cuentas 115xxx),
**When** se asigna partner sobre "Cuentas corriente socios",
**Then** el **partner ledger cuadra al peso** con el saldo de las cuentas 115xxx (la única partición que reconcilia); **Israel se resuelve por la cuenta 115041**, no por glosa.

**Given** las dimensiones dispersas (propiedad/área/offshore/por-cuenta-de/socio-uso),
**When** se asignan vía `analytic_distribution`,
**Then** NO se exige que sumen 100% de ninguna cuenta.

**Given** los buckets dudosos (Deudores Varios, Otros hijos, CIS),
**When** se procesan,
**Then** quedan como placeholder marcado "revisar con contadoras", no se fusionan a ciegas.

**Given** el reporte de cobertura de glosa (FR10),
**When** una línea no matchea ningún alias,
**Then** queda marcada Y entra al reporte; el AC de cierre exige **sign-off** de los sin-match (contados y revisados, no solo marcados).

### Story E1.5: Loader idempotente (full history) hacia Odoo

As a family office,
I want cargar toda la historia a Odoo vía loader con external IDs, probadamente idempotente y sin doble-carga de apertura,
So that Odoo tiene la historia completa y re-correr el loader nunca duplica ni infla el historial.

**Acceptance Criteria:**

**Given** el output de los transformadores,
**When** corre el loader (`odoo shell` / XML-RPC),
**Then** crea cuentas/asientos/líneas con **external IDs determinísticos** y postea los asientos, ambas compañías.

**Given** la idempotencia (FR11),
**When** se corre el loader 2× sobre Odoo limpio,
**Then** el estado es **idéntico** (mismo N de asientos y saldos, 0 duplicados); y el caso de recuperación: correr / borrar la mitad / re-correr → **converge** al estado completo. (Probado sobre el golden slice, no sobre 5 años.)

**Given** la apertura 2021,
**When** se carga,
**Then** **no hay doble-conteo de apertura** (AC explícito — ya causó ~727M fantasma una vez).

**Given** multi-moneda,
**When** se cargan líneas USD,
**Then** llevan `currency_id`+`amount_currency` y el asiento CLP+USD del golden slice cuadra por moneda.

### Story E1.6: Verificación lado-Odoo (gate de release)

As a contadora,
I want el verificador que corre contra Odoo post-carga (paridad origen + destino + clasificación + muestreo dirigido), como gate de release,
So that antes de dar E1 por cerrado tengo la prueba al peso Y la prueba de que la clasificación no está podrida por debajo.

**Acceptance Criteria:**

**Given** la carga completa en Odoo,
**When** corre el verificador **Tier B** (query a `account.move.line`),
**Then** `Σ por x_laudus_account_code, por moneda == saldo Laudus` con **0 diffs** en los 569 códigos, ambas compañías, toda la historia (FR8).

**Given** el gate de destino (FR12),
**When** corre,
**Then** valida Σ por cuenta destino, conteo de líneas/asientos, y el resultado del sinceramiento (ingreso −46B, activos de origen +ese monto).

**Given** el muestreo dirigido (FR12d),
**When** se seleccionan los **20 asientos de mayor monto + 20 aleatorios con seed fijo** (N pineado por determinismo, NFR1; misma selección en cada corrida),
**Then** se revisan a mano contra Laudus (cuenta + partner + dimensión) y se firma el resultado.

**Given** los dos tiers de verificación,
**When** se define dónde vive el gate,
**Then** Tier A (Python puro) corre **por-push en CI**; Tier B (Odoo, lento) corre como **gate de release en el contenedor**, no por-commit (lección `tsc --noEmit`: el gate tiene que ser el comando real, no un no-op).
