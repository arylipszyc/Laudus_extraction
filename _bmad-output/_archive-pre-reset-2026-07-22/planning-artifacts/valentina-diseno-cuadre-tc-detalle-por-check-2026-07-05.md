# Diseño — Detalle por chequeo en la vista de cuadre TC (/cuadre-tc)

**Fecha:** 2026-07-05 · **Autora:** Valentina · **Pedido de Ary:** cada "C" debe poder abrirse y
mostrar QUÉ compara con QUÉ, los números de cada lado, y la diferencia — pensado para que un contador
pueda actuar sobre cada error.

## Principio

Cada C es una igualdad **"esto (contabilidad) debería ser igual a esto (cartola/banco)"**. Al abrir un
C se muestran las dos partes con su fuente, el número de cada una y la diferencia. Deuda en **positivo**
(magnitud), no el signo contable negativo (confunde al contador). Semáforo arriba; texto de acción abajo
cuando está en rojo/amarillo.

**Formato:** CLP sin decimales, punto de miles. USD con 2 decimales. Siempre etiqueta de moneda; en USD,
mostrar el dólar (fx) usado en la conversión.

## C1 · Cuadre de la deuda 🔴

| Lado | Fuente | Valor |
|---|---|---|
| Deuda en la contabilidad | saldo de la cuenta de la tarjeta al cierre del mes (`tc_real_balance`, en positivo) | $ |
| Deuda según la cartola | cierre del estado × dólar (`closing_clp`) | $ |
| Diferencia | debería ≈ 0 | $ ✓/✗ |

- USD: lado cartola = `USD {closing} × dólar {fx} = ${closing_clp}` (mostrar el dólar del estado; sale
  del pago que saldó el estado).
- 🔴: "La deuda registrada no coincide con el estado de cuenta: sobran/faltan $Z. Causas típicas: una
  compra o un pago se cargó mal, o falta cargar una cartola de un mes anterior. Revisá y, si hace falta,
  rechazá y volvé a importar."

## C2 · Continuidad entre meses 🟡

| Lado | Fuente | Valor |
|---|---|---|
| Apertura de esta cartola | `opening` (nativo) | |
| Cierre de la cartola del mes anterior | `c2_prior_closing` (nativo) | |
| Diferencia | debería ≈ 0 | ✓/✗ |

- 🟡: "La apertura de este mes no coincide con el cierre del mes pasado — probablemente falte cargar una
  cartola entre medio."
- Sin mes anterior (`c2_reason`): "Es la primera cartola de esta tarjeta; no hay mes anterior con qué
  comparar. Cargá los meses en orden." (no es descuadre)

## C3 · Compras con su deuda 🔴 — REQUIERE DATO NUEVO DEL BACKEND

El `c3_corrupted_count` solo es inaccionable: el contador necesita saber CUÁLES compras perdieron su
deuda para arreglarlas.

**Pedido al backend:** devolver la lista de los asientos corruptos cuando `count > 0`:
`c3_corrupted: [{date, narration, amount}]` (fecha, glosa, monto por línea).

- 🟢: "Las {N} compras del mes conservan su deuda." (N = total de compras del mes, contado de
  `movements` con op compra/cuota — ya viene).
- 🔴: "{count} compras perdieron su registro de deuda:" + tabla (fecha · glosa · monto). "Estas compras
  se categorizaron mal y se borró su deuda. Solución: rechazá y volvé a importar la cartola de este mes."

## C4 · Pago vs banco 🟡

| Lado | Fuente | Valor |
|---|---|---|
| Pago según la cartola | `pago_cartola` | $ |
| Pago registrado por el banco (Laudus) | `laudus_payment_total` | $ |
| Diferencia | debería ≈ 0 | $ ✓/✗ |

- Debajo: detalle de `laudus_payments[]` (fecha · glosa · monto) — ya disponible.
- 🟡: "El pago de la cartola no coincide con lo que registró el banco. Suele pasar cuando el banco paga
  varias tarjetas en un solo movimiento (pago consolidado), o si falta el pago del mes."

## C5 · Gasto del mes saldado 🟡 (informativo)

Un solo número (no forzar dos lados):
- "Gasto sin detallar todavía: ${c5_residual}."
- "El banco carga el gasto de la tarjeta en bloque; a medida que se categorizan las compras este saldo
  baja a $0. Es informativo, no un descuadre."

## Resumen para el dev

- Único dato nuevo del backend: **C3 → lista `c3_corrupted[{date, narration, amount}]`** cuando hay
  corruptos (en `compute_tc_cuadre` C3 + schema + endpoint).
- C1/C2/C4 ya tienen los dos lados; C5 queda con un número.
- Interacción (cada C abrible / acordeón vs. todos abiertos al expandir la fila) = decisión de dev/UX;
  el CONTENIDO por C es lo de arriba. Deuda en positivo, moneda etiquetada, dólar visible en USD.
