# Rollback runbook — deprecación de Sheets (Story 9.11)

**Objetivo:** revertir la deprecación de Sheets/Supabase y volver al path legacy (reporte leyendo de Sheets, sync semanal repoblando Sheets) en **< 30 minutos**.

**Cuándo usar:** si post-deprecación el reporte `/reportes/gastos` se rompe o deja de cuadrar y la causa raíz no se resuelve rápido en el path Beancount.

**Responsable:** Ary.

> **Nota de diseño:** este rollback debería ser raro. El reporte ya leía de Beancount en prod **antes** de 9.11 (flag `USE_BEANCOUNT_ENGINE_LEDGER=true`, validado peso-por-peso vs el workbook del contador). 9.11 no cambió el motor del reporte — solo retiró el sync legacy y degradó Sheets a read-only. Revertir 9.11 ≠ arreglar un bug del reporte; es volver al archivo histórico como fuente.

---

## Pasos (cronometrados en dry-run al escribir, 2026-06-17)

| # | Paso | Comando / acción | Tiempo estimado |
|---|---|---|---|
| 1 | **Reporte vuelve a Sheets** | En Render (backend `srv-d7dk4hv41pts73a35aqg`), setear env `USE_BEANCOUNT_ENGINE_LEDGER=false` y redeploy. El reporte vuelve a leer la pestaña `ledger_final` de Sheets. | ~5 min (redeploy) |
| 2 | **Reactivar el cron de sync a Sheets** | Restaurar el workflow borrado desde git y commitear: `git show 99bb5b0:.github/workflows/sync-weekly.yml > .github/workflows/sync-weekly.yml` → commit + push. El cron `0 9 * * 1` (`python -m pipeline.sync`) vuelve a repoblar Sheets cada lunes. Disparo manual inmediato vía GitHub UI (`workflow_dispatch`) si se necesita repoblar ya. | ~3 min (+ run del sync) |
| 3 | **Restaurar permisos Editor en Drive** | En el Google Sheet (Drive), devolver a los usuarios family + la service account de `Viewer` → `Editor`. El sync del paso 2 necesita Editor para escribir. **Hacer ANTES de disparar el sync manual.** | ~3 min |
| 4 | **(Solo si se apagó) Reactivar Supabase standby** | En el dashboard de Supabase, "Resume project" (free tier se auto-pausa). Tarda 1-3 min en estar caliente (DNS antes que PostgREST). Solo aplica si en algún momento se apagó — **a la fecha de 9.11 NO se apagó** (sigue prendido por `bank-accounts`/`CartolaUploadPage`, ver Story 9.14). | ~3 min (si aplica) |

**Total estimado:** ~14 min de trabajo activo (+ tiempo de redeploy/sync run en background). Holgado dentro del objetivo de < 30 min.

### Validación del dry-run (2026-06-17)

- Paso 2 (git-restore del workflow): comando `git show 99bb5b0:.github/workflows/sync-weekly.yml` verificado — devuelve el YAML completo del cron borrado. SHA `99bb5b0` = commit anterior al borrado de 9.11 (HEAD al momento de la deprecación). 0s.
- Pasos 1, 3, 4: acciones de dashboard (Render/Drive/Supabase) — no scripteables desde el repo; tiempos estimados por experiencia operativa (redeploy Render ~5 min, toggle de permisos Drive ~3 min, resume Supabase 1-3 min).

---

## Orden importante

- **Paso 3 (Editor) antes de disparar el sync (paso 2 manual)** — si el sync corre contra un Sheet viewer-only, falla escribiendo.
- **Paso 1 (flag) es el que efectivamente devuelve el reporte a Sheets** — los pasos 2-4 repueblan/habilitan Sheets, pero sin el flag el reporte sigue leyendo Beancount.

## Después del rollback

- Investigar la causa raíz que motivó el rollback en el path Beancount (ledger, importer Laudus, o el reporte) antes de re-intentar la deprecación.
- El git history del ledger Beancount sigue siendo el backup autoritativo (NFR14), independiente de Sheets.
