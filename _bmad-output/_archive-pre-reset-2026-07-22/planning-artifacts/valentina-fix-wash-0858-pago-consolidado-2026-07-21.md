# Fix del "payment wash" del 0858 — pago consolidado Santander parte el pago vía ControlYLiquidación

**Autora:** Valentina 💰 · 2026-07-21
**Origen:** Ary vio en Ingresos/Gastos que las cuentas-gasto pasarela de pago TC (430005-430010) mostraban saldos +/−/0; la mayoría netea, el 0858 no. Investigación forense (agente general) + diagnóstico contable (Valentina).
**Estado:** diagnóstico CERRADO con datos al peso. Diseño de fix listo → story de dev.

---

## 0. TL;DR

El residuo del 0858 en la cuenta-gasto 430009 **es, peso por peso, lo que Laudus mete en la cuenta
puente `ControlYLiquidación-115099`** al pagar. Laudus paga las tarjetas Santander en un asiento
consolidado y **parte el pago del 0858** entre 430009 (pizca) y ControlYLiquidación (grueso). La
cartola revierte la apertura completa contra 430009 solito → residuo = la parte de la puente. Fix =
que el asiento de pago de la cartola **espeje el desglose de Laudus** (revierte contra 430009 Y contra
ControlYLiquidación por los montos que Laudus usó). La deuda ya está correcta y no se toca.

---

## 1. Lo que NO está roto (verificado)

- **Deuda del 0858 CLP correcta:** `Liabilities:EAG:TC:Real:Tc0858VisaLatanpass` cierra en −7.466.345
  = exactamente el closing de la última cartola. Cadena apertura→cierre encadena: feb 4.825.462→9.440.753,
  mar →8.986.948, abr →6.854.328, may →7.466.345.
- **Compras reales e itemizadas:** comercios reales (ENEL, Aguas Andinas, Clínica Las Condes, DirecTV…),
  ruteadas a categorías reales + Gastos Varios.
- **NO es revolving:** el 0858 se paga COMPLETO cada mes (pago = apertura). (Corrijo mi hipótesis inicial
  de revolving — el mecanismo es otro.)

## 2. La causa raíz (verificada al peso)

Laudus paga las tarjetas Santander (0858 + 8996, CLP y USD) en **un solo asiento consolidado** desde
BancoSantander, y **parte el pago del 0858 en dos cuentas**. Ejemplo real (2026-02-07, je 5624,
"Visa Santander 0858 Eduardo Avayu"):

```
BancoSantander63188824-111009    −28.290.591
Tc0858VisaLatanpass-430009           572.990   ← lo que ve la pasarela de la cartola
ControlYLiquidacin-115099          4.252.472   ← el resto del pago del 0858 (cuenta puente, activo 115)
Tc8996MastercardLanpass-430007     9.038.300
Tc8996MastercardLanpassUs-430008  12.731.744
Tc0858VisaLatanpassUs-430010       1.695.085
```

La cartola-TC revierte la **apertura completa** (4.825.462) contra 430009 únicamente:

```
Tc0858VisaLatanpass-430009        −4.825.462
Liabilities:...Tc0858VisaLatanpass +4.825.462
```

Como Laudus solo puso 572.990 en 430009 (y 4.252.472 en la puente), el residuo en 430009 =
572.990 − 4.825.462 = **−4.252.472 = exactamente la pata de ControlYLiquidación.**

### El match, mes a mes

| Mes | Residuo 430009 (cartola + laudus) | ControlYLiquidación en el pago 0858 | Match |
|---|---:|---:|:--:|
| 2026-02 | −4.252.472 | 4.252.472 | exacto |
| 2026-03 | −8.701.593 | 8.701.593 | exacto |
| 2026-04 | −7.671.204 | 7.671.204 | exacto |
| 2026-05 | −6.398.716 | 6.425.683 | off por **26.967** (revisar) |

**Por qué las otras tarjetas SÍ netean:** 1027 (BCI) y 8996 se pagan con asiento donde Laudus pone el
monto en la cuenta-gasto directo (sin partir a la puente) → pago cartola = pago Laudus en esa cuenta →
netea a 0. El 0858 se rompe SOLO porque es Santander-consolidado-con-puente.

## 3. El fix (diseño contable)

El asiento de pago de la cartola debe **espejar el desglose del asiento consolidado de Laudus** en vez
de revertir todo contra la cuenta-gasto. De:

```
430009                 −apertura
TC:Real:Tc0858…        +apertura
```

a (matcheando el pago consolidado Laudus del mismo mes/tarjeta):

```
430009                 −(monto que Laudus puso en 430009)       ; netea a 0
ControlYLiquidacin-115099  −(monto que Laudus puso en la puente)  ; netea a 0
TC:Real:Tc0858…        +apertura                                 ; la deuda baja igual → sigue cuadrando
```

(Los dos montos de gasto/puente suman la apertura, así el asiento balancea y la deuda se reduce por la
apertura completa.)

**Efecto:** 430009 → 0 · ControlYLiquidación → 0 · deuda reconcilia igual (−closing). El pago deja de
aparecer como gasto (correcto: pagar la tarjeta salda un pasivo, no es gasto).

**Doctrina:** consistente con §6.2 pt.1 (`valentina-correccion-tc-cartolas-2026-06-20.md`): *el asiento
de pago (b) = el pago CLP REAL de Laudus (glosa-match), nunca la apertura contra una sola cuenta.* Acá
el "pago real" está partido en 2 cuentas; el fix lee ambas del asiento consolidado.

### Cómo lo ve el dev (no implementar a ciegas — es una story)

- Es la story **"fallback por monto / pagos consolidados Santander"** que ya tenía pendiente (nota
  2026-07-06). `pipeline/importers/tc_correction.py` ya tiene andamiaje de fallback por monto (~línea 46).
- El importer debe: (1) detectar que el pago del período es consolidado (un asiento Laudus toca varias
  cuentas-gasto TC + ControlYLiquidación); (2) leer cuánto asignó Laudus a la cuenta-gasto de ESTA
  tarjeta y cuánto a la puente; (3) emitir el pago de la cartola con esas dos patas.
- Guardas: si no encuentra el asiento consolidado que matchee (monto/glosa/fecha), NO inventar el split
  → dejar el comportamiento actual + marcar para revisión (nunca romper la deuda que ya cuadra).

## 4. Pendientes

1. **Mayo: desfase de 26.967** (residuo 6.398.716 vs ControlYLiquidación 6.425.683). Probablemente una
   comisión o ítem chico que cae distinto. Revisar al implementar; no rompe el diseño.
2. **0858 USD (430010):** problema DISTINTO — **nunca se le importó cartola** (lump puro de Laudus desde
   2021, "0858 USD retirada"). No es este wash. Necesita: conseguir la cartola USD del 0858 + importarla.
   Ojo: NO existe cuenta `Liabilities:...Tc0858VisaLatanpassUs` con datos (la deuda USD no se materializó).
3. **Generalizar:** verificar si otras tarjetas Santander futuras caen en el mismo patrón consolidado
   (8996 hoy netea, pero si un mes Laudus la parte a la puente, mismo fix aplica).

## 4b. REENCUADRE (hipótesis de Ary, confirmada con datos) — NO es mecánica de pago, es gasto de JAB

Lo que parecía un "split de pago" es en realidad esto: **los PAT de la 0858 son gastos de JAB / Fondo
Común que EAG paga con su tarjeta por cuenta de ellos.** Los contadores (que llevan Laudus, NO saben de
nuestras cartolas) los rutean a `ControlYLiquidación` porque para EAG **no son gasto — son cuenta por
cobrar**. Evidencia:

- `ControlYLiquidación` se salda contra **Traspaso a Fondo Común**-113031 (+86M), **RetirosDelMes**-890001
  JAB (+64M) y los bancos de las hijas (Jeannette/Jocelyn/Johanna/Jael, +108M) → es cuenta de enlace/por
  cobrar, no un simple clearing.
- Los mismos recibos (Enel 2.641.378 / Aguas 4.866.830 / Metrogas 1.059.987) están como **gasto de JAB**
  en el libro RUT2 (Luz-811005 / Agua-811006 / Gas-811010).
- Servicios JAB (7-12M/mes) > lo que cubre la 0858 (4-8,7M/mes) → la 0858 paga un SUBCONJUNTO de JAB.

**Consecuencia — el que está mal es NUESTRO desglose de cartola:** itemiza TODAS las compras de la 0858
como gasto de EAG, incluidos esos PAT que son de JAB. Sobre-declara EAG y, en el consolidado familiar,
**duplica** el gasto (EAG-cartola + JAB-Laudus). El residuo de −8,7M en 430009 es la contracara de la
parte que Laudus mandó bien a la cuenta por cobrar.

**El fix correcto (reencuadrado):** la cartola debe distinguir, en la 0858, los PAT-por-cuenta-de-JAB
(→ cuenta por cobrar / ControlYLiquidación, como Laudus) de las compras que sí son gasto de EAG. Los
primeros NO van a gasto de EAG. **Dependencia:** qué recibo es de qué propiedad lo saben los contadores;
nosotros podemos inferir por comercio/monto (match contra gastos JAB) pero necesitamos su criterio →
preguntas P1/P2/P3 en `valentina-preguntas-contadores-2026-07-21.md`.

## 5. Impacto en el reporte / demo

Mientras no se implemente, el 0858 CLP muestra un "gasto negativo" (~−7M) en Ingresos/Gastos y la puente
ControlYLiquidación queda inflada. **La deuda y las compras itemizadas están bien** — solo el wash del
pago está distorsionado. Para la demo: enmarcarlo como reconciliación en curso de una tarjeta Santander
con pago consolidado (honesto, acotado, no es error de datos).
