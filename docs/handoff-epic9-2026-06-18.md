# Handoff operativo — cierre de review Epic 9 (2026-06-18)

Checklist de tareas **manuales / no codeables** (deploy, creds, Drive, smoke) que quedaron tras
el code-review de las 9 stories del Epic 9 (branch `feat/10-3-cuentas-pendientes`, commits
`2c8b7d4` + `6a2c5fd`). **Ordenado por dependencia** — seguir las fases en orden.

Runbooks de rollback ya escritos: `docs/rollback-deprecation-sheets.md` (9.11 + flip 9.15),
`docs/rollback-bank-accounts-beancount.md` (9.14).

## ⚠️ Gotchas transversales (leer primero)

- **Render no redeploya solo** al cambiar env vars (PUT). Después de cada cambio de flag →
  **`POST /deploys` explícito**.
- La **deploy key de Fava ahora debe ser WRITE** (el editor commitea+pushea, fix F2 del review).
  Se puede reusar la write key del importer o generar otra.
- Todos los patches del review están **detrás de flags ya existentes** → mergear no cambia
  comportamiento hasta flipear.

---

## Fase 0 — Merge + baseline (pre-condición de todo lo demás)

- [ ] Revisar/abrir PR de `feat/10-3-cuentas-pendientes` → `main` (trae el remanente del Epic 9:
      7 stories de código + el review).
- [ ] Merge a `main`.
- [ ] Redeploy del **backend** desde `main` (`POST /deploys`). Health check OK. Los flags
      `USE_BEANCOUNT_ENGINE_*` ya están como en prod → sin cambio de comportamiento.

## Fase 1 — 🔴 Cerrar la ventana de dashboards congelados (URGENTE) — 9.15 + 9.11

> Al mergear, el cron que refrescaba las tabs `balance_sheet_{entity}` se borró (9.11). Los
> dashboards Activos/Pasivos quedan **estáticos** hasta este flip. Hacerlo pronto.

> **⚠️ RESULTADO del parity (corrido 2026-06-18, read-only) — NO-GO, requiere investigación tuya:**
> Se corrió `parity_check_balance_sheet.py` contra prod (Sheets + ledger local, que estaba al día
> con origin/main). Hallazgos:
> 1. **El tab legacy de Sheets `balance_sheet` no es un balance limpio** — incluía cuentas de
>    resultado (Income/Expenses) **y** las cuentas de las hijas (Jocelyn/Jeannette/Johanna/Jael)
>    amontonadas bajo EAG. Se ajustó el script para comparar solo `Assets|Liabilities|Equity`
>    (filtro `balance_only`), bajando el ruido de 164 → 40 diffs.
> 2. **4 de 5 entidades (Jocelyn/Jeannette/Johanna/Jael) NO tienen tab `balance_sheet_*`** en el
>    Sheet → sus dashboards en la rama OFF hoy leen un tab inexistente; flipear les daría data.
> 3. **EAG: 24 diffs reales.** ~13 son cuentas de las hijas que el tab viejo metía en EAG (beancount
>    las separa por entidad). **Decisión Ary 2026-06-18: los movimientos de las hijas deben tratarse
>    como EGRESOS de EAG** → la separación estricta por entidad de beancount puede NO ser lo que se
>    quiere para el dashboard de EAG; es una decisión de consolidación (EAG solo vs EAG+hijas) a
>    confirmar con el contador/Winston antes de flipear.
> 4. **`Liabilities:EAG:Apertura-211005` está DOBLE-CONTADO en beancount** (-698M vs -349M de
>    Sheets): tiene el "Saldo inicial" de Laudus (2021-01-01) **+** un `pad` del bootstrap
>    (2020-12-31), ambos -349M. Bug del ledger/bootstrap (9.1) a corregir — chequear si otras
>    cuentas "Apertura" tienen el mismo doble.
> 5. ~10 diffs chicos en cuentas reales de EAG (millones) — estilo "fantasmas de marzo" (9.11),
>    probable staleness de Sheets; confirmar cuenta por cuenta vs Laudus.
>
> **Decisión Ary 2026-06-18 (refinada):** los movimientos de las hijas **son egresos de EAG** —
> verificado: de 1077 tx que tocan cuentas de hijas, **971 tienen contraparte en EAG** (604
> Assets/bancos + 347 Expenses). → **Consolidar** (EAG = EAG + hijas); la separación por entidad se
> hará después como reporte. Además: **"Laudus prima sobre Sheets"** → los diffs chicos donde
> beancount espeja Laudus son Sheets stale, no bloquean (beancount es la verdad).
>
> **Probado (read-only, sin tocar el motor):** beancount CONSOLIDADO (todas las entidades, A/L/E)
> vs el tab `balance_sheet_eag` (que ya era consolidado) → **~20 diffs**. De esos: `211005` es el
> doble real de beancount (va el fix del ledger); las otras ~19 son beancount-vs-Sheets (ej.
> inversiones de hijas `6/7/8/9 0005`, `613019`) que por "Laudus prima" son Sheets stale → beancount
> correcto, pero conviene spot-check de 2-3 contra Laudus.
>
> **→ Camino al flip (supersede el 9.15 per-entity original):**
> 1. **Consolidar el motor** (`balance_sheet_via_beancount`: EAG → sin filtro de entidad, o un modo
>    "consolidado") — cambio de diseño chico, **pasar por Winston** (afecta el selector de entidad
>    del frontend). NO es un flip de config.
> 2. **Fix del doble de `211005`** (Laudus "Saldo inicial" + `pad` del bootstrap) en el ledger/9.1;
>    chequear otras cuentas "Apertura".
> 3. **Spot-check de 2-3 de los ~19** contra Laudus para confirmar "Laudus prima".
> 4. Recién ahí: flip `USE_BEANCOUNT_ENGINE_BALANCE_SHEET=true` + smoke.
> Output en `_handoff/parity-out2.txt` (gitignored).

- [ ] (1) Consolidar el motor del balance-sheet (con Winston).
- [ ] (2) Fix del doble de 211005 + chequear otras "Apertura".
- [ ] (3) Spot-check de 2-3 cuentas vs Laudus.
- [ ] (4) Flip + smoke. Re-correr el parity (script ya filtra A/L/E; falta el modo consolidado):
      `GOOGLE_APPLICATION_CREDENTIALS=... GOOGLE_SHEET_ID=... LEDGER_PATH=ledger/main.beancount PYTHONUTF8=1 python scripts/parity_check_balance_sheet.py`
- [ ] Verificar **exit 0** (solo diffs esperados TC→Liabilities). Si exit 1 con inesperados →
      **NO flipear**, investigar.
- [ ] En Render: `USE_BEANCOUNT_ENGINE_BALANCE_SHEET=true` + **`POST /deploys`**.
- [ ] Smoke `BalanceSheetPage` (5 entidades, Q1 2026 + FY 2025): charts cargan, **TC aparecen
      como Pasivo** (cambio esperado).
- [ ] **Avisar a la family**: las tarjetas ahora se ven como pasivo (modelado contable correcto).
- [ ] MEMORY (reference): balance-sheet en beancount + decisión de prender sin gate de contadora.

## Fase 2 — Deploy de Fava (9.3)

- [ ] Generar/reusar **deploy key SSH con WRITE** al repo del ledger → `base64` → guardar para
      `BEANCOUNT_DEPLOY_KEY`.
- [ ] Crear web service Render **`laudus-fava`** (Docker = `Dockerfile.fava`), **persistent disk
      montado en `/ledger` ≥ 1GB**.
- [ ] Env vars: `BEANCOUNT_REPO_URL` (SSH), `BEANCOUNT_DEPLOY_KEY` (write, base64),
      `FAVA_BASIC_AUTH_USER`, `FAVA_BASIC_AUTH_PASSWORD`, `EDIT_HOOK_ENABLED=true`.
- [ ] Smoke: URL → **401** → con auth → home + Trial Balance con datos → BQL
      `SELECT count(*) FROM #` > 0 → editar un archivo válido (**persiste y pushea**, fix F2) y
      uno inválido (se revierte).
- [ ] **Poblar `bank_account_last4` en las 47 cuentas** vía Fava editor (~30 min). *Pre-condición
      para que 9.5 valide cartolas.* Ahora propaga a origin (fix F2).

## Fase 3 — Apagar Supabase (9.14 AC5) — después de que cartola-upload funcione sin Supabase

- [ ] **Captura one-time**: por cada cuenta con `active=false` en Supabase →
      `PATCH /bank-accounts/{id} {active:false}` (escribe el `close` en beancount; hoy todas
      migran como `active=true`).
- [ ] Smoke sin Supabase: cartola upload + dropdown bank-accounts + dashboards.
- [ ] Apagar el proyecto Supabase standby.
- [ ] Remover env vars `SUPABASE_URL` / `SUPABASE_KEY` de Render (no están en `render.yaml`).
- [ ] Desinstalar `supabase==2.5.0` de `backend/requirements.txt`.
- [ ] Cerrar Story 4.0 (sunk-cost) + MEMORY.

## Fase 4 — Sheets read-only (9.11 AC5) — después del merge (crons ya borrados)

- [ ] Cambiar permisos del Google Sheet en Drive a **Viewer** (family + service account).
- [ ] MEMORY (reference): "Sheets es archivo histórico read-only desde {fecha}".

## Fase 5 — Smoke del reporte (9.11 AC7)

- [ ] Navegar `/reportes/gastos` prod ene–may 2026 vs el workbook del contador → **cuadra
      peso-por-peso** + el sync timestamp del Header refleja el último import Laudus.

---

## 🟡 Decisiones abiertas (no bloquean)

- [ ] **9.7 seams** — instalar `smart_importer` + `GeminiClient.suggest_category` (decisión de
      dependencia/costo). Sin ellos la categorización corre degradada limpio
      (supra → historical → suspense).
- [ ] **Pase de UX a Sally** — defers de frontend (9.8/9.12): badge inline sobre los 4 dashboards,
      dropdown de Expenses en `/categorizacion`, chips que desaparecen en error de fetch. Detalle
      en `_bmad-output/implementation-artifacts/deferred-work.md`.

---

## Contexto del review (referencia)

16 patches de backend (con tests) + 3 fixes en 9.3 (auth git SSH, editor commit+push, path del
ledger). Suite 625 passed / 1 xfailed (único rojo = `test_run_backfill` pre-existente
date-dependiente). Findings de frontend/UX en `deferred-work.md`. Las 9 stories del Epic 9 que
estaban en `review` quedaron en `done`.
