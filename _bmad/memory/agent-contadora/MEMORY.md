# Memory

_Conocimiento curado de largo plazo. Vacío al nacer — crece a través de las sesiones._

_Este archivo es para insights destilados, no notas crudas. Captura la esencia: decisiones tomadas, ideas que valen la pena, patrones detectados, lecciones aprendidas._

_Mantén bajo 200 líneas. Las notas crudas van en `sessions/YYYY-MM-DD.md` (no aquí). Destila insights de los session logs en este archivo. Poda lo obsoleto. Cada token aquí se carga en cada sesión — que cada uno cuente._

## Modelo de Datos — Estado Actual

**Problema conocido — Tarjetas de crédito en LAUDUS:**
Las compras de tarjeta están registradas en cuentas de GASTO (no pasivo). El pago mensual también va a gasto, no cancela deuda. Esto genera:
- Doble conteo de gastos de tarjeta
- Balance sin pasivos reales de tarjeta
- Reportes de gasto total sobreestimados

**Estado:** No corregido, pero actualmente NO genera doble conteo — porque las cartolas de tarjeta aún no están integradas. El problema se activa recién cuando se importen los movimientos de cartola.
**Decisión de diseño — modelo correcto al integrar cartolas:**
- Importar detalle cartola de tarjeta: `Deuda por Pagar CC (Cr)  vs  Gasto por categoría (Dr)`
- Corregir pago de tarjeta en LAUDUS: de `Caja vs Gasto` → `Caja (Cr)  vs  Deuda por Pagar CC (Dr)`
- Resultado: pasivo netea a $0, gastos reflejan categorías reales del detalle
- **Migración requerida:** reclasificar pagos históricos de tarjeta de Gasto a Deuda por Pagar
- **Bonus:** el pasivo muestra deuda pendiente de tarjeta al cierre de cada período (útil como reporte)

**Fuentes de datos:**
- LAUDUS: activo, única fuente hoy
- Cartolas bancarias: no integradas (fuente de verdad planificada)
- Cartolas de tarjetas: no integradas

## Decisiones de Diseño

**Multi-RUT:** MVP tiene un solo RUT. La arquitectura debe soportar múltiples RUTs después del MVP — diseñar con eso en mente desde el principio.

**Drill-down:** todos los reportes de categorías deben ir de lo más agregado a lo más detallado (hasta movimiento individual). No mostrar detalle plano.

**UI:**
- Pie charts → categorías
- Bar charts → períodos de tiempo
- Click en gráfico → **filtro aditivo** (multiselección). Botón "Resetear filtros" visible siempre que haya filtros activos
- Drill-down → **expansión inline** (no abre nueva vista)

**Cuentas >6000:** son de las hijas del cliente. Deben poder excluirse en todos los reportes principales. También tienen su propio reporte dedicado.

## Reportes Aprobados

| # | Reporte | Visualización | Drill-down | Estado |
|---|---------|--------------|------------|--------|
| 1 | Flujo de Caja del Período | Barra (ingresos vs gastos) | No | Viable hoy |
| 2 | Gastos por Categoría | Pie + tabla detalle | Sí — inline jerárquico | Viable hoy |
| 3 | Ingresos por Fuente | Pie + tabla detalle | Sí — inline jerárquico | Viable hoy |
| 4 | Tendencia Mensual | Barra apilada (12 meses) | Click → filtra período | Viable hoy |
| 5 | Seguimiento de Hijas (cuentas >6000) | Pie + barra + tabla | Sí — inline jerárquico | Viable hoy |
| 6 | Saldos por Cuenta | Tabla | No | Viable hoy |
| 7 | Gastos Reales de Tarjeta | Pie | Sí | Requiere cartolas |
| 8 | Deuda de Tarjeta al Cierre | KPI / tabla | No | Requiere cartolas |

## Stories Revisadas

**Story 3.4 y 3.5 — ACs reformulados (2026-04-12):**
- 3.4: Agrega filtro cuentas >6000, bar chart especificado, drill-down habilitado vía 3.5, variación patrimonial clarificada como net worth
- 3.5: Reescrito completamente — drill-down inline jerárquico (no modal), filtros aditivos con chips, botón reset, detalle de tarjetas diferido al epic de cartolas
