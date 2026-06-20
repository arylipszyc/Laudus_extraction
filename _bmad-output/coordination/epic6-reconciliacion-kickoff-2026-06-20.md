# Kickoff Epic 6 — Reconciliación Mensual (handoff a sesión fresca)

**Fecha:** 2026-06-20
**De:** sesión que cerró Epic 9 (retro + cleanup c4)
**Para:** la próxima sesión que arranca Epic 6

## Contexto: dónde está el proyecto

- **Epic 9 (migración a Beancount) — CERRADO de verdad.** Cutover live en prod, validado peso-por-peso vs el contador. El cleanup del andamiaje (Story 9.16) sacó la doble fuente: Beancount es la **fuente única**, sin Sheets, sin Supabase, sin feature flags. Retrospectiva hecha (`epic-9-retro-2026-06-20.md`).
- **Epic 10 (reportes) — funcionalmente done** (10.1/10.2/10.3). Sin retro formal aún (opcional).

## Qué es Epic 6 y por qué ahora

Reconciliación mensual cartola bancaria ↔ Laudus/Beancount. Estaba parqueado "para después de Epic 9 done" → **ahora desbloqueado**.

**Lo grande ya está construido durante Epic 9:**
- **Motor de reconciliación (Story 9.6b)** — `pipeline/importers/` : `matching_engine` (7 estados), `fx_calculator`, `discrepancy_writer` (JSONL append-only), `reconcile.py` (`reconcile_and_build`, `process_match_result`, `commit_reconciliation`). Engine LISTO y testeado.
- **Dashboard de reconciliación (Story 9.12)** — `ReconciliationPage` + badge, lee `ledger/_meta/cartola-discrepancies.jsonl`. DONE.
- **Extracción de cartola PDF (9.5h/9.6a)** — Gemini Flash 3.5 + validators, parser beangulp. DONE.

## El SEAM (lo que falta wirear)

Per el storyfile de **9.6b** y `pipeline/importers/README.md`: el **wiring del upload real** está pendiente. Hoy el promote del upload hace `extract`; falta reemplazarlo por **`reconcile_and_build` + `load_laudus_entries`** para que subir una cartola dispare la reconciliación de verdad (no solo la extracción). El engine ya existe; es conectar el flujo `cartolas/router.py` (upload) → reconcile.

> Verificar el estado exacto del SEAM como primer paso (el código pudo moverse). Punto de entrada: `pipeline/importers/reconcile.py` + `backend/app/api/v1/cartolas/router.py` + el storyfile `9-6b-matching-cartola-laudus-discrepancias.md`.

## Primer paso recomendado

El epic se escribió **pre-pivot c4** → su definición está stale. Antes de codear:
1. **Reframear Epic 6 bajo c4** — `bmad-correct-course` o sesión con John (PM): la reconciliación ya no es "contra Sheets" sino el wiring del engine Beancount existente.
2. **Mapear el SEAM** real (qué falta entre upload y reconcile) — `bmad-investigate` si querés precisión antes de planificar.
3. Crear stories → dev.

## Hilos abiertos (NO son Epic 6)
- **Auditoría de inversiones (Valentina)** — DEFERRED, bloqueado esperando que el contador confirme saldos reales del custodio. Acción de Ary (mail al contador), no código. Ver `valentina-auditoria-ingresos-inversiones-2026-06-20.md`.
- **Corrección plena de TC (estado 2)** — diseño de Valentina, necesita una cartola de TC de muestra.
