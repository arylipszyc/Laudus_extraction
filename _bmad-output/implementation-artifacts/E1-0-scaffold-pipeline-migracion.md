# Story E1.0: Scaffold del pipeline de migración + fixture golden

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **equipo de desarrollo del family office**,
I want **un scaffold testeable (harness pytest + Odoo en Docker + fixture golden con caso USD + helper de external IDs)**,
so that **toda story posterior (E1.1→E1.6) se construye y verifica sin re-armar infra y sin descubrir bugs de moneda recién en el full load**.

## Contexto (por qué esta story es la story-0 bloqueante)

Esta es la **primera story de Epic E1** (Migración Laudus → Odoo, Fase 1a) y es **bloqueante**: nada de E1.1→E1.6 arranca hasta que este scaffold esté verde. No implementa lógica de negocio (colapso, sinceramiento, dimensiones, loader) — eso son las stories siguientes. Su única misión es dejar la **infraestructura de desarrollo y verificación** lista, con tres piezas que la mesa redonda 2026-07-23 marcó como precondición para no repetir dolores conocidos del proyecto:

1. **Harness pytest** integrado al comando de verificación real del proyecto (lección `tsc --noEmit`: el gate tiene que ser el comando que el proyecto ya corre, no uno inventado que da verde vacío).
2. **Fixture golden con caso USD obligatorio** — para descubrir bugs de multi-moneda en un slice chico y rápido, no recién en el full load de 5 años × 2 compañías × ~100k+ líneas.
3. **Helper de external IDs determinísticos** — la columna vertebral de la idempotencia del loader (E1.5); se testea unitariamente desde el día 0.

> **Arquitectura aprobada:** el resumen ejecutivo de `winston-arquitectura-e1-odoo-2026-07-23.md` fue **aprobado por Ary el 2026-07-24**. El detalle técnico está auto-aprobado según `project-context.md`.

## Acceptance Criteria

Copiadas del epic (`epics.md` → Story E1.0), en formato Given/When/Then:

**AC1 — Harness integrado al comando real del proyecto**
**Given** el repo del proyecto,
**When** corro `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest <ruta-pipeline-migración>`,
**Then** el harness del pipeline de migración corre en verde y **queda integrado al comando de verificación del proyecto** (no un comando inventado — ver §Testing Requirements: el módulo vive donde `pytest backend/tests pipeline` ya lo descubre).

**AC2 — Fixture golden con USD + un caso-borde por naturaleza**
**Given** el espejo Beancount (`ledger/main.beancount`),
**When** se construye el fixture golden,
**Then** es un slice **pinneado** (1 entidad, pocos meses) que incluye **obligatoriamente**:
- ≥1 asiento **USD** (con `currency_id` + `amount_currency`), y
- ≥1 **caso-borde de cada naturaleza de sinceramiento**: traspaso, retiro, aporte, wash apertura/cierre, ambiguo.

**AC3 — Helper de external IDs determinístico y testeado**
**Given** el helper de external IDs,
**When** se le pasa `(compañía, code)` / `(compañía, je_id)` / `(compañía, je_id, n)`,
**Then** devuelve **determinísticamente** `acc_<cía>_<code>` / `mv_<cía>_<jeid>` / `aml_<cía>_<jeid>_<n>`, cubierto por **test unitario**.

**AC4 — Odoo en Docker levanta y el módulo instala**
**Given** el `docker-compose` del spike,
**When** se levanta para los tests del loader,
**Then** **Odoo 18 Community + Postgres 16 responde** y el módulo `x_laudus_migration` **se puede instalar** (aunque el módulo en sí lo construye E1.1 — E1.0 solo verifica que el stack levanta y acepta un addon custom; ver §Alcance).

## Alcance — qué SÍ y qué NO hace E1.0

**SÍ (deliverables de esta story):**
- Crear el paquete Python del pipeline de migración con su `__init__.py` y sub-paquete de tests.
- Implementar `external_ids.py` (el helper de AC3) + su test unitario.
- Construir el **fixture golden** (`golden_slice.beancount` o equivalente) que cumple AC2, + un test de sanidad que lo carga con `beancount.loader` y verifica que trae los casos requeridos.
- Dejar el `docker-compose` de Odoo listo para los tests del loader (promovido/hardened desde `_spike-odoo/docker-compose.yml`), + un smoke test (marcado, opt-in) que levanta el stack y confirma que responde.
- Actualizar `project-context.md` (o dejarlo ya cubierto) para que el comando de verificación descubra el nuevo harness **sin inventar un comando nuevo**.

**NO (es de otra story — no implementar acá):**
- El módulo Odoo `x_laudus_migration` con sus campos custom / planes analíticos → **E1.1**.
- El transformador de colapso (569→336) → **E1.2**.
- El sinceramiento por naturaleza → **E1.3**.
- Dimensiones + partners → **E1.4**.
- El loader real hacia Odoo → **E1.5**.
- El verificador de paridad Tier A/B → nace en **E1.2**, full en **E1.6**.

## Tasks / Subtasks

- [x] **Task 1 — Crear el paquete del pipeline de migración (AC1)**
  - [x] Crear `pipeline/odoo_migration/__init__.py` (paquete nuevo, hermano de los sub-paquetes existentes del `pipeline/`).
  - [x] Crear `pipeline/odoo_migration/tests/__init__.py` y `pipeline/odoo_migration/tests/conftest.py`.
  - [x] Verificar que `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest pipeline/odoo_migration -q` descubre y corre los tests (el comando de verificación del proyecto ya incluye `pipeline`, así que el nuevo sub-paquete queda cubierto sin cambiar el comando — confirmar). **Confirmado**: el comando full `pytest backend/tests pipeline` descubre y corre los 19 tests Tier A (smoke Tier B skipped).
- [x] **Task 2 — Helper de external IDs + test unitario (AC3)**
  - [x] Implementar `pipeline/odoo_migration/external_ids.py` con tres funciones puras:
    - `account_xmlid(company, code) -> "acc_<company>_<code>"`
    - `move_xmlid(company, je_id) -> "mv_<company>_<je_id>"`
    - `line_xmlid(company, je_id, n) -> "aml_<company>_<je_id>_<n>"`
  - [x] Definir la **normalización de los componentes** (mayúsculas/minúsculas, caracteres no válidos para un external ID de Odoo, colisiones EAG vs RUT2) y documentarla en el módulo. Un external ID de Odoo debe ser único y estable → decidir la convención exacta (p.ej. `company` en minúsculas, `code`/`je_id` tal cual, `n` como índice de la pata) y **congelarla acá** porque E1.5 depende de ella. **Congelado**: `company` a minúsculas (EAG/RUT2 no colapsan; misma entidad en cualquier caja → mismo id = feature); `code`/`je_id` `str().strip()` tal cual; `n` = índice 0-based de la pata; componentes vacíos o con chars no válidos para XML ID → `ValueError` (fail-loud).
  - [x] `test_external_ids.py`: casos de las 3 funciones, incluyendo determinismo (mismo input → mismo output), unicidad EAG vs RUT2 para el mismo `code`, y estabilidad del formato.
- [x] **Task 3 — Fixture golden (AC2)**
  - [x] Construir `pipeline/odoo_migration/tests/fixtures/golden_slice.beancount` (o `.py` que lo genera desde `ledger/main.beancount`). **Ojo (ver Dev Notes):** un corte ingenuo por fecha/entidad NO garantiza cubrir todas las naturalezas → el fixture es **curado**: se seleccionan asientos reales del mirror que cubren cada caso. **Hecho**: 4 asientos reales verbatim (retiro id 1237, aporte id 3994, traspaso id 29, ambiguo id 4158) + par wash sintético (Latinoamericana ±423,6M) + asiento USD sintético; procedencia anotada por asiento.
  - [x] Garantizar cobertura obligatoria: ≥1 USD, y ≥1 de {traspaso, retiro, aporte, wash apertura/cierre, ambiguo}.
  - [x] `test_fixture_golden.py`: carga el slice con `beancount.loader`, verifica 0 errores de bean-check, y assertea que cada naturaleza y el caso USD están presentes (guardrail contra que alguien "simplifique" el fixture y borre un caso). **+** test extra que el par wash netea a 0.
- [x] **Task 4 — Docker Odoo listo para tests del loader (AC4)**
  - [x] Promover/hardenear `_spike-odoo/docker-compose.yml` a la ubicación del pipeline de migración (o referenciarlo explícitamente). Confirmar Odoo 18 + Postgres 16. **Decisión**: referenciar el del spike (recomendación Dev Notes #3), bajo un project name aislado `migration_smoke` para no tocar los volúmenes del spike.
  - [x] Smoke test **marcado y opt-in** (`@pytest.mark.odoo` o similar, saltado por defecto en CI-por-commit): levanta el stack, confirma que Odoo responde en :8069, y que acepta instalar un addon custom mínimo. (El módulo real es E1.1; acá basta un addon-stub o verificar que `--stop-after-init -i <addon>` no falla por infra.) **Verificado end-to-end** en esta máquina (Docker disponible): Odoo 18 responde + scaffold + `--stop-after-init -i` de addon custom = exit 0.
  - [x] Documentar en README del paquete: cómo levantar el stack, cómo correr el smoke, y que **NO** corre por-commit (es Tier B — gate de release, lección `tsc --noEmit`).
- [x] **Task 5 — Cerrar el AC1 de "comando real"**
  - [x] Verificar/actualizar que `project-context.md` §Comandos de verificación cubra el nuevo harness sin comando inventado. Si el comando actual (`pytest backend/tests pipeline`) ya lo descubre, dejar una nota confirmándolo; si hiciera falta ampliar la ruta, actualizar `project-context.md` Y el hook `.githooks/pre-push` de forma consistente. **El comando actual ya descubre el paquete sin cambios** → agregada nota en `project-context.md` confirmándolo + aclarando que el smoke es Tier B opt-in. No hizo falta tocar el hook.
  - [x] Correr el comando de verificación completo del backend y confirmar 0 regresiones en la suite existente. **0 regresiones de E1.0**: `1 failed, 275 passed, 3 skipped`. El único fallo (`test_rut2_import_historico::test_apertura_es_je_real_via_211005`) es **pre-existente** (falla aislado sin mi paquete; el ledger re-importado trae narración "JE 1" y el test viejo espera "Saldo Inicial" — viene de commits fd023df/a53b7de, no de esta story).

## Dev Notes

### Decisión de ubicación (por qué `pipeline/odoo_migration/`)
El comando de verificación del proyecto es, textual de `project-context.md`:
`PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q`.
Poniendo el paquete nuevo **bajo `pipeline/`** (`pipeline/odoo_migration/`), pytest lo descubre **sin cambiar el comando** — que es justo lo que pide AC1 ("no un comando inventado"). El `pipeline/` existente es el sync Laudus→Beancount/Sheets; el sub-paquete `odoo_migration/` es lógicamente distinto pero convive limpio. **Alternativa descartada:** un top-level `migration/` obligaría a ampliar el comando en `project-context.md` + el hook pre-push — más superficie de error por menos beneficio. [Source: _bmad-output/project-context.md §Comandos de verificación]

### El helper de external IDs — la convención se congela acá
De la arquitectura: external IDs determinísticos `acc_<company>_<laudus_code>`, `mv_<company>_<je_id>`, `aml_<company>_<je_id>_<n>`. Son "la columna vertebral de la idempotencia" del loader: re-correr hace **upsert, no duplica**. E1.5 (loader) y E1.6 (verificador) dependen de que esta convención sea estable. **Congelar el formato exacto acá** y no cambiarlo después. [Source: winston-arquitectura-e1-odoo-2026-07-23.md §2.3, §7.3] **(Corregido en code-review 2026-07-24: la línea lleva `company` — el `id` de Laudus reinicia por entidad, `id=1` existe en EAG y RUT2, así que `aml_<je_id>_<n>` sin `company` colisionaba entre entidades y rompía la idempotencia.)**

### El fixture golden es CURADO, no un corte por fecha
AC2 pide "1 entidad, pocos meses" **y** "≥1 caso-borde de cada naturaleza". Esos dos requisitos pueden tensionar: una sola entidad en pocos meses **no** contiene naturalmente todas las naturalezas (p.ej. el **aporte** Sade vive en FFCC/`Income:FFCC:Sade-310011`; los **retiros** grandes en EAG `RetirosTecnin-310013`; los **washes** apertura/cierre en `OtrosIngresos-310099`). → El fixture se **cura**: se copian asientos reales del mirror que cubren cada caso, aunque provengan de más de una cuenta/mes, manteniéndolo chico. Documentar en el fixture **de dónde salió cada caso** (comentario con el código/glosa origen) para trazabilidad. Casos de referencia útiles del generador de Valentina:
- **retiro** → `RetirosTecnin-310013` (EAG) — [Source: spec §2.2·B]
- **aporte** → `Income:FFCC:Sade-310011` (+4.876M, signo +) — [Source: spec §2.2·C]
- **traspaso** → glosa "traspaso de/a", "a cta X" en `OtrosIngresos-310099` — [Source: spec §2.2·G]
- **wash apertura/cierre** → par "comprobante de apertura/cierre" igual-y-opuesto (caso canónico: Latinoamericana ±423,6M que netea a 0) — [Source: spec §3.2 paso 1; epics.md E1.3]
- **ambiguo** → el +32M "dividendo" dudoso de Nuevo Ciclo (H) o una línea sin match claro — [Source: epics.md E1.3 último AC]
- **USD** → cualquier asiento con `units.currency=="USD"` del mirror (el generador hoy solo suma CLP; el fixture debe forzar ≥1 USD para que E1.5 lo ejerza con `amount_currency`). [Source: winston §6 multi-moneda; epics.md E1.5]

### Separación transformador / loader (NFR3) — respetarla desde el scaffold
El transformador es **Python puro testeable sin Odoo levantado** (rápido, en pytest/CI). El loader es el **único** que toca Odoo (lento, requiere el contenedor). E1.0 ya refleja esto: los tests de `external_ids` y del fixture corren sin Odoo (Tier A, por-commit); el smoke de Docker es Tier B (opt-in, gate de release). No mezclar. [Source: winston §2.4 nota de honestidad arquitectónica, NFR3]

### Stack pineado (boring technology)
Odoo 18 Community + Postgres 16, Docker Compose, en el VPS Hetzner del runbook del spike. Cero licencia, sin costo recurrente nuevo (NFR5). El `_spike-odoo/docker-compose.yml` ya está probado (levantó 1 mes EAG+RUT2 vía `odoo shell`). [Source: winston §7.1; _spike-odoo/docker-compose.yml]

### Insumos existentes que E1.0 NO reescribe
- `ledger/main.beancount` — el espejo crudo confiable, fuente del fixture. **No se toca.**
- `valentina-tabla-mapeo-generador-2026-07-23.py` — el generador que E1.2+ va a **extender** (no reescribir). E1.0 no lo toca todavía, pero el fixture debe ser consistente con cómo el generador lee el mirror (`loader.load_file`, postings CLP/USD). [Source: winston §1, §2.2]
- `_spike-odoo/import_to_odoo.py` — el loader-prototipo del spike (external IDs, formato o2m de asientos). Referencia para E1.5; E1.0 solo reusa el compose.

### Project Structure Notes
- Paquete nuevo: `pipeline/odoo_migration/` (código) + `pipeline/odoo_migration/tests/` (tests + fixtures). Alineado con la convención del repo (`pipeline/` ya tiene sub-paquetes `services/`, `writers/`, `importers/`… con tests en `backend/tests/`).
- **Variante a decidir por el dev:** ¿los tests del nuevo paquete viven en `pipeline/odoo_migration/tests/` (co-locados) o en `backend/tests/`? El resto del proyecto co-loca en `backend/tests/`. Recomendación: co-locar en el paquete (`pipeline/odoo_migration/tests/`) porque es un track nuevo y autónomo; confirmar que el comando `pytest ... pipeline` los descubre igual. Documentar la elección.
- El `docker-compose` de migración: promover a `pipeline/odoo_migration/docker/` o dejar referencia a `_spike-odoo/`. Recomendación: referenciar el del spike hasta que E1.1 necesite el addon custom montado, para no duplicar.

### Testing Requirements
- **Comando de verificación (fuente de verdad, NO inventar otro):**
  `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q` (Windows: `PYTHONUTF8=1` obligatorio; venv del repo = `venv/`). [Source: project-context.md]
- **bean-check del fixture:** `venv/Scripts/python.exe -m beancount.scripts.check <fixture>` debe dar exit 0 (borrar cualquier `.picklecache` antes si aplica). [Source: project-context.md]
- Los tests de E1.0 (external IDs, fixture) son **Tier A** (Python puro, por-commit). El smoke de Docker es **Tier B** (opt-in, no por-commit). [Source: epics.md §Dos tiers de verificación]
- 0 regresiones en la suite backend existente tras agregar el paquete.

### References
- [Source: _bmad-output/planning-artifacts/odoo-migracion/epics.md#Story-E1.0] — ACs originales.
- [Source: _bmad-output/planning-artifacts/odoo-migracion/epics.md#Additional-Requirements] — "Scaffold (story E1.0, bloqueante)", "Dos tiers de verificación".
- [Source: _bmad-output/planning-artifacts/odoo-migracion/winston-arquitectura-e1-odoo-2026-07-23.md#2.3] — mecanismo de carga + external IDs.
- [Source: _bmad-output/planning-artifacts/odoo-migracion/winston-arquitectura-e1-odoo-2026-07-23.md#7.3] — idempotencia por external ID.
- [Source: _bmad-output/planning-artifacts/odoo-migracion/valentina-spec-estructura-odoo-2026-07-23.md#2] — lista de cuentas por naturaleza (insumo del fixture).
- [Source: _bmad-output/project-context.md] — comandos de verificación (NO inventar).
- [Source: _spike-odoo/docker-compose.yml] — stack Odoo 18 + Postgres 16.
- [Source: _spike-odoo/import_to_odoo.py] — loader-prototipo (referencia para E1.5).

### Preguntas guardadas para el dev / Ary (no bloquean el arranque)
1. **Ubicación de tests** (co-locados en `pipeline/odoo_migration/tests/` vs `backend/tests/`) — recomiendo co-locar; decisión técnica, el dev puede resolver.
2. **Formato exacto del external ID de la línea:** `aml_<company>_<je_id>_<n>` — `n` es el índice 0-based de la pata dentro del asiento. **(Resuelto en code-review 2026-07-24: se agregó `company` porque el `id` de Laudus reinicia por entidad y `aml_<je_id>_<n>` colisionaba entre EAG y RUT2.)**
3. **Compose promovido vs referenciado:** recomiendo referenciar el del spike hasta E1.1.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Amelia / dev-story)

### Debug Log References

- Tier A: `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest pipeline/odoo_migration -q` → 19 passed, 1 skipped (smoke Tier B).
- bean-check del fixture: `... -m beancount.scripts.check pipeline/odoo_migration/tests/fixtures/golden_slice.beancount` → exit 0.
- Smoke Tier B: `... -m pytest pipeline/odoo_migration -m odoo -q` → 1 passed (27s); Odoo 18 responde + scaffold + install addon custom OK; sin volúmenes huérfanos tras `down -v`.
- Suite full: `... -m pytest backend/tests pipeline -q` → 1 failed (pre-existente), 275 passed, 3 skipped.

### Completion Notes List

- **Decisiones congeladas (E1.5 depende de ellas):** external ID = `acc_<company-minúsc>_<code>` / `mv_<company-minúsc>_<je_id>` / `aml_<company-minúsc>_<je_id>_<n>`, con `n` = índice **0-based** de la pata. `company` a minúsculas (idempotencia case-insensitive) y **en las tres** llaves (incl. la línea — ver code-review 2026-07-24: el `id` de Laudus reinicia por entidad); componentes inválidos → `ValueError` (incl. separador `_`/`-` dentro del componente y `n` no-entero, endurecido en el mismo review). `<je_id>` = metadato `id` del asiento en el mirror (mismo que usa el prototipo del spike `import_to_odoo.py`), NO el `je_num`.
- **USD sintético (decisión técnica, auto-aprobada):** el mirror **no tiene ningún posting en USD** — todo es CLP y el "USD" real vive solo como texto en `desc`. AC2 exige ≥1 asiento USD con `amount_currency`, así que el fixture **fuerza** un asiento sintético `100 USD @ 800 CLP` (documentado como `[SINTÉTICO]`), para que E1.5 ejerza `currency_id`/`amount_currency`.
- **Wash sintético:** el asiento real de cierre (Latinoamericana ±423,6M) es un cierre anual de **184 patas** — incompatible con "fixture chico". Se redujo al par mínimo apertura/cierre Latinoamericana↔Apertura que netea a 0, conservando la señal que E1.3 detecta (glosa "Comprobante de apertura/cierre"). Documentado como `[SINTÉTICO]` con la procedencia real.
- **Docker aislado:** el smoke referencia el compose del spike pero bajo project name `migration_smoke`, así `down -v` nunca borra los volúmenes del stack del spike de Ary.
- **⚠️ Hallazgo fuera de scope (no arreglado — es de otra story):** `backend/tests/test_rut2_import_historico.py::test_apertura_es_je_real_via_211005` **falla pre-existente**: espera `narration == "Saldo Inicial"` pero el ledger re-importado (commits fd023df/a53b7de, "narración neutra") trae `"JE 1"`. Falla aislado sin mi paquete → no es regresión de E1.0. Amerita actualizar ese test aparte.

### File List

- `pipeline/odoo_migration/__init__.py` (nuevo)
- `pipeline/odoo_migration/external_ids.py` (nuevo)
- `pipeline/odoo_migration/README.md` (nuevo)
- `pipeline/odoo_migration/tests/__init__.py` (nuevo)
- `pipeline/odoo_migration/tests/conftest.py` (nuevo)
- `pipeline/odoo_migration/tests/test_external_ids.py` (nuevo)
- `pipeline/odoo_migration/tests/test_fixture_golden.py` (nuevo)
- `pipeline/odoo_migration/tests/test_odoo_smoke.py` (nuevo)
- `pipeline/odoo_migration/tests/fixtures/golden_slice.beancount` (nuevo)
- `_bmad-output/project-context.md` (modificado — nota de que el harness Odoo queda cubierto por el comando actual + smoke Tier B opt-in)
- `_bmad-output/implementation-artifacts/E1-0-scaffold-pipeline-migracion.md` (modificado — este registro)

## Change Log

- 2026-07-24 — E1.0 implementada: scaffold del pipeline de migración Odoo (paquete `pipeline/odoo_migration/`), helper de external IDs congelado + tests, fixture golden curado (5 naturalezas + USD forzado) + tests guardrail, smoke Docker Tier B opt-in verificado end-to-end. Tier A verde (19 tests), 0 regresiones de E1.0 en la suite backend. Status → review.
