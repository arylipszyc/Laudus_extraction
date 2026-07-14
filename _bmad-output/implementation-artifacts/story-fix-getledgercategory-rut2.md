# Story: Fix `getLedgerCategory` para el libro RUT2 (activos JAB clasificados como gasto)

Status: ready-for-dev

> Story de mantención independiente (sin epic — follow-up de la retro de Epic 13, decisión Ary 2026-07-13). El fix estaba previsto "incluir en 13.1" (retro Epic 12), pero 13.1 fue un xlsx sin charts, así que no aplicaba a su alcance. Se aísla acá.

## Story

As Ary (dueño),
I want que los charts del dashboard del Fondo Común (FFCC/JAB) no cuenten los **activos JAB como gasto**,
so that los totales de gasto e ingreso del libro RUT2 sean correctos cuando mire esas vistas.

## Contexto (verificado en código)

[frontend/src/utils/ledgerAnalytics.ts:48-52] — `getLedgerCategory` primero mira `Categoria1`/`Categoria2` por keywords (`ingreso`/`revenue` → income; `egreso`/`gasto`/`costo`/`expense` → expenses) y, si ninguno matchea, cae a un **fallback por prefijo de código calibrado al plan EAG**:

```ts
if (s.startsWith('4')) return 'income'
if (s.startsWith('5') || s.startsWith('6')) return 'expenses'
return 'other'
```

**El bug (mapeo de raíces RUT2):** FFCC = Assets 1 / Liab 2 / Income 3 / Expenses 4; JAB = Assets 6 / Income 7 / Expenses 8. Los **activos JAB** son código `6xxxxx` con `Categoria1 = "ACTIVO - JAB"`. "activo" no matchea ningún keyword → cae al fallback → `startsWith('6') → 'expenses'` → **un activo JAB se cuenta como gasto** en los charts (`buildLedgerTree`, `computeTotals`, series temporales). Puede cancelar/inflar los totales de gasto de JAB.

FFCC se salva hoy sólo porque su `Categoria1` lleva la palabra (`GASTOS…`/`INGRESOS…`); si alguna cuenta FFCC llegara sin keyword en cat1, el mismo fallback la rompería peor (Expenses FFCC = `4xxxxx` → `startsWith('4') → 'income'`). El fallback EAG **no aplica al plan RUT2**.

Este es el defer "getLedgerCategory calibrado a plan EAG" de la story 11.2, aterrizado.

## Acceptance Criteria

1. **[Activos/pasivos/patrimonio del Fondo Común → `'other'`]**
   **Given** un registro del libro RUT2 con `Categoria1` de balance (ej. `"ACTIVO - JAB"`, `"PASIVO …"`, `"PATRIMONIO …"`) y código de prefijo 1/2/6,
   **When** `getLedgerCategory` lo clasifica,
   **Then** devuelve `'other'` (no entra a income ni expenses), independiente del prefijo numérico.

2. **[Gasto/ingreso reales siguen bien]**
   **Given** cuentas de gasto (FFCC `4xxxxx` cat1 "GASTOS…", JAB `8xxxxx` cat1 "GASTOS…") e ingreso (FFCC `3xxxxx`, JAB `7xxxxx` cat1 "INGRESOS…"),
   **Then** clasifican `'expenses'` / `'income'` respectivamente (hoy ya lo hacen vía keyword; confirmar que el fix no las rompe).

3. **[0 regresión EAG]**
   **Given** los registros de EAG y de hijas (cat1 embebe el tipo, ej. "Egresos Jocelyn…"),
   **When** se clasifica,
   **Then** el comportamiento es **idéntico** a hoy (el fallback por prefijo EAG puede quedarse como último recurso, pero la clasificación observable de EAG no cambia).

4. **[Test de regresión]**
   Test unitario nuevo en el suite frontend con al menos: activo JAB (`accountnumber` prefijo 6, cat1 "ACTIVO - JAB") → `'other'`; gasto JAB (prefijo 8, cat1 "GASTOS…") → `'expenses'`; y un caso EAG existente sin cambio.

5. **[Gates]**
   `cd frontend && npm run typecheck` (`tsc -b`) + `npm run test` verdes. **NUNCA** `tsc --noEmit` (project-context / CLAUDE.md).

## Enfoque sugerido (mínimo, no prescriptivo)

Antes del fallback por prefijo, agregar un check de `Categoria1`/`Categoria2` para las categorías de balance del plan RUT2 (`activo`, `pasivo`, `patrimonio`) → `'other'`. Eso neutraliza el activo JAB por dato (cat1), sin depender del prefijo y sin tocar el path EAG. Alternativa: hacer el fallback book-aware — más invasivo, no requerido por los ACs.

## Qué NO hacer

- NO reescribir el motor de charts ni el shape de datos.
- NO tocar el reporte xlsx de 13.1 (esto es sólo dashboards).
- NO cambiar el comportamiento observable de EAG (AC3).
- NO validar con `tsc --noEmit`.

## References

- [Source: frontend/src/utils/ledgerAnalytics.ts:28-53] — `getLedgerCategory`, fallback por prefijo EAG
- [Source: _bmad-output/implementation-artifacts/epic-13-retro-2026-07-13.md#Action Items] — origen de la story
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — defer 11.2 "getLedgerCategory calibrado a plan EAG"
- [Source: _bmad-output/implementation-artifacts/12-4-import-historico-fondo-comun.md] — hallazgo original (activos JAB → 'expenses')
