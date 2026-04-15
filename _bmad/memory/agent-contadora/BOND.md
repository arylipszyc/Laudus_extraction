# Bond

## Basics
- **Name:** Ary
- **Call them:** Ary
- **Language:** Spanish (always)

## Fuentes de Datos
_Qué fuentes financieras están activas, cuál es su estado, y qué limitaciones tienen._

- **LAUDUS (ERP):** Activo. Limitación conocida: tarjetas de crédito en cuentas de gasto, no pasivo.
- **Cartolas bancarias:** No integradas aún. Planificadas como fuente de verdad.
- **Cartolas de tarjetas de crédito:** No integradas aún.

## Entidades Financieras
- **Un solo RUT** — no son empresas separadas, son categorías dentro de las finanzas personales de un cliente
- La app es para un **cliente** (no son las finanzas de Ary, sino las de su cliente)
- **Cuentas >6000:** seguimiento de gastos e ingresos de las **hijas del cliente** — deben poder filtrarse en todos los reportes

## Bancos y Tarjetas
{Por descubrir — qué bancos y tarjetas de crédito tiene el cliente}

## Preguntas Financieras Clave
{Por descubrir — qué quiere saber, qué decisiones quiere tomar}

## Preferencias de Reporting
- **Drill-down:** empezar desde categoría más alta y poder bajar hasta el máximo detalle (movimiento individual)
- **Pie charts** para reportes de categorías
- **Bar charts** para reportes de períodos de tiempo
- **Click-to-filter en gráficos** — hacer click en una sección del gráfico filtra la vista
- **Multi-RUT futuro:** la arquitectura debe soportar agregar más RUTs después del MVP actual (1 RUT)

## Prioridades del Proyecto
- Proponer reportes útiles para Epic 3 (sesión actual)
- Diseño de ingesta de cartolas (futuro)

## Things They've Asked Me to Remember
- Las cuentas numeradas sobre 6000 son de las hijas — siempre deben poder excluirse de los reportes principales

## Things to Avoid
{Por descubrir}
