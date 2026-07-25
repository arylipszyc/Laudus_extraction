# Story E1.1: Módulo Odoo x_laudus_migration + 2 compañías sin l10n_cl

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **family office**,
I want **un módulo Odoo propio (`x_laudus_migration`) con los campos custom indexados, los 6 planes analíticos, un diario por compañía, y las 2 compañías (EAG / RUT2) creadas sin plan chileno**,
so that **la estructura receptora de la migración existe con trazabilidad al origen Laudus y sin el árbol del SII contaminando el plan — lista para que E1.2→E1.5 carguen datos encima**.

## Contexto (qué construye E1.1 y qué NO)

Es la **segunda story de Epic E1**. E1.0 dejó el scaffold del **transformador** (Python puro, pipeline `pipeline/odoo_migration/`). E1.1 construye la otra mitad: la **estructura receptora dentro de Odoo** — un módulo addon de verdad (versionado en git, NO Studio), instalable en la instancia Odoo 18 Community del spike.

E1.1 crea **contenedores vacíos**, no datos:
- Los **campos custom** donde el loader (E1.5) va a estampar la trazabilidad al origen Laudus.
- Los **6 planes analíticos** (los contenedores `account.analytic.plan`), NO sus cuentas/valores individuales (eso es E1.4).
- **Un diario por compañía** y **las 2 compañías** EAG y RUT2.

Nada de plan de cuentas Laudus (E1.2), sinceramiento (E1.3), dimensiones-valores/partners (E1.4), ni carga de asientos (E1.5).

> **Arquitectura aprobada:** resumen ejecutivo de `winston-arquitectura-e1-odoo-2026-07-23.md` aprobado por Ary el 2026-07-24. Detalle técnico auto-aprobado según `project-context.md`.

## Acceptance Criteria

Copiadas del epic (`epics.md` → Story E1.1), en formato Given/When/Then:

**AC1 — El módulo instala y declara los campos custom (todos los de línea indexados)**
**Given** una instancia Odoo 18 Community limpia,
**When** se instala el módulo `x_laudus_migration`,
**Then** instala **sin error** y declara:
- en `account.move.line`: `x_laudus_account_code`, `x_laudus_je_id`, `x_laudus_entity` (los tres **indexados**),
- `x_laudus_group` en `account.account`,
- `x_laudus_je_id` en `account.move` (indexado).

**AC2 — El seed crea los 6 planes analíticos + un diario por compañía**
**Given** el módulo instalado,
**When** se ejecuta su seed,
**Then** crea los **6 planes analíticos** (`account.analytic.plan`): propiedad/objeto, área/centro, offshore/vehículo, por-cuenta-de, socio-uso, entidad; y **un diario** (`account.journal`, tipo general) **por compañía**.

**AC3 — Las 2 compañías se crean sin l10n_cl**
**Given** la creación de compañías,
**When** se crean `EAG` (RUT1) y `RUT2` (FFCC+JAB),
**Then** **ninguna tiene `l10n_cl` instalado**; si algún módulo exige un CoA para operar, se usa `l10n_generic_coa` con sus cuentas **archivadas**.

**AC4 — `x_laudus_account_code` tiene índice de base de datos**
**Given** el campo `x_laudus_account_code`,
**When** se inspecciona el esquema de la base,
**Then** tiene **índice de base de datos** (es la query más caliente del verificador de paridad: `GROUP BY x_laudus_account_code` sobre ~100k+ líneas).

## Alcance — qué SÍ y qué NO hace E1.1

**SÍ (deliverables):**
- Crear el módulo addon `x_laudus_migration` (manifest + modelos + data seed) versionado en git, mountable en la instancia Odoo.
- Declarar los 5 campos custom vía `_inherit` (3 en `account.move.line` indexados, 1 en `account.account`, 1 en `account.move` indexado).
- Seed de los 6 `account.analytic.plan` (solo los contenedores) + 1 `account.journal` por compañía.
- Crear las 2 `res.company` (EAG, RUT2) sin `l10n_cl`; fallback `l10n_generic_coa` con cuentas archivadas si algo lo exige.
- Un `docker-compose` propio de E1.1 que monta este addon (resuelve el defer de E1.0: no escribir en el bind-mount compartido del spike) + un test Tier B (opt-in) que instala el módulo y verifica AC1–AC4.

**NO (es de otra story):**
- Plan de cuentas Laudus (colapso 569→336) → **E1.2**.
- Sinceramiento por naturaleza → **E1.3**.
- Las **cuentas analíticas / valores** dentro de los planes + partners → **E1.4**.
- Carga de asientos hacia Odoo → **E1.5**.
- Acción de servidor de paridad (opcional en la arquitectura) → diferida; nace como script externo en E1.2/E1.6.

## Tasks / Subtasks

- [x] **Task 1 — Estructura del módulo addon `x_laudus_migration` (AC1)**
  - [x] Crear el árbol del addon: `__manifest__.py`, `__init__.py`, `models/`, `data/`. **Hecho** en `pipeline/odoo_migration/addons/x_laudus_migration/` (ubicación recomendada).
  - [x] `__manifest__.py`: `version 18.0.1.0.0`, `depends ["account","analytic"]`, `license LGPL-3`, `data`, `post_init_hook`. Patrón: `spike_account_panel`.
  - [x] `depends` mínimo confirmado (account + analytic; NO l10n_cl). El módulo instala limpio en Odoo 18 (Tier B verde).
- [x] **Task 2 — Campos custom vía `_inherit` (AC1, AC4)**
  - [x] `models/account_move_line.py`: 3 campos `Char(index=True)`.
  - [x] `models/account_account.py`: `x_laudus_group = Char()` (sin índice).
  - [x] `models/account_move.py`: `x_laudus_je_id = Char(index=True)`.
  - [x] `models/__init__.py` + `__init__.py` wiring.
  - [x] `index=True` crea el índice btree — confirmado por el test vía `pg_indexes` (AC4).
- [x] **Task 3 — Seed: 6 planes analíticos + diario por compañía + 2 compañías (AC2, AC3)**
  - [x] 2 compañías + diario por compañía vía `post_init_hook` (`hooks.py`), idempotente (search-before-create). **Gotcha resuelto** (ver Completion Notes): había que **cancelar la auto-carga de `generic_coa`** que `account` programa para la compañía principal — si no, su `chart_template._load` BORRA el "Diario Laudus" recién creado. Referencia ORM: `import_to_odoo.py`.
  - [x] 6 `account.analytic.plan` vía `data/analytic_plans.xml` (solo contenedores; valores en E1.4).
  - [x] Ninguna compañía instala `l10n_cl` (AC3 verde). Camino tomado: **sin CoA** (se cancela `generic_coa`), como el spike/arquitectura §7.2. No hizo falta el fallback `l10n_generic_coa`+archivar.
- [x] **Task 4 — Compose propio de E1.1 + test Tier B (AC1–AC4)**
  - [x] `pipeline/odoo_migration/docker-compose.yml` (E1.1-owned, puerto 8070, project aislado `migration_e1`, monta `./addons`) + `odoo.conf` (necesario para que `exec odoo` conozca el db host). Resuelve el defer de E1.0.
  - [x] `tests/test_x_laudus_migration_install.py` (Tier B, `@pytest.mark.odoo`, fixture module-scoped): instala + verifica los 5 campos, 4 índices, 6 planes, 2 diarios, 2 compañías sin l10n_cl. **4 passed** (~37s).
  - [x] README del paquete actualizado con la sección E1.1.
- [x] **Task 5 — Regresión y guardrail del mirror**
  - [x] `bean-check` del mirror verde (E1.1 no toca `ledger/`): exit 0.
  - [x] Suite backend completa sin regresiones: **284 passed, 7 skipped** (los 4 de E1.1 + 3 previos, todos Tier B).

### Review Findings

Code review 2026-07-24 (3 capas: Blind Hunter / Edge Case Hunter / Acceptance Auditor). AC1–AC4: **4/4 PASS** (veredicto del auditor). 0 decision-needed, 5 patch, 2 defer, 12 dismissed. **Los 5 patches aplicados y re-verificados**: Tier B 4 passed (~59s, db fresca con hook parcheado), suite completa backend+pipeline 284 passed / 7 skipped (= baseline, 0 regresiones).

- [x] [Review][Patch] El fixture no espera readiness de Postgres entre `up -d` y el install exec — en volumen fresco (initdb en curso) el `odoo -i` pega connection-refused y el gate falla flaky sobre código sano; E1.0 sí pollea (`_wait_for_odoo`) [pipeline/odoo_migration/tests/test_x_laudus_migration_install.py:58-68]
- [x] [Review][Patch] DB `test_e1` estale de un run anterior matado a la fuerza (`restart: unless-stopped` + `finally` nunca corrido) → el `-i` sobre db ya instalada NO re-corre el `post_init_hook` y los 4 tests validan lo que dejó código VIEJO (falso verde). Falta `dropdb --if-exists test_e1` antes de instalar [pipeline/odoo_migration/tests/test_x_laudus_migration_install.py:62-68]
- [x] [Review][Patch] La búsqueda idempotente de diarios no ve diarios archivados (search default excluye `active=False`) → reinstall con LAU1/LAU2 archivado crashea contra la unique constraint por compañía. Falta `with_context(active_test=False)` [pipeline/odoo_migration/addons/x_laudus_migration/hooks.py:58]
- [x] [Review][Patch] Asserts del test más débiles que lo que los ACs piden: AC2 cuenta diarios por code sin verificar `type='general'` ni 1-por-compañía; AC3 verifica pertenencia y no cardinalidad (==2 compañías); y el invariante central "compañías sin CoA" no tiene assert directo (`count(account_account)==0` — hoy solo lo guarda indirectamente el conteo de diarios) [pipeline/odoo_migration/tests/test_x_laudus_migration_install.py:107-126]
- [x] [Review][Patch] `restart: unless-stopped` en un stack cuyo ciclo de vida lo maneja el fixture — un run huérfano se auto-resucita tras reiniciar el daemon y retiene el puerto 8070 [pipeline/odoo_migration/docker-compose.yml:18,33]
- [x] [Review][Defer] `del registry._auto_install_template` depende de un interno privado de Odoo + tag flotante `odoo:18` — si Odoo lo renombra, el guard `hasattr` lo vuelve no-op silencioso. Mitigado: la regresión la pescan los tests (más fuerte aún tras el patch de asserts). Pinnear la imagen = decisión de stack que afecta también al spike — deferred [pipeline/odoo_migration/addons/x_laudus_migration/hooks.py:20-22]
- [x] [Review][Defer] `up -d` fallido → `pytest.skip` con razón "¿daemon abajo?" enmascara causas reales (p.ej. puerto 8070 ocupado): el gate opt-in no corre y parece verde. Mismo patrón ya adjudicado en el smoke de E1.0 — hardening low-pri, no re-litigado [pipeline/odoo_migration/tests/test_x_laudus_migration_install.py:58-59]

Dismissed destacados (verificados, no ruido especulativo): "planes analíticos ligados a la compañía principal" = falso positivo (`account.analytic.plan` NO tiene `company_id` en Odoo 18 — verificado en el source de la imagen; el `company_id` con default es de `account.analytic.applicability`); conftest sí cubre el archivo nuevo (opt-in intacto); `--without-demo all` vigente en 18.0 (`tools/config.py:114`); `_has_index` LIKE sin colisiones entre los 5 nombres reales; credenciales hardcodeadas = stack local descartable (patrón del spike); hook asume db fresca (rename de main company + CLP) = diseño spec'd de la story.

## Dev Notes

### Ubicación del addon + compose propio (decisión recomendada)
La arquitectura dice "módulo propio en `addons/`". El spike monta `_spike-odoo/addons/` (bind mount) y ya tiene un addon de ejemplo (`spike_account_panel`) + OCA clonado. Dos opciones:
- **(Recomendada)** El addon vive en el track de migración versionado: `pipeline/odoo_migration/addons/x_laudus_migration/`, y E1.1 trae **su propio** `docker-compose.yml` que monta ese dir. Ventaja: resuelve el defer de E1.0 (el smoke ya no escribe en el `_spike-odoo/addons` compartido), queda todo en el track tracked, y `_spike-odoo/` (untracked, "spike") no es dependencia dura.
- Alternativa: dejarlo en `_spike-odoo/addons/x_laudus_migration/`. Descartada: `_spike-odoo/` está untracked y es el spike; acoplar el módulo de producción ahí lo hace frágil.
El dev puede ajustar la ruta exacta; lo que NO cambia: **E1.1 tiene su propio compose que monta el addon** (Tier B aislado). [Source: deferred-work.md; winston §7.1]

### Los campos custom — tabla exacta (congelar tipos)
[Source: winston §4, tabla de campos]

| Modelo | Campo | Tipo | Índice |
|---|---|---|---|
| `account.move.line` | `x_laudus_account_code` | Char | **Sí** — la llave de paridad |
| `account.move.line` | `x_laudus_je_id` | Char | Sí |
| `account.move.line` | `x_laudus_entity` | Char | Sí |
| `account.account` | `x_laudus_group` | Char | — |
| `account.move` | `x_laudus_je_id` | Char | Sí |

> **El punto que hace cuadrar todo:** `account.account.code` = la cuenta Odoo COLAPSADA (nueva). `x_laudus_account_code` (en la LÍNEA) = el código Laudus ORIGINAL. Muchos códigos Laudus → una cuenta Odoo, pero cada línea conserva su origen. La paridad (E1.6) NO se verifica por cuenta Odoo, sino **agrupando por `x_laudus_account_code`** → por eso ese campo se indexa (query más caliente, ~100k+ líneas × 5 años). [Source: winston §4]

### Consistencia con la convención congelada de external IDs (E1.0)
El loader (E1.5) estampa estos campos y usa external IDs `acc_<company>_<code>` / `mv_<company>_<je_id>` / `aml_<company>_<je_id>_<n>` (congelados en `pipeline/odoo_migration/external_ids.py`, story E1.0, incluye `company` en la línea porque el `id` Laudus reinicia por entidad). E1.1 solo declara los campos; NO los llena. Pero los **tipos** (Char) deben aguantar lo que E1.5 va a poner: `x_laudus_je_id` = el meta `id` del asiento (string), `x_laudus_entity` ∈ {EAG, Jocelyn, Jeannette, Johanna, Jael, FFCC, JAB}, `x_laudus_account_code` = code Laudus (string numérico). [Source: E1.0 external_ids.py; winston §2.3]

### Los 6 planes analíticos = contenedores, NO valores
E1.1 crea los 6 `account.analytic.plan` vacíos. Las `account.analytic.account` (Vía Gris, Leo, AAG, EAG…) las crea E1.4 (transformador de dimensiones). No adelantar valores acá. En Odoo 17/18 la analítica es plan + account con `analytic_distribution` (JSON) en la línea. [Source: winston §5.1, §5.3; epics.md E1.4]

### Compañías: entidad interna = dimensión, NO compañía
Solo **2** `res.company`: EAG (RUT1, incluye las 4 hijas) y RUT2 (FFCC+JAB). Las hijas/FFCC/JAB son **dimensión** (`x_laudus_entity` + plan analítico Entidad), no compañías — hacerlas compañía forzaría un asiento inter-compañía en cada gasto. Plan de cuentas **por compañía** (no compartido), como el spike (`company_ids` a una sola company). Consolidación "EAG+hijas" se resuelve en capa de reporte (Community no trae consolidación Enterprise). [Source: winston §3]

### Sin l10n_cl (por qué)
La contabilidad familiar no declara IVA ni renta por Odoo → no necesita el árbol del SII. El spike ya demostró crear `account.account` por ORM sin plantilla CoA. Si un módulo exige CoA mínimo: `l10n_generic_coa` + archivar sus cuentas. [Source: winston §7.2]

### Insumos existentes que E1.1 reusa (NO reescribe)
- `_spike-odoo/addons/spike_account_panel/` — patrón de addon Odoo 18 (manifest, `_inherit`, campo custom `store=True`, view). Referencia de estructura.
- `_spike-odoo/import_to_odoo.py` — crea EAG/RUT2 (`res.company`), journal "Diario Laudus" (tipo general, code), cuentas por ORM. Referencia para el `post_init_hook`.
- `_spike-odoo/docker-compose.yml` + `odoo.conf` — stack Odoo 18 + PG 16. El compose de E1.1 se modela en este.
- `pipeline/odoo_migration/` (E1.0) — el paquete hermano; E1.1 agrega el addon + su compose bajo el mismo track.

### Testing Requirements
- **Tier B (Odoo, opt-in)** es el gate real de E1.1: instalar el módulo y verificar AC1–AC4 exige Odoo levantado. Marcar `@pytest.mark.odoo` (el `conftest.py` de E1.0 ya lo salta por defecto). Correr: `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest pipeline/odoo_migration -m odoo -q`.
- **Tier A (por-commit)**: mínimo — a lo sumo un test estructural de que el `__manifest__.py` parsea y lista los data files esperados. El grueso es Tier B.
- **Verificación del índice (AC4):** consultar `pg_indexes` (o `\d account_move_line`) dentro del contenedor para confirmar el índice sobre `x_laudus_account_code`.
- **bean-check del mirror** sigue verde (guardrail: E1.1 no toca `ledger/`). [Source: project-context.md §Comandos de verificación]
- 0 regresiones en la suite backend existente.

### Project Structure Notes
- Addon nuevo: `pipeline/odoo_migration/addons/x_laudus_migration/` (recomendado) — `__manifest__.py`, `__init__.py`, `models/{__init__,account_move_line,account_account,account_move,hooks}.py`, `data/analytic_plans.xml`.
- Compose nuevo: `pipeline/odoo_migration/docker-compose.yml` (E1.1-owned, monta el addon, project aislado).
- Test nuevo: `pipeline/odoo_migration/tests/test_x_laudus_migration_install.py` (Tier B).
- README del paquete: agregar sección de E1.1 (instalar módulo + correr Tier B).

### References
- [Source: _bmad-output/planning-artifacts/odoo-migracion/epics.md#Story-E1.1] — ACs originales.
- [Source: winston-arquitectura-e1-odoo-2026-07-23.md#4] — campos custom + índice de paridad.
- [Source: winston-arquitectura-e1-odoo-2026-07-23.md#5.1] — los 6 planes analíticos.
- [Source: winston-arquitectura-e1-odoo-2026-07-23.md#3] — estructura de 2 compañías + entidad como dimensión.
- [Source: winston-arquitectura-e1-odoo-2026-07-23.md#7.2] — sin l10n_cl.
- [Source: _spike-odoo/addons/spike_account_panel/] — patrón de addon Odoo 18.
- [Source: _spike-odoo/import_to_odoo.py] — creación de compañías/diario por ORM.
- [Source: pipeline/odoo_migration/external_ids.py] — convención congelada que E1.5 estampa en estos campos.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — el compose propio de E1.1 resuelve el defer del smoke de E1.0.

### Preguntas guardadas para el dev / Ary (no bloquean)
1. **Compañías vía módulo vs entorno:** la story sigue el epic (E1.1 crea EAG/RUT2 vía `post_init_hook` idempotente). Alternativa: dejarlas como setup de entorno del loader (E1.5). Recomiendo seguir el epic — la reproducibilidad del entorno (módulo instala → estructura completa) vale. Decisión técnica, el dev puede resolver.
2. **`x_laudus_je_id` es Char en línea y en cabecera:** mismo nombre, dos modelos — correcto en Odoo. La línea lo lleva para corte/idempotencia de la pata; la cabecera para el upsert del move.
3. **OCA en el compose de E1.1:** no hace falta para instalar `x_laudus_migration` (solo depende de `account`+`analytic`). OCA `account-financial-reporting` es para reportes (fase posterior). Mantener el compose de E1.1 mínimo.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Amelia / dev-story)

### Debug Log References

- Tier B (gate real): `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest pipeline/odoo_migration/tests/test_x_laudus_migration_install.py -m odoo -q` → **4 passed** (~37s). Instala el módulo en db fresca + verifica AC1-AC4 por SQL.
- Tier A: `pytest pipeline/odoo_migration -q` → 27 passed, 5 skipped (los 4 de E1.1 + el smoke de E1.0, todos Tier B).
- bean-check mirror: exit 0.

### Completion Notes List

- **Gotcha central resuelto — la auto-carga de `generic_coa` borraba el diario.** El primer install dejaba solo 1 de los 2 diarios. Causa (investigada en el source de Odoo): al instalar `account`, `ir_module.write` programa `registry._auto_install_template` que, al finalizar el módulo (`ir_module._register_hook`), carga `generic_coa` en la compañía principal. Ese `chart_template._load`, cuando la compañía no tiene contabilidad aún, **borra sus journals** (unlink) antes de cargar el template → se llevaba puesto el "Diario Laudus" (LAU1) de EAG. RUT2 (compañía nueva, no principal) no recibía el auto-load, por eso su LAU2 sobrevivía. **Fix:** el `post_init_hook` **cancela** ese auto-load (`del registry._auto_install_template`) — corre antes de `_register_hook`. Alineado con el diseño (compañías SIN CoA, plan Laudus-puro lo cargan E1.2/E1.5), no un workaround.
- **`odoo.conf` en el compose de E1.1:** `docker compose exec odoo …` NO pasa por el entrypoint de la imagen, así que las env vars `HOST/USER/PASSWORD` no se traducen a `--db_host` y Odoo intentaba un socket local. Se monta `odoo.conf` con `db_host` (como el spike) para que cualquier `exec odoo` conecte.
- **Fixture del test module-scoped:** levanta e instala UNA vez; los 4 tests consultan la misma db (function-scope reinstalaría Odoo 4 veces).
- **Compose propio de E1.1** (puerto 8070, project `migration_e1`) resuelve el defer de E1.0 (el smoke ya no escribe en el `_spike-odoo/addons` compartido). El smoke de E1.0 sigue usando el compose del spike; ambos coexisten en puertos distintos.
- Alcance respetado: E1.1 crea solo **contenedores** (campos, planes vacíos, diarios, compañías). Sin plan de cuentas Laudus (E1.2), sin sinceramiento (E1.3), sin valores de dimensiones/partners (E1.4), sin carga de asientos (E1.5).

### File List

- `pipeline/odoo_migration/addons/x_laudus_migration/__manifest__.py` (nuevo)
- `pipeline/odoo_migration/addons/x_laudus_migration/__init__.py` (nuevo)
- `pipeline/odoo_migration/addons/x_laudus_migration/hooks.py` (nuevo)
- `pipeline/odoo_migration/addons/x_laudus_migration/models/__init__.py` (nuevo)
- `pipeline/odoo_migration/addons/x_laudus_migration/models/account_move_line.py` (nuevo)
- `pipeline/odoo_migration/addons/x_laudus_migration/models/account_account.py` (nuevo)
- `pipeline/odoo_migration/addons/x_laudus_migration/models/account_move.py` (nuevo)
- `pipeline/odoo_migration/addons/x_laudus_migration/data/analytic_plans.xml` (nuevo)
- `pipeline/odoo_migration/docker-compose.yml` (nuevo — compose propio de E1.1)
- `pipeline/odoo_migration/odoo.conf` (nuevo)
- `pipeline/odoo_migration/tests/test_x_laudus_migration_install.py` (nuevo — Tier B)
- `pipeline/odoo_migration/README.md` (modificado — sección E1.1)
- `_bmad-output/implementation-artifacts/E1-1-modulo-odoo-x-laudus-migration.md` (este registro)

## Change Log

- 2026-07-24 — E1.1 implementada: módulo Odoo `x_laudus_migration` (5 campos custom de trazabilidad indexados, 6 planes analíticos, 2 compañías EAG/RUT2 sin l10n_cl + diario por compañía) + compose propio + test Tier B. Gotcha del auto-CoA de Odoo resuelto. Tier B 4 passed, bean-check verde. Status → review.
- 2026-07-24 — Code review 3 capas: AC1–AC4 4/4 PASS. 5 patches aplicados (readiness-wait de Postgres + dropdb pre-install en el fixture, `active_test=False` en la búsqueda idempotente de diarios, asserts reforzados AC2/AC3 + guard directo sin-CoA, sin `restart: unless-stopped`), 2 defers a deferred-work.md, 12 descartados (2 falsos positivos verificados contra el source de Odoo 18 en la imagen). Tier B 4 passed post-patch, suite completa 284/7 sin regresiones. Status → done.
