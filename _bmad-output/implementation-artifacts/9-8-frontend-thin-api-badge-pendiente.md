---
story: 9.8
title: Frontend LAUDUS consume thin API + badge "pendiente revisar" (era 4.3)
status: ready-for-dev
epic: 9
depends_on: [9.2]
blocks: []
---

# Story 9.8 — Frontend LAUDUS consume thin API + badge "pendiente revisar"

## User Story

As Ary / Eduardo / Abel,
I want my dashboards to look exactly the same as today (same charts, same drill-downs, same data shape) but with a visible badge "⚠ pendiente revisar" on credit-card transactions whose category isn't confirmed yet,
So that the engine migration is invisible to me except for the new visibility into uncertain categorizations.

## Context

Story 4.3 reformulada bajo c4. Esta story:
- Switch del frontend de Sheets/Supabase directo al thin API (cuando Story 9.2 está done con feature flags activadas).
- Agrega el badge `⚠ pendiente revisar` a las transactions con `flag = "!"` (categorías pendientes — Story 9.7).
- Subsume parcialmente el contenido de Story 5.2 original (review UI) — el contador puede confirmar categorías desde el drill-down si tiene rol `contador`.

Restricción explícita: **dashboards visualmente idénticos** — mismas charts Recharts, mismos drill-downs, mismos filtros entity/date. Lo único que cambia para family es el badge visual sobre tx flagged.

## Acceptance Criteria

**AC1 — Frontend consume thin API en lugar de paths legacy**

**Given** las env vars `USE_BEANCOUNT_ENGINE_*` están `true` en backend (Story 9.2)
**When** el frontend hace requests a `/api/v1/balance-sheets`, `/api/v1/ledger-entries`, `/api/v1/income-statement`, `/api/v1/equity-variation`
**Then** las respuestas vienen del ledger Beancount via BQL
**And** el frontend NO tiene cambios estructurales — solo cambia la fuente server-side
**And** los hooks React Query existentes (`useBalanceSheet`, `useLedgerEntries`, etc.) NO se modifican

---

**AC2 — Dashboards Epic 3 visualmente idénticos**

**Given** los 4 dashboards (Activos/Pasivos, Ingresos/Gastos, Estado de Resultado, Variación Patrimonial)
**When** se renderean con datos del thin API
**Then** son visualmente idénticos a la versión pre-c4: mismas Recharts, mismas tablas, misma jerarquía, mismos colores, mismo formato `toLocaleString('es-CL')`
**And** los regression tests visuales (si existen — Playwright/screenshot) pasan sin cambios

---

**AC3 — Badge "pendiente revisar" en drill-down**

**Given** una transaction en el drill-down con `meta.flag = "!"` (`category_status` ∈ `suggested|pending`)
**When** se renderiza
**Then** la celda de categoría muestra: `<categoria> ⚠ pendiente revisar` en color amber (`text-amber-600` Tailwind)
**And** hover sobre el badge muestra tooltip: `match_source` + `confidence` ("Sugerida por smart_importer (confianza 0.72) — falta confirmación")

---

**AC4 — Badge en tablas summary cuando aplica**

**Given** una row de Income/Expenses summary que agrupa N transactions, donde M de ellas tienen flag `!`
**When** se renderiza
**Then** la row muestra un mini-badge `⚠ {M}` (compacto, en hover muestra "M de N transacciones pendientes de revisar")
**And** click en el row drill-downea como antes; el detalle muestra cada tx con su badge AC3

---

**AC5 — Drill-down preservado y mejorado**

**Given** Story 3.5 fue deferred (originalmente requería cartolas Phase 2)
**When** la family hace click en un summary de tarjeta de crédito
**Then** ve el drill-down a movimientos individuales (merchant, amount, date, categoría) leídos del ledger
**And** los movimientos vienen de `imports/cartolas/*.beancount` cuando hay cartolas, o del importer Laudus cuando no
**And** las categorías muestran badge `⚠ pendiente revisar` para tx flagged

---

**AC6 — Acción "confirmar categoría" para rol contador**

**Given** el usuario tiene rol `contador` y está en el drill-down con tx flagged
**When** clickea sobre el badge `⚠ pendiente revisar`
**Then** se abre un modal/popover con: dropdown de categorías (filtrado por root Expenses) + amount + description (read-only)
**And** seleccionar una categoría + click "Confirmar" → llama `PATCH /api/v1/transactions/{tx_id}/category` (Story 9.7)
**And** post-success: la tx muestra flag `*` (sin badge) + el dashboard re-fetch (React Query invalidate)

---

**AC7 — Family rol NO ve la acción de confirmar**

**Given** el usuario tiene rol `family` (ex `owner`)
**When** ve el drill-down
**Then** ve el badge `⚠ pendiente revisar` (visibilidad)
**And** NO ve botones/acciones de confirmar (solo el contador puede)
**And** click en el badge muestra solamente el tooltip informativo (sin modal de edit)

---

**AC8 — Frontend respeta empty states**

**Given** un período sin data en el ledger
**When** un dashboard se renderiza
**Then** muestra el mismo empty state que hoy ("No hay datos para el período seleccionado")
**And** ningún chart roto

---

**AC9 — `useFavorites` o storage preservado**

**Given** el frontend tiene state local de filtros (entity + date_range en React Context)
**When** el switch a thin API ocurre
**Then** el state local persiste sin cambios
**And** los filtros se aplican igual que antes (server-side)

---

**AC10 — Badge global "M categorías pendientes" en Header**

**Given** el contador está logueado
**When** carga cualquier dashboard
**Then** el `Header.tsx` muestra un badge `⚠ {M} categorías pendientes` que linkea a `CartolaReviewPage` (o equivalente) — opcional v1, nice-to-have
**And** family NO ve este badge

---

## Tasks / Subtasks

- [ ] Task 1: Verificar que hooks React Query no requieren cambios
  - [ ] Revisar `useBalanceSheet`, `useLedgerEntries`, `useIncomeStatement`, `useEquityVariation`
  - [ ] Confirmar que el shape de respuesta del thin API (Story 9.2) matchea exactamente lo que esperan
  - [ ] Si no matchea: ese es bug de 9.2; reportar a Bob/Moishe en lugar de hackear el frontend

- [ ] Task 2: Componente `<CategoryBadge tx={...} />`
  - [ ] Render: `<categoria> ⚠ pendiente revisar` cuando `tx.meta.flag === "!"`
  - [ ] Tooltip con `match_source` + `confidence`
  - [ ] Color amber Tailwind
  - [ ] Para rol contador: clickeable → abre modal de confirmación

- [ ] Task 3: Componente `<CategorySummaryBadge count={M} total={N} />`
  - [ ] Mini-badge `⚠ {M}` en summary rows
  - [ ] Tooltip `"{M} de {N} transacciones pendientes de revisar"`

- [ ] Task 4: Modal de confirmación (rol contador, AC6)
  - [ ] `<ConfirmCategoryModal tx={...} onConfirm={...} />`
  - [ ] Dropdown de categorías Expense (cargar de `GET /api/v1/plan-de-cuentas/?root=Expenses`)
  - [ ] Submit → `PATCH /api/v1/transactions/{tx_id}/category`
  - [ ] Loading + error handling

- [ ] Task 5: Drill-down adaptado
  - [ ] Modificar `<DrillDownPanel />` (o equivalente) para mostrar `flag` por tx + integrar badges
  - [ ] Preservar sort + filtros existentes
  - [ ] Asegurar regresión 0 en behavior original

- [ ] Task 6: Header badge global (AC10, opcional v1)
  - [ ] `useGlobalPendingCount()` hook → llama `GET /api/v1/categorization/pending` y devuelve count
  - [ ] Render condicional por rol contador
  - [ ] Polling cada 60s o invalidación al PATCH

- [ ] Task 7: RBAC frontend
  - [ ] Asegurar que la acción de confirmar respeta rol (frontend gate); pero el server (Story 9.7) ya gate (defense in depth)

- [ ] Task 8: Tests
  - [ ] Unit: `<CategoryBadge>` con flags `!` y `*`
  - [ ] Unit: modal confirma → llama PATCH con payload correcto
  - [ ] Integration: dashboard render con mix de flags → counts correctos
  - [ ] Snapshot regression: dashboards sin tx flagged son idénticos a baseline pre-c4

---

## Dev Notes

### Input autoritativo

`architecture-c4.md` §5.2 (endpoints actualizados — `PATCH transactions/category`, `GET categorization/pending`). Decisión Q6 (Ary): badge `⚠ pendiente revisar` en frontend LAUDUS.

### Restricción visual

**Cero regresión visual** en los 4 dashboards. La family no debería notar diferencia salvo el badge. Si algo se ve distinto, es bug.

### Subsume parcialmente Story 5.2

Story 5.2 original definía una `CartolaReviewPage` dedicada para revisar pending categorizations. Bajo c4, la review puede hacerse:
- Inline desde el drill-down (este story).
- O en una página dedicada futura (no incluida en Epic 9 — Ary decide si vale la pena).

Por defecto: inline. Si el contador después pide página dedicada, abrir story aparte.

### Out of scope

- Página dedicada de review (`CartolaReviewPage` original) — opcional post-Epic 9.
- Cambios visuales mayores (rediseño de dashboards) — explícitamente NO.
- Editar transactions que NO sean categoría (ej: cambiar amount). Eso es trabajo del contador en Fava (Story 9.3).

### Project structure

```
frontend/src/
  components/
    CategoryBadge.tsx                      # NEW
    CategorySummaryBadge.tsx               # NEW
    ConfirmCategoryModal.tsx               # NEW
  pages/
    BalanceSheetPage.tsx                   # MODIFY (badges en summary)
    IncomeExpensesPage.tsx                 # MODIFY (badges en summary)
    IncomeStatementPage.tsx                # MODIFY (badges en summary)
    EquityVariationPage.tsx                # MODIFY (badges en summary)
  components/DrillDownPanel.tsx            # MODIFY (badges + modal trigger por rol)
  hooks/useGlobalPendingCount.ts           # NEW (opcional v1)
```

### References

- [Source: architecture-c4.md §5.2 — endpoint mapping]
- [Source: architecture-c4.md §4.3 — categorization output shape]
- [Source: bob-x-moishe-epic9-2026-04-30.md — Q6 (badge en frontend)]
- [Source: epics.md Story 4.3 + 5.2 + 5.3 originales — partes preservadas conceptualmente]
