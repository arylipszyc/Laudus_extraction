---
story: 9.15
title: Flip del balance-sheet a Beancount (dashboards Activos/Pasivos)
status: ready-for-dev
epic: 9
depends_on: [9.1, 9.2, 9.11]
gate_condition: paridad-balance-por-entity-mes-confirmada
blocks: []
---

# Story 9.15 — Flip del balance-sheet a Beancount (dashboards Activos/Pasivos)

## Story

As Ary,
I want the balance-sheet dashboards (Activos/Pasivos, `BalanceSheetPage`) to read from the Beancount ledger via BQL instead of the `balance_sheet_{entity}` Sheets tables — by flipping `USE_BEANCOUNT_ENGINE_BALANCE_SHEET` to `true` in production once balance parity per entity × month-end is confirmed,
So that every dashboard reads from the single Beancount source of truth (completing the cutover started with the ledger/report flip), and the credit-card reclassification to Liabilities is reflected correctly.

## Context

Último paso del cutover de dashboards. El reporte y el ledger ya leen Beancount en prod (`USE_BEANCOUNT_ENGINE_LEDGER=true`); el cutover fue **gradual a propósito** y dejó `USE_BEANCOUNT_ENGINE_BALANCE_SHEET` **off** porque el balance-sheet no tenía su propia validación de paridad. **Story 9.11 desbloquea esta** (consolida el plan de cuentas como SoT); 9.15 ejecuta el flip.

Origen del diseño + estado verificado del path: `design-note-balance-sheet-flip-2026-06-17.md`.

**Decisiones de Ary (2026-06-17):**
1. **Prender sin gate de contadora** — el balance va a mostrar las TC como Liabilities (corrección semántica esperada, `architecture-c4.md §2.5`); se prende y se **avisa a la family**, no se espera confirmación previa de la contadora.
2. **Story 9.15 en Epic 9** (migración de dashboard).
3. **Income-statement y equity-variation quedan AFUERA** (placeholders sin BQL ni página real).

## Acceptance Criteria

**AC1 — Paridad del balance por entity × cierre-de-mes**

**Given** el ledger Beancount poblado (importer 9.4 LIVE) y las hojas `balance_sheet_{entity}` aún accesibles
**When** se corre `scripts/parity_check_balance_sheet.py` para cada entity (EAG, Jocelyn, Jeannette, Johanna, Jael) a cada **cierre de mes** del último año
**Then** el diff es **0 CLP** por (entity, cuenta, mes), **salvo diferencias esperadas y documentadas:**
- **TC reclasificadas a `Liabilities`** (modelado correcto Beancount vs modelado viejo Sheets) — diff esperado, NO blocker.
- **Fantasmas stale ya conocidos de Sheets** (asientos anulados en Laudus que Sheets arrastra; documentados en el parity del reporte de 9.11) — solo si afectan cuentas de balance.
**And** la comparación se hace **AT fin-de-mes** (point-in-time), NO sobre un rango que cruce snapshots (ver Dev Notes §semántica)
**And** cualquier diff que NO caiga en esas dos categorías → se investiga y la story NO procede

---

**AC2 — Flip del flag en producción**

**Given** AC1 pasa (diffs explicados)
**When** se setea `USE_BEANCOUNT_ENGINE_BALANCE_SHEET=true` en el servicio backend de Render + se hace redeploy
**Then** el endpoint `GET /api/v1/balance-sheets` lee del ledger vía `balance_sheet_via_beancount`
**And** el redeploy es explícito (`POST /deploys`) — gotcha conocido: el PUT de env-vars NO redeploya solo
**And** el shape JSON no cambia (mismas keys); el frontend no requiere cambios

---

**AC3 — Smoke de los dashboards (regression)**

**Given** el flag on
**When** se navega `BalanceSheetPage` (Activos/Pasivos) por las 5 entidades y períodos (Q1 2026, FY 2025)
**Then** los charts cargan, sin errores, activos y pasivos cuadran con lo esperado
**And** las tarjetas de crédito aparecen como `Liabilities` (cambio esperado, visible) y el balance es coherente con esa reclasificación

---

**AC4 — Aviso a la family del cambio de TC**

**Given** el flip cambia cómo se ven las TC en el balance (pasan a pasivo)
**When** se completa el flip
**Then** Ary avisa a la family del cambio (las TC ahora se muestran como pasivo — modelado contable correcto)
**And** se documenta el cambio en MEMORY (reference) + se nota la decisión de prender sin gate de contadora

---

**AC5 — Rollback documentado**

**Given** algo se rompe post-flip
**When** se decide rollback
**Then** existe runbook (puede sumarse a `docs/rollback-deprecation-sheets.md` o uno propio) con: `USE_BEANCOUNT_ENGINE_BALANCE_SHEET=false` + redeploy → vuelve a Sheets
**And** ejecutable en < 30 minutos

---

## Tasks / Subtasks

- [ ] **Task 1: Script de parity del balance (AC1)**
  - [ ] Crear `scripts/parity_check_balance_sheet.py` (espejo de `parity_check_sheets_vs_beancount.py`): por (entity, cuenta) compara `balance_sheet_via_beancount(AT fin-de-mes)` vs la hoja `balance_sheet_{entity}` vigente
  - [ ] Pinear `date_to` a cierres de mes (no rangos multi-snapshot)
  - [ ] Clasificar diffs: TC→Liabilities (esperado), fantasmas Sheets conocidos (esperado), resto (investigar)
  - [ ] Documentar uso en `scripts/README.md`

- [ ] **Task 2: Correr el parity y clasificar (AC1)**
  - [ ] Correr por las 5 entidades × cierres de mes del último año (`PYTHONUTF8=1` + creds Sheets + `LEDGER_PATH`)
  - [ ] Confirmar que todo diff cae en las categorías esperadas; si no → STOP, investigar
  - [ ] Pegar el resumen en Completion Notes

- [ ] **Task 3: Flip del flag (AC2, AC3)** *(HANDOFF a Ary — deploy, no codeable)*
  - [ ] Render: `USE_BEANCOUNT_ENGINE_BALANCE_SHEET=true` + `POST /deploys`
  - [ ] Smoke de `BalanceSheetPage` por 5 entidades + períodos; verificar TC como Liabilities

- [ ] **Task 4: Aviso + docs (AC4, AC5)**
  - [ ] Ary avisa a la family del cambio de TC
  - [ ] Documentar en MEMORY (reference)
  - [ ] Runbook de rollback (sumar a `docs/rollback-deprecation-sheets.md` o uno propio)

---

## Dev Notes

### Estado actual del path (verificado 2026-06-17 — NO requiere cambios de frontend)

- **Branch del flag** ([dashboard/service.py:28-36](../../backend/app/api/v1/dashboard/service.py)): flag ON → `balance_sheet_via_beancount(ledger, entity, date_from, date_to)`; OFF → hoja `balance_sheet_{entity}` (`repo.get_records`, filtra por rango, sin dedupe).
- **BQL** ([bql_queries.py:56-97](../../backend/app/services/bql_queries.py)): `SELECT account, sum(position) WHERE account ~ "^(Assets|Liabilities|Equity):{entity}" AND date <= {date_to} GROUP BY account`. **Point-in-time AT `date_to`**; `date_from` se ignora. Una fila por cuenta, `is_latest="TRUE"`, `account_id=None`.
- **Endpoint** ([dashboard/router.py:50-66](../../backend/app/api/v1/dashboard/router.py)): `GET /api/v1/balance-sheets`, params `entity`/`date_from`/`date_to`, RBAC = cualquier user autenticado.
- **Frontend** ([BalanceSheetPage.tsx] + [useBalanceSheet.ts]): manda `entity`+rango, agrupa por prefijo (1xxx activos/2xxx pasivos/3xxx equity), **suma `netPosition = debit_balance - credit_balance`** sobre las filas. No usa `account_id`. Shape idéntico en ambas ramas → **cero cambios de frontend**.

### Semántica de fecha — por qué el parity va AT fin-de-mes

El frontend manda un rango y suma todas las filas. Beancount AT `date_to` devuelve **una fila por cuenta** → suma correcta. El path Sheets, si tuviera >1 snapshot por cuenta en el rango, los sumaría (inflado) — hoy no pasa (`pipeline/sync.py` hace `replace_sheet`, no append → un solo snapshot), pero por eso **el parity compara snapshot Beancount AT fin-de-mes vs snapshot vigente en Sheets**, nunca sobre un rango multi-snapshot (daría falso diff).

### El cambio esperado — TC como Liabilities

`architecture-c4.md §2.5`: las tarjetas de crédito en Beancount son `Liabilities:{Entity}:TC:...` (pago TC = `Asset:Bancos → Liability:TC`, modelado correcto) vs el modelado viejo de Sheets. → **El balance-sheet se ve distinto para TC; es la corrección esperada, NO un bug.** Un diff en cuentas TC entre Sheets y Beancount es esperado. Decisión Ary: prender igual + avisar a la family (sin gate de contadora).

### Out of scope (explícito)

- **Income-statement y equity-variation:** flags comentados en `.env.example`, **sin funciones BQL** (`income_statement_via_beancount`/`equity_variation_via_beancount` no existen) y **sin página real** (rutas `/income-statement` y `/equity-variation` → `DashboardPlaceholder`). Migrarlas = trabajo separado (BQL + páginas nuevas).
- **`IncomeExpensesPage`** ya lee Beancount vía `/ledger-entries` (gated por `USE_BEANCOUNT_ENGINE_LEDGER`, on) — no es parte de este flip.
- **Dedupe del path Sheets** (riesgo latente multi-snapshot): moot post-flip.
- **RBAC por entity:** sin control de acceso por entidad; fuera de scope (deferred).

### Dependencias y secuencia

- **Desbloqueada por 9.11** (plan de cuentas como SoT consolidado; debe estar merged).
- **Independiente de 10.3 y 9.14** (camino de promoción/Supabase) → puede ir en **paralelo** a esos una vez cerrada 9.11.
- No requiere cambios de frontend ni nueva infra.

### Riesgos

- **Diff inesperado en AC1** (fuera de TC/fantasmas conocidos): STOP, investigar mapping/entity-pattern; no prender.
- **Entity pattern:** el BQL asume entity como 2º componente del path (`Assets:EAG:...`); cuentas sin jerarquía de entity correcta no matchean → data faltante. Verificar en el parity.
- **Ledger parse error → 503:** si el ledger tiene error de sintaxis, el endpoint devuelve 503 `LEDGER_UNAVAILABLE`. El ledger en prod ya está validado (bean-check en cada import), bajo riesgo.

### Project Structure Notes

```
scripts/
  parity_check_balance_sheet.py    # NEW (espejo del de reporte)
  README.md                        # MODIFY (instrucciones)
docs/
  rollback-deprecation-sheets.md   # MODIFY (sumar pasos del flip) o runbook propio
backend/app/api/v1/dashboard/service.py   # READ (branch ya existe, no cambia)
backend/app/services/bql_queries.py       # READ (balance_sheet_via_beancount ya existe)
```

### References

- [Source: design-note-balance-sheet-flip-2026-06-17.md] — mapeo completo + decisiones
- [Source: architecture-c4.md §2.5 — TC como Liabilities]
- [Source: 9-2-backend-thin-api-bql.md AC3 — balance-sheet BQL; AC5/AC6 income/equity deferred]
- [Source: 9-11-deprecation-sheets.md — parity del reporte + fantasmas Sheets conocidos]
- [Source: backend/app/api/v1/dashboard/{service,router}.py + services/bql_queries.py — estado actual]
- [Source: frontend BalanceSheetPage.tsx + useBalanceSheet.ts — consumidor]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
