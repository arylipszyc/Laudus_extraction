# Deprecación de Sheets/Supabase como source of truth — audit log

**Fecha:** 2026-06-17
**Story:** 9.11 — Plan de cuentas en Beancount (SoT) + deprecación de Sheets/Supabase
**Responsable:** Ary
**ADR de referencia:** `_bmad-output/planning-artifacts/adr-001-plan-de-cuentas-beancount-source-of-truth.md` (ratificado por Winston 2026-06-10)

---

## Qué cambió

El **single source of truth** del plan de cuentas (taxonomía `Categoria1/2/3` + metadata bancaria) pasa a ser la metadata `Open` de **`ledger/accounts.beancount`** (baseline) **+ la zona `manual/`** (edits humanos vía Fava), editable directamente. **Google Sheets queda como archivo histórico read-only; Supabase `plan_de_cuentas` queda deprecado (sin borrar).**

El reporte `/reportes/gastos` ya leía categorías desde la metadata `Open` de Beancount en prod (flag `USE_BEANCOUNT_ENGINE_LEDGER=true`) antes de esta story; 9.11 ratifica el estado, retira el sync legacy y degrada Sheets.

---

## Timeline

| Fecha | Hito |
|---|---|
| 2026-04-30 | Pivot arquitectónico c4 aprobado (Beancount engine). Decisión Ary: Sheets read-only, sin Vercel. |
| 2026-06-10 | ADR-001 ratificado por Winston: beancount SoT, retirar `generate_accounts.py`/Supabase de rutina, promoción de cuentas = Story 10.3. Sprint-change-proposal amplía 9.11. |
| 2026-06-16 | Cutover Beancount LIVE en prod (flag `USE_BEANCOUNT_ENGINE_LEDGER=true`). Reporte cuadra peso-por-peso vs workbook del contador (ene–may). Cron importer Laudus LIVE (Story 9.4). |
| **2026-06-17** | **Story 9.11 ejecutada (este doc).** |

---

## Decisiones de scope (Ary, 2026-06-17)

1. **Balance-sheet flip → AFUERA de 9.11.** `USE_BEANCOUNT_ENGINE_BALANCE_SHEET` sigue off; los dashboards Activos/Pasivos siguen en Sheets. 9.11 lo desbloquea; va en story aparte con su propia paridad de balance.
2. **Deprecación Supabase/`generate_accounts.py` = documentar + retirar de rutina, sin borrar código vivo.** Cero riesgo de regresión.
3. **Apagar el proyecto Supabase standby = BLOQUEADO fuera de 9.11.** Lo consume `GET /api/v1/bank-accounts/` (→ `SupabaseRepository`) vía `CartolaUploadPage`. Pre-condición para apagarlo = migrar `bank-accounts` a metadata de `accounts.beancount` → **Story 9.14**.
4. **AC1 (parity) cerrado PASS-con-caveat** (ver abajo).

---

## ⚠️ Ventana de data congelada en los dashboards Activos/Pasivos (consecuencia del borrado del cron)

**Identificado en el code-review de 9.11 (2026-06-17). Decisión Ary: documentar + flipear 9.15 pronto post-merge.**

Al borrar `sync-weekly.yml` se retiró el **único writer** de las pestañas `balance_sheet_{entity}` (`pipeline/sync.py` → `replace_sheet`). Mientras `USE_BEANCOUNT_ENGINE_BALANCE_SHEET` siga **off**, los dashboards Activos/Pasivos (`BalanceSheetPage`) leen esas pestañas (`dashboard/service.py`, rama OFF) — y el importer Laudus→Beancount **no escribe a Sheets**. 

**Consecuencia:** entre el merge de este branch y el flip de Story 9.15, los dashboards Activos/Pasivos muestran **data estática del último run del cron (último lunes)**, sin warning en la UI. El reporte `/reportes/gastos` NO está afectado (ya lee Beancount). 

**Mitigación (acordada):** correr el parity + flipear `USE_BEANCOUNT_ENGINE_BALANCE_SHEET=true` (Story 9.15) **pronto después de mergear** este branch para cerrar la ventana. Hasta el flip, tratar los Activos/Pasivos como congelados a la fecha del último sync.

---

## AC1 — Resultado de la paridad (caveat documentado)

`scripts/parity_check_sheets_vs_beancount.py --from 2025-06 --to 2026-06` → exit 1 (no 0 CLP exacto):

- **15 diffs** en la ventana completa; **12 son drift del mes en curso (junio 2026)** — beancount adelantado por el import del día vs Sheets del último lunes. Esperado en un mes abierto con dos fuentes a distinto watermark (incl. `990099`, cuenta de cierre, 179M).
- **4 diffs reales en marzo 2026 (202K CLP):** `411037` (−80K), `111009` (+80K), `111005` (+21K), `430083` (−21K).

**Investigación:** se refrescó el ledger local (backfill Laudus → hoy) y los diffs de marzo quedaron idénticos → **no es staleness local**. El fetch crudo de Laudus confirmó que los 80K (Movilización) y 21K (Wizo) **no existen en Laudus vivo** — son asientos **fantasma de la pestaña Sheets `ledger_final`** (stale / manuales / borrados de Laudus tras un sync viejo).

**Veredicto:** beancount = Laudus vivo = validado peso-por-peso vs el workbook del contador (ene–may) es la fuente correcta. El residual del gate está **100% del lado que se retira (Sheets)** — es exactamente el tipo de divergencia que la deprecación corrige. Decisión Ary: **proceder + documentar** (no se abre issue de importer: no hay bug en beancount).

---

## Cambios concretos (commit de deprecación)

- `bootstrap/generate_accounts.py` — header DEPRECATED (solo re-bootstrap DR), lógica intacta.
- `backend/app/api/v1/plan_de_cuentas/router.py` — deprecación en docstring de módulo + endpoints `GET /` y `POST /sync`, código vivo intacto.
- `bootstrap/README.md` — SoT del plan = `accounts.beancount` + `manual/`, no Supabase; apagado de Supabase bloqueado por Story 9.14.
- `.github/workflows/sync-weekly.yml` — **borrado** (era el cron vivo `0 9 * * 1` que escribía a Sheets).
- `.github/workflows/backup.yml` — **borrado** (cron muerto: `python sync.py` apuntaba a path movido a `pipeline/`).
- `_bmad-output/planning-artifacts/architecture.md` — header DEPRECATED (superseded por `architecture-c4.md`).
- `_bmad-output/planning-artifacts/architecture-c4.md` — §7.4/§7.8 marcadas COMPLETADO/CERRADO; refs a "Sheets sync legacy en paralelo" retiradas.
- `pipeline/README.md` — contrato env re-homeado desde el `README.txt` borrado; `pipeline/sync.py` marcado como fallback DR.
- `docs/rollback-deprecation-sheets.md` — runbook de rollback (< 30 min, dry-run cronometrado).

---

## NFR14 (backup)

Cubierto por construcción por el **git history del propio ledger Beancount** (cada sync del importer commitea). `pipeline/sync.py` se retiene como fallback de re-importación histórica de Laudus. El run history de `backup.yml` no se pudo verificar desde el entorno local (sin `gh` CLI); dado que su step estaba roto (`python sync.py` → path inexistente), no se asume que haya producido artefactos de backup.

---

## Pendientes (fuera de 9.11)

- **Sheets read-only en Drive (AC5):** acción manual de Ary — cambiar permisos family + service account a `Viewer`. Documentar en MEMORY.
- **Smoke test del reporte (AC7):** navegar `/reportes/gastos` ene–may 2026 vs workbook del contador en prod.
- **Balance-sheet flip (Story 9.15):** story aparte — **prioritario post-merge** para cerrar la ventana de data congelada (ver sección ⚠️ arriba).
- **Apagar Supabase:** tras Story 9.14.
