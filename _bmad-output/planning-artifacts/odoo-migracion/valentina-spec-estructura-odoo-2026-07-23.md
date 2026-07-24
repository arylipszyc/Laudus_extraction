# SPEC — Estructura contable definitiva para migrar a Odoo

**Autora:** Valentina · **Fecha:** 2026-07-23 · **Destinatarias:** contadoras del family office
**Estado:** DISEÑO — para revisión **antes** de construir. No se implementa nada hasta que este documento esté conversado y aprobado.

---

## 0. Propósito, alcance y lo que este documento NO es

**Qué es.** El plano de cómo va a quedar armada la contabilidad de la familia cuando pase de Laudus a Odoo:
el plan de cuentas, las dimensiones analíticas (para no volver a hacer los pivotes a mano en Excel), y una
regla clara para **sincerar el resultado** — sacar del "ingreso" lo que en realidad son movimientos de plata
entre bolsillos propios.

**Qué NO es.**
- **No** es una corrección de Laudus. Laudus no se toca. Odoo arranca con el espejo fiel de lo que hay hoy.
- **No** es una valorización de las inversiones. El valor real de las posiciones offshore (Leo, Tauro, Sade,
  Julius Baer) se reconoce en una **Fase 2** separada, con la posición del custodio en la mano. Hoy sólo
  ordenamos; no inventamos valor.
- **No** cambia la plata que entró o salió. Cada peso sigue igual; sólo se re-clasifica **en qué tipo de cuenta**
  queda registrado (activo / ingreso / gasto), para que el reporte diga la verdad.

**Principio rector (de Ary, correcto):** la ganancia o pérdida de una inversión **se genera en la cuenta de
origen** (el activo), no en la cuenta que recibe la plata. La que recibe sólo ve un traspaso de caja. Por eso
la Fase 1 muestra puros traspasos (conservador, real), y la utilidad recién aparece en Fase 2 cuando se valúa
el origen contra el custodio.

---

## 1. Plan de cuentas — estrategia

### 1.1 Regla de oro: **Laudus puro, sin plan chileno auto-instalado**

En el spike, al crear la compañía en Odoo se auto-metió el **plan de cuentas chileno (`l10n_cl`)** — cientos
de cuentas SII que nadie de esta contabilidad usa, mezcladas con las nuestras. **Eso no va.**

- La estructura de cuentas se importa **1:1 desde Laudus**: mismo **código** (`310011`, `115023`, `430005`…),
  mismo nombre, misma jerarquía. El código Laudus es la llave de todo el sistema (reportes, conciliación,
  paridad); no se renumera.
- **No** se instala la plantilla de cuentas `l10n_cl` en la compañía. Si Odoo la exige para operar (por el
  módulo de localización), se instala el módulo pero se **importa nuestro plan encima** y se archivan/ocultan
  las cuentas de la plantilla que no usamos. La contabilidad familiar no declara IVA ni renta por acá; no
  necesita el árbol del SII.
- Mapeo raíz → tipo de cuenta Odoo (mecánico, ya validado en los dos libros):

  | Raíz del código | Entidad | Tipo Odoo |
  |---|---|---|
  | 1 / 6 | Assets | Activo |
  | 2 | Liabilities | Pasivo |
  | 3 / 7 / 9 | Income | Ingreso |
  | 4 / 8 | Expenses | Gasto |
  | 5 | Income (resultado inv.) | Ingreso |

  (El dígito de entidad separa EAG / FFCC / JAB / hijas — igual que hoy en Beancount.)

### 1.2 Cuentas de **activo nuevas** a crear

Estas son las cuentas que **no existen hoy** en Laudus y que la Fase 1 necesita como destino de lo que hoy
está mal puesto en ingreso. Son cuentas de **balance (activo)**, marcadas **"provisional / a valuar en Fase 2"**.

| Cuenta nueva (propuesta) | Libro | Para qué | Origen del saldo | Nota |
|---|---|---|---|---|
| `Assets:FFCC:InversionesSade` | FFCC | Aporte de capital a Inversiones Sade SpA (chilena) | +4.876M que hoy está en `Income:FFCC:Sade-310011` | **Cerrado.** Es aporte, no pérdida. Costo, no valor. |
| `Assets:EAG:InvTecnion` (origen) | EAG | Recibir los retiros de Tecnión que hoy inflan ingreso | `RetirosTecnin-310013` −12,2B | Saldo quedará negativo/provisional — aceptado (§3) |
| `Assets:EAG:InvNuevoCiclo` (origen) | EAG | Retiros Inv. Nuevo Ciclo | `RetirosInvNuevoCiclo-310016` −5,9B | Provisional |
| `Assets:EAG:InmobiliariaEspana` (origen) | EAG | Retiros Inmobiliaria España | `RetirosInmobiliariaEspaa-310018` −9,0B | Provisional |
| `Assets:EAG:InmobiliariaMetropolitana` | EAG | Retiros Inmob. Metropolitana | `-310019` −0,41B | Provisional |
| `Assets:EAG:MBI` (origen) | EAG | Rescates de fondo MBI | `Mbi-310027` −4,8B | Provisional |
| `Assets:EAG:JuliusBaer` (origen) | EAG | Traspasos/retiros JB | `Jb-310029` −3,3B | Cruza con placeholder JB (§4) |
| `Assets:EAG:Pleyades` (origen) | EAG | Retiros Pléyades | `-310015` −8,9M | Provisional, chico |
| `Assets:<hija>:InvTecnion` (×4) | Jocelyn/Jeannette/Johanna/Jael | Retiros Tecnión de las hijas | `X70011` −2,26B a −2,59B c/u | Provisional (¿fondos propios? — ver §3 nota hijas) |
| `Assets:<hija>:JuliusBaer` / `:MBI` | hijas | Retiros JB / MBI de hijas | varios, chicos | Provisional |
| `Assets:EAG:AccionesPerla` | EAG | Venta Acciones Perla (disposición) | `-310059` −0,27B | Disposición de activo, no ingreso |
| `Assets:<libro>:ActivosEnVenta` o baja directa | EAG/FFCC | Ventas de autos/activos ("Venta de Activos") | `VentaDeActivos-310091` (EAG −0,36B / FFCC −2,95B) | **Pregunta abierta P-2** — ver abajo |
| `Assets:EAG:PrestamoJhonnyGuerra` | EAG | "Abono préstamo Jhonny" (devolución de capital) | `JhonnyGuerra-310045` −8,2M | Cuenta por cobrar, chico |

> **Cuentas de origen ya existentes** que NO hay que crear (ya son activo en el plan): `Assets:FFCC:LeoPartnershipLimited-111012`,
> `Assets:EAG:Tauro-113021`. Sus saldos quedan **como están** (decisión de Ary — "van a decir cualquier cosa"); se
> corrigen en Fase 2. Leo hoy −3.286M (negativo imposible), Tauro +6.208M (congelado al costo del aporte).

**Nomenclatura (P-4 resuelta):** las cuentas de origen **heredan el nombre de la cuenta Laudus** que drenan; no
se inventan nombres; se trabaja solo con las cuentas que sabemos que existen.

### 1.3 Cuentas de **activo para patrimonio** (yate / avión / casas) — decisión Ary 2026-07-23

Hoy estos activos son **invisibles** en el balance (solo aparecen como gasto al consumirse). Para el **reporte de
patrimonio** se crean cuentas de activo con **saldo inicial**. Reglas:

| Regla | Detalle |
|---|---|
| **Crear cuenta de activo** | `Assets:<libro>:KeikiKai` (yate), `:Avion<matrícula>`, `:CasaViaGris` / `:CasaMolco` / `:CasaMiami` |
| **Participación (obligatorio)** | Cada libro carga **su parte**, no el 100%. El yate/avión son ⅓ AAG · ⅓ EAG · ⅓ DAG → EAG registra ⅓. Sin esto el patrimonio queda inflado 3×. |
| **Saldo inicial contra Equity** | La apertura va a `Equity:…:Apertura`, **no** a ingreso. Es apertura, no ganancia. |
| **Base de valor** | **Costo** desde los asientos Laudus ahora (avión N225AW USD 2,27M; yate por participación); **tasación/mercado** en Fase 3. Mismo patrón que el "placeholder de valor" de las inversiones (§4). |
| **Sin depreciación** | Uso personal → no se deprecia; se **revalúa a mercado** cuando hay un número (tasación / seguro / venta). |
| **Traspasos ongoing = gasto** | Financiar mantención/uso **no** capitaliza (se consume). Solo el saldo inicial y las revaluaciones mueven el activo. |
| **AZBA aparte** | Los −2.490M a favor de la rama AZBA = **cuenta por pagar**, línea separada; no es valor del activo (§6, P-6). |

> **Autos:** NO se capitalizan uno por uno (mucha rotación, poco material). Se tratan como consumo personal;
> la "Venta de Activos" recupera caja (§2.D). Si en algún momento se quiere, un único `Assets:…:Vehiculos` a
> valor de mercado grueso — decisión menor, diferible.

---

## 2. La LISTA de cuentas de ingreso clasificada por naturaleza

> Esta es la pieza central: el **input directo** de la regla de sinceramiento de Fase 1 (§3) y lo que dicta qué
> cuentas de origen crear (§1.2). Los montos son el **acumulado real** de todos los años (2021→hoy), leídos del
> ledger; en Beancount el ingreso es de signo negativo (crédito), así que **un número más negativo = más ingreso**;
> un **positivo = plata saliendo** por una cuenta de ingreso (típico de aportes/pérdidas mal ubicados).

**Total de "ingresos" en el libro: −78.253M.** De eso, el **ingreso operativo real es < 10%**. El resto son
movimientos de capital y traspasos entre cuentas propias.

### 2.1 Resumen por naturaleza

| Naturaleza | Qué es | Fase 1 lo manda a… | Monto aprox. |
|---|---|---|---|
| **A. Ingreso real** | Dividendos, sueldos, directorio, arriendos, intereses | **Se queda en Ingreso** | ≈ −34,2B |
| **B. Retiro de inversión** | Rescate/retiro/devolución de un vehículo de inversión | Activo de **origen** (§1.2) | ≈ −38B |
| **C. Aporte de capital** | Plata **entrando** a una inversión (signo +) | Activo (Sade) | +4,9B |
| **D. Disposición de activo** | Venta de autos / acciones / propiedades | Baja del activo | ≈ −3,6B |
| **E. Pérdida / financiamiento operativo** | Molco (campo con pérdidas) | Gasto **o** activo — **P-1 abierta** | +1,7B neto |
| **F. Reembolso / contra-gasto** | Devolución isapre, seguros, oficina | Se queda (baja gasto) | ≈ −0,55B |
| **G. MIXTO** | "Otros Ingresos" — cada línea es distinta | **Regla por-glosa, transacción a transacción** | ≈ −1,8B |

### 2.2 Detalle cuenta por cuenta

**A — INGRESO REAL (se queda en Ingreso):**

| Cuenta | Monto | Por qué se queda |
|---|---|---|
| `Income:EAG:RetirosIndumotora-310011` | −25.269M | **Dividendo** (aunque se llame "Retiros"). Decisión Ary: se deja como ingreso — asunción documentada, no se consolida Indumotora. **Allowlist explícito.** |
| `Income:FFCC:Indumotora-310001` | −6.342M | Dividendos Indumotora en FFCC. Real. |
| `Income:EAG:DirectorioIndumotoraOne-310022` | −418M | Dieta de directorio. Real. |
| `Income:EAG:DirectorioIpChile-310021` | −97M | Dieta de directorio. Real. |
| `Income:EAG:KiaChileSpa-310023` | −380M | Pago recurrente mensual (15,84M fijo). **Confirmar naturaleza (P-3):** ¿arriendo / royalty? Probable ingreso real. |
| `Income:EAG:HyundaiChileSpa-310024` | −95M | Ídem, recurrente (3,96M). P-3. |
| `Income:EAG:DevolucinOficinaTecnin-310035` | −387M | Reembolso mensual de oficina de Tecnión (~15M). Operativo recurrente → real. |
| `Income:EAG:SueldoFcComplemento-310005` | −429M | Sueldo. Real. |
| `Income:EAG:SueldoTecnin-310003` | −187M | Sueldo. Real. |
| `Income:EAG:IngresosPorInversiones-310095` | −108M | Ingreso de inversiones (dividendo/interés). Real. |
| `Income:EAG:DividendosRetiros-310009` | −0,7M | Dividendo. Real. |
| Cuentas 5xxx `Resultado*`, `Dividendos Art.107`, `FIP` | 0 | Vacías (0 asientos). Se crean en el plan pero no mueven nada — reservadas para Fase 2. |

**B — RETIRO DE INVERSIÓN (→ activo de origen):**

| Cuenta | Monto | Origen (§1.2) |
|---|---|---|
| `Income:EAG:RetirosTecnin-310013` | −12.204M | `Assets:EAG:InvTecnion` |
| `Income:EAG:RetirosInmobiliariaEspaa-310018` | −9.047M | `Assets:EAG:InmobiliariaEspana` |
| `Income:EAG:RetirosInvNuevoCiclo-310016` | −5.931M | `Assets:EAG:InvNuevoCiclo` |
| `Income:EAG:Mbi-310027` | −4.767M | `Assets:EAG:MBI` |
| `Income:EAG:Jb-310029` | −3.259M | `Assets:EAG:JuliusBaer` |
| `Income:Jael:RetirosTecnin-970011` | −2.595M | `Assets:Jael:InvTecnion` |
| `Income:Johanna:RetirosTecnin-870011` | −2.278M | `Assets:Johanna:InvTecnion` |
| `Income:Jeannette:RetirosTecnin-770011` | −2.257M | `Assets:Jeannette:InvTecnion` |
| `Income:Jocelyn:RetirosTecnin-670011` | −2.257M | `Assets:Jocelyn:InvTecnion` |
| `Income:EAG:RetirosInmobiliariaMetropolitana-310019` | −410M | `Assets:EAG:InmobiliariaMetropolitana` |
| `Income:Jael:RetirosBankJuliusBaer…-970010` | −380M | `Assets:Jael:JuliusBaer` |
| `Income:EAG:RetirosFondoComn-310006` | −125M | traspaso desde FFCC (cuenta corriente de socios) |
| `Income:Jael/Johanna/Jeannette/Jocelyn:Mbi-…023` | −17 a −10M c/u | `Assets:<hija>:MBI` |
| `Income:EAG:RetirosPlyades-310015` (+ hijas −0,09M) | −9M | `Assets:EAG:Pleyades` |

> **Nota hijas (Jocelyn/Jeannette/Johanna/Jael):** sus retiros de Tecnión suman ~9,4B. **No sabemos si retiran de
> fondos propios o del pozo común.** Se mandan a un activo de origen provisional por hija, pero es **ítem de
> auditoría diferida** — igual que los retiros de inversión de EAG. No se afirma nada del saldo.

**C — APORTE DE CAPITAL (signo +, → activo):**

| Cuenta | Monto | Destino |
|---|---|---|
| `Income:FFCC:Sade-310011` | **+4.876M** | `Assets:FFCC:InversionesSade` (§1.2, cerrado) |

> **Barrido pendiente:** Sade es el aporte-disfrazado que encontramos; hay que barrer el resto de las líneas de
> signo **positivo** dentro de cuentas de ingreso buscando el mismo patrón (§6, tarea abierta).

**D — DISPOSICIÓN DE ACTIVO (venta → baja del activo, no ingreso):**

| Cuenta | Monto | Qué se vendió |
|---|---|---|
| `Income:FFCC:VentaDeActivos-310091` | −2.953M | Autos (Kia/Subaru/Rolls…) + una línea USD grande −2,6B. **Ojo:** trae un wash apertura/cierre de 2,8B que netea a 0. |
| `Income:EAG:VentaDeActivos-310091` | −361M | Autos (Bentley, Kia, Ford, Subaru…) |
| `Income:EAG:VentaAccionesPerla-310059` | −274M | Venta de acciones Perla |
| `Income:Jael:VentaDeActivos-970091` | −47M | Venta de activos hija |

> **P-2 (abierta):** ¿"Venta de Activos" es venta de bienes propios (→ da de baja el activo, la ganancia es
> valor − costo) o hay ventas que son giro habitual (autos del negocio automotor)? La glosa dice "venta Kia
> Sportage / Bentley / Rolls" — parecen bienes propios, pero necesito que las contadoras confirmen si algún
> bloque es reventa comercial. Cambia si es baja de activo o ingreso operativo.

**E — PÉRDIDA / FINANCIAMIENTO OPERATIVO (Molco):**

| Cuenta | Monto | Glosa dominante |
|---|---|---|
| `Income:FFCC:Molco-310005` | **+2.896M** | "traspaso de cuenta" (×77) — plata saliendo hacia Molco |
| `Income:JAB:Molco-710005` | −1.200M | "traspaso de agrícola" (×37) — plata entrando desde Molco |

> **P-1 — RESUELTA (Ary, 2026-07-23): Molco = GASTO, no activo.** Molco es un fundo operativo + campo recreativo
> familiar que opera a pérdida y se financia constantemente. La contabilidad de Molco **no** entra ahora (más
> adelante, como 3ª entidad: EAG · FFCC · Molco). **Fase 1:** los traspasos a Molco → `Expenses:…:MolcoFinanciamiento`,
> con tag `propiedad:Molco`; los flujos que vuelven (JAB "traspaso de agrícola" −1.200M) netean contra ese gasto.
> **NO se capitaliza como activo** — inflaría el patrimonio con plata que se consume (el error que estamos
> corrigiendo). El gasto es lo honesto: muestra lo que el campo cuesta por año y baja el patrimonio de verdad.
> Migra limpio a "inter-entidad" cuando Molco entre como entidad propia.

**F — REEMBOLSO / CONTRA-GASTO (se queda; baja el gasto asociado):**

| Cuenta | Monto | Naturaleza |
|---|---|---|
| `Income:EAG:DevolucinIsapre-310043` | −13M | Reembolso isapre (recupero de un gasto) |
| `Income:EAG:DevolucinSeguros-310049` | −19M | Reembolso seguros |
| `Income:EAG:DevolucinGerencia50-310037` | −20M | Reembolso gerencia |
| `Income:FFCC:ClubDeGolfDevolucionLab-310019` | −17M | Devolución Club de Golf |
| `Income:Jael:DevolucinIsapreJael-970051` | −4M | Reembolso isapre hija |
| `Income:EAG:DevolucinInternet-310041`, `DevolucinGastosReaca-310039` | ~0 | Reembolsos chicos |

> Son inflows reales de baja materialidad. **Opción simple:** dejarlos como "otros ingresos" (no distorsionan el
> P&L). **Opción purista:** netearlos contra el gasto que devuelven. Recomiendo dejarlos como ingreso menor en
> Fase 1 y no complicar — se puede refinar después.

**G — MIXTO (regla por-glosa, transacción a transacción — NO se puede clasificar la cuenta entera):**

| Cuenta | Monto | Contenido real (por glosa) |
|---|---|---|
| `Income:EAG:OtrosIngresos-310099` | −725M | "a cta BCI" −370M (traspaso), "traspaso de Raquel/Daniel/Alfredo" (traspasos), "Kia Chile" (ingreso), "devol pasaje/isapre" (reembolso), "donación", "préstamo" |
| `Income:FFCC:OtrosIngresos-310099` | −566M | "préstamo USD" −530M, "reemb USD", "Molco patente", washes apertura/cierre |
| `Income:JAB:OtrosIngresos-710099` | −519M | Washes apertura/cierre grandes, "venta Sorento", "traspaso a cuenta", "flight USD" |

> Estas tres cuentas son el cajón de sastre. **Aquí la regla por-naturaleza corre línea por línea sobre el campo
> glosa** (`desc`), no sobre el nombre de la cuenta. Es exactamente el caso que justifica que la regla sea
> "por naturaleza, no por nombre".

---

## 3. Reglas de sinceramiento — Fase 1 (determinística, en el import)

**Objetivo:** al pasar a Odoo, cada asiento de ingreso pasa por una regla que decide, **por la naturaleza del
movimiento**, si es ingreso de verdad o un movimiento de capital mal ubicado. **Determinística** = mismo input,
mismo output; nada a mano; auditable.

### 3.1 El campo que se lee

La regla lee, en este orden:
1. El **código de cuenta** Laudus (llave primaria — la tabla §2 ya clasifica la mayoría de las cuentas enteras).
2. La **glosa por-pata** (`desc`) — sólo para las cuentas MIXTAS (grupo G) y para desambiguar.

### 3.2 La regla, por naturaleza

```
PARA cada asiento con pata en una cuenta de Income:

  1. NETEAR WASH DE CIERRE ANUAL
     Si la glosa contiene "comprobante de apertura" / "comprobante de cierre"
     y existe su par igual-y-opuesto en el mismo ejercicio
        → excluir ambos (ruido de cierre Laudus, netea a 0). No re-clasificar.

  2. ALLOWLIST DE INGRESO REAL (se queda, aunque el nombre diga "retiro")
     Si cuenta ∈ {RetirosIndumotora-310011, Indumotora-310001,
                  Directorio*, Sueldo*, Kia/Hyundai, DevolucionOficinaTecnin,
                  IngresosPorInversiones, Dividendos*}
        → NO tocar. Queda en Income.

  3. POR NATURALEZA (glosa/cuenta), en cascada:
     a. dividendo / interés / directorio / arriendo / sueldo / distribución de utilidad
           → INGRESO REAL. Se queda.
     b. reembolso / devolución / "reemb" / "devol"
           → CONTRA-GASTO. Se queda como ingreso menor (Fase 1).
     c. rescate / retiro / "abono mandato" / devolución de préstamo / traspaso /
        "a cta X" / "traspaso de/a"
           → MOVIMIENTO DE CAPITAL. Sale de Income → Activo de ORIGEN (§1.2).
             (crear cuenta si no existe; marcar "provisional")
     d. aporte de capital / "aporte" / inversión ENTRANDO (signo +)
           → ACTIVO. Sale de Income → Assets:…:Inversion<X> (ej. Sade).
     e. venta de activo / "venta <bien>"
           → DISPOSICIÓN. Sale de Income → baja del Activo (§2.D). [sujeto a P-2]
     f. pérdida operativa de un negocio propio
           → GASTO. [Molco sujeto a P-1]

  4. SIN MATCH
     → queda en Income + se marca "sin clasificar" para revisión humana.
        NUNCA se descarta en silencio. (Misma disciplina que el desglose TC.)
```

### 3.3 Garantías (para que las contadoras confíen)

- **No se pierde ni se crea plata.** Cada re-clasificación es un cambio de *cuenta destino* dentro del mismo
  asiento balanceado. La suma total del libro no cambia; se mueve entre categorías (ingreso → activo/gasto).
- **Conservador.** En Fase 1 el resultado **subestima** la ganancia (los retiros bajan un activo que aún no está
  valuado). Nunca la sobreestima. Preferimos quedar cortos y sincerar en Fase 2, no inflar.
- **Reversible y auditable.** Cada asiento re-clasificado lleva metadata (`sinceramiento: "capital"`,
  `origen_provisional: true`), así se puede listar exactamente qué se movió y volver atrás.
- **Los saldos de origen van a quedar raros** (negativos, provisionales). **Es esperado y correcto** para Fase 1
  — el origen se valúa en Fase 2. Un activo de inversión en −12B no es un error de la regla; es la foto honesta
  de "sacamos plata de acá y todavía no cargamos cuánto vale lo que queda".

---

## 4. Registro de placeholders (Fase 2 — se declara ahora, se llena después)

Para valuar los orígenes en Fase 2 hace falta la posición real del custodio. Definimos **tres tipos de
placeholder** que se registran como estructura ahora y se rellenan cuando lleguen los datos.

### 4.1 Placeholder de **VALOR** (cuánto vale hoy la posición)

El valor de mercado de cada vehículo de inversión a una fecha de corte. Es lo que reemplazará al "costo
congelado" del origen.

| Vehículo | Valor custodio | Fecha corte | Fuente |
|---|---|---|---|
| **Leo** (offshore, Julius Baer) | bruto **USD 9,27M** / neto **~7,4M** | 30-06-2025 | Custodio JB (`Portfolio Valuations`) |
| **Tauro** (offshore, JB) | bruto **USD 11,3M** / neto **~4,9M** | 30-06-2025 | Custodio JB |
| **Sade** (SpA chilena, local) | — (falta) | — | Estados financieros SpA |
| Otros (Inmobiliaria España, Nuevo Ciclo, MBI, Tecnión) | — (falta) | — | Por conseguir |

> El "neto" de Leo/Tauro descuenta un **Misc** grande (Leo −1,9M ≈ ¿Lombard?; Tauro −6,4M) — **hay que confirmar
> con JB qué es ese Misc** antes de valuar (¿préstamo Lombard contra la cartera? ¿posición fuera de custodia?).

### 4.2 Placeholder de **RESULTADO ACUMULADO** (ganancia/pérdida no reconocida)

La diferencia entre el **valor** (4.1) y el **costo** con que quedó el origen tras la Fase 1. Es la utilidad que
Laudus nunca reconoció (la que "se fugó" — ver auditoría de inversiones EAG ≈26.193M diferida).

| Vehículo | Costo en libro (post Fase 1) | Valor (4.1) | Resultado acumulado |
|---|---|---|---|
| Leo | −3.286M CLP (hoy, negativo) → se ajusta | USD 7,4M | = valor − costo (Fase 2) |
| Tauro | +6.208M CLP (costo aporte) | USD 4,9M | = valor − costo (Fase 2) |
| Sade | +4.876M CLP (costo aporte) | falta | = valor − costo (Fase 2) |

> Se reconoce **una sola vez** contra `Income:…:Resultado<X>` (las cuentas 5xxx que hoy están vacías). Método
> multi-moneda: IAS 21 — partida en USD a dólar de cierre, diferencia de cambio a resultado (ver doctrina
> `valentina-metodo-multimoneda-ias21-2026-07-18.md`).

### 4.3 Placeholder de **PARTICIPACIÓN** (quién es dueño de qué, en qué proporción)

El registro de propiedad — insumo de la dimensión analítica "socio" y del netting de activos compartidos.

| Activo / vehículo | Participación | Fuente |
|---|---|---|
| **Yate (Keiki Kai / Fraser)** — costo FIJO | 1/3 AAG · 1/3 EAG · 1/3 DAG | Asientos Laudus (split verificado) + relato contadoras |
| **Yate** — costo de USO | quien incurre (viaje) | Retiros itemizados ("Vuelo X Hrs → RetirosDag") |
| **Avión** (N225AW nuevo) | AAG · EAG · DAG (AZBA salió) | Laudus 2025 |
| **Inyección offshore (netting)** | partes iguales EAG/AAG/DAG (histórico +AZBA) | "Abono Julius/Leo" en Excel |
| **Leo / Tauro** — cuentas por miembro | EAG/AAG/DAG + hijas + Raquel + Cone Marshall Trustees | Custodio JB |

> **AZBA sin liquidar:** salió del yate/avión, pero su rama (115029 + 4 nietos) queda **−2.490M** que el fondo le
> debe, todo como saldo entre cuentas corriente **sin pago en efectivo**. Ítem de auditoría: ¿se liquida en cash
> o queda como reparto de patrimonio? (Pregunta para las contadoras.)

---

## 5. Planes analíticos (las dimensiones que reemplazan el Excel a mano)

Hoy las contadoras arman **a mano, cada período**, el pivote de retiros por socio + netting Julius/Leo +
acumulado (`Resúmen Retiros al 30-06-2026.xlsx`). Odoo hace eso **nativo** con contabilidad analítica: se taggea
una vez por regla y los reportes se generan solos y reconcilian.

### 5.1 Regla de oro: **partición vs. disperso**

Cada dimensión analítica es de uno de dos tipos:

- **PARTICIÓN** (excluyente y exhaustiva): cada peso pertenece a **exactamente un** valor de la dimensión, y la
  suma de las partes **reconcilia** con la cuenta contable. Se puede exigir que cuadre.
- **DISPERSO** (etiqueta parcial): sólo algunos asientos llevan la etiqueta; **no** se exige que sume el 100% de
  ninguna cuenta. Sirve para agrupar/filtrar, no para cuadrar.

Meter una dimensión dispersa donde se espera partición es lo que descuadra los reportes analíticos. Por eso cada
dimensión declara su tipo **antes** de construir.

### 5.2 Las cinco dimensiones

| Dimensión | Valores | Tipo | Regla de asignación | Fuente (escalón) |
|---|---|---|---|---|
| **socio-dueño** | AAG · EAG · DAG · AZBA · SAG · FGK (+ Zeldis/Alazraki/Borzutzky) | **Partición** | Toda pata de una cuenta `Retiros<Socio>-115xxx` → ese socio. Reconcilia con el saldo de la cuenta corriente. | Cuentas 115021-039 (escalón 1) |
| **socio-usuario** | AAG · EAG · DAG (quien usó el activo) | **Disperso** | Sólo asientos de USO con socio identificable en glosa ("Vuelo X Hrs → RetirosDag"). El costo FIJO no lleva usuario (es 1/3 partición). | Glosas de retiros de uso (escalón 1-2) |
| **propiedad / activo** | Keiki Kai (yate) · aviones · Vía Gris · Molco · Miami | **Disperso** | `categoria2` "85 Yates"/"83 Aviones" + glosa. No todo asiento tiene propiedad. | categoria2 + glosas (escalón 1-2) |
| **sociedad offshore** | Leo · Tauro · Julius Baer · Pictet | **Disperso** | Cuentas 111012/113021 + glosa ("Leo Limited Partnership EAG"). | cuentas + glosas (escalón 1-2) |
| **por cuenta de** | FGK · JAB (gasto que EAG paga por ellos) | **Disperso** | `ControlYLiquidación` + PAT de la 0858 ruteados a por-cobrar. | ControlYLiquidación + PAT 0858 (escalón 2) |

> **"socio-dueño" es la única partición** — es la que reemplaza el "Resúmen Retiros" del Excel y **debe cuadrar
> al peso** contra el saldo de las cuentas corriente de socios. Las otras cuatro son etiquetas de análisis
> (dispersas): enriquecen el reporte pero no se les exige sumar el 100%.

### 5.3 Lo que la analítica NO arregla (data, no herramienta)

La analítica hace la reportería **reproducible y más rica**, pero **hereda los huecos de Laudus**:
- Valuación offshore (Leo/Tauro/Sade) → Fase 2 (§4).
- Capitalización de yate/avión (no hay cuenta de activo; hoy sólo mantención) → auditoría diferida.
- Rendiciones del capitán del yate → fuera de Laudus (Fraser gestiona cobrando desde Leo); confirmar si se traen.

---

## 6. Preguntas para las contadoras + tareas abiertas

**Preguntas RESUELTAS con Ary (2026-07-23):**
- **P-1 (Molco): RESUELTA → gasto.** Ver §2.E. Fundo/campo familiar a pérdida; se financia; no se capitaliza;
  entra como 3ª entidad más adelante.
- **P-2 (Venta de Activos): RESUELTA → autos propios, disposición personal.** Salen del ingreso. **NO se
  capitalizan uno por uno** (mucha rotación, poco material vs yate/avión). Mecanismo real = trade-in con
  Indumotora (facturan el auto nuevo, dejan **cuenta por pagar** hasta vender el viejo, netean, se paga la
  diferencia). **Verificar en la data** si Laudus registra esa cuenta por pagar transitoria o solo el neto.
- **P-3 (Kia/Hyundai): RESUELTA → sueldo de director (ingreso real, se queda).** Los hermanos son directores y
  socios de Indumotora: cobran sueldo/dieta (el pago fijo mensual) **y** dividendos (vía `RetirosIndumotora`,
  allowlist). Ninguno necesita sinceramiento.
- **P-4 (orígenes): RESUELTA → nombres de Laudus.** Las cuentas de origen heredan el nombre de la cuenta Laudus
  que drenan; no se inventan nombres; se trabaja solo con las cuentas que sabemos que existen.

**Preguntas ABIERTAS (para las contadoras / terceros):**
- **P-5 (Misc JB):** el descuento de Leo (−1,9M) y Tauro (−6,4M) del custodio, ¿qué es? ¿Lombard / posición fuera?
- **P-6 (AZBA): parcialmente resuelta.** El −2.490M = 5 cuentas corriente de la rama AZBA (`RetirosAzba-115029`
  −493M + `JosAlazraki-115031` −482M + `DeniseZeldis-115033` −485M + `MichelleZeldis-115035` −494M +
  `ArielBorzutzky-115037` −535M), a favor de ellos = **pasivo del fondo**. **Sigue abierto:** ¿se liquida en cash
  o queda como reparto de patrimonio?
- **P-7 (rendiciones):** ¿el control de rendiciones del capitán vive en un sistema aparte (Fraser)? ¿Se trae a Odoo?

**Tareas técnicas abiertas (nuestras, no de las contadoras):**
- [ ] Barrer todas las líneas de **signo positivo** dentro de cuentas de ingreso buscando más "aportes de capital
      disfrazados" tipo Sade.
- [ ] Reconciliar al peso los saldos de retiro Laudus vs el "Acumulado" del Excel de las contadoras (paridad).
- [ ] Definir la lista final de metadata de sinceramiento (`sinceramiento`, `origen_provisional`) para que el
      import la estampe.

---

## 7. Resumen de una línea

> Odoo arranca con el **espejo Laudus puro** (sin plan chileno auto-instalado); una **regla determinística por
> naturaleza** saca del ingreso los ~46B de traspasos/retiros/aportes mal ubicados y los manda a cuentas de
> activo de origen (provisionales); las **cinco dimensiones analíticas** (una partición — socio — y cuatro
> dispersas) reemplazan el Excel a mano; y el **valor real** de las inversiones queda para la Fase 2 con la
> posición del custodio. Fase 1 = P&L honesto y conservador **ahora**. Valuación = después.
