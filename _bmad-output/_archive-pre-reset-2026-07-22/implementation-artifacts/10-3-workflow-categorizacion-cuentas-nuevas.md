# Story 10.3: Workflow de categorización de cuentas nuevas (promoción desde cuarentena)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **contador** (rol `contador`/`admin`),
I want **una UI self-serve que liste las cuentas que el importer Laudus dejó en cuarentena (`_new-accounts-pending.beancount`, tag `#pending-account`), me sugiera Cat1/Cat2 por prefijo, me deje fijar Cat3, y al confirmar escriba el `open` final + metadata `laudus_categoria1/2/3` al ledger Beancount (con lock + `bean-check` + `git_commit_push`), saque la cuenta de cuarentena y me recomiende correr el backfill**,
so that **una cuenta creada nueva en Laudus deja de aparecer como "sin categorizar" en el reporte y queda incorporada al plan de cuentas (fuente única Beancount) sin que yo tenga que editar archivos `.beancount` a mano**.

## Context

Esta story es la **promoción** del ciclo de vida de una cuenta nueva que ADR-001 §2 ya definió. **NO es infra nueva** — es orquestación del andamiaje que Epic 9 ya construyó:

- El importer Laudus (Story 9.4) detecta un `accountnumber` ausente de `accounts.beancount` → emite un `open` tentativo `Assets:EAG:PendingReview:Cuenta-{code}` en `ledger/imports/_new-accounts-pending.beancount` y taggea sus JEs con `#pending-account` ([beancount_writer.py:80-83, 198-210](../../pipeline/writers/beancount_writer.py#L80-L83)).
- Ya existen: lock de filesystem (`acquire_lock` / `.import.lock`), validación (`bean_check`), commit+push guardado (`git_commit_push`) — todos en [laudus_run.py:52-136](../../pipeline/importers/laudus_run.py#L52-L136).
- El reporte ya lee Beancount en prod y cuadra (`USE_BEANCOUNT_ENGINE_LEDGER=true`, Story 9.11). El guard de Story 10.2 hace visible la plata de cuentas sin categoría pero **no las categoriza** — esta story cierra ese loop.

**Gating CUMPLIDO** (ADR-001 §5): 10.2 ✅ + 9.4 en prod ✅ + 9.11 reporte-sobre-Beancount ✅ → 10.3 entrega valor pleno ahora (el reporte lee la misma fuente a la que esta story escribe).

**Distinta de Story 9.7:** 9.7 categoriza *transacciones* de cartola (smart_importer); 10.3 categoriza *cuentas del plan*. Vecinos, no duplicados.

**La reusa Story 9.14:** la mitad de escritura que armás acá (helper que escribe `open`+metadata con lock+bean-check+git) la reusa 9.14 para crear/editar bank-accounts. **Diseñá el helper de escritura como una pieza reutilizable, no inline en el endpoint.**

## 🚨 Decisión de diseño central — D1: dónde se escribe la cuenta promovida (RESUELTA → Camino A)

> **DECISIÓN (Ary, 2026-06-17): Camino A — append a `ledger/accounts.beancount`.** Cero cambios al writer; el backfill funciona out of the box. El dev implementa Camino A; la tabla y el Camino B quedan como contexto del *por qué*. **Consecuencia para 9.14:** el helper de escritura reusable escribe a `accounts.beancount`, así que 9.14 hereda ese destino (no `manual/` como decía su AC3 draft — 9.14 deberá alinearse). **Nota:** el header de `accounts.beancount` dice "NO editar a mano sin re-correr generate_accounts.py" — ese comentario quedó **stale** tras 9.11 (generate_accounts es DR-only); el append manual/programático ES ahora el mecanismo de edición. Actualizar ese header como parte de la implementación.

ADR-001 §3 **recomendaba** escribir a la zona `manual/` (`ledger/manual/*.beancount`) por limpieza Open/Closed, pero marcó la decisión como *"confirmar al implementar 10.3"*. **La verificación de código destapó un acoplamiento que la hizo load-bearing, no cosmética** (por eso se resolvió por Camino A):

El índice de cuentas del importer — `load_account_index()` — lee **solo `accounts.beancount`** ([beancount_writer.py:68-77](../../pipeline/writers/beancount_writer.py#L68-L77)). De ahí dependen TRES cosas:
1. **Resolución de JEs nuevas** (`_rows_to_jes`): un code que no está en ese índice → se vuelve a mandar a PendingReview.
2. **Reconciliación de la cuarentena** (`write_jes` línea 269: `c not in account_index`): un code que no está en el índice → la entrada de cuarentena **nunca se borra**.
3. **Re-resolución del backfill**: `run_import(mode="backfill")` re-corre el writer con el mismo índice → si el code no está en `accounts.beancount`, el backfill es **no-op** (las JEs viejas siguen en PendingReview para siempre).

➡️ **Consecuencia:** si la cuenta promovida se escribe SOLO a `manual/`, el importer nunca la reconoce: las JEs nuevas siguen yendo a cuarentena, la entrada pendiente no se limpia, y el backfill no re-apunta nada. **El feature no funciona end-to-end.** Que el reporte la "vea" (porque `main.beancount` incluye `manual/*.beancount`) es irrelevante: las JEs viejas siguen posteadas a `PendingReview:Cuenta-{code}`, que no tiene categoría → siguen apareciendo como "sin categorizar".

**Dos caminos válidos — elegí uno y dejalo registrado en Completion Notes:**

| | **Camino A (recomendado) — `accounts.beancount`** | **Camino B — `manual/` + índice unificado** |
|---|---|---|
| Escritura | Append del `open` a `ledger/accounts.beancount` | `open` a `ledger/manual/*.beancount` |
| Cambio al writer | **Ninguno** — `load_account_index` ya lo lee | Extender `load_account_index` (+ `_min_account_number` + reconciliación de cuarentena) para unir `accounts.beancount` + `manual/*.beancount` |
| Backfill re-resuelve | ✅ out of the box | ✅ solo tras extender el índice |
| Limpieza Open/Closed | Mezcla generado+manual (aceptable: `generate_accounts.py` ya es DR-only tras 9.11/ADR §4) | ✅ separación limpia |
| Consistencia con 9.14 | 9.14 AC3 asume `manual/` → habría que alinear | ✅ coincide con 9.14 |
| Superficie/riesgo | Mínima (pura orquestación) | Toca código del importer 9.4 (más superficie, más tests) |

**Resuelto por Camino A** (ver caja de DECISIÓN arriba): "Simplicity First" — `generate_accounts.py` ya quedó retirado a DR-only (9.11/ADR §4), así que el argumento histórico contra appendear a `accounts.beancount` ("seguro solo una vez retirada la generación", ADR §3) **ya se cumple**. Cero cambios al writer; el backfill funciona sin tocar nada.

## Acceptance Criteria

**AC1 — Listar cuentas en cuarentena (endpoint de lectura)**

**Given** el importer dejó cuentas en `_new-accounts-pending.beancount` con tag `#pending-account`
**When** se llama `GET /api/v1/cuentas-pendientes/` (rol `contador`/`admin`)
**Then** la respuesta lista, por cada code pendiente: `code`, `pending_account` (la cuenta `PendingReview:Cuenta-{code}`), `monto_acumulado` (suma de las JEs `#pending-account` que la referencian, para que el contador la priorice), y `laudus_account_name` si el importer lo capturó
**And** los datos se leen del ledger vía `LedgerService` (entries del `main.beancount` cargado), no de Supabase ni Sheets
**And** el endpoint está gated por `USE_BEANCOUNT_ENGINE_LEDGER` (con el flag off, Beancount no es la fuente → 404/lista vacía, consistente con el resto del backend)

---

**AC2 — Sugerencia Cat1/Cat2 por prefijo (NO Cat3)**

**Given** un code pendiente (ej. `413xxx`)
**When** se arma la sugerencia
**Then** `Cat1`/`Cat2` se derivan de las cuentas **ya existentes en `accounts.beancount` que comparten el prefijo numérico** del code (relación prefijo→Cat1/Cat2 verificada 1:1 — ADR-001 §Contexto + sprint-change-proposal §Evidencia)
**And** `Cat3` **nunca** se autosugiere (el rubro fino requiere criterio humano: el número completo determina Cat3 1:1, el prefijo no)
**And** si no hay cuentas hermanas con ese prefijo, la sugerencia Cat1/Cat2 va vacía (el humano fija todo) — sin inventar valores

---

**AC3 — Promover: escribir `open`+metadata, bean-check, git (endpoint de escritura, helper reusable)**

**Given** el contador revisó una cuenta pendiente y fijó `categoria1`/`categoria2`/`categoria3` (+ opcionalmente edita el `laudus_account_name` y el nombre de cuenta Beancount)
**When** se llama `POST /api/v1/cuentas-pendientes/{code}/promover` (rol `contador`/`admin`) con el body de categorías
**Then** un **helper de escritura reusable** (no inline — lo reusa 9.14):
- appendea el `open` final con metadata `code`, `laudus_account_name`, `laudus_categoria1/2/3` a `ledger/accounts.beancount` (Camino A, ver D1)
- toma `acquire_lock(.import.lock)` antes de escribir (mismo lock que el cron del sábado → sin carrera; ver ADR-001 §Riesgos)
- corre `bean_check(main.beancount)` **antes de commitear — NO-NEGOCIABLE**; si falla → rollback (revierte la escritura, no commitea) y responde `422` con el detalle del error
- commitea+pushea vía `git_commit_push` (guardado por `IMPORTER_GIT_ENABLED`); si el push falla → degrada con gracia (la escritura local persiste, se reporta el fallo) — mismo patrón que el importer
**And** reusa las funciones existentes de [laudus_run.py](../../pipeline/importers/laudus_run.py) (`acquire_lock`, `bean_check`, `git_commit_push`) — **no reimplementar lock/validación/git**
**And** antes de escribir, refresca el clon del ledger del backend a `origin/main` (reusar `_refresh_ledger_clone`, [sync/service.py:125](../../backend/app/api/v1/sync/service.py#L125)) para no chocar con un push del cron (non-fast-forward)

---

**AC4 — La cuenta sale de cuarentena y entra al índice del importer**

**Given** AC3 + la decisión D1 implementada
**When** la promoción terminó OK
**Then** el code promovido queda en el índice que usa `load_account_index()` del writer, de modo que:
- la próxima corrida del importer (o la reconciliación de `write_jes`) **deja de listar el code** en `_new-accounts-pending.beancount` (`c not in account_index` → se cae solo)
- las JEs nuevas de ese code dejan de ir a `PendingReview` y se postean a la cuenta real
**And** se verifica con un test que tras promover, un re-run del writer no vuelve a emitir el code como pending

---

**AC5 — Disparar/recomendar backfill post-promoción**

**Given** una promoción exitosa
**When** se responde al cliente
**Then** la respuesta incluye `backfill_recommended: true` con un mensaje claro de que **las JEs históricas siguen apuntando a `PendingReview:Cuenta-{code}` hasta correr un backfill** (limitación documentada en [importers/README.md:113-115](../../pipeline/importers/README.md#L113-L115))
**And** la UI ofrece un CTA "correr backfill ahora" que **reusa el endpoint existente** `POST /api/v1/sync/trigger` con `mode=backfill` (Story 9.4) — **NO crear un endpoint de backfill nuevo**
**And** no se auto-dispara el backfill (es pesado; el contador decide cuándo) — solo se recomienda

---

**AC6 — La cuenta deja de aparecer como "sin categorizar" en el reporte**

**Given** AC3 + el backfill de AC5 corrido
**When** el contador regenera el reporte de gastos (Story 10.2)
**Then** la cuenta promovida **deja de salir en la fila "⚠️ cuentas sin categorizar"** y su plata cae en el `Cat1`/`Cat2`/`Cat3` asignado
**And** tras la escritura, el endpoint invoca `LedgerService.load()` para que el reporte en el proceso del backend vea el cambio sin esperar redeploy ([ledger_service.py](../../backend/app/services/ledger_service.py), método `load()`)
**And** test de regresión: una cuenta pendiente con movimiento → tras promover+backfill → aparece categorizada y NO en el balde de sin clasificar

---

**AC7 — UI self-serve (frontend contador/admin)**

**Given** los endpoints AC1/AC3
**When** el contador abre la página de cuentas pendientes
**Then** ve la lista de cuentas en cuarentena con su monto acumulado y la sugerencia Cat1/Cat2 precargada
**And** por cada cuenta puede: editar Cat1/Cat2 (precargadas), **fijar Cat3 (obligatorio, vacío por defecto)**, y confirmar → dispara el `POST` de promoción
**And** tras una promoción exitosa, muestra el CTA "correr backfill ahora" (AC5) y refresca la lista (la cuenta promovida desaparece)
**And** sigue el patrón existente: página bajo `frontend/src/pages/`, service bajo `frontend/src/services/` con `fetch(..., { credentials: 'include' })`, modelado sobre `ReportesPage.tsx` + `services/reportes.ts`
**And** la página es visible solo para `contador`/`admin` (gating frontend RBAC, Story 9.13)

---

**AC8 — Tests + no-regresión**

**Given** la implementación
**When** corre la suite
**Then** hay tests backend contra un **ledger fixture** (patrón `tmp_path` + `LedgerService` + `app.dependency_overrides`, ver [test_dashboard_beancount.py:26-99](../../backend/tests/test_dashboard_beancount.py#L26-L99)) que cubren: listar pendientes (AC1), sugerencia por prefijo (AC2), promoción con bean-check verde (AC3), **rollback con bean-check rojo** (AC3 — `open` malformado no commitea), reconciliación de cuarentena (AC4)
**And** RBAC: `family` recibe 403 en los endpoints de esta story; `contador`/`admin` pasan
**And** **cero regresiones** en el importer Laudus (9.4) ni en el reporte (10.2): correr la suite existente verde (ojo: `test_run_backfill` y `test_sync` tienen rojos pre-existentes date-dependientes no relacionados — no atribuírselos a esta story)

## Tasks / Subtasks

- [x] **Task 1: Helper de escritura reusable** (AC3, AC4) — *lo reusa 9.14, diseñar como módulo, no inline* · **destino = `accounts.beancount` (Camino A, resuelto)**
  - [x] Función que, dado `code` + `laudus_account_name` + `categoria1/2/3` (+ nombre de cuenta Beancount), arma el bloque `open` con metadata y lo **appendea a `ledger/accounts.beancount`**
  - [x] Envolver en `acquire_lock(.import.lock)` + `bean_check(main.beancount)` + `git_commit_push` reusando [laudus_run.py](../../pipeline/importers/laudus_run.py) (importar, no reimplementar)
  - [x] Refresh del clon (`_refresh_ledger_clone`) antes de escribir; rollback si bean-check falla; degradar con gracia si push falla
  - [x] Actualizar el header stale de `accounts.beancount` (ver caja DECISIÓN D1)
  - [x] Tras escritura OK: `LedgerService.load()` para refrescar el ledger en proceso (AC6)

- [x] **Task 2: Endpoint de lectura + sugerencia** (AC1, AC2)
  - [x] `GET /api/v1/cuentas-pendientes/` → lee `_new-accounts-pending.beancount`/entries vía `LedgerService`; suma montos de JEs `#pending-account` por code
  - [x] Motor de sugerencia: agrupar opens de `accounts.beancount` por prefijo numérico → proponer Cat1/Cat2 de las hermanas; Cat3 siempre vacío
  - [x] Gating `USE_BEANCOUNT_ENGINE_LEDGER`; router nuevo `cuentas_pendientes/{router,service,schemas}.py` registrado en [api/v1/router.py](../../backend/app/api/v1/router.py)
  - [x] RBAC `require_role(["contador","admin"])`

- [x] **Task 3: Endpoint de promoción** (AC3, AC5)
  - [x] `POST /api/v1/cuentas-pendientes/{code}/promover` → valida body (Cat3 obligatorio), llama al helper de Task 1
  - [x] Respuesta con `backfill_recommended: true` + mensaje (AC5); errores: `422` bean-check, `409` lock timeout, `503`/`404` ledger no disponible
  - [x] RBAC `require_role(["contador","admin"])`

- [x] **Task 4: UI self-serve** (AC7)
  - [x] `frontend/src/services/cuentasPendientes.ts` (list + promote) modelado sobre `services/reportes.ts`/`sync.ts`
  - [x] Página `frontend/src/pages/CuentasPendientesPage.tsx` con lista de pendientes, form Cat1/Cat2/Cat3, confirmar, CTA backfill (reusa `triggerSync('backfill')`)
  - [x] Ruta + nav gated a `contador`/`admin` (RBAC frontend, Story 9.13); registrado en `App.tsx` + `Sidebar.tsx`

- [x] **Task 5: Tests + no-regresión** (AC8)
  - [x] Backend: list, sugerencia, promote (bean-check verde), rollback (bean-check rojo), reconciliación de cuarentena, RBAC 403 family — contra ledger fixture `tmp_path`
  - [x] Test AC4: re-run del writer tras promoción no re-emite el code como pending
  - [x] Test AC6: pre-backfill cae en cuarentena (Categoria vacía) → post-promover+backfill categorizada, no en "sin clasificar"
  - [x] Correr suite existente: 530 passed / 1 xfailed; único rojo = `test_run_backfill_calls_upsert_for_both_sheets` (date-dependiente pre-existente, no atribuible)

### Review Findings

_Code review adversarial (Blind Hunter + Edge Case Hunter + Acceptance Auditor), 2026-06-17. 3 capas, 0 fallidas. 5 patches, 0 decision-needed, 0 deferred, 14 descartados como ruido (falsos positivos verificados: LEDGER_DIR mismatch, tipo de excepción de `git_commit_push`, `LedgerUnavailableError.detail`, doble-submit, double-count de `monto_acumulado` con importer real, etc.)._

- [x] [Review][Patch] **[HIGH] El frontend trata el push-fallido como éxito pleno y ofrece el backfill que descarta el commit local** [frontend/src/pages/CuentasPendientesPage.tsx:103-121] — En el path de push fallido el backend devuelve HTTP 200 con `git_commit_sha=null` + `message` de advertencia ("el push falló… reintentá antes de correr el backfill"). El frontend ignora `git_commit_sha`/`message`: muestra "✅ Cuenta promovida" y el botón "Correr backfill ahora" igual. Como `_refresh_ledger_clone()` hace `git reset --hard origin/main` (sync/service.py:144), correr el backfill ahí **descarta el commit local no-pusheado y pierde la categorización en silencio**. Fix: cuando `git_commit_sha === null`, mostrar `promote.data.message` como advertencia y NO ofrecer el botón de backfill (ofrecer "reintentar promoción").
- [x] [Review][Patch] **[MEDIUM] El error del backfill no se muestra en el frontend** [frontend/src/pages/CuentasPendientesPage.tsx:108-116] — La mutation `backfill` no renderiza `isError`. Si `triggerSync('backfill')` falla (ej. sync ya corriendo → ValueError → non-200), el usuario no recibe feedback: el botón se re-habilita sin señal. Fix: agregar `{backfill.isError && <p className="text-sm text-destructive">{(backfill.error as Error).message}</p>}`.
- [x] [Review][Patch] **[LOW] El parse de error del frontend asume `detail` string** [frontend/src/services/cuentasPendientes.ts:45-46] — `detail?.detail` puede ser un array (422 de validación de FastAPI), produciendo `Error: [object Object]`. En la práctica el body siempre va bien formado, pero un guard defensivo es barato. Fix: si `Array.isArray(detail?.detail)`, mapear `.msg`.
- [x] [Review][Patch] **[LOW] Comentario engañoso sobre el lock vs el cron** [backend/app/services/beancount_promote.py:132] — "dentro del lock → el cron no puede pushear entre refresh y push" sobreestima la garantía: el cron corre en otro proceso/disco (`/tmp/ledger-repo`, cron-importer-entry.sh) con su propio `.import.lock` — el lock NO lo serializa. La carrera real se maneja con gracia (push-reject → `CalledProcessError` → degradación). Como 9.14 reusa este helper, vale aclarar el comentario para no inducir a error.
- [x] [Review][Patch] **[LOW] Test gap: el rol `admin` no está cubierto** [backend/tests/test_cuentas_pendientes.py] — Solo se testea `contador` (éxito) y `family` (403). AC8 nombra `admin` explícitamente; `require_role(["contador","admin"])` lo cubre pero no hay test. Fix: agregar un caso con JWT `role="admin"`.

## Dev Notes

### Andamiaje EXISTENTE a REUSAR (no reinventar)

| Pieza | Dónde | Cómo se usa |
|---|---|---|
| Lock de filesystem | `acquire_lock(lock_path)` [laudus_run.py:52](../../pipeline/importers/laudus_run.py#L52) | `with acquire_lock(root/".import.lock"): ...` — mismo lock que el cron |
| Validación | `bean_check(main_path)` [laudus_run.py:82](../../pipeline/importers/laudus_run.py#L82) | retorna `(ok, detail)`; si `not ok` → rollback, no commit |
| Git commit/push | `git_commit_push(root, paths, msg)` [laudus_run.py:106](../../pipeline/importers/laudus_run.py#L106) | guardado por `IMPORTER_GIT_ENABLED`; propaga fallo real de git |
| Refresh del clon | `_refresh_ledger_clone()` [sync/service.py:125](../../backend/app/api/v1/sync/service.py#L125) | fetch+reset a origin/main antes de escribir (evita non-fast-forward) |
| Backfill | `run_import(mode="backfill", from_date=...)` [laudus_run.py:214](../../pipeline/importers/laudus_run.py#L214) | **vía `POST /sync/trigger` `mode=backfill`** — no llamar directo desde 10.3 |
| Índice de cuentas | `load_account_index(accounts_path)` [beancount_writer.py:68](../../pipeline/writers/beancount_writer.py#L68) | code→cuenta; **clave para D1** (lee solo accounts.beancount) |
| Cuenta de cuarentena | `_pending_account(code)` = `Assets:EAG:PendingReview:Cuenta-{code}` [beancount_writer.py:80](../../pipeline/writers/beancount_writer.py#L80) | |
| LedgerService | `Depends(get_ledger_service)` [dependencies.py:28](../../backend/app/dependencies.py#L28) | `.entries()` para leer; `.load()` para refrescar tras escritura |
| RBAC | `require_role(["contador","admin"])` [dependencies.py:71](../../backend/app/dependencies.py#L71) | roles válidos: `family`/`contador`/`admin` |
| Feature flag | `_flag("USE_BEANCOUNT_ENGINE_LEDGER")` (patrón en sync/dashboard/reportes) | env var truthy |

### Formato del `open` a escribir (espejo de `accounts.beancount`)

```beancount
2020-12-31 open Assets:EAG:<Nombre>-<code> CLP
  code: "<code>"
  laudus_account_name: "<nombre Laudus>"
  laudus_categoria1: "<Cat1>"
  laudus_categoria2: "<Cat2>"
  laudus_categoria3: "<Cat3>"
```

Ver ejemplos reales en [accounts.beancount:8-31](../../ledger/accounts.beancount#L8-L31). La fecha del `open` puede ser una fecha-piso estable (las cuentas existentes usan `2020-12-31`); no inventar una fecha "de hoy" que rompa balances históricos. El **árbol de cuenta Beancount** (`Assets:EAG:...` / `Expenses:EAG:...`) lo determina la raíz según Cat1 — derivarlo del patrón de las cuentas hermanas del prefijo (mismo criterio que la sugerencia Cat1/Cat2), o dejar que el contador lo confirme.

### Flujo end-to-end (lo que tiene que pasar para que "funcione")

1. Importer detecta code desconocido → `PendingReview:Cuenta-{code}` + JEs `#pending-account` (ya pasa).
2. Contador abre la UI → ve el code, monto, sugerencia Cat1/Cat2 (AC1/AC2).
3. Contador fija Cat3, confirma → `POST /promover` → helper escribe `open` (destino D1) con lock+bean-check+git (AC3).
4. El code entra al índice del importer → cuarentena se limpia, JEs nuevas resuelven a la cuenta real (AC4).
5. Contador corre backfill (CTA → `/sync/trigger` `mode=backfill`) → JEs históricas se re-apuntan de `PendingReview` a la cuenta real (AC5).
6. Reporte: la plata cae en su categoría, ya no en "sin categorizar" (AC6).

⚠️ **Sin el paso 5 (backfill), los pasos 3-4 NO arreglan el reporte para la plata histórica** — solo para JEs futuras. Por eso AC5 es parte del contrato, no un nice-to-have.

### Estado actual a PRESERVAR (no romper)

- **Importer Laudus 9.4** ([laudus_run.py](../../pipeline/importers/laudus_run.py), [beancount_writer.py](../../pipeline/writers/beancount_writer.py)): determinista e idempotente. **Camino A no toca el writer** — solo appendea a `accounts.beancount`, que `load_account_index` ya lee. No reimplementar ni alterar `write_jes`/`load_account_index`.
- **Cuarentena** `_new-accounts-pending.beancount`: el writer la **regenera entera en cada corrida** ([beancount_writer.py:198](../../pipeline/writers/beancount_writer.py#L198)) — su header dice "no editar a mano". 10.3 NO edita ese archivo directamente; lo limpia indirectamente vía el índice (AC4). No escribir a mano en él.
- **Reporte 10.2** ([report_builder.py](../../backend/app/api/v1/reportes/report_builder.py)): el guard de "sin categorizar" detecta por prefijo. Verificar que una cuenta promovida+backfilleada deja de caer ahí.
- **`main.beancount`** ya incluye `accounts.beancount`, `manual/*.beancount` y `imports/_new-accounts-pending.beancount` ([main.beancount:22-28](../../ledger/main.beancount#L22-L28)) — ambos destinos D1 son visibles para el reporte; el corte está en el índice del importer, no en el reporte.

### Convención de endpoints / dónde va el código nuevo

- Router modular nuevo: `backend/app/api/v1/cuentas_pendientes/{router.py, service.py, schemas.py}` (patrón de `sync/`, `bank_accounts/`), registrado en [api/v1/router.py](../../backend/app/api/v1/router.py) (¿con prefix `/cuentas-pendientes`? — alinear con `plan-de-cuentas`/`bank-accounts` kebab).
- El endpoint más parecido a copiar es **`/sync/trigger`** ([sync/router.py](../../backend/app/api/v1/sync/router.py) + [sync/service.py:149-183](../../backend/app/api/v1/sync/service.py#L149-L183)): gated por flag, RBAC contador/admin, corre el importer.

### Project Structure Notes

```
backend/app/api/v1/cuentas_pendientes/
  router.py     # NEW — GET /, POST /{code}/promover (RBAC contador/admin, gated por flag)
  service.py    # NEW — listar pendientes + motor de sugerencia por prefijo
  schemas.py    # NEW — PendingAccount, PromoteRequest (Cat3 obligatorio), PromoteResponse
backend/app/services/
  beancount_promote.py   # NEW (sugerido) — helper de escritura REUSABLE (lo reusa 9.14): open+metadata + lock + bean-check + git
  ledger_service.py      # READ — .entries() / .load()
ledger/accounts.beancount  # MODIFY — destino de escritura (Camino A) + actualizar header stale
frontend/src/pages/CuentasPendientesPage.tsx   # NEW
frontend/src/services/cuentasPendientes.ts     # NEW
backend/tests/test_cuentas_pendientes.py       # NEW
```

### References

- [Source: adr-001-plan-de-cuentas-beancount-source-of-truth.md §2-§3 — 10.3 ES la promoción; destino de escritura = decisión a confirmar (D1); reusa lock/git/bean-check]
- [Source: adr-001 §Riesgos y trade-offs — bean-check NO-NEGOCIABLE; lock compartido con el cron; git como audit log + degradar si push falla; backfill post-promoción]
- [Source: sprint-change-proposal-2026-06-10.md §4.1 Story 10.3 — ACs draft (detectar, sugerir Cat1 por prefijo, persistir a fuente única, dejar de mostrar "sin clasificar")]
- [Source: sprint-change-proposal-2026-06-10.md §Evidencia — prefijo→Cat1/Cat2 1:1, número completo→Cat3 1:1 → Cat3 requiere humano]
- [Source: 9-14-migrar-bank-accounts-beancount.md AC3 + Dev Notes — 9.14 reusa el helper de escritura de 10.3; asume destino manual/ (relevante para D1)]
- [Source: pipeline/importers/README.md — limitación backfill post-promoción; promote() reusa lock+bean-check+git]
- [Source: pipeline/importers/laudus_run.py:52-136,214 — acquire_lock, bean_check, git_commit_push, run_import(backfill)]
- [Source: pipeline/writers/beancount_writer.py:68-83,198-271 — load_account_index, _pending_account, reconciliación cuarentena (el acoplamiento de D1)]
- [Source: backend/app/api/v1/sync/service.py:125-183 — _refresh_ledger_clone, patrón importer-on-demand gated por flag]
- [Source: backend/app/dependencies.py:28-91 — get_ledger_service, require_role, roles válidos]
- [Source: backend/tests/test_dashboard_beancount.py:26-99 — patrón de ledger fixture (tmp_path + dependency_overrides)]
- [Source: backend/app/api/v1/reportes/report_builder.py:68-87 — guard 10.2 "sin categorizar" por prefijo]
- [Source: ledger/accounts.beancount:8-31 + main.beancount:22-28 — formato open+metadata, includes del ledger]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Amelia / dev-story)

### Debug Log References

- Suite nueva: `backend/tests/test_cuentas_pendientes.py` → 13 passed.
- Suite completa backend: `530 passed, 1 xfailed, 1 failed`. Único rojo =
  `test_sync.py::test_run_backfill_calls_upsert_for_both_sheets` (`balance_sheet_upserted == 1`
  got 3) — fallo date-dependiente pre-existente en el path Sheets (eom date calc), sin relación
  con esta story (la story lo declara explícitamente como no atribuible en AC8).
- Frontend: `tsc --noEmit` limpio; `Sidebar.test.tsx` 3/3.

### Completion Notes List

- **D1 implementado por Camino A** (resuelto por Ary): el helper appendea el `open` a
  `ledger/accounts.beancount`. Cero cambios al writer 9.4; `load_account_index()` ya lo lee →
  el backfill re-resuelve out of the box (AC4/AC5). Header stale de `accounts.beancount`
  actualizado (la edición ahora es por append/endpoint, `generate_accounts.py` quedó DR-only).
- **Helper reusable** en `backend/app/services/beancount_promote.py` (`promote_account`,
  `build_open_block`, `is_valid_account`, `camel_leaf`) — diseñado como módulo, NO inline, para
  que Story 9.14 lo reuse. Garantías: `acquire_lock` (mismo lock del cron) → `bean_check`
  (NO-NEGOCIABLE; rollback de la escritura si rojo → `PromoteError` → 422) → `git_commit_push`
  (degrada con gracia). `refresh_clone` se inyecta como callable (el router pasa
  `_refresh_ledger_clone`; tests/local = no-op). Importa lock/validación/git de `laudus_run.py`,
  no los reimplementa.
- **Motor de sugerencia**: agrupa los `open` existentes por prefijo numérico de 3 dígitos →
  propone Cat1/Cat2 + cuenta Beancount (`Root:Entity:CamelCaseLeaf-{code}`) de la hermana de
  menor code. Cat3 nunca se sugiere (criterio humano, AC2); sin hermanas → todo vacío.
- **Endpoints** (`backend/app/api/v1/cuentas_pendientes/`): `GET /` lista pendientes +
  monto acumulado (suma de magnitudes de las postings `#pending-account`) + sugerencia;
  `POST /{code}/promover` valida Cat3 obligatorio (en el router → 422 limpio; un `field_validator`
  de Pydantic chocaba con el error-handler custom que no serializa el `ctx`), deriva/valida la
  cuenta destino, llama al helper, hace `ledger.load()` (AC6) y responde `backfill_recommended:
  true` + CTA `POST /sync/trigger mode=backfill` (no se crea endpoint de backfill nuevo, AC5).
  Ambos gated por `USE_BEANCOUNT_ENGINE_LEDGER` (flag off → GET lista vacía, POST 404) + RBAC
  contador/admin.
- **Ledger root** se deriva de `LedgerService.main_path` (nueva property read-only) → el dir que
  contiene `main.beancount`/`accounts.beancount`/`.import.lock`. Hace el helper testeable con
  `tmp_path` y consistente en prod (clon del backend).
- **AC6 verificado end-to-end** vía `report_rows_via_beancount` + `build_report`: pre-backfill la
  JE postea a `PendingReview:Cuenta-{code}` (Categoria vacía → cae en "sin categorizar");
  post-promover+backfill postea a la cuenta real cuyo `open` lleva las categorías → la plata cae
  en su Cat2 y NO aparece en el balde de sin clasificar.
- **UI** (`CuentasPendientesPage.tsx` + `services/cuentasPendientes.ts`): lista con monto +
  sugerencia precargada, Cat1/Cat2 editables, Cat3 obligatorio (botón disabled si vacío), CTA
  "correr backfill ahora" tras promover (reusa `triggerSync('backfill', '2021-01-01')`). Ruta
  `/cuentas-pendientes` + nav en Sidebar, gated contador/admin (Story 9.13).
- **HANDOFF a Ary (no codeable, post-merge):** flujo end-to-end real en prod requiere
  `USE_BEANCOUNT_ENGINE_LEDGER=true` (ya on) + `IMPORTER_GIT_ENABLED=true` + `BEANCOUNT_DEPLOY_KEY`
  (ya configurados para el cron 9.4). Tras promover una cuenta real, correr el backfill desde la
  UI re-apunta las JEs históricas; verificar en el reporte que la cuenta deja de salir en
  "sin categorizar".

### File List

**Nuevos (backend):**
- `backend/app/services/beancount_promote.py` — helper de escritura reusable (lock+bean-check+git+rollback)
- `backend/app/api/v1/cuentas_pendientes/__init__.py`
- `backend/app/api/v1/cuentas_pendientes/schemas.py`
- `backend/app/api/v1/cuentas_pendientes/service.py` — listado + motor de sugerencia
- `backend/app/api/v1/cuentas_pendientes/router.py` — GET / + POST /{code}/promover
- `backend/tests/test_cuentas_pendientes.py` — 13 tests (AC1/AC2/AC3/AC4/AC6/AC8)

**Modificados (backend):**
- `backend/app/api/v1/router.py` — registra el router `cuentas-pendientes`
- `backend/app/services/ledger_service.py` — property `main_path` (raíz del ledger para escribir)
- `ledger/accounts.beancount` — header stale actualizado (SoT editable por append/endpoint)

**Nuevos (frontend):**
- `frontend/src/services/cuentasPendientes.ts`
- `frontend/src/pages/CuentasPendientesPage.tsx`

**Modificados (frontend):**
- `frontend/src/App.tsx` — ruta `/cuentas-pendientes` gated contador/admin
- `frontend/src/components/layout/Sidebar.tsx` — nav "Cuentas Pendientes"

## Change Log

| Fecha | Cambio |
|---|---|
| 2026-06-17 | Implementación 10.3 (Camino A): helper de promoción reusable + endpoints cuentas-pendientes + UI self-serve + 13 tests. Status → review. |
