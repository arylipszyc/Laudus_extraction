---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments:
  - _bmad-output/project-context.md
  - _bmad-output/implementation-artifacts/sprint-status.yaml
workflowType: 'research'
lastStep: 1
research_type: 'technical'
research_topic: 'Migración de family-office-eag a Odoo Community self-hosted'
research_goals: 'Pros/cons de migrar vs seguir con el stack actual; costo/esfuerzo realista para un único encargado no-desarrollador (vibe coding); qué se reutiliza y qué no; recomendación final con criterios objetivos'
user_name: 'Ary'
date: '2026-07-10'
web_research_enabled: true
source_verification: true
---

# Research Report: technical

**Date:** 2026-07-10
**Author:** Ary
**Research Type:** technical

---

## Research Overview

**Pregunta:** ¿conviene migrar family-office-eag (FastAPI + React + Beancount, en producción y validado al peso contra el contador) a Odoo Community self-hosted, operado por una sola persona sin perfil de desarrollador?

**Respuesta corta: NO (confianza alta).** El corte entre Odoo Community y Enterprise pasa exactamente por encima de lo que la app necesita: la conciliación bancaria automatizada, los reportes contables (Balance/P&L), la consolidación multi-entidad (la próxima etapa del proyecto: segundo RUT) y el OCR son Enterprise-only o directamente no existen para cartolas chilenas. Todo el valor diferencial del proyecto seguiría siendo código custom — solo que escrito dentro de un framework ERP con upgrades mayores forzados, en vez de en una app propia de ~11K líneas que ya está terminada. Y el self-hosting agrega 15–25 h/mes de operación tipo sysadmin, el peor terreno posible para el perfil del operador. Se reutilizaría el conocimiento (specs, prompts Gemini, lógica de reconciliación como diseño, datos) pero se tiraría el 100% del código, los ~750 tests y — lo más caro — la validación en producción. Llegar a paridad tomaría ~6–10+ meses.

Ver §6 para la recomendación completa y los 4 criterios objetivos bajo los cuales Odoo SÍ tendría sentido (el principal: si algún día la decisión pasa a ser *reemplazar Laudus*, evaluar Odoo Enterprise con partner — no Community solo). Metodología y fuentes en §7.

---

<!-- Content will be appended sequentially through research workflow steps -->

## Technical Research Scope Confirmation

**Research Topic:** Migración de family-office-eag a Odoo Community self-hosted (gestionado por Ary, NO Odoo.sh ni Enterprise)
**Research Goals:**

1. Pros y contras de migrar vs seguir con el stack actual (FastAPI + React + Beancount/Fava, deploy en Render, en producción validado al peso).
2. Costo/esfuerzo realista de la migración considerando que Ary es el único encargado y no es desarrollador (vibe coding), incluyendo el costo de operar/mantener un Odoo self-hosted (upgrades, backups, seguridad, hosting).
3. Qué se puede reutilizar del proyecto actual y qué no.
4. Recomendación final con criterios objetivos (en qué escenario Odoo SÍ tendría sentido).

**Preguntas críticas a responder:**

1. ¿Odoo Community self-hosted cubre los casos de uso reales (espejo de Laudus vía API, extracción Gemini de cartolas chilenas en PDF, reconciliación con tolerancias/FX BCCh, desglose TC, dashboards read-only para family, colaboración owner-contadora)? ¿Cuánto es out-of-the-box vs módulos custom?
2. ¿Qué significa para un no-desarrollador solo mantener Odoo self-hosted vs el estado actual (Render managed, texto plano en git)?
3. ¿Qué queda fuera de Community en la versión actual (conciliación bancaria automatizada y otros features contables Enterprise-only)?
4. ¿Qué se reutiliza y qué se tira?
5. Costo de oportunidad: cuánto tardaría un vibe-coder solo en llegar a paridad funcional en Odoo.
6. Recomendación final con criterios objetivos.

**Contexto de la decisión:** sugerencia externa ("sería mejor hacerlo con Odoo") tras poco research; si se migra, sería un proyecto greenfield limpio, NO un correct-course del actual.

**Metodología:**

- Datos web actuales con verificación rigurosa de fuentes (docs oficiales Odoo, OCA, comparativas Community/Enterprise)
- Validación multi-fuente para las afirmaciones críticas (especialmente el corte Community vs Enterprise en contabilidad)
- Niveles de confianza para información incierta
- Verificación contra el repo real (c:\dev\bmad-workspace-new\family-office-eag) para el análisis de reutilización

**Scope Confirmed:** 2026-07-10 (alcance pre-confirmado por Ary en el pedido original — sesión autónoma)

---

## 1. Cobertura funcional: ¿qué cubre Odoo Community de lo que la app hace HOY?

Este es el corazón de la decisión. La versión actual de Odoo es la 19 (docs oficiales 19.0 activas). El hallazgo estructural, verificado contra múltiples fuentes independientes, es que **el corte Community/Enterprise pasa exactamente por encima de las funciones que esta app necesita**:

### 1.1 El corte Community vs Enterprise en contabilidad

- **Community trae "Invoicing", no "Accounting"**: la app de Contabilidad completa (libro mayor con reportes dinámicos, balance, estado de resultados, dashboards contables) es Enterprise. En Community, el motor de asientos existe (double-entry, journal entries) pero **sin Balance Sheet ni P&L nativos** — se necesitan módulos de terceros (OCA `account_financial_report`). _Fuentes: [foro oficial Odoo](https://www.odoo.com/forum/help-1/accounting-community-vs-enterprise-271286), [Cudio](https://www.cudio.com/blog/odoo-community-vs-enterprise), [Tirnav](https://tirnav.com/blog/odoo-enterprise-vs-community-2026)_
- **El widget de conciliación bancaria fue REMOVIDO de Community** desde Odoo 16/17: sin el módulo OCA `account_reconcile_oca`, no hay interfaz de conciliación en absoluto. El módulo OCA la reinstala, pero es conciliación **manual** — el matching automático inteligente es Enterprise. _Fuentes: [OCA/account-reconcile](https://github.com/OCA/account-reconcile), [app store OCA](https://apps.odoo.com/apps/modules/16.0/account_reconcile_oca), [guía LedgerLabs](https://theledgerlabs.com/odoo-bank-reconciliation-guide/)_
- **Sincronización bancaria automática (Plaid/Yodlee) y OCR con IA de documentos = Enterprise-only**. Y además irrelevantes para el caso: ningún agregador cubre cartolas de bancos chilenos en PDF — exactamente la conclusión del research previo del proyecto (2026-06-10: ningún prebuilt lee cartola chilena). _Fuentes: [Cudio](https://www.cudio.com/blog/odoo-community-vs-enterprise), [Technaureus](https://www.technaureus.com/blog-detail/comparison-between-odoo-community-accounting-and-e)_
- **Consolidación multi-entidad = Enterprise-only**. Cita textual de la comparativa: "en el momento en que tenés una segunda entidad legal, Community deja de ser la herramienta correcta". **Esto choca de frente con la próxima etapa ya decidida del proyecto: el segundo RUT como entidad hermana de EAG con consolidación por grupos.** _Fuente: [oec.sh](https://oec.sh/blog/odoo-community-vs-enterprise)_
- **Odoo Studio (personalización no-code) = Enterprise-only**. En Community, TODA personalización es desarrollo: módulos Python + XML + OWL/QWeb. Para un no-desarrollador esto elimina la única vía "sin código" de Odoo. _Fuentes: [Odoo Studio oficial](https://www.odoo.com/app/studio), [DeployMonkey](https://deploymonkey.com/blog/odoo-studio-customization-nocode)_
- **Localización chilena**: `l10n_cl` (plan de cuentas, impuestos SII) existe en Community; `l10n_cl_edi` (facturación electrónica SII) y `l10n_cl_reports` (F29, balance tributario) requieren certificación y/o Enterprise. Para este proyecto es casi irrelevante: **Laudus sigue siendo el ERP ante el SII** — la app es un espejo, no emite DTEs. _Fuente: [docs oficiales localización Chile 19.0](https://www.odoo.com/documentation/19.0/es_419/applications/finance/fiscal_localizations/chile.html)_

### 1.2 Mapeo caso de uso → cobertura en Odoo Community

| Caso de uso actual (en prod, validado) | ¿Odoo Community lo trae? | Qué habría que construir |
|---|---|---|
| Espejo de Laudus vía API (cron incremental, ventana solapada) | ❌ No | Módulo custom o script externo contra la API XML-RPC/JSON-RPC de Odoo (la API sí está en Community). Toda la lógica de sync se reescribe. |
| Extracción Gemini de cartolas chilenas PDF | ❌ No (el OCR IA es Enterprise y no lee cartolas chilenas) | Módulo custom que llame a Gemini — el prompt/parser se porta, el wiring es nuevo |
| Reconciliación cartola-vs-Laudus con tolerancias, períodos, FX BCCh ±5% | ❌ No (widget OCA = manual; el motor con tolerancias/BCCh no existe en ningún Odoo) | Módulo custom completo — es la lógica más fina del proyecto (6.5b period-aware, padding ±3d, fx heredado) |
| Desglose TC dos estados (lump → itemizado, TC:Real, FX derivado) | ❌ No | Módulo custom completo |
| Dashboards read-only para rol family | ⚠️ Parcial | Vistas Odoo dan listas/pivots genéricos; los dashboards actuales (Activos/Pasivos, gastos itemizados por hija) = QWeb/OWL custom. Sin Studio, es código. |
| RBAC 3 roles con Google OAuth | ⚠️ Parcial | Odoo trae usuarios/grupos y OAuth Google configurable — esto SÍ es out-of-the-box razonable |
| Comentarios owner↔contadora anclados a transacción (Epic 7) | ⚠️ Parcial | Odoo Chatter da mensajería por registro gratis — cubre el caso básico si las tx viven como asientos Odoo (el ancla 3-capas resistente a re-import no existiría, pero quizás no haría falta) |
| Editor del contador (hoy Fava + bean-check) | ⚠️ Distinto | Odoo reemplaza Fava con sus formularios de asientos — funcional, pero la contadora pierde el flujo texto-plano/git ya adoptado |
| Reporte de gastos que cuadra peso-por-peso con el contador | ❌ No nativo en Community (sin P&L) | OCA `account_financial_report` + re-validación completa de paridad desde cero |

**Conclusión de cobertura (confianza ALTA, multi-fuente):** lo que Odoo regala (formularios, usuarios, chatter, asientos) es la parte que ya está construida y barata. Lo que constituye el valor diferencial del proyecto — extracción de cartolas chilenas, reconciliación con tolerancias, desglose TC, paridad con Laudus — **es código custom en cualquier escenario**; en Odoo sería código custom *dentro de un framework ERP grande*, en vez de código custom en una app chica ya terminada.

### 1.3 Desajuste de categoría (hallazgo de arquitectura)

Odoo es un ERP: está diseñado para SER el sistema de registro. La regla de oro de este proyecto es la inversa: **Laudus es y sigue siendo el ERP; la app es un espejo fiel + capa de valor** (reconciliación, reportes, colaboración). Migrar a Odoo significa operar un segundo ERP completo (PostgreSQL, workers, framework de módulos, ciclo de upgrades) para usarlo como... espejo read-mostly de otro ERP. Es traer una fábrica para usar una mesa. El motor actual (Beancount: texto plano, git, bean-check, ~6.000 asientos) es órdenes de magnitud más simple de operar y ya demostró paridad al peso.

---

## 2. Operación self-hosted: qué significa para un no-desarrollador solo

Comparación del costo operativo real (verificado contra guías de hosting/administración Odoo 2026):

### 2.1 Carga de mantenimiento Odoo self-hosted

- **15–25 horas/mes** de mantenimiento típico: parches de seguridad del OS y de Odoo, renovación SSL, verificación de backups, revisión de logs, optimización de PostgreSQL, monitoreo. Con picos de **20–40 horas por upgrade de versión mayor**. _Fuente: [skysize.io](https://www.skysize.io/blog/guides-5/odoo-hosting-options-in-2026-shared-managed-or-self-hosted-30)_
- **Upgrade mayor obligatorio cada ~2–3 años** (Odoo soporta las últimas 3 versiones mayores y saca una por año). Para Community self-hosted **no hay herramienta oficial gratuita de migración de base de datos entre versiones mayores**: la vía es [OpenUpgrade](https://github.com/OCA/OpenUpgrade) (herramienta comunitaria, proceso técnico con scripts de migración por módulo) o pagar el servicio de Odoo (que requiere contrato Enterprise). Cada módulo custom debe portarse a mano a la nueva versión. _Fuentes: [docs oficiales upgrade 19.0](https://www.odoo.com/documentation/19.0/administration/upgrade.html), [oec.sh](https://oec.sh/blog/managed-vs-self-hosted-odoo)_
- **Seguridad = administración Linux real**: firewall, fail2ban, control de accesos PostgreSQL, hardening del reverse proxy. Cita textual de la guía de trade-offs: *"si no tenés experiencia administrando Linux, un servidor self-hosted mal configurado es un pasivo"* y *"dueños de negocio y equipos no técnicos deberían mirar otra cosa"*. _Fuentes: [oec.sh](https://oec.sh/blog/managed-vs-self-hosted-odoo), [opsily](https://opsily.com/blog/self-hosted-odoo)_
- La responsabilidad de protección de datos cae 100% en el operador (relevante: datos financieros de la familia; en Chile, Ley 21.719).

### 2.2 Estado actual (línea base)

- Render managed: la plataforma parchea OS, provee TLS, reinicia procesos, corre los crons. Plan Standard 2GB ≈ USD 25/mes (decisión ya tomada tras el review de estabilidad 2026-07-06/07).
- El "estado" del sistema es texto plano en git: backup = el propio repo (más su historial completo); restore = `git clone`. No hay base de datos que migrar entre versiones, ni schema, ni workers.
- Costo de mantenimiento observado: cercano a cero horas/mes de infra (el trabajo va a features, no a operación).

### 2.3 Comparación directa

| Dimensión | Hoy (FastAPI+Beancount en Render) | Odoo Community self-hosted |
|---|---|---|
| Hosting | ~USD 25/mes, managed | VPS ~USD 15–50/mes, **auto-gestionado** (o managed Odoo hosting USD 50–150+/mes, que contradice "gestionado por mí") |
| Horas de operación/mes | ~0 (managed) | 15–25 h/mes documentadas |
| Upgrades | Sin ciclo forzado; dependencias Python a demanda | Mayor cada ~2–3 años, 20–40 h, migración de DB vía OpenUpgrade + porteo de cada módulo custom |
| Backup/restore | git (trivial, probado) | pg_dump + filestore + runbook de restore que hay que mantener y ensayar |
| Superficie de seguridad | Plataforma gestiona el OS | OS + PostgreSQL + Odoo + proxy, todo propio |
| Base de conocimiento del operador | Ya la tiene (construyó el sistema) | Aprender administración Linux/PostgreSQL/Odoo desde cero |

**Conclusión (confianza ALTA):** la migración *aumenta* el costo recurrente real (en horas y riesgo) para un operador solo no-técnico. La licencia gratis de Community se paga en operación.

---

## 3. Análisis de reutilización: qué se lleva y qué se tira

Medido contra el repo real (2026-07-10): backend 75 archivos / ~5.450 líneas de producción + 59 archivos / ~9.680 líneas de tests (~750 tests verdes); frontend 75 archivos / ~6.100 líneas TS/TSX; más `ledger/` (datos, ~6.000 asientos), `pipeline/`, `bootstrap/`, `scripts/`.

### 3.1 SE REUTILIZA (sobrevive a la migración)

| Activo | Forma de reutilización | Valor |
|---|---|---|
| **Conocimiento de dominio** (PRD, epics, ADRs, specs de stories, decisiones de Valentina: TC pasivo dos estados, FX BCCh, híbrido USD) | Directo — es el activo más caro del proyecto y es 100% portable | ⭐⭐⭐ |
| **Prompts + parser Gemini de cartolas** | Portable casi tal cual (es Python que llama a Gemini); en Odoo correría como servicio externo o dentro de un módulo | ⭐⭐⭐ |
| **Lógica de reconciliación como SPEC** (tolerancias ±3d, period-aware, matching, fx heredado, gate BCCh ±5%) | Como especificación para reimplementar — el código en sí no corre en el ORM de Odoo | ⭐⭐ |
| **Datos**: ledger Beancount, fx-bcch-eom.jsonl, cartolas procesadas | Exportables a CSV/asientos importables en Odoo | ⭐⭐ |
| **Integración Laudus** (conocimiento de la API, paginación, journalEntryId=0, ventana solapada) | Como spec + fragmentos de cliente HTTP portables | ⭐⭐ |
| **Escenarios de test** (los ~750 tests como catálogo de casos borde: revolving, cuotas, USD, boundary slop) | Como checklist de aceptación — el código de test no corre | ⭐ |

### 3.2 SE TIRA (costo hundido de la migración)

- **Todo el backend FastAPI** (~5.450 líneas prod): routers, RBAC, ledger service, watcher, locks, jobs async, sync status — Odoo tiene sus propios equivalentes.
- **Todo el frontend React** (~6.100 líneas): dashboards, ReconciliationPage, CartolaUpload, CommentsInbox — se reemplaza por vistas Odoo (OWL/QWeb) reescritas.
- **Los ~750 tests** (~9.680 líneas): atados a FastAPI/Beancount; en Odoo se testea con su framework propio.
- **El motor Beancount completo**: bean-check como validador, Fava como editor del contador, BQL, git como base de datos y auditoría.
- **La infra Render ya endurecida** (review de estabilidad Fases 1–3 de julio: locks atómicos, jobs 202+polling, timeouts, ErrorBoundary — todo eso se re-descubre en Odoo).
- **La validación en producción**: paridad peso-por-peso vs el contador, smoke de cartolas 13/14, materialización TC completa. **Esto es lo más caro de tirar: no es código, es confianza construida con datos reales, y habría que reconstruirla entera contra el nuevo sistema.**

Relación aproximada: se reutiliza el *conocimiento* (~el 30–40% del esfuerzo histórico, en forma de specs y prompts) y se tira el 100% del *código y la validación*.

---

## 4. Costo y esfuerzo de migración (estimación para un vibe-coder solo)

Referencia empírica: el proyecto actual llegó a su estado de hoy (Epics 1–6, 9–10 done, prod validado) en ~3 meses calendario de trabajo intenso asistido por LLM, sobre un stack donde el LLM rinde al máximo (FastAPI/React/pytest = ecosistemas masivamente representados, feedback loop inmediato, todo el código visible y chico).

Factores que CAMBIAN en Odoo para peor (confianza MEDIA-ALTA):

1. **Curva del framework**: módulos Odoo = Python + ORM propio + XML de vistas + OWL/QWeb + convenciones de seguridad por grupos. Los LLM escriben módulos Odoo razonables, pero **depurar dentro de un framework de cientos de miles de líneas es cualitativamente más difícil para un no-desarrollador** que depurar una app propia de 11K líneas: los errores aparecen como stack traces del ORM/vistas, no del código propio. _Fuente: [guía desarrollo módulos custom](https://nerithonx.com/blog/how-to-develop-custom-odoo-modules/)_
2. **Sin Studio** (Enterprise-only) no hay atajo no-code: cada campo, vista y automatización es código.
3. **Instalación/operación previa al primer feature**: servidor, PostgreSQL, workers, proxy, backups — trabajo que hoy es cero.
4. **Re-validación contable completa**: la paridad al peso vs Laudus/contador hay que reconstruirla y re-certificarla con Valentina desde cero.

**Estimación** (rangos, solo-dev vibe coding):

| Fase | Esfuerzo estimado |
|---|---|
| Aprender Odoo + montar y asegurar el servidor | 3–6 semanas |
| Importador Laudus→Odoo + carga histórica 2021→hoy + paridad | 4–8 semanas |
| Pipeline cartolas (Gemini + staging + import) como módulo | 3–6 semanas |
| Motor de reconciliación con tolerancias/períodos/FX + UI | 6–10 semanas |
| Desglose TC dos estados | 3–5 semanas |
| Dashboards family + RBAC + colaboración | 3–5 semanas |
| Re-validación al peso con la contadora | 2–4 semanas |
| **Total a paridad funcional** | **~6 a 10+ meses calendario** |

Más el costo permanente nuevo: 15–25 h/mes de operación + upgrade mayor cada 2–3 años con porteo de todos los módulos custom. Y el costo de oportunidad: Epic 7 a mitad, segundo RUT planificado — todo congelado durante la migración.

---

## 5. Pros y contras

### Pros de migrar a Odoo Community self-hosted

- Plataforma ERP madura con módulos que el proyecto nunca necesitó pero podría querer algún día (compras, documentos, proyectos).
- Chatter (mensajería por registro) gratis — cubriría parte del Epic 7 sin código.
- Comunidad/ecosistema enormes (OCA, foros, partners chilenos disponibles si algún día se contrata ayuda).
- UI administrativa consistente sin construir frontend propio para CRUD genérico.
- Si en el FUTURO la familia quisiera abandonar Laudus y llevar la contabilidad completa en un solo sistema, Odoo es un candidato natural (ver criterios en §6).

### Contras

- **Las funciones que definen el proyecto no vienen incluidas** — conciliación automatizada, reportes contables, consolidación multi-entidad y OCR son Enterprise o simplemente no existen para el caso chileno (§1).
- **La consolidación multi-entidad (próxima etapa: segundo RUT) es explícitamente el punto donde Community "deja de ser la herramienta"** según las propias comparativas del ecosistema.
- Operación self-hosted dimensionada para sysadmins: 15–25 h/mes + upgrades mayores forzados sin herramienta gratuita de migración (§2).
- Sin Studio, toda personalización es desarrollo formal — peor terreno para vibe coding que una app propia y chica.
- Se tira el 100% del código y, más grave, el 100% de la validación en producción (paridad al peso, confianza de la contadora) (§3).
- 6–10+ meses de re-trabajo para volver al punto donde ya se está hoy (§4).
- Desajuste de categoría: un ERP completo usado como espejo read-mostly de otro ERP (§1.3).
- La motivación de origen ("me dijeron tras poco research que sería mejor") no identifica ningún dolor concreto del sistema actual que Odoo resuelva.

---

## 6. Síntesis y recomendación

### Recomendación: NO migrar. Confianza ALTA.

La sugerencia "hacelo con Odoo" tiene sentido superficial (es "contabilidad" y Odoo es "el open source de contabilidad") pero falla al contacto con los tres hechos centrales de este proyecto:

1. **El proyecto no es un ERP** — es un espejo + capa de reconciliación/reportes sobre Laudus, que sigue siendo el ERP. Odoo compite con Laudus, no con esta app.
2. **Todo el valor diferencial es custom en cualquier escenario** (cartolas chilenas vía Gemini, reconciliación con tolerancias, desglose TC, paridad al peso). Odoo no regala nada de eso; solo cambia dónde se escribe el código custom — de una app propia de ~11K líneas ya terminada y validada, a módulos dentro de un framework ERP con ciclo de upgrades forzado.
3. **El perfil del operador es el peor caso para self-hosted**: las guías del propio ecosistema Odoo dicen que self-hosting es para sysadmins con experiencia, y que equipos no técnicos deben evitarlo.

### Criterios objetivos: cuándo Odoo SÍ tendría sentido (revisitar si alguno se cumple)

1. **Si la decisión de negocio pasa a ser reemplazar Laudus** y llevar la contabilidad tributaria completa (SII, DTEs, F29) en un solo sistema propio → evaluar Odoo **Enterprise** con partner chileno de implementación (no Community solo, no self-hosted solo).
2. **Si aparece un equipo**: al menos una persona con experiencia real en administración de sistemas o desarrollo Odoo que absorba las 15–25 h/mes y los upgrades.
3. **Si el alcance explota hacia ERP genérico** (compras, inventario, RRHH, proyectos) donde los módulos estándar de Odoo pesan más que el costo de la migración contable.
4. **Si Laudus desaparece o cambia su API** de forma que el modelo espejo deje de ser viable — ahí se reabre la decisión de plataforma completa.

Ninguna de las cuatro condiciones se cumple hoy.

### Camino sugerido en cambio

Continuar el plan vigente: cerrar Epic 7 (7-1b es la próxima story), validar la app en uso real como ya se decidió, y encarar el segundo RUT sobre el motor Beancount — que, a diferencia de Odoo Community, maneja la consolidación de entidades hermanas con el patrón roots-only ya construido y testeado en este repo. Si la persona que sugirió Odoo tiene un dolor concreto en mente (¿qué problema ve en el sistema actual?), vale la pena capturarlo: los dolores específicos se evalúan mejor que las plataformas en abstracto.

---

## 7. Metodología y fuentes

**Método:** verificación multi-fuente por afirmación crítica (corte Community/Enterprise verificado contra 4+ fuentes independientes incluyendo docs y foro oficial de Odoo; carga operativa contra 3 guías de hosting/administración 2026), más medición directa del repo local para el análisis de reutilización. Niveles de confianza indicados por sección. Limitación: las horas de mantenimiento (15–25 h/mes) provienen de guías de proveedores de hosting — pueden estar algo infladas por interés comercial; incluso descontándolas a la mitad, la conclusión no cambia.

**Fuentes primarias:**

- [Odoo — Editions comparison (oficial)](https://www.odoo.com/page/editions)
- [Odoo Forum — Accounting: Community vs Enterprise (oficial)](https://www.odoo.com/forum/help-1/accounting-community-vs-enterprise-271286)
- [Odoo docs 19.0 — Upgrade (oficial)](https://www.odoo.com/documentation/19.0/administration/upgrade.html)
- [Odoo docs 19.0 — Localización Chile (oficial)](https://www.odoo.com/documentation/19.0/es_419/applications/finance/fiscal_localizations/chile.html)
- [Odoo Studio (oficial)](https://www.odoo.com/app/studio)
- [OCA/account-reconcile (GitHub)](https://github.com/OCA/account-reconcile) · [account_reconcile_oca (app store)](https://apps.odoo.com/apps/modules/16.0/account_reconcile_oca)
- [OCA/OpenUpgrade (GitHub)](https://github.com/OCA/OpenUpgrade)

**Fuentes secundarias:**

- [oec.sh — Community vs Enterprise: What You Actually Need in 2026](https://oec.sh/blog/odoo-community-vs-enterprise) · [oec.sh — Managed vs Self-Hosted Odoo](https://oec.sh/blog/managed-vs-self-hosted-odoo)
- [Cudio — Odoo Community vs Enterprise](https://www.cudio.com/blog/odoo-community-vs-enterprise)
- [LedgerLabs — Odoo Community Edition Guide 2026](https://theledgerlabs.com/odoo-community-edition-guide/) · [LedgerLabs — Bank Reconciliation Guide](https://theledgerlabs.com/odoo-bank-reconciliation-guide/)
- [Technaureus — Community vs Enterprise accounting](https://www.technaureus.com/blog-detail/comparison-between-odoo-community-accounting-and-e)
- [Skysize — Odoo Hosting Options in 2026](https://www.skysize.io/blog/guides-5/odoo-hosting-options-in-2026-shared-managed-or-self-hosted-30)
- [Opsily — Self-Hosted Odoo Guide](https://opsily.com/blog/self-hosted-odoo)
- [Tirnav — Enterprise vs Community 2026](https://tirnav.com/blog/odoo-enterprise-vs-community-2026)
- [DeployMonkey — Odoo Studio no-code guide](https://deploymonkey.com/blog/odoo-studio-customization-nocode)
- [Nerithonx — Custom Odoo module development](https://nerithonx.com/blog/how-to-develop-custom-odoo-modules/)

**Fuentes internas:** repo `family-office-eag` (medición de código 2026-07-10), `_bmad-output/project-context.md`, sprint-status.yaml, research previo de stack de extracción (2026-06-10), memoria del proyecto (segundo RUT, decisión Render, review de estabilidad).

---

**Fecha de cierre del research:** 2026-07-10
**Nivel de confianza global:** ALTO en el corte Community/Enterprise y la recomendación; MEDIO en las estimaciones de esfuerzo (rangos amplios a propósito).
