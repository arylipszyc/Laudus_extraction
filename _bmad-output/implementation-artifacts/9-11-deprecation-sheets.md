---
story: 9.11
title: Plan de cuentas en Beancount (SoT) + deprecación de Sheets/Supabase
status: review
epic: 9
depends_on: [9.1, 9.2, 9.4]
gate_condition: paridad-1-1-confirmada
blocks: [10.3]  # + balance-sheet-flip (story aparte aún sin id asignado)
---

# Story 9.11 — Plan de cuentas en Beancount (SoT) + deprecación de Sheets/Supabase

## Story

As Ary,
I want the chart of accounts taxonomy (`Categoria1/2/3`) to live as editable `Open` metadata in Beancount as the single source of truth — retiring the fragmented Supabase/`generate_accounts.py` path — and Sheets demoted from "source of truth" to "read-only historical archive",
So that we operate on one editable source of truth, the report stops depending on the external `ledger_final` join for categories, Sheets stays accessible only as legacy reference, and the balance-sheet flip (separate story) and Story 10.3 (self-serve account promotion) are unblocked.

## Context

Esta story es la **consolidación F4-final** del plan de migración a Beancount (`architecture-c4.md` §7.4 + §7.8), **ampliada** por el `sprint-change-proposal-2026-06-10` y ratificada por Winston en `adr-001-plan-de-cuentas-beancount-source-of-truth.md`.

**Estado real al momento de crear esta story (2026-06-17) — verificado en código + prod:**

- `USE_BEANCOUNT_ENGINE_LEDGER=true` **ya está en prod**. El reporte `/reportes/gastos` ya lee `Categoria1/2/3` desde la **metadata `Open` de beancount** (`laudus_categoria1/2/3`) vía `report_rows_via_beancount`, **no** desde el join externo de la pestaña `ledger_final`. El reporte **cuadra peso-por-peso** vs el workbook del contador. → El corazón del scope ampliado (eliminar el join externo de Sheets para categorías) **ya está arquitectónicamente logrado cuando el flag está on**.
- El cron importer Laudus → Beancount está **LIVE** (Story 9.4, `crn-d8on53rtqb8s73c85p90`).
- `scripts/parity_check_sheets_vs_beancount.py` **ya existe** (herramienta de AC1 ya construida).
- `USE_BEANCOUNT_ENGINE_BALANCE_SHEET` sigue **off** (los dashboards Activos/Pasivos aún leen Sheets). **El flip del balance-sheet NO es parte de esta story** — 9.11 lo *desbloquea*; va en story aparte (requiere su propia paridad de balance por entity/período).
- `generate_accounts.py` + Supabase `plan_de_cuentas` siguen vivos: el bootstrap los lee y existen los endpoints `GET /api/v1/plan-de-cuentas/` y `POST /api/v1/plan-de-cuentas/sync`.
- **El sync a Sheets que SÍ corre es `.github/workflows/sync-weekly.yml`** (cron `0 9 * * 1`, lunes; `python -m pipeline.sync`). `.github/workflows/backup.yml` (cron diario, `python sync.py`) **ya está roto** — `sync.py` se movió a `pipeline/sync.py` (commit b333873), así que su step falla con `No such file`. Verificado 2026-06-17. → La deprecación debe apuntar a **`sync-weekly.yml`** (el vivo), no solo a `backup.yml`.

**Naturaleza de la story — gate operacional + deprecación, NO implementación heavy.** Decisiones de scope tomadas con Ary al crear la story:
1. **Balance-sheet flip: AFUERA de 9.11** (story aparte que esta desbloquea).
2. **Deprecación Supabase/`generate_accounts.py`: documentar + retirar de rutina, SIN borrar código vivo** (cero riesgo de regresión; beancount ya es SoT por el flag prendido). **Apagar el proyecto Supabase standby NO entra en 9.11** — `bank-accounts`/`CartolaUploadPage` aún lo consume (ver AC3/Riesgos); apagarlo es story aparte tras migrar `bank-accounts` a metadata de `accounts.beancount`.
3. **ACs ya cumplidos en prod (flag ledger, parity reporte, cron Laudus): marcar DONE + re-verificación barata**, centrando el trabajo net-new en el plan de cuentas + deprecación.

**La promoción de cuentas nuevas (escribir el `open` final + metadata desde una UI) NO es parte de 9.11 — es Story 10.3** (per ADR-001 §2). El andamiaje (cuarentena `_new-accounts-pending.beancount`, lock, `git_commit_push`, `bean-check`) ya existe (Story 9.4/9.0); 9.11 solo ratifica beancount como destino editable.

## Acceptance Criteria

**AC1 — Paridad 1:1 reporte/ledger re-confirmada (ledger flag, ya live → re-verify)**

**Given** `USE_BEANCOUNT_ENGINE_LEDGER=true` en prod y la pestaña Sheets `ledger_final` todavía accesible
**When** se corre `scripts/parity_check_sheets_vs_beancount.py --from 2025-06 --to 2026-06`
**Then** la diferencia es **0 CLP** en cada (cuenta, mes) — exit 0
**And** si aparece un diff: la story NO procede con la deprecación; se investiga (mapping de cuenta / FX / JE faltante) y se abre issue
**Note:** este AC valida el path del *reporte/ledger* únicamente (lo que el flag `USE_BEANCOUNT_ENGINE_LEDGER` gobierna). La paridad del *balance-sheet* queda para la story de flip del balance-sheet.

---

**AC2 — Plan de cuentas confirmado como SoT editable en Beancount**

**Given** el reporte lee categorías desde la metadata `Open` (`laudus_categoria1/2/3`) de `accounts.beancount` + `manual/*.beancount`
**When** se edita la taxonomía de una cuenta directamente en el `.beancount` de la zona `manual/` (ej: cambiar `laudus_categoria3` de una cuenta) y se recarga el ledger
**Then** el cambio se refleja en el reporte **sin tocar Sheets ni Supabase**, y **la evidencia se captura** (diff del `.beancount` + screenshot/dump del reporte antes y después) en Completion Notes — para que la verificación quede probada aunque el cambio de prueba se revierta
**And** el join externo de la pestaña `ledger_final` **deja de ser autoritativo** para categorías (documentado; el flag ya lo hace efectivo en prod)
**And** se revierte el cambio de prueba (no se persiste un cambio real de categoría a menos que sea una corrección legítima de Ary); la prueba de la SoT-editabilidad queda en la evidencia capturada, no en el estado del ledger

---

**AC3 — Supabase `plan_de_cuentas` + `generate_accounts.py` deprecados (documentar + retirar de rutina, sin borrar código)**

**Given** beancount es ahora el SoT del plan de cuentas
**When** se cierra esta story
**Then** `bootstrap/generate_accounts.py` lleva un header de docstring marcándolo **"DEPRECATED como paso de rutina — solo re-bootstrap de disaster-recovery"** (per ADR-001 §4)
**And** los endpoints `GET /api/v1/plan-de-cuentas/` y `POST /api/v1/plan-de-cuentas/sync` (Sheets→Supabase) llevan un comentario de deprecación apuntando a ADR-001 (NO se elimina el código vivo en esta story — cero regresión)
**And** `bootstrap/README.md` (o `scripts/README.md`) documenta que el SoT del plan de cuentas es `accounts.beancount` (baseline congelado) + `manual/` — no Supabase
**And** apagar el proyecto Supabase standby queda **BLOQUEADO fuera del cierre de 9.11**: `GET /api/v1/bank-accounts/` (servicio `list_bank_accounts` → `SupabaseRepository`) lo consume una vista activa (`CartolaUploadPage` — dropdown de cuenta para subir cartola), y `create_bank_account` valida contra la tabla `plan_de_cuentas` de Supabase. Apagar Supabase rompería la carga de cartolas. **Pre-condición para apagar Supabase = migrar `bank-accounts` a leer la metadata bancaria de `accounts.beancount` (modelo unificado 9.1: `bank_account_id`/`bank_name`/`bank_account_type`/`bank_account_currency`), que NO está wireado hoy → story aparte.** Verificado 2026-06-17: `GET /api/v1/plan-de-cuentas/` NO tiene consumidor frontend (sí se depreca); el bloqueante es `bank-accounts`.

---

**AC4 — Crons de sync a Sheets legacy discontinuados (`sync-weekly.yml` vivo + `backup.yml` roto)**

**Given** `.github/workflows/sync-weekly.yml` (cron `0 9 * * 1`, `python -m pipeline.sync`) es el sync a Sheets que **efectivamente corre**, y `.github/workflows/backup.yml` (cron diario, `python sync.py`) **ya está roto** (`sync.py` movido a `pipeline/`)
**When** se desactivan
**Then** **`sync-weekly.yml` se discontinúa** (decisión Ary 2026-04-30, ratificada): se borra o se deja solo `workflow_dispatch` sin el step `python -m pipeline.sync` — esto es lo que realmente detiene los writes a Sheets
**And** `backup.yml` se borra también (cron muerto desde el move de `sync.py`); NO se asume que cubrió NFR14 — re-verificar su run history antes de citarlo como backup
**And** NFR14 (backup) queda cubierto por construcción por el git history del propio ledger Beancount + `pipeline/sync.py` queda como fallback de re-importación histórica de Laudus si fuera necesario
**And** el endpoint `POST /api/v1/sync/trigger` solo dispara el importer Laudus → Beancount (verificar — ya gated por `USE_BEANCOUNT_ENGINE_LEDGER`; Story 9.4)

---

**AC5 — Sheets read-only (manual, fuera de CI)**

**Given** AC1–AC4 pasaron
**When** Ary actualiza permisos del Google Sheet en Drive
**Then** los usuarios family + service account tienen permiso `Viewer` (no `Editor`)
**And** Ary documenta el cambio en MEMORY (memoria reference): "Sheets es archivo histórico read-only desde {fecha}"

---

**AC6 — Audit log del switch (commit + docs)**

**Given** el switch ocurre
**When** se completa
**Then** se appendea un commit explícito: `chore(deprecation): plan de cuentas en Beancount es SoT — Sheets/Supabase retirados`
**And** el commit incluye: header `DEPRECATED — superseded by architecture-c4.md desde {fecha}` en `_bmad-output/planning-artifacts/architecture.md`; remoción de las referencias a "Sheets sync legacy en paralelo" en `architecture-c4.md` (§7.4/§7.8); actualización de `sprint-status.yaml` (9.11 → done, `epic-9-retrospective` disponible)
**And** se crea `docs/deprecation-sheets-{fecha}.md` con timeline + decisiones + responsable (Ary)

---

**AC7 — Smoke test post-deprecación (regression, reporte/ledger)**

**Given** el reporte corre contra Beancount y Sheets quedó read-only
**When** se navega el reporte `/reportes/gastos` por los períodos en producción (ene–may 2026) y se compara contra el workbook del contador
**Then** no hay errores, el reporte cuadra peso-por-peso, las cuentas hijas se itemizan, y las cuentas en cuarentena (`#pending-account`) se muestran con el guard de 10.2
**And** el sync timestamp del Header refleja el último run del importer Laudus (cron sábados)
**Note:** los dashboards de balance-sheet (Activos/Pasivos) NO se tocan en esta story — siguen en Sheets hasta su flip.

---

**AC8 — Rollback plan documentado**

**Given** algo se rompe post-deprecación
**When** se decide rollback
**Then** existe `docs/rollback-deprecation-sheets.md` con los pasos: revertir `USE_BEANCOUNT_ENGINE_LEDGER=false` (reporte vuelve a Sheets) + reactivar `sync-weekly.yml` (`python -m pipeline.sync`, el cron que repobla Sheets) + restaurar permisos `Editor` en Drive + (si se apagó) reactivar Supabase standby
**And** el runbook se valida con un dry-run cronometrado al escribirlo, para respaldar el objetivo de ejecutable en < 30 minutos

---

## Tasks / Subtasks

- [x] **Task 1: Re-verificar paridad reporte/ledger (AC1)** — PASS-con-caveat (decisión Ary 2026-06-17)
  - [x] Correr `scripts/parity_check_sheets_vs_beancount.py --from 2025-06 --to 2026-06` con `PYTHONUTF8=1` + credenciales Sheets + `LEDGER_PATH=ledger/main.beancount`
  - [x] ~~Confirmar exit 0~~ → exit 1 (15 diffs ventana completa; 4 reales en marzo = 202K, resto drift junio). Investigado: refresh del ledger descartó staleness; causa = Sheets tiene ~101K fantasma de marzo ausentes de Laudus vivo (beancount=Laudus=validado vs contador es correcto). Divergencia del lado legacy (Sheets). Decisión Ary: proceder + documentar (no abrir issue de importer — no es bug de beancount)
  - [x] Resumen del run en Debug Log References + Completion Notes

- [x] **Task 2: Verificar beancount como SoT editable (AC2)**
  - [x] Editar la metadata `laudus_categoria3` de una cuenta (cambio de prueba), recargar el ledger, confirmar que el reporte refleja el cambio sin tocar Sheets/Supabase — evidencia en Completion Notes. Nota: el `open`/metadata de una cuenta existente vive en `accounts.beancount` (beancount no permite re-abrir cuenta); la zona `manual/` es para edits nuevos del contador. El AC se cumple igual: editar taxonomía en beancount → fluye al reporte
  - [x] Revertir el cambio de prueba (git checkout — restaurado a "Vehiculos", working tree limpio)
  - [x] Documentar en Dev Notes que el join `ledger_final` ya no es autoritativo (el flag lo hace efectivo)

- [x] **Task 3: Deprecar Supabase + `generate_accounts.py` (documentar + retirar de rutina, AC3)**
  - [x] Header docstring "DEPRECATED — solo re-bootstrap DR" en `bootstrap/generate_accounts.py` (lógica intacta; py_compile OK)
  - [x] Comentario de deprecación + link a ADR-001 en `backend/app/api/v1/plan_de_cuentas/router.py` (docstring de módulo + ambos endpoints `GET /` y `POST /sync`) — código vivo intacto, py_compile OK
  - [x] Actualizar `bootstrap/README.md`: SoT del plan = `accounts.beancount` + `manual/`, no Supabase; apagado de Supabase bloqueado por Story 9.14
  - [x] **NO apagar Supabase en 9.11** (bloqueado): documentada la pre-condición (migrar `bank-accounts` → metadata de `accounts.beancount`, Story 9.14); Supabase queda prendido

- [x] **Task 4: Discontinuar los crons de sync a Sheets (AC4)**
  - [x] **Discontinuado `.github/workflows/sync-weekly.yml`** (el cron VIVO: `0 9 * * 1`, `python -m pipeline.sync`) — `git rm` (borrado). Detiene los writes a Sheets. Rollback restaura desde git (`git show 99bb5b0:.github/workflows/sync-weekly.yml`)
  - [x] Borrado `.github/workflows/backup.yml` (cron muerto: `python sync.py` apunta a path movido a `pipeline/`). Run history NO verificable desde el env local (sin `gh`); NFR14 queda cubierto por construcción vía git history del ledger (documentado en deprecation/rollback docs)
  - [x] Verificado que `POST /api/v1/sync/trigger` solo dispara el importer Laudus: `_run_sync`/`_run_backfill` chequean `_flag("USE_BEANCOUNT_ENGINE_LEDGER")` (líneas 188/236) → con flag ON (prod) llaman `_run_laudus_import` y retornan, sin llegar a `pipeline.sync.sync_api` (path Sheets). Sin cambio de código
  - [x] Commit del cambio → en Task 6 (commit consolidado de deprecación)

- [ ] **Task 5: Sheets read-only (manual, fuera de CI — AC5)** — ⏸ HANDOFF A ARY (no codeable)
  - [ ] **Handoff a Ary:** cambiar permisos en Drive del Google Sheet a `Viewer` (family + service account). Hacer DESPUÉS de mergear este branch (los crons de sync ya borrados → no fallará ningún write a viewer-only)
  - [ ] Documentar en MEMORY (memoria reference): "Sheets es archivo histórico read-only desde {fecha}"

- [x] **Task 6: Documentación + audit log (AC6, AC8)**
  - [x] Header `DEPRECATED — superseded by architecture-c4.md desde 2026-06-17` en `_bmad-output/planning-artifacts/architecture.md`
  - [x] Refs a "Sheets sync legacy en paralelo" retiradas en `architecture-c4.md` (§7.4/§7.8 marcadas COMPLETADO/CERRADO; env-vars bloque post-9.1 actualizado)
  - [x] Contrato env de `sync.py` ya re-homeado a `pipeline/README.md` (Review Finding aplicada previo; `README.txt` borrado confirmado; `pipeline/sync.py` = fallback DR)
  - [x] `sprint-status.yaml`: 9.11 → **review** (per workflow dev-story Step 9; el "done" + `epic-9-retrospective` disponible de AC6 ocurre tras code-review). Nota agregada
  - [x] Crear `docs/rollback-deprecation-sheets.md` (AC8) — runbook < 30 min con dry-run cronometrado del paso git-restore
  - [x] Crear `docs/deprecation-sheets-2026-06-17.md` (timeline + decisiones + responsable Ary)
  - [x] Commit `chore(deprecation): plan de cuentas en Beancount es SoT — Sheets/Supabase retirados` (en branch `feat/9-11-deprecation-sheets`; ver Change Log)

- [~] **Task 7: Smoke test post-deprecación (AC7)** — sanity local OK; navegación prod-UI = HANDOFF A ARY
  - [x] Sanity local (soporte): `report_rows_via_beancount` ene–may 2026 = 1303 filas, 100% con Categoria1 poblada, 86 cuentas (code,Cat3) itemizables, 0 `#pending-account`. El reporte tiene data limpia desde beancount
  - [ ] **Handoff a Ary:** navegar `/reportes/gastos` prod ene–may 2026 + comparar peso-por-peso vs workbook del contador (ya validado 2026-06-16 per memoria; re-confirmar post-deprecación) + sync timestamp del Header
  - [x] **NO se tocaron** los dashboards de balance-sheet (siguen en Sheets) — fuera de scope

---

## Dev Notes

### Decisiones de scope (tomadas con Ary al crear la story, 2026-06-17)

1. **Balance-sheet flip → AFUERA.** `USE_BEANCOUNT_ENGINE_BALANCE_SHEET` sigue off. 9.11 lo desbloquea pero no lo ejecuta; va en story separada que necesita su propia paridad de balance por entity/período. El AC2 viejo ("4 flags true") queda **superseded** por esta decisión — 9.11 solo confirma el flag de *ledger* (ya on).
2. **Deprecación Supabase = documentar + retirar de rutina, sin borrar código vivo.** Cero riesgo de regresión. beancount ya es SoT por el flag prendido. El código de `generate_accounts.py` y los endpoints `plan-de-cuentas` se marcan deprecados con comentarios, no se eliminan (DR-only). Ary apaga Supabase standby por fuera.
3. **ACs ya live en prod → DONE + re-verify barato.** El grueso del gate (ledger flag, parity reporte, cron Laudus) ya ocurrió; la story los re-verifica (correr parity, smoke reporte) en vez de re-ejecutar de cero.

### Estado actual del código a tocar (leído antes de escribir — preservar comportamiento)

- **`backend/app/services/bql_queries.py` — `report_rows_via_beancount()`** (≈líneas 159–200): YA extrae `Categoria1/2/3` desde la metadata `Open` (`laudus_categoria1/2/3`) del ledger. **NO se modifica.** Es la prueba de que el join externo de Sheets ya no es necesario para categorías cuando el flag está on.
- **`backend/app/api/v1/reportes/router.py`** (≈líneas 25–51): `_use_beancount()` lee `USE_BEANCOUNT_ENGINE_LEDGER`; si on → usa `report_rows_via_beancount`, si off → `repo.get_records` (Sheets). **NO se modifica** — el flag ya está on en prod.
- **`scripts/parity_check_sheets_vs_beancount.py`**: YA existe; reusa `_income_accounts`, `_num`, `_row_ym` de `report_builder` para signo/fecha fieles. Exit 0/1/2. **Solo se corre, no se modifica.**
- **`bootstrap/generate_accounts.py`** (1–387): one-shot, lee Laudus API + Supabase `plan_de_cuentas` para emitir `accounts.beancount` con metadata `laudus_categoria1/2/3`. **Solo se agrega header de deprecación**, sin tocar la lógica (queda como re-bootstrap DR).
- **`backend/app/api/v1/plan_de_cuentas/router.py`**: `POST /sync` (Sheets→Supabase, role contador/admin) + `GET /` (lista activas de Supabase). **Solo comentario de deprecación**, sin borrar — algo podría seguir consumiéndolos; eliminarlos es trabajo aparte fuera de scope.
- **`.github/workflows/sync-weekly.yml`**: cron `0 9 * * 1` (lunes) corre `python -m pipeline.sync` — **es el sync a Sheets que efectivamente corre**. Se discontinúa (Task 4); es lo que detiene los writes a Sheets.
- **`.github/workflows/backup.yml`**: cron `0 12 * * *` corre `python sync.py`, pero `sync.py` se movió a `pipeline/` (commit b333873) → **el step ya está roto**. Se borra también (Task 4), sin asumir que cubrió NFR14.
- **`ledger/main.beancount`**: incluye `accounts.beancount` (generado/baseline) + `manual/*.beancount` (zona humana, nunca regenerada — ya existe `manual/2026-04.beancount`) + `imports/_new-accounts-pending.beancount` (cuarentena). La zona `manual/` es donde viven las ediciones humanas de taxonomía (AC2).

### Andamiaje existente (NO es infra nueva — Story 9.4/9.0)

- Cuarentena `ledger/imports/_new-accounts-pending.beancount` + tag `#pending-account` en JEs (escrito por el importer).
- Lock `ledger/.import.lock` (`acquire_lock`, `pipeline/importers/laudus_run.py`).
- `git_commit_push(repo_root, paths, message)` — gated por `IMPORTER_GIT_ENABLED`; usa `BEANCOUNT_DEPLOY_KEY` (SSH write) en prod.
- `bean_check(main_path) -> (ok, detail)` — validación pre-commit, NO-NEGOCIABLE antes de commitear (un `open` malformado rompe todas las queries).
- La **promoción** de cuentas (escribir el `open` final desde UI) es **Story 10.3**, no 9.11.

### Out of scope (explícito)

- **Flip del balance-sheet** (`USE_BEANCOUNT_ENGINE_BALANCE_SHEET=true` + paridad de Activos/Pasivos) — story aparte que 9.11 desbloquea.
- **Borrar el código vivo de Supabase/`plan-de-cuentas`** — solo se marca deprecado.
- **Borrar Sheets físicamente** — queda read-only.
- **UI de promoción de cuentas pendientes** — Story 10.3.
- **Migrar comments/históricos del Sheet a metadata** — no aplica.

### Riesgos

- **Diff inesperado en AC1:** si el parity no da 0, NO proceder — investigar mapping (probable Story 9.1) o FX. Es un gate duro.
- **Apagar Supabase standby — BLOQUEADO (verificado 2026-06-17):** `GET /plan-de-cuentas/` NO tiene consumidor frontend (seguro deprecar), PERO `GET /api/v1/bank-accounts/` (→ `SupabaseRepository`) sí lo usa una vista activa (`CartolaUploadPage`). Apagar Supabase rompe la carga de cartolas. No apagar Supabase en 9.11; migrar `bank-accounts` a leer metadata de `accounts.beancount` primero → **Story 9.14** (`9-14-migrar-bank-accounts-beancount.md`).
- **Discontinuar `backup.yml`:** NFR14 lo cubre el git history del ledger; `pipeline/sync.py` queda como fallback. Documentar en el rollback runbook cómo reactivarlo.

### Project Structure Notes

```
scripts/
  parity_check_sheets_vs_beancount.py      # EXISTE — solo se corre (AC1)
bootstrap/
  generate_accounts.py                     # MODIFY (header DEPRECATED, sin tocar lógica)
  README.md                                # MODIFY (SoT = accounts.beancount + manual/)
backend/app/api/v1/plan_de_cuentas/
  router.py                                # MODIFY (comentario deprecación, sin borrar)
.github/workflows/
  backup.yml                               # DELETE / discontinuar (sync Sheets legacy)
ledger/
  accounts.beancount                       # baseline (generado) — metadata laudus_categoria*
  manual/*.beancount                       # zona humana editable = SoT de ediciones (AC2)
docs/
  rollback-deprecation-sheets.md           # NEW (AC8)
  deprecation-sheets-{fecha}.md            # NEW (AC6, audit)
_bmad-output/planning-artifacts/
  architecture.md                          # MODIFY (header DEPRECATED)
  architecture-c4.md                       # MODIFY (remover refs Sheets legacy)
_bmad-output/implementation-artifacts/
  sprint-status.yaml                       # MODIFY (9.11 → done)
```

### References

- [Source: adr-001-plan-de-cuentas-beancount-source-of-truth.md] — decisiones ratificadas por Winston 2026-06-10 (beancount SoT, retirar generate_accounts.py/Supabase, promoción = 10.3). Nota: el ADR §3/§49 deja el **destino de escritura de la promoción** como *recomendación `manual/`, a confirmar al implementar 10.3* — no como decisión cerrada. 9.11 usa `manual/` solo como zona de edición humana para la prueba de AC2, sin ratificarlo como destino final de 10.3.
- [Source: sprint-change-proposal-2026-06-10.md §4.2] — refinamiento de 9.11 (Categoria1/2/3 → metadata Open, eliminar join externo)
- [Source: sprint-status.yaml:143] — nota de scope ampliado de 9.11
- [Source: architecture-c4.md §7.4 — Plan F3 (importer Laudus único source)]
- [Source: architecture-c4.md §7.8 — Riesgo de drift durante transición]
- [Source: architecture-c4.md §2.1 / §2.3 — naming + mapeo Categoria1 → Root/Entity, metadata laudus_categoria*]
- [Source: backend/app/services/bql_queries.py — report_rows_via_beancount (categorías desde metadata Open)]
- [Source: backend/app/api/v1/reportes/router.py — _use_beancount() gate]
- [Source: scripts/parity_check_sheets_vs_beancount.py — herramienta AC1]
- [Source: pipeline/importers/laudus_run.py — acquire_lock / bean_check / git_commit_push]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (dev-story 9.11)

### Debug Log References

**2026-06-17 — Task 1 / AC1 parity check: GATE FAILED (no se procede con la deprecación).**

Corrida: `GOOGLE_APPLICATION_CREDENTIALS=pipeline/config/serviceAccountKey.json GOOGLE_SHEET_ID=… LEDGER_PATH=ledger/main.beancount PYTHONUTF8=1 PYTHONPATH=. venv/Scripts/python.exe scripts/parity_check_sheets_vs_beancount.py --from 2025-06 --to 2026-06` → exit 1.

- Ventana completa (2025-06 → 2026-06): **15 (cuenta,mes) con diff, |Σ| = 239.907.375 CLP**. 12 de 15 caen en **2026-06** (mes en curso) — drift de sync esperado (incl. 990099 = 179M en Sheets vs 0 en beancount, cuenta 99xxxx de cierre/transferencia).
- Ventana validada (2026-01 → 2026-05): **4 (cuenta,mes) con diff, |Σ| = 202.000 CLP**, todos en **2026-03**:
  - `111009` (Santander) Sheets −3.542.190 vs bean −3.462.190 → **+80.000**; pareado con `411037` (Movilización/Viajes/Choferes) Sheets 920.156 vs bean 840.156 → **−80.000**. El ledger local tiene 3 JEs marzo a 411037 (40.000 + 238.156 + 562.000 = 840.156); Sheets tiene 80.000 extra (Santander→Movilización) **ausente en el ledger local**.
  - `111005` (BCI) Sheets −10.689.174 vs bean −10.668.174 → **+21.000**; pareado con `430083` (Wizo) Sheets 21.000 vs bean **0** (sin JE en marzo en el ledger local) → **−21.000**.
- Firma: 1–2 asientos chicos (transfer banco→gasto) presentes en Sheets `ledger_final` y ausentes del ledger Beancount local. Estado del ledger local: backfill completo 2021→2026-06-12 (5946 JE) + sync 2026-06-16 (commit 99bb5b0, +2 JE). No es snapshot grosero → más probable un JE dropeado por el importer (filtro id=0 / dedup) o backdateado entre syncs, que puro drift.
- **Investigación (decisión Ary: refrescar ledger local y re-correr):** Re-corrí el importer Laudus `backfill 2026-01-01 → hoy` (fetch real, +457 JE, 0 pending, git skip por `IMPORTER_GIT_ENABLED` off). Re-corrí AC1 → **los 4 diffs de marzo quedaron IDÉNTICOS (80.000 + 21.000)**. ⇒ **descarta staleness local de forma concluyente** (un fetch fresco de Laudus sigue sin esos asientos).
- **Causa raíz (fetch crudo Laudus marzo, `default_fetch("2026-03-01","2026-03-31")` = 468 filas):**
  - `430083` (Wizo): en Laudus vivo marzo solo existe la fila `journalentryid==0` "Saldo anterior" (114.000 deb), que el `beancount_writer` dropea por diseño (synthetic opening balance) → beancount=0 correcto. **NO hay JE real de 21.000 en Laudus** → el 21.000 de Sheets es fantasma.
  - `411037` (Movilización): Laudus vivo marzo = exactamente 3 JEs (40.000+238.156+562.000 = 840.156) → beancount correcto. Sheets=920.156 → **80.000 fantasma ausente de Laudus**.
  - ⇒ **Sheets `ledger_final` contiene ~101.000 CLP de asientos de marzo que NO existen en Laudus vivo** (stale / manual / borrados de Laudus tras un sync viejo). Beancount = Laudus vivo = validado peso-por-peso vs workbook del contador (ene–may). El rojo del gate está del lado que se retira (Sheets), no en beancount. Diffs de junio = drift esperado del mes abierto (beancount adelantado por el import de hoy vs Sheets del lunes).
- **Estado del gate AC1:** umbral literal 0 CLP NO cumplido, pero el residual (202K, solo marzo) es divergencia del lado legacy (Sheets), no de beancount. Decisión de proceder/no = HALT a Ary.

### Completion Notes List

**AC1 (parity reporte/ledger) — PASS-con-caveat.** Parity `--from 2025-06 --to 2026-06` = exit 1 (15 diffs; 12 = drift junio mes-abierto, incl. 990099 cuenta de cierre 179M). 4 diffs reales en marzo (202K). Refresh del ledger (backfill Laudus a hoy) NO los movió → no es staleness. Fetch crudo Laudus confirmó que los 80K (411037) y 21K (430083) **no existen en Laudus vivo** = fantasmas de Sheets `ledger_final`. Beancount = Laudus = validado vs contador. Decisión Ary 2026-06-17: proceder, documentar divergencia (es lo que la deprecación corrige).

**AC2 (SoT editable en beancount) — VERIFICADO con evidencia.** Cuenta de prueba `411037` (Movilización/Viajes/Choferes), ventana marzo 2026 (3 filas):
- BEFORE: `Categoria3 = 'Vehiculos'` en las 3 filas (vía `report_rows_via_beancount`).
- Edit: `laudus_categoria3: "Vehiculos"` → `"AC2-PRUEBA-SoT-Editable"` en `ledger/accounts.beancount` (solo beancount, sin tocar Sheets/Supabase).
- AFTER (reload `LedgerService` desde disco): las 3 filas reflejan `Categoria3 = 'AC2-PRUEBA-SoT-Editable'`. ⇒ la taxonomía editada en beancount fluye al reporte.
- Revert: `git checkout` → restaurado a `'Vehiculos'`, working tree limpio. La SoT-editabilidad queda probada en esta evidencia, no en el estado del ledger.

### File List

**Modificados:**
- `backend/app/api/v1/plan_de_cuentas/router.py` — deprecación (docstring módulo + ambos endpoints), código vivo intacto
- `bootstrap/generate_accounts.py` — header DEPRECATED (re-bootstrap DR), lógica intacta
- `bootstrap/README.md` — SoT = `accounts.beancount` + `manual/`; apagado Supabase bloqueado por 9.14
- `_bmad-output/planning-artifacts/architecture.md` — header DEPRECATED (superseded por architecture-c4.md)
- `_bmad-output/planning-artifacts/architecture-c4.md` — §7.4/§7.8 COMPLETADO/CERRADO; refs Sheets-legacy-paralelo retiradas; bloque env-vars post-9.1 actualizado
- `pipeline/README.md` — contrato env re-homeado desde `README.txt`; `pipeline/sync.py` = fallback DR (Review Finding)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — 9.11 → review
- `_bmad-output/implementation-artifacts/9-11-deprecation-sheets.md` — story (tasks, Dev Agent Record, File List, Change Log)

**Borrados:**
- `.github/workflows/sync-weekly.yml` — cron vivo de sync a Sheets (`python -m pipeline.sync`)
- `.github/workflows/backup.yml` — cron muerto (`python sync.py`, path movido)
- `README.txt` — contrato env re-homeado a `pipeline/README.md` (Review Finding)

**Nuevos:**
- `docs/rollback-deprecation-sheets.md` — runbook de rollback (AC8)
- `docs/deprecation-sheets-2026-06-17.md` — audit log (AC6)

**No modificados (verificados, sin cambio):** `backend/app/api/v1/sync/service.py` (trigger gated por flag), `backend/app/services/bql_queries.py`, `scripts/parity_check_sheets_vs_beancount.py`, `ledger/accounts.beancount` (cambio AC2 revertido).

## Change Log

| Fecha | Cambio |
|---|---|
| 2026-06-17 | Dev-story 9.11. AC1 parity PASS-con-caveat (Sheets fantasma marzo; beancount=Laudus=contador correcto; decisión Ary proceder). AC2 SoT-editable verificado con evidencia. AC3 Supabase/`generate_accounts.py` deprecados (doc, sin borrar código). AC4 crons `sync-weekly.yml`+`backup.yml` borrados; `/sync/trigger` verificado gated por flag. AC6/AC8 docs (architecture headers, deprecation audit, rollback runbook). AC5 (Drive read-only) + AC7 (smoke prod-UI) = handoff a Ary. 121 tests relevantes verde (1 rojo pre-existente date-dependiente sin relación). Status → review. |

## Review Findings

> Code review 2026-06-17 (bmad-code-review, 3 capas: Blind Hunter + Edge Case Hunter + Acceptance Auditor vs ADR-001). Edge Hunter verificó 9/10 afirmaciones factuales = CIERTAS; Auditor = 0 violaciones duras del ADR.

- [x] [Review][Patch] README.txt borrado pierde el único doc del contrato env de `sync.py` — APLICADO 2026-06-17: contrato env re-homeado a `pipeline/README.md` (paths adaptados a `pipeline/`, marcado DEPRECATED/DR-fallback); borrado de `README.txt` confirmado. Task 6 actualizada.
- [x] [Review][Decision] AC1 — ventana de paridad `--from 2025-06 --to 2026-06` (cuenta×mes) — RESUELTO (Ary 2026-06-17): OK como está; balance/entity quedan para la story del flip. Sin cambio.
- [x] [Review][Patch] (APLICADO 2026-06-17 — AC4/Task 4/AC8/Dev Notes corregidos: `sync-weekly.yml` agregado como el cron vivo, `backup.yml` marcado roto) AC4/Task 4 omiten `sync-weekly.yml` — el sync a Sheets que SÍ corre [.github/workflows/sync-weekly.yml:5,38]. AC4/Task 4 sólo discontinúan `backup.yml` (cron diario, `python sync.py`) que **ya está roto** (`sync.py` movió a `pipeline/sync.py`, commit b333873). El sync vivo es `sync-weekly.yml` (cron `0 9 * * 1`, `python -m pipeline.sync`). Discontinuar sólo `backup.yml` NO detiene los writes a Sheets; y AC5 (Sheets read-only) sin desactivar `sync-weekly.yml` hará fallar el cron de los lunes (write a viewer-only). Corregir la caracterización + agregar `sync-weekly.yml` a AC4/Task 4. Re-verificar que NFR14 alguna vez se cubrió por `backup.yml` (probablemente nunca produjo artefactos).
- [x] [Review][Patch] (APLICADO 2026-06-17) AC3 vs Context #2 — contradicción sobre apagar Supabase. Context scope-decision #2 cierra "Apagar el proyecto Supabase standby." (imperativo, in-scope), pero AC3 + Riesgos lo marcan BLOQUEADO (lo consume `bank-accounts`/`CartolaUploadPage`). Alinear la línea de Context con AC3 (suavizar a "Ary apaga Supabase por fuera SÓLO tras migrar bank-accounts").
- [x] [Review][Patch] (APLICADO 2026-06-17 — AC2 + Task 2 reformulados: captura de evidencia antes de revertir) AC2 no verificable — el test "editar→revertir" deja el estado final == inicial, sin artefacto persistente que pruebe la SoT-editabilidad. Reformular para que la verificación deje evidencia (log/screenshot del reporte reflejando el cambio antes de revertir), o usar una edición legítima.
- [x] [Review][Patch] (APLICADO 2026-06-17 — References suavizado) `manual/` presentado como destino decidido vs ADR-001 §3/§49 que lo deja "confirmar al implementar 10.3" — References ("destino promoción = manual/") y AC2 lo afirman como cerrado. Suavizar para no citarlo como decisión ratificada de 10.3.
- [x] [Review][Patch] (APLICADO 2026-06-17) Cleanups menores de consistencia del doc — (a) `blocks: [balance-sheet-flip, ...]` usa un slug no resoluble a story-id; (b) AC4 "discontinuado en su totalidad" contradice retener `pipeline/sync.py` + `workflow_dispatch`; (c) AC8 "ejecutable en < 30 min" no es testeable sin un task que lo mida; (d) AC6 pide `epic-9-retrospective disponible` pero Task 6 lo dropeó.
- [x] [Review][Defer] Dashboards balance-sheet (Activos/Pasivos) sin smoke post Sheets→read-only [9-11-deprecation-sheets.md AC7] — deferred, pertenece a la story del flip del balance-sheet. AC7 los excluye explícitamente; tras AC5 (read-only) quedan sin cobertura de regresión, pero el flip es out-of-scope.
