---
name: revisar-story
description: Revisa specs de stories de reporting para validar que respondan preguntas reales y sean contablemente coherentes
code: RS
---

# Revisar Story

## What Success Looks Like

La story sale de la revisión con criterios de aceptación que un usuario real podría verificar, con claridad sobre exactamente qué datos muestra y desde qué fuente, y sin métricas vacías que se ven bien pero no dicen nada. Si hay limitaciones conocidas del modelo de datos que afectan la story, están documentadas en los criterios — no escondidas.

## Your Approach

Para cada story de reporte, aplica estas tres preguntas de forma sistemática:

**1. ¿Qué pregunta responde esto?**
Si la story no puede articular en una oración qué pregunta del dueño responde, es una señal de que el reporte no tiene propósito claro. No avanzar hasta tener esa respuesta.

**2. ¿Los datos existen y son confiables?**
Revisa si el reporte depende de:
- Datos con limitaciones conocidas (ej: gastos de tarjeta sobreestimados en LAUDUS)
- Datos que aún no están integrados (cartolas bancarias, tarjetas)
- Datos cuya lógica debit/credit puede ser incorrecta

Si existen limitaciones, los criterios de aceptación deben incluir un indicador visual o nota en el reporte.

**3. ¿Los criterios de aceptación son verificables?**
"El reporte muestra los gastos" no es verificable. "El reporte muestra el total de gastos por categoría del mes seleccionado, con una nota visible si hay movimientos de tarjeta incluidos" sí lo es.

Proporciona feedback específico y accionable. Si algo está mal, di exactamente qué cambiar y por qué. Si algo está bien, dilo — el dueño necesita saber qué mantener.

## Memory Integration

Revisa MEMORY.md para:
- El estado del modelo de datos y limitaciones activas
- Decisiones de diseño de reportes tomadas en sesiones anteriores
- Qué tipo de feedback le ha resultado útil al dueño

Usa el contexto del proyecto para referencias cruzadas — si la story menciona cuentas específicas de LAUDUS, verifica que la lógica sea consistente con lo que se sabe del plan de cuentas.

## After the Session

Captura en el session log:
- La story revisada y el veredicto (aprobada, necesita cambios, bloqueada)
- Los cambios específicos recomendados
- Si se identificaron nuevas limitaciones del modelo de datos, agrégalas a MEMORY.md
