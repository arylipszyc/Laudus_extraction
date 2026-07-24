# Story: Fix `getLedgerCategory` para el libro RUT2 (activos JAB clasificados como gasto)

Status: done

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

## Dev Agent Record

### Implementation Plan
Enfoque sugerido del spec (mínimo, por dato — no book-aware): agregar, **después** del loop de keywords ingreso/egreso y **antes** del fallback por prefijo, un check de Cat1/Cat2 para las categorías de balance del plan RUT2 (`activo`/`pasivo`/`patrimonio`) → `'other'`. El orden importa: el loop de ingreso/gasto corre primero y gana si una categoría llevara ambas palabras (protege AC2/AC3), luego el nuevo check neutraliza el activo JAB por dato (cat1 "ACTIVO - JAB"), luego cae el fallback EAG intacto (protege AC3).

### Completion Notes
- **Bug reproducido (RED)**: `getLedgerCategory('600001', 'ACTIVO - JAB')` daba `'expenses'` (fallback `startsWith('6')`) — test rojo confirmado antes del fix.
- **Fix (GREEN)**: 6 líneas en [frontend/src/utils/ledgerAnalytics.ts](frontend/src/utils/ledgerAnalytics.ts) — loop de balance-keywords → `'other'`. No toca el path EAG ni el shape de datos ni el reporte xlsx de 13.1.
- **0 regresión EAG (AC3)**: los activos/pasivos/patrimonio EAG tienen prefijo 1/2/3 → hoy ya caían a `'other'` por el fallback; con el fix siguen `'other'`. Suite completa verde sin cambios observables (incl. caso existente `Patrimonio Johanna`).
- **Tests (AC4)**: 5 casos nuevos en `getLedgerCategory` — activo JAB (prefijo 6)→other, pasivo→other, patrimonio→other, gasto JAB (prefijo 8)→expenses, ingreso JAB (prefijo 7)→income.
- **Gates (AC5)**: `cd frontend && npm run typecheck` (`tsc -b`) exit 0; `npm run test` (`vitest run`) 131 passed / 19 files (+5 nuevos, 0 regresiones). NO se usó `tsc --noEmit`.

### File List
- `frontend/src/utils/ledgerAnalytics.ts` — modificado (check de balance-keywords antes del fallback por prefijo)
- `frontend/src/utils/ledgerAnalytics.test.ts` — modificado (5 tests de regresión RUT2)

## Change Log
- 2026-07-14 — Fix `getLedgerCategory`: activos/pasivos/patrimonio del libro RUT2 (FFCC/JAB) ya no caen al fallback por prefijo calibrado a EAG (activo JAB prefijo 6 → `'expenses'`); ahora clasifican `'other'` por Cat1/Cat2. Status → review.

## Review Findings (code-review 2026-07-14 — 3 capas: Blind Hunter / Edge Case Hunter / Acceptance Auditor)

Auditor: **0 violaciones de AC** (AC1–AC5 PASS, AC3 verificado empíricamente contra `ledger/accounts.beancount` — ningún registro EAG/hija con prefijo 4/5/6 lleva una balance-keyword sin keyword de gasto/ingreso; el fix no cambia nada observable en EAG).

- [x] [Review][Patch] Tests `pasivo` y `patrimonio` son vacuos (pasan con el loop nuevo borrado) — APLICADO 2026-07-14: prefijos → `'600002'`/`'400002'` (colisionan con fallback); tsc -b verde, 51/51 tests [frontend/src/utils/ledgerAnalytics.test.ts:146,150] — `'200001'` (prefijo 2) y `'300001'` (prefijo 3) ya caen a `'other'` por el fallback sin tocar el loop nuevo; sólo el test `activo` (prefijo 6) ejercita realmente el fix. Fix: usar prefijos que colisionan con el fallback (4/5/6) para que el test falle si se borra el loop — p.ej. `getLedgerCategory('600002', 'PASIVO CORRIENTE JAB')→'other'` (sin loop: 6→expenses) y `getLedgerCategory('400002', 'PATRIMONIO FFCC')→'other'` (sin loop: 4→income).
- [x] [Review][Defer] Activos prefijo-6 de las hijas EAG (Jocelyn) siguen clasificando `'expenses'` [frontend/src/utils/ledgerAnalytics.ts:56-58] — deferred, pre-existente + fuera de scope (story = RUT2/FFCC/JAB). 16 cuentas reales `Assets:Jocelyn:*` (codes 610xxx/613xxx, cat1 "DISPONIBLE JOCELYN…") no llevan keyword de balance ni de gasto/ingreso → caen al fallback `6→expenses` → los movimientos de caja/inversión de Jocelyn se cuentan como gasto en su vista per-entity. Misma clase de bug que el activo JAB, pero el fix keya en la palabra `activo` (que estas cuentas no tienen). No es regresión (idéntico antes/después → AC3 OK). Candidato a follow-up: fallback book-aware o clasificar assets por dato.
- [x] [Review][Defer] `includes()` + escaneo de Cat2 es más amplio de lo estrictamente necesario (over/under-match latente) [frontend/src/utils/ledgerAnalytics.ts:51-54] — deferred, latente sin trigger en datos actuales. Substring: `'activo'` matchea `inactivo`/`retroactivo`; `'patrimonio'` NO matchea `patrimonial`. Además escanea Cat2, así que un futuro registro de gasto/ingreso con "Compra de Activos"/"Venta de Activos"/"…Patrimonio" en Cat1/Cat2 (hoy sólo aparecen como *nombre de cuenta*, que la función no lee) caería a `'other'` y desaparecería de los totales. Verificado: 0 cuentas prefijo-4/5/6 con balance-substring hoy. Trade-off aceptado del enfoque by-data que sugirió el spec.

Dismiss (1, no persistido): tests `gasto`/`ingreso` RUT2 (líneas 154,158) resuelven vía el primer loop de keywords y no ejercitan el loop nuevo — son documentación válida de AC2 ("el fix no rompe gasto/ingreso"), el reparo de nombre "prefijo 7/8" es ruido (7/8 no están en el fallback).
