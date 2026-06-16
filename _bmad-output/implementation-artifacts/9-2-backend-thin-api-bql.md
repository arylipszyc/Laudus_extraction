---
story: 9.2
title: Backend thin API con BQL endpoints (F1)
status: review
epic: 9
depends_on: [9.1]
blocks: [9.8]
---

# Story 9.2 — Backend thin API con BQL endpoints

## User Story

As the LAUDUS frontend (and any future API consumer),
I want all Phase 1+2 endpoints (balance-sheets, ledger-entries, income-statement, equity-variation, sync status, cartolas, plan-de-cuentas, bank-accounts) to read from the Beancount ledger via BQL queries instead of Supabase/Sheets,
So that the frontend continues to work without visual regression while the source of truth migrates to `ledger/`.

## Context

F1 del plan de migración (`architecture-c4.md` §7.2 + §5). El backend actual lee del Sheets (vía `SheetsRepository`) y del Supabase (registries). Esta story:

- Implementa `LedgerService` que carga `ledger/main.beancount` en memoria con file watcher (§5.1).
- Reescribe los endpoints de dashboard (`/api/v1/balance-sheets`, `/ledger-entries`, `/income-statement`, `/equity-variation`) para usar BQL queries en lugar de Sheets.
- Agrega un feature flag `USE_BEANCOUNT_ENGINE` para coexistencia durante migración (Sheets fallback).
- Preserva los endpoints de registry (plan-de-cuentas, bank-accounts) que siguen leyendo de Supabase.
- NO toca el sync trigger (eso es Story 9.4) ni los endpoints de cartolas (eso es Story 9.5/9.6).

## Acceptance Criteria

**AC1 — `LedgerService` singleton con file watcher**

**Given** `backend/app/services/ledger_service.py` existe
**When** el backend inicia
**Then** `LedgerService` es instanciado como singleton (vía DI o módulo-level), apunta a `LEDGER_PATH` (env var, default `./ledger/main.beancount`)
**And** lazy-loads en la primera request (`beancount.loader.load_file`)
**And** un file watcher (`watchfiles.awatch`) corre en background y dispara `load()` cuando algún `.beancount` en `ledger/` cambia
**And** errores de carga (`bean-check` errors) se loguean pero no crashean el backend — el endpoint que necesita ledger devuelve HTTP 503 con `{"error": {"code": "LEDGER_UNAVAILABLE", "message": "Ledger has parse errors", "detail": "..."}}`

---

**AC2 — Feature flag `USE_BEANCOUNT_ENGINE` granular**

**Given** las env vars `USE_BEANCOUNT_ENGINE_BALANCE_SHEET`, `USE_BEANCOUNT_ENGINE_LEDGER`, `USE_BEANCOUNT_ENGINE_INCOME_STATEMENT`, `USE_BEANCOUNT_ENGINE_EQUITY_VARIATION` (default `false` en cada una)
**When** un endpoint de dashboard se llama
**Then** si la flag correspondiente es `true` → lee del ledger via BQL
**And** si es `false` → lee del Sheets como antes (path actual sin cambios)
**And** la respuesta JSON tiene la **misma forma exacta** en ambos paths (mismo snake_case, mismas keys, mismo orden de records, mismo ISO 8601, mismas redondeos) — el frontend NO distingue

---

**AC3 — `GET /api/v1/balance-sheets`**

**Given** `entity` y `date_range` query params + flag activa
**When** el endpoint se llama
**Then** internamente corre BQL: `SELECT account, sum(position) AS balance FROM HAS_ACCOUNT("Assets|Liabilities|Equity") AT {date_range.end} WHERE account ~ "^Assets:{entity}|^Liabilities:{entity}|^Equity:{entity}" GROUP BY account`
**And** transforma el resultado a la misma shape JSON que devuelve hoy desde Sheets (mismo schema)
**And** response time < 3s para entity + año completo (NFR1)

---

**AC4 — `GET /api/v1/ledger-entries`**

**Given** `entity`, `date_range`, opcional `account` query params + flag activa
**When** el endpoint se llama
**Then** internamente corre BQL: `SELECT date, account, narration, position FROM CLOSED_ON ... WHERE date >= {start} AND date <= {end} AND account ~ "{entity_pattern}" {AND account = {account}}` ordenado por date desc
**And** todos los amounts se devuelven como `float` (no string)
**And** las fechas se devuelven como ISO 8601

---

**AC5 — `GET /api/v1/income-statement`**

**Given** `entity` + `date_range` + flag activa
**When** el endpoint se llama
**Then** corre BQL income statement: total Income por cuenta + total Expenses por cuenta + net result, todo filtrado por entity + date range
**And** la respuesta sigue la misma estructura jerárquica que `IncomeStatementPage.tsx` espera hoy desde Sheets
**And** este endpoint reemplaza el render local actual del frontend (que hoy calcula income statement client-side con datos de ledger-entries)

---

**AC6 — `GET /api/v1/equity-variation`**

**Given** `entity` + `date_range` + flag activa
**When** el endpoint se llama
**Then** corre BQL para devolver `Equity:{entity}:*` balances at each period boundary in the range (pre-period vs post-period equity, agrupado mes a mes)
**And** la respuesta tiene mismo shape que `EquityVariationPage.tsx` espera hoy

---

**AC7 — Endpoints `sync/status` adaptados**

**Given** `GET /api/v1/sync/status`
**When** el endpoint se llama
**Then** lee `ledger/_meta/import-log.jsonl` (último run del importer Laudus + del importer cartolas) en lugar de la tabla actual
**And** la respuesta mantiene el shape actual: timestamps ISO 8601 por data type
**And** `last_sync_balance_sheet` y `last_sync_ledger` se derivan del mismo run (no hay sync separados bajo c4 — Laudus importer hace ambos en una pasada)

---

**AC8 — Registries preservados sin cambios funcionales**

**Given** `GET /api/v1/plan-de-cuentas/`, `GET /api/v1/bank-accounts/`, `POST /api/v1/bank-accounts/`, `PATCH /api/v1/bank-accounts/{id}`
**When** se llaman
**Then** el comportamiento es idéntico al de Story 4.0 (siguen leyendo de Supabase)
**And** los tests de Story 4.0 que cubrían estos endpoints siguen pasando sin modificación

---

**AC9 — Tests de paridad Sheets ↔ Beancount**

**Given** un set de fixtures (entity, date_range) sintéticos pero realistas (al menos: full-year EAG 2024, Q1 2025 EAG, full-year Jocelyn 2024)
**When** los tests corren con `USE_BEANCOUNT_ENGINE_*=true` y comparan vs `=false`
**Then** la respuesta JSON es **estructuralmente idéntica** (mismas keys, mismo orden, mismas dates) — los amounts pueden diferir si la migración descubrió bugs en Sheets, pero la SHAPE no
**And** discrepancias > 0 en amounts se loguean en el test output con detalle (cuenta, valor Sheets, valor Beancount, diff)
**And** el test es declarativamente xfail o documentado en `tests/README-beancount-parity.md` mientras Q4 + bootstrap full no estén ejecutados

---

**AC10 — RBAC sin cambios**

**Given** todos los endpoints de dashboard
**When** se acceden
**Then** `get_current_user()` se aplica como antes; `family` (ex `owner`) y `contador` ambos leen; ningún endpoint trusta role del cliente

---

## Tasks / Subtasks

- [x] Task 1: `LedgerService` (AC1)
  - [x] Crear `backend/app/services/ledger_service.py` (adaptado: load síncrono bajo lock — patrón `bank_account_index` — + watcher async, ver Completion Notes)
  - [x] Inyectar via DI (FastAPI dependency `get_ledger_service`) — singleton de proceso (`@lru_cache`)
  - [x] Background task para `watch_and_reload` (FastAPI lifespan en `main.py`)
  - [x] Manejar errores de `loader.load_file`: log + `available` property; consumidores levantan `LedgerUnavailableError` → 503
  - [x] Test unitario: load → entries no vacío; reload tras change → entries actualizados; load con archivo roto → unavailable + raise
  - [x] Env var `LEDGER_PATH` (default `<repo>/ledger/main.beancount`)

- [x] Task 2: Feature flags granulares (AC2)
  - [x] Definir env vars `USE_BEANCOUNT_ENGINE_*` en `.env.example` con default `false` (BALANCE_SHEET, LEDGER, SYNC_STATUS activos; INCOME_STATEMENT/EQUITY_VARIATION reservados — AC5/AC6 deferred)
  - [x] Selector en `backend/app/api/v1/dashboard/service.py` (ruta real; no existe `services/dashboard_service.py`): `get_balance_sheets`/`get_ledger_entries` rutean a BQL vs Sheets según flag

- [x] Task 3: BQL queries para los dashboards (AC3-AC4; **AC5/AC6 deferred** — ver Completion Notes)
  - [x] `backend/app/services/bql_queries.py` con funciones puras `(LedgerService, entity, date_range) → JSON` (balance_sheet + ledger_entries)
  - [x] Usar `beanquery.connect("beancount:", entries=…)` sobre los entries cargados
  - [x] Validar shape contra los modelos Pydantic actuales (parity suite estructural)
  - [x] Cache: omitido — BQL sobre el ledger actual responde < 200ms (la story lo permite explícitamente)

- [x] Task 4: `sync/status` desde JSONL (AC7)
  - [x] Leer `ledger/_meta/import-log.jsonl` (último run `laudus`) — gated por `USE_BEANCOUNT_ENGINE_SYNC_STATUS` para no romper los tests Sheets de Story 2.x
  - [x] Parsear timestamp; `balance_sheet` y `ledger` last_sync derivan del mismo run Laudus (single-pass c4)
  - [x] Si el archivo no existe (pre-bootstrap): `null` por data type

- [x] Task 5: Tests de paridad (AC9)
  - [x] Crear `backend/tests/test_beancount_parity.py` + `README-beancount-parity.md`
  - [x] Fixtures: mini-ledger sintético (el ledger real aún no está bootstrapeado — importer Laudus es 9.4)
  - [x] Parity estructural (keys/modelo) corre ahora; parity de montos vs Sheets queda `xfail` documentado hasta 9.4
  - [x] Marcado `@pytest.mark.beancount_parity` (registrado en `conftest.py`) para CI separado

- [x] Task 6: No tocar registries (AC8)
  - [x] Verificado: ningún cambio toca `plan_de_cuentas/` ni `bank_accounts/`
  - [x] Tests existentes de 4.0 (`test_plan_de_cuentas`, `test_bank_accounts`) siguen verdes

---

## Dev Notes

### Input autoritativo

`architecture-c4.md` §5 — diseño de endpoints. La tabla §5.2 lista mapping endpoint-actual → c4-endpoint con la implementación exacta. Esta story implementa **toda** esa tabla excepto las filas de cartolas (Story 9.5/9.6) y `transactions/category` PATCH (Story 9.7+9.8).

### LedgerService skeleton (literal del artifact)

```python
# backend/app/services/ledger_service.py
import asyncio, os
from datetime import datetime
from beancount import loader
from watchfiles import awatch

class LedgerService:
    def __init__(self, main_path: str):
        self._main_path = main_path
        self._entries = None
        self._errors = None
        self._options = None
        self._loaded_at = None
        self._lock = asyncio.Lock()

    async def load(self):
        async with self._lock:
            self._entries, self._errors, self._options = loader.load_file(self._main_path)
            self._loaded_at = datetime.utcnow()

    async def get_entries(self):
        if self._entries is None:
            await self.load()
        return self._entries

    async def watch_and_reload(self):
        async for changes in awatch(os.path.dirname(self._main_path), recursive=True):
            if any(p.endswith(".beancount") for _, p in changes):
                await self.load()
```

### BQL — runtime esperado

Ledger 2021-now con ~50K JE: load 2-4s, RAM 100-200MB. BQL queries típicas: < 200ms. Render web service single instance alcanza.

### Endpoints OUT OF SCOPE de esta story

- `POST /api/v1/sync/trigger` (Story 9.4 — importer Laudus)
- `POST /api/v1/cartolas/upload` (Story 9.5)
- `PATCH /api/v1/cartolas/{batch_id}/validate-balance` (Story 9.9)
- `GET /api/v1/categorization/pending` (Story 9.7+9.8)
- `PATCH /api/v1/transactions/{id}/category` (Story 9.7+9.8)
- `POST /api/v1/transactions/bulk-confirm` (Story 9.7+9.8)

### Project structure

```
backend/
  app/
    services/
      ledger_service.py                    # NEW
      bql_queries.py                       # NEW
      dashboard_service.py                 # MODIFY — agregar selector via flag
    api/v1/
      sync/router.py                       # MODIFY — sync/status lee del JSONL
  tests/
    test_beancount_parity.py               # NEW
    README-beancount-parity.md             # NEW
.env.example                               # MODIFY — agregar 4 USE_BEANCOUNT_ENGINE_* + LEDGER_PATH
```

### Dependencies

Agregar a `backend/requirements.txt`:
```
beancount>=3.2,<4
beanquery>=0.2
watchfiles>=0.21
```

### References

- [Source: architecture-c4.md §5 — Backend FastAPI thin]
- [Source: architecture-c4.md §7.2 — Plan F1]
- [Source: architecture-c4.md §7.8 — Riesgo de drift durante transición]
- [Source: backend/app/services/dashboard_service.py — service pattern existente]
- [Source: backend/app/api/v1/router.py — registration pattern]

---

## Dev Agent Record

### Implementation Plan

Slice pragmático acordado con Ary (2026-06-10): implementar la infraestructura del
motor Beancount + los 2 endpoints que existen hoy (balance-sheets, ledger-entries) +
sync/status, todo detrás de feature flags para coexistencia. AC5 (income-statement) y
AC6 (equity-variation) **diferidos** porque sus páginas frontend no existen aún (solo
hay `IncomeExpensesPage.tsx`) — serían endpoints net-new sin consumidor ni shape de
referencia que validar.

1. `LedgerService` (carga + watcher + 503) → verify: unit tests load/reload/broken.
2. Feature flags + selector en dashboard service → verify: flag-off = Sheets sin cambios.
3. BQL queries shape-compatibles → verify: unit tests de shape + correctitud vs mini-ledger.
4. sync/status desde JSONL (flag-gated) → verify: tests JSONL + Sheets path intacto.
5. Parity scaffold (estructural ahora, montos xfail) → verify: corre en suite.
6. Registries intactos → verify: git diff vacío en esos dirs + sus tests verdes.

### Completion Notes

**Divergencias spec ↔ repo resueltas:**
- La spec asumía `backend/app/services/dashboard_service.py` con métodos
  `get_balance_sheet_via_beancount()/_via_sheets()`. La estructura real es
  `backend/app/api/v1/dashboard/service.py`. Adapté el selector ahí mismo
  (`get_balance_sheets`/`get_ledger_entries` con param `ledger=` + chequeo de flag),
  sin crear un `services/dashboard_service.py` redundante. Sí creé el paquete
  `backend/app/services/` para `ledger_service.py` + `bql_queries.py` (cross-cutting,
  como pide la story).
- **LedgerService — carga síncrona + watcher async:** el skeleton del artifact era
  100% async (`asyncio.Lock`, `await load()`). Pero los endpoints de dashboard son
  síncronos. Seguí el precedente probado del codebase (`integrations/bank_account_index.py`:
  load síncrono bajo `threading.Lock`, usable desde endpoints sync) y agregué el
  `watchfiles.awatch` async exigido por AC1 como tarea de background en el lifespan.
  Mejor de ambos: acceso sync para los endpoints + reload proactivo ante edición externa.
- **503 LEDGER_UNAVAILABLE:** el middleware global envuelve toda `HTTPException` en
  `HTTP_<code>`, así que un `raise HTTPException(503, …)` no podía producir el body
  exacto de AC1. Solución limpia: `LedgerUnavailableError` (en `ledger_service`) +
  exception handler dedicado en `middleware.py` → body exacto `{"error":{"code":
  "LEDGER_UNAVAILABLE", …}}`. Los endpoints solo dejan propagar la excepción.

**Decisiones de diseño:**
- AC7 (sync/status desde JSONL) quedó **gated por `USE_BEANCOUNT_ENGINE_SYNC_STATUS`**.
  Sin flag rompía los tests Sheets de Story 2.1/2.2 (que esperan `null`/null vs valores
  de mock_repo). Con flag off (default) el path Sheets queda idéntico; con flag on lee
  el `import-log.jsonl`. Coherente con el principio de coexistencia de AC2.
- `balance_sheet`/`ledger` last_sync derivan del **mismo run Laudus** (`importer:"laudus"`),
  por el modelo single-pass de c4 (AC7).
- Convención de montos en BQL (best-effort): split débito/crédito por signo del balance.
  La paridad de montos real vs Sheets es `xfail` hasta el bootstrap del ledger (9.4),
  documentado en `tests/README-beancount-parity.md` (AC9). El contrato que protege al
  frontend hoy es la **paridad estructural** (keys == modelos Pydantic), que sí corre.

**ACs diferidos (decisión de scope de Ary):**
- **AC5 — `GET /api/v1/income-statement`:** NO implementado. No existe `IncomeStatementPage.tsx`.
- **AC6 — `GET /api/v1/equity-variation`:** NO implementado. No existe `EquityVariationPage.tsx`.
  Flags reservados (comentados) en `.env.example`. Retomar cuando esas páginas existan
  (o plegar a Story 9.8 frontend).

### Debug Log

- `beanquery` no estaba instalado (sí en Dev Notes). Instalado `beanquery>=0.2` +
  agregado a `requirements.txt` junto con `watchfiles>=0.21` (explícito).
- Pre-existentes detectados (NO regresiones de 9.2, confirmados contra HEAD):
  1. `test_sync.py::test_run_backfill_calls_upsert_for_both_sheets` — date-dependiente
     (`from_date=2026-04-01` → 3 EOM hasta hoy 2026-06-10; el test hardcodea `== 1`).
     Ya documentado en sprint-status como "único rojo pre-existente test_sync".
  2. `test_fava_edit_validator.py` — `ModuleNotFoundError: fava` (dep no instalada en
     venv local; Story 9.0). Se ignora localmente.

### Test Results

Suite backend (ignorando `test_fava_edit_validator.py` por dep faltante de entorno):
**434 passed, 1 xfailed, 1 failed** — el único failed es el pre-existente date-dependiente
de backfill. Tests nuevos de 9.2: 8 (ledger_service) + 13 (bql_queries) + 5
(dashboard_beancount) + 2+1xfail (parity) + 4 (sync AC7) = **32 verdes + 1 xfail**.

## File List

**Nuevos:**
- `backend/app/services/__init__.py`
- `backend/app/services/ledger_service.py`
- `backend/app/services/bql_queries.py`
- `backend/tests/test_ledger_service.py`
- `backend/tests/test_bql_queries.py`
- `backend/tests/test_dashboard_beancount.py`
- `backend/tests/test_beancount_parity.py`
- `backend/tests/README-beancount-parity.md`
- `backend/tests/conftest.py`

**Modificados:**
- `backend/app/api/v1/dashboard/router.py` — inyecta `get_ledger_service`, pasa `ledger=`
- `backend/app/api/v1/dashboard/service.py` — selector flag Sheets↔BQL
- `backend/app/api/v1/sync/service.py` — sync/status desde import-log.jsonl (AC7, flag-gated)
- `backend/app/dependencies.py` — `get_ledger_service` singleton
- `backend/app/middleware.py` — handler `LedgerUnavailableError` → 503
- `backend/main.py` — lifespan que arranca el ledger watcher
- `backend/requirements.txt` — `beanquery>=0.2`, `watchfiles>=0.21`
- `.env.example` — `LEDGER_PATH` + flags `USE_BEANCOUNT_ENGINE_*`
- `backend/tests/test_sync.py` — tests AC7 (JSONL path)

## Change Log

- 2026-06-10 — Story 9.2 implementada (slice pragmático). LedgerService + file watcher,
  feature flags granulares, BQL para balance-sheets/ledger-entries, sync/status desde
  JSONL, scaffold de paridad Sheets↔Beancount. AC5/AC6 (income-statement, equity-variation)
  diferidos por ausencia de páginas frontend consumidoras. 32 tests nuevos verdes, cero
  regresiones. Status → review.
