# Project Context — Política de decisiones y gates

> Este archivo es la fuente de verdad para los agentes BMAD (Analyst, PM, Architect, Dev, QA)
> sobre cuándo avanzar solos y cuándo detenerse a preguntarme. En caso de duda entre categorías,
> el agente debe tratarlo como "requiere mi aprobación" (fail-safe hacia preguntar).

## Sobre mí
No soy técnico. Tomo decisiones de producto, negocio, alcance y prioridad — no de
implementación técnica. Para cualquier decisión de arquitectura, stack, patrones de código,
librerías, estructura de datos o implementación, el agente debe **usar su propia
recomendación por defecto**, explicarla brevemente en el documento correspondiente
(architecture.md, story notes, ADR), y avanzar sin detenerse a consultarme — salvo que
la decisión tenga impacto directo en costo recurrente, en cumplimiento legal, o en algo
que yo experimente como usuario/negocio (ver tabla abajo).

## Gates que requieren mi aprobación explícita (STOP, no continuar sin luz verde)
- Aprobación de PRD completo (antes de pasar a arquitectura)
- Aprobación de arquitectura **solo en su resumen ejecutivo** (qué se va a construir y por qué,
  no el detalle técnico) — el Architect no necesita mi aprobación de las decisiones técnicas
  en sí, solo que le confirme que el resultado final cumple lo que pedí
- Cierre de cada épica (antes de pasar a la siguiente)
- Cualquier decisión que implique:
  - Costo recurrente nuevo (API de pago, servicio cloud, licencia, etc.)
  - Cambio de alcance no contemplado en el PRD original
  - Temas de compliance (Ley 21.719 protección de datos, Ley 21.668 interoperabilidad,
    datos de salud en mydatasalud, cualquier dato sensible)
  - Algo que cambie la experiencia visible para el usuario final de forma significativa

## Gates que el agente puede auto-aprobar y seguir sin detenerse
- **Toda decisión técnica**: elección de librerías, patrones de diseño, estructura de
  base de datos, estructura de carpetas, nombres de variables/funciones, framework interno,
  estrategia de testing, manejo de errores, versión de dependencias — usar la recomendación
  del agente (Architect/Dev) por defecto
- Aprobación historia por historia dentro de una épica ya aprobada
- QA/testing de una historia individual, mientras pase los criterios de aceptación
  ya definidos en el PRD/épica

## Regla de desempate
Si el agente no está seguro de si algo es "técnico" o tiene impacto de negocio/costo/legal,
debe tratarlo como que requiere mi aprobación — mejor preguntar de más que ejecutar una
decisión de negocio sin que yo la vea.

## Nota para el Architect
Cuando documentes una decisión técnica en architecture.md o en un ADR, agrega una línea
de "por qué" en lenguaje simple (una frase, sin jerga), para que si más adelante reviso el
documento entienda el motivo sin tener que preguntar.
