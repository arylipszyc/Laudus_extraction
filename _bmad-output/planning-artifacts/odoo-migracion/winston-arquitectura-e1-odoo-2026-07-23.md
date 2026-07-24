# Arquitectura — Epic E1: Carga de la historia Laudus en Odoo (espejo corregido y estructurado)

**Autor:** Winston (Arquitecto) · **Fecha:** 2026-07-23 · **Estado:** ✅ **APROBADO por Ary (resumen ejecutivo §0), 2026-07-24.** El detalle técnico queda auto-aprobado según `project-context.md`.

> **⚠️ Nota de estructura (2026-07-24) — leer antes de usar §8:** el desglose de stories vive en `epics.md`
> y es la **autoridad**. Tras la mesa redonda 2026-07-23, la estructura se revisó respecto de la secuencia
> §8 de este documento: (a) se **agregó E1.0** (scaffold + fixture golden con caso USD + helper de external
> IDs) como story-0 bloqueante — no aparece en §8; (b) el **patrimonio salió de E1**: lo que §8 lista como
> **E1.7 (activos de patrimonio a costo + reporte v1) es ahora Epic E1B**, hermano de E1 y fuera del gate de
> paridad, para dejar el gate del espejo inmaculado. **No construir patrimonio dentro de E1.** El resto de §8
> (E1.1→E1.6) sigue vigente.
**Insumos:** los 6 artefactos de Valentina (brief, spec, mapa de normalización, tabla CSV, resumen, generador).
**Precede a:** desglose de stories de E1. **No es construcción todavía.**

---

## 0. Resumen ejecutivo (esto es lo que necesito que me confirmes, Ary)

Vamos a cargar **toda la historia de Laudus en Odoo** (2021→hoy), corregida y estructurada, **sin re-hacer
el trabajo contable que ya existe**. La pieza central de la decisión:

> **La corrección NO se re-implementa dentro de Odoo, ni se hornea un segundo ledger Beancount "corregido".
> Se escribe UNA sola función de transformación en Python (que extiende el generador que Valentina ya
> escribió), que lee el espejo Beancount confiable + la tabla de mapeo, aplica las reglas de sinceramiento,
> y carga Odoo directo. Odoo queda como destino "tonto"; la inteligencia vive en un solo lugar, testeado
> con el mismo pytest del proyecto.**

**Por qué (en simple):** el espejo Beancount de hoy ya cuadra al peso contra Laudus y es la base de toda
la reportería que ya construimos. Si metiéramos la lógica dentro de Odoo, o creáramos un segundo ledger
"corregido", tendríamos dos verdades que mantener y que se van a desincronizar. Un solo transformador,
afuera, testeable, que se puede volver a correr cuando haga falta.

**Las 6 decisiones, resueltas:**

| # | Decisión | Resolución |
|---|---|---|
| 1 | ¿Dónde vive la corrección? | **Transformador externo en Python** (extiende el generador), lee el espejo Beancount + tabla, carga Odoo vía `odoo shell`/XML-RPC. Ni Odoo ni un 2º Beancount. |
| 2 | Estructura de compañías | **2 `res.company`: EAG (RUT1, +hijas) y RUT2 (FFCC+JAB).** Entidad interna (hijas / FFCC / JAB) = dimensión, no compañía. (Ya cerrado por vos + Valentina; lo arquitecturo.) |
| 3 | Campos custom | Módulo Odoo propio `x_laudus_migration` con `x_laudus_account_code`, `x_laudus_je_id`, `x_laudus_entity` **en la línea** (`account.move.line`), indexados. |
| 4 | Dimensiones + partners | **6 planes analíticos** (dispersos) para propiedad/área/offshore/por-cuenta-de/socio-uso/entidad + **`res.partner`** para socio-dueño/deudores/donaciones/beneficiarios (partición y saldo por persona). |
| 5 | Verificación de paridad | Script externo: `Σ(líneas Odoo por x_laudus_account_code, por moneda) == saldo cuenta Laudus`. Gate DoD = **0 diffs** en los 569 códigos, ambas compañías, toda la historia. |
| 6 | Odoo Community sin `l10n_cl` | **Odoo 18 Community**, compañías creadas **sin localización fiscal**; plan Laudus-puro cargado por el importador. OCA `account-financial-reporting` para reportes. |

**Costo:** cero licencia (Community es gratis). Corre en el **mismo VPS Hetzner+Docker** que ya estás
levantando para el spike — no hay costo recurrente nuevo más allá de ese VPS. **No es un gate nuevo de costo.**

**Lo que te pido:** confirmá que este resultado (carga histórica honesta y estructurada en Odoo, un solo
transformador afuera, paridad al peso como gate) es lo que querías. El detalle técnico de abajo lo auto-apruebo
según `project-context.md`; solo necesito tu OK al resumen.

---

## 1. Contexto y restricciones que mandan el diseño

**Lo que YA existe y hay que respetar (no reinventar):**

- **Espejo Beancount confiable** en `ledger/` — mirror fiel de Laudus (EAG+hijas y RUT2=FFCC/JAB),
  reconciliado al peso (RUT2: 0 diffs / 237 cuentas, story 12.5). Es la **fuente de verdad de la historia**.
  Toda la reportería (Epic 9/10), la conciliación de TC (Epic 6) y los crons de sync leen de acá.
- **Generador determinístico** (`valentina-tabla-mapeo-generador-2026-07-23.py`) — ya lee `ledger/main.beancount`
  y produce la tabla de mapeo 569→336 + dimensiones + sinceramiento. **Es el seed del importador; no se reescribe.**
- **Spike Odoo probado** — `_spike-odoo/` cargó 1 mes (EAG+RUT2) vía `odoo shell` (`import_to_odoo.py`) con
  cuentas + diario + asientos posteados y validación de total de gastos. **Odoo 18 Community**, Postgres 16,
  OCA `account-financial-reporting` 18.0 para reportes. El camino técnico está validado a pequeña escala.

**Las restricciones no negociables (de Valentina/Ary):**

1. **Paridad al peso** contra Laudus (la disciplina del proyecto). Es el gate de aceptación de E1.
2. **Plan Laudus puro** — sin el árbol `l10n_cl` del SII auto-instalado.
3. **Sinceramiento determinístico** — mismo input, mismo output; nada a mano; auditable y reversible.
4. **Trazabilidad al origen** — cada línea Odoo sabe de qué código Laudus vino, aunque el plan colapse.

**La tensión central que resuelve la arquitectura:** el **colapso** (569→336 cuentas + dimensiones) y el
**sinceramiento** (ingreso→activo) *rompen* la correspondencia 1:1 cuenta-Odoo ↔ cuenta-Laudus. Si la paridad
se verificara a nivel de cuenta Odoo, no cuadraría nunca. La solución (de Valentina, §5 del mapa, correcta):
**la paridad se verifica a nivel de LÍNEA, agrupando por el código Laudus original estampado en cada línea.**
Todo el diseño gira alrededor de preservar ese código.

---

## 2. Decisión #1 (la clave) — Dónde vive la corrección

### 2.1 Las tres opciones reales

El brief lo plantea como binario ("desde Beancount corregido" vs "reimplementar en Odoo"), pero hay **tres**
opciones, y la trampa está en que **el Beancount "corregido" no existe** — el espejo de hoy es el mirror
*crudo*. Las correcciones viven solo como reglas (en el generador), sin aplicar. Entonces:

| Opción | Qué es | Veredicto |
|---|---|---|
| **A — Hornear un 2º Beancount corregido** | Aplicar sinceramiento+colapso al ledger, generar `ledger-corregido/`, y Odoo espeja *eso*. | ❌ **Descartada.** Crea una 2ª fuente de verdad que se desincroniza del mirror crudo reconciliado del que depende TODO el stack (reportería, TC, sync). Y las dimensiones (analítica, partner, partición) son conceptos **nativos de Odoo**; expresarlos en Beancount para re-exportarlos es un round-trip con pérdida. |
| **B — Reimplementar la corrección DENTRO de Odoo** | Reglas de sinceramiento como server-actions/ORM en Odoo; el import trae crudo y Odoo corrige. | ❌ **Descartada.** Las reglas YA están escritas como Python-sobre-Beancount (el generador). Reimplementarlas dentro de Odoo tira ese trabajo, mete lógica de negocio en un lugar difícil de testear/versionar, y rompe la disciplina pytest del proyecto. |
| **C — Un transformador externo único (RECOMENDADA)** | Una función Python que **extiende el generador**: lee el mirror crudo confiable + la tabla, aplica sinceramiento (SPEC §3) y colapso, y emite registros Odoo. Odoo = destino tonto. | ✅ **Elegida.** Un solo lugar de lógica, testeable afuera con pytest, idempotente, re-corrible. No forka el ledger. No mete lógica en Odoo. Reusa el seed que ya existe. |

### 2.2 Por qué C (el "por qué" en simple)

- **Una sola verdad de la historia.** El mirror crudo sigue siendo el único ledger; nadie más que E1 lo
  transforma. No hay un segundo ledger que mantener cuadrado.
- **La inteligencia en un solo lugar, testeable.** El transformador es Python puro, corre con
  `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest` como todo el proyecto. Odoo no tiene lógica de negocio
  que testear por separado.
- **Idempotente y re-corrible** — clave para la decisión §5 del brief (si las contadoras siguen en Laudus,
  el mismo transformador re-corre en cada refresh). Ver §7.
- **Reusa, no reinventa.** El generador ya expresa las reglas. E1 lo promueve de "genera un CSV de mapeo" a
  "genera los artefactos de carga de Odoo". Rule of Three: no abstraemos nada nuevo, extendemos lo probado.

### 2.3 Cómo llega a Odoo — el mecanismo de carga

El spike probó dos caminos; elijo el robusto:

- **Descartado: import CSV por la UI** (`base_import`). Frágil a escala: el formato o2m de asientos, el orden
  de las filas, los external IDs y las dimensiones se rompen con 5 años × 2 compañías × ~100k+ líneas.
- **Elegido: loader programático vía `odoo shell` / XML-RPC** (como `import_to_odoo.py` del spike, endurecido).
  Con **external IDs determinísticos** (`acc_<company>_<code>`, `mv_<company>_<je_id>`, `aml_<...>`) para que
  **re-correr haga upsert, no duplicados**. Esa es la columna vertebral de la idempotencia.

### 2.4 El pipeline de datos de E1 (una imagen)

```
  Laudus (ERP)                        [NO se toca]
      │  (sync existente, ya construido)
      ▼
  ledger/  (espejo Beancount CRUDO)   [fuente de verdad, reconciliado al peso]
      │
      │   ┌─────────────────────────────────────────────────────────────┐
      │   │  TRANSFORMADOR E1  (Python, extiende el generador)           │
      └──▶│  1. lee entries del mirror + tabla de mapeo                  │
          │  2. colapso: cuenta Laudus → cuenta Odoo (+ dims + partner)  │
          │  3. sinceramiento por naturaleza (SPEC §3, por-cuenta+glosa) │
          │  4. estampa x_laudus_account_code / je_id / entity en c/línea│
          │  5. emite plan de cuentas + asientos + dims + partners       │
          └──────────────────────────┬──────────────────────────────────┘
                                      │  (external IDs determinísticos → upsert)
                                      ▼
                        LOADER  (odoo shell / XML-RPC)
                                      │
                                      ▼
                           Odoo 18 Community  (2 compañías)
                                      │
                                      ▼
                  VERIFICADOR DE PARIDAD  (Σ por x_laudus_account_code)
                                      │
                                      ▼
                          Gate E1: 0 diffs al peso ✓
```

**Nota de honestidad arquitectónica:** el transformador y el loader se separan a propósito. El transformador
es Python-puro-sobre-Beancount, testeable sin Odoo levantado (rápido, en CI/pytest). El loader es el único que
toca Odoo (lento, requiere el contenedor). Así el 90% de la lógica se testea sin depender de la infra.

---

## 3. Decisión #2 — Estructura de compañías y entidad

**Ya cerrado (mapa §6); acá lo arquitecturo:**

- **`res.company` EAG** (RUT1) — incluye las 4 hijas (Jocelyn/Jeannette/Johanna/Jael).
- **`res.company` RUT2** — incluye FFCC y JAB/FGK.
- **Entidad interna** (hijas dentro de EAG; FFCC/JAB dentro de RUT2) = **dimensión**, NO compañía.

**Por qué (en simple):** JAB/FGK no es una entidad autónoma (FFCC le paga los gastos; no tiene patrimonio
propio). Hacerla compañía forzaría un asiento inter-compañía en cada gasto. La "vista de 3" (EAG/FFCC/JAB) se
logra como **reporte por dimensión**, no como estructura legal.

**Cómo se implementa la entidad (doble registro, a propósito):**

1. **`x_laudus_entity`** (campo custom en la línea) — para la **paridad** y trazabilidad. Valor: `EAG`,
   `Jocelyn`, `Jeannette`, `Johanna`, `Jael`, `FFCC`, `JAB`.
2. **Plan analítico "Entidad"** (cuenta analítica) — para **filtrar/reportar** ("consolidado EAG+hijas",
   "solo FFCC"). Es la dimensión que reemplaza el corte manual de hoy.

**Plan de cuentas: por compañía, no compartido.** Los códigos Laudus ya son únicos por entidad (el dígito de
entidad los separa), pero para mantener el modelo simple y alineado con el spike, **cada compañía tiene sus
cuentas** (`company_ids` apuntando a una sola company, como en el spike). No forzamos chart compartido — Rule
of Three: no hay tercer caso que lo justifique.

**Consolidación (limitación de Community, a declarar):** Odoo Community **no** trae el módulo de consolidación
(es Enterprise). El "consolidado EAG+hijas" y cualquier vista cruzada de las 2 compañías se resuelven en la
**capa de reporte** — vía la dimensión Entidad + la vista multi-compañía de asientos de Odoo, o reusando el
stack de reportería Beancount que ya existe. Para Fase 1 (patrimonio v1) alcanza con reportes sobre las líneas
+ dimensiones. **No es un bloqueante; es una decisión de dónde vive el reporte, y ya tenemos herramienta.**

---

## 4. Decisión #3 — Campos custom para la paridad

**Módulo Odoo propio, versionado en git: `x_laudus_migration`** (NO Studio — un módulo de verdad se versiona,
se despliega y se testea; Studio guarda los campos en la base y se pierde la trazabilidad).

**Campos declarados:**

| Modelo | Campo | Tipo | Índice | Para qué |
|---|---|---|---|---|
| `account.move.line` | `x_laudus_account_code` | Char | **Sí** | **La llave de paridad.** El código Laudus ORIGINAL, aunque la cuenta Odoo haya colapsado o el sinceramiento la haya movido. |
| `account.move.line` | `x_laudus_je_id` | Char | Sí | El `id`/`je_num` del asiento Laudus. Idempotencia + deep-link al origen. |
| `account.move.line` | `x_laudus_entity` | Char | Sí | Entidad (EAG/hijas/FFCC/JAB) para paridad y corte. |
| `account.account` | `x_laudus_group` | Char | — | El path `categoria1/2/3` de Laudus (contexto, no paridad). |
| `account.move` | `x_laudus_je_id` | Char | Sí | El id del asiento a nivel cabecera (upsert del move). |

**El punto crítico a entender (el que hace que todo cuadre):**

> **`account.account.code` = la cuenta Odoo COLAPSADA (nueva, limpia).**
> **`x_laudus_account_code` (en la línea) = el código Laudus ORIGINAL.**
> Muchos códigos Laudus → una cuenta Odoo, pero **cada línea conserva su código de origen**.
> La paridad NO se verifica por cuenta Odoo; se verifica **agrupando por `x_laudus_account_code`.**

**Por qué se indexa `x_laudus_account_code`:** el verificador hace `GROUP BY x_laudus_account_code` sobre
~100k+ líneas de 5 años. Sin índice, el gate de paridad se arrastra. Es la query más caliente del sistema.

---

## 5. Decisión #4 — Dimensiones analíticas + partners

**El principio (de Valentina, mapa §2): personas = partner; propiedad/área/objeto = analítica.** El diseño
respeta la distinción **partición vs disperso** del SPEC §5, porque **calza 1:1 con dos mecanismos nativos
distintos de Odoo**:

- **PARTICIÓN → partner ledger sobre cuenta de balance.** Suma exacta por persona, nativo, **reconcilia**.
- **DISPERSO → plan analítico sobre P&L.** Etiqueta parcial, filtra/agrupa, **no se le exige sumar 100%**.

**Meter una dispersa donde se espera partición es lo que descuadra los reportes** (SPEC §5.1). Por eso cada
dimensión declara su tipo *antes* de construir, y el tipo dicta el mecanismo Odoo.

### 5.1 Los 6 planes analíticos (dispersos)

`account.analytic.plan` + `account.analytic.account`; se estampan en `analytic_distribution` de la línea.

| Plan analítico | Valores (del CSV) | Se deriva de | Tipo |
|---|---|---|---|
| **Propiedad / objeto** | Vía Gris, Reñaca, Molco, Miami, Golf, Yates (Keiki Kai/Destiny/Alfín II), Aviones (N225AW/N266WW/AJK/grl) | `categoria3` de JAB + glosa | Disperso |
| **Área / centro** | Oficina, Gerencia, Vehículos, Salud, Cuentas Básicas… | `categoria3` de EAG/FFCC | Disperso |
| **Offshore / vehículo** | Leo, Tauro, MBI, Tecnión, Hemanext, W&M, FIP, FM BCI, Sade… | cuentas 111012/113021 + glosa | Disperso |
| **Por cuenta de** | FGK, JAB | `ControlYLiquidación` + PAT 0858 | Disperso |
| **Socio-uso** | AAG, EAG, DAG (quien USÓ el activo) | glosa de retiros de uso ("Vuelo X Hrs→RetirosDag") | Disperso |
| **Entidad** | EAG, Jocelyn, Jeannette, Johanna, Jael, FFCC, JAB | `x_laudus_entity` | Disperso (corte) |

### 5.2 Partners (`res.partner`) — el "quién"

| Uso | Cuenta Odoo | Tipo | Reconciliación |
|---|---|---|---|
| **Socio-dueño** (AAG/EAG/DAG/AZBA/SAG/FGK + apellidos) | `Cuentas corriente socios` (balance, receivable/payable) | **PARTICIÓN** | **Debe cuadrar al peso** con las cuentas 115xxx. El partner ledger ES el "Resúmen Retiros" que hoy se hace a mano. |
| **Deudores / préstamos** (Johnny Guerra, Deudores Varios) | `Préstamos/Deudores a terceros` (balance) | Partición local | Saldo por deudor nativo |
| **Donaciones / clubes / membresías** | `Donaciones` / `Cuotas y Membresías` (gasto) | Disperso | Agrupa por institución |
| **Beneficiario** (Raquel, Deutsch, Gloria) | cuenta de gasto por naturaleza | Disperso | **Solo P&L, sin posición de balance** (mapa §3.1) |

**La sutileza de "socio" (a propósito, dos mecanismos):** socio-**dueño** (partición, partner, sobre 115xxx,
reconcilia) es distinto de socio-**uso** (disperso, analítica, sobre uso de activos, no reconcilia). No se
mezclan. El SPEC §5.2 lo pide explícito y el diseño lo respeta.

**Por qué partner y no analítica para personas (en simple):** los analíticos de Odoo son de resultado (P&L);
no te dan saldo en cuentas de balance. El partner ledger sí — te da "cuánto le debe el fondo a AAG" nativo,
que es justo lo que la partición socio-dueño tiene que cuadrar.

### 5.3 Activos nuevos (patrimonio + orígenes) — fuera de la paridad Laudus, a propósito

Dos clases de cuentas nuevas (no existen en Laudus, no tienen código origen):

1. **Orígenes de inversión** (`Assets:EAG:InvTecnion`, etc., SPEC §1.2) — reciben las líneas que el
   sinceramiento saca del ingreso. **Esas líneas SÍ llevan el código Laudus del ingreso drenado**
   (`RetirosTecnin-310013`), así que **siguen dentro de la paridad** (agrupan por el código origen). El saldo
   del activo nuevo = Σ de las líneas movidas. Van a quedar negativos/provisionales — esperado (SPEC §3.3).
2. **Patrimonio a costo** (yate/avión/casas, SPEC §1.3) — asientos de **apertura nuevos** contra
   `Equity:Apertura`, con **participación** (⅓, no 100%). **NO tienen código Laudus → quedan FUERA del check
   de paridad por diseño.** Son estructura de capital nueva, no historia Laudus. Se verifican aparte: un set
   chico (~12 cuentas), montos conocidos (avión USD 2,27M, yate por participación), revisado a mano.

**Regla de paridad, precisa:** el gate `Σ por x_laudus_account_code` cubre **todo lo que vino de Laudus**
(incluido lo sincerado). Los asientos de apertura de patrimonio son un conjunto separado, pequeño y
verificado manualmente. **Dos gates, no uno**, y hay que decirlo claro para que nadie crea que un descuadre
del patrimonio-nuevo es un bug de la carga.

---

## 6. Decisión #5 — Mecanismo de verificación de paridad

**El gate de aceptación de E1.** Script externo (Python, vía XML-RPC o leyendo el Postgres de Odoo directo),
que corre en 3 pasos:

```
1. LADO LAUDUS (verdad):  del mirror Beancount, Σ(units.number) por (código Laudus, moneda).
   [el generador ya hace bal[account] += units.number — se reusa]

2. LADO ODOO:  SELECT x_laudus_account_code, currency, SUM(debit - credit)
               FROM account_move_line GROUP BY x_laudus_account_code, currency

3. DIFF:  para cada (código, moneda) → |lado_laudus - lado_odoo| debe ser 0.
```

**Por qué cuadra aunque haya colapso Y sinceramiento (la elegancia del diseño):** el check agrupa por el
**código origen preservado en la línea**, no por la cuenta Odoo. El colapso cambia `account_id` pero no
`x_laudus_account_code`. El sinceramiento cambia `account_id` (ingreso→activo) pero tampoco toca el código
origen. Entonces **el check es invariante bajo las dos transformaciones** — valida automáticamente que ni el
colapso ni el sinceramiento perdieron o crearon un peso.

**Convención de signo (para que el diff dé 0):** cada línea Laudus → una línea Odoo con el mismo monto firmado.
Beancount guarda el número firmado (activo/gasto +, ingreso/pasivo/equity −); Odoo `debit - credit` reproduce
ese signo. Por eso `Σ(debit-credit)` por código == `Σ(units.number)` por cuenta Laudus, exacto.

**Multi-moneda (CLP y USD):** el check corre **por moneda**. Las líneas USD llevan `currency_id=USD` +
`amount_currency` (USD) + `debit/credit` en CLP al precio registrado (de `prices.beancount`). La paridad se
mide en la **misma base que Valentina** (ella sumó solo CLP en el generador): CLP contra CLP, USD contra USD,
por separado. IAS 21 / revalúo es Fase 3 — en E1 se carga el USD **nominal** tal cual está registrado.

**Caso de test obligatorio — washes de apertura/cierre:** el sinceramiento excluye los pares
"comprobante de apertura/cierre" iguales-y-opuestos (SPEC §3.2 paso 1). Como el par netea a 0, excluir ambas
patas **no cambia** el saldo del código → la paridad se mantiene. Hay que testearlo explícitamente (excluir
solo pares completos; nunca una pata suelta).

**El gate:** 0 diffs en los 569 códigos × moneda, ambas compañías, toda la historia. Misma disciplina que
la reconciliación RUT2 (12.5: 0 diffs / 237 cuentas). Se corre en CI y como paso final del loader.

---

## 6·B. Robustez del transformador ante glosas inconsistentes (data tipeada a mano)

**Preocupación de Ary (2026-07-23, correcta):** la data de Laudus la tipean a mano las contadoras, así que la
**glosa** (`desc`) del asiento no es consistente — la misma entidad aparece escrita de varias formas
("Señora Raquel" / "Raquel Ventura" / "esposa EAG") y hay errores de ortografía. Reglas determinísticas sobre
glosa libre son frágiles.

**Verificado en la data real** (grep sobre el ledger, 2026-07-23):

| Grafía en glosas | Nº | Qué es |
|---|---|---|
| `Tecnion` | 465 | vehículo de inversión Tecnión |
| `Tecnin` | 104 | **el mismo** Tecnión, otra grafía → *matches perdidos* |
| `tecnica` / `tecnico` | 67 | *"servicio técnico"* — **NO es Tecnión** → *falso positivo* de un regex ingenuo |

La preocupación tiene las **dos caras** y las dos están en la data: (1) misma entidad, distinta grafía →
matches perdidos; (2) distinta entidad, grafía parecida → falsos positivos.

### 6·B.1 Por qué el blast radius es acotado — estructura primero, glosa último

El diseño de Valentina (SPEC §3.1, mapa §1) **minimiza a propósito** la dependencia de la glosa: lee primero
metadata **estructurada** (código de cuenta, `categoria2/3`, prefijo del nombre) y cae a la glosa **solo** para
las cuentas genuinamente sin estructura.

- **El grueso keyea en el CÓDIGO, no en la glosa.** Tecnión el vehículo vive en `RetirosTecnin-310013`; el
  sinceramiento retiro→activo keyea en **310013**, inmune a cómo se deletree "Tecnin/Tecnion" en el nombre o
  la glosa (de hecho el nombre de cuenta ya trae el typo congelado — 7 "Tecnin" vs 2 "Tecnion" — y da igual,
  porque agrupamos por código).
- **La glosa es load-bearing solo en una minoría:** las 3 cuentas `OtrosIngresos-310099` (el cajón de sastre,
  ~1,8B, grupo G MIXTO) + algunos tags dispersos (beneficiario Raquel; socio-uso "Vuelo X Hrs→RetirosDag").
  Ahí es donde se concentra el trabajo de robustez; el resto (colapso por código+cat3, socio-dueño por 115xxx,
  allowlist por código) no toca glosa.

### 6·B.2 Las dos garantías que hacen esto seguro aunque el matching falle

1. **La plata nunca se descuadra, pase lo que pase con la glosa.** La paridad keyea en `x_laudus_account_code`,
   no en la glosa. Una línea mal-clasificada por glosa **igual carga su código origen** → el gate de 0 diffs
   se cumple. Una glosa mal interpretada solo degrada la **analítica** (un gasto de Raquel sin taggear), nunca
   el cuadre al peso.
2. **Sin match ≠ mal clasificado. Sin match = marcado para revisión, nunca en silencio** (SPEC §3.2 paso 4,
   disciplina del desglose TC). El transformador matchea lo inequívoco; lo demás queda en su lugar + flag
   "sin clasificar". Nunca adivina-y-reza.

### 6·B.3 El tooling correcto (y lo que NO se usa)

- **NO fuzzy / distancia de strings como decisor.** El caso "técnico vs Tecnión" muestra por qué: falsos
  positivos impredecibles. Para un conjunto **cerrado y conocido** (6 socios, Raquel, Deutsch, Gloria, los
  vehículos Leo/Tauro/Tecnión/MBI…), lo correcto es una **tabla de alias explícita** — data versionada y
  auditable: `{"señora raquel","raquel ventura","esposa eag","sra raquel"} → beneficiario:Raquel`. Boring
  technology: un lookup sobre un set cerrado, no ML.
- **Normalización antes de matchear:** minúsculas, sin tildes, espacios colapsados (el generador ya hace
  `name.lower()` + `norm()`; se extiende con `unidecode` y la tabla de alias).
- **Reporte de cobertura + regenerar (loop de convergencia):** cada corrida emite (a) glosas que no matchearon
  ningún alias, (b) histograma por-glosa de las cuentas MIXTO. Valentina/contadoras revisan → agregan alias →
  regeneran (idempotente). En 2-3 pasadas converge. Igual que las cuentas TC sin mapear (Suspense + review).
- **Fuzzy solo como *sugeridor* en la cola de revisión** — "'tecnon' se parece 90% a 'tecnion', ¿alias?" — un
  humano confirma. La máquina nunca auto-aplica; la tabla de alias es la fuente de verdad determinística.

### 6·B.4 Impacto en los componentes

- **E1.3/E1.4** incorporan la **tabla de alias** (`aliases.yaml` versionado) + normalización como paso previo
  a toda regla que lea glosa.
- **E1.6 (verificador)** emite además el **reporte de cobertura de glosa** (no-matcheados + histograma MIXTO)
  como salida de cada corrida — es el insumo del loop de convergencia, no un extra opcional.
- **Métrica de aceptación (analítica, distinta del gate de paridad):** % de líneas de las cuentas MIXTO y de
  los tags dispersos que quedan clasificadas vs "sin clasificar". No se exige 100% (regla 80/20 del proyecto);
  se exige que **lo no clasificado esté visible y sea revisable**, nunca perdido.

---

## 7. Decisión #6 — Odoo Community sin `l10n_cl` + idempotencia + ongoing

### 7.1 Stack (del spike, se pinea — boring technology)

- **Odoo 18 Community** + **Postgres 16**, Docker Compose, en el VPS Hetzner del runbook del spike.
- **OCA `account-financial-reporting` 18.0** en `addons/` para los reportes financieros (balance,
  mayor, etc.) sin necesidad de Enterprise.
- **Módulo propio `x_laudus_migration`** en `addons/` — campos custom (§4), planes analíticos seed (§5),
  diarios, y opcionalmente la acción de servidor de paridad.

### 7.2 Sin plan chileno auto-instalado

- Las compañías se crean **sin localización fiscal** (no se instala `l10n_cl`). El spike ya demostró que se
  pueden crear `account.account` directo por ORM **sin** una plantilla de CoA — no hace falta el árbol del SII.
- Si algún módulo llegara a exigir un CoA mínimo para operar, se instala `l10n_generic_coa` (genérico) y se
  **archivan** sus cuentas; encima se carga el plan Laudus-puro. La contabilidad familiar no declara IVA ni
  renta por acá; no necesita el árbol del SII.

### 7.3 Idempotencia y el caso "ongoing" (§5 del brief)

Todo el loader usa **external IDs determinísticos** derivados de los ids Laudus:

- Cuenta: `acc_<company>_<laudus_code>` · Asiento: `mv_<company>_<je_id>` · Línea: `aml_<company>_<je_id>_<n>`.

Con eso, **re-correr el loader hace upsert, no duplica** — la base de la idempotencia. Esto habilita el caso
del brief §5 sin decidirlo ahora:

- **Opción B (contadoras trabajan en Odoo):** E1 es una **migración de una sola vez**. El loader corre una vez;
  listo.
- **Opción A (contadoras siguen en Laudus):** el **mismo transformador** re-corre en cada refresh (el sync
  Laudus→mirror ya existe; el transformador re-lee el mirror y el loader hace upsert). El único pedazo difícil
  —asientos Laudus editados/borrados tarde (el problema de watermark que ya conocemos, memoria del reporte de
  gastos)— es un tema de **Fase 2 / decisión §5**, no de E1. E1 entrega la **carga completa idempotente**; el
  "delta repetible" fino se diseña cuando (y si) las contadoras eligen A.

**Por qué esto no nos bloquea (en simple):** la Fase 1 es idéntica en las dos opciones (cargar toda la historia
corregida). La arquitectura deja el transformador re-corrible, así que cualquier decisión que tomen después
se apoya en lo mismo que construimos ahora.

---

## 8. Componentes y secuencia de construcción (verificable)

Cada hito tiene un check concreto (disciplina "goal-driven" del proyecto). Esto alimenta el desglose de
stories, no lo reemplaza.

```
E1.1  Módulo x_laudus_migration (campos custom + planes analíticos + diarios)
      → verify: módulo instala limpio en Odoo 18; campos visibles en account.move.line; bean-check del mirror sigue verde.

E1.2  Transformador: colapso de cuentas (plan de cuentas Odoo desde la tabla)
      → verify: 569 códigos Laudus → 336 cuentas Odoo; toda cuenta Laudus tiene destino; snapshot test del plan.

E1.3  Transformador: sinceramiento por naturaleza (SPEC §3, cuenta + glosa)
      → verify: pytest sobre casos canónicos (allowlist Indumotora se queda; RetirosTecnin→activo; Sade→activo;
        Molco→gasto; washes netean; sin-match queda en Income marcado). Nada se descarta en silencio.

E1.4  Transformador: dimensiones + partners (analytic_distribution + res.partner)
      → verify: cada línea con dimensión esperada según CSV; socio-dueño mapea a partner sobre 115xxx.

E1.5  Loader (odoo shell/XML-RPC) con external IDs idempotentes — carga full history, 2 compañías
      → verify: re-correr NO duplica (upsert); todos los asientos posteados; debe==haber por asiento.

E1.6  Verificador de paridad (Σ por x_laudus_account_code, por moneda)
      → verify (GATE E1): 0 diffs en 569 códigos × moneda, EAG y RUT2, 2021→hoy.

E1.7  Activos de patrimonio a costo + participación (aperturas contra Equity) → REPORTE PATRIMONIO v1
      → verify: 12 cuentas con saldo inicial correcto (participación ⅓, no 100%); reporte de patrimonio lista
        yate/avión/casas + inversiones; set verificado a mano (fuera del gate de paridad Laudus, §5.3).
```

**Dependencias:** E1.1 primero (los campos son la base de todo). E1.2→E1.4 son el transformador (pueden ir en
paralelo tras E1.1). E1.5 depende del transformador. E1.6 depende de E1.5. E1.7 es el "win temprano" (brief §7)
y depende de E1.5 (necesita las compañías/plan cargados) pero es independiente de la paridad.

---

## 9. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **Volumen** (5 años × 2 cía × ~100k+ líneas) hace lento el loader por ORM | Loader batcheado + `create` en lote; external IDs para reanudar; el spike ya posteó 1 mes OK, se mide 1 año antes del full. |
| **USD / multi-moneda** mal cargado descuadra la paridad | Paridad **por moneda**; USD con `amount_currency`; test de un asiento USD conocido antes del full. |
| **Glosa inconsistente / typos** (data tipeada a mano: "Tecnion/Tecnin", "Señora Raquel/Raquel Ventura") | **§6·B completo:** estructura-primero (keyea código, no glosa) acota el blast radius; tabla de alias auditable (no fuzzy) + normalización para la minoría glosa-dependiente; reporte de cobertura + regenerar; paridad invariante (la plata no se descuadra aunque el tag falle). |
| **Sinceramiento sin-match** silencioso | Regla SPEC §3 paso 4: queda en Income + marcado "sin clasificar"; el verificador lista los marcados. Nunca se descarta. |
| **Consolidación no nativa en Community** | Declarado (§3): se resuelve en capa de reporte (dimensión Entidad + reportería existente). No bloquea Fase 1. |
| **Odoo edita/borra un asiento** en modo ongoing (§5 opción A) | Fuera de scope de E1; se diseña en Fase 2 si eligen A. E1 entrega carga idempotente re-corrible. |
| **`revisar-ingreso` (12) y sanity-check contadoras** (donaciones/deudores por-institución) | No bloquean E1 (mapa §6); se anotan como pulido; el generador es idempotente (cambia regla → regenera). |

---

## 10. Lo que este documento decide vs lo que queda abierto

**Decidido (técnico, auto-aprobado por `project-context.md`):** las 6 decisiones del §0. El transformador
externo único, los campos custom, los 6 planes analíticos + partners, el mecanismo de paridad, el stack
Odoo 18 Community sin `l10n_cl`, la idempotencia por external ID.

**Queda abierto (no bloquea E1):**
- Decisión §5 del brief (contadoras: Laudus-ongoing vs Odoo-nativo) — la arquitectura la deja para después,
  ambas se apoyan en lo mismo.
- Preguntas contables abiertas de Valentina (P-5 Misc JB, P-6 AZBA cash vs patrimonio, P-7 rendiciones) — son
  Fase 2/3, no E1.
- Los 12 `revisar-ingreso` y el barrido de aportes-disfrazados tipo Sade — pulido del transformador, idempotente.

**Necesito de vos, Ary:** el OK al resumen ejecutivo (§0). El detalle lo avanzo solo. Si algo del §0 no es lo
que esperabas, lo ajusto antes de que se desglose en stories.

---

## 11. Resumen de una línea

> Un solo transformador Python (que extiende el generador de Valentina) lee el espejo Beancount confiable +
> la tabla de mapeo, aplica el sinceramiento y el colapso, y carga Odoo 18 Community (2 compañías, sin
> `l10n_cl`) estampando el código Laudus en cada línea — de modo que la paridad al peso se verifica agrupando
> por ese código, invariante al colapso y al sinceramiento. Odoo queda tonto; la inteligencia, afuera y
> testeada; la historia, una sola verdad.
