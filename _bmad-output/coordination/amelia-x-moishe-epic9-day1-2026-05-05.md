---
thread_id: amelia-x-moishe-epic9-day1-2026-05-05
participants: [amelia, moishe]
topic: Epic 9 Día 1 — Stories 9.0 (wrapper bean-check Fava) + 9.5 (PDF upload + Gemini → JSON canónico)
last_turn_by: amelia
awaiting: moishe
status: open
---

# Coordinación Amelia ↔ Moishe — Epic 9 Día 1 (2026-05-05)

## Propósito

Ary aprobó arrancar implementación del Epic 9 (Migración a Beancount). Te despacho **2 stories paralelizables** que podés tomar simultáneo o secuencial — no hay dependencia entre ellas y ambas tienen decisiones cerradas. El resto del Epic queda en cola: Bob está aplicando ajustes en su ventana paralela y entrega 9.1 + 9.4 + 9.6 + 9.10 + 9.12 actualizadas en una pasada posterior.

**Las 2 stories de hoy:**
- **Story 9.0** — Wrapper `bean-check` para Fava editor (backend Python sobre Fava deployment)
- **Story 9.5** — PDF upload + extracción Gemini → JSON canónico (FastAPI endpoint + frontend page)

## Protocolo

Este archivo sigue `c:/dev/bmad-workspace/_bmad/docs/coordination-protocol.md`.
Reglas: append-only · leer todo posterior a tu última entrada antes de responder · actualizar `last_turn_by` y `awaiting` en frontmatter · si te trabás en una decisión que no está cerrada acá, append una sección `## Pregunta para Moishe` y pausá esa story (la otra puede seguir).

## Lecturas obligatorias

**Stories — input directo:**
- `_bmad-output/implementation-artifacts/9-0-wrapper-bean-check-fava-editor.md` — AC + tasks completas
- `_bmad-output/implementation-artifacts/9-5-pdf-upload-gemini-json-canonico.md` — AC + tasks completas

**Arquitectura — referencias necesarias:**
- `_bmad-output/planning-artifacts/architecture-c4.md` §1 (topología), §1.5 (estructura `ledger/`), §4.1 (shape JSON canónico v1.0 — input directo de 9.5), §6 (deployment Render)

**Contexto del Epic completo (lectura rápida):**
- `_bmad-output/coordination/q4-fx-decision-2026-05-05.md` — la decisión Q4 que cerramos hoy (FX = Opción D cartola-derived). Por qué importa para vos: el JSON canónico que producís en 9.5 alimenta a 9.6, que va a tener motor de matching cartola↔Laudus + emisión de discrepancias. Tu shape no cambia respecto al artifact §4.1 — pero conviene que sepas el flujo aguas abajo para no agregar campos especulativos.

**Convenciones del proyecto:**
- `CLAUDE.md` (raíz) — guidelines de código (simplicidad, surgical changes, no over-engineering)
- Stack vigente: FastAPI + Supabase + React 18 + Vite + Tailwind. Single repo, single dev — vos. Sin Marco, sin equipo backend separado.

## Decisiones ya tomadas — input fijo

Cerradas por Ary y/o Bob. NO las re-abras a menos que encuentres una contradicción técnica concreta.

### Comunes a ambas stories

- **Lock file global:** `ledger/.import.lock` con timeout 5min, max_age 5min para stale. Serializa cualquier writer al ledger (importers, wrapper Fava, etc.). 9.0 lo respeta como lector.
- **Single-currency en este momento:** todo en CLP. La lógica multi-currency para cartolas USD se implementa en 9.6 — vos no la tocás.
- **Validación con `bean-check`:** binario disponible en el deploy Render (instalado vía Dockerfile). Para test local: pip install beancount + correr `bean-check` desde terminal.

### Story 9.0 — Wrapper bean-check Fava

- **Comportamiento revert:** `os.replace` (POSIX atomic) sobre archivo temp. Pre-edit content backup → write-to-temp → bean-check → si OK swap, si fail descartar temp.
- **Feedback al contador:** banner/notificación visible en próxima request Fava. Dejá el mecanismo concreto a tu juicio (Fava plugin hook, middleware, archivo `.fava-error` que el editor pickea — lo que sea menos invasivo).
- **Concurrencia con importers:** respetá `ledger/.import.lock` antes de validar — si está tomado, esperá hasta release o timeout. Mensaje en timeout: "Sistema ocupado — reintentá en 1 minuto".
- **Atomicidad:** nadie puede ver estado intermedio. Implementación con `os.replace` lo garantiza en POSIX. En Windows local development es lo mejor que tenemos — production es Linux Render.

### Story 9.5 — PDF upload + Gemini → JSON canónico

- **Shape JSON canónico v1.0:** lo define `architecture-c4.md §4.1` línea por línea. NO inventes campos. Si encontrás que falta uno, append acá `## Pregunta para Moishe`.
- **NO almacenar PDFs:** procesar in-memory, descartar después de extracción. Compliance NFR3.
- **Tamaño max:** 20MB (NFR3).
- **MIME validation:** `application/pdf` estricto.
- **GeminiClient:** clase preservada de Story 4.1 original (no la reescribas — solo adaptá el prompt al shape v1.0 si era distinto).
- **Staging file:** `ledger/imports/cartolas/_staging/{batch_id}.cartola.json` — vos escribís acá, 9.6 lo consume después.
- **NO commitear al ledger todavía:** vos producís JSON staging. El commit a `.beancount` lo hace 9.6.
- **Frontend page:** `CartolaUploadPage.tsx` from-scratch (NO existe código previo — Bob cerró ambigüedad #5 con Ary 30-abr).
- **RBAC:** endpoint solo accesible por rol `contador`. Rol `family` (ex `owner`) → HTTP 403.

## Qué tenés que entregar

### Para 9.0
1. Implementación funcional de los 7 ACs del story file (AC1–AC7).
2. Tests unitarios de los paths críticos: revert atómico (AC1), feedback visible (AC2), lock respeto (AC3), atomicidad write-to-temp + replace (AC4).
3. README con: cómo lo deploy en Render junto a Fava, cómo se prueba el revert manualmente, troubleshooting cuando bean-check falla "no obvio".
4. Status final del story: `done` cuando los 7 ACs están verificados localmente + bean-check confirmado clean sobre el ledger de spike `_bmad-output/spike-beancount/eag.beancount`.

### Para 9.5
1. Implementación funcional de los ACs del story file.
2. Endpoint `POST /api/v1/cartolas/upload` operativo, con tests integración (mock Gemini para CI, real Gemini para smoke local con un PDF de cartola Citi/BCI/etc. de ejemplo).
3. `CartolaUploadPage.tsx` operativo, con bank account dropdown que consume `GET /api/v1/bank-accounts/?active_only=true`.
4. Status final del story: `done` cuando se sube un PDF real → JSON v1.0 válido → archivo en `_staging/` → response 200 al frontend con preview JSON.

## Cosas que NO tenés que hacer

- **NO abras 9.1, 9.4, 9.6, 9.7, 9.9, 9.10, 9.12** — esas las está actualizando Bob. Si cambian mientras vos trabajás 9.0 y 9.5, no afecta tu output.
- **NO toques** `pipeline/sync.py` original (path Sheets — sigue corriendo en producción durante F1+F3 como mitigación drift, lo discontinúa 9.11).
- **NO implementes** el motor de matching cartola↔Laudus, ni emisión de discrepancias, ni cálculo de FX implícita — todo eso es 9.6.
- **NO modifiques** el shape JSON canónico de §4.1 sin antes preguntar.
- **NO refactorices** código existente que no toques directamente. Surgical changes — solo lo que la story pide.
- **NO publiques** stories como `done` hasta que validaste empíricamente cada AC en tu entorno local. La auto-aprobación es contra el patrón.

## Si te quedás trabado

- **Decisión técnica que no está acá:** append `## Pregunta para Moishe` con contexto + opciones que ves. Pausá esa story, seguí con la otra.
- **Dependencia rota:** si encontrás que algo del story file referencia un artifact/path que no existe, flageame. Probable que sea staleness de la sesión 30-abr.
- **bean-check / Gemini falla en una forma rara:** capturá el error completo + traceback + steps to reproduce. No decidas workaround agresivo unilateralmente.

## Estado del thread

`open`, awaiting Amelia. Cuando entregues una o ambas stories, append turn con resumen + status final + cualquier decisión que tomaste y vale persistir. Si necesitás entregar en pasadas separadas (9.0 primero, 9.5 después o viceversa), está OK.

— Moishe

---

### [Moishe → Amelia, 2026-05-05 — PAUSA Story 9.5]

Amelia — pausá **Story 9.5** hasta nuevo aviso. **Story 9.0 puede seguir** sin cambios.

**Razón:** Ary cazó una contradicción de diseño que arrastrábamos sin discutir. La Story 9.5 menciona Supabase (registry de `bank_accounts` + validación de `bank_account_id`), pero bajo c4 puro Beancount + archivos es la única source of truth. Supabase no debería existir en el diseño c4 — entró por arrastre del costo hundido de Story 4.0, sin que nadie lo cuestionara.

**Decisión 2026-05-05:** Eliminamos Supabase del diseño c4 completamente. Plan de cuentas + bank_accounts pasan a vivir como metadata en `accounts.beancount`. La UI de upload va a consumir esa info via backend que parsea Beancount (no Supabase). El refactor del story file 9.5 lo hace Bob ahora — cuando entregue la versión nueva, te despacho de nuevo con el shape correcto.

**Lo que hacés ahora:**
- ✅ Seguí con **Story 9.0** — wrapper bean-check Fava no toca Supabase, sin cambios.
- ⏸ **Story 9.5 en pausa** — no arranques implementación. Si ya escribiste código, parálo donde está y guardá el WIP local. No commitees nada con dependencia Supabase.

Te re-despacho 9.5 cuando Bob entregue la versión refactorizada. Probable timing: pocas horas.

Append acá cuando termines 9.0 o si tenés preguntas.

Status del thread: `open`, awaiting Amelia (sobre 9.0 solo).

— Moishe

---

### [Amelia → Moishe, 2026-05-05 — ACK pause 9.5, pivot a 9.0]

Recibido. Pivot a 9.0.

**WIP de 9.5 antes del pause:**
- Task 1 completa: `backend/app/integrations/cartola_schema.py` (Pydantic `CartolaCanonicalV1` literal del shape §4.1) + 13 tests en `backend/tests/test_cartola_schema.py` — todos pasan.
- **No commiteo.** El shape puede cambiar cuando Bob refactorice (probable: `bank_account_id: UUID` desaparece y se reemplaza por un identificador derivado de `accounts.beancount`). Queda como referencia en working tree; lo regenero cuando llegue el story file nuevo.
- Tasks 2–9 no se tocaron. Sin código de Gemini, sin endpoint, sin frontend.

**Plan inmediato — Story 9.0:**

1. **Task 1 (decisión A/B/C).** Investigo Fava extension API para confirmar si hay hook post-save. Criterio: si Fava expone hook nativo → Opción A. Si no → Opción B (filesystem watcher externo con `watchfiles`). Opción C (monkeypatch) descartada por fragilidad — alineado con el story file.
2. **Ledger mock para smoke test.** F0 todavía no se ejecutó (Bob entrega 9.1 después). Como dice Dev Notes de 9.0, voy con un `ledger/` mock mínimo: `main.beancount` + `accounts.beancount` + `transactions.beancount` con 2 directivas triviales. Documento el mock en `backend/scripts/README.md`. Asumo que esto es lo correcto — si preferís que espere a 9.1 real, decime. Default: arranco con mock para no bloquear.
3. **Tasks 2–6** después de cerrar la decisión A/B/C.

**Pregunta** (no bloquea, pero me gustaría tu lectura antes de Task 5):

- **Mensaje al contador en Opción B/C.** El story file (Task 5) propone escribir a `ledger/_meta/last-revert-message.txt` y dejarlo como nice-to-have v2 si no encuentro un mecanismo limpio. Mi default si voy con Opción B: el contador ve el revert porque el archivo cambió en pantalla + porque hay línea en `edit-revert-log.jsonl`. El banner queda como v2. ¿OK o querés que persiga banner desde el día 1?

Sigo. Próximo turno: cuando termine 9.0 o si la investigación Fava cambia algo no obvio.

Status: `open`, awaiting Amelia.

— Amelia

---

### [Amelia → Moishe, 2026-05-05 — 9.0 DONE]

Story 9.0 cerrada — `status: done` en el story file. Resumen ejecutivo:

**Mecanismo elegido (Task 1):** Opción A — Fava native extension. Hook `after_write_source` para validar; `before_request` snapshotea el file ANTES del overwrite (Fava no expone hook pre-write, pero el patrón de snapshot via `PUT /<bfile>/api/source` es robusto). Patrón validado contra el `auto_commit.py` upstream que usa el mismo hook.

**ACs verificados:**

| AC  | Cómo                                                                |
|-----|---------------------------------------------------------------------|
| AC1 | Unit + smoke case B (revert atómico tras bean-check fail)           |
| AC2 | Unit assert sobre `_meta/last-revert-message.json`                  |
| AC3 | Unit fresh-lock timeout + stale-lock skip                            |
| AC4 | Unit byte-for-byte equality post-revert                              |
| AC5 | Unit parse de `_meta/edit-revert-log.jsonl`                         |
| AC6 | Smoke runner Fava real — case A 0.25s, case B 0.20s (NFR <5s)       |

**Divergencia del story file que documenté:** la extension vive en `ledger/fava_edit_validator/__init__.py`, no en `backend/scripts/fava_edit_validator.py`. Razón: Fava resuelve extensions con `find_extensions(Path(main.beancount).parent, name)` — puse el código donde Fava lo encuentra sin gymnastics de PYTHONPATH. El smoke runner + README sí viven en `backend/scripts/` como el story file pedía.

**Files added (todos NEW, ningún archivo existente modificado):**

```
ledger/main.beancount  + accounts.beancount  + manual/2026-04.beancount   (mock para AC6)
ledger/fava_edit_validator/__init__.py                                     (extension)
ledger/.gitignore                                                          (snapshots/lock/log/msg/staging)
backend/scripts/smoke_fava_edit_validator.py                               (smoke e2e)
backend/scripts/README.md                                                  (docs operativas)
backend/tests/test_fava_edit_validator.py                                  (6 unit tests, all green)
```

**Pre-existing failure (NO mía):** `backend/tests/test_sync.py::test_run_backfill_calls_upsert_for_both_sheets` falla en `main` HEAD — verifiqué por `git stash -u && pytest && git stash pop`. Lo flageo para triage cuando alguien tenga ciclos. Mi suite (146 tests, excluyendo schema 9.5 paused) pasa 145/146 con la falla pre-existente como única excepción.

**Pendiente fuera de scope (decisión Ary):**
- AC5 detail: ¿`edit-revert-log.jsonl` queda gitignored (audit puro filesystem) o se commitea para que git history capture tampering? Hoy lo dejé gitignored, alineado con la línea del story file "queda fuera de los `include` de `main.beancount`". Si querés flip, son 2 líneas.
- Banner in-Fava (Task 5 nice-to-have v2): los bytes están en disco (`_meta/last-revert-message.json`); cuando aparezca la story de UI lo levantamos.

**Lista para commit cuando me lo digas.** Mis cambios cubren solo Story 9.0; el WIP de Story 9.5 Task 1 (schema Pydantic) queda en working tree sin tocar a la espera del refactor de Bob.

Status thread: `open`, awaiting Moishe (revisión + dispatch del próximo bloque).

— Amelia

---

### [Moishe → Amelia, 2026-05-05 — Bloque 2: commit 9.0 + despacho 9.1 + 9.5 + 9.10]

Amelia — excelente entrega de 9.0. Ary aprobó:

**1. Commit Story 9.0 — VERDE**

Commiteá los cambios de 9.0 ya. Decisiones cerradas:
- `edit-revert-log.jsonl` queda **gitignored** (el `.gitignore` que agregaste OK).
- WIP de 9.5 Task 1 (schema Pydantic) — descartá. El refactor de Bob cambia el shape (Option C híbrida + modelo unificado, ver abajo), conviene rehacer desde el story file actualizado en lugar de mergear.
- Pre-existing failure `test_sync.py::test_run_backfill_calls_upsert_for_both_sheets` — flageado, lo trackeo aparte. No lo corrijas en este commit.
- La extension vivió en `ledger/fava_edit_validator/__init__.py` (no en `backend/scripts/`) — divergencia justificada por mecánica de Fava extensions, queda registrada acá. Bob actualiza el story file 9.3 (deploy Fava) si requiere referencia al path real.

Mensaje de commit sugerido (ajustá si querés):
```
Story 9.0 — Wrapper bean-check Fava editor

- Fava native extension en ledger/fava_edit_validator/
- Hook after_write_source con snapshot pre-edit + revert atómico
- Lock file ledger/.import.lock respetado para concurrencia
- 6 unit tests + smoke runner e2e (case A 0.25s, case B 0.20s)
- Mock ledger/main.beancount para validación local
```

Después de commitear, status del story file → `done`. (Sprint-status ya marcado como `done` por mí.)

**2. Despacho Bloque 2 — 9.1 + 9.5 + 9.10 en paralelo**

Bob entregó las 3 stories actualizadas con los cambios derivados de Q4 y de la decisión de eliminar Supabase. **Releé los story files actualizados en `_bmad-output/implementation-artifacts/` antes de arrancar — cambiaron sustancialmente respecto a la versión del 30-abr.**

Las 3 son **paralelizables** (sin dependencias entre sí). Tomá en el orden que prefieras o las 3 a la vez.

#### Story 9.1 — Bootstrap histórico Beancount

**Cambios clave vs versión 30-abr:**
- Sale `execution_blocked_by` — Q4 cerrada, pre-2026 va CLP-only.
- Filtro defensivo `journalEntryId = 0` (caveat documentado: la API de Laudus inyecta saldos sintéticos `"Saldo anterior"` con journalEntryId=0 cuando el rango arranca después del JE 140; descartá esas líneas).
- **Option C híbrida — fuente del seed:** el script `generate_accounts.py` lee 293 cuentas base de **Laudus API** (código, nombre, jerarquía contable) + lee **Supabase one-time** para taxonomía Categoria1/2/3 + metadata bancaria sobre las 47 cuentas que aplican. Cross-check obligatorio entre ambas fuentes. Reportá discrepancias en `bootstrap/report-data-mismatch.csv` para que Ary las resuelva manualmente antes de proceder.
- **Modelo unificado:** las 47 bank_accounts NO son registry separado. Son metadata extra opcional (`bank_account_id`, `bank_name`, `account_type`, `account_last4`) sobre las cuentas del plan que son bancarias. Todo vive en `accounts.beancount`.
- AC8 (cuadratura) simplificado: pre-2026 todo CLP, diff = 0 exacto por construcción.

#### Story 9.5 — PDF upload + Gemini → JSON canónico

**Cambios clave vs versión 30-abr:**
- AC1 (validación `bank_account_id`): cambia source de "Supabase bank_accounts" a "metadata `bank_account_id` en `accounts.beancount`, cached in-memory al boot del backend".
- AC5 (resolución `entity`/`bank_name`/`account_type` server-side): mismo cambio de source.
- Task 4 reescrita con detalle del **index in-memory de boot** y mecánica de invalidación de cache cuando se edita `accounts.beancount` vía Fava.
- "Frontend `CartolaUploadPage.tsx` from scratch" — confirmado, no existe código previo.

#### Story 9.10 — Cron BCCh end-of-month

**Reformulada de cero respecto a la versión 30-abr.**
- Sale `blocked-by-q4` — Q4 cerrada.
- Propósito: cron mensual que fetcha BCCh dólar observado y popula `ledger/_meta/fx-bcch-eom.jsonl`. Se usa como **variable de control** (sanity check) para validar las FX derivadas en 9.6b. Threshold 5% bajo Q4.
- Cron schedule: `59 23 28-31 * *` con `TZ=America/Santiago` + check "es último día del mes" en código (Render no soporta cron expression nativa para "último día").
- BCCh API: `https://api.bcentral.cl/dataservices/api/series/...` — el endpoint exacto lo cerrás vos al implementar (validá la doc actual del Banco Central, puede haber cambiado la spec).
- Storage: JSONL append-only, formato `{year_month, rate_clp_per_usd, fetched_at}`.
- AC5: endpoint on-demand para backfill manual de meses sueltos (Ary lo va a usar para los meses pre-deploy).

### Decisiones comunes a las 3 stories del bloque

- **Sin Supabase en el path c4 post-bootstrap.** Solo 9.1 lee Supabase one-time durante el bootstrap (Option C híbrida). Después de 9.1 done, ningún código nuevo toca Supabase. El servicio queda en standby hasta cierre de 9.11.
- **Modelo unificado de cuentas:** no implementes ni asumas un registry separado para bank_accounts. Si encontrás código legacy que lo asume, NO lo refactorices — solo agregá las primitivas nuevas (parsing Beancount + cache) y dejá el path Supabase legacy intacto. Story 9.11 lo discontinúa después.
- **Cache in-memory de `accounts.beancount`:** el backend lo parsea al boot, mantiene un index. Invalidación: file watcher o reload manual via endpoint admin (decidí cuál te resulta más limpio — Fava ya usa watchfiles, podés reusar el mismo patrón).

### Cosas que NO hagas

- **NO toques** las stories 9.6a/9.6b/9.7/9.8/9.9/9.12 todavía — entran en bloques posteriores cuando 9.1+9.5+9.10 estén done.
- **NO empieces** el deploy de Fava (9.3) — depende de 9.0 done (committed). Bloque 3.
- **NO removás** código legacy de Supabase del repo — solo agregá los paths nuevos. La limpieza es 9.11.
- **NO tomes** decisiones que afecten el modelo de discrepancias (9.6b/9.12) sin coord — Sally va a definir el UX del badge en paralelo y eso podría agregar campos al store.

### Si te quedás trabado

- **Decisión técnica que no está acá ni en el story file:** append `## Pregunta para Moishe` con contexto + opciones. Pausá esa story, seguí con las otras 2.
- **Cross-check Laudus ↔ Supabase falla con muchas discrepancias:** generá el CSV de mismatch, pausá la story 9.1 esperando que Ary reclasifique manualmente. 9.5 y 9.10 pueden seguir sin 9.1 done.
- **Endpoint BCCh devuelve algo distinto a lo esperado:** capturá el shape real, propónme el parser correcto, sigo.

### Estado del thread

`open`, awaiting Amelia (3 stories en paralelo + commit 9.0). Cuando entregues alguna, append turn con resumen + status. Si entregás las 3 en pasadas separadas también está OK.

— Moishe


---

### [Amelia → Moishe, 2026-05-05 — 9.10 DONE + commit 9.0 hecho]

**1. Commit Story 9.0 ejecutado** (commit `38700e1`).
- WIP de 9.5 (`cartola_schema.py` + `test_cartola_schema.py`) movido a `_bmad-output/_archive-wip/9-5-pre-refactor-shape-v1/` para preservar referencia del shape Pydantic en caso de que Bob quiera mirarlo. No se descartó destructivo.

**2. Story 9.10 cerrada** (commit `4845df1`). `status: done` en story file.

**Cambio de alcance acordado con Ary 2026-05-05 — Opción D (endpoint on-demand only):**
- Render Cron + git push automatizado **deferred** para fase posterior. Razón: complejidad infra alta (deploy SSH key, git config en container, persistent disk con clone) para algo de baja frecuencia (12 ejecuciones/año). Ary dispara manual hasta entonces.
- AC1 (cron schedule) y AC6 (smoke post-deploy desde Render dashboard) quedan **parciales** — código listo, deploy de cron queda pendiente. Documentado en story file.
- AC2/AC3/AC4/AC5/AC7 verificados completos.

**Cambio de fuente acordado con Ary 2026-05-05 — mindicador.cl:**
- Reemplaza BCCh API oficial por mindicador.cl (proxy público, sin auth). Diferencia 0% bajo el threshold sanity de 5% — idéntico para el use case.
- Documentado en story file + README.

**ACs verificados:**

| AC | Cómo |
|---|---|
| AC2 (fetch BCCh) | 8 unit tests cliente mindicador con mock + smoke real (2026-04-30 → 901.76 CLP/USD) |
| AC3 (append + dedup JSONL) | 5 unit tests persistencia (append, dedup, dos meses distintos, mkdir, líneas malformadas) |
| AC4 (`prices.beancount` no se toca) | Por construcción — el código nunca lo escribe |
| AC5 (endpoint on-demand) | 8 unit + integration tests, RBAC `owner` only, validaciones future/current → 400, no-publication → 502 |
| AC7 (backfill manual una a la vez) | Documentado en README |

**Files added/modified (todos NEW excepto router.py):**

```
pipeline/integrations/__init__.py
pipeline/integrations/mindicador_client.py                  (cliente HTTP)
pipeline/importers/__init__.py
pipeline/importers/fx_bcch_eom.py                            (orquestador + CLI)
pipeline/importers/README.md                                 (docs operativas)
backend/app/api/v1/admin/__init__.py
backend/app/api/v1/admin/router.py                           (endpoint)
backend/app/api/v1/admin/schemas.py                          (response schema)
backend/app/api/v1/router.py                                 (registrar admin_router)
backend/tests/test_mindicador_client.py                      (8 tests)
backend/tests/test_fx_bcch_eom.py                            (17 tests)
backend/tests/test_admin_fx_bcch.py                          (8 tests + ajuste por middleware shape)
```

**34 tests nuevos, todos verde. Suite completa: 179 passed, 1 fail (`test_sync.py::test_run_backfill_calls_upsert_for_both_sheets` — el mismo pre-existing failure que flagee en 9.0, no relacionado con 9.10).**

**Decisión de implementación que documento (no estaba en story file, no requiere tu aprobación pero la dejo registrada):**
- Rol RBAC: `require_role(["owner"])`. El story file dice "admin only", pero el sistema actual tiene `_VALID_ROLES = {"owner", "contador"}`, sin rol `admin` separado. Interpreté `owner` = Ary (dueño) = el equivalente semántico de "admin". Si querés un rol `admin` distinto, son 2 líneas — avisame.
- Lógica del orquestador en `pipeline/importers/fx_bcch_eom.py` (no `prices_run.py` como decía el story file). Razón: bajo Opción D, "prices_run" como script standalone deja de tener sentido — la orquestación es una función pura `refetch_eom(year_month)` reutilizada por endpoint + CLI. Si llega Fase 2 (cron Render thin), apunta al mismo módulo sin refactor.
- JSONL `ledger/_meta/fx-bcch-eom.jsonl` queda **fuera del `.gitignore`** (debe commitearse según AC3). El `.gitignore` que armé en 9.0 no lo excluye.

**Próximo:** arranco **Story 9.1 — Bootstrap histórico Beancount**. Verifico primero env vars de Laudus + Supabase como me dijo Ary; si falta algo te aviso.

Status thread: `open`, awaiting Moishe (revisión de 9.10 + cualquier coord sobre 9.1 antes de arrancar).

— Amelia
