---
name: conciliacion
description: Diseña la estrategia de conciliación entre cartolas bancarias y LAUDUS para garantizar datos confiables
code: CO
---

# Conciliación

## What Success Looks Like

El dueño tiene una estrategia clara para saber cuándo confiar en los datos — qué porcentaje de movimientos están reconciliados, qué hacer con los que no lo están, y cómo el sistema señalará cuándo un reporte está basado en data parcialmente confiable. La conciliación no es un proceso que pasa una vez — es una práctica continua.

## Context: Por Qué la Conciliación es Fundamental

Un reporte de finanzas personales solo es útil si el dueño confía en los números. Sin conciliación, no hay forma de saber si lo que muestra el sistema es real o refleja errores de registro, movimientos duplicados, o cuentas que faltan.

La arquitectura de este proyecto define que:
- **Cartola bancaria = fuente de verdad** para los movimientos de cuentas corrientes
- **Cartola de tarjeta = fuente de verdad** para los gastos de tarjeta
- **LAUDUS** = sistema contable que puede tener movimientos adicionales sin contraparte bancaria (cuentas no monitoreadas, asientos contables puros)

## Your Approach

**Niveles de reconciliación:**

Diseña la estrategia en tres niveles:

1. **Reconciliación de transacciones** — cada movimiento de la cartola se empareja con su contraparte en LAUDUS (si existe). Estado: Reconciliado / Solo en cartola / Solo en LAUDUS.

2. **Reconciliación de saldos** — al cierre de cada período, el saldo de la cuenta en LAUDUS debe coincidir con el saldo de la cartola. Si no coincide, hay movimientos sin emparejar.

3. **Reconciliación de tarjetas** — caso especial: el movimiento en la cartola bancaria es el pago de la tarjeta; los movimientos reales son los del estado de cuenta de la tarjeta. La reconciliación debe relacionar el pago de tarjeta con los gastos individuales.

**Reglas de matching:**

Define las reglas para emparejar movimientos automáticamente (fecha ± N días, monto exacto, monto aproximado por diferencias de redondeo) y qué hacer cuando no hay match automático.

**Cobertura de reconciliación:**

Propone una métrica de cobertura: qué porcentaje de los movimientos en la cartola están reconciliados. Los reportes financieros deben mostrar esta cobertura. Un reporte basado en 60% de reconciliación no es tan confiable como uno al 98%.

**Movimientos LAUDUS sin contraparte:**

Definir la categoría "solo en LAUDUS" y cuándo es aceptable vs. cuándo requiere investigación. Ejemplos aceptables: asientos de depreciación, provisiones, traspasos internos entre cuentas no monitoreadas.

## Memory Integration

Revisa MEMORY.md para decisiones de arquitectura previas sobre el modelo de datos. Si hay un esquema ya definido para los estados de reconciliación, construye sobre él.

## After the Session

Documenta en MEMORY.md la estrategia de conciliación acordada. Este es contexto crítico para las próximas stories de ingesta de cartolas — el desarrollador necesita saber exactamente qué estados de reconciliación debe implementar y cómo calcular la cobertura.
