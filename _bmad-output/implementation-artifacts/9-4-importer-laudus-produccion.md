---
story: 9.4
title: Importer Laudus en producción (cron sábados 23:59 + on-demand)
status: ready-for-dev
epic: 9
depends_on: [9.1]
blocks: []
---

# Story 9.4 — Importer Laudus en producción

## User Story

As Ary,
I want a production-grade Laudus ERP importer that runs every Saturday at 23:59 (Chile time) and is triggerable on-demand from the frontend,
So that the Beancount ledger stays in sync with Laudus weekly without manual intervention, and I can force a sync whenever I need fresher data.

## Context

F3 + F4 (parte) del plan de migración (`architecture-c4.md` §3 + §7.4). Reusa lo bueno del `pipeline/sync.py` actual:
- `pipeline/services/{ledger,balance_sheet}_service.py` (auth, retry, paginación) — preservados intactos.
- `pipeline/utils/dates.py` — preservado.
- `pipeline/models.py` map functions — preservadas; `enrich_*` se reescriben para leer de Supabase `plan_de_cuentas` (registry) en lugar de Sheets.

Lo nuevo:
- `pipeline/writers/beancount_writer.py` — toma JEs Laudus normalizadas y emite directivas.
- Reescritura de `pipeline/sync.py` orquestación → llama al writer Beancount en lugar del `gspread_utils.py`.
- Render Cron Job `laudus-importer-laudus` corriendo `python -m pipeline.importers.laudus_run` los sábados 23:59 (decisión Q3 — Ary prefiere semanal, NO diario como recomendó Winston).
- Endpoint on-demand `POST /api/v1/sync/trigger` preservado (Story 2.1) — dispara el mismo importer en el backend.

## Acceptance Criteria

**AC1 — Writer Beancount emite directivas correctas**

**Given** una lista de JEs Laudus normalizadas (output de `ledger_service.fetch + map_ledger_row`)
**When** `BeancountWriter.write_jes(jes, target_dir="ledger/imports/laudus/")` es invocado
**Then** se generan archivos `imports/laudus/YYYY-MM.beancount` (un archivo por mes — write-and-replace)
**And** cada `Transaction` tiene metadata: `id:` (= `journalentryid`), `je_num:`, `source: "laudus-erp"`
**And** las cuentas referenciadas usan el mapping del registry `plan_de_cuentas` (Supabase) + tabla §2.3
**And** las JEs en USD preservan amount original + (eventualmente, post-Q4) FX embebido en metadata

---

**AC2 — Idempotencia por `id:` metadata**

**Given** el importer corre dos veces seguidas con el mismo input (sin nuevas JEs en Laudus)
**When** termina la segunda corrida
**Then** los archivos en `imports/laudus/` son bit-idénticos al fin de la primera corrida
**And** no se crean duplicados ni archivos extras

---

**AC3 — Cron schedule: sábados 23:59 hora Chile (Q3)**

**Given** un Render Cron Job llamado `laudus-importer-laudus` está configurado
**When** revisás su schedule
**Then** corre los sábados a las 23:59 hora Chile (CLT/CLST según DST → cron expression `59 23 * * 6` con `TZ=America/Santiago`)
**And** NO corre diariamente (decisión Q3 difiere de la recomendación original de Winston)

---

**AC4 — Endpoint on-demand preservado**

**Given** `POST /api/v1/sync/trigger` (de Story 2.1) sigue existiendo
**When** un usuario `contador` lo llama con `{}` o `{"mode": "incremental"}`
**Then** el backend dispara el importer Laudus (subprocess local, o Render API call, o background task)
**And** la response es inmediata: `{"status": "triggered", "job_id": "..."}`
**And** la corrida es visible vía `GET /api/v1/sync/status` cuando completa
**And** un usuario `family` (ex `owner`) llamando este endpoint recibe HTTP 403 (sin cambios vs Story 2.1)

---

**AC5 — Modo full-backfill preservado**

**Given** `POST /api/v1/sync/trigger` con `{"mode": "backfill", "from_date": "2021-01-01"}`
**When** el endpoint se invoca
**Then** el importer corre en modo full-backfill (regenera todos los archivos `imports/laudus/YYYY-MM.beancount` desde 2021-01)
**And** este es el mismo modo que usa Story 9.1 (bootstrap) para la primera carga histórica

---

**AC6 — Cuentas nuevas → `_new-accounts-pending.beancount`**

**Given** durante una corrida aparece un `account_number` que no está en `accounts.beancount`
**When** el importer la encuentra
**Then** NO abre la cuenta automáticamente
**And** appendea entry tentativo a `imports/laudus/_new-accounts-pending.beancount` (formato §3.4)
**And** las JEs que la referencian van a `imports/laudus/YYYY-MM.beancount` con `tag #pending-account`
**And** el run log incluye: "N cuentas nuevas pendientes review"
**And** un email/log al admin (Ary) se dispara — método de notificación: log estructurado en stdout (Render logs) + entrada en `_meta/import-log.jsonl`. Email opcional v2.

---

**AC7 — Validación pre-commit con `bean-check`**

**Given** el importer terminó de escribir nuevos archivos
**When** se corre `bean-check ledger/main.beancount`
**Then** si exit-code 0 → continúa con `git add + commit + push`
**And** si exit-code ≠ 0 → rollback: revertir cambios en `imports/laudus/`, no commit, log error completo a `_meta/import-log.jsonl` + Render stdout

---

**AC8 — Lock file contra race con otros writers**

**Given** otro writer (importer cartolas o el wrapper de Fava) podría estar activo
**When** el importer Laudus inicia
**Then** intenta tomar `ledger/.import.lock` (filesystem lock)
**And** si ya existe con mtime < 5min → wait con polling cada 5s, max 60s; si timeout → abort + log
**And** si la toma exitosa → la libera al final (incluyendo paths de error)

---

**AC9 — Commit message estructurado**

**Given** el importer commitea exitosamente
**When** revisamos `git log -1 -- ledger/imports/laudus/`
**Then** el mensaje es: `[importer-laudus] sync YYYY-MM-DD: +N JE, M dedup, K pending account` con valores reales
**And** el push va a branch `main` (no PR — single dev)

---

**AC10 — Smoke test post-deploy**

**Given** el cron está deployado en Render
**When** se dispara una corrida manual desde Render dashboard (o via on-demand endpoint)
**Then** completa en < 10 minutos (incremental mode con 7 días de delta)
**And** `_meta/import-log.jsonl` registra la corrida con success=true
**And** `git log` sobre `ledger/` muestra el commit

---

## Tasks / Subtasks

- [ ] Task 1: `BeancountWriter` (AC1)
  - [ ] Crear `pipeline/writers/beancount_writer.py`
  - [ ] Input: lista de JEs normalizadas (mismo shape que el actual `map_ledger_row`)
  - [ ] Output: archivos `.beancount` agrupados por mes
  - [ ] Resolver cuenta destino: leer Supabase `plan_de_cuentas` + aplicar tabla §2.3 + slug §2.1
  - [ ] Tests unitarios: 5-10 casos de JE → directivas; verificar metadata + format

- [ ] Task 2: Reescribir orquestación `pipeline/sync.py` → `pipeline/importers/laudus_run.py`
  - [ ] Mantener `pipeline/sync.py` actual (path Sheets) como fallback durante F1+F3 (drift mitigation §7.8)
  - [ ] Crear `pipeline/importers/laudus_run.py` que llama a `ledger_service.fetch + balance_sheet_service.fetch` y luego al `BeancountWriter`
  - [ ] Modos: `incremental` (default) y `backfill` (con `from_date`)
  - [ ] Determinar `from_date` para `incremental`: `max(date)` en `imports/laudus/*.beancount` actuales

- [ ] Task 3: Idempotencia (AC2)
  - [ ] Pre-write: leer todos los `id:` existentes en `imports/laudus/*.beancount`
  - [ ] Filtrar JEs nuevas: skip las que ya tienen `id` matching
  - [ ] Agrupar por mes y regenerar `imports/laudus/YYYY-MM.beancount` write-and-replace

- [ ] Task 4: Cuentas nuevas (AC6)
  - [ ] Pre-write: leer `accounts.beancount` y construir set de cuentas conocidas
  - [ ] Si una JE referencia una cuenta nueva: emitir entry tentativo en `_new-accounts-pending.beancount` + tag JE con `#pending-account`
  - [ ] Acumular contador para reporte al final

- [ ] Task 5: Lock file (AC8)
  - [ ] Función helper `acquire_lock(path, timeout=60, max_age=300)`
  - [ ] Manejar limpiar stale locks (mtime > max_age)
  - [ ] Liberar siempre — usar context manager / try-finally

- [ ] Task 6: bean-check pre-commit + git commit/push (AC7 + AC9)
  - [ ] Después de write: `subprocess.run(["bean-check", "ledger/main.beancount"], ...)`
  - [ ] Si OK: `git add ledger/imports/laudus/`, `git commit -m "..."`, `git push origin main`
  - [ ] Si KO: revertir cambios (re-leer git tree y restore archivos), log error completo
  - [ ] Auth git push: SSH key `BEANCOUNT_DEPLOY_KEY` (write access, configurado solo para este servicio)

- [ ] Task 7: `_meta/import-log.jsonl` append
  - [ ] Cada corrida appendea una línea con: `ts`, `mode`, `from_date`, `to_date`, `jes_added`, `jes_dedup`, `pending_accounts`, `success`, `error_msg`, `git_commit_sha`
  - [ ] Esta línea es lo que Story 9.2 lee para `GET /sync/status`

- [ ] Task 8: Render Cron Job config (AC3)
  - [ ] Crear nuevo Render Cron Job `laudus-importer-laudus`
  - [ ] Schedule: `59 23 * * 6` con `TZ=America/Santiago`
  - [ ] Command: `python -m pipeline.importers.laudus_run`
  - [ ] Env vars: Laudus credentials, Supabase credentials, `BEANCOUNT_DEPLOY_KEY`, `BEANCOUNT_REPO_URL`, `LEDGER_PATH`
  - [ ] Persistent disk con git clone del ledger en startup

- [ ] Task 9: Endpoint on-demand (AC4 + AC5)
  - [ ] Adaptar `backend/app/api/v1/sync/router.py` para llamar al nuevo `laudus_run` en lugar del path Sheets cuando flag `USE_BEANCOUNT_ENGINE_LEDGER=true`
  - [ ] Mantener job_id tracking compatible con frontend actual
  - [ ] RBAC sin cambios (de Story 1.4 + 2.1)

- [ ] Task 10: Smoke test (AC10)
  - [ ] Documentar en `pipeline/importers/README.md` cómo correr smoke local + cómo verificar en Render

---

## Dev Notes

### Input autoritativo

`architecture-c4.md` §3 — Contrato del importer Laudus, §7.4 — Plan F3, §7.7 — Costo hundido (qué se preserva).

### Diferencia clave vs recomendación original Winston

Winston recomendó cron diario 02:00. **Q3 cerrada por Ary: cron sábados 23:59 + on-demand.** Razón: data Laudus se cierra al fin del mes contable; weekly alcanza para el caso de uso real de la family. On-demand cubre el caso "necesito refresh ahora".

### Reuso explícito

| Archivo | Acción |
|---|---|
| `pipeline/config/laudus_config.py` | preservado intacto |
| `pipeline/services/{ledger,balance_sheet}_service.py` | preservado intacto |
| `pipeline/utils/dates.py` | preservado |
| `pipeline/models.py` `map_*` functions | preservadas |
| `pipeline/models.py` `enrich_*` functions | reescribir para leer de Supabase |
| `pipeline/utils/gspread_utils.py` | NO usar más en path nuevo (path Sheets sigue por F3 mitigation; queda como dead code candidate post-9.11) |

### Mitigación de drift (§7.8)

Durante F1+F3 (transición), `pipeline/sync.py` ORIGINAL (path Sheets) **sigue corriendo en paralelo** con el nuevo importer. Misma source (Laudus API) → dos sinks (Sheets legacy + .beancount nuevo) → consistencia automática. Esto se desactiva en Story 9.11.

### Project structure

```
pipeline/
  importers/
    laudus_run.py                          # NEW — orquestador (reemplaza sync.py)
    README.md                              # NEW — runbook
  writers/
    beancount_writer.py                    # NEW
  sync.py                                  # PRESERVED — path Sheets sigue activo durante F3
  services/                                # NO CAMBIA
  config/                                  # NO CAMBIA
  utils/                                   # NO CAMBIA
backend/app/api/v1/sync/router.py          # MODIFY — selector via flag
ledger/_meta/import-log.jsonl              # NEW — append cada corrida
```

### References

- [Source: architecture-c4.md §3 — Importer Laudus]
- [Source: architecture-c4.md §7.4 — Plan F3]
- [Source: architecture-c4.md §7.8 — Drift mitigation]
- [Source: bob-x-moishe-epic9-2026-04-30.md — Q3 (cron sábados)]
- [Source: pipeline/services/ledger_service.py — preservado]
- [Source: backend/app/api/v1/sync/router.py — endpoint on-demand existente]
