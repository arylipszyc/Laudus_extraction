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

> **Matiz crítico (Valentina 2026-06-26):** esta prueba solo se sostiene si **TODA** línea del estado
> se itemiza en (a). Si una línea se descarta (impuesto, comisión, avance…), el pasivo `TC:Real` deja
> de cuadrar con el `closing` Y el gasto queda corto. El test de completitud es **`saldo TC:Real al
> cierre == −closing del estado`** (verificado en sandbox: cuando se dropeaban impuesto+comisión el
> pasivo quedaba corto exactamente esa suma). Ver §10.1 para el mapeo que garantiza que nada se cae.

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

- **CORRECCIÓN 2026-06-25 (Valentina) — el flujo 10.3 NO sirve para estas cuentas.** El plan previo
  decía crearlas vía `POST /cuentas-pendientes/{code}/promover`. Al verificarlo contra el código:
  (1) `promover` exige que la cuenta esté **en cuarentena** (`Assets:EAG:PendingReview:Cuenta-{code}`,
  descubierta por el importer en Laudus) → las `TC:Real` son sintéticas, daría **404**; y (2) el
  endpoint **obliga `categoria3` no-vacía** (router línea 54), justo lo contrario de lo que estas
  cuentas necesitan (cat2/cat3 vacías). Además `_new-accounts-pending.beancount` se **regenera** en
  cada corrida del importer → sembrar ahí no sobrevive.
- **Mecanismo real (decisión Ary 2026-06-25): declaradas directo en `accounts.beancount`** como `open`
  nuevos + bean-check + git. No viola la regla de oro: son **declaraciones de cuentas nuevas**, no se
  toca metadata de cuentas existentes, ni el motor, ni el importer. **HECHO 2026-06-25** (bean-check
  exit 0, 589 tests passed/0 regresiones). Codes sintéticos asignados (verificados libres): `TC:Real`
  = espejo 2-prefix del code de gasto (230005/230006/230007/230008/230009/230010/230017/230019);
  `Equity:Apertura:TarjetasSinDetalle` = 311005.
- **Item bank_account_id en las `...Us`: ya estaba resuelto.** Las 9 cuentas-gasto TC (incl. las 3 USD
  430006/430008/430010) ya tienen su `bank_account_id` distinto en `accounts.beancount`. Nada que hacer.

## 10. Mapeo cartola → asientos

| Campo cartola | Uso |
|---|---|
| `transactions[].raw.operation_type` | **clasifica el asiento — ver tabla completa abajo (§10.1)** |
| `balances.opening` (primera cartola del card) | asiento (c) apertura |
| `transactions[].raw.card_suffix` | identifica la tarjeta física; **una cartola JSON puede traer varios suffixes** → separar por tarjeta |
| `source.bank_account_id` → `bank_account_resolver` | resuelve la cuenta Beancount destino |

### 10.1 — Mapeo COMPLETO de `operation_type` (Valentina 2026-06-26, cierra el drop silencioso)

> **Origen:** la verificación end-to-end con la cartola BCI Visa Infinity 2026-04 real destapó que el
> builder solo manejaba `{compra, cuota, abono, pago}` y **descartaba en silencio** todo lo demás
> (`else: continue` en `tc_correction.py:151`). La BCI traía `impuesto` (timbres DL 3475, $781) y
> `comision` ("COBRO ADM MENSUAL", $6.014) → se perdían **los dos lados** del asiento: el pasivo
> `TC:Real` quedaba corto $6.795 Y ese gasto bancario desaparecía de los libros. `operation_type` es
> **libre** en `raw` (sin constraint de schema) → el código DEBE tener un default seguro, no un drop.

**Principio rector:** *toda* línea del estado emite asiento (a) y toca `Liabilities:EAG:TC:Real:<tarjeta>`
por `-monto×fx` (así el pasivo cuadra con el `closing`). **La contrapartida depende del tipo** — y NO
todo lo que sube la deuda es gasto (un avance es plata que entró, no consumo):

| `operation_type` | Asiento | Contrapartida (lado +) | ¿Suma al gasto? |
|---|---|---|---|
| `compra`, `cuota` | (a) | `Expenses:<categoría>` vía categorizador 9.7 | Sí |
| `impuesto`, `comision`, `interes`, `seguro`, `mantencion` | (a) | `Expenses:EAG:GastosBancarios-430003` (FIJO, **no** pasa por 9.7) | Sí |
| `abono` / reverso / nota de crédito | (a) | compra invertida (signo del `amount`, §12.2) | Negativo |
| `avance` (giro en efectivo) | (a) | `Assets:EAG:Caja-111001` (CLP) / `Assets:EAG:CajaUs-111003` (USD) | **No** — es préstamo, no consumo |
| `pago` (monto negativo) | (b) | `Expenses:EAG:TC:<tarjeta>-<code>` (reclasif., §6b) | — |
| `balances.opening` | (c) | `Equity:Apertura:TarjetasSinDetalle` | No |
| **cualquier otro / no reconocido** | (a) | `Expenses:EAG:Suspense` **+ contar en el `result`** (count + razón) | revisar |

**Normalización previa (barrido de 304 cartola.json ya extraídas, 2026-06-26).** Gemini NO es
consistente con `operation_type`: emite ~6 sinónimos para "compra" + deja muchas líneas en `None`.
Antes de despachar el asiento hay que **normalizar** a la columna canónica de arriba:

| `operation_type` crudo (Gemini) | #tx barrido | Normaliza a | Por qué |
|---|---|---|---|
| `None` (sin etiqueta) | 630 | `compra` si monto + / `abono` si monto − | compras sin taggear (Uber Eats, Warner…); el signo decide |
| `COMPRAS P.A.T.`, `pat`, `compra_automatica` | 69 | `compra` | pago automático de servicios (Aguas, Enel, Claro, DirecTV) = consumo |
| `cargo_automatico` | 7 | `compra` | suscripciones/cargos (Netflix, Colmena) = consumo |
| `nota_credito` | 1 | `abono` | nota de crédito = plata que volvió |

> Band-aid en el builder (normalizar + red de seguridad), NO tocar el prompt 9.5 (capa riesgosa). La
> normalización upstream queda como limitación conocida (§11). Lo no listado → Suspense + reportar.

**Reglas de oro para el dev:**
1. **Nunca descartar una línea.** Lo no mapeado → asiento (a) contra `Suspense` y se **reporta** en el
   `result` (campo nuevo tipo `unmapped: [{line, op, monto}]`). Así `TC:Real = closing` se sostiene
   SIEMPRE y lo desconocido queda visible, no perdido. (Esto es lo que el comentario del código
   *prometía* y no hacía.)
2. **Cargos bancarios son determinísticos** por `operation_type` → cuenta FIJA `GastosBancarios-430003`
   (global, decisión Ary 2026-06-26: no per-tarjeta; la metadata `bank_account_id` del asiento conserva
   el detalle si después se quiere cortar por tarjeta). NO los manda al categorizador 9.7 (eso es solo
   para `compra`/`cuota`).
3. **`avance` → Caja**, NO gasto. Default `Assets:EAG:Caja-111001` (USD → `CajaUs-111003`). Si un avance
   real cayó a una cuenta corriente, la metadata `bank_account_id` deja la traza para reclasificar a
   mano. Cuentas Caja **ya existen** (nativas Laudus), no hay que crear nada.
4. **Cero cuentas nuevas.** `GastosBancarios-430003`, `Caja-111001`, `CajaUs-111003`, `Suspense` ya
   están en el plan. Verificado 2026-06-26.

### 10.2 — Recomendación + revisión del contador (regla de colores) (Ary 2026-06-27)

**Decisión Ary: el contador confirma SIEMPRE. Nada va a automático (por ahora).** La confirmación es su
chequeo rápido de que todo está ok. Lo que se afina NO es saltarse la confirmación, sino la **calidad de
la recomendación** y una **señal de color** que le diga de un vistazo dónde fijarse.

El categorizador 9.7 ya calcula una **confianza** por recomendación (`CategorizationResult.confidence` +
`match_source`); hoy se pierde (el `predict()` público devuelve solo `(category, match_source, flag)` y el
builder TC toma solo `[0]`). **Hay que exponer confianza + fuente y mapearlas a color:**

| Color | Confianza / fuente | Qué hace el contador |
|---|---|---|
| 🟢 Verde | `historical-30+` o glosa recurrente ya muy confirmada (confianza alta) | ojeada y confirma |
| 🟡 Amarillo | `smart_importer`, `historical` con pocas confirmaciones, cargo bancario/avance por keyword (confianza media) | mira y confirma |
| 🔴 Rojo | Suspense, adivinanza de Gemini, monto raro, tipo no reconocido (confianza baja/nula) | **acá decide él** |

**3 colores** (decisión Ary 2026-06-27; sin 🟠 naranja por ahora — se agrega si el contador pide el matiz).

**El aprendizaje sin automatización:** como el umbral `SUPRA_THRESHOLD=30` ya NO es compuerta a auto
(nada va a auto), pasa a ser **solo el termómetro del color**: la confianza de un ítem `historical` =
`#confirmaciones / 30`, así que **la misma glosa se pone más verde con cada pasada** → el contador la
confirma cada vez más rápido pero NUNCA deja de confirmar. Eso es "el sistema aprende y refina con el
tiempo" + "confirmación siempre", sin contradicción. NO bajar el umbral, NO promover a auto.

**Implica (modesto):** backend expone `confianza`+`fuente` y el builder TC preserva el flag (deja de
hacer `[0]`); frontend pinta el badge de color en `/categorizacion` (ya existe) y ordena rojos arriba.
Cero cambio al comportamiento global del 9.7 — solo señal visual.

## 11. Pendientes a confirmar / fuera de este diseño

- **Categorización real de las compras** (asiento a): hoy `NoopCategoryPredictor` manda todo a
  `Expenses:EAG:Suspense`. Story 9.7 lo reemplaza. La calidad del reporte de gastos depende de esto.
- Verificar el diagnóstico contra el estado **corregido** del importer de Laudus (no contra el
  estado actual, que aún no es confiable).
- **Normalización de `operation_type` en la extracción (limitación conocida, 2026-06-26):** Gemini emite
  vocabulario sucio (sinónimos + `None`). El fix vive en el builder (band-aid, §10.1). Lo durable sería
  normalizar en el prompt 9.5, pero es capa riesgosa → diferido. La red de seguridad (Suspense +
  reportar + color rojo) cubre lo que se escape.

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

### 12.4 — `operation_type` más allá de compra/cuota/pago (Valentina, 2026-06-26)

Disparada por la verificación end-to-end (cartola BCI 2026-04 real, en sandbox). El builder descartaba
en silencio toda op fuera de `{compra, cuota, abono, pago}` → perdía cargos bancarios reales (impuesto
de timbres + comisión mensual), subvaluando **a la vez** el pasivo `TC:Real` y el gasto. **El mapeo
completo y las reglas de oro están en §10.1** (tabla canónica para el dev). Decisiones de Ary:

- **Cargos bancarios** (`impuesto`/`comision`/`interes`/`seguro`/`mantencion`) → cuenta existente
  `Expenses:EAG:GastosBancarios-430003`, **global** (no per-tarjeta; la metadata del asiento conserva
  el `bank_account_id` por si después se quiere el corte). Son gasto del período, sin tratamiento
  especial (el impuesto DL 3475 para persona natural no se recupera ni difiere).
- **`avance`** → `Assets:EAG:Caja-111001` (CLP) / `Assets:EAG:CajaUs-111003` (USD), NO gasto: es plata
  que entró, no consumo. Cuentas ya existen (sirven para TC y débito — decisión Ary). Default Caja; si
  un avance real cayó a una cuenta corriente, reclasificar a mano (la metadata deja la traza).
- **Nunca descartar:** op no reconocida → asiento (a) contra `Suspense` + reportar en el `result`. Así
  `TC:Real = closing` se sostiene siempre. Cero cuentas nuevas (todo verificado en el plan 2026-06-26).

### 12.5 — Recomendación, revisión y aprendizaje (Ary 2026-06-27)

El barrido de 304 cartolas ya extraídas mostró que `operation_type` es vocabulario sucio (630 `None` +
sinónimos PAT/automática) → la normalización del §10.1 es obligatoria, no opcional. Sobre eso, Ary fijó:

- **El contador confirma SIEMPRE. Nada va a automático.** La confirmación es el chequeo rápido de que
  todo está ok. (Descartado: bajar `SUPRA_THRESHOLD`, promover a auto, regla permanente.)
- **Regla de colores (3): 🟢 verde / 🟡 amarillo / 🔴 rojo** = confianza de la recomendación, para que el
  contador vea de un vistazo dónde fijarse (rojos arriba). Detalle y mapeo en §10.2.
- **Aprendizaje = el color se pone más verde con cada pasada** (la confianza `historical` sube con cada
  confirmación, `#conf/30`), nunca "deja de preguntar". El umbral 30 deja de ser compuerta y pasa a ser
  termómetro del color. NO tocar el comportamiento global del 9.7; solo exponer confianza+fuente y pintar.
