---
story: 9.2
title: Backend thin API con BQL endpoints (F1)
status: ready-for-dev
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

- [ ] Task 1: `LedgerService` (AC1)
  - [ ] Crear `backend/app/services/ledger_service.py` con la clase del artifact §5.1
  - [ ] Inyectar via DI (FastAPI dependency) — singleton de proceso
  - [ ] Background task para `watch_and_reload` (FastAPI startup hook)
  - [ ] Manejar errores de `loader.load_file`: log + estado `unavailable` accesible vía property
  - [ ] Test unitario: load → entries no vacío; reload tras change → entries actualizados; load con archivo roto → estado unavailable
  - [ ] Env var `LEDGER_PATH` (default `ledger/main.beancount`)

- [ ] Task 2: Feature flags granulares (AC2)
  - [ ] Definir 4 env vars (`USE_BEANCOUNT_ENGINE_*`) en `.env.example` con default `false`
  - [ ] Pattern de selección en `backend/app/services/dashboard_service.py`: nuevo método `get_balance_sheet_via_beancount()` + el actual queda como `get_balance_sheet_via_sheets()`. Selector lee la flag.

- [ ] Task 3: BQL queries para los 4 dashboards (AC3-AC6)
  - [ ] `backend/app/services/bql_queries.py` con funciones puras `(LedgerService, entity, date_range) → JSON`
  - [ ] Usar `beanquery.connect("beancount://...")` o `beanquery.run_query` directamente sobre los entries cargados
  - [ ] Validar shape contra fixtures de respuesta actual de Sheets
  - [ ] Cache LRU corto (60s) si performance lo requiere — skip si BQL responde < 200ms

- [ ] Task 4: `sync/status` desde JSONL (AC7)
  - [ ] Leer `ledger/_meta/import-log.jsonl` (tail del archivo, last record por importer)
  - [ ] Parsear timestamp + records counts; respond JSON con shape actual
  - [ ] Si el archivo no existe (pre-bootstrap): respond `null` por data type (mismo shape que hoy)

- [ ] Task 5: Tests de paridad (AC9)
  - [ ] Crear `backend/tests/test_beancount_parity.py`
  - [ ] Fixtures: subset del ledger ejecutado por Story 9.1 (o un mini-ledger de prueba)
  - [ ] Tests parametrizados: para cada (entity, date_range, endpoint) → comparar JSON Sheets vs Beancount → assertEqual de structure, assertAlmostEqual de amounts
  - [ ] Marcar como `@pytest.mark.beancount_parity` para correr en CI separado

- [ ] Task 6: No tocar registries (AC8)
  - [ ] Verificar que ningún cambio toca `backend/app/api/v1/plan_de_cuentas/` o `backend/app/api/v1/bank_accounts/`
  - [ ] Tests existentes de 4.0 siguen verdes — assert en CI

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
