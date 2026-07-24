# Preguntas para los contadores — reunión (tarjeta 0858 / PAT / ControlYLiquidación / cruce EAG↔JAB)

**Autora:** Valentina 💰 · 2026-07-21
**Para:** Ary, en la reunión con los contadores (firma Laudus).
**Origen:** investigación del wash del 0858 en Ingresos/Gastos → destapó que Laudus rutea los PAT de la
0858 a ControlYLiquidación. Hipótesis (de Ary, con evidencia fuerte): son gastos de JAB/Fondo Común que
EAG paga con su tarjeta → cuenta por cobrar. Estas preguntas confirman/cierran eso.

**Cómo usarlas:** están ordenadas de la más importante a la menor. Tono: entender su diseño, no señalar
error. Ellos NO saben de nuestras cartolas — para ellos esto es su contabilidad normal.

---

## 🔑 P1 — ControlYLiquidación y los PAT de las tarjetas Santander (la central)

> "Veo que los **PAT** (pagos automáticos de servicios — Enel, Metrogas, Aguas Cordillera, Claro, Entel,
> Abastible) de las tarjetas **Santander** los llevan a la cuenta **ControlYLiquidación** (115099), en vez
> de a una cuenta de gasto de EAG. Me imagino que es por diseño — ¿es porque esos servicios son de
> **propiedades de JAB / Fondo Común**, y EAG los paga con su tarjeta **por cuenta de ellos**, así que
> para EAG queda como una **cuenta por cobrar** y no como gasto propio?"

**Por qué preguntamos:** la evidencia lo apunta fuerte — ControlYLiquidación se salda contra *Traspaso a
Fondo Común* (+86M), *Retiros del Mes de JAB* (+64M) y los bancos de las hijas; y los mismos recibos
(Enel 2.641.378, Aguas 4.866.830, Metrogas 1.059.987) están como **gasto de JAB** en su otro libro.
**Si confirman:** validamos que lo están haciendo bien y que el que debe ajustar es nuestro desglose de
cartola (hoy mete esos PAT como gasto de EAG → sobre-declara EAG y duplica el gasto de JAB).

## 🔑 P2 — Qué gastos de la 0858 son "por cuenta de JAB" vs gasto propio de EAG

> "¿Cómo distinguen, dentro de la 0858, **qué compras son por cuenta de JAB/Fondo Común y cuáles son
> gasto propio de EAG**? ¿Hay una regla (por comercio, por propiedad, por PAT vs compra manual) o lo
> deciden caso a caso?"

**Por qué preguntamos:** para que nuestra cartola separe bien. Los servicios de JAB (7-12M/mes) son más
grandes que lo que cubre la 0858 (4-8,7M/mes) → la 0858 paga **un subconjunto**. Necesitamos su criterio
para saber cuáles.

## P3 — Cómo se reembolsa ese "por cobrar"

> "Ese saldo que queda en ControlYLiquidación (EAG pagó por cuenta de JAB) — ¿cómo se recupera? ¿Es vía
> el **Fondo Común / los retiros de JAB**, como una compensación entre cuentas, o hay un movimiento de
> plata real?"

**Por qué preguntamos:** cierra el modelo del por-cobrar y nos dice si hay que reflejar una conciliación
EAG↔Fondo Común (que es una dirección que ya teníamos en el radar).

## P4 — La tarjeta 0858 en dólares (USD)

> "La **0858 en dólares** — ¿cómo la manejan? No le vemos desglose ni pagos claros por tarjeta; ¿se usa
> poco, o esos movimientos entran por otro lado?"

**Por qué preguntamos:** el 0858 USD nunca se materializó de nuestro lado (lump de Laudus desde 2021, sin
cartola importada). Saber cómo la tratan nos dice si vale la pena conseguir esa cartola o si es marginal.

## P5 (menor) — Desfase chico en mayo

> "En mayo hay una diferencia chica (~27.000) entre lo que va a ControlYLiquidación y el resto del pago de
> la 0858 — ¿puede ser una comisión o un ítem que cae en otro mes?"

**Por qué preguntamos:** los otros meses calzan exacto; solo mayo tiene ese residuo. Es cosmético, pero si
lo aclaran cerramos el diseño del fix al 100%.

---

## Otros temas de contexto (no de esta investigación — están en el guion de demo)

Si sobra tiempo o surge, hay preguntas más grandes ya anotadas en el guion de la demo
(`guion-demo-contadores-2026-07-21.md`): cartolas de custodios de inversiones (Julius Baer y otros),
separación capital vs ganancia en retiros de inversión, y la rama AZBA sin liquidar. Esas son de otro
frente; este archivo es específico del cruce 0858 / PAT / JAB.
