# Story 6.7: Batch-resolve de discrepancias de reconciliación (un `bean-check` + un commit para N diferencias) + cierre de los 2 defers de atomicidad de 6.3

Status: done  <!-- 2026-07-08 review adversarial 3 capas → DONE: 0 bloqueantes, 4 patches (G1/dedup-single/G2/G6), 4 defers (G3/G4/G5/G7 → deferred-work). Suite 712/1 xfailed, tsc+vitest verdes. SIN COMMIT. -->

<!-- DECISIONES CERRADAS 2026-07-08 (Ary delegó las 5 por ser técnicas → defaults del orquestador):
     1. Tope N por batch = 50 (rechaza 422 si se excede).
     2. Batch MIXTO (confirm-cartola-only + acciones baratas, todo-o-nada).
     3. Justificación = UNA COMÚN para todo el batch (menos fricción al cerrar el mes; el audit trail
        registra la misma justificación en cada resolución del batch). NO por-item.
     4. NO commitear el JSONL de resoluciones (apoyarse en el dedup por ref_discrepancy_id; surgical).
     5. NO migrar el path single al motor batch (single intacto = anti-regresión pura, AC7).
     Epic tag = epic-6-tail (reabre Epic 6 como cola de hardening; no cerrar el epic de nuevo hasta la
     retro-adenda ya anotada en deferred-work). -->


<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

<!-- EPIC TAG — DECISIÓN DE ARY: Epic 6 (Reconciliación Mensual) está marcado `done`. Esta story lo
     REABRE como cola de hardening (performance + atomicidad), NO como feature nueva. Es la contracara
     de 6.3 (que dejó los 2 defers de atomicidad que acá se cierran) y de 6.4/6.6 (el dashboard que acá
     gana multiselect). Ary: etiquetar como `epic-6-tail` / hardening, o abrir un "Epic 6.b — robustez
     de reconciliación". Sin cerrar el epic de nuevo hasta la retro-adenda ya anotada en deferred-work
     (tramo 06-26→07-06 sin retro). -->

## Story

As a **contador del family office**,
I want **aprobar varias diferencias de reconciliación de una sola vez desde el dashboard (seleccionando N líneas y resolviéndolas en un solo click), con la garantía de que la operación es todo-o-nada**,
so that **cerrar el mes no me cueste N requests de 30-120s serializados (hoy cada aprobación corre su propio `bean-check` del ledger completo + su propio `git push` por la red), y para que un fallo de red a mitad de camino nunca deje una diferencia "resuelta" sin su asiento en el ledger — ni un asiento en el ledger sin cerrar su diferencia (el doble-conteo silencioso que 10.2 tapó)**.

> **Continuación de 6.3.** 6.3 entregó `annotate_discrepancy` (aprobar un `missing-in-laudus` → escribe la tx a `manual/`) pero lo hace **de a uno**: cada `confirm-cartola-only` corre `commit_reconciliation` = 1 `bean_check(main.beancount)` (parseo del ledger COMPLETO) + 1 `git_commit_push` (fetch+rebase+push por la red) bajo `.import.lock`. Resolver 20 diferencias = 20 parseos + 20 pushes serializados. Esta story: **un endpoint batch que resuelve N con UN `bean_check` + UN commit+push**, y de paso cierra los **2 defers de atomicidad** que 6.3 dejó anotados en `deferred-work.md`.

## Contexto — por qué esta story (y por qué ahora)

El review de 6.3 (2026-06-24) dejó dos defects reales, ambos en el boundary write/git de la anotación, ambos de clase *silent-loss*:

1. **Commit parcial (doble-conteo en retry).** `commit_reconciliation` ([reconcile.py:192](../../pipeline/importers/reconcile.py#L192)) escribe el archivo `manual/`, corre `bean_check` verde, y **recién entonces** hace `git_commit_push` ([reconcile.py:221](../../pipeline/importers/reconcile.py#L221)) **sin try/except**. Si el push lanza (deploy-key rechazada, red caída), la excepción escapa con el archivo YA escrito (el rollback de `commit_reconciliation` solo cubre `bean-check` rojo, [reconcile.py:213-219](../../pipeline/importers/reconcile.py#L213)), la discrepancia queda abierta (no se appendeó resolución), el caller recibe 500 — y un **retry pasa el guard `_resolved_ids`** ([service.py:202](../../backend/app/api/v1/reconciliation/service.py#L202)) porque no hubo resolución, y **appendea una SEGUNDA copia de la tx** → gasto duplicado. (deferred-work.md "6-3" defer #1.)

2. **Lost-update RMW fuera del lock.** `annotate_discrepancy` hace `existing = out_file.read_text()` y concatena **ANTES** de llamar a `commit_reconciliation` ([reconcile.py:322](../../pipeline/importers/reconcile.py#L322)), que es quien toma el lock ([reconcile.py:209](../../pipeline/importers/reconcile.py#L209)). Dos `confirm-cartola-only` concurrentes sobre la misma cuenta+mes leen el mismo `existing` y el 2º write pisa la entry del 1º (last-writer-wins; una entry perdida, `bean-check` pasa igual). (deferred-work.md "6-3" defer #2.)

> **Nota de line-drift:** deferred-work.md cita `reconcile.py:196-211` (defer #1) y `reconcile.py:269` (defer #2); el código se corrió desde 6.3 → los puntos reales HOY son `git_commit_push` en **221** y el `read_text` en **322**. Verificado leyendo el archivo para esta story.

El batch resuelve los dos de raíz: un solo write por archivo **dentro** del lock (mata #2) y un rollback de **todos** los archivos si el push falla, con la resolución appendeada **solo** tras el push exitoso (mata #1).

## Alcance / decisiones de diseño

### Qué acciones entran en un batch

Bajo modelo A, la **única** acción que ESCRIBE al ledger es `confirm-cartola-only` sobre un `missing-in-laudus` (append de una tx nueva a `manual/`). Las demás acciones de cierre (`confirm-laudus-only`, `accept-laudus*`, `escalate`, etc.) **solo appendean al JSONL** (`append_resolution`) y ya son baratas — no tocan git ni `bean-check`.

**Decisión (default): el batch acepta acciones MIXTAS.** Un batch puede contener M `confirm-cartola-only` (que anotan) + K acciones baratas (que solo cierran). Las anotaciones se acumulan en UN `bean_check` + UN commit; las baratas se appendean en el mismo batch, gateadas por el mismo éxito todo-o-nada. Motivo: el contador cierra el mes seleccionando *todo lo pendiente* de una cuenta, no filtrando por tipo de acción. (Ary: ver Pregunta 2 — alternativa = batch solo-`confirm-cartola-only`, más simple pero obliga al contador a dos pasadas.)

### Atomicidad todo-o-nada (el corazón de la story)

El batch es **una unidad transaccional**. Secuencia, toda dentro de UN `acquire_lock`:

```
1. PREFLIGHT (sin escribir nada):
   por cada id del batch → cargar el original, correr los MISMOS guards que resolve() hoy:
     - existe (ResolveError si no)
     - no está ya resuelta (_resolved_ids, AC6 de 6.3)
     - acción válida para el estado (ACTIONS_BY_STATE)
     - justificación ≥10 (salvo escalate)
     - si confirm-cartola-only: datos de cartola presentes + cuenta resoluble + (USD) FX>0
   Si CUALQUIER id falla el preflight → 400/422 con el detalle del id culpable, y NADA se escribe.
2. RENDER: por cada confirm-cartola-only → construir la Transaction (reusa la lógica de
   annotate_discrepancy: _build_postings/build_usd_postings, meta source=reconciliation,
   ref_discrepancy_id, category_status). AGRUPAR por archivo destino
   manual/reconciliation-<leaf>-<YYYY-MM>.beancount.
3. IDEMPOTENCIA: por cada entry, si su ref_discrepancy_id YA aparece en el archivo destino
   (o en el contenido acumulado), NO la re-appendea (dedup → un retry no duplica).
4. WRITE (dentro del lock): por cada archivo agrupado, leer existing UNA vez, concatenar TODAS
   sus entries, escribir UNA vez. Snapshot del contenido previo de cada archivo (para rollback).
5. bean_check(main.beancount) UNA sola vez.
   - rojo → restaurar TODOS los archivos a su snapshot, 422, NINGUNA resolución appendeada.
6. git_commit_push(root, [todos los paths manual/], mensaje batch) UNA sola vez.
   - lanza/falla → restaurar TODOS los archivos a su snapshot, 5xx/422, NINGUNA resolución.
7. Solo si push OK → append_resolution de TODAS las discrepancias del batch (anotadas + baratas).
```

**Invariante:** al terminar, o (a) las N discrepancias están cerradas Y sus tx están en el ledger commiteadas, o (b) ninguna lo está y los archivos `manual/` quedan bit-idénticos a como estaban. Nunca un estado intermedio observable por un retry.

> **Ventana residual (crash entre push y append):** si el proceso muere DESPUÉS del push exitoso pero ANTES de appendear las resoluciones, las tx quedan commiteadas y las discrepancias abiertas. El **dedup por `ref_discrepancy_id`** (paso 3) hace que el retry NO duplique la tx: re-renderiza, ve el ref ya en el archivo, la salta, y solo appendea la resolución faltante. Ese dedup es lo que convierte "commit+resolution atómico" en "idempotente ante retry" — la opción que la propia deferred-work.md nombra como fix durable.

### Persistencia del JSONL de resoluciones (pregunta abierta, ver Pregunta 4)

El path single de 6.3 **NO commitea** el JSONL de discrepancias tras `append_resolution` — la línea de resolución queda escrita en disco pero un `git reset --hard` del refresh del backend la perdería (reabriendo la discrepancia). Hoy eso lo salva de duplicar el gasto **solo** si existe el dedup por `ref_discrepancy_id` (que esta story agrega). Decisión para Ary: ¿el batch **también commitea** el JSONL junto a los archivos `manual/` (durabilidad completa), o se apoya en el dedup y deja el commit del JSONL para otra story? El default de esta story = **apoyarse en el dedup** (surgical: cierra los 2 defers nombrados sin abrir el tema del ciclo de vida del JSONL), pero se anota como riesgo.

### Tope de N por batch (ver Pregunta 1)

Un batch de 500 ids haría un `render` grande pero **igual un solo** `bean_check`/push — el costo no escala con N como hoy. Aun así conviene un tope defensivo (payload, tiempo de render, tamaño del commit). Default propuesto: **50** por request (el contador rara vez cierra >50 diferencias de una cuenta/mes). Configurable/ajustable; rechazar con 422 si se excede.

### Fuera de scope (explícito)

- **Editar asientos Laudus existentes** (`value-mismatch`/`accept-cartola`, soft-mismatch). Sigue diferido (6.3 lo excluyó; sin cambio).
- **Refactorizar `commit_reconciliation` para el path single.** El endpoint single (`POST .../{id}/resolve`) sigue existiendo y sin cambios de comportamiento (anti-regresión, AC7). Los 2 defers se cierran en el **path batch**; el single queda como estaba (si Ary quiere migrarlo al motor batch-de-1, es una decisión aparte — ver Pregunta 5).
- **Multiselect de acciones que requieren input distinto por item** más allá de `category_account` (que ya es por-item). Justificación: ver Pregunta 3.
- **Commit del JSONL de resoluciones** (salvo que Ary lo suba a scope en la Pregunta 4).

## Acceptance Criteria

**AC1 — Endpoint batch resuelve N con UN `bean_check` + UN commit.**
Given un set de N discrepancias abiertas (mezcla de `confirm-cartola-only` y acciones baratas),
When el contador llama `POST /api/v1/reconciliation/discrepancies/resolve-batch` con una lista de `{discrepancy_id, action, justification, category_account?}`,
Then el sistema corre **exactamente un** `bean_check(main.beancount)` y **exactamente un** `git_commit_push` para TODAS las anotaciones del batch (verificable con spies/contadores de llamadas: `bean_check` y `git_commit_push` invocados ≤1 vez cada uno, no N veces), escribe cada archivo `manual/` afectado **una sola vez**, y devuelve un `BatchResolveResponse` con el resultado por-id + el `git_commit_sha` único.

**AC2 — Atomicidad todo-o-nada: `bean-check` rojo → cero efecto.**
Given un batch cuyo render produce un ledger que NO pasa `bean_check` (p.ej. una categoría destino inexistente),
Then TODOS los archivos `manual/` escritos se restauran a su contenido previo (bit-idéntico), NINGUNA resolución se appendea al JSONL, TODAS las discrepancias siguen abiertas, y el endpoint responde 422 con el detalle. Verificable: tras el fallo, `read_discrepancies` devuelve las N como abiertas y los archivos `manual/` no cambiaron.

**AC3 — Atomicidad todo-o-nada: `git push` falla DESPUÉS de `bean-check` verde → rollback total (cierra defer #1 de 6.3).**
Given un batch que pasa `bean_check` pero cuyo `git_commit_push` lanza (simular con un `git_commit_push` que raise),
Then TODOS los archivos `manual/` escritos se restauran a su snapshot previo (NO quedan escritos), NINGUNA resolución se appendea, y todas las discrepancias siguen abiertas. **Un retry del mismo batch no produce doble-conteo** (ni por el rollback, ni — si el archivo hubiera sobrevivido — por el dedup de AC5). Verificable con un test que fuerza el raise del push y luego reintenta.

**AC4 — Lost-update: anotaciones a la misma cuenta+mes se escriben en UN write dentro del lock (cierra defer #2 de 6.3).**
Given dos (o más) `confirm-cartola-only` del mismo `bank_account_id` + mismo mes en el mismo batch,
Then ambas entries terminan en el archivo `manual/reconciliation-<leaf>-<YYYY-MM>.beancount` (ninguna se pierde), producto de una única lectura de `existing` + una única escritura, ejecutadas **dentro** del `.import.lock`. Verificable: tras el batch, el archivo contiene las 2 entries; el read del `existing` ocurre dentro del lock (no antes).

**AC5 — Idempotencia por `ref_discrepancy_id`.**
Given una discrepancia cuya tx YA fue escrita al archivo `manual/` (su `ref_discrepancy_id` ya aparece ahí),
When entra (de nuevo) en un batch,
Then su entry NO se re-appendea (dedup por `ref_discrepancy_id`) — el archivo no gana una copia duplicada. La resolución sí se appendea si faltaba (cierra la ventana crash-entre-push-y-append). Verificable: correr el batch dos veces → el archivo tiene la entry una sola vez.

**AC6 — Preflight: un id inválido aborta el batch entero antes de escribir.**
Given un batch donde AL MENOS un id falla un guard (no existe / ya resuelto / acción inválida para su estado / justificación <10 / `confirm-cartola-only` sin datos de cartola o cuenta no resoluble o USD sin FX>0),
Then el endpoint responde 400 (guard de validación) o 422 (anotación) identificando el id culpable, y **NINGUNA** discrepancia del batch se resuelve ni se escribe nada (todo-o-nada también en la validación). Verificable: batch de 3 con 1 acción inválida → los 3 siguen abiertos.

**AC7 — Anti-regresión del endpoint single + suite.**
Given el endpoint `POST .../{id}/resolve` (6.3) y `test_reconciliation_annotate.py`,
Then su comportamiento no cambia (mismos ACs de 6.3: anota → cierra; `bean-check` rojo → 422 + abierta; `escalate` → no cierra/no write; doble aprobación → rechazada). Cero regresión en la suite. `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` sin fallos nuevos (los 2 rojos de `test_fava_edit_validator` son PRE-EXISTENTES) + `npx tsc --noEmit` verde.

**AC8 — Frontend: multiselect en `ReconciliationPage`.**
Given el dashboard de reconciliación con una lista de discrepancias,
When el contador marca varias filas (checkbox por fila + "seleccionar todo") y elige resolverlas,
Then la UI arma el request batch (acción por-defecto derivable del estado de cada fila — p.ej. el único action de `missing-in-laudus` es `confirm-cartola-only`; para `confirm-cartola-only` opcionalmente una `category_account` por item), llama `resolve-batch`, muestra un resultado agregado (N resueltas / cuántas anotaron con su `git_commit_sha`), y ante 422/400 muestra el id culpable + el aviso "las diferencias siguen ABIERTAS — no se contabilizó nada" (paralelo al mensaje single de [ReconciliationPage.tsx:318](../../frontend/src/pages/ReconciliationPage.tsx#L318)). Invalida las queries `reconciliation`/`reconciliation-count` al terminar.

**AC9 — Tests.**
Backend: AC1 (spies de `bean_check`/`git_commit_push` ≤1); AC2 (`bean-check` rojo → rollback total + abiertas); AC3 (`git push` raise → rollback total + retry sin doble-conteo); AC4 (2 anotaciones misma cuenta+mes → ambas presentes, read dentro del lock); AC5 (batch dos veces → sin duplicado); AC6 (preflight con id inválido → todo-o-nada); batch mixto (anotan + baratas) → todas cerradas con un solo commit; batch solo-baratas → sin `bean_check`/git. Frontend: component test del multiselect (marcar varias → un request batch; resultado agregado; 422 → mensaje "siguen abiertas"). `bean-check` real sobre el render (patrón de `test_reconciliation_annotate.py`).

## Tasks / Subtasks

- [x] **Task 1 — Motor batch de anotación (acumula → un `bean_check` → un commit → rollback total)** (AC1, AC2, AC3, AC4, AC5)
  - [x] Nueva función `annotate_discrepancies_batch(items, *, importer, ledger_root, ts)` en `reconcile.py`: lock una vez, render-all primero (aborta sin tocar disco si algún item no rinde), agrupa por archivo, un read + un write por archivo dentro del lock, dedup por `ref_discrepancy_id`, un `bean_check`, un `git_commit_push` envuelto en try/except, rollback total de snapshots en ambos fallos. Helper puro `_render_annotation_entry(discrepancy, category_account, importer)` extraído (lanza `AnnotationRenderError` con los mismos mensajes) y usado idéntico por el single.
  - [x] **NO** appendea resoluciones (lo hace el service tras el push OK).

- [x] **Task 2 — Servicio `resolve_batch` (preflight + orquestación todo-o-nada)** (AC1, AC2, AC3, AC6, AC7)
  - [x] `resolve_batch(items, *, justification, user_email, now_iso, path, ledger_root, importer)` en `service.py`.
  - [x] Preflight con UNA lectura del JSONL: existe / resuelta (mismo criterio que `_resolved_ids`) / `ACTIONS_BY_STATE` / justificación común ≥10 (salvo todo-escalate) / ids duplicados intra-batch / tope `MAX_BATCH=50`.
  - [x] Separa anotan (`missing-in-laudus`+`confirm-cartola-only`) de baratas; llama al motor; `not success` → `AnnotationFailed`.
  - [x] Solo tras `success` (o nada que anotar) → `append_resolution` de TODAS, con el `git_commit_sha` por-id.

- [x] **Task 3 — Endpoint + schemas** (AC1, AC8)
  - [x] `POST /api/v1/reconciliation/discrepancies/resolve-batch` en `router.py`, RBAC contador/admin, `ResolveError`→400 / `AnnotationFailed`→422.
  - [x] Schemas `BatchResolveItem`/`BatchResolveRequest`/`BatchResolveResult`/`BatchResolveResponse` en `models.py`. **Desviación (por decisión cerrada 3):** la justificación va a nivel batch en `BatchResolveRequest`, no por-item.

- [x] **Task 4 — Frontend multiselect** (AC8)
  - [x] Checkbox por fila + "Seleccionar todo" + barra de acción ("Resolver N seleccionadas") con justificación común; acción por item = default del estado. **Desviación menor:** sin `category_account` por-item en el batch (van a Suspense; se categorizan luego en `/categorizacion` o vía el DrillDown single) — "opcional" en el AC.
  - [x] `resolveBatch(items, justification)` en `services/reconciliation.ts`, reusa `ResolveHttpError`.
  - [x] Resultado agregado + 422 con "siguen ABIERTAS". Invalida `['reconciliation']` + `['reconciliation-count']`.

- [x] **Task 5 — Tests + verificación** (AC9)
  - [x] `backend/tests/test_reconciliation_batch.py` (bean-check real): AC1 (spies ≤1), AC2, AC3 (raise+retry), AC5 (dedup engine + retry crash-window), AC6 (id inválido/acción inválida/ids duplicados), justificación corta, tope MAX_BATCH, batch mixto, batch solo-baratas, batch todo-escalate. 14 tests.
  - [x] Anti-regresión: `test_reconciliation_annotate.py` 11/11 sin cambios.
  - [x] Frontend: 3 component tests del multiselect en `ReconciliationPage.test.tsx`.
  - [x] `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` → 708 passed / 1 xfailed / 0 failed. `npx tsc --noEmit` verde.

## Dev Notes

### Estado actual de los archivos que se tocan (leídos para esta story)

- **[pipeline/importers/reconcile.py](../../pipeline/importers/reconcile.py)** —
  - `commit_reconciliation(file_path, new_content, discrepancy_id, action, ledger_root)` ([línea 192](../../pipeline/importers/reconcile.py#L192)): el motor write-and-replace de UN archivo. Toma `acquire_lock` ([209](../../pipeline/importers/reconcile.py#L209)), snapshot del `original` ([210](../../pipeline/importers/reconcile.py#L210)), write, `bean_check` ([212](../../pipeline/importers/reconcile.py#L212)) con rollback si rojo ([213-219](../../pipeline/importers/reconcile.py#L213)), `git_commit_push` ([221](../../pipeline/importers/reconcile.py#L221)) **sin try/except** (← defer #1). El batch NO llama a esta función N veces; implementa su propia versión multi-archivo con el mismo esqueleto pero un solo `bean_check`/push y rollback de todos.
  - `annotate_discrepancy(discrepancy, *, category_account, importer, ledger_root, ts)` ([línea 230](../../pipeline/importers/reconcile.py#L230)): renderiza la tx de la cartola y llama `commit_reconciliation`. El `existing = out_file.read_text()` + concat está en [322-324](../../pipeline/importers/reconcile.py#L322) **fuera del lock** (← defer #2). El batch mueve ese read dentro del lock. **Extraer el render (líneas 261-316) a un helper compartido.**
- **[backend/app/api/v1/reconciliation/service.py](../../backend/app/api/v1/reconciliation/service.py)** — `resolve()` ([182](../../backend/app/api/v1/reconciliation/service.py#L182)): el flujo single. Guards a reusar en el preflight: `_iter_lines`/`_is_original` (buscar original), `_resolved_ids` ([202](../../backend/app/api/v1/reconciliation/service.py#L202)), `ACTIONS_BY_STATE` ([18](../../backend/app/api/v1/reconciliation/service.py#L18) / validación [207](../../backend/app/api/v1/reconciliation/service.py#L207)), justificación ≥10 ([209](../../backend/app/api/v1/reconciliation/service.py#L209)). Excepciones `ResolveError`(400)/`AnnotationFailed`(422) ([29-34](../../backend/app/api/v1/reconciliation/service.py#L29)). `append_resolution` importado de `discrepancy_writer`.
- **[backend/app/api/v1/reconciliation/router.py](../../backend/app/api/v1/reconciliation/router.py)** — el single `POST .../{id}/resolve` ([71-85](../../backend/app/api/v1/reconciliation/router.py#L71)) mapea `ResolveError`→400, `AnnotationFailed`→422. El batch replica el mapeo.
- **[backend/app/api/v1/reconciliation/models.py](../../backend/app/api/v1/reconciliation/models.py)** — `ResolveRequest` (action/justification/category_account) + `ResolveResponse` (status/discrepancy_id/action/git_commit_sha). Los schemas batch se agregan acá.
- **[pipeline/importers/laudus_run.py](../../pipeline/importers/laudus_run.py)** — `git_commit_push(repo_root, paths, message)` ([208](../../pipeline/importers/laudus_run.py#L208)): no-op salvo `IMPORTER_GIT_ENABLED`; propaga fallos reales de git (add/commit/push) — por eso el batch DEBE envolverlo en try/except para rollback (hoy `commit_reconciliation` no lo hace). `bean_check(main_path)` ([~170](../../pipeline/importers/laudus_run.py#L170)): carga `main.beancount` completo con el loader. Acepta **una lista de paths** en un solo `git add` → el commit único del batch es natural.
- **[frontend/src/pages/ReconciliationPage.tsx](../../frontend/src/pages/ReconciliationPage.tsx)** — tabla de discrepancias ([136-147](../../frontend/src/pages/ReconciliationPage.tsx#L136)) + `DrillDown` single ([248](../../frontend/src/pages/ReconciliationPage.tsx#L248)) con el `CategoryAutocomplete` ([335](../../frontend/src/pages/ReconciliationPage.tsx#L335)) y el mensaje 422 "sigue ABIERTA" ([318](../../frontend/src/pages/ReconciliationPage.tsx#L318)). El multiselect se agrega a la tabla; el DrillDown single queda intacto.
- **[frontend/src/services/reconciliation.ts](../../frontend/src/services/reconciliation.ts)** — `resolveDiscrepancy` ([91](../../frontend/src/services/reconciliation.ts#L91)) + `ResolveHttpError` ([26](../../frontend/src/services/reconciliation.ts#L26)) + `ACTIONS_BY_STATE` ([52](../../frontend/src/services/reconciliation.ts#L52)). `resolveBatch` se modela sobre `resolveDiscrepancy`.

### Piezas existentes — REUSAR, no reescribir

| Pieza | Ubicación | Uso en 6.7 |
|---|---|---|
| render de la tx (postings + meta + FX) | inline en `annotate_discrepancy` [reconcile.py:261-316] | **extraer a helper puro** compartido single+batch |
| `bean_check`, `git_commit_push`, `acquire_lock` | [laudus_run.py](../../pipeline/importers/laudus_run.py) | el motor batch los llama UNA vez cada uno |
| guards de resolución | `resolve()` [service.py:198-210] | reusar en el preflight batch (factorizar si conviene) |
| `append_resolution` | [discrepancy_writer.py](../../pipeline/importers/discrepancy_writer.py) | cerrar cada discrepancia tras el push OK |
| `_iter_lines`/`_is_original`/`_resolved_ids` | [service.py](../../backend/app/api/v1/reconciliation/service.py) | cargar/validar el batch con UNA lectura del JSONL |
| `CategoryAutocomplete` / `ResolveHttpError` | ReconciliationPage.tsx / reconciliation.ts | reusar en la UI multiselect |

### Anti-patrones a evitar

- **NO** llamar `commit_reconciliation` (ni `annotate_discrepancy`) N veces en un loop desde el batch — eso reintroduce N `bean_check` + N push, que es justo lo que la story elimina.
- **NO** appendear ninguna resolución antes de que el push del batch sea exitoso (el orden write→bean-check→push→resolution es la correctitud central, heredada de 6.3 AC2).
- **NO** leer `existing` de los archivos `manual/` fuera del lock (reintroduce defer #2).
- **NO** dejar `git_commit_push` sin try/except en el path batch (reintroduce defer #1).
- **NO** tocar el path single ni sus tests (AC7 anti-regresión); si se extrae el helper de render, verificar que el single lo usa idéntico.

### Testing standards

- pytest en `backend/tests/`, `PYTHONUTF8=1` (gotcha Windows), venv `./venv/Scripts/python.exe`.
- `bean-check` real sobre el render (cargar `main.beancount` con el loader) — patrón [test_reconciliation_annotate.py](../../backend/tests/test_reconciliation_annotate.py).
- Ledger fixture: `accounts.beancount` (cuentas de banco/TC + Expenses + Suspense) + `manual/` + `main.beancount` que incluya `manual/*.beancount`.
- Spies: monkeypatchear `bean_check`/`git_commit_push` para contar llamadas (AC1) y forzar el raise del push (AC3).
- `monkeypatch.delenv("IMPORTER_GIT_ENABLED")` → git no-op local. Los 2 rojos de `test_fava_edit_validator` son PRE-EXISTENTES.
- Frontend: `vitest` component test, `npx tsc --noEmit` verde.

### Project Structure Notes

- Motor batch: `pipeline/importers/reconcile.py` (cohesión con `commit_reconciliation`/`annotate_discrepancy`).
- API: `backend/app/api/v1/reconciliation/` (service `resolve_batch`, router `resolve-batch`, models batch).
- Frontend: `frontend/src/pages/ReconciliationPage.tsx` + `frontend/src/services/reconciliation.ts`.
- Tests: `backend/tests/test_reconciliation_batch.py` (nuevo) + component test frontend.

### References

- [Source: _bmad-output/implementation-artifacts/6-3-aprobar-diferencia-anotar-beancount.md] — `annotate_discrepancy`, `resolve()` wiring, atomicidad AC2, los 2 defers de review (Review Findings, defers).
- [Source: _bmad-output/implementation-artifacts/deferred-work.md#Deferred from: code review of 6-3-aprobar-diferencia-anotar-beancount] — los 2 defers que esta story cierra (git push parcial + RMW lost-update).
- [Source: pipeline/importers/reconcile.py] — `commit_reconciliation` (192), `annotate_discrepancy` (230), read fuera del lock (322), `_BLOCKING`.
- [Source: pipeline/importers/laudus_run.py:208] — `git_commit_push` (propaga fallos → requiere try/except en el batch), `bean_check`, `acquire_lock`.
- [Source: backend/app/api/v1/reconciliation/service.py] — `resolve()`, `_resolved_ids`, `ACTIONS_BY_STATE`, `ResolveError`/`AnnotationFailed`.
- [Source: frontend/src/pages/ReconciliationPage.tsx, frontend/src/services/reconciliation.ts] — dashboard + service a extender con multiselect.
- [Source: memoria project_epic6_reconciliacion_next] — modelo A, Epic 6 estado.

## Preguntas de diseño para Ary (resolver antes/durante el dev)

1. **Tope N por batch.** Default propuesto = **50** por request (rechaza 422 si se excede). Costo real no escala con N (un solo `bean_check`/push), el tope es defensivo (payload/render/tamaño del commit). ¿50, otro número, o sin tope?

2. **¿Batch mixto o solo `confirm-cartola-only`?** Default propuesto = **mixto** (anotan + baratas en el mismo batch, todo-o-nada). Alternativa = batch solo-anotaciones (más simple: sin la rama de acciones baratas), obligando al contador a resolver las baratas por separado. ¿Mixto o solo-anotaciones?

3. **Justificación: por-item o una para el batch.** El single exige ≥10 chars por resolución. Opciones: (a) una justificación por item (fiel al single, más clicks); (b) una justificación común para todo el batch (menos fricción al cerrar el mes, pero menos granular en el audit trail). ¿Cuál?

4. **¿El batch commitea también el JSONL de resoluciones?** Default = **NO** (apoyarse en el dedup por `ref_discrepancy_id` para la durabilidad ante `git reset`; surgical, cierra solo los 2 defers nombrados). Alternativa = incluir el JSONL de discrepancias en el commit del batch (durabilidad completa de las resoluciones, pero abre el ciclo de vida del JSONL que hoy el path single tampoco commitea → asimetría). ¿Se sube a scope o queda para otra story?

5. **¿Migrar el path single al motor batch (batch-de-1)?** Default = **NO** (el single queda como está; los defers se cierran solo en el batch). Alternativa = reimplementar `annotate_discrepancy` sobre el motor batch con N=1, cerrando los 2 defers también en el single a costo de tocar 6.3 + sus tests. ¿Dejar el single como está (anti-regresión pura) o unificar?

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (1M context) — dev-story 2026-07-08.

### Debug Log References

- Baseline `test_reconciliation_annotate.py`: 11/11 antes y después del refactor (single intacto).
- Suite backend completa: 708 passed / 1 xfailed / 0 failed (694 baseline D7 + 14 nuevos).
- Frontend: `tsc --noEmit` limpio; vitest 103/103 (14 archivos), incluye 3 tests nuevos del multiselect.

### Completion Notes List

- **Atomicidad (snapshot/rollback):** el motor batch renderiza TODAS las tx primero (sin escribir); si un item no rinde aborta antes de tocar el lock. Dentro de UN `acquire_lock`: por archivo lee `existing` una vez, guarda `snapshots[out_file] = existing|None`, y escribe una vez. Un solo `bean_check(main.beancount)`; si rojo → `_restore()` (reescribe cada snapshot; los que eran None se borran). Un solo `git_commit_push` envuelto en `try/except Exception` → si lanza, mismo `_restore()`. Las resoluciones las appendea el service SOLO tras `success`, así nunca hay resolución sin tx commiteada ni tx sin resolución (cierra defers #1 y #2 de 6.3).
- **Dedup (AC5):** al escribir, se saltean las entries cuyo `ref_discrepancy_id: "<id>"` ya aparece en el `existing` del archivo destino. Si tras el dedup no queda nada nuevo (retry tras la ventana crash-entre-push-y-append), el motor devuelve `success=True` sin bean_check/commit y el service igual appendea la resolución que faltaba. Verificado corriendo el motor dos veces (AC5 engine) y con un test que borra la línea de resolución y reintenta (AC5 service).
- **Preflight todo-o-nada:** una lectura del JSONL construye `originals` + `resolved`; los guards (existe/resuelta/acción/justificación común/ids duplicados/tope) corren antes de llamar al motor. La validez de render de `confirm-cartola-only` (datos/cuenta/FX) la valida el motor en su render-all, previo a cualquier write.
- **Single sin cambios:** `annotate_discrepancy` ahora llama al helper extraído `_render_annotation_entry` y conserva su comportamiento (lee `existing` fuera del lock, vía `commit_reconciliation`) — el defer #2 sigue en el single a propósito (AC7 anti-regresión; los defers se cierran solo en el batch).

### Change Log

- 2026-07-08 — Story 6.7 redactada (batch-resolve + cierre de los 2 defers de atomicidad de 6.3). Draft, sin implementar.
- 2026-07-08 — Implementada: motor batch + helper de render compartido en `reconcile.py`; `resolve_batch` + `MAX_BATCH` en `service.py`; schemas + endpoint `resolve-batch`; multiselect + `resolveBatch` en el frontend; 14 tests backend + 3 frontend. Suite verde (708/1xfail; tsc + vitest OK). Sin commit.

### File List

- `pipeline/importers/reconcile.py` — `AnnotationRenderError`, `_render_annotation_entry` (extraído), `annotate_discrepancy` refactorizado a usarlo, `annotate_discrepancies_batch` (motor batch).
- `backend/app/api/v1/reconciliation/service.py` — `MAX_BATCH`, `resolve_batch`.
- `backend/app/api/v1/reconciliation/models.py` — `BatchResolveItem`/`BatchResolveRequest`/`BatchResolveResult`/`BatchResolveResponse`.
- `backend/app/api/v1/reconciliation/router.py` — endpoint `POST /discrepancies/resolve-batch`.
- `backend/tests/test_reconciliation_batch.py` — 14 tests (nuevo).
- `frontend/src/services/reconciliation.ts` — `resolveBatch` + tipos `BatchResolveItem`/`BatchResolveResponse`.
- `frontend/src/pages/ReconciliationPage.tsx` — multiselect (checkbox por fila + seleccionar todo + barra de acción batch).
- `frontend/src/pages/ReconciliationPage.test.tsx` — 3 tests nuevos del multiselect + mock de `resolveBatch`.
