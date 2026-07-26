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

## Piezas (E1.5) — loader idempotente hacia Odoo

La ÚNICA pieza que toca Odoo (winston §2.4). Dos capas a propósito (NFR3 —
el 90% de la lógica se testea sin infra):

- **`load.py`** (Tier A, Python puro) — el payload builder: convierte el
  output de la cadena (`collapse → sincerar → dimensionar`) + la tabla en
  payloads Odoo con su external ID cada uno. El **chart es el plan COLAPSADO**
  (una cuenta por `(company, odoo_account)`, 361 al corte; `code` = menor
  código Laudus origen en orden numérico) **+ las cuentas de ORIGEN SINCERADO**
  (`build_origin_accounts`: los destinos que E1.3 escribe al re-rutear —
  JuliusBaer, InvTecnion, … — 21 al corte, xmlid propio `accs_*`, marcadas
  `ORIGEN-SINCERADO`). Los xmlids congelados `acc_<company>_<code>` se emiten
  POR CÓDIGO: N alias → la misma cuenta (ir.model.data acepta N nombres al
  mismo res_id). **Cada línea rutea a la cuenta de su DESTINO
  (`line.odoo_account`, sinceramiento incluido), no al colapso de su código**
  (review E1.5, P1). Convención de signo: monto firmado == `debit − credit`;
  las patas no-CLP exigen `price` (contravalor = `amount × price` CUANTIZADO
  a precisión CLP, igual que Odoo al escribir) y llevan `currency_id` +
  `amount_currency`. Valida fail-loud: `otype` población cerrada (7 valores)
  y consistente por destino (cierra defers E1.2/E1.4), destino sin cuenta en
  el chart, move desbalanceado en CLP, je_id duplicado, colisión de slug.
- **`loader_rpc.py`** (Tier B) — cliente XML-RPC (stdlib, cero deps) +
  `load_all`: **upsert = skip-si-existe por xmlid** (namespace
  `ir.model.data.module = "__laudus__"`), create batcheado, `action_post`
  solo de lo recién creado, y **convergencia ante corridas interrumpidas**:
  lo creado sin xmlid (crash en la ventana create→register) se ADOPTA por
  clave natural (cuenta: code+cía; partner: nombre; analítica: nombre+plan;
  move: `x_laudus_je_id`+cía, re-verificando el contenido línea a línea) y
  los moves del payload que quedaron en draft se postean al final
  (`moves_reposted`). Re-correr NO duplica (FR11); correr / borrar la mitad /
  re-correr converge. **Prerequisitos que el loader se asegura a sí mismo (y
  reporta en los conteos):** grupo Analytic Accounting para su usuario RPC
  (`analytic_group_granted`, solo si falta) y activación de monedas del
  payload (`currencies_activated`). **Disciplina de re-corrida:** el loader
  es para cargas frescas o reanudación — si CAMBIAN los transformadores, lo
  ya cargado con xmlid no se re-sincroniza (skip): db nueva + carga completa.

```bash
# Tier B (opt-in, Docker): idempotencia probada sobre el golden (AC1–AC4)
PYTHONUTF8=1 venv/Scripts/python.exe -m pytest pipeline/odoo_migration/tests/test_loader_idempotente.py -m odoo -q

# CLI (default: golden slice contra el compose migration_e1 en :8070)
PYTHONUTF8=1 venv/Scripts/python.exe -m pipeline.odoo_migration.loader_rpc --db test_e15
```

⚠️ **El full load real** (`--ledger ledger/main.beancount`, al VPS) es una
corrida operativa **post-E1.6**: gates pendientes D-1 Latinoamericana
(veredicto Valentina) + VPS Hetzner + medir 1 año antes del full (winston §9).

## Piezas (E1.6) — verificación lado-Odoo (el gate de release)

El otro lado del espejo del loader: **`verify_odoo.py`** lee lo que quedó EN
Odoo y lo compara contra el mirror/cadena. **Tres planos, no uno** — la
lección P1 del review E1.5: el loader ruteaba 182 líneas a la cuenta
equivocada y la paridad por código daba 0 diffs igual (el código viaja
correcto aunque la cuenta esté mal). Por eso:

1. **Paridad ORIGEN (FR8)** — Σ `amount_currency` por `x_laudus_account_code`
   × moneda × compañía == mirror PURO (`parity.laudus_balances` tal cual, sin
   pasar por la cadena — un bug compartido no puede auto-validarse acá).
2. **Gate de DESTINO (FR12)** — Σ `balance` por cuenta Odoo REAL
   (`account_id`) == Σ(debit−credit) de los `MovePayload` (la MISMA fuente que
   el loader escribió, `accs_*` de origen sincerado incluidas). Este plano
   pesca el ruteo podrido que el plano 1 no ve.
3. **CONTEOS + invariantes (FR12b)** — identidades `(company, x_laudus_je_id)`
   exactas sin duplicados, N líneas, todo posteado, 0 líneas con `x_laudus_*`
   vacíos, y las líneas 211005 == exactamente las del payload (**derivado, no
   pinneado a 0**: en el full history sobreviven 2 patas sin par).

Columna por plano, explícito: origen agrega `amount_currency`; destino agrega
`balance` — columnas **almacenadas independientes** en Odoo 18. Las mutaciones
del Tier B tocan LA columna que su plano agrega (un `UPDATE … SET debit` no
movería ninguna de las dos y ningún plano lo vería).

- Lado esperado en Python puro (Tier A por-push); lado Odoo vía XML-RPC
  (`read_group` agrega server-side: el full history vuelve como ~570 códigos ×
  moneda, no 57k líneas). `ParityError` ahora lleva los diffs COMPLETOS como
  atributos (`origin_diffs`/`destination_diffs`/`count_diffs` — cierra el
  defer E1.2 de diffs programáticos).
- **Muestreo dirigido (FR12d)**: 20 asientos de mayor monto + 20 aleatorios
  con seed pinneada (`20260723` — misma selección en cada corrida, NFR1) →
  reporte markdown con la cuenta/partner/dims **leídos de Odoo** + anexo de
  cobertura de glosa (resúmenes de la cadena + histograma por-glosa de las
  patas MIXTO sin clasificar + listado sin-match E1.4). La FIRMA es humana
  (Ary/Valentina) — el CLI entrega el reporte.
- Tier B (`test_verify_odoo_tier_b.py`, `-m odoo`, db `test_e16`): carga el
  golden con el loader E1.5 → 0 diffs en los 3 planos → **mutaciones contra
  Odoo real** que prueban que el gate PUEDE fallar: `amount_currency` alterado
  (origen acusa), línea movida de cuenta (destino acusa y origen NO — el
  plano 2 existe por eso), move borrado (conteos acusan) — y reconverge con el
  loader.

```bash
# Tier B — gate de release (opt-in, Docker)
PYTHONUTF8=1 venv/Scripts/python.exe -m pytest pipeline/odoo_migration/tests/test_verify_odoo_tier_b.py -m odoo -q

# CLI del verificador (default: golden slice contra el compose migration_e1)
PYTHONUTF8=1 venv/Scripts/python.exe -m pipeline.odoo_migration.verify_odoo --db test_e16
# El full load usa el MISMO CLI, con --full (post-gates D-1 + VPS):
#   --ledger ledger/main.beancount --full
# --full declara que el ledger es el mirror COMPLETO al corte y convierte el
# pin FR12c del sinceramiento (Δ ingreso pre−post = −45.576.501.123) en GATE
# (exit 1 si no calza) — sin --full el Δ es solo informativo.
```

Además de los 3 planos Odoo, el CLI corre el gate **Tier A sobre el ledger
vivo** (`run_tier_a`: exclusiones por identidad + neteo a 0 del conjunto
excluido) — los planos 2/3 comparan payload↔Odoo (misma cadena en ambos
lados), así que una exclusión equivocada que netea a 0 por código solo la
pesca el gate del mirror.

⚠️ **E1 NO se cierra con el código verde**: quedan los gates humanos — el
sign-off AC5 de E1.4 (partición), la **firma del muestreo** (este reporte),
D-1 Latinoamericana y las preguntas 5-6 a Valentina — y el cierre de epic
requiere aprobación explícita de Ary.

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
