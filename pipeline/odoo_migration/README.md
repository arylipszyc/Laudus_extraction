# pipeline/odoo_migration — Migración Laudus (espejo Beancount) → Odoo

Scaffold de Epic **E1** (Fase 1a). Convierte el espejo crudo `ledger/main.beancount`
al modelo de Odoo 18. Este paquete es el **scaffold bloqueante (story E1.0)**: deja lista
la infra de desarrollo y verificación; la lógica de negocio la agregan E1.1→E1.6.

## Dos tiers de verificación (lección `tsc --noEmit`)

El gate por-commit tiene que ser **rápido, determinístico y el comando real del proyecto**
— no uno inventado que dé verde vacío.

| Tier | Qué | Cuándo | Cómo |
|------|-----|--------|------|
| **A** | `external_ids`, fixture golden (Python puro, sin Odoo) | por-commit | `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q` |
| **B** | Smoke Docker (levanta Odoo real) | gate de release, **opt-in** | `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest pipeline/odoo_migration -m odoo -q` |

El smoke (`test_odoo_smoke.py`) está marcado `@pytest.mark.odoo` y el `conftest.py` lo
**salta por defecto**: solo corre con `-m odoo` explícito. Así el harness por-commit no
depende de Docker.

## Piezas (E1.0)

- **`external_ids.py`** — external IDs determinísticos de Odoo. La columna vertebral de
  la idempotencia del loader (E1.5): re-correr hace upsert, no duplica. **El formato está
  congelado acá** (`acc_<company>_<code>`, `mv_<company>_<je_id>`, `aml_<company>_<je_id>_<n>`);
  no cambiarlo. Ver el docstring del módulo.
- **`tests/fixtures/golden_slice.beancount`** — slice **curado** (no un corte por fecha):
  cubre a propósito cada naturaleza de sinceramiento (retiro, aporte, traspaso, wash
  apertura/cierre, ambiguo) + ≥1 asiento **USD** (sintético — el mirror no tiene ningún
  posting en USD). Cada asiento anota su procedencia (id Laudus / glosa).
  `test_fixture_golden.py` es el guardrail: si alguien borra un caso, se pone rojo.

## Smoke Docker (Tier B) — cómo correrlo

Requiere Docker. Usa el compose del spike (`_spike-odoo/docker-compose.yml`, referenciado
—no duplicado—; E1.1 promoverá su propio compose cuando monte el addon custom real), pero
bajo un **project name aislado** (`migration_smoke`) para no tocar los volúmenes del stack
del spike.

```bash
PYTHONUTF8=1 venv/Scripts/python.exe -m pytest pipeline/odoo_migration -m odoo -q
```

Levanta Odoo 18 + Postgres 16, confirma que Odoo responde en `:8069`, hace scaffold +
`--stop-after-init -i` de un addon custom mínimo (prueba que el stack acepta instalar un
addon), y **siempre baja el stack** (`down -v` sobre su project aislado) al terminar. Es
lento (~2-3 min): por eso NO corre por-commit.

## Piezas (E1.2) — colapso del plan + verificador de paridad Tier A

Primer transformador real + el verificador que lo cuadra. Todo **Tier A** (Python
puro, sin Odoo, por-commit).

- **`mapping.py`** — acceso a la tabla de mapeo de Valentina
  (`_bmad-output/planning-artifacts/odoo-migracion/valentina-tabla-mapeo-odoo-2026-07-23.csv`).
  Key = `(entity, code)` — los códigos Laudus se repiten entre entidades. Valida al
  cargar: keys únicas (incl. `(company, code)`, que protege `acc_<company>_<code>`),
  todo código con destino. La única fila sin código (`Expenses:EAG:Suspense`, cuenta
  interna del proyecto) queda excluida del universo y pinneada en test.
- **`transform.py`** — el colapso 569→destino: mirror → `OdooMoveRecord`/`OdooLineRecord`
  neutrales. Cada línea lleva su cuenta Odoo destino según la tabla **y** el código
  Laudus origen (`laudus_code` → futuro `x_laudus_account_code`). Universo = solo
  transacciones `source: "laudus-erp"`. Fail-loud ante cuenta sin código, mapeo
  faltante o asiento sin `id`.
- **`parity.py`** — el verificador: paridad-**origen** (FR8: Σ por código origen ×
  moneda × compañía == mirror, 0 diffs), gate de **destino** (FR12a: Σ por cuenta
  destino == Σ de sus códigos origen según la tabla, cruzado contra el mirror) y
  **conteos** (FR12b: N moves/líneas preservados, con exclusiones **declaradas
  por identidad** vía `excluded_je_ids={(company, je_id), …}` — las usa E1.3
  para los washes auditados).

### El contrato de regresión (E1.3 / E1.4, leer esto)

El verificador **nace acá y es reusable**: la paridad-origen es invariante al
colapso y al sinceramiento (el código origen viaja en la línea). **Todo
transformador nuevo termina con esto en verde sobre el golden slice:**

```python
from pipeline.odoo_migration.parity import run_tier_a
run_tier_a(entries, moves, mapping)  # levanta ParityError con el detalle si descuadra
# Tras un transformador que excluye washes (E1.3+) o re-rutea destinos, las
# exclusiones se declaran por IDENTIDAD y el ruteo esperado se comparte:
run_tier_a(entries, moves, mapping, route=..., excluded_je_ids={(company, je_id), ...})
```

Los tests incluyen **mutaciones** (monto alterado, línea borrada, código/entidad
cambiados) que verifican que el gate SÍ se pone rojo — un verificador que no puede
fallar es `tsc --noEmit`.

```bash
PYTHONUTF8=1 venv/Scripts/python.exe -m pytest pipeline/odoo_migration -q
```

## Piezas (E1.3) — sinceramiento por naturaleza (0/A–H)

Segundo transformador de la cadena: `collapse → sincerar`. Todo **Tier A**.

- **`sincerar.py`** — reclasifica cada pata de INGRESO según la tabla-madre 0/A–H
  del inventario de Valentina (población cerrada; una cuenta de ingreso sin
  naturaleza revienta fuerte). A nivel pata: **B** retiros → activo de ORIGEN
  provisional (`ORIGEN_ASSETS`, cross-check de completitud vs la columna `sinc`
  de la tabla); **H** Jhonny → por-cobrar; **G** MIXTO → cascada por glosa
  (normalización + `valentina-tabla-alias-*.yaml`, word-boundary, homónimos
  vetan — NUNCA fuzzy); **D** queda marcada sin re-ruteo (P-2 abierta);
  **C/E** ya vienen ruteadas del colapso (solo se estampan). Los **washes**
  (Comprobante apertura/cierre + reversos Latinoamericana) se excluyen por
  **pares completos iguales-y-opuestos** con log auditable (`excluded_pairs`).
  Sin match = queda en Income + `sin clasificar` + reporte de cobertura —
  nunca descarte silencioso. Cada línea tocada lleva metadata reversible
  (`sinc_naturaleza`/`sinc_regla`/`sinc_flag`/`odoo_account_colapso`).
- **Exclusiones por IDENTIDAD** (upgrade de `parity.py`): `verify_counts`/
  `run_tier_a` reciben `excluded_je_ids={(company, je_id), …}` y verifican que
  exactamente esos moves faltan, ninguno más, y que el conjunto excluido
  **netea a 0 por código** — excluir el par equivocado o una pata suelta falla
  con alarma (un conteo ciego no puede pescarlo).
- **Gate FR12c** (`test_sinceramiento_full_mirror.py`): la cadena completa
  sobre TODO el mirror (16.633 asientos, <2s) con las cifras del inventario
  pinneadas al peso — Sade **+4.876.249.792**, Molco FFCC **+2.895.757.384**,
  ingreso −84.825.124.241 → −39.248.623.118 (Δ −45.576.501.123). El mirror es
  un archivo vivo: el test corta a la fecha del inventario (2026-07-23) para
  que la historia pinneada no se mueva con syncs futuros.

## Piezas (E1.4) — dimensiones analíticas + partners

Tercer transformador de la cadena: `collapse → sincerar → dimensionar`. Todo
**Tier A**. Agrega el "quién" (partner) y el "sobre qué" (dimensiones) como
**METADATA por línea** — no cambia cuentas, ni montos, ni el set de moves: el
**contrato de regresión no cambia de firma**, `run_tier_a` corre tras
`dimensionar` con los MISMOS `route`/`excluded_je_ids` de E1.3 y da idéntico.

- **`dimensionar.py`** — `dimensionar(moves, mapping, alias_table) ->
  DimensionadoResult` (función pura, mismo patrón de `sincerar`). Dos
  mecanismos (winston §5.2): **PARTICIÓN** (socio-dueño sobre 115xxx FFCC —
  el partner ledger debe cuadrar al peso, es el "Resumen Retiros") y
  **DISPERSO** (deudores/donaciones/clubes/beneficiarios/socio-disperso +
  los planes analíticos — agrupa, NUNCA se le exige sumar 100%, AC3).
  - Partner por CUENTA: tabla `PARTNER_CANONICO` (los 48 valores reales de la
    columna `partner`, población cerrada + snapshot pinneado) + pins por
    `(entity, code)` (Jhonny 310045/310047, Raquel T/C 430019) + columna
    `socio` → socio-disperso (mismo canónico que la partición, sin duplicar).
  - Dims por columna, verbatim: `prop`→propiedad_objeto, `area`→area_centro
    (salvo el marcador `por-cuenta-de` → plan por_cuenta_de), `offshore`→
    offshore_vehiculo. Entidad = `line.entity` (ya viaja; E1.5 la convierte).
  - Reglas por glosa ACOTADAS (`resolve_alias`, sección `personas` del YAML,
    nombre completo + word-boundary + homónimos vetan — el nombre completo
    gana sobre su propio substring excluido): beneficiarios en gasto (caso
    Raquel) y socio-USO en retiros (plan socio_uso). Duda → sin estampar +
    reporte (`sin_match`: mencionado-pero-no-resuelto ≠ no-mencionado).
  - Buckets dudosos (Deudores Varios por entidad, Donaciones varias, CIS×3,
    Otros hijos, Israel) = placeholder + `revisar con contadoras` (AC4).
- **`verify_particion(entries, moves)`** — el gate NUEVO: Σ(patas por partner
  de partición, por moneda) == Σ del mirror crudo para sus códigos 115xxx.
  Se verifica por PARTNER, no por cuenta destino (115028 mapea a `Cuentas por
  cobrar` y cuadra igual por DAG). Al corte 2026-07-23 los 11 saldos dieron
  EXACTOS contra la lista independiente de Valentina, al peso.
- **Gate full-mirror** (`test_dimensionado_full_mirror.py`): partición verde +
  anchors pinneados + cobertura pinneada (67 sin-match listados para sign-off,
  264 a revisar) + invariante estructural + tests de mutación (el gate puede
  fallar). La carga del mirror es compartida (`conftest.full_mirror_chain`).

## Piezas (E1.1) — el módulo Odoo `x_laudus_migration`

- **`addons/x_laudus_migration/`** — módulo addon de verdad (versionado, NO Studio). La
  **estructura receptora** de la migración dentro de Odoo:
  - Campos custom (`_inherit`) de trazabilidad al origen Laudus: `x_laudus_account_code`
    / `x_laudus_je_id` / `x_laudus_entity` en `account.move.line` (los 3 **indexados** —
    la paridad de E1.6 agrupa por `x_laudus_account_code`); `x_laudus_group` en
    `account.account`; `x_laudus_je_id` en `account.move`.
  - `data/analytic_plans.xml` — los **6 planes analíticos** (solo contenedores; los
    valores los crea E1.4).
  - `hooks.py` (`post_init_hook`) — crea las 2 compañías (**EAG** / **RUT2**) sin
    `l10n_cl` + un diario "Diario Laudus" por compañía. **Cancela** la auto-carga del CoA
    genérico que `account` programa para la compañía principal (el diseño quiere plan
    Laudus-puro; además ese load borraría el diario recién creado — ver comentario en el hook).
- **`docker-compose.yml` + `odoo.conf`** (raíz del paquete) — compose **propio** de la
  migración (puerto 8070, project aislado `migration_e1`), monta `./addons`. Resuelve el
  defer de E1.0 (el smoke ya no escribe en el `_spike-odoo/addons` compartido). El
  `odoo.conf` es necesario para que `docker compose exec odoo …` conozca el host de la db
  (no pasa por el entrypoint).

### Verificar E1.1 (Tier B, opt-in)

```bash
PYTHONUTF8=1 venv/Scripts/python.exe -m pytest pipeline/odoo_migration/tests/test_x_laudus_migration_install.py -m odoo -q
```

Instala `x_laudus_migration` en una db fresca y verifica por SQL: los 5 campos + sus
índices, 6 planes analíticos, 2 diarios (LAU1/LAU2), 2 compañías sin `l10n_cl`. ~40s.
