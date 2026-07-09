# Story: Indicador "Datos de Laudus al:" muestra fecha real (pushear el import-log)

Status: ready-for-dev

<!-- Hardening de sync/importer (reabre Epic 2 en espíritu, sin feature nueva). No gated — 1 sola decisión de diseño (path no-op) tiene default recomendado. -->

## Story

As a **dueño / contador del family office**,
I want **que el indicador "Datos de Laudus al: <fecha>" muestre la fecha del último sync real de Laudus**,
so that **cuando lo miro sepa si los datos están frescos, en vez de ver "--" o una fecha vieja congelada que me hace dudar de si todo el sistema está roto**.

> **Contexto — bug COSMÉTICO confirmado con evidencia de prod, NO hay problema de datos.** El sync de Laudus **funciona**: los logs de Render del 2026-07-09 muestran `POST /sync/trigger → 202` + `[main a65d774] [importer-laudus] sync 2026-07-09: +17 JE` (commit real en origin). Corre y pushea bien. **Lo único roto es el indicador de fecha.**

## Causa raíz

El importer **nunca commitea/pushea** `ledger/_meta/import-log.jsonl`. El commit de cada sync ([laudus_run.py:423-425](pipeline/importers/laudus_run.py#L423-L425)) solo stagea `ledger/imports/laudus/` y `_new-accounts-pending.beancount`:

```python
result["git_commit_sha"] = git_commit_push(
    root, ["ledger/imports/laudus/", "ledger/imports/_new-accounts-pending.beancount"], message,
)
result["success"] = True
append_import_log(meta_dir, result)   # ← corre DESPUÉS del commit, y el path no está en el commit
```

Dos consecuencias:

1. **`append_import_log` corre después de `git_commit_push`** ([laudus_run.py:427](pipeline/importers/laudus_run.py#L427)) → la entrada fresca queda en el working-tree, **fuera** del commit.
2. **`git_commit_push` hace `fetch + rebase` antes de pushear** (hardening db9b41b) → esa entrada working-tree se **revierte** a la copia de origin, que está **congelada** (la última entrada `laudus`+`success` en git es del **2026-06-20**, aunque los syncs siguieron: 2026-06-28, 2026-07-05, 2026-07-09).

Resultado: el lector del status ([sync/service.py:25-58](backend/app/api/v1/sync/service.py#L25) `_read_import_log_last_sync`, que devuelve el timestamp del último registro `importer=="laudus"` con `success==true`) **nunca ve una fecha nueva** → `ledger.last_sync = null` → el frontend renderiza `"—"` ([ReportesPage.tsx:19-21](frontend/src/pages/ReportesPage.tsx#L19)).

Es el residual ya anotado en `deferred-work.md` ("import-log no se pushea → /sync/status ciego").

## Alcance / decisiones de diseño

### El fix (núcleo)

En el **path de éxito** de `run_import`: **(a)** appendear el import-log **antes** de `git_commit_push`, y **(b)** incluir `ledger/_meta/import-log.jsonl` en los paths commiteados. Así la entrada queda **commiteada** (sobrevive el rebase, es rebase-safe) y **origin avanza** (fuente única de verdad). El lector y el frontend **no cambian** — empiezan a mostrar la fecha real solos.

### Decisión de diseño (default recomendado, no gated)

**Path "no hay fechas nuevas"** ([laudus_run.py:392-396](pipeline/importers/laudus_run.py#L392)): un sync que no encuentra movimientos nuevos hace `append_import_log` y `return` **sin** commitear (no hay `imports/laudus/` que cambie). Con eso, un sync no-op **no** avanzaría la fecha del indicador — mostraría el último sync *con datos*, no el último *chequeo*.
**Recomendación:** commitear también el import-log en ese path (un commit chico de solo ese archivo, `git_commit_push` con `["ledger/_meta/import-log.jsonl"]`), para que "Datos de Laudus al:" refleje **la última vez que se consultó Laudus**, que es lo que el usuario espera del indicador. Si se prefiere no ensuciar la historia con commits de no-op, dejarlo fuera y documentar que la fecha = último sync con cambios. **Default: incluirlo.**

### `git_commit_sha` en el propio registro

Al appendear **antes** del commit, el registro del import-log no puede contener el sha del commit que lo incluye (chicken-egg) → `git_commit_sha` queda `null` en esa línea. **Es aceptable**: el lector del status solo usa `timestamp`/`importer`/`success`, no el sha. No introducir un segundo commit ni un amend para poblarlo.

### Fuera de scope

- **Paths de fallo/rollback** ([laudus_run.py:411-416,430-439](pipeline/importers/laudus_run.py#L411)): appendean con `success=False` y **no** commitean — se quedan así. Una corrida rolleada no debe avanzar nada, y el lector ignora los registros no-`success`. No tocar.
- **Setear `LEDGER_DIR`/`LEDGER_IMPORT_LOG` en Render** — hoy no están seteadas y ambas caen a rutas relativas al código (write y read apuntan al mismo `<repo>/ledger/_meta/import-log.jsonl`), así que el fix funciona sin tocar env. No es parte de esta story.
- **Reescribir el modelo de status** (per-tipo balance_sheet vs ledger, tiempo-de-ejecución vs rango-de-datos) — residuales de Epic 2 ya anotados, fuera de scope.

## Acceptance Criteria

1. **AC1 — Un sync con cambios deja el import-log commiteado y pusheado.**
   **Given** un `run_import` incremental que importa ≥1 JE nuevo (con `IMPORTER_GIT_ENABLED=true`),
   **When** termina exitosamente,
   **Then** el commit resultante **incluye** `ledger/_meta/import-log.jsonl` con una entrada nueva `importer="laudus"`, `success=true`, `timestamp` de esta corrida — y ese archivo, tras el `fetch+rebase` interno del push, **conserva** la entrada nueva (no se revierte).

2. **AC2 — El status refleja la fecha del último sync.**
   **Given** el import-log ya con la entrada nueva commiteada,
   **When** se llama `GET /api/v1/sync/status` (o `_read_import_log_last_sync` directamente),
   **Then** `ledger.last_sync` y `balance_sheet.last_sync` = el `timestamp` de la corrida más reciente (no `null`, no una fecha vieja).

3. **AC3 — Sync no-op también avanza la fecha (default recomendado).**
   **Given** un `run_import` incremental donde `start > to_date` (nada nuevo que traer),
   **When** termina,
   **Then** el import-log queda con la entrada `success=true` de esta corrida **y se commitea/pushea** (commit de solo `_meta/import-log.jsonl`), de modo que el indicador muestra este chequeo. *(Si Ary/dev elige la variante "no commitear no-ops", este AC se ajusta a: la entrada se registra localmente y el indicador muestra el último sync con cambios — documentar la elección.)*

4. **AC4 — Sin regresión en el commit de datos.**
   **Given** el cambio de orden (append antes del commit) + el path extra,
   **When** corre un sync con cambios,
   **Then** `ledger/imports/laudus/` y `_new-accounts-pending.beancount` se siguen commiteando igual que hoy, el mensaje de commit no cambia, y `git_commit_push` sigue siendo no-op si de verdad no hubo nada que commitear.

5. **AC5 — Tests.**
   **Given** los cambios,
   **When** corre la suite,
   **Then** hay un test que corre `run_import` con un `fetch_fn` fake (≥1 JE) sobre un repo git temporal y verifica que el import-log quedó **commiteado** (aparece en `git show --stat HEAD`) con la entrada de esta corrida; + un test del path no-op (según la elección de AC3); + no-regresión de que los paths de datos siguen en el commit. `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q` sin regresiones nuevas.

## Tasks / Subtasks

- [ ] **Task 1 — Reordenar + extender el commit del path de éxito** (AC1, AC4)
  - [ ] En [laudus_run.py:418-428](pipeline/importers/laudus_run.py#L418): mover `append_import_log(meta_dir, result)` **antes** de `git_commit_push`, y agregar `"ledger/_meta/import-log.jsonl"` a la lista de paths. Dejar `git_commit_sha=null` en el registro (chicken-egg, aceptable).
- [ ] **Task 2 — Commitear el import-log en el path no-op** (AC3, default recomendado)
  - [ ] En [laudus_run.py:392-396](pipeline/importers/laudus_run.py#L392): tras `append_import_log`, llamar `git_commit_push(root, ["ledger/_meta/import-log.jsonl"], f"[importer-laudus] check {to_date}: sin cambios")` antes del `return`. (Si se elige no hacerlo, documentar en Dev Notes y ajustar AC3.)
- [ ] **Task 3 — Tests** (AC5)
  - [ ] Test con repo git temporal (init + config user + remote fake o `IMPORTER_GIT_ENABLED=true` local sin push real — ver cómo lo hacen los tests de sync existentes): `run_import` con `fetch_fn` que devuelve filas → verificar `import-log.jsonl` en `git show --stat HEAD` + entrada `success=true`. Test del path no-op. No-regresión de los paths de datos.
  - [ ] Reusar el patrón de `backend/tests/test_sync.py` (fake spreadsheet/fetch en memoria).

## Dev Notes

### Evidencia de prod recogida para esta story (2026-07-09)

- **El sync funciona.** Logs Render (`srv-d7dk4hv41pts73a35aqg`, `laudus-backend.onrender.com`): `16:08 POST /sync/trigger → 202` + `[main a65d774] [importer-laudus] sync 2026-07-09: +17 JE, 1188 dedup, 0 pending account`. `a65d774` está en origin/main, rebaseado limpio sobre el commit de categorización previo.
- **El import-log en git está congelado en 2026-06-20** (última línea `laudus`+`success`). Los commits `[importer-laudus] sync` posteriores (2026-06-28 `2c7be2d`, 2026-07-05 `f4b06c7`, 2026-07-09 `a65d774`) **no tocan** `_meta/import-log.jsonl` → confirmado con `git log -- ledger/_meta/import-log.jsonl` (vacío para esos commits).
- **Env vars del backend:** `IMPORTER_GIT_ENABLED=true`; **no** hay `LEDGER_DIR` ni `LEDGER_IMPORT_LOG` → write (`_ledger_root()`, [laudus_run.py:38-42](pipeline/importers/laudus_run.py#L38)) y read (`_import_log_path()`, [sync/service.py:17-22](backend/app/api/v1/sync/service.py#L17)) resuelven ambos a `<repo>/ledger/_meta/import-log.jsonl` (mismo archivo). Por eso el fix funciona sin tocar Render.

### Archivos que se tocan

- **[pipeline/importers/laudus_run.py](pipeline/importers/laudus_run.py)** — `run_import` (341-439). Único archivo con cambio de lógica. `append_import_log` (197-202) y `git_commit_push` (208+, hace fetch+rebase antes del push) no cambian.
- **Ningún cambio** en `backend/app/api/v1/sync/service.py` (el lector ya está bien) ni en `ReportesPage.tsx`/`useSyncStatus` (mostrarán la fecha solos).

### Por qué el rebase revierte hoy y por qué el fix lo arregla

`git_commit_push` hace `fetch origin main` + `rebase` antes de pushear (para no chocar con el cron/backend que también escriben). Un cambio **working-tree no commiteado** (la entrada de import-log de hoy) se pierde en ese rebase. Al **commitear** el import-log dentro del mismo commit, deja de ser working-tree → el rebase lo preserva y el push lo sube. Origin pasa a ser la fuente única y el lector (que corre sobre el mismo checkout) ve la fecha real.

### Testing standards

- `pytest`, patrón de `test_sync.py` (fetch fake en memoria). Repo git temporal por fixture; correr con `PYTHONUTF8=1` (gotcha Windows). Los 2 rojos `test_fava_edit_validator` que a veces aparecen son PRE-EXISTENTES — no atribuírselos a esta story.

### References

- [Source: pipeline/importers/laudus_run.py:418-428 + 392-396] — el path de éxito y el no-op de `run_import`.
- [Source: backend/app/api/v1/sync/service.py:25-58] — `_read_import_log_last_sync` (lector, sin cambio).
- [Source: frontend/src/pages/ReportesPage.tsx:19-21] — render de `"Datos de Laudus al:"` (sin cambio).
- [Source: _bmad-output/implementation-artifacts/deferred-work.md — residual "import-log no se pushea"] — origen conocido del bug.
- [Source: logs Render srv-d7dk4hv41pts73a35aqg 2026-07-09 16:08] — evidencia de que el sync corre y pushea; solo el indicador falla.
