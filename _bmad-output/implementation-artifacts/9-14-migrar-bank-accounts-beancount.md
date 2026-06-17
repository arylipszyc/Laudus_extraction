---
story: 9.14
title: Migrar bank-accounts a Beancount + apagar Supabase
status: ready-for-dev
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

- [ ] **Task 1: Lectura desde Beancount (AC1, AC2)**
  - [ ] Reescribir `list_bank_accounts()` ([bank_accounts/service.py:12](../../backend/app/api/v1/bank_accounts/service.py#L12)) para leer del `LedgerService` en vez de `SupabaseRepository`
  - [ ] Helper que extraiga, de los `open` con metadata `bank_account_id`, los campos del schema `BankAccount`; derivar `active` de open/close
  - [ ] Mantener orden por `account_number` (= `code`)
  - [ ] Test de regresión: shape de `GET /bank-accounts/` contra ledger fixture; smoke de `CartolaUploadPage` (dropdown carga igual)

- [ ] **Task 2: Escritura reusando 10.3 (AC3)** *(bloqueada hasta 10.3 done)*
  - [ ] `create_bank_account` → escribe `open`+metadata a `manual/` vía el helper de promoción de 10.3 (lock + bean-check + git)
  - [ ] `update_bank_account`: `active=false` → `close`; `bank_name` → editar metadata del `open`
  - [ ] Validación "account_number en el plan" → contra `accounts.beancount` (reemplaza `plan_de_cuentas_exists`)
  - [ ] RBAC sin cambios (contador/admin escriben)
  - [ ] Tests de create/update contra ledger fixture (bean-check verde, idempotencia)

- [ ] **Task 3: Auditar y deprecar consumidores Supabase (AC4)**
  - [ ] Grep de callers en runtime de `SupabaseRepository.{list_bank_accounts,get_bank_account_by_id,create_bank_account,update_bank_account,plan_de_cuentas_exists,list_plan_de_cuentas}`
  - [ ] Confirmar que el importer de cartolas (9.6a `BankAccountResolver`) ya no usa Supabase
  - [ ] Marcar deprecados los métodos sin caller (eliminación = limpieza opcional)

- [ ] **Task 4: Apagar Supabase + docs (AC5, AC6)**
  - [ ] Smoke completo sin Supabase (dashboards + reporte + carga de cartolas + bank-accounts)
  - [ ] **Handoff a Ary (manual):** apagar proyecto Supabase standby; remover env vars de Render (documentar)
  - [ ] Documentar apagado en MEMORY + cerrar Story 4.0 sunk-cost
  - [ ] Runbook de rollback

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

### Debug Log References

### Completion Notes List

### File List
