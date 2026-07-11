# Valentina — Contexto de negocio del Fondo Común / JAB (libro RUT2)

**Fecha:** 2026-07-11
**Fuente:** Ary (contexto directo). Complementa `valentina-clasificacion-rut2-fondo-comun-2026-06-30.md` (clasificación técnica del plan) — este doc es el QUÉ ES el libro, no el cómo se mapea.
**Estado:** contexto registrado + watchlist de revisión contable DIFERIDA a post-import (decisión Ary: "lo veremos cuando empecemos a cargar los números de Laudus en Beancount").

## 1. Qué es este libro

El RUT2 lleva **los fondos familiares**. El **Fondo Común (FFCC)** es donde están acumulados los fondos de la familia; de ahí se reparte a:

| Beneficiario | Quién es | Cuenta de retiro en el plan |
|---|---|---|
| AAG | hijo de JAB | 115021 Retiros AAG |
| EAG | hijo de JAB — **la entidad de nuestro libro principal** | 115023 Retiros EAG |
| SAG | la hija de JAB que falleció — madre de los 4 nietos AZBA. Su cuenta quedó (en 0 en los reportes actuales); los retiros de esa rama siguen vía AZBA | 115025 Retiros SAG |
| DAG | hijo de JAB | 115027 Retiros DAG |
| AZBA | los 4 hijos de la hija fallecida: José Alazraki, Denise Zeldis, Michelle Zeldis, Ariel Borzutzky | 115029 Retiros AZBA |
| FGK | la esposa (viuda) de JAB | (gastos raíces 6–8, no retiro) |

- **"JAB" en el plan = hoy FGK en la práctica.** Todos los gastos que dicen JAB son de FGK (JAB es el patriarca que dio nombre al libro histórico). → Dato para 11.2: el label de la sub-entidad lo decide Ary (¿JAB, FGK, JAB/FGK?).
- **Todos los gastos del libro salen del Fondo Común** — FFCC es la caja; JAB/FGK es un centro de gasto financiado por el fondo.
- **Cross-book con nuestro libro principal:** los retiros EAG del FFCC deberían tener contrapartida como ingreso/aporte en el libro de EAG. Oportunidad de conciliación cruzada cuando importemos (nadie la pidió aún — anotada como valor futuro).

## 2. Inventario de activos detrás de los buckets del reporte (raíz 8, gastos JAB)

| Bucket | Qué es | Estado / alerta |
|---|---|---|
| 81 Casas — Vía Gris | casa donde vive FGK | activa |
| 81 Casas — Reñaca | casa en Reñaca | **VENDIDA este año (2026) → no debería tener movimientos nuevos**; ver 310091 Venta de Activos |
| 81 Casas — Molco | campo productivo (ganado + forestal) con casa de FGK + casa de cada hijo | pérdidas constantes; mezcla productivo/personal — **revisar catalogación de sus ingresos (310005/710005) y gastos** |
| 81 Casas — Miami | departamento de FGK en Miami | activa |
| 81 Casas — Golf | cancha de práctica, está EN Molco | activa (¿debería colgar de Molco?) |
| 83 Aviones (3 cuentas) | solo tienen UN avión vigente | las otras 2 = aviones anteriores → **no deberían tener movimientos**; cuál es el activo se identifica por movimientos al importar (Ary no lo tiene claro) |
| 85 Yates (3: Destiny, Alfín II, Keiki Kai) | Ary solo conoce **Keiki Kai** | Destiny/Alfín II posiblemente antiguos o sin uso → **no deberían tener movimientos** |
| 87 Gastos Personales | incluye TC 871005 (JAB) / 873005 (FGK) | limitación TC lumpeada ya conocida. Detalle Ary 2026-07-11: **871005 (JAB) probablemente SIN uso** (verificar por movimientos); **873005 (FGK) activa y acumula ~3 tarjetas en una sola cuenta** — cuando toque el desglose estilo Epic 6, esa cuenta se abre en una `TC:Real` por línea de crédito |

## 3. Ingresos — la sospecha grande de Ary

- Deberían existir **ingresos por rentabilidad de los instrumentos financieros** donde están colocados los fondos (+ otros menores). Las cuentas existen (310001 Indumotora, 310003 Bank JB, 310007 MBI, 310009 Latinoamericana, 310011 SADE, 310005/710005 Molco…) pero **Ary no ve ingresos acreditados en Laudus** (el reporte del contador FFCC 05-2025 muestra MBI en 0 todos los meses).
- **Hipótesis de Ary:** los contadores usan Laudus SOLO para registrar gastos — no llevan cuentas de balance de verdad. Coherente con: sin saldos iniciales, sin Equity, retiros como CxC.
- → Se verifica al importar: ¿hay movimientos en cuentas de balance (raíces 1/2/6) más allá de la contrapartida de gastos?

## 4. Watchlist contable (revisar POST-IMPORT, no ahora — decisión Ary)

1. **Retiros como cuentas por cobrar (115021–115039, activo FFCC):** solo es correcto si esos montos se recuperan en algún momento. Si nunca se recuperan, es un activo que crece para siempre y esconde que el fondo se está repartiendo (debería ser distribución/patrimonio). VERIFICADO en plan: están en raíz 1 = activo. Revisar si tienen abonos (recuperos) o solo cargos.
2. **Traspasos FFCC→familia catalogados como ingresos:** sospecha de Ary; un traspaso interno no es ingreso. Cruzar cuentas 31xxxx contra movimientos que en realidad son transferencias.
3. **Ingresos de rentabilidad ausentes:** mismo patrón que la auditoría de inversiones de EAG 2026-06-20 (retiros sin separar capital/ganancia, Income:Resultado = 0). El patrón del contador se repite entre libros.
4. **Reñaca vendida:** cortar/alertar movimientos post-venta; la venta misma debería aparecer (¿310091 Venta de Activos? ¿precio vs valor libro?).
5. **Aviones y yates fantasma:** 2 de 3 aviones y 2 de 3 yates no deberían tener movimientos. Si los tienen → misposteo.
6. **Molco:** ingresos y gastos existen (campo productivo con pérdidas) — validar que estén bien catalogados y separados de lo personal (casas de los hijos, cancha de golf).
7. ~~SAG~~ **RESUELTO (Ary 2026-07-11):** SAG = la hija fallecida de JAB, madre de los AZBA. Cuenta legacy (en 0 en reportes actuales) — si aparecen movimientos nuevos en 115025 post-fallecimiento, revisar (deberían ir por AZBA).
8. **Avión vigente: identificarlo por movimientos.** Ary no sabe cuál de los 3 (CC-AJK / N266WW / N225AW) es el activo — se resuelve solo al importar: el único con movimientos recientes es el vigente; los otros 2 quedan legacy.

## 5. Impacto en las preguntas abiertas de mi análisis 2026-06-30

- **¿Raíces 4 y 8 P&L separados?** → Sí como estructura de reporte, pero conceptualmente TODO se financia del FFCC: raíz 4 = gastos de administrar el fondo; raíces 6–8 = el gasto de la rama FGK. El reporte debe dejar ver "cuánto sale del fondo y hacia quién/qué".
- **¿Apertura/Equity?** → Consistente con la hipótesis "solo gastos": probablemente no hay apertura real. La convención Equity de apertura (12.1) sigue haciendo falta para que Beancount cierre, pero el monto puede ser un plug grande; no interpretarlo como patrimonio real hasta la revisión post-import.
- **¿Pregunta de negocio del reporte?** → Se afina a DOS preguntas: (a) *"¿en qué gasta el fondo y en qué gasta FGK, por activo?"* (como EAG) y (b) *"¿cuánto repartió el fondo y a quién?"* (retiros por persona — el reporte del contador gira en torno a esto). El diseño de 13.1 debería contemplar ambas.

## 6. Excel de clasificación DEVUELTO (2026-07-11) — insumo de 12.1 completo

Ary llenó `_handoff/Plan-Cuentas-RUT2-para-clasificar-2026-07-10.xlsx`: **357/357 filas con
sub-entidad confirmada SI** (ratifica el mapeo mecánico FFCC/JAB por dígito de raíz y los labels
FFCC / JAB / FondoComun), **2 cuentas marcadas TC** (871005, 873005), cero correcciones ni
comentarios. La clasificación técnica del 06-30 queda VALIDADA por el dueño.

## 7. Dirección futura — reconciliación de BANCOS e INVERSIONES (ambos libros, incl. EAG)

Planteado por Ary 2026-07-11: hoy **no se están conciliando los bancos** — el esfuerzo de cartolas
se concentró en TC porque estaban mal catalogadas y sin detalle, pero las cuentas corrientes
(que sí están bien registradas en Laudus) tampoco se verifican contra el banco. Eventualmente:

- **Cartolas de cuenta corriente** → reconciliación rutinaria (EAG y RUT2). Nota: para EAG la
  maquinaria YA existe (extractor 9.5 validado con cartolas bancarias reales BCI/Santander/Chile
  + motor de reconciliación Epic 6 con matching cuenta corriente ±3d + dashboard + cierre de
  período). El gap es OPERACIONAL (rutina de subir cartolas de banco), no de construcción.
- **Cartolas/estados de cuentas de INVERSIÓN** → capacidad NUEVA (formato distinto de banco/TC).
  Valor extra grande: desbloquea la auditoría de inversiones EAG DIFERIDA 2026-06-20 (≈26.193M
  mal cargados, bloqueada esperando saldos reales del custodio) y testea la hipótesis
  "rentabilidad ausente" del FFCC (§3).
- **Mi recomendación de prioridad** cuando se retome: inversiones ≥ cuenta corriente — la cta cte
  agrega confianza sobre data probablemente sana; inversiones destapa errores CONOCIDOS y plata
  grande. Secuencia sugerida: cerrar Epics 11–13 (RUT2 en Beancount) → brief de epic
  "reconciliación bancos+inversiones" (los dos libros juntos, mismo motor).

## 8. Qué NO cambia

- El mapeo mecánico raíz→Beancount (1-4=FFCC, 6-8=JAB) queda intacto — este contexto no altera la clasificación técnica, la enriquece.
- Nada de esto bloquea 12.1/12.2/12.3. La watchlist es para DESPUÉS de tener los números en Beancount.
