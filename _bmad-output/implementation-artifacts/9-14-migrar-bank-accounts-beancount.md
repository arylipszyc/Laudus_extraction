---
story: 9.14
title: Migrar bank-accounts a Beancount + apagar Supabase
status: done
epic: 9
depends_on: [9.1, 10.3]
gate_condition: cartola-upload-funciona-sin-supabase
blocks: [apagar-supabase-standby]
---

# Story 9.14 — Migrar bank-accounts a Beancount + apagar Supabase

## Story

As Ary,
I want the `bank-accounts` registry endpoints (`GET`/`POST`/`PATCH /api/v1/bank-accounts/`) to read and write the bank metadata that already lives in `accounts.beancount` (modelo unificado 9.1) instead of the Supabase `bank_accounts` table,
So that the last live consumer of Supabase is retired, I can shut down the Supabase standby project, and Story 4.0's sunk-cost is fully closed — completing Epic 9's goal of replacing Sheets+Supabase as source of truth.

## Context

**Por qué existe esta story:** durante la verificación de scope de 9.11 (2026-06-17) se destapó que `bank-accounts` es el **último consumidor vivo de Supabase**. La Story 9.11 depreca el plan de cuentas (`plan_de_cuentas`) hacia metadata Beancount, pero **no puede apagar Supabase** porque:

- `GET /api/v1/bank-accounts/` → `list_bank_accounts()` → `SupabaseRepository().list_bank_accounts()` lee de la tabla Supabase `bank_accounts` (con join a `plan_de_cuentas`).
- Lo consume una **vista activa**: `CartolaUploadPage` (dropdown de cuenta bancaria para subir cartola PDF — [bankAccounts.ts:14-21](../../frontend/src/services/bankAccounts.ts#L14-L21), [CartolaUploadPage.tsx:28-29](../../frontend/src/pages/CartolaUploadPage.tsx#L28-L29)).
- `create_bank_account` valida `account_number` contra la tabla `plan_de_cuentas` de Supabase y escribe a `bank_accounts`.

**La fuente ya existe en Beancount.** El modelo unificado de Story 9.1 (`architecture-c4.md` §2.5) puso toda la metadata bancaria en los `open` de `accounts.beancount`:

```beancount
2020-12-31 open Assets:EAG:Bancos:BancoBci10160175-111005 CLP
  code: "111005"
  laudus_account_name: "Banco BCI - 10160175"
  laudus_categoria1: "ACTIVO EAG"
  ...
  bank_account_id: "d844c24e-e5da-41c6-8734-039424f13613"
  bank_name: "BCI"
  bank_account_type: "cta_corriente"
  bank_account_currency: "CLP"
```

Falta sólo el **wiring del endpoint** a esa fuente. El importer de cartolas (9.6a `BankAccountResolver`) **ya lee `accounts.beancount`** (no Supabase), así que el patrón de lectura existe.

**Por qué depende de 10.3:** la mitad de **escritura** (`POST`/`PATCH`) es conceptualmente la **misma operación que la promoción de cuentas de 10.3** (escribir `open` + metadata al ledger con `lock` + `git_commit_push` + `bean-check`). No se construye esa máquina dos veces — 9.14 reusa el endpoint/helper de escritura de 10.3.

**Decisión de scope (heredada de la verificación de 9.11):** apagar Supabase es el payoff de esta story, no de 9.11. Camino crítico: **9.11 → 10.3 → 9.14 → apagar Supabase.**

## Acceptance Criteria

**AC1 — Lectura de bank-accounts desde Beancount (mitad independiente)**

**Given** la metadata bancaria vive en los `open` de `accounts.beancount` + `manual/*.beancount`
**When** se llama `GET /api/v1/bank-accounts/`
**Then** la respuesta se arma desde el `LedgerService` (entries del ledger), no desde `SupabaseRepository`, con el mapeo:
- `id` ← `bank_account_id` (metadata)
- `account_number` ← `code`
- `account_name` ← `laudus_account_name`
- `account_type` ← `bank_account_type`
- `account_currency` ← `bank_account_currency`
- `bank_name` ← `bank_name`
- `active` ← `true` si la cuenta tiene `open` y no tiene `close`; `false` si tiene `close`
**And** el shape JSON es **idéntico** al actual (mismo `BankAccount` schema — el frontend no distingue)
**And** sólo se devuelven cuentas que tienen metadata bancaria (las que hoy están en `bank_accounts`, i.e. tipo banco/TC/línea/inversión), no todo el plan de cuentas

---

**AC2 — `CartolaUploadPage` sigue funcionando idéntico (regression)**

**Given** AC1 implementado
**When** el contador abre `CartolaUploadPage`
**Then** el dropdown de cuentas bancarias carga las mismas cuentas que antes (mismo orden por `account_number`, mismo `account_name` visible)
**And** la subida de una cartola PDF a una cuenta seleccionada funciona end-to-end sin Supabase
**And** test de regresión que verifica el shape de `GET /bank-accounts/` contra un ledger fixture

---

**AC3 — Escritura de bank-accounts reusa la máquina de 10.3 (`POST`/`PATCH`)**

**Given** Story 10.3 entregó el endpoint/helper de promoción (escribe `open` + metadata a `manual/` con `lock` + `bean-check` + `git_commit_push`)
**When** se llama `POST /api/v1/bank-accounts/` (crear) o `PATCH /api/v1/bank-accounts/{id}` (editar `bank_name` / desactivar)
**Then** la escritura va al ledger Beancount reusando esa máquina:
- `POST` → escribe un `open` con la metadata bancaria a `manual/*.beancount` (mismo path que la promoción)
- `PATCH` con `active=false` → escribe un `close` para esa cuenta
- `PATCH` con `bank_name` → actualiza la metadata del `open`
**And** `bean-check` corre antes de commitear (NO-NEGOCIABLE); rollback si falla
**And** RBAC sin cambios: `contador`/`admin` escriben, `family` lee (igual que el router actual, [bank_accounts/router.py](../../backend/app/api/v1/bank_accounts/router.py))
**And** la validación de "account_number existe en el plan" pasa a chequear contra `accounts.beancount` (no contra la tabla Supabase `plan_de_cuentas`)

---

**AC4 — `SupabaseRepository` queda sin consumidores vivos de bank_accounts/plan_de_cuentas**

**Given** AC1–AC3 implementados
**When** se audita el backend
**Then** ningún endpoint servido a una vista activa lee/escribe las tablas Supabase `bank_accounts` ni `plan_de_cuentas`
**And** los métodos `list_bank_accounts` / `get_bank_account_by_id` / `create_bank_account` / `update_bank_account` / `plan_de_cuentas_exists` / `list_plan_de_cuentas` de `SupabaseRepository` quedan sin caller en runtime (se pueden marcar deprecados; eliminarlos es opcional/limpieza)
**And** se verifica que el importer de cartolas (9.6a) ya no dependa de Supabase para resolver cuentas (usa `BankAccountResolver` sobre `accounts.beancount` — confirmar)

---

**AC5 — Apagar Supabase standby + cerrar Story 4.0**

**Given** AC1–AC4 pasaron y el smoke confirma que la app funciona sin Supabase
**When** Ary apaga el proyecto Supabase standby (acción manual fuera de CI)
**Then** la app sigue funcionando: dashboards, reporte, carga de cartolas, registry de bank-accounts — todo desde Beancount
**And** se documenta el apagado en MEMORY (reference) + se marca Story 4.0 como sunk-cost cerrado
**And** las env vars de Supabase (`SUPABASE_URL`, `SUPABASE_KEY`, etc.) se pueden remover de Render (documentar cuáles)

---

**AC6 — Rollback documentado**

**Given** algo se rompe post-migración
**When** se decide rollback
**Then** el runbook lista: revertir el wiring del endpoint a `SupabaseRepository` + (si se apagó) reactivar Supabase standby + restaurar env vars
**And** es ejecutable en < 30 minutos

---

## Tasks / Subtasks

- [x] **Task 1: Lectura desde Beancount (AC1, AC2)**
  - [x] Reescribir `list_bank_accounts()` para leer del `LedgerService` en vez de `SupabaseRepository`
  - [x] `BankAccount.from_ledger_open()` extrae los campos de los `open` con `bank_account_id`; `active` se deriva de open/close
  - [x] Orden por `account_number` (= `code`)
  - [x] Test de regresión: shape de `GET /bank-accounts/` contra ledger fixture (el shape JSON no cambió → `CartolaUploadPage` no se toca)

- [x] **Task 2: Escritura reusando 10.3 (AC3)**
  - [x] `create_bank_account` → **agrega metadata al `open` existente** (modelo unificado: la cuenta ya está en el plan; appendear un open nuevo duplicaría → bean-check rojo) vía `apply_to_accounts` (lock + bean-check + git). Destino = `accounts.beancount` (Camino A de 10.3, NO `manual/` — alineado a D1)
  - [x] `update_bank_account`: `active=false` → `close`; `active=true` → quita el `close`; `bank_name` → edita metadata del `open`
  - [x] Validación "account_number en el plan" → contra `accounts.beancount` (reemplaza `plan_de_cuentas_exists`); 409 si ya está registrada
  - [x] RBAC sin cambios (contador/admin escriben; family lee)
  - [x] Tests de create/update/close/reopen/bank_name contra ledger fixture (bean-check verde, sin duplicar el open)

- [x] **Task 3: Auditar y deprecar consumidores Supabase (AC4)**
  - [x] Grep de callers en runtime: el ÚNICO consumidor vivo (bank-accounts) migró. `plan_de_cuentas/service.py` aún referencia Supabase pero son endpoints legacy sin vista activa (deprecados en 9.11)
  - [x] Confirmado: `BankAccountResolver` (9.6a) ya lee `accounts.beancount`, no Supabase
  - [x] Métodos de bank-accounts de `SupabaseRepository` marcados deprecados (sin borrar)

- [~] **Task 4: Apagar Supabase + docs (AC5, AC6)**
  - [x] Runbook de rollback: `docs/rollback-bank-accounts-beancount.md` (< 30 min)
  - [ ] **Handoff a Ary (manual, AC5):** smoke prod sin Supabase + apagar proyecto standby + remover env vars `SUPABASE_URL`/`SUPABASE_KEY` de Render + desinstalar `supabase==2.5.0` + documentar en MEMORY + cerrar Story 4.0 sunk-cost. **No codeable — fuera del alcance del dev-story.**

---

## Dev Notes

### Estado actual del subsistema (leído 2026-06-17 — preservar comportamiento)

- **`BankAccount` schema** ([bank_accounts/schemas.py](../../backend/app/api/v1/bank_accounts/schemas.py)): `id` (UUID), `account_number`, `account_type` (`tarjeta_credito|cta_corriente|linea_credito|cta_inversiones`), `account_currency` (`CLP|USD`), `bank_name`, `active`, `account_name` (joined). `from_supabase()` arma desde el row con join. Hay que escribir un equivalente `from_ledger_open()`.
- **Service** ([bank_accounts/service.py](../../backend/app/api/v1/bank_accounts/service.py)): `list_bank_accounts` (Supabase), `create_bank_account` (valida vs `plan_de_cuentas_exists` + insert), `update_bank_account`.
- **Router** ([bank_accounts/router.py](../../backend/app/api/v1/bank_accounts/router.py)): `GET /` (cualquier user), `POST /` + `PATCH /{id}` (require_role `contador`/`admin`). **El RBAC no cambia.**
- **Repo** ([supabase_repository.py:106-151](../../backend/app/repositories/supabase_repository.py#L106-L151)): `list_bank_accounts` hace `select("*, plan_de_cuentas(account_name)")` ordenado por `account_number`. Hay también `get_active_bank_accounts_for_account_number` (línea ~155) — verificar si lo usa el importer de cartolas o si ya migró a beancount.
- **Frontend** ([bankAccounts.ts](../../frontend/src/services/bankAccounts.ts)): solo `listBankAccounts` (GET) se consume, desde `CartolaUploadPage`. **No hay consumidor frontend de `POST`/`PATCH` hoy** — son del flujo de admin/contador.
- **Fuente Beancount** (`accounts.beancount`, modelo unificado 9.1): los `open` de cuentas bancarias llevan `bank_account_id`, `bank_name`, `bank_account_type`, `bank_account_currency` además del `code`/`laudus_account_name`. `LedgerService` ([ledger_service.py]) ya expone `entries()` para leerlos.

### Por qué la escritura espera a 10.3

10.3 construye el endpoint de **promoción de cuentas pendientes**: escribir `open` + metadata `laudus_categoria*` a `manual/*.beancount`, reusando `lock` (`.import.lock`) + `bean_check` + `git_commit_push` (Story 9.4/9.0). Crear/editar una bank-account es la misma primitiva (escribir/cerrar un `open` con metadata). 9.14 Task 2 reusa ese helper; por eso `depends_on: 10.3`. La **lectura (Task 1) es independiente** y se puede hacer apenas haya capacidad — no necesita 10.3.

### Out of scope

- **Auto-detección de cuenta desde el PDF** (Story 9.5b — last4) — distinta capability; 9.5b lee `accounts.beancount` directo, no este endpoint.
- **Borrar físicamente los métodos de `SupabaseRepository`** — se marcan deprecados; la limpieza es opcional.
- **Migrar otras tablas Supabase** si quedara alguna (auditar en Task 3; el objetivo es que no quede consumidor vivo).

### Auditoría de consumidores Supabase (read-only, 2026-06-17)

Barrido completo del backend/frontend/pipeline para saber exactamente qué bloquea apagar Supabase:

- **Chokepoint único:** TODO acceso a Supabase pasa por `SupabaseRepository` ([supabase_repository.py](../../backend/app/repositories/supabase_repository.py)). Cero uso directo del client (`create_client`/`.table(`) fuera de esa clase, en backend, frontend, pipeline o scripts. Migrar = reescribir una sola clase de consumidores.
- **Cartola pipeline YA desacoplado (confirma AC4):** `BankAccountResolver` ([bank_account_resolver.py](../../pipeline/importers/bank_account_resolver.py)) lee `bank_account_id`/`bank_account_type`/etc. de los `Open` de `accounts.beancount`, NO de Supabase. Ningún path de cartola toca Supabase.
- **`POST`/`PATCH /bank-accounts/` NO tienen consumidor frontend** — solo `GET` (vía `CartolaUploadPage`). La mitad de escritura no rompe ninguna vista; es de admin/contador por API.
- **`GET`/`POST /plan-de-cuentas/*` sin consumidor frontend** — se deprecan en 9.11 (documental).
- **Métodos muertos (sin caller en runtime, safe deprecar):** `get_active_bank_accounts_for_account_number`, `upsert_records`, `replace_records`.
- **El reporte NO consume Supabase:** su fallback (`USE_BEANCOUNT_ENGINE_LEDGER=false`) lee **Sheets** vía `get_repository`/`DataRepository`, no Supabase. Irrelevante para apagar Supabase.
- **`bootstrap/sources.py`** (generate_accounts) lee Supabase one-time → DR-only, ya cubierto por la deprecación de 9.11 AC3.
- **Env vars a remover al apagar Supabase:** `SUPABASE_URL`, `SUPABASE_KEY` (leídas en [supabase_repository.py:23-24], documentadas en `.env.example:48-49`; **no están en `render.yaml`** → se setean a mano en el dashboard de Render). Además desinstalar `supabase==2.5.0` de `backend/requirements.txt`.

**Verdict:** tras la deprecación documental de 9.11 (plan-de-cuentas), el ÚNICO consumidor runtime que realmente exige Supabase es **bank-accounts (GET LIVE + POST/PATCH)** — exactamente el scope de esta story. Confirma el plan.

### Riesgos

- **`active` en Beancount — RIESGO CONCRETO (verificado):** hoy hay **CERO directivas `close`** en todo `ledger/` y el flag `active` es un constructo **solo-Supabase**. Si derivamos `active` de `open`/`close` sin más, TODAS las cuentas quedarían `active=true` post-migración. **Acción para 9.14 (Task 1/3):** antes de apagar Supabase, consultar la tabla viva `bank_accounts` por filas con `active=false`; por cada una, emitir una directiva `close` en `accounts.beancount`/`manual/` para preservar el estado. Es una captura de datos one-time.
- **`bank_account_id` (UUID) estabilidad:** el `id` del schema debe seguir siendo el UUID generado en bootstrap 9.1 (`bank_account_id`), no regenerarse — `CartolaUploadPage` y `cartola_batches.account_name`/routing pueden referenciarlo.
- **Orden de tasks:** Task 1 (lectura) desbloquea el dropdown sin Supabase pero NO permite apagar Supabase si `create/update` siguen escribiendo ahí; Supabase recién se apaga tras Task 2 + Task 3 (AC4).

### Project Structure Notes

```
backend/app/api/v1/bank_accounts/
  service.py        # MODIFY (lectura desde LedgerService; escritura vía helper 10.3)
  schemas.py        # MODIFY (agregar from_ledger_open())
  router.py         # sin cambios (RBAC igual)
backend/app/repositories/
  supabase_repository.py   # MODIFY (marcar deprecados los métodos sin caller)
backend/app/services/
  ledger_service.py        # READ (entries() ya existe)
  <helper de promoción 10.3>  # REUSE (escritura)
docs/
  rollback-bank-accounts-beancount.md   # NEW (AC6)
```

### References

- [Source: 9-11-deprecation-sheets.md — Riesgos: "Apagar Supabase standby — BLOQUEADO"] (origen de esta story)
- [Source: adr-001-plan-de-cuentas-beancount-source-of-truth.md §2 — promoción = 10.3, reusa lock/git/bean-check]
- [Source: architecture-c4.md §2.5 — bank accounts: metadata en accounts.beancount, modelo unificado]
- [Source: 9-1-bootstrap-historico-beancount.md AC2 — metadata bancaria en el open (bank_account_id, etc.)]
- [Source: 9-2-backend-thin-api-bql.md AC8 — registries quedaron leyendo Supabase a propósito (deuda que esta story salda)]
- [Source: backend/app/api/v1/bank_accounts/* + repositories/supabase_repository.py:106-151 — estado actual]
- [Source: frontend/src/pages/CartolaUploadPage.tsx + services/bankAccounts.ts — único consumidor vivo (GET)]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Amelia / dev-story)

### Debug Log References

- `test_bank_accounts.py` reescrito (mocks Supabase → ledger fixture): **13 passed**.
- Suite backend completa: **528 passed / 1 xfailed / 1 failed**. El rojo es el pre-existente
  date-dependiente `test_sync.py::test_run_backfill_calls_upsert_for_both_sheets` (sin relación).
  El delta de conteo vs corridas previas (531→528) es por el rewrite del test file (menos casos,
  más enfocados), no por regresiones.
- 10.3 (`test_cuentas_pendientes.py`) sigue **14 passed** tras refactorizar el helper compartido.

### Completion Notes List

- **Decisión técnica clave (mía):** en el modelo unificado 9.1 las bank-accounts YA tienen su
  `open` en `accounts.beancount`. Por eso **crear = agregar metadata al open existente**
  (`add_meta_to_open`), no appendear un open nuevo (duplicaría → bean-check rojo). La story AC3
  asumía "escribe un open a `manual/`"; lo alineé a **Camino A** (escribir a `accounts.beancount`),
  consistente con la resolución D1 de 10.3.
- **Helper compartido generalizado:** extraje de `promote_account` (10.3) el core
  `apply_to_accounts(mutate, msg, ...)` (lock + bean-check + rollback + git) y agregué editores de
  bloque `open` (`add_meta_to_open`, `set_open_meta`, `append_close`, `remove_close`,
  `format_open`). 10.3 quedó intacto en comportamiento (14/14 verde). 9.14 reusa todo eso — la
  "máquina de escritura" se construyó una sola vez (objetivo de la dependencia 10.3→9.14).
- **AC1 lectura:** `GET /bank-accounts/` arma `BankAccount` desde los `open` con `bank_account_id`
  (subset bancario del plan), `active` derivado de open/close, orden por `code`. Shape JSON
  idéntico → `CartolaUploadPage` no se toca (AC2).
- **AC3 escritura:** `POST` agrega metadata (400 si el code no está en el plan, 409 si ya es
  bank-account, UUID nuevo generado); `PATCH active=false` → `close`, `active=true` → quita el
  close, `bank_name` → edita metadata. bean-check NO-NEGOCIABLE con rollback (422). RBAC sin cambios.
- **AC4:** único consumidor vivo de Supabase (bank-accounts) migrado; `BankAccountResolver` (9.6a)
  ya estaba en Beancount; métodos de bank-accounts de `SupabaseRepository` marcados deprecados (sin
  borrar). Los endpoints `plan-de-cuentas` siguen referenciando Supabase pero son legacy sin vista
  activa (deprecados en 9.11).
- **`active` (riesgo verificado):** hoy hay CERO `close` en el ledger → toda cuenta migrada arranca
  `active=true`. El runbook documenta la captura one-time de las inactivas (vía PATCH active=false)
  antes de apagar Supabase.
- **HANDOFF a Ary (AC5, no codeable):** smoke prod sin Supabase → apagar proyecto standby → remover
  env vars `SUPABASE_URL`/`SUPABASE_KEY` de Render (no están en `render.yaml`) → desinstalar
  `supabase==2.5.0` → documentar en MEMORY → cerrar Story 4.0 sunk-cost. Rollback en
  `docs/rollback-bank-accounts-beancount.md` (< 30 min).

### File List

**Modificados (backend):**
- `backend/app/api/v1/bank_accounts/service.py` — lee/escribe Beancount (antes Supabase)
- `backend/app/api/v1/bank_accounts/router.py` — inyecta `LedgerService` (RBAC sin cambios)
- `backend/app/api/v1/bank_accounts/schemas.py` — `from_ledger_open()` (+ `from_supabase` deprecado)
- `backend/app/services/beancount_promote.py` — generalizado: `apply_to_accounts` + editores de bloque `open`
- `backend/app/repositories/supabase_repository.py` — métodos de bank-accounts marcados deprecados
- `backend/tests/test_bank_accounts.py` — reescrito sobre ledger fixture (13 tests)

**Nuevos (docs):**
- `docs/rollback-bank-accounts-beancount.md` — runbook de rollback (AC6)

## Change Log

| Fecha | Cambio |
|---|---|
| 2026-06-17 | 9.14: bank-accounts lee/escribe Beancount (no Supabase). Helper 10.3 generalizado y reusado. 13 tests. AC5 (apagar Supabase) = handoff a Ary. Status → review. |
| 2026-06-17 | Code review 3 capas (Auditor PASS) → 2 patches aplicados (POST/PATCH manejan LockTimeout→409 y CalledProcessError→502 espejando 10.3, antes daban 500 + se perdía la escritura; toggle de active idempotente = no duplica close) + 3 tests nuevos (621 suite, 0 regresiones, 10.3 intacto). 5 defers. Status → done. |

### Review Findings

Code review 3 capas (Blind Hunter + Edge Case Hunter + Acceptance Auditor), 2026-06-17. Verificado contra código real (líneas de las capas alucinadas; corregidas abajo). Auditor: PASS (los 6 ACs satisfechos; la desviación Camino A es la decisión correcta). AC5 (apagar Supabase) + captura one-time de `active=false` = handoffs declarados a Ary, no defectos.

- [x] [Review][Patch] POST/PATCH solo capturan `PromoteError` → `LockTimeout` y `CalledProcessError` dan 500 + se pierde la escritura [bank_accounts/service.py:96,135] — Blind y Edge convergieron. El consumidor hermano 10.3 ([cuentas_pendientes/router.py:103-122]) maneja `LockTimeout`→409 y `CalledProcessError`(push falla tras bean-check OK)→degradación con aviso. Acá propagan como 500 con stacktrace, y el commit local (ya escrito + bean-check verde) se descarta en el próximo `git reset --hard` del refresh — sin señal al usuario. Fix: espejar el patrón de 10.3 (LockTimeout→409; CalledProcessError→error claro 502 "escritura local persiste, push falló, reintentá", NO enmascarar como éxito).
- [x] [Review][Patch] PATCH `active=false` sobre una cuenta ya cerrada → `close` duplicado → bean-check rojo → 422 opaco [bank_accounts/service.py:121-126] — `append_close` agrega un segundo `close` incondicionalmente; beancount da "Duplicate close" → rollback → 422 "bean-check falló". Seguro (rollback) pero confuso, y el `closed` set ya se conoce. Pasa con la captura one-time de inactivas (AC5 handoff) o un doble click. Fix: toggle idempotente — solo `append_close` si no está cerrada, solo `remove_close` si lo está.
- [x] [Review][Defer] create no puede setear `bank_account_last4` → cuentas nuevas con last4=None pueden romper el matching de cartola [bank_accounts/service.py:80-87] — deferred; `BankAccountResolver` lee `bank_account_last4` para el matching; una cuenta registrada por este endpoint queda sin él (se puebla vía Fava, 9.3). Fuera del schema 9.14 pero gap real.
- [x] [Review][Defer] create/update sin re-check bajo el lock (TOCTOU) → el 409 "ya registrada" se evalúa sobre el snapshot in-memory [bank_accounts/service.py:64-78,110-114] — deferred; en Render single-instance/single-worker el lock serializa; con multi-worker o cron concurrente el guard podría bypassearse (dup `bank_account_id`). Hardening de concurrencia.
- [x] [Review][Defer] orden lexicográfico de `account_number` + line blanca acumulada en ciclos close/reopen + bank_name no reseteable a null [bank_accounts/service.py:54, beancount_promote.py append/remove_close, service.py:119] — deferred; cosméticos/menores (codes uniformes → lexi==numérico, == orden Supabase previo).
