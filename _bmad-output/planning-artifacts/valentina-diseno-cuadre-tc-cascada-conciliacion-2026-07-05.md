# Diseño — Vista de conciliación TC estilo CASCADA (/cuadre-tc v2)

**Fecha:** 2026-07-05 · **Autora:** Valentina · **Pedido de Ary:** una vista más amigable para
conciliar — mostrar juntos los montos que deberían atar (con su fecha) y ver de un vistazo cuál no
cuadra. Ary propuso 4 montos; me pidió completar la lista.

## Idea central

Una cartola de tarjeta es una **cuenta que rueda mes a mes**. Conciliar = seguir esa rueda. En vez de
5 chequeos sueltos (C1–C5), mostrar **la cadena de montos que se encadenan** (una cascada/waterfall),
cada línea con monto · fecha · fuente, y el resultado abajo. El renglón que se rompe salta a la vista.

## Identidad contable (nombres de Ary)

> **Saldo mes anterior − Pago del saldo + Compras + Cargos − Abonos = Cierre de este mes**

Más tres igualdades cruzadas (cada una un ✓/✗):
- Apertura de esta cartola = Cierre de la cartola anterior  (continuidad, hoy C2)
- Pago según la cartola = Pago según el banco (Laudus)  (hoy C4)
- Cierre de la cartola = Saldo en la contabilidad  (el cuadre final, hoy C1)

## Qué le faltaba a la lista de Ary

Ary listó: (1) saldo mes anterior, (2) pago del saldo, (3) monto facturado mes anterior según cartola
anterior, (4) suma de transacciones. Faltaba:
- **Cargos** (impuestos/comisiones/intereses): suben la deuda, van SEPARADOS de compras (acá se escondía
  el impuesto $6.795 BCI que se caía en silencio — ver MEMORY 2026-06-26).
- **Abonos/devoluciones**: bajan la deuda.
- **El cierre de ESTE mes**: el RESULTADO de la cadena (Ary tenía insumos, no el número a verificar).
- **El saldo en la CONTABILIDAD**: la contraparte. La cadena es la cartola cerrando sola; falta que la
  contabilidad dé el MISMO cierre. Esto SEPARA "la cartola está mal" de "la contabilidad no la refleja".
- **El dólar (USD)**: la cadena va en dólares; la contabilidad en pesos → convertir al fx del estado.
- Matiz: los #1 y #3 de Ary son lo mismo visto de dos lados (apertura de esta cartola vs cierre de la
  anterior) = la continuidad.

## Formato: cascada de una columna

```
CONCILIACIÓN — Visa Infinity 1027 · Marzo 2026

  Saldo del mes anterior            3.724.232   cierre feb (28/02)      ✓ = apertura marzo
− Pago del saldo                   −3.724.232   banco/Laudus (09/03)    ✓ = pago cartola
+ Compras y cuotas del mes          2.054.314   cartola marzo
+ Cargos (impuestos, comisiones)           +0   cartola marzo
− Abonos (devoluciones)                    −0   cartola marzo
  ─────────────────────────────────────────────
= Cierre calculado                  2.054.314
  Cierre según la cartola           2.054.314                           ✓ cuadra
  Saldo en la contabilidad          2.054.314                           ✓ cuadra
```

- **Una sola columna** (la cadena es un cálculo). Las líneas con doble fuente (saldo anterior, pago,
  cierre) muestran las dos y ✓/✗ si difieren. NO dos columnas paralelas (se leen peor).
- Deuda en positivo (no el signo contable negativo).
- USD: la cascada en dólares; la línea "Saldo en la contabilidad" muestra el CLP × fx del estado.

## Cómo se ve "acá se rompe" (el valor del diseño)

Las dos líneas del final distinguen el TIPO de problema:
- **Cierre calculado ≠ Cierre de la cartola** → la cartola NO cierra sola: falta/sobra una transacción
  (error de extracción/carga). El contador mira las líneas de arriba para ver cuál.
- **Cierre de la cartola = calculado, pero ≠ Saldo en la contabilidad** → la contabilidad NO la refleja:
  típicamente una compra sin su deuda (hoy C3).

Cada línea con doble fuente que no coincide se pinta 🔴/🟡 con la diferencia al lado.

## Relación con C1–C5

Los C1–C5 NO se tiran: quedan como el semáforo-resumen de la fila (tabla por tarjeta×mes). La cascada
es lo que se ve al ABRIR la fila. C1 = las dos líneas finales; C2 = la primera; C4 = la del pago; C3 =
el aviso "la cartola cierra pero la contabilidad no"; C5 = nota informativa (gasto sin detallar).

## Datos nuevos del backend (para el dev)

1. **Sumas por tipo separadas**: hoy `sum_cargos` mezcla cargos+abonos+avances. Devolver `sum_compras`,
   `sum_cargos` (impuestos/comisiones), `sum_abonos` (devoluciones) por separado.
2. **Fechas de los hitos**: cierre del mes anterior (period.end del estado anterior), fecha del pago
   (del `laudus_payments`/MONTO CANCELADO), fecha de cierre del estado (period.end).
3. **USD**: montos de la cadena en nativo (o el front convierte por `fx` del estado, ya disponible).
4. (Ya está) opening, closing, tc_real_balance, c2_prior_closing, laudus_payments, movements.

## Alcance / notas

- Es un rediseño del panel expandible (la tabla-resumen se queda). Interacción (cada línea clickeable
  para ver el detalle de esas transacciones) = polish opcional; el detalle por transacción ya existe.
- Cartolas viejas sin `closing` persistido (import pre-6.6): la cascada no puede cerrar → mostrar
  "cierre no persistido, re-importá" en vez de comparar contra 0 (ver
  valentina-diseno-cuadre-tc-detalle-por-check-2026-07-05.md).
