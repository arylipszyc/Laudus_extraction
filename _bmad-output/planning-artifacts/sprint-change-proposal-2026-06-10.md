# Sprint Change Proposal — 2026-06-10

**Autor:** Dev (correct-course) · **Aprobador:** Ary
**Disparador:** code-review de alto esfuerzo del feature "reporte de gastos"
**Clasificación de alcance:** Híbrido (Minor + Moderate + Major)

---

## Sección 1 — Resumen del problema

Durante un code-review de alto esfuerzo del feature **"reporte de gastos"** (integrado al backend y ya en `main`, sin haber pasado por planificación BMAD — es código huérfano, no existe en `epics.md`) se destapó un **defecto real en código ya entregado** más una **decisión de arquitectura pendiente** que lo condiciona.

### El defecto: el reporte pierde plata en silencio

Las categorías contables (`Categoria1/2/3`) **no las provee Laudus** — Laudus solo expone número/nombre de cuenta ([bootstrap/sources.py:19](../../bootstrap/sources.py#L19)). Las categorías salen de un **join con un plan de cuentas** que hoy está fragmentado. Una cuenta **creada nueva en Laudus** no está en ese plan → llega al reporte con `Categoria` vacía.

**Reproducido** en `report_builder.py` con una cuenta nueva (prefijo 413 = Casa Sur, con movimiento, sin categoría):

```
cuenta nueva (9.999.999) aparece en celdas: NO APARECE EN NINGUNA PARTE
fila resumen '   Casa Sur': [1000, ...]   ← solo la cuenta vieja categorizada
```

La plata desaparece de **todas** las secciones, sin error:
- **Resumen:** cae en `cat2[""]`, bucket que el loop nunca lee.
- **Detalle:** requiere que el código esté en `template_order.json` (lista fija).
- **TC:** requiere `Categoria2 == "GASTOS PERSONALES"` exacto.
- → `TOTAL EGRESOS` queda corto sin aviso.

### Evidencia de soporte (verificada contra `laudus_dump.json`, 17.916 filas)

- El **prefijo** del número de cuenta determina `Cat1` y `Cat2` **1:1**, pero **NO `Cat3`** (el rubro fino: 7 prefijos con múltiples valores). El número **completo** sí determina `Cat3` 1:1 → por eso una cuenta nueva no se puede auto-clasificar al rubro; requiere criterio humano.
- Las 17.916 filas históricas están 100% categorizadas **porque todas esas cuentas ya están en el plan** — no porque Laudus las traiga.

### La causa raíz arquitectónica: plan de cuentas fragmentado

| Lugar | Estado | Quién lo usa |
|-------|--------|--------------|
| Supabase `plan_de_cuentas` | Dormido (no en `render.yaml`; marcado para deprecación en 9.11) | nadie en prod |
| `ledger/accounts.beancount` (metadata `laudus_categoria*`) | Generado una vez desde Supabase | dashboard (BQL) |
| Columnas `Categoria*` de la hoja `ledger_final` | **Live** (join externo en la planilla) | **reporte** (SheetsRepository) |

Tres fuentes desconectadas que pueden divergir. El reporte lee la hoja; el dashboard lee beancount; Supabase está muerto.

---

## Sección 2 — Análisis de impacto

**Checklist de navegación de cambio (resumen de estados):**

- **§1 Trigger/contexto:** [x] — defecto técnico descubierto en implementación + causa raíz de datos.
- **§2 Impacto en épicas:** [x] — ver abajo.
- **§3 Conflicto de artefactos:** [x] — `epics.md`, `architecture-c4.md`, `sprint-status.yaml`, `deferred-work.md`.
- **§4 Camino a seguir:** [x] — Opción 1 (Direct Adjustment), híbrido. No rollback, no recorte de MVP.

### Impacto en épicas

- **Feature huérfano "reporte de gastos":** no tiene épica. → Se crea **Epic 10 "Reportes para Contadores"** que lo adopta retroactivamente y aloja el trabajo nuevo.
- **Epic 9 (Migración a Beancount):** la **Story 9.11** ("Deprecation Sheets como source of truth") **amplía su scope** para incluir explícitamente que el plan de cuentas (`Categoria1/2/3`) pase a ser **metadata beancount editable** como fuente única.
- **Story 9.7** (categorización smart_importer): **no se modifica**, pero se documenta la distinción — 9.7 categoriza *transacciones* (cartola); el nuevo workflow categoriza *cuentas del plan*. Vecinos, no duplicados.
- Sin invalidación de épicas futuras. Sin resecuenciación mayor (Epic 10 depende de 9.11 para su pieza de fondo, pero el guard interino es independiente).

### Conflicto de artefactos

- **PRD:** sin conflicto con objetivos core. El reporte para contadores es coherente con FR4 (contador edita categorizaciones). MVP no se redefine.
- **Architecture (`architecture-c4.md`):** requiere actualización en §2.x del mapeo de taxonomía — registrar beancount como fuente única del plan de cuentas (decisión de Winston). Ripple: el reporte deberá migrar de SheetsRepository a la lectura beancount cuando 9.11 cierre.
- **UX:** nueva — pantalla/UI de "cuentas sin categorizar" para el workflow (Story 10.3). El guard interino (10.2) es solo una fila de aviso en el xlsx, sin UI nueva.
- **Otros:** `deferred-work.md` recibe los nits no aplicados del code-review.

---

## Sección 3 — Camino recomendado

**Opción elegida: 1 — Direct Adjustment (híbrido).** Agregar una mini-épica y refinar una story existente, dentro de la estructura actual. Sin rollback (el feature aporta valor; el defecto se tapa con un guard chico). Sin recorte de MVP.

- **Esfuerzo:** Bajo (guard) + Medio (workflow) + Medio (consolidación 9.11).
- **Riesgo:** Bajo. El guard es aditivo; la consolidación ya estaba en el roadmap (9.11).
- **Timeline:** el guard interino tapa la fuga de plata de inmediato; la consolidación y el workflow siguen el ritmo de Epic 9.

---

## Sección 4 — Propuestas de cambio detalladas

### 4.1 Nueva Epic 10 — "Reportes para Contadores"

```
Epic 10: Reportes para Contadores
Estado: in-progress (el feature base ya está en main)
Objetivo: generar reportes de gastos para contadores desde el ledger,
          robustos ante cuentas nuevas y desacoplados del plan de cuentas externo.
```

**Story 10.1 — Reporte de gastos (retroactiva, documentar lo entregado)**
- Estado: `done` (ya en `main`: `backend/app/api/v1/reportes/`, `ReportesPage.tsx`).
- AC: documentar el comportamiento actual + los 4 cleanups del code-review ya aplicados.

**Story 10.2 — Guard interino: no perder plata en silencio** *(Minor → Dev/Amelia, AHORA)*
- **Como** contador, **quiero** que el reporte marque la plata de cuentas sin categorizar **para** no recibir totales cortos en silencio.
- AC1: tras armar las secciones, barrer cuentas con movimiento (`have`) no consumidas (`used`).
- AC2: ubicar por **prefijo** el centro de costo (Cat1/Cat2) donde se pueda; lo que no calce va a un balde "sin clasificar".
- AC3: renderizar una fila visible `⚠️ Cuentas sin categorizar: $X` por centro de costo afectado, contada en el total, con el `accountName` de Laudus.
- AC4: test de regresión que reproduzca el caso de la cuenta nueva sin categoría (hoy invisible → debe aparecer).

**Story 10.3 — Workflow de detección + categorización de cuentas nuevas** *(Moderate → PO/SM + Dev; depende de 9.11)*
- **Como** contador, **quiero** que la app avise cuando aparece una cuenta nueva y me deje categorizarla **para** que quede creada en el plan de cuentas.
- AC1: detectar `accountnumber` presentes en el ledger y ausentes del plan.
- AC2: UI que liste las cuentas nuevas y **sugiera Cat1 por prefijo**.
- AC3: el contador fija Cat2/3; al confirmar, se **persiste al plan de cuentas** (fuente única definida por 9.11).
- AC4: el reporte deja de mostrarlas como "sin clasificar" una vez categorizadas.

### 4.2 Refinamiento de Story 9.11 (Epic 9)

- **OLD:** "Deprecation Sheets como source of truth."
- **NEW:** + AC explícito: el plan de cuentas (`Categoria1/2/3`) pasa a ser **metadata `Open` en beancount**, fuente única editable. Eliminar la dependencia del join externo de la planilla `ledger_final` para las categorías. El reporte (Epic 10) migra a leer categorías desde beancount.
- **Pre-requisito:** decisión de diseño de **Winston (Architect)** sobre el "cómo" (formato de metadata, migración de las 3 fuentes, orden vs. población del ledger beancount por 9.4).

### 4.3 `deferred-work.md` — nits del code-review (no aplicados)

Nueva sección `## Deferred from: code review of reporte de gastos (2026-06-10)`:
- route-string-sniffing en `DashboardLayout` (`pathname.startsWith('/reportes')`) — acoplamiento layout↔ruta; bajo impacto para 1-2 rutas.
- 3 pasadas sobre el ledger en `report_builder` (`_laudus_by_code` ×2 + cat1/cat2 + tc_codes) — eficiencia; despreciable a escala family-office.

---

## Sección 5 — Handoff de implementación

| Pieza | Alcance | Handoff | Responsabilidad |
|-------|---------|---------|-----------------|
| Story 10.2 guard interino | Minor | **Dev (Amelia)** | implementar ahora; tapa la fuga de plata |
| Story 9.11 refinada (consolidación plan→beancount) | Major | **Architect (Winston)** | ratificar el diseño antes de implementar |
| Epic 10 + Story 10.3 workflow | Moderate | **PO/SM** (`bmad-create-story`) → **Dev** | crear stories formales; implementar tras 9.11 |
| Nits | — | `deferred-work.md` | hardening pass futuro |

**Secuencia recomendada:** (1) Dev implementa 10.2 ya · (2) Winston ratifica el diseño de 9.11 · (3) SM crea 10.3 + Dev la implementa sobre la base de 9.11.

**Criterio de éxito:** ninguna cuenta nueva creada en Laudus puede desaparecer del reporte sin aviso; el plan de cuentas tiene una única fuente editable; el reporte deja de depender del join externo de Sheets.
