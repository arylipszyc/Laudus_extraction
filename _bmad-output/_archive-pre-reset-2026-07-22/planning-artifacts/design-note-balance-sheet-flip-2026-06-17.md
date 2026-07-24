# Nota de diseño — Flip del balance-sheet a Beancount

**Fecha:** 2026-06-17 · **Autor:** SM (create-story prep) · **Estado:** borrador para ratificar con Ary antes de crear la story formal
**Story propuesta:** 9.15 — "Flip del balance-sheet a Beancount (dashboards Activos/Pasivos)" · **Epic 9** · `depends_on: [9.1, 9.2]` · desbloqueada por 9.11
**Por qué nota y no story aún:** evita escribir `sprint-status.yaml` mientras `dev-story 9.11` está en curso, y deja 2-3 decisiones abiertas (abajo) que cambian el scope.

---

## 1. Qué es

Hoy los dashboards de balance (`BalanceSheetPage` — Activos/Pasivos) leen de **Sheets** (`balance_sheet_{entity}`). El reporte y el ledger ya migraron a Beancount (`USE_BEANCOUNT_ENGINE_LEDGER=true` en prod), pero **`USE_BEANCOUNT_ENGINE_BALANCE_SHEET` sigue off** — el cutover fue gradual a propósito porque el balance-sheet no tenía su propia validación de paridad.

El flip = validar paridad Sheets↔Beancount del balance por entity/período → prender `USE_BEANCOUNT_ENGINE_BALANCE_SHEET=true` en prod → smoke. **9.11 lo desbloquea** (consolida el plan de cuentas como SoT); esta story lo ejecuta.

## 2. Estado actual del path (verificado 2026-06-17)

**Backend — las dos ramas** ([dashboard/service.py:28-36](dashboard/service.py)):
- **Flag ON:** `balance_sheet_via_beancount(ledger, entity, date_from, date_to)` ([bql_queries.py:56-97](bql_queries.py)) — BQL `SELECT account, sum(position) WHERE account ~ "^(Assets|Liabilities|Equity):{entity}" AND date <= {date_to} GROUP BY account`. Semántica **point-in-time AT `date_to`** (saldo acumulado a esa fecha); `date_from` se ignora. Devuelve **una fila por cuenta**, `is_latest="TRUE"`, `account_id=None`.
- **Flag OFF (hoy):** lee la hoja `balance_sheet_{entity}` (`repo.get_records`), filtra por rango de fecha, **sin dedupe** por cuenta.

**Shapes idénticos** (mismas keys/orden): `account_id, account_number, account_name, debit, credit, debit_balance, credit_balance, query_date, is_latest`. Diferencias: Beancount siempre `account_id=None` + `is_latest="TRUE"`; Sheets puede traer `account_id` y `is_latest` alternando.

**Endpoint:** `GET /api/v1/balance-sheets` ([dashboard/router.py:50-66](dashboard/router.py)) — params `entity` (EAG/Jocelyn/Jeannette/Johanna/Jael), `date_from`, `date_to`; RBAC = cualquier user autenticado.

**Frontend:** `BalanceSheetPage.tsx` (en router activo, `App.tsx`) vía `useBalanceSheet` → manda `entity`+`date_from`+`date_to` (un **rango**, preset 'year' por default), agrupa por prefijo de cuenta (1xxx activos / 2xxx pasivos / 3xxx equity) y **suma `netPosition = debit_balance - credit_balance` sobre todas las filas devueltas**. **No usa `account_id`.** No requiere cambios para el flip (shape igual).

## 3. El hallazgo de diseño — semántica de fecha + snapshots

El frontend manda un **rango** y suma todas las filas. Las dos ramas reaccionan distinto:

- **Beancount:** point-in-time AT `date_to` → **una fila por cuenta** → la suma del front da el saldo correcto al cierre del período. ✔ Robusto.
- **Sheets:** filtra por rango → si la hoja tuviera **más de un snapshot por cuenta** dentro del rango, el front los **suma** → balance inflado. Hoy NO pasa porque `pipeline/sync.py` hace `replace_sheet` (reemplaza, no appendea) → un solo snapshot. Pero es un riesgo latente del path Sheets (era el deferred #5 del code-review 06-16).

**Consecuencia para el parity:** la comparación debe **pinear `date_to` a un cierre de mes único** (no un rango que cruce varios snapshots), y comparar el snapshot Beancount AT fin-de-mes vs el snapshot vigente en Sheets. Comparar sobre un rango multi-snapshot daría un falso diff.

## 4. El riesgo grande — TC como Liabilities (cambio de forma del balance)

`architecture-c4.md §2.5`: en Beancount las **tarjetas de crédito pasan a `Liabilities:{Entity}:TC:...`** (modelado correcto: pago TC = `Asset:Bancos → Liability:TC`). El modelado viejo en Sheets las trataba distinto (posible `Expense:Pago-TC`). → **El balance-sheet en Beancount va a verse DIFERENTE para TC** (aparecen como pasivo). Esto **no es un bug de paridad**: es la corrección semántica esperada. Pero significa que un diff en las cuentas TC entre Sheets y Beancount es **esperado y correcto**, no un blocker.

`architecture-c4.md §2.5` ya marcó: *"Ary debería confirmar con su contadora actual antes de cerrarlo."* → **Decisión abierta #1.** El flip hace visible este cambio en los dashboards de la family; conviene el OK de la contadora antes de prenderlo en prod.

## 5. Scope propuesto (draft de ACs)

- **AC1 — Función BQL existe y filtra bien:** `balance_sheet_via_beancount` ya existe; verificar que el patrón de entity matchea las 5 entidades y que las cuentas TC caen en `Liabilities`.
- **AC2 — Paridad por entity × cierre-de-mes:** para cada entity (EAG, Jocelyn, Jeannette, Johanna, Jael) y cada cierre de mes del último año, comparar `balance_sheet_via_beancount(AT fin-de-mes)` vs el balance vigente en Sheets. Diff = 0 CLP **salvo** las diferencias esperadas y documentadas (TC reclasificadas a Liabilities; fantasmas stale de Sheets ya conocidos del parity del reporte). Script tipo `scripts/parity_check_balance_sheet.py` (nuevo, espejo del de reporte).
- **AC3 — Flip del flag:** `USE_BEANCOUNT_ENGINE_BALANCE_SHEET=true` en Render + redeploy (gotcha conocido: el PUT de env-vars no redeploya solo, hace falta `POST /deploys`).
- **AC4 — Smoke de los dashboards:** `BalanceSheetPage` por las 5 entidades + períodos (Q1 2026, FY 2025); charts cargan, sin errores, el activo/pasivo cuadra contra lo esperado; el cambio de TC se ve y es el esperado.
- **AC5 — Rollback:** `USE_BEANCOUNT_ENGINE_BALANCE_SHEET=false` + redeploy vuelve a Sheets en < 30 min.

## 6. Out of scope (explícito)

- **Income-statement y equity-variation:** sus flags están **comentados** en `.env.example`, **no hay funciones BQL** (`income_statement_via_beancount`/`equity_variation_via_beancount` no existen) y **no hay páginas frontend** (las rutas `/income-statement` y `/equity-variation` van a `DashboardPlaceholder`). Quedan AFUERA — migrarlas es trabajo separado (BQL + páginas nuevas). *(Nota: `IncomeExpensesPage` se renderiza client-side desde `/ledger-entries`, que ya está gated por `USE_BEANCOUNT_ENGINE_LEDGER` (on) → esa vista ya lee Beancount; no es parte del flip del balance-sheet.)*
- **Dedupe del path Sheets** (riesgo latente de multi-snapshot): moot post-flip; no se arregla acá.
- **RBAC por entity:** sin control de acceso por entidad hoy; fuera de scope (deferred).

## 7. Dependencias y secuencia

- **Desbloqueada por 9.11** (plan de cuentas como SoT consolidado).
- **Independiente de 10.3 y 9.14** (esos son el camino de promoción/Supabase). El flip del balance-sheet puede ir en **paralelo** a 10.3/9.14 una vez cerrada 9.11.
- No requiere cambios de frontend.

## 8. Decisiones abiertas para Ary (antes de crear la story)

1. **TC como Liabilities — ¿OK de la contadora antes del flip?** El balance de la family va a mostrar las TC como pasivo (correcto, pero distinto a hoy). ¿Prendemos igual y avisamos, o esperamos confirmación de la contadora? *(Recomendación: pedir OK de la contadora — es un cambio visible para la family y `architecture-c4.md §2.5` ya lo pidió.)*
2. **Número de story:** ¿9.15 en Epic 9 (mi recomendación — es migración de dashboard, misión de Epic 9)?
3. **Income-statement/equity-variation:** confirmar que quedan AFUERA (son placeholders sin BQL ni página). *(Recomendación: AFUERA.)*

## 9. Referencias

- [Source: dashboard/service.py:28-36 — branch del flag] · [bql_queries.py:56-97 — balance_sheet_via_beancount]
- [Source: dashboard/router.py:50-66 — endpoint] · [frontend BalanceSheetPage.tsx + useBalanceSheet.ts — consumidor]
- [Source: architecture-c4.md §2.5 — TC como Liabilities, "confirmar con contadora"]
- [Source: 9-2-backend-thin-api-bql.md AC3/AC5/AC6 — balance-sheet BQL + income/equity deferred]
- [Source: memoria project_epic9_c4_backend_foundation — cutover gradual, balance_sheet flag held; deferred #5 multi-snapshot]
