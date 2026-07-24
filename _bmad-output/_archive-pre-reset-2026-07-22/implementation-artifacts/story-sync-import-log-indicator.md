# Story: Indicador "Datos de Laudus al:" muestra fecha real (pushear el import-log)

Status: done

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

- [x] **Task 1 — Reordenar + extender el commit del path de éxito** (AC1, AC4)
  - [x] En [laudus_run.py:418-428](pipeline/importers/laudus_run.py#L418): mover `append_import_log(meta_dir, result)` **antes** de `git_commit_push`, y agregar `"ledger/_meta/import-log.jsonl"` a la lista de paths. Dejar `git_commit_sha=null` en el registro (chicken-egg, aceptable).
  - [x] Guard destapado por el fix: el `except Exception` ahora resetea `result["success"] = False` — al setear `success=True` antes del commit, un fallo de push habría reportado éxito silencioso (lo cachó el test pre-existente `test_run_import_marks_failure_when_push_fails`).
- [x] **Task 2 — Commitear el import-log en el path no-op** (AC3, default recomendado)
  - [x] En [laudus_run.py:392-396](pipeline/importers/laudus_run.py#L392): tras `append_import_log`, llamar `git_commit_push(root, ["ledger/_meta/import-log.jsonl"], f"[importer-laudus] check {to_date}: sin cambios")` antes del `return`. Se eligió el default (commitear no-ops).
- [x] **Task 3 — Tests** (AC5)
  - [x] `test_import_log_commiteado_en_sync_con_cambios` (repo git temporal + remote bare seedeado): `run_import` con `fetch_fn` que devuelve 1 JE → verifica `ledger/_meta/import-log.jsonl` en `git diff-tree HEAD` (sobrevive el fetch+rebase) + entrada `success=true` en `HEAD:...import-log.jsonl` + los paths de datos siguen en el commit (AC4).
  - [x] `test_import_log_commiteado_en_sync_noop`: path no-op (backfill `from_date=2099`) → commit de SOLO el import-log con mensaje "sin cambios", sin fetch.
  - [x] Helpers `_seed_repo_with_remote` / `_head_files` reusan el patrón git de los tests existentes de `test_laudus_run.py`.

### Review Findings

_Code review 2026-07-09 (Blind Hunter + Edge Case Hunter + Acceptance Auditor — las 3 capas convergieron en el mismo hallazgo; verificado contra el lector `sync/service.py:33-57`)._

- [x] **[Review][Patch aplicado] El reorden introducía una regresión: un fallo de push dejaba una línea `success:true` que el indicador leía como sync fresco** [pipeline/importers/laudus_run.py:436](pipeline/importers/laudus_run.py#L436) — **RESUELTO (opción 1):** el `except` ahora, si ya se appendeó una línea `success=True` (`success_logged`), la REESCRIBE como `success=False` vía `_rewrite_last_import_log` en vez de appendear una segunda contradictoria. El working-tree (lo que lee el indicador) queda sin la línea fantasma. Test de regresión `test_push_fallido_no_deja_linea_success_fantasma`. Suite verde (28 laudus + 82 sync/import-log).
  Con el append **antes** del commit, en el path de éxito: `append_import_log` escribe la línea `success:true` (timestamp T) → `git_commit_push` hace `commit` local (con esa línea) y luego `push`; si el **push/rebase falla** (deploy key sin permiso, non-fast-forward, red), lanza → el `except` setea `result["success"]=False` y appendea una **segunda** línea `success:false` (mismo timestamp T). El lector `_read_import_log_last_sync` recorre TODO el working-tree, ignora la línea `success:false` y toma el **max timestamp de las success truthy** → devuelve T → el indicador "Datos de Laudus al:" muestra fecha **fresca** aunque a origin **no llegó nada**. El guard `success=False` solo corrige el `result` en memoria (job status), NO la línea ya escrita que lee el indicador. Durante una caída sostenida de push, cada corrida re-appendea una línea fresca `success:true` (tras el `reset --hard` del `refresh_clone`) → el indicador queda perpetuamente "fresco" con origin congelado. **Es exactamente el "parece OK pero está roto" que la story quería matar, invertido.** Antes del cambio (append DESPUÉS de un push exitoso) un push fallido solo dejaba `success:false`, así que es una regresión nueva. `test_run_import_marks_failure_when_push_fails` no lo caza (solo assert sobre `result["success"]`, nunca inspecciona el log commiteado). Consecuencia secundaria misma causa: el path no-op, antes infalible, ahora marca el job como `failed` ante cualquier hiccup transitorio de git.
  **Requiere decisión de diseño** (ver opciones en la conversación): (A) en el `except`, reescribir/truncar la línea `success:true` pendiente en vez de appendear una segunda; (B) mover el append de la línea `success` a DESPUÉS del push confirmado y commitearla en un segundo commit (rompe "una sola commit"); (C) que el lector confíe solo en origin, no en working-tree; (D) aceptar y documentar el riesgo.

- [x] **[Review][Dismiss] Un commit "sin cambios" por cada sync no-op + crecimiento del historial** — por diseño (AC3: el indicador refleja el último chequeo). Sin acción; nota de visibilidad: la garantía de "syncs idempotentes silenciosos" desaparece (el append siempre stagea el log).

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

## Dev Agent Record

### Implementation Plan

1. Path de éxito ([laudus_run.py](pipeline/importers/laudus_run.py) `run_import`, ~418-437): `result["success"] = True` → `append_import_log` → `git_commit_push` con los 3 paths (datos + pending + `ledger/_meta/import-log.jsonl`). El log entra en el MISMO commit → sobrevive el `fetch+rebase` interno del push.
2. Path no-op (~392-401): tras `append_import_log`, `git_commit_push(["ledger/_meta/import-log.jsonl"], "…check {to_date}: sin cambios")`.
3. Guard en `except Exception`: revertir `result["success"] = False` (necesario porque ahora `success` se setea antes del commit).

### Completion Notes

- **Núcleo (AC1/AC2/AC4):** en el path de éxito, el import-log se appendea ANTES de `git_commit_push` y su ruta se suma a los paths commiteados. La entrada queda dentro del commit y el `fetch+rebase` ya no la revierte → origin avanza → `_read_import_log_last_sync` (sin cambios) empieza a devolver la fecha real. Los paths de datos (`imports/laudus/`, `_new-accounts-pending.beancount`) siguen commiteando igual; el mensaje de commit no cambia. `git_commit_sha` queda `null` en la línea del log (chicken-egg, aceptable — el lector no lo usa).
- **No-op (AC3, default recomendado):** un sync sin movimientos nuevos igual commitea/pushea un commit de solo el import-log ("…check {date}: sin cambios") → el indicador refleja el último chequeo de Laudus.
- **Guard anti silent-success:** al mover `success=True` antes del commit, un fallo de push habría reportado éxito. El `except Exception` ahora resetea `success=False`. Lo cachó el test pre-existente `test_run_import_marks_failure_when_push_fails` (rojo → verde con el guard). Consecuencia benigna: en un push fallido, el commit local (con la línea `success=True`) y las líneas working-tree las limpia el `refresh_clone` (reset --hard origin/main) del próximo run.
- **Sin cambios** en `sync/service.py` (lector) ni frontend, como preveía la story.
- **Verificación:** `test_laudus_run.py` 27/27; suite completa `backend/tests pipeline` = **731 passed / 1 xfailed / 0 failed**, sin regresiones nuevas (los 2 rojos `test_fava_edit_validator` pre-existentes no aparecieron en esta corrida).

### File List

- `pipeline/importers/laudus_run.py` — modificado (`run_import`: reorden del append + path extra en el commit de éxito; `git_commit_push` en el path no-op; `except` resetea `success=False`).
- `backend/tests/test_laudus_run.py` — modificado (2 tests nuevos + helpers `_seed_repo_with_remote`/`_head_files`).

## Change Log

- 2026-07-09 — Dev (Amelia): implementada la story. Import-log commiteado dentro del commit de datos (path de éxito) + commit propio en el path no-op → el indicador "Datos de Laudus al:" muestra la fecha real. Guard `success=False` en el except (anti silent-success al push fallido). 2 tests nuevos; suite 731 passed/1 xfailed, 0 regresiones. Status → review.
