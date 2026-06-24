# Corrección contable de Tarjetas de Crédito vía import de cartolas

**Autor:** Valentina (asesora financiera) · **Fecha:** 2026-06-20 · **Owner:** Ary
**Estado:** Diseño acordado. **BASE implementada 2026-06-20** (ver nota); la corrección con cartolas sigue pendiente del flujo de import.

---

> **NOTA 2026-06-20 — base implementada (cambia los paths de este diseño):**
> Las cuentas TC originales ya **NO** son `Liabilities:EAG:TC:*` — pasaron a **`Expenses:EAG:TC:*`**
> (gasto, tal cual Laudus) en el ledger vivo (PR #19, ver `docs/handoff-tc-gasto-2026-06-20.md`). El
> override viejo que las forzaba a Pasivo se sacó. Esto **no cambia la contabilidad** de este diseño,
> pero sí los **paths**:
> - El **asiento (b)** del §6 ahora **saca el gasto falso de `Expenses:EAG:TC:<code>`** (la cuenta
>   original, ahora gasto), no de `Liabilities:EAG:TC:<code>`.
> - El destino de la **deuda real** sigue siendo una cuenta nueva `Liabilities:EAG:TC:Real:*` (§9).
> - **Estado interino** (tarjeta/período sin cartola): la TC queda como **gasto** en su cuenta
>   `Expenses:EAG:TC` original — antes el §1 decía que era pasivo-con-metadata-gasto; ahora es
>   directamente gasto, más simple y fiel a Laudus.

---

## 1. Problema

En Laudus (y por lo tanto en el espejo Beancount, una vez que el importer quede bien armado) las
tarjetas de crédito están mal contabilizadas:

- Las **compras individuales no se registran**. Solo se registra el **pago mensual** de la tarjeta
  (`Assets:Bancos -X` / `Liabilities:EAG:TC:...  +X`).
- Las cuentas `Liabilities:EAG:TC:*` existen como pasivo en el árbol Beancount, **pero su metadata
  dice `laudus_categoria1: "GASTOS - EGRESOS"`**. Como el reporte agrupa por esa categoría, el
  **pago mensual se lee como el gasto** de la tarjeta (lumpeado, sin detalle).

Diagnóstico verificado contra el histórico Laudus 2021-2022: de 568 movimientos que tocan cuentas
TC, **566 son pagos y solo 2 son compras**. El saldo de las cuentas TC queda absurdamente positivo
(deuda debería ser negativa en Beancount). Confirma: se registran pagos, no compras.

## 2. Objetivo

Cuando se importe la cartola (estado de cuenta) de una tarjeta, corregir la contabilidad de esa
tarjeta para ese período:

- Las **compras** del detalle de la cartola pasan a ser el **gasto real itemizado**.
- El **pago** de la tarjeta pasa a ser un **movimiento entre cuentas** (banco → tarjeta), no un gasto.

## 3. Restricción de diseño (regla de oro)

> La corrección se hace **exclusivamente con asientos contables estándar** (transacciones Beancount
> normales que emite la funcionalidad de import), **como si un contador ingresara asientos a mano**.
> **No se toca** el motor de Beancount, ni el importer de Laudus, ni la metadata de las cuentas
> existentes, ni la base de datos. Esto evita introducir bugs.

Corolarios:

- El importer de Laudus deja Beancount = Laudus, fielmente. Eso se queda así.
- **Mientras una tarjeta/período no tenga cartola importada, su asiento queda tal cual** (gasto en la
  cuenta TC original de Laudus). Es el estado interino aceptado.
- La corrección es **por tarjeta y por período** — solo donde efectivamente hay cartola.

## 4. Alcance

- Se importan **solo cartolas de 2026 en adelante** (2026 es el arranque de un proceso continuo).
- Pre-2026: intacto, espejo Laudus, gasto en las cuentas TC originales.

## 5. Modelo objetivo (convención de signo Beancount: pasivo deuda-negativa)

**Compra** (fuente de verdad = cartola; ya implementado por `_build_postings` en `cartola_pdf_importer.py`):
```beancount
2026-03-24 * "PAYU *UBER EATS"
  Liabilities:EAG:TC:Real:Tc8996MastercardLanpass   -5069 CLP    ; ↑ deuda real
  Expenses:EAG:<categoría>                            5069 CLP    ; gasto itemizado
```

**Pago** (movimiento entre cuentas, NO gasto):
```beancount
2026-04-09 * "Pago TC 8996"
  Liabilities:EAG:TC:Real:Tc8996MastercardLanpass   17045465 CLP  ; ↓ deuda real
  Assets:EAG:Bancos:BancoSantander63188824-111009  -17045465 CLP  ; sale del banco
```
Nota: el pago **ya existe en Laudus** como `Banco → TC original`. No se vuelve a tocar el banco
(ver asiento (b), que solo reclasifica).

## 6. Los asientos de corrección (lo que emite la funcionalidad de import)

Por cada tarjeta, al importar su cartola de 2026:

### (a) Compras itemizadas
Una transacción por línea `raw.operation_type ∈ {compra, cuota}` de la cartola:
```beancount
Liabilities:EAG:TC:Real:<tarjeta>   -<monto> CLP
Expenses:EAG:<categoría>             <monto> CLP
```
Granularidad: **una transacción por compra** (para drill-down en Fava).

### (b) Reclasificación del pago — saca el gasto falso, no toca el banco
Por cada línea `raw.operation_type == pago` (la "MONTO CANCELADO", monto negativo en la cartola).
Fechada **el mismo mes del pago** (calza con el pago de Laudus del mismo mes):
```beancount
Liabilities:EAG:TC:<tarjeta>-<code>        -<Q> CLP   ; saca el +Q que dejó el pago de Laudus (cuenta-gasto)
Liabilities:EAG:TC:Real:<tarjeta>           <Q> CLP   ; ↓ deuda real
```
La línea `pago` de la cartola **no genera una compra**; es el mismo evento que el pago de Laudus.
(El matching engine 9.6b debe asegurar que el pago se reconcilie y no se emita dos veces.)

### (c) Apertura — una sola vez por tarjeta, en su primera cartola
Toma `balances.opening` de la primera cartola 2026 (deuda arrastrada de 2025):
```beancount
Liabilities:EAG:TC:Real:<tarjeta>   -<opening> CLP   ; deuda real inicial
Equity:Apertura:TarjetasSinDetalle   <opening> CLP   ; posición inicial (NO gasto)
```
**La contrapartida va a `Equity`, no a `Expenses`.** El `opening` es consumo de 2025 (deuda previa),
o sea posición inicial, no gasto de 2026. Mandarlo a un gasto inflaría el gasto 2026.

## 7. Por qué no hay doble conteo ni fuga (prueba de la suma anual)

Gasto 2026 después de la corrección, por tarjeta:
```
  Σ pagos 2026        ← lo que puso Laudus (lump, como gasto)
− Σ pagos 2026        ← asiento (b): los saco de la cuenta-gasto
+ Σ compras 2026      ← asiento (a): las itemizo
+ opening → Equity    ← asiento (c): aporta 0 al gasto
─────────────────────
= Σ compras 2026      ✓ exactamente el consumo real de 2026
```
Como se importa **todo** 2026, cada pago cancelado por (b) tiene sus compras itemizadas en alguna
cartola del set. Sin diferido (todo se fecha en el mes del evento). Sin descuadre (cada asiento
balancea por construcción).

## 8. Bordes

- **Entrada (1-ene-2026):** resuelto por el asiento (c) → `Equity`. El consumo 2025 arrastrado es
  posición inicial, no gasto 2026.
- **Salida (dic-2026 pagado en ene-2027):** se arregla solo. Como el proceso es **continuo**, al
  importar la cartola de ene-2027 el asiento (b) cancela ese pago. No requiere asiento de cierre.
  (Solo haría falta un asiento de cierre si 2026 fuera un piloto que se detiene — no es el caso.)
- **Tarjetas sin cartola / períodos sin cartola:** intactos, gasto en la cuenta TC original.

## 9. Estructura de cuentas requerida

> **CORRECCIÓN 2026-06-22 (Valentina, tras leer `report_builder.py`).** La versión previa decía
> "`laudus_categoria1: "PASIVO"` para que el reporte no la cuente como gasto". **Eso es impreciso y
> peligroso.** El reporte de gastos agrupa el egreso por **`Categoria2`**, no por `Categoria1`: una
> fila entra al TOTAL EGRESOS solo si su `Categoria2` ∈ {`DEPARTAMENTO SANTIAGO`, `Casa Sur`,
> `DEPARTAMENTO MIAMI`, `GASTOS PERSONALES`} (EAG) o su `Categoria1` ∈ las cat de hijas. Lo que saca
> la cuenta del gasto es tener **`Categoria2` (y `Categoria3`) VACÍOS** — NO el label `PASIVO`.
> **Trap:** las cuentas TC originales son `categoria2: "GASTOS PERSONALES"` / `categoria3:
> "Tarjetas Credito"`. Si al crear la `TC:Real` se copia su metadata y solo se cambia `Categoria1`,
> **la cuenta seguiría sumando al gasto**.

### Lista exacta de cuentas (confirmada 2026-06-22 contra `accounts.beancount` + actividad 2026)

**8 `Liabilities:EAG:TC:Real:*`** — una por tarjeta-moneda con actividad 2026 (regla Ary §12.3, CLP y
USD separadas). El stem copia EXACTO el de la cuenta-gasto Laudus (decisión Ary: el asiento (b) deriva
el destino con transformación de string pura `Expenses:EAG:TC:<X>-<code>` → `Liabilities:EAG:TC:Real:<X>`):

| Cuenta-gasto Laudus | Code | `TC:Real:` |
|---|---|---|
| Tc1027VisaInfinity | 430005 | `Tc1027VisaInfinity` |
| Tc1027VisaInfinityUs | 430006 | `Tc1027VisaInfinityUs` |
| Tc8996MastercardLanpass | 430007 | `Tc8996MastercardLanpass` |
| Tc8996MastercardLanpassUs | 430008 | `Tc8996MastercardLanpassUs` |
| Tc0858VisaLatanpass | 430009 | `Tc0858VisaLatanpass` |
| Tc0858VisaLatanpassUs | 430010 | `Tc0858VisaLatanpassUs` |
| TcVariasEag | 430017 | `TcVariasEag` |
| TcRaquelVentura | 430019 | `TcRaquelVentura` |

+ **`Equity:Apertura:TarjetasSinDetalle`** (1).

**Skip: Amex 8083 (430011)** — cero actividad 2026, no hay cartola. Si aparece, decisión aparte (es
`CLP, USD` en UNA sola cuenta, a diferencia de las demás).

**Caveats:** `TcVariasEag` es un cajón de varias tarjetas físicas → se crea la cuenta pero se queda en
lump hasta que haya un estado de cuenta real que mapear. `Latanpass 0858` y la USD de Raquel: cuentas
creadas, la corrección espera la cartola. Raquel SÍ se itemiza (es tarjeta que le paga EAG — decisión
Ary 2026-06-22).

### Metadata requerida en cada cuenta nueva (lo que de verdad importa)

| Cuenta | `laudus_categoria1` | `laudus_categoria2` | `laudus_categoria3` | `code` |
|---|---|---|---|---|
| `TC:Real:*` (8) | `"PASIVO"` | **vacío** | **vacío** | sintético, rango pasivo `2xxxxx` |
| `Equity:Apertura:TarjetasSinDetalle` | `"PATRIMONIO"` (no-vacío) | **vacío** | **vacío** | sintético, rango patrimonio `3xxxxx` |

- **`Categoria2`/`Categoria3` vacíos** = caen en `cat2[""]`, bucket que el resumen nunca lee → fuera
  del gasto. Es el mecanismo real de exclusión.
- **`Categoria1` no-vacío** = evita que el guard "cuentas sin categorizar" (Story 10.2) las marque.
  `PASIVO` es correcto y mapea a Liabilities si se re-bootstrappea.
- **`code` (importante):** estas cuentas se postean por NOMBRE, no por código. Sin `code`, todos sus
  postings caen en `accountnumber=""`, colisionan, y el balance del pasivo aflora como una línea
  fantasma "Total prefijo desconocido" al final del reporte. Con un `code` en rango no-gasto el guard
  las saltea limpio. (Cosmético, no rompe el total, pero hay que hacerlo.)

- Se crean por el **flujo sancionado** de cuentas (`_new-accounts-pending.beancount` →
  `POST /cuentas-pendientes/{code}/promover`, Story 10.3). No se edita metadata de cuentas existentes.
  OJO: NO vienen de Laudus → se siembran a mano en el pending (no las descubre el flujo automático).

## 10. Mapeo cartola → asientos

| Campo cartola | Uso |
|---|---|
| `transactions[].raw.operation_type == compra/cuota` | asiento (a) compra |
| `transactions[].raw.operation_type == pago` (monto negativo) | asiento (b) reclasif. pago |
| `balances.opening` (primera cartola del card) | asiento (c) apertura |
| `transactions[].raw.card_suffix` | identifica la tarjeta física; **una cartola JSON puede traer varios suffixes** → separar por tarjeta |
| `source.bank_account_id` → `bank_account_resolver` | resuelve la cuenta Beancount destino |

## 11. Pendientes a confirmar / fuera de este diseño

- **Categorización real de las compras** (asiento a): hoy `NoopCategoryPredictor` manda todo a
  `Expenses:EAG:Suspense`. Story 9.7 lo reemplaza. La calidad del reporte de gastos depende de esto.
- Verificar el diagnóstico contra el estado **corregido** del importer de Laudus (no contra el
  estado actual, que aún no es confiable).

## 12. Decisiones contables para Story 6.2 (Valentina, 2026-06-22)

Resueltas para cerrar el diseño de la story de import. Reemplazan las notas tentativas de USD/FX y
nombre del §11.

### 12.1 — FX de cartolas USD y matching pago↔estado

> **CORRECCIÓN 2026-06-22 (Valentina, tras el hallazgo del dev en el FX).** La versión previa de este
> §12.1 decía que "una liquidación juega dos roles (denominador del FX **y** asiento (b)) **del mismo
> estado**". **Eso era un error y rompía el cuadre anual (§7).** Lo correcto: un estado tiene DOS
> pagos distintos, y son DOS pagos Laudus diferentes. Ver abajo.

**Cada estado USD tiene dos eventos de pago distintos:**

| Evento | Qué es | Para qué | Cuándo |
|---|---|---|---|
| Liquidación del estado | El pago del **mes siguiente** que salda ESTE estado (glosa USD == `closing`) | **denominador del FX** del estado | mes M+1 |
| `MONTO CANCELADO` (línea interna) | El pago hecho en el ciclo M — **salda el estado ANTERIOR** (M−1) | **asiento (b)** del estado M | mes M |

Un mismo pago Laudus `Pay_M` juega dos roles, pero en **estados ADYACENTES**: denominador del FX del
estado **M−1** (lo salda) y lump del asiento (b) del estado **M** (es su `MONTO CANCELADO`).

**FX (denominador):**

- **Principio:** `FX = CLP que SALDA el estado USD / total_USD_facturado_del_estado`. Fuerza
  `Σ(compras × FX) = CLP_que_salda` → cuadre exacto por construcción. NO usar BCCh (descuadra).
- **El CLP que salda el estado puede venir de dos lados** (Ary 2026-06-22):
  - **(i) Pago directo de la TC USD:** lump de Laudus `Banco → Expenses:EAG:TC:...Us` que paga el
    estado (normalmente el mes siguiente al cierre; glosa USD == `closing`).
  - **(ii) Traspaso USD→CLP:** si el contador NO pagó la TC USD directamente y el monto facturado se
    pasó a la TC en pesos, en Laudus hay un **movimiento entre la TC USD y la TC CLP**. El FX sale de
    ese movimiento: `CLP que entra a la TC CLP / USD que sale de la TC USD`.
- **NO del `MONTO CANCELADO` interno de la cartola** (ese paga el período anterior, no este estado).

**Asiento (b) — lump del `MONTO CANCELADO`:**

- El lump del asiento (b) es el **CLP real del pago Laudus** que matchea (por glosa USD) el USD de la
  **línea `MONTO CANCELADO`** — NO `MONTO_CANCELADO_USD × FX_del_estado`. El `MONTO CANCELADO` se
  pagó al tipo de cambio del estado **anterior** (que es el que liquidó); aplicar el FX del estado
  actual dejaría el asiento (b) sin igualar el lump real → `Expenses:EAG:TC:<code>` no netea a cero →
  residual de gasto falso (bug silencioso que descuadra). Mismo mecanismo glosa-matching que el FX,
  pero sobre el USD de esa línea.

**Por qué este modelo (MONTO CANCELADO) y no el del estado-propio:** la prueba de la suma anual (§7)
solo se sostiene si el asiento (b) remueve **exactamente los lumps Laudus de 2026, una vez cada uno**.
Procesar los estados Ene…Dic 2026 con el modelo MONTO CANCELADO cancela `Pay_Ene…Pay_Dic` 2026 = los
12 lumps que Laudus posteó en 2026 ✓. El modelo "liquidación del propio estado" cancelaría
`Pay_Feb…Pay_Ene2027` → dejaría `Pay_Ene2026` sin cancelar (gasto falso vivo en 2026) y cancelaría un
pago de 2027 → rompe la paridad peso-por-peso vs el contador. Por eso es el MONTO CANCELADO.

- **Unidad de matching:** dos matchings por estado, contra Laudus por glosa USD —
  (closing) ↔ (liquidación del mes siguiente, para el FX) y (`MONTO CANCELADO`) ↔ (su pago Laudus del
  mismo mes, para el asiento (b)). Cada pago Laudus se cancela una sola vez (por el asiento (b) del
  estado cuyo `MONTO CANCELADO` es) → sin doble conteo.
- **Timing:** proceso continuo/retrospectivo → la liquidación suele estar en Laudus al itemizar. Si
  aún no existe → **bloqueante, NO estimar el FX**; esperar al próximo import.
- CLP nacional: sin FX (montos ya en CLP).

**Flag menor (apertura USD):** el asiento (c) usa `opening × FX_actual` contra Equity, pero la deuda
de apertura se liquidó a otro tipo de cambio → queda un pequeño residual FX **en `TC:Real` (pasivo),
nunca en Expenses**. No toca el cuadre de gasto; es revalorización esperable de un pasivo en USD. Una
sola vez por tarjeta.

### 12.2 — Líneas `abono` (devoluciones / notas de crédito)

Espejo invertido de la compra (asiento a):
```beancount
Liabilities:EAG:TC:Real:<tarjeta>   +<monto> CLP   ; ↓ deuda
Expenses:EAG:<categoría>            -<monto> CLP   ; revierte el gasto
```
USD: mismo FX del estado. Categoría: la del comercio si el categorizador la pesca, si no Suspense.
**No** distinguir devolución-de-comercio vs nota-de-crédito-de-impuesto — para finanzas personales
ambos son "plata que volvió" = gasto negativo. Mantener simple.

### 12.3 — Convención de cuentas `TC:Real`: una por TARJETA-MONEDA

> **CORRECCIÓN de Ary (2026-06-22), supersede mi propuesta de unificar nacional+USD.** CLP y USD se
> tratan como **dos TC distintas, cada una con su propio pago** — tal como Laudus ya las separa
> (`-43000X` nacional vs `...Us-43000X` internacional). NO unificar.

- **Una `Liabilities:EAG:TC:Real:<Producto>` por tarjeta nacional CLP** y **una
  `Liabilities:EAG:TC:Real:<Producto>Us` por tarjeta internacional USD**. Cada una con su pago.
  Ej: `TC:Real:VisaInfinity1027` (CLP) + `TC:Real:VisaInfinity1027Us` (USD).
- Cada cuenta-gasto Laudus reclasifica (asiento b) contra **su** `TC:Real`: `-430005` → `...1027`;
  `-430006` (Us) → `...1027Us`.
- **Tarjetas adicionales / `card_suffix`:** dentro de una misma tarjeta-moneda, las adicionales
  ruedan a la misma `TC:Real` (comparten cupo en esa moneda) → NO se necesita cuenta por suffix;
  suffix = metadata opcional, no bloquea ni toca el prompt 9.5. (Este punto sigue válido; lo que
  cambia es que CLP y USD NO se unifican.)
- Metadata `laudus_categoria1: "PASIVO"`, creada vía flujo de cuentas pendientes (Story 10.3).
