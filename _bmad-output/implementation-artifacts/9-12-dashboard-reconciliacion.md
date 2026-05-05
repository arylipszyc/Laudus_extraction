---
story: 9.12
title: Dashboard de reconciliación cartola ↔ Laudus
status: ready-for-dev
epic: 9
depends_on: [9.6b, 9.2]
blocks: []
---

# Story 9.12 — Dashboard de reconciliación

## User Story

As Ary (contador interino) — eventualmente como contador externo,
I want a dedicated dashboard view that lists all flagged transactions grouped by discrepancy state (value-mismatch, missing-in-laudus, missing-in-cartola, date-mismatch, description-mismatch, category-mismatch, fx-out-of-tolerance), with filters and per-line actions to resolve each one,
So that I can review and resolve discrepancies manually with clear context (cartola vs Laudus side-by-side), and the ledger gets re-emitted clean post-resolution.

## Context

Story nueva derivada del cierre Q4 (2026-05-05, Opción D — FX cartola-derivada). El motor de matching de 9.6b emite discrepancias a `ledger/_meta/cartola-discrepancies.jsonl` (single source — sin Supabase mirror, decisión 2026-05-05). Esta story es la **vista accionable** sobre ese JSONL.

**Frontend:** página nueva en LAUDUS frontend (React/Vite + Recharts existente).
**Backend:** endpoint nuevo en thin API que parsea el JSONL.
**Sin SQL** — performance OK para cientos/miles de líneas (volumen real esperado del proyecto).

## Acceptance Criteria

**AC1 — Endpoint backend `GET /api/v1/reconciliation/discrepancies` + deep-link por `discrepancy_id`**

**Given** existe `ledger/_meta/cartola-discrepancies.jsonl` con N entradas
**When** el frontend llama `GET /api/v1/reconciliation/discrepancies?state=&year_month=&bank_account_id=&discrepancy_id=`
**Then** el backend parsea el JSONL line-by-line, filtra por query params, y retorna JSON shape:
```json
{
  "discrepancies": [
    {
      "discrepancy_id": "uuid",
      "ts": "2026-05-05T14:30:00Z",
      "state": "value-mismatch",
      "bank_account_id": "...",
      "bank_account_label": "BCI Cta Corriente EAG",
      "year_month": "2026-04",
      "cartola": { "line_no": 12, "date": "2026-04-15", "amount": -45000, "currency": "CLP", "description": "JUMBO" },
      "laudus": { "journal_entry_id": "12345", "date": "2026-04-15", "amount": -47000, "description": "Jumbo Costanera" },
      "fx": { "implied": null, "bcch": null, "deviation_pct": null },
      "resolution": null
    }
  ],
  "summary": { "total": 42, "by_state": { "value-mismatch": 5, "missing-in-laudus": 12, ... } }
}
```
**And** el endpoint solo retorna discrepancias **sin resolución** (el `resolution` field es null) — discrepancias resueltas son audit trail histórico, accesible vía endpoint separado si se necesita
**And** si se pasa `discrepancy_id={uuid}` (deep-link desde Story 9.8 badge), el endpoint retorna esa discrepancia específica (incluso si está resuelta — para soportar drill-down) y la frontend abre el panel de detalle automáticamente
**And** RBAC: requiere rol `contador` o `admin` (family no accede a este dashboard)

---

**AC2 — Endpoint backend `GET /api/v1/reconciliation/history/{discrepancy_id}`**

**Given** una discrepancia que tuvo resolución
**When** se consulta el historial completo de esa discrepancia
**Then** el backend retorna todas las líneas del JSONL con ese `discrepancy_id` (entry original + entry de resolución) en orden cronológico
**And** el frontend muestra el historial cuando el usuario hace drill-down

---

**AC3 — Endpoint backend `POST /api/v1/reconciliation/discrepancies/{discrepancy_id}/resolve`**

**Given** un usuario `contador`/`admin` toma una acción de resolución sobre una discrepancia
**When** el frontend llama `POST .../resolve` con body `{action, justification}`
**Then** el backend:
  1. Valida la acción (∈ tabla de acciones por estado, AC4)
  2. Appendea entrada de resolución al JSONL (`discrepancy_id` referenciando original)
  3. Invoca a Story 9.6b `re_emit_after_resolution(discrepancy_id)` para regenerar el `.beancount` correspondiente
  4. Espera que `bean-check` pase
  5. Commit + push (mensaje `[reconciliation] resolve {discrepancy_id}: {action}`)
  6. Retorna `{"status": "resolved", "commit_sha": "..."}`
**And** si `bean-check` falla → rollback (revert JSONL append + revert .beancount changes) + retorna 500 con error
**And** RBAC: requiere `contador` o `admin`

---

**AC4 — Acciones por estado**

**Given** la tabla de acciones permitidas por estado (la UI las expone como botones contextuales)
**When** un usuario interactúa con una discrepancia
**Then** las acciones disponibles son:

| Estado | Acciones permitidas |
|---|---|
| `value-mismatch` | `accept-cartola` (importar con valor cartola, fix Laudus en ERP por separado) / `accept-laudus` (descartar cartola, fix manualmente cartola fuera de scope) / `escalate` (no resolver ahora — queda pendiente) |
| `missing-in-laudus` | `confirm-cartola-only` (Laudus se actualizará en próximo sync) / `escalate` |
| `missing-in-cartola` | `confirm-laudus-only` (sin USD original) / `escalate` |
| `date-mismatch` | `accept-cartola-date` / `accept-laudus-date` / `escalate` |
| `description-mismatch` | `accept-cartola-description` / `accept-laudus-description` / `merge` (combinación manual con texto custom) / `escalate` |
| `category-mismatch` | `accept-cartola-category` / `accept-laudus-category` / `manual-category` (edit + selecciona del plan) / `escalate` |
| `fx-out-of-tolerance` | `accept-derived-fx` (la implícita queda) / `accept-bcch-fx` (recalcular usando BCCh) / `manual-fx` (input custom + justification) / `escalate` |

**And** `escalate` no cierra la discrepancia — solo agrega comentario `escalated_at` para seguimiento
**And** todas las acciones (excepto `escalate`) requieren `justification` ≥ 10 caracteres en el body

---

**AC5 — Vista frontend `ReconciliationPage.tsx` + soporte deep-link**

**Given** un usuario contador/admin navega a `/reconciliation` (con o sin `?discrepancy_id={uuid}`)
**When** la página carga
**Then** se muestra:
  - Header con título "Reconciliación cartola ↔ Laudus" + sync timestamp del último import
  - Resumen: chips por estado con conteos (`value-mismatch: 5`, `missing-in-laudus: 12`, etc.) — clickeable para filtrar
  - Filtros: dropdown estado, dropdown bank_account, dropdown year_month, dropdown threshold (solo aplicable a fx-out-of-tolerance)
  - Tabla principal con columnas: fecha (cartola), monto USD, monto CLP, FX implícita, FX BCCh, %dev, estado, fuente cartola, fuente Laudus, descripción cartola, descripción Laudus, **columna acción** (botones contextuales según AC4)
  - Pagination: 50 líneas por página
**And** si la URL incluye `?discrepancy_id={uuid}`, la página abre automáticamente el drill-down (AC6) de esa discrepancia al cargar (sin requerir click manual)

---

**AC6 — Drill-down de una línea**

**Given** un usuario clickea sobre una línea de la tabla
**When** se abre el panel lateral o modal
**Then** se muestra:
  - Información completa de la cartola entry (todos los campos)
  - Información completa de la Laudus entry (si aplica)
  - Cálculo FX (si aplica): `fx_implied`, `fx_bcch`, `fx_deviation_pct`
  - Historial completo de la discrepancia (vía endpoint AC2 — incluye entry original + cualquier escalation previa)
  - Botones de acción contextuales (los de AC4)
  - Campo `justification` (textarea, requerido para acciones excepto `escalate`)
  - Botón "Confirmar acción" — dispara `POST .../resolve`

---

**AC7 — Re-emit del archivo `.beancount` post-resolución**

**Given** la acción se confirma exitosamente (AC3 OK)
**When** el backend re-emite el archivo
**Then** el archivo `imports/cartolas/{slug}.beancount` correspondiente se regenera con la directiva ajustada
**And** `bean-check` pasa post-re-emit
**And** la línea desaparece del dashboard (filter `resolution IS NULL` la oculta) — refrescar página o re-fetch automático

---

**AC8 — Manejo de discrepancias sin Laudus disponible**

**Given** una discrepancia `missing-in-laudus` (cartola tiene la línea, Laudus no)
**When** el usuario elige `confirm-cartola-only`
**Then** la Transaction emitida en `imports/cartolas/{slug}.beancount` mantiene flag `*` (confirmada por usuario) en vez de `!`
**And** se appendea metadata `resolution_note: "confirmed-cartola-only-{ts}"` a la directiva
**And** si en futuro sync de Laudus aparece la línea matching → 9.6b detecta dedup por amount+date+description y no duplica (mecanismo de dedup ya implementado en 9.4 + 9.6a)

---

**AC9 — Chip global "Reconciliaciones pendientes" en Header (severidad diferenciada)**

**Given** hay discrepancias sin resolver
**When** un usuario `contador` o `admin` abre cualquier página del frontend
**Then** el header muestra un chip con conteo total: `⚠ {N} reconciliaciones` (click → navega a `/reconciliation`)
**And** **color del chip determinado por severidad:**
  - **Default amber** (`text-amber-600 bg-amber-50`) cuando todas las discrepancias pendientes son no-bloqueantes
  - **Rojo** (`text-red-600 bg-red-50`) si entre las N pendientes hay **≥1 en estado bloqueante**: `value-mismatch` (línea NO se importa) o `fx-out-of-tolerance` (FX derivada >5% de BCCh — atención alta)
**And** el **conteo del chip muestra el total de discrepancias pendientes**; el **color refleja "el caso más grave"** presente en el conjunto
**And** **tooltip al hover según color:**
  - Amber: *"{N} diferencias entre cartola y Laudus para revisar."*
  - Rojo: *"{N} diferencias entre cartola y Laudus — {M} con valores que no cuadran (bloqueante)."* (donde M = conteo de bloqueantes)
**And** chip oculto cuando `N = 0` (coherente con chip de Story 9.8 AC10)
**And** este chip es complementario al chip "Categorías pendientes" de Story 9.8 (smart_importer flag `!`); ambos pueden coexistir y el header los renderea agrupados o separados según UX (decisión del dev)
**And** rol `family` NO ve este chip

---

**AC10 — Performance OK para volumen real**

**Given** el JSONL tiene hasta 5000 entradas (estimado upper-bound para 5 años de cartolas con discrepancias)
**When** el endpoint `/discrepancies` se invoca con filtros
**Then** la response llega en < 500ms (parseo lazy + filtros in-memory)
**And** si en el futuro el volumen supera ese threshold, abrir story de optimización (ej.: index secundario, sqlite local, etc.) — no aplica para v1

---

## Tasks / Subtasks

- [ ] Task 1: Endpoint backend `GET /discrepancies` (AC1)
  - [ ] Crear `backend/app/api/v1/reconciliation/router.py`
  - [ ] Función que lee `ledger/_meta/cartola-discrepancies.jsonl` line-by-line (usar generator para no cargar todo a memoria si crece mucho)
  - [ ] Filtros in-memory: state, year_month, bank_account_id
  - [ ] Solo retorna discrepancias con `resolution: null` (las resueltas son audit trail)
  - [ ] Summary: counts por estado, agrupado
  - [ ] RBAC middleware: contador/admin only

- [ ] Task 2: Endpoint `GET /discrepancies/{id}/history` (AC2)
  - [ ] Lee todas las líneas con ese `discrepancy_id`
  - [ ] Retorna en orden cronológico

- [ ] Task 3: Endpoint `POST /discrepancies/{id}/resolve` (AC3 + AC4)
  - [ ] Validador: action ∈ tabla por estado
  - [ ] Justification ≥ 10 caracteres (excepto `escalate`)
  - [ ] Appendea entry de resolución al JSONL
  - [ ] Invoca `re_emit_after_resolution` de 9.6b
  - [ ] bean-check + commit + push
  - [ ] Rollback completo si falla
  - [ ] Tests con fixtures por cada estado × cada acción

- [ ] Task 4: Frontend `ReconciliationPage.tsx` (AC5)
  - [ ] Crear página + ruta `/reconciliation` (gated por rol contador/admin via Story 9.13)
  - [ ] Componentes:
    - `<DiscrepancySummary />` — chips clickeable
    - `<DiscrepancyFilters />` — dropdowns
    - `<DiscrepancyTable />` — tabla paginada con columnas de AC5
    - `<DiscrepancyDrillDown />` — modal/panel lateral
  - [ ] **Soporte deep-link**: leer query param `discrepancy_id` con `useSearchParams`. Si presente, abrir el drill-down de esa discrepancia automáticamente al cargar la página.
  - [ ] Usar React Query existente para data fetching
  - [ ] Estilo coherente con dashboards Epic 3

- [ ] Task 5: Drill-down + acciones (AC6)
  - [ ] Panel lateral o modal según UX preference
  - [ ] Mostrar historial vía endpoint AC2
  - [ ] Botones contextuales por estado
  - [ ] Form `justification` con validación
  - [ ] Loading + error states

- [ ] Task 6: Chip global "Reconciliaciones pendientes" (AC9)
  - [ ] Componente `<PendingReconciliationBadge />` en el header app
  - [ ] Lógica de color según severidad: amber default, rojo si ≥1 estado bloqueante (`value-mismatch` o `fx-out-of-tolerance`)
  - [ ] Tooltips diferenciados por color (ver AC9)
  - [ ] Oculto cuando count=0
  - [ ] Render condicional por rol (`contador` o `admin`) — gated via Story 9.13
  - [ ] Polling cada 5 min (o invalidación post-action via React Query)
  - [ ] Endpoint dedicado `GET /api/v1/reconciliation/count` retorna `{total, blocking}` (necesario para color); o reusa endpoint AC1 con limit 0 (solo summary by_state)
  - [ ] Coexiste con `<PendingCategorizationChip />` de Story 9.8 — agrupar visualmente o separar es decisión del dev

- [ ] Task 7: Tests E2E
  - [ ] Mock JSONL con discrepancias variadas
  - [ ] Test: filtros funcionan
  - [ ] Test: resolve action → JSONL append + re-emit + bean-check
  - [ ] Test: rollback si bean-check falla

- [ ] Task 8: Documentación
  - [ ] `docs/reconciliation-dashboard.md` con runbook para el contador
  - [ ] Actualizar `docs/contador-onboarding-fava.md` (Story 9.3) con referencia al dashboard

---

## Dev Notes

### Input autoritativo

`q4-fx-decision-2026-05-05.md` — decisión Opción D + tabla estados. `bob-x-moishe-epic9-2026-04-30.md` — ítem #5 + ítem #7 (story 9.12 nueva) + ítem #9 (sin Supabase). `9-6b-...md` — emisor del JSONL que esta story consume.

### Sin SQL — JSONL como source

El backend lee `ledger/_meta/cartola-discrepancies.jsonl` directo. No hay tabla SQL.

Performance: parseo lazy line-by-line. Para 5000 líneas: < 100ms. Filtros in-memory después del parseo.

Si el volumen crece más allá de eso (no se espera), se evalúa indexación local (sqlite, redis cache, etc.) en story aparte.

### Re-emit del archivo .beancount

La función `re_emit_after_resolution` vive en Story 9.6b (Task 6 de 9.6b). Esta story (9.12) la **invoca** desde el endpoint resolve. Re-emit:
1. Lee la cadena de discrepancies del JSONL (original + resolución)
2. Determina nuevo estado del file
3. Regenera `imports/cartolas/{slug}.beancount` write-and-replace
4. bean-check + git commit + push

Mantenemos el contrato single-direction: 9.6b escribe archivos, 9.12 dispara cuando el usuario lo decide.

### RBAC

`family` (Eduardo, Abel) NO accede a este dashboard. Reconciliación es trabajo del contador (interino = Ary, eventual = externo) o del admin (Ary).

Matriz de roles autoritativa: **Story 9.13 — RBAC 3 roles**. Esta story consume los gates: backend endpoint `/reconciliation/*` requiere `contador` o `admin`; frontend chip + página gated por mismo rol.

### UX considerations

- Los 7 estados pueden ser muchos para un usuario contador no-técnico. Considerar agrupar visualmente: "Bloqueantes" (value-mismatch) vs "Informativos" (missing-in-laudus, etc.) vs "FX" (fx-out-of-tolerance).
- El word "discrepancia" es técnico. UX puede preferir "Diferencias" o "Para revisar" en español.
- Sally (UX) podría tomar pase de revisión cuando 9.12 esté implementada.

### Project structure

```
backend/app/api/v1/reconciliation/
  router.py                                # NEW (Tasks 1-3)
  service.py                               # NEW (parser JSONL + filters)
  models.py                                # NEW (Pydantic schemas)
frontend/src/pages/Reconciliation/
  ReconciliationPage.tsx                   # NEW (Task 4)
  components/
    DiscrepancySummary.tsx                 # NEW
    DiscrepancyFilters.tsx                 # NEW
    DiscrepancyTable.tsx                   # NEW
    DiscrepancyDrillDown.tsx               # NEW
frontend/src/components/Header/
  PendingReconciliationBadge.tsx           # NEW (Task 6)
docs/
  reconciliation-dashboard.md              # NEW (Task 8)
```

### Out of scope

- Bulk actions (resolver múltiples discrepancias de una vez) — v2 si Ary lo pide después de uso real.
- Export a CSV/Excel — v2.
- Notificaciones email cuando aparece una discrepancia bloqueante — v2.
- Vista "histórico de resoluciones" (las ya resueltas) — v2 si se necesita.

### References

- [Source: q4-fx-decision-2026-05-05.md — tabla de estados + storage JSONL]
- [Source: bob-x-moishe-epic9-2026-04-30.md — ítem #5, #7, #9 + flags Sally 2026-05-05 (Flag 3, Flag 4)]
- [Source: sally-x-moishe-badges-pendiente-2026-05-05.md — modelo UX híbrido + severidad diferenciada]
- [Source: 9-6b-matching-cartola-laudus-discrepancias.md — emisor del JSONL]
- [Source: 9-2-backend-thin-api-bql.md — patrón de endpoints]
- [Source: 9-8-frontend-thin-api-badge-pendiente.md — chip "Categorías pendientes" complementario]
- [Source: 9-13-rbac-3-roles.md — matriz de roles autoritativa]
