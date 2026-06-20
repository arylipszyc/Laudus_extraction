---
name: disenar-esquema
description: Diseña estructuras de datos para integrar nuevas fuentes financieras como cartolas bancarias y tarjetas de crédito
code: DE
---

# Diseñar Esquema

## What Success Looks Like

El dueño tiene una propuesta de esquema de datos que resuelve la integración de la nueva fuente, es compatible con lo que ya existe en LAUDUS, y no introduce nuevos problemas de categorización. La propuesta incluye cómo manejar los casos borde conocidos — especialmente los movimientos de tarjeta de crédito y los movimientos que aparecen en LAUDUS pero no en las cartolas.

## Context: Los Problemas Conocidos a Resolver

Cuando diseñes esquemas de integración, estos son los problemas que debe resolver la arquitectura:

**Problema 1: Tarjetas de crédito en LAUDUS**
Las compras de tarjeta están registradas como gastos directos (cuentas de tipo gasto) en lugar de contra una cuenta pasivo (deuda de tarjeta). El pago mensual también se registra como gasto, no como cancelación de pasivo. Esto genera doble conteo.

La integración de cartolas de tarjeta debe resolver esto: cuando llegue la data real de tarjeta, la lógica debe evitar el doble conteo con lo que ya está en LAUDUS.

**Problema 2: Movimientos LAUDUS sin contraparte bancaria**
Habrá movimientos en LAUDUS que no aparecen en las cartolas bancarias — porque provienen de cuentas no monitoreadas, o son asientos contables sin movimiento real de caja. Estos no son errores — son "no reconciliados por diseño" y deben manejarse como categoría propia.

**Problema 3: Cartolas como fuente de verdad**
Cuando haya discrepancia entre LAUDUS y la cartola, la cartola gana. El esquema debe permitir marcar el estado de reconciliación de cada movimiento.

## Your Approach

Para cada nueva fuente de datos a integrar:

1. **Mapeo de campos** — qué campos trae la fuente y cómo se mapean al esquema interno
2. **Reglas de categorización** — cómo se asignan categorías a los movimientos (automático vs manual)
3. **Estado de reconciliación** — qué estados puede tener un movimiento (reconciliado, solo en LAUDUS, solo en cartola, conflicto)
4. **Manejo de duplicados** — cómo detectar y resolver movimientos que ya existen de otra fuente
5. **Corrección de datos históricos** — si hay data histórica incorrecta (como el problema de tarjetas), cómo migrarla

Propone el esquema como tablas o estructuras concretas, no abstracciones. El dueño debe poder visualizar exactamente qué columnas tendrá cada tabla.

## Memory Integration

Revisa MEMORY.md para el estado del modelo de datos actual y las decisiones de arquitectura previas. No rediseñar lo que ya está decidido sin una razón explícita.

## After the Session

Captura en el session log el esquema propuesto o las decisiones de diseño tomadas. Si se tomaron decisiones sobre el manejo del problema de tarjetas, documéntalas en MEMORY.md — son fundamentales para las próximas stories de ingesta.
