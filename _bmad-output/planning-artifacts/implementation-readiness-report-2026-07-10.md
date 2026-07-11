---
stepsCompleted: [step-01-document-discovery, step-02-prd-analysis, step-03-epic-coverage-validation, step-04-ux-alignment, step-05-epic-quality-review, step-06-final-assessment]
workflowStatus: complete
completedAt: '2026-07-10'
scope: Segundo RUT (Fondo Común FFCC/JAB) — Epics 11-13, FR45-FR56
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/planning-artifacts/architecture-c4.md
  - _bmad-output/planning-artifacts/epics-segundo-rut.md
  - _bmad-output/planning-artifacts/discovery-segundo-rut-intake-2026-06-30.md
  - _bmad-output/planning-artifacts/valentina-clasificacion-rut2-fondo-comun-2026-06-30.md
---

# Implementation Readiness Assessment Report

**Date:** 2026-07-10
**Project:** family-office-eag — alcance Segundo RUT (Fondo Común FFCC/JAB)

## Document Inventory

| Tipo | Documento | Estado |
|---|---|---|
| PRD | prd.md (2026-05-18, FR1–FR44) | ✓ usado — no contiene FR45–56 (gap conocido, evaluado en paso 2) |
| Arquitectura | architecture.md + architecture-c4.md (2026-06-19) | ✓ ambos; c4 manda en conflictos (pivot Beancount vigente) |
| Epics & Stories | epics-segundo-rut.md (2026-07-10) | ✓ objeto del check (Epics 11–13, 8 stories) |
| Epics legacy | epics.md (Epics 1–10) | Excluido — fuera de alcance, mayormente implementado |
| UX | — | No existe; esperado para este alcance |
| Soporte | discovery-segundo-rut-intake-2026-06-30.md, valentina-clasificacion-rut2-fondo-comun-2026-06-30.md | ✓ contexto de trazabilidad |

Sin duplicados whole/sharded. Excluido: prd-validation-report.md (es reporte, no PRD).

## PRD Analysis

### Functional Requirements

El PRD (2026-04-06, editado 2026-04-08) contiene **44 FRs** en 8 grupos:

- **Auth & Access (FR1–FR5):** Google OAuth; roles owner/contador; owner solo lectura+comentarios; contador sube cartolas/categoriza/reconcilia; log de mutaciones.
- **ERP Sync (FR6–FR11):** sync automático Balance Sheet + General Ledger desde Laudus; incremental; backfill histórico desde 2021; dedup por PK; timestamp de último sync.
- **Dashboards (FR12–FR19):** filtro por entidad **(EAG, Jocelyn, Jeannette, Johanna, Jael — lista hardcodeada en FR12)**; filtro por fecha; dashboards activos/pasivos, ingresos/gastos, estado de resultado, variación patrimonial; drill-down a transacciones; detalle TC a nivel movimiento.
- **Ingesta cartolas (FR20–FR27):** upload PDF/Excel; extracción Gemini JSON; validación apertura+Σmov=cierre; bloqueo/override justificado; flags duplicados/anómalos.
- **Categorización (FR28–FR31):** sugerencia desde plan de cuentas; aceptar/corregir; confirmación explícita; aprendizaje por correcciones (umbral 30).
- **Reconciliación (FR32–FR35):** corrida mensual por entidad/período; cruce ERP vs cartola; reporte matched/unmatched; cierre de período.
- **Colaboración (FR36–FR41):** comentarios en líneas; notificaciones in-app+email; inbox; resolver hilos.
- **Alertas (FR42–FR44):** detección de variación de gasto sobre umbral; notificación; umbrales configurables.

**Total FRs en PRD: 44.** Los FR45–FR56 del alcance Segundo RUT **NO existen en el PRD** — fueron inventariados en `epics-segundo-rut.md` a partir del discovery 2026-06-30 (posterior al PRD).

### Non-Functional Requirements

**19 NFRs:** Performance (NFR1–4: carga <3s, filtros <2s, upload 20MB async, reconciliación async); Seguridad (NFR5–9: TLS, sheets no públicos, RBAC server-side, credenciales fuera del repo, expiración de sesión); Confiabilidad (NFR10–14: fallas de sync loggeadas sin datos parciales, retry de token, rechazo limpio de extracciones fallidas, audit log append-only, backup diario); Integración (NFR15–19: token transparente, capa de storage abstracta, extracción sin config por banco, OAuth único, schema Gemini validado).

`epics-segundo-rut.md` agrega **NFR20** (aislamiento entre libros, 0 diffs EAG) y **NFR21** (bean-check verde) — tampoco existen en el PRD.

### Additional Requirements

- Compliance: Ley 19.628 (datos financieros privados); Laudus sigue siendo la fuente autoritativa para SII; sin KYC/AML/PCI.
- Constraints técnicos del PRD: storage Phase 1 = Google Sheets, Phase 2 = PostgreSQL — **SUPERSEDIDO** por el pivot c4 (Beancount como fuente única; Sheets/Supabase deprecados 2026-06). architecture-c4.md manda.
- Desktop-only Chrome, SPA, backend Python FastAPI.

### PRD Completeness Assessment

El PRD está completo y claro **para su alcance original (FR1–44)**, pero está desactualizado en dos ejes respecto del check actual:

1. **Gap de trazabilidad formal (conocido, aceptado):** los FR45–FR56 del Segundo RUT no están en el PRD. El inventario de requisitos del alcance vive en `epics-segundo-rut.md` con base en discovery + análisis contable de Valentina. Impacto práctico: bajo — la cadena discovery→FRs→stories es trazable; el costo es que el PRD ya no es el índice único de FRs del producto.
2. **Supuesto de entidades fijas:** FR12 enumera las 5 entidades EAG como lista cerrada. El alcance Segundo RUT rompe ese supuesto (agrega FFCC/JAB como grupo hermano) — exactamente lo que FR45–FR47 resuelven. No es contradicción: es extensión consciente.
3. **Referencias de storage obsoletas** (Sheets/PostgreSQL): supersedidas por el pivot Beancount documentado en architecture-c4.md y sprint-change-proposal-2026-06-10. Sin impacto en el alcance nuevo.

**Recomendación (no bloqueante):** en la próxima edición del PRD, anexar FR45–56/NFR20–21 o referenciar `epics-segundo-rut.md` como extensión de alcance, para restaurar el índice único.

## Epic Coverage Validation

### Coverage Matrix (alcance Segundo RUT — FR45–FR56)

| FR | Requisito (resumen) | Cobertura | Status |
|---|---|---|---|
| FR45 | Grupos de consolidación explícitos; EAG no absorbe otras entidades | Epic 11, Story 11.1 (AC 2) | ✓ Covered |
| FR46 | Grupo RUT2 [FFCC, JAB] separado del grupo EAG | Epic 11, Story 11.1 (AC 3) | ✓ Covered |
| FR47 | Entidades nuevas en VALID_ENTITIES/selector | Epic 11, Story 11.2 | ✓ Covered |
| FR48 | Árbol RUT2 (308 hojas) pre-creado con mapeo mecánico por raíz | Epic 12, Story 12.3 (AC 1) | ✓ Covered |
| FR49 | Cuenta Equity de apertura del libro | Epic 12, Story 12.3 (AC 2) | ✓ Covered |
| FR50 | Entidad/libro como parámetro explícito del import | Epic 12, Story 12.2 (AC 1) | ✓ Covered |
| FR51 | Índice (entidad, código) — colisión de 18 códigos | Epic 12, Story 12.2 (AC 2) | ✓ Covered |
| FR52 | Assert de nombre de empresa, sin validación DV | Epic 12, Story 12.2 (AC 3) | ✓ Covered |
| FR53 | Import histórico + apertura desde fecha de corte | Epic 12, Story 12.4 | ✓ Covered (⏳ bloqueada por contador) |
| FR54 | Reporte dos niveles FFCC/JAB × grupos numéricos | Epic 13, Story 13.1 (AC 1) | ✓ Covered |
| FR55 | TC lumpeada marcada en cuerpo del reporte | Epic 13, Story 13.1 (AC 2) | ✓ Covered |
| FR56 | Reconciliación contra ancla | Epic 12, Story 12.5 (DoD del epic) | ✓ Covered (⏳ bloqueada por contador) |

### Missing Requirements

Ninguno dentro del alcance. Los 12 FRs del alcance tienen story y AC específico.

Notas de trazabilidad:
- **FRs en epics pero no en PRD:** los 12 (FR45–56) — gap formal documentado en PRD Analysis, aceptado.
- **FR1–FR44 del PRD:** cubiertos por `epics.md` legacy (Epics 1–10), fuera del alcance de este check por decisión explícita (mayormente implementados; Epics 6, 7, 9, 10 con retro/review cerrados).
- La story 12.1 (clasificación con Valentina) no mapea a un FR — es precondición de proceso que protege FR48/FR54; correcto que no tenga FR propio.

### Coverage Statistics

- Total FRs del alcance: 12
- FRs cubiertos en epics: 12
- Cobertura: **100%**

## UX Alignment Assessment

### UX Document Status

**Not Found** — no existe `*ux*.md` en planning-artifacts (verificado en Document Discovery).

### ¿UX implicado en este alcance?

Sí, pero mínimo y sobre superficies existentes:
1. **Selector de entidad** (Story 11.2): agrega opciones a un componente existente; el AC de estado-vacío-limpio cubre el único caso UX nuevo.
2. **Reporte de gastos RUT2** (Story 13.1): reutiliza el patrón visual del reporte de EAG ya validado en producción; el único elemento de presentación nuevo (marca de TC lumpeada en el cuerpo) está especificado en AC.

### Alignment Issues

Ninguno. La arquitectura existente ya soporta ambas superficies (SPA + FastAPI + motor Beancount multi-entidad); no se introducen componentes UI nuevos.

### Warnings

- ⚠️ Informativa (no bloqueante): si al ejecutar 13.1 se decide que el reporte de RUT2 necesita un layout distinto al patrón EAG (dos sub-entidades en una vista puede pedir jerarquía visual propia), involucrar a la UX designer (Sally) a nivel de story — patrón ya usado en este proyecto (ej. spec embebido en 6.4). No requiere documento UX de alcance completo.

## Epic Quality Review

### Estructura de epics

| Check | Epic 11 | Epic 12 | Epic 13 |
|---|---|---|---|
| Entrega valor de usuario | ✓ (con nota 🟡1) | ✓ | ✓ |
| Independencia (no requiere epics futuros) | ✓ | ✓ (funciona sin 13) | ✓ (usa 11+12, hacia atrás) |
| Stories dimensionadas para sesión única | ✓ (S, XS) | ✓ (mayor = 12.2, M) | ✓ (M) |
| Sin dependencias hacia adelante | ✓ | ✓ (12.3←12.1, 12.4←12.2+12.3, 12.5←12.4) | ✓ |
| Entidades/tablas creadas solo cuando se necesitan | ✓ | ✓ (con rationale, ver abajo) | ✓ |
| ACs Given/When/Then testeables | ✓ | ✓ | ✓ |
| Trazabilidad a FRs | ✓ | ✓ | ✓ |

**Checks especiales:** starter template N/A (brownfield). Indicadores brownfield presentes: puntos de integración con sistema existente explícitos (importador, selector, report_builder), ACs de regresión en toda story que toca EAG (0 diffs / suite verde), sin file churn entre epics (archivos disjuntos por epic).

**Pre-creación del árbol (12.3) vs principio "crear solo cuando se necesita":** desviación deliberada y correcta — FR48 exige el subárbol ANTES de cualquier import porque la creación perezosa es exactamente el mecanismo del bug de colisión (verificado con sonda: sin subárbol pre-creado, los asientos de RUT2 matchean cuentas de EAG en silencio, sin pasar por cuarentena). Rationale documentado en el epics doc.

### Hallazgos por severidad

**🔴 Críticos:** ninguno.

**🟠 Mayores:** ninguno.

**🟡 Menores (3, todos con rationale documentado — no requieren remediación previa):**
1. **Epic 11 tiene título/goal de tono técnico** ("consolidación por grupos"). Se acepta: es una frontera de riesgo real (toca reportes vivos de EAG) y su valor de usuario es la garantía verificable de no-contaminación; la alternativa (fusionarlo en Epic 12) diluiría el checkpoint de cierre que el dueño usa como gate. Adjudicado en elicitación (mesa redonda) y validación del workflow de creación.
2. **Story 12.1 es una story de proceso/decisión** (clasificación firmada con Valentina), sin FR propio y sin código. Se acepta: produce un artefacto versionado que 12.3 consume; omitirla fue la causa de retrabajos en el pasado del proyecto (clasificación EAG). Precondición explícita > dependencia implícita.
3. **Stories 12.4/12.5 dependen de insumos externos (contador).** No es dependencia hacia adelante (es hacia afuera); está mitigada: marcadas ⏳ en el doc, intake se envía al arrancar Epic 11, y 12.5 tiene fallback definido (balance Laudus fin de mes). Riesgo residual: calendario, no estructura.

### Recomendación de calidad

El documento cumple los estándares de create-epics-and-stories. Las tres desviaciones menores son conscientes, documentadas y con justificación verificable — no bloquean implementación.

## Summary and Recommendations

### Overall Readiness Status

**✅ READY** — el alcance Segundo RUT (Epics 11–13) está listo para pasar a implementación.

### Critical Issues Requiring Immediate Action

Ninguno. 0 hallazgos críticos, 0 mayores, 3 menores (todos adjudicados con rationale documentado).

### Recommended Next Steps

1. **Sprint planning** (`bmad-sprint-planning`): incorporar Epics 11–13 a la cola de implementación. Orden: 11.1 → 11.2 → 12.1/12.2 (paralelizables) → 12.3 → [espera contador] 12.4 → 12.5 → 13.1.
2. **Enviar la Sección 1 del intake al contador** al arrancar el Epic 11 (acción de Ary, no de dev) — desbloquea 12.4/12.5. Recordar quitar los bloques de nota interna antes de reenviar (instrucción en el propio intake).
3. **Higiene documental (no bloqueante):** en la próxima edición del PRD, referenciar `epics-segundo-rut.md` como extensión de alcance (FR45–56, NFR20–21) para restaurar el índice único de requisitos.

### Final Note

Esta evaluación encontró **3 hallazgos, todos menores**, en 5 categorías revisadas (inventario documental, análisis de PRD, cobertura de FRs, alineación UX, calidad de epics). Cobertura de requisitos del alcance: 12/12 (100%). Ninguno de los hallazgos requiere corrección previa a la implementación; pueden abordarse en el camino (higiene de PRD) o ya están mitigados (dependencia del contador).

**Assessor:** BMAD check-implementation-readiness workflow · **Fecha:** 2026-07-10 · **Alcance:** Segundo RUT (Fondo Común FFCC/JAB), Epics 11–13
