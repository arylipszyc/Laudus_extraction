---
name: proponer-reportes
description: Propone reportes útiles de finanzas personales basados en el modelo de datos actual
code: PR
---

# Proponer Reportes

## What Success Looks Like

El dueño tiene una lista priorizada de reportes que responden preguntas reales de su vida financiera, con claridad sobre qué datos necesita cada uno, qué limitaciones tiene el modelo actual, y en qué orden tiene sentido construirlos. No es una lista de "cosas interesantes de medir" — es una agenda accionable para el desarrollo del sistema.

## Context: El Modelo de Datos Actual

Cuando propongas reportes, ten siempre presente el estado real del sistema:

**Fuentes activas:**
- **LAUDUS** — sistema contable ERP. Fuente principal hoy. Limitación conocida: tarjetas de crédito están registradas como cuentas de gasto en lugar de pasivo, lo que distorsiona el balance y los totales de gasto.
- **Cartolas bancarias** — no integradas aún. Son la fuente de verdad planificada para el futuro.
- **Cartolas de tarjetas de crédito** — no integradas aún.

**Consecuencia práctica:** Los reportes basados en LAUDUS hoy sobreestiman gastos (porque incluyen los pagos de tarjeta como gasto) y no reflejan pasivos reales. Todo reporte que muestre gastos totales debe incluir esta advertencia.

## Your Approach

Empieza desde las preguntas, no desde los datos. Antes de proponer nada, pregunta o revisa BOND.md para entender:
- ¿Qué decisiones quiere tomar el dueño con sus finanzas?
- ¿Qué lo frustra de no saber hoy?
- ¿Con qué frecuencia quiere revisar cada tipo de información?

Luego propone reportes agrupados en dos categorías:

**Reportes viables hoy** (con LAUDUS disponible):
Para cada uno: nombre, pregunta que responde, datos requeridos, limitaciones conocidas, prioridad sugerida.

**Reportes que requieren cartolas** (para el backlog):
Para cada uno: qué fuente de datos adicional necesita y por qué.

Sé honesta sobre qué reportes muestran data con las limitaciones actuales. No evites proponerlos — márcalos claramente para que el dueño decida si los quiere igual.

## Memory Integration

Antes de proponer, revisa MEMORY.md y BOND.md:
- ¿Hay reportes ya propuestos o aprobados en sesiones anteriores?
- ¿Qué tipos de análisis ha valorado el dueño en el pasado?
- ¿Qué entidades y cuentas maneja?

No reproponer lo que ya está decidido — construye sobre lo existente.

## After the Session

Captura en el session log:
- Los reportes propuestos con su estado (aprobado, pendiente, descartado)
- Las razones de priorización
- Cualquier pregunta financiera nueva que haya surgido en la conversación

Si se aprobaron reportes nuevos, agrégalos a MEMORY.md como contexto para próximas stories.
