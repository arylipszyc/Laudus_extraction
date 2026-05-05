---
story: 9.11
title: Deprecation Sheets como source of truth
status: ready-for-dev
epic: 9
depends_on: [9.1, 9.2, 9.4]
gate_condition: paridad-1-1-confirmada
blocks: []
---

# Story 9.11 — Deprecation Sheets como source of truth

## User Story

As Ary,
I want Sheets to be promoted from "source of truth" to "read-only historical archive" once the Beancount ledger is confirmed to match Sheets 1:1 cuenta-por-cuenta and período-por-período,
So that we operate on a single source of truth, eliminate duplicate-write maintenance burden, and keep Sheets accessible only as legacy reference.

## Context

F4-final del plan de migración (`architecture-c4.md` §7.4 + §7.8). Q10 cerrada por Ary: "En cuanto el modelo nuevo esté armado y la información cuadre 1:1. Sheets queda read-only. **No espera 1 mes paridad formal — Ary considera el mes parte natural del cuadre.**"

Esta story es un **gate operacional** — no es código nuevo significativo, es:
1. Validación que la paridad 1:1 cuenta-por-cuenta está confirmada (smoke test).
2. Switch de feature flags `USE_BEANCOUNT_ENGINE_*` a `true` en producción.
3. Desactivación de `pipeline/sync.py` legacy (path Sheets) — el cron actual de GitHub Actions o equivalente.
4. Sheets se marca read-only manualmente (Google Drive permissions: solo viewer).
5. Documentación del switch + actualización de BOND/MEMORY.

## Acceptance Criteria

**AC1 — Paridad 1:1 confirmada**

**Given** el thin API leyendo del ledger (Story 9.2 con flags `true`) y Sheets corriendo en paralelo
**When** se corre el script de validación `scripts/parity_check_sheets_vs_beancount.py` para los últimos 12 meses + balance al cierre de cada mes + por entity
**Then** la diferencia es **0 CLP** en cada (mes, entity, account)
**And** si hay diferencia: el script imprime tabla detallada y la story NO procede; bug a investigar (probable mapping mal en Story 9.1) y abrir issue

---

**AC2 — Feature flags `true` en producción**

**Given** AC1 pasa
**When** se actualiza la config de Render del servicio `laudus-backend`
**Then** las 4 env vars `USE_BEANCOUNT_ENGINE_*` están `true`
**And** el servicio se restartea
**And** los dashboards siguen funcionando idénticos visualmente (regression test post-switch)

---

**AC3 — `pipeline/sync.py` legacy desactivado**

**Given** el sync legacy a Sheets corre como cron (GitHub Action existente, o cron Render)
**When** se desactiva
**Then** el workflow GitHub Actions `.github/workflows/backup.yml` (o equivalente) se actualiza para no correr más el sync Sheets — solo el backup snapshot read-only
**And** el endpoint `POST /api/v1/sync/trigger` ya solo dispara el importer Laudus → Beancount (Story 9.4)

---

**AC4 — Sheets read-only (manual)**

**Given** AC1-AC3 pasaron
**When** Ary actualiza permisos del Google Sheet en Drive
**Then** los usuarios family + service account tienen permiso `Viewer` (no `Editor`)
**And** Ary documenta el cambio en BOND/MEMORY (memoria reference): "Sheets es archivo histórico read-only desde {fecha}"

---

**AC5 — Audit log del switch**

**Given** el switch ocurre
**When** se completa
**Then** se appendea un commit explícito al repo: `chore(deprecation): Sheets retired as source of truth — Beancount is canonical`
**And** el commit incluye: actualización de `architecture.md` (legacy doc) marcando Sheets como "deprecated", actualización de `architecture-c4.md` borrando referencias a "Sheets sync legacy en paralelo", actualización de `sprint-status.yaml` con epic-9 progress

---

**AC6 — Smoke test post-switch (regression)**

**Given** los dashboards corren contra Beancount
**When** se navega los 4 dashboards (Activos/Pasivos, Ingresos/Gastos, Estado de Resultado, Variación Patrimonial) por entity (EAG, Jocelyn, Jeannette, Johanna, Jael) y períodos (Q1 2026, FY 2025)
**Then** no hay errores visuales, charts cargan, drill-down funciona, badges flagged se muestran correctamente
**And** sync timestamp del Header refleja el último run del importer Laudus (cron sábados)

---

**AC7 — Rollback plan documentado**

**Given** algo se rompe post-switch
**When** se decide rollback
**Then** existe un runbook `docs/rollback-deprecation-sheets.md` que lista los pasos: revertir flags `false` + reactivar workflow Sheets sync + restaurar permisos Editor en Drive
**And** el rollback es ejecutable en < 30 minutos

---

## Tasks / Subtasks

- [ ] Task 1: Script de validación paridad
  - [ ] Crear `scripts/parity_check_sheets_vs_beancount.py`
  - [ ] Para cada (entity, mes, account): comparar balance Sheets vs balance Beancount BQL
  - [ ] Output tabla CSV + summary (count diferencias > 0)
  - [ ] Threshold: 0 CLP (no porcentaje — Q10 explicit: cuadre 1:1)
  - [ ] Documentar uso en `scripts/README.md`

- [ ] Task 2: Correr el script y resolver diferencias
  - [ ] Generar reporte; si hay diferencias → investigar (mapping cuenta, FX, missing JE, etc.) y arreglar en Story 9.1 (bootstrap regenera ledger)
  - [ ] Iterar hasta 0 diferencias
  - [ ] Esto NO es código nuevo de esta story — es trabajo de QA antes de cumplir AC1

- [ ] Task 3: Switch de flags
  - [ ] Render dashboard: editar env vars `USE_BEANCOUNT_ENGINE_*` a `true`
  - [ ] Restart del servicio
  - [ ] Smoke test (AC6)

- [ ] Task 4: Desactivar sync legacy + discontinuar backup snapshot Sheets
  - [ ] Editar `.github/workflows/backup.yml` para quitar el step de sync activo
  - [ ] **Discontinuar `.github/workflows/backup.yml` (snapshot diario Sheets) completamente** — Ary confirmó OK porque `pipeline/sync.py` queda como fallback para reimportar histórico Laudus si fuera necesario. El git history del propio ledger Beancount cubre NFR14 (backup) por construcción.
  - [ ] Commit del cambio
  - [ ] Apagar el proyecto Supabase en standby (Story 4.0 sunk-cost se cierra junto con esta story)

- [ ] Task 5: Sheets read-only (manual, fuera de CI)
  - [ ] Ary cambia permisos en Drive
  - [ ] Documentar el cambio en MEMORY (memoria reference)

- [ ] Task 6: Documentación del switch
  - [ ] Update `_bmad-output/planning-artifacts/architecture.md` con header "DEPRECATED — superseded by architecture-c4.md desde {fecha}"
  - [ ] Update `_bmad-output/planning-artifacts/architecture-c4.md` removiendo referencias a "Sheets sync legacy"
  - [ ] Update `sprint-status.yaml`: `epic-9-retrospective` puede dispararse post-9.11
  - [ ] Crear `docs/rollback-deprecation-sheets.md` (AC7)
  - [ ] Crear `docs/deprecation-sheets-{fecha}.md` con timeline + decisiones + responsable (Ary)

---

## Dev Notes

### Input autoritativo

`architecture-c4.md` §7.4 + §7.8 — plan de transición + drift mitigation. Q10 cierre Ary: cuadre 1:1, Sheets read-only.

### NO es deprecation total de Sheets

Sheets queda **read-only** (no se borra). Razón: hasta 2025 Sheets fue el source of truth, hay valor histórico en preservarlo. Costo Drive ≈ $0. Sólo si Ary decide explícitamente borrar el sheet, se hace en story aparte.

### Gate operacional, no implementación heavy

La mayoría del trabajo es validación + config. La única "code" nueva es Task 1 (parity script) y Task 4 (workflow edit). El resto son acciones operativas + docs.

### Riesgos

- **Diferencias inesperadas en paridad:** Q4 (FX) puede causar que ciertos balances USD↔CLP no cuadren si la decisión de Q4 difiere del approach actual. Esta story se ejecuta DESPUÉS de Q4 cerrada y bootstrap (9.1) re-ejecutado.
- **GitHub Actions backup.yml:** discontinuado en su totalidad (decisión Ary 2026-04-30). NFR14 (backup) lo cubre el git history del ledger Beancount. Sheets queda read-only — el snapshot pierde valor.

### Out of scope

- Borrar Sheets físicamente (no se borra, queda read-only).
- Migrar el contenido de comments/históricos del Sheet a Beancount metadata (si ese feature existe — no aplica acá).
- Cambios al backup snapshot policy (NFR14) — evaluar en story aparte si Ary lo pide.

### Project structure

```
scripts/
  parity_check_sheets_vs_beancount.py      # NEW
  README.md                                # MODIFY (instrucciones)
.github/workflows/
  backup.yml                               # MODIFY (desactivar sync, mantener snapshot opcional)
docs/
  rollback-deprecation-sheets.md           # NEW
  deprecation-sheets-{fecha}.md            # NEW (post-execution audit)
_bmad-output/planning-artifacts/
  architecture.md                          # MODIFY (header DEPRECATED)
  architecture-c4.md                       # MODIFY (remover refs a Sheets legacy)
```

### References

- [Source: architecture-c4.md §7.4 — Plan F3]
- [Source: architecture-c4.md §7.8 — Riesgo de drift]
- [Source: bob-x-moishe-epic9-2026-04-30.md — Q10 cierre Ary]
