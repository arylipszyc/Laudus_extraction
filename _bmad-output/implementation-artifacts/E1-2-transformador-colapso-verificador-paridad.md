# Story E1.2: Transformador de colapso del plan + verificador de paridad-origen (Tier A)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **contadora**,
I want **el plan Laudus colapsado a Odoo (569→336) con cada línea estampada con su código origen, y el verificador de paridad naciendo en esta story**,
so that **el plan queda limpio y puedo medir la paridad al peso desde el primer transformador, no recién al final tras un load lento**.

## Contexto (qué construye E1.2 y qué NO)

Tercera story de Epic E1. E1.0 dejó el scaffold (`pipeline/odoo_migration/`: harness pytest, fixture golden, `external_ids.py` congelado). E1.1 dejó la estructura receptora en Odoo (módulo `x_laudus_migration`, compañías, diarios). **E1.2 construye el primer transformador real (colapso del plan) y el verificador de paridad Tier A** — Python puro, SIN Odoo:

1. **Acceso a la tabla de mapeo** — la tabla de Valentina (CSV, 569 filas) como fuente del colapso, cargada y validada (snapshot del plan).
2. **Transformador de colapso** — lee el espejo Beancount y emite registros neutrales (moves/líneas estilo Odoo) donde cada línea lleva su cuenta Odoo destino según la tabla **y** el código Laudus origen estampado (`x_laudus_account_code`).
3. **Verificador de paridad-origen Tier A** — `Σ(líneas por código origen, por moneda) == saldo Laudus` con 0 diffs, contra `beancount.loader` directo. **Nace acá y se reusa como regresión tras cada transformador posterior** (E1.3, E1.4) — no es un hito terminal de E1.6.
4. **Gate de destino (FR12a/b)** — Σ por cuenta Odoo destino == Σ de sus códigos origen mapeados; conteo de líneas y asientos preservado (ninguna fusión/partición silenciosa).

**Nada de Odoo levantado en esta story**: todo es Tier A (por-commit). El Tier B lado-Odoo es E1.6.

> **Arquitectura aprobada:** resumen ejecutivo de `winston-arquitectura-e1-odoo-2026-07-23.md` aprobado por Ary el 2026-07-24. Detalle técnico auto-aprobado según `project-context.md`.

## Acceptance Criteria

Copiadas del epic (`epics.md` → Story E1.2), en formato Given/When/Then:

**AC1 — Colapso según la tabla + código origen en cada línea**
**Given** el espejo Beancount + la tabla de mapeo,
**When** corre el transformador de colapso,
**Then** cada cuenta Laudus mapea a su cuenta Odoo destino según la tabla y **cada línea lleva `x_laudus_account_code` = código origen** (aunque N códigos colapsen a 1 cuenta).

**AC2 — Verificador Tier A: paridad-origen 0 diffs sobre el golden slice**
**Given** el output del transformador,
**When** corre el verificador **Tier A** (Python puro contra `beancount.loader`, SIN Odoo),
**Then** `Σ(líneas por x_laudus_account_code, por moneda) == saldo Laudus` con **0 diffs** sobre el golden slice.

**AC3 — El verificador es regresión reusable, no hito único**
**Given** el verificador Tier A,
**When** se agrega cualquier transformador posterior (E1.3, E1.4),
**Then** corre como **test de regresión reusable** tras cada uno (no es un hito único de E1.6).

**AC4 — Gate de destino: Σ por cuenta destino + conteos preservados (FR12a/b)**
**Given** el colapso a nivel destino,
**When** se verifica,
**Then** `Σ por cuenta Odoo destino == Σ de sus códigos origen mapeados`, y el **conteo de líneas y asientos se preserva** (ninguna fusión/partición silenciosa).

Además, del §8 de la arquitectura (verify de E1.2): **snapshot test del plan** — 569 códigos Laudus → 336 cuentas Odoo; toda cuenta Laudus tiene destino.

## Alcance — qué SÍ y qué NO hace E1.2

**SÍ (deliverables):**
- `pipeline/odoo_migration/mapping.py` — carga y valida la tabla de mapeo CSV (key `(entity, code)`), snapshot del plan.
- `pipeline/odoo_migration/transform.py` — transformador de colapso: entries del mirror → moves/líneas neutrales con destino Odoo + código origen + entidad + je_id estampados.
- `pipeline/odoo_migration/parity.py` — verificador Tier A: paridad-origen por `(company, code, moneda)`, gate de destino, conteos. **API reusable** (E1.3/E1.4 la llaman tras su transformador).
- Tests Tier A de todo lo anterior sobre el golden slice + **tests de mutación** (el verificador DEBE detectar un peso perdido — un gate que no puede fallar no es gate).
- README del paquete: sección E1.2 + cómo E1.3/E1.4 reusan el verificador.

**NO (es de otra story):**
- Sinceramiento por naturaleza (reglas transaccionales por cuenta+glosa, washes, tabla de alias) → **E1.3**. El colapso de E1.2 mapea **cuentas** según la columna `odoo` de la tabla tal cual (incluidos los destinos que la tabla ya redirige a nivel cuenta, p.ej. Sade→`Assets:FFCC:InversionesSade`); NO aplica reglas por-glosa ni excluye washes.
- Dimensiones analíticas / partners (columnas `prop/socio/benef/area/offshore/partner` de la tabla) → **E1.4**. E1.2 no las estampa.
- Carga hacia Odoo / XML-RPC / odoo shell → **E1.5**.
- Verificación lado-Odoo (query a `account_move_line`) + muestreo dirigido → **E1.6**.
- Asignación de `code` numérico Odoo a las cuentas colapsadas → decisión de E1.5 (el loader); la paridad no depende de eso.

## Tasks / Subtasks

- [x] **Task 1 — Acceso a la tabla de mapeo + snapshot del plan (AC1, snapshot §8)**
  - [x] `mapping.py`: carga el CSV (path parametrizable, default el de planning-artifacts). Key = **`(entity, code)`** — los códigos se repiten entre entidades (111005 EAG/FFCC; 710005 Jeannette/JAB, cubierto por test).
  - [x] Validaciones fail-loud al cargar: `(entity, code)` único; `(company, code)` único (protege `acc_<company>_<code>`); toda fila con code tiene destino. Company derivada SIEMPRE de la entity (las 2 aperturas Equity sintéticas 900001/900002 traen company vacía → RUT2).
  - [x] Fila sin code (`Expenses:EAG:Suspense`) excluida del universo y **pinneada en test** (exactamente 1).
  - [x] `test_mapping_table.py`: snapshot pinneado con los números REALES de la tabla versionada — **568 filas con code + 1 sin code = 569**; **335 destinos únicos globales** (el "336" del resumen contaba el 'Gasto:' de la fila sin code); **361 cuentas `(company, odoo)`** (el plan operativo por compañía). 12 tests (17 tras el code review).
- [x] **Task 2 — Transformador de colapso (AC1)**
  - [x] `transform.py`: `collapse(entries, mapping)` → `OdooMoveRecord`/`OdooLineRecord` neutrales; filtro de universo `source: "laudus-erp"`; code desde meta del open, entity desde el nombre de cuenta, company vía `EAG_ENTITIES`, `je_id` = meta `id` (NO `je_num`).
  - [x] Fail-loud: cuenta sin `code`, mapeo faltante, asiento sin `id`, asiento que cruza compañías, pata sin monto — todos con contexto, cubiertos por test.
  - [x] Multi-moneda: la línea conserva `units.currency` + monto firmado (USD 100 / CLP −80.000 verificados).
  - [x] `test_transform_collapse.py`: 11 tests (15 tras el code review) — colapso 5 códigos RetirosTecnin → 1 destino conservando cada código origen; retiro id 1237 con 5 entidades y company única EAG; destino redirigido por tabla (Sade→activo) tal cual; filtro de universo; fail-louds.
- [x] **Task 3 — Verificador de paridad Tier A (AC2, AC4)**
  - [x] `parity.py`: `verify_origin_parity` por `(company, code, moneda)` con el MISMO filtro de universo, todas las monedas; `verify_destination` (FR12a) computa el lado esperado desde el MIRROR ruteado por la tabla (cruza contra la fuente, no contra sí mismo); `verify_counts` (FR12b) con `expected_excluded_moves/lines` listos para E1.3.
  - [x] `test_parity_tier_a.py`: 14 tests (16 tras el code review) — 0 diffs origen/destino/conteos sobre el golden slice; anclas al peso (310013 = −1.022.700.000; USD = +100); wash netea a 0; **6 tests de mutación** (monto alterado → 1 diff exacto; línea borrada; código cambiado → los 2 códigos acusan; entidad cambiada → las 2 compañías acusan — la key incompleta no puede colapsar EAG con FFCC).
- [x] **Task 4 — Verificador como regresión reusable (AC3)**
  - [x] `run_tier_a(entries, moves, mapping, *, expected_excluded_*)` corre origen+destino+conteos y levanta `ParityError` con detalle. Test del caso E1.3: excluir el par wash completo declarándolo → verde; excluir UNA pata → descuadra.
  - [x] README sección E1.2 con el contrato: "todo transformador nuevo termina con `run_tier_a` en verde sobre el golden slice" + snippet + comando real.
- [x] **Task 5 — Regresión y guardrails del proyecto**
  - [x] Suite completa `pytest backend/tests pipeline -q`: **321 passed, 7 skipped, 0 failed** (baseline 284+7 → +37 tests nuevos de E1.2, 0 regresiones; el fallo pre-existente de rut2 ya estaba arreglado en a8c0561).
  - [x] `bean-check ledger/main.beancount` (picklecache borrado antes): **exit 0** — E1.2 solo lee el ledger.

### Review Findings

<!-- Code review 2026-07-25 — 3 capas (Blind Hunter / Edge Case Hunter / Acceptance Auditor). Auditor: 4/4 ACs PASS + snapshot PASS (números 568/335/361 re-derivados independientemente; suites re-corridas: 64/5 y 321/7). 26 hallazgos brutos → 7 patch, 4 defer, 3 dismiss, 0 decision-needed. -->

- [x] [Review][Patch] Loader de la tabla no es fail-loud ante CSV regenerado: BOM/header renombrado → `raw.get("code")=None` en TODAS las filas → tabla VACÍA sin excepción (unicidad pasa vacuamente); además acepta N filas sin code en silencio (la promesa "un segundo caso falla fuerte" vive solo en el pin del test). Fix: `utf-8-sig`, validar headers esperados, fail si `rows` vacío, fail si >1 fila sin code. [pipeline/odoo_migration/mapping.py:86-116] (blind+edge)
- [x] [Review][Patch] `company_for_entity` clasifica cualquier entidad desconocida como RUT2 en silencio (mundo cerrado solo del lado EAG) y la columna `company` del CSV se ignora siempre — si el generador de Valentina y `EAG_ENTITIES` divergen (nueva hija EAG), la company queda mal y la paridad NO lo ve (ambos lados usan la misma función). Fix: cross-validar la columna `company` no-vacía del CSV contra la derivada al cargar. [pipeline/odoo_migration/mapping.py:42-46,105] (blind+edge)
- [x] [Review][Patch] `collapse` no detecta `(company, je_id)` duplicado (doble-import de un mes en el mirror): Tier A queda verde (ambos lados cuentan doble) pero los dos moves comparten `mv_<company>_<je_id>` y el upsert de E1.5 pisa uno en silencio. Fix: set de `(company, je_id)` vistos + fail-loud. [pipeline/odoo_migration/transform.py:92-143] (blind+edge)
- [x] [Review][Patch] Transacción del universo sin postings produce move con `company==""` que pasa todos los gates y revienta lejos (external_ids E1.5). Fix: fail-loud si el move queda sin líneas. [pipeline/odoo_migration/transform.py:104-142] (blind+edge)
- [x] [Review][Patch] Simetría fail-loud en parity: `laudus_balances`/`verify_destination` acceden `posting.units.currency` sin el guard que `transform` sí tiene, y `verify_destination` pasa `code=None` a `mapping.get` → error que despista ("code='None' no está en la tabla" en vez de "cuenta sin meta code"). [pipeline/odoo_migration/parity.py:89,137-140] (blind+edge+auditor)
- [x] [Review][Patch] Tests: `zip(txn.postings, move.lines)` sin `strict=True` verifica solo el prefijo si un move pierde líneas de la cola (el conteo global puede compensarse entre moves); y 2 fail-louds de Task 2 declarados "cubiertos por test" NO tienen test (asiento cruza-compañías, pata sin monto). [pipeline/odoo_migration/tests/test_transform_collapse.py] (blind+auditor)
- [x] [Review][Patch] Registro: conteos por archivo imprecisos en Task 1/Task 3 — `test_mapping_table.py` tiene 12 tests (dice 11) y `test_parity_tier_a.py` tiene 14 (dice 15); el total 37 sí cuadra. [este archivo] (auditor)
- [x] [Review][Defer] Exclusiones de `verify_counts`/`run_tier_a` se declaran por CONTEO, no por identidad: excluir el par equivocado que también netea a 0 daría verde. → **E1.3** (la story que implementa washes con log auditable; ahí la API sube a set de `je_id` excluidos con su consumidor real). [pipeline/odoo_migration/parity.py:163-185] (blind+edge)
- [x] [Review][Defer] `OdooLineRecord` no conserva `posting.price` (la pata `100 USD @ 800 CLP` pierde el contravalor que `amount_currency` necesita). → **E1.5** (la story lo asigna ahí explícitamente; los records se regeneran in-process desde el mirror — no hay pérdida real de información entre stories). [pipeline/odoo_migration/transform.py:131-141] (edge)
- [x] [Review][Defer] `ParityError` no expone los diffs como atributos programáticos (mensaje trunca a 5 reprs). → cuando el verificador corra a escala (E1.3/E1.6). [pipeline/odoo_migration/parity.py:202-218] (blind)
- [x] [Review][Defer] Consistencia `(company, odoo_account) → otype` no validada al cargar (hoy 0 conflictos en la tabla versionada). → **E1.5** (quien crea el chart y decide tipos). [pipeline/odoo_migration/mapping.py] (edge)

## Dev Notes

### Datos verificados HOY contra los artefactos reales (no re-derivar, ya está chequeado)

- La tabla CSV tiene **569 filas con code + 1 fila sin code** (`Expenses:EAG:Suspense` — la única cuenta del ledger sin meta `code`; es la cuenta interna de cuarentena del proyecto, no viene de Laudus).
- **`(entity, code)` es único** y **`(company, code)` es único** en las 569 (verificado con awk sobre el CSV). Los códigos sueltos NO son únicos: 111005 = banco BCI en EAG **y** banco BCI en FFCC; 710005 = banco Jeannette (EAG) **y** cuenta JAB (RUT2). → **la key de mapeo es `(entity, code)`**; la paridad puede agrupar por `(company, code)` sin ambigüedad.
- Las cuentas del golden slice están TODAS en la tabla con su entidad correcta (verificado fila por fila, incluidos los 5 `RetirosTecnin` y el par wash FFCC 310009/211005).
- La tabla ya redirige a nivel CUENTA algunos destinos de sinceramiento (Sade 310011 FFCC → `Assets:FFCC:InversionesSade` tipo asset; JAB 710005 → `Expenses:MolcoFinanciamiento`). **E1.2 los mapea tal cual dice la columna `odoo`** — la paridad es invariante (el código origen viaja en la línea). Las reglas POR TRANSACCIÓN (glosa, washes) son E1.3.

### La fuente del colapso: la tabla CSV, no re-derivar reglas

El AC1 dice "el espejo Beancount + **la tabla de mapeo**". El generador de Valentina (`valentina-tabla-mapeo-generador-2026-07-23.py`) es quien produce la tabla; sus reglas NO se reescriben ni se re-derivan en el transformador — el transformador **consume la tabla generada** (CSV versionado). Si una regla cambia, Valentina regenera la tabla (idempotente) y el transformador la lee. Eso ES "extender el generador" a nivel pipeline: generador = reglas→tabla; E1.2 = tabla+mirror→registros Odoo. [Source: epics.md §Additional Requirements; valentina-tabla-mapeo-resumen §Cómo se usa]

**Gotcha del generador (NO arreglar acá, solo saber):** su `out` interno apunta al path pre-reorg (`_bmad-output/planning-artifacts/valentina-tabla-mapeo-odoo-2026-07-23.csv`, sin `odoo-migracion/`). Si alguien lo re-corre, el CSV nuevo cae en el path viejo. Es artefacto de Valentina; no tocarlo en esta story.

### El número "336" del snapshot: pinnear lo que DÉ, con criterio explícito

El resumen dice "569→336 cuentas Odoo (−41%)" contando `odoo` únicos GLOBALES (así lo imprime el generador: `Counter(r["odoo"])` sin company). Pero el plan real de Odoo es **por compañía** (arquitectura §3: chart no compartido) → el conteo operativo es `(company, odoo)` únicos, que puede dar distinto de 336. El snapshot test debe **pinnear ambos números reales** (el global, que documenta la reducción 569→N vs el resumen; y el por-compañía, que es el plan que E1.5 creará) con un comentario de qué mide cada uno. Si el global no da exactamente 336, anotar el valor real en Completion Notes — el 336 del resumen es del run de Valentina, la verdad es lo que dé la tabla versionada.

### Filtro del universo Laudus: `source == "laudus-erp"`

`ledger/main.beancount` incluye TAMBIÉN asientos manuales del proyecto (conciliación TC, categorizaciones → tocan p.ej. `Expenses:EAG:Suspense`). La migración es el espejo de **Laudus**: el transformador procesa solo transacciones con meta `source: "laudus-erp"` (todas las del fixture lo llevan). Ese filtro es parte del contrato y se documenta en el docstring. Nota: el lado-Laudus del verificador usa el MISMO filtro (si no, la paridad compararía universos distintos).

### Convención de signo y multi-moneda (para que el diff dé 0 exacto)

- Beancount guarda el número **firmado** (`units.number`: activo/gasto +, ingreso/pasivo/equity −). La línea transformada conserva ese firmado; en Odoo será `debit - credit` (E1.5). Σ firmado por código == saldo Laudus, exacto. [Source: winston §6]
- La paridad corre **por moneda**: CLP contra CLP, USD contra USD, nunca mezclar ni convertir. La línea USD del slice (100 USD @ 800 CLP) suma como +100 USD bajo su código; el precio CLP es dato para E1.5 (`amount_currency`), no para la paridad Tier A.
- Usar `Decimal` end-to-end (beancount ya lo da); nunca `float`.

### Diseño de las estructuras de salida (neutral, sin Odoo)

Registros Python puros (dataclasses) — NO dicts anónimos, NO objetos Odoo. Sugerencia mínima: `OdooMoveRecord(company, je_id, date, narration, lines)` y `OdooLineRecord(n, odoo_account, laudus_code, entity, currency, amount, desc)`. Los nombres de campo que E1.5 estampará en Odoo ya están congelados (E1.1: `x_laudus_account_code`, `x_laudus_je_id`, `x_laudus_entity`); acá basta que el dato viaje — el naming exacto del dataclass es decisión del dev. Los external IDs se pueden derivar con `external_ids.py` (helper ya congelado, story E1.0) pero no son necesarios hasta E1.5 — opcional incluirlos.

### El verificador nace REUSABLE (AC3) — el porqué

La paridad-origen es **invariante** al colapso Y al sinceramiento (el código origen viaja en la línea pase lo que pase con la cuenta destino) → el mismo verificador corre tras E1.3 y E1.4 como regresión, sin cambios. Por eso: (a) API por funciones que reciben `(entries, lines)` — no un script acoplado al colapso; (b) `verify_counts` ya acepta exclusiones esperadas (E1.3 excluirá pares wash con log auditable — el conteo DEBE poder descontarlas explícitamente, nunca en silencio). [Source: epics.md nota (b) del epic; winston §6 caso washes]

### Tests de mutación: el gate tiene que poder fallar

Disciplina anti-`tsc --noEmit` del proyecto: junto al test "0 diffs", tests que corrompen el output (monto alterado, línea borrada, code cambiado) y asserten que el verificador **detecta** cada corrupción. Sin esto, un verificador con un bug de agrupación (p.ej. key incompleta que colapsa EAG con FFCC en el mismo 111005) daría verde vacío — y ese caso exacto (código repetido entre entidades) existe en la data real.

### Insumos existentes que E1.2 reusa (NO reescribe)

- `pipeline/odoo_migration/tests/fixtures/golden_slice.beancount` (E1.0) — el fixture de TODOS los tests de esta story. No modificarlo (su guardrail `test_fixture_golden.py` se pone rojo).
- `pipeline/odoo_migration/external_ids.py` (E1.0) — convención congelada; si el transformador emite xmlids, usar esto, jamás re-implementar.
- `pipeline/odoo_migration/tests/conftest.py` (E1.0) — marker `odoo` Tier B. **E1.2 no agrega tests Tier B** (todo es Python puro).
- `valentina-tabla-mapeo-odoo-2026-07-23.csv` — la tabla (fuente del colapso). Solo lectura.
- Patrón fail-loud con `ValueError` contextual: seguir el estilo de `external_ids.py`.

### Project Structure Notes

- Código nuevo: `pipeline/odoo_migration/mapping.py`, `transform.py`, `parity.py` (hermanos de `external_ids.py`).
- Tests nuevos: `pipeline/odoo_migration/tests/test_mapping_table.py`, `test_transform_collapse.py`, `test_parity_tier_a.py` (co-locados, patrón E1.0).
- README del paquete: sección E1.2.
- Todo queda descubierto por el comando real (`pytest backend/tests pipeline`) sin tocar comandos ni hooks.

### Testing Requirements

- **Comando de verificación (fuente de verdad, NO inventar otro):** `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q`. Para iterar rápido: `… -m pytest pipeline/odoo_migration -q`. [Source: project-context.md]
- Todos los tests de E1.2 son **Tier A** (sin Docker/Odoo). No marcar nada `@pytest.mark.odoo`.
- `bean-check` del mirror: `venv/Scripts/python.exe -m beancount.scripts.check ledger/main.beancount` (borrar `.picklecache` antes) — guardrail de que E1.2 no tocó el ledger.
- 0 regresiones vs baseline (284 passed / 7 skipped + 1 fallo pre-existente conocido documentado en E1.0).

### References

- [Source: _bmad-output/planning-artifacts/odoo-migracion/epics.md#Story-E1.2] — ACs originales + nota (b) "el verificador nace en E1.2 y corre continuo".
- [Source: _bmad-output/planning-artifacts/odoo-migracion/winston-arquitectura-e1-odoo-2026-07-23.md#6] — mecanismo de paridad (3 pasos, signo, por-moneda, caso washes).
- [Source: winston-arquitectura-e1-odoo-2026-07-23.md#4] — código origen en la línea vs cuenta colapsada (el punto que hace cuadrar todo).
- [Source: winston-arquitectura-e1-odoo-2026-07-23.md#8] — verify E1.2: "569→336; toda cuenta tiene destino; snapshot test del plan".
- [Source: valentina-mapa-normalizacion-odoo-2026-07-23.md#5] — la paridad se preserva agrupando por código.
- [Source: valentina-tabla-mapeo-resumen-2026-07-23.md] — qué es la tabla, flags, cómo la usa E1.
- [Source: valentina-tabla-mapeo-generador-2026-07-23.py] — criterio company/EAG_ENT + cómo se leyó la metadata (referencia, no dependencia).
- [Source: pipeline/odoo_migration/external_ids.py] — convención congelada + patrón fail-loud.
- [Source: _bmad-output/implementation-artifacts/E1-0-scaffold-pipeline-migracion.md / E1-1-…md] — learnings previos (fixture curado, je_id = meta `id`, baseline de la suite).

### Preguntas guardadas para el dev / Ary (no bloquean)

1. **¿El transformador corre también sobre el mirror completo en un test?** Scope pinneado: el gate de E1.2 es el golden slice (AC2). Un smoke full-mirror Tier A es tentador pero puede ser lento y es exactamente lo que E1.6 formaliza — no agregarlo salvo que salga gratis (<5s).
2. **Naming de los dataclasses de salida** — decisión del dev; lo que importa es el dato (code/entity/je_id/moneda/monto firmado por línea).
3. **El "336"** — si el conteo real de `odoo` únicos de la tabla versionada no da 336 exacto, pinnear el real y anotarlo (el resumen de Valentina manda como intención, la tabla versionada como verdad).

## Dev Agent Record

### Agent Model Used

claude-fable-5 (dev-story)

### Debug Log References

- Tier A del paquete: `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest pipeline/odoo_migration -q` → **64 passed, 5 skipped** (0.19s; los 5 skipped son Tier B opt-in de E1.0/E1.1).
- Suite completa: `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q` → **321 passed, 7 skipped** (2:05). 0 regresiones.
- bean-check del mirror: exit 0 (picklecache borrado antes).

### Completion Notes List

- **Snapshot del plan — números reales pinneados (difieren del resumen, documentado):** la tabla versionada tiene **569 filas = 568 con código Laudus + 1 sin código** (`Expenses:EAG:Suspense`, cuenta interna del proyecto). Destinos únicos globales = **335** (el "336" del resumen de Valentina contaba también el destino `Gasto:` de la fila sin code). El plan operativo por compañía (charts no compartidos, winston §3) = **361 cuentas `(company, odoo)`**. La tabla versionada manda como verdad; el resumen como intención.
- **Company derivada SIEMPRE de la entity** (regla única `EAG_ENTITIES`, la del generador): la columna `company` del CSV viene vacía en las 2 aperturas Equity sintéticas (900001 FFCC / 900002 JAB) → derivan RUT2. Aplica igual en mapping, transform y parity (la company de una línea sale de su `entity`, no del move — así una entidad mal estampada descuadra en vez de camuflarse).
- **La fuente del colapso es la tabla CSV** (el generador de Valentina NO se toca ni se re-derivan sus reglas — regla del epic "extender, no reescribir", resuelto a nivel pipeline: generador = reglas→tabla; E1.2 = tabla+mirror→registros).
- **Filtro de universo `source: "laudus-erp"`** compartido por transformador y verificador (mismo universo en ambos lados de la paridad). Los asientos manuales del proyecto (TC, categorizaciones) quedan fuera de la migración por contrato, no por descarte silencioso.
- **El verificador puede ponerse rojo (probado):** 6 tests de mutación cubren monto alterado, línea borrada, código cambiado (acusan los 2 códigos), entidad cambiada (acusan las 2 compañías — con 111005 real repetido EAG/FFCC), y `run_tier_a` levantando `ParityError`.
- **API de exclusiones lista para E1.3:** `expected_excluded_moves/lines` en `verify_counts`/`run_tier_a`; testeado con el caso real (excluir el par wash completo declarado → verde y la paridad sigue en 0 porque netea; excluir una sola pata → descuadra).
- Alcance respetado: sin sinceramiento por glosa (E1.3), sin dimensiones/partners (E1.4), sin Odoo (E1.5/E1.6). Todo E1.2 es Tier A; no se agregó ningún test `@pytest.mark.odoo`.

### File List

- `pipeline/odoo_migration/mapping.py` (nuevo)
- `pipeline/odoo_migration/transform.py` (nuevo)
- `pipeline/odoo_migration/parity.py` (nuevo)
- `pipeline/odoo_migration/tests/test_mapping_table.py` (nuevo)
- `pipeline/odoo_migration/tests/test_transform_collapse.py` (nuevo)
- `pipeline/odoo_migration/tests/test_parity_tier_a.py` (nuevo)
- `pipeline/odoo_migration/README.md` (modificado — sección E1.2 + contrato de regresión)
- `_bmad-output/implementation-artifacts/E1-2-transformador-colapso-verificador-paridad.md` (este registro)

## Change Log

- 2026-07-25 — **Code review 3 capas (Blind Hunter / Edge Case Hunter / Acceptance Auditor) → DONE.** Auditor: 4/4 ACs PASS + snapshot PASS (números 568/335/361 re-derivados independientemente del CSV; suites re-corridas y coincidentes). 26 hallazgos brutos → **7 patches aplicados** (loader fail-loud: utf-8-sig + headers + tabla vacía + >1 fila sin code; cross-check columna `company` CSV vs derivada; `(company, je_id)` duplicado fail-loud; move sin patas fail-loud; simetría de guards en parity; `zip strict=True` + 2 tests de fail-loud faltantes; conteos del registro corregidos), **4 defers con razón** (exclusiones por identidad → E1.3; `posting.price` → E1.5; diffs programáticos en `ParityError` → E1.3/E1.6; validación `otype` → E1.5; en `deferred-work.md`), 3 dismiss. +11 tests del review (paquete 75 passed / 5 skipped; suite completa **332 passed / 7 skipped**, 0 regresiones). Status → done.
- 2026-07-25 — E1.2 implementada: transformador de colapso (`mapping.py` + `transform.py`) y verificador de paridad Tier A (`parity.py`: origen FR8 + destino FR12a + conteos FR12b con exclusiones declarables) como regresión reusable para E1.3/E1.4. 37 tests nuevos (incl. 6 de mutación); paquete 64 passed / 5 skipped; suite completa 321 passed / 7 skipped, 0 regresiones; bean-check verde. Snapshot del plan pinneado con números reales (568 códigos / 335 destinos globales / 361 por compañía). Status → review.
