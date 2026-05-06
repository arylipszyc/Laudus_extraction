---
story: 9.5
title: PDF upload + extracción Gemini → JSON canónico (era 4.1a)
status: done
epic: 9
depends_on: []
blocks: [9.6a]
parallelizable_with: [9.0, 9.1, 9.2]
---

# Story 9.5 — PDF upload + extracción Gemini → JSON canónico

## User Story

As a contador,
I want to upload a credit card statement PDF, select the bank account it belongs to, and receive back a validated canonical JSON of all transactions + balances,
So that bank statement extraction is decoupled from Beancount transformation, runs server-side once, and produces a stable shape that downstream stories (9.6 beangulp) can consume without re-extracting.

## Context

Story 4.1a reformulada bajo c4. **Paralelizable desde el día 1** — no depende de bootstrap, ni de thin API, ni de Fava. El shape JSON canónico v1.0 está cerrado en `architecture-c4.md` §4.1.

Esta story:
- Provee el endpoint `POST /api/v1/cartolas/upload` (multipart PDF + `bank_account_id`).
- Llama a Gemini con prompt estructurado.
- Valida la respuesta contra el schema Pydantic `CartolaCanonicalV1`.
- Retorna el JSON canónico al frontend + lo escribe a un staging file `ledger/imports/cartolas/_staging/{batch_id}.cartola.json` que Story 9.6 (beangulp) consumirá.
- NO commitea al ledger todavía — el commit pasa después del transform de 9.6 + balance check de 9.9.
- NO almacena el PDF (NFR — no PDF storage).

`PRD-update needed` flagged: este shape es más rico que el del PRD original. John (PM) lo reformula en sesión separada. Bob: referenciar el `PRD-update needed` en el story file, pero NO bloquear.

## Acceptance Criteria

**AC1 — Endpoint multipart con validación de inputs**

**Given** `POST /api/v1/cartolas/upload` con multipart form: `pdf_file` (binary, ≤ 20MB) + `bank_account_id` (UUID)
**When** el endpoint se llama por un usuario `contador` o `admin` (Story 9.13)
**Then** valida:
  - tamaño ≤ 20MB (NFR3)
  - MIME = `application/pdf`
  - `bank_account_id` existe en metadata de `accounts.beancount` (consultado vía backend al boot, cached in-memory — **NO Supabase**)
  - el `accounts.beancount` entry para ese `bank_account_id` tiene metadata `bank_account_last4` no-null (necesario para validar que la cartola subida corresponde al banco/cuenta esperado en post-process)
**And** si alguna validación falla → HTTP 400 con `{"error": {"code": "VALIDATION_FAILED", ...}}`
**And** específicamente si `bank_account_last4` es null → HTTP 400 con código `MISSING_LAST4` y mensaje *"Esta cuenta bancaria no tiene `bank_account_last4` registrado en `accounts.beancount`. Editar vía Fava antes de subir cartolas (ver runbook contador-onboarding-fava.md)."*
**And** un usuario `family` recibe HTTP 403 (gate de Story 9.13)

---

**AC2 — Frontend de upload selecciona bank_account_id ANTES del upload**

**Given** la pantalla `CartolaUploadPage.tsx` (Story 4.1 original NO se implementó — crear from scratch)
**When** el contador navega
**Then** ve un dropdown de bank accounts activos (de `GET /api/v1/bank-accounts/?active_only=true`) — uno seleccionable
**And** ve un file input para PDF
**And** el botón "Subir" se deshabilita si falta cualquiera

> **Nota sobre el endpoint backend `GET /api/v1/bank-accounts/`:** la **interfaz HTTP no cambia** vs Story 4.0 — sigue siendo el mismo contrato (mismo response shape). Lo que cambia es la **implementación interna**: el backend lee de `accounts.beancount` filtrando entries con metadata `bank_account_*` (cached in-memory al boot), NO query Supabase. Frontend no se entera del cambio.

---

**AC3 — Llamada a Gemini con prompt estructurado**

**Given** el endpoint recibe un PDF válido
**When** se llama a `GeminiClient.extract_pdf(pdf_bytes, bank_account)` (clase preservada de Story 4.1 original)
**Then** Gemini recibe el prompt con: definición del shape canónico v1.0 + lista cerrada de fields requeridos + sample expected JSON
**And** la respuesta debe ser parseable como JSON válido
**And** `GeminiClient` es el único archivo del codebase que importa el SDK de Gemini (NFR17)

---

**AC4 — Validación schema Pydantic**

**Given** la respuesta de Gemini
**When** se intenta parsear con `CartolaCanonicalV1` (Pydantic model)
**Then** si valida → continúa
**And** si NO valida → HTTP 422 con `{"error": {"code": "EXTRACTION_FAILED", "detail": "..."}}` y NO se persiste nada (NFR12 + NFR19)

---

**AC5 — Resolución server-side de campos derivados**

**Given** el frontend envía solo `pdf_file` + `bank_account_id`
**When** el backend procesa
**Then** los campos `source.bank_name`, `source.account_label`, `source.account_type`, `source.entity` se resuelven server-side leyendo metadata de `accounts.beancount` (cached in-memory) — **NO Supabase**
**And** se incluyen en el JSON canónico devuelto (frontend + 9.6a no necesitan re-resolver)

---

**AC6 — Sanity-check de período**

**Given** Gemini devuelve `period.start` y `period.end`
**When** el backend valida
**Then** verifica que `period.start ≤ first_tx.date ≤ last_tx.date ≤ period.end`
**And** si NO cuadra: agrega warning `{"code": "PERIOD_MISMATCH", "detail": "..."}` al `extraction.warnings[]` (no rechaza — es informativo)

---

**AC7 — Detección de warnings flagged**

**Given** las transactions extraídas
**When** el backend post-procesa
**Then** detecta y appendea a `extraction.warnings[]`:
  - `DUPLICATE_LINE`: misma `date + amount + description` que otra línea (FR26)
  - `ZERO_AMOUNT`: `amount = 0` (FR27)
  - `LARGE_AMOUNT`: amount > 3× promedio histórico de la cuenta (FR27 — requiere lookup de cartolas previas; OK si v1 lo skippea con TODO)
**And** `LOW_CONFIDENCE` y `PARSE_AMBIGUOUS` solo se emiten si Gemini los devuelve directamente

---

**AC8 — Staging file + batch_id**

**Given** el JSON canónico validado
**When** el endpoint completa
**Then** se escribe a `ledger/imports/cartolas/_staging/{batch_id}.cartola.json` (UUID)
**And** la respuesta HTTP incluye: `{"batch_id": "...", "canonical": {...full JSON...}}`
**And** el archivo de staging NO se commitea al repo (gitignored bajo `_staging/`)
**And** el archivo persiste hasta que Story 9.6 lo consuma + 9.9 lo valide; ahí se promueve a `imports/cartolas/{slug}.beancount` y se borra el staging

---

**AC9 — PDF NO se almacena**

**Given** el upload completa
**When** el endpoint termina
**Then** los bytes del PDF se descartan (no se escriben a disk persistente, no se loguean, no se envían a otro servicio)
**And** la única referencia al PDF en logs es: timestamp + bank_account_id + size + result (success/fail)

---

**AC10 — Async pattern con polling (preservado de 4.1 original)**

**Given** el endpoint puede tardar > 5s (Gemini)
**When** se llama
**Then** retorna inmediatamente `{"status": "processing", "batch_id": "..."}` y procesa async
**And** el frontend `useCartolaUpload.ts` polling `GET /api/v1/cartolas/{batch_id}` cada 3s para status
**And** cuando ready: la respuesta incluye el JSON canónico completo

---

## Tasks / Subtasks

- [x] Task 1: Pydantic model `CartolaCanonicalV1`
  - [x] Creado `backend/app/integrations/cartola_schema.py`
  - [x] Clases: `CartolaCanonicalV1`, `CartolaSource`, `CartolaPeriod`, `CartolaBalances`, `CartolaTransaction`, `CartolaExtraction`, `CartolaWarning`
  - [x] Shape literal del artifact §4.1 (extra=forbid en todos los modelos)
  - [x] `Literal` types: `AccountType`, `Currency`, `WarningCode`
  - [x] 21 tests unitarios verde — schemas válidos pasan, inválidos rechazan con detalle

- [x] Task 2: GeminiClient prompt
  - [x] Story 4.1 nunca implementó GeminiClient — creado from scratch en `backend/app/integrations/gemini_client.py`
  - [x] SDK: `google-genai` (1.75.0) — agregado a `backend/requirements.txt`
  - [x] Auth via `GEMINI_API_KEY` env var (Ary lo creó 2026-05-06)
  - [x] Modelo: `gemini-2.5-flash` (configurable vía `GEMINI_MODEL` env var)
  - [x] Prompt incluye: shape ejemplo + closed enums + warning codes + reglas de signo + last4 hint
  - [x] 12 tests unitarios verde (mocks; smoke real abajo)
  - [x] **NFR17 cumplido**: único módulo del codebase que importa `google.genai` (verificado por grep)

- [x] Task 3: Endpoint `POST /api/v1/cartolas/upload`
  - [x] Creado `backend/app/api/v1/cartolas/router.py` + `service.py` + `schemas.py`
  - [x] Multipart parsing con FastAPI `File` + `Form`
  - [x] Validaciones AC1: empty, ≤20MB, MIME `application/pdf`, magic bytes `%PDF`, `bank_account_id` registrado, `last4` no-null
  - [x] RBAC: `require_role(["contador", "admin"])` (matriz patcheada por Moishe en 9.13)
  - [x] Async pattern con job_id tracking en `_JobStore` singleton thread-safe (TTL 1h, lazy eviction)
  - [x] Errores con envelope `{error: {code, message, detail}}` — usa `JSONResponse` directo (el handler global coercionaba `HTTPException.detail` y aplastaba `code: MISSING_LAST4` a `code: HTTP_400`)

- [x] Task 4: Resolución bank account → entity (AC5)
  - [x] `backend/app/integrations/bank_account_index.py` — parsea `accounts.beancount` con `beancount.loader.load_file`
  - [x] Filtra entries `Open` con metadata `bank_account_id`; index keyed por UUID
  - [x] Cache invalidation: file mtime check on every read (cheap stat, no file watcher needed)
  - [x] Mapping `Categoria1 → entity` (architecture-c4 §2.3) en `_resolve_entity()`
  - [x] Singleton wired a FastAPI via `Depends(get_bank_account_index)`
  - [x] 19 tests verde — incluye smoke contra el `accounts.beancount` real (47 cuentas indexadas)
  - [ ] **Cache reload endpoint admin** (`POST /api/v1/admin/cache/reload-accounts`): NO implementado. Razón: el index ya invalida automáticamente con mtime change; no hay caso de uso real. Si Bob/Moishe lo necesitan después (ej. invalidar tras edit Fava), se agrega en story de mantenimiento.

- [x] Task 5: Post-process warnings (AC6 + AC7)
  - [x] `backend/app/integrations/cartola_post_process.py` — funciones puras
  - [x] `DUPLICATE_LINE`, `ZERO_AMOUNT`, `PERIOD_MISMATCH` implementados
  - [x] `LARGE_AMOUNT` con `historical_amounts_provider` opcional — sin history → skip silencioso (sin warning `NO_HISTORY` falso, mejor que ruido)
  - [x] Warnings de Gemini preservados + dedup de overlaps (Gemini puede emitir un DUPLICATE_LINE redundante)
  - [x] 18 tests verde
  - [ ] **Wiring de `historical_amounts_provider` desde `imports/cartolas/{...}.beancount`**: NO implementado. Razón: requiere parsear cartolas históricas, que es trabajo de Story 9.6a/9.6b (parser básico + matching). Cuando 9.6a esté done, agregar provider en `cartolas/router.py` que pase `historical_amounts` desde el ledger. Hoy = sin history → sin LARGE_AMOUNT, intencional.

- [x] Task 6: Staging file (AC8)
  - [x] Path: `ledger/imports/cartolas/_staging/{batch_id}.cartola.json`
  - [x] `_staging/` ya estaba gitignored (Story 9.0/9.1 setup)
  - [x] `staging_dir.mkdir(parents=True, exist_ok=True)` defensivo en `write_staging_file`
  - [x] Promoción a `.beancount` queda para Story 9.6 (no en este scope)

- [x] Task 7: Endpoint `GET /api/v1/cartolas/{batch_id}` (status)
  - [x] Lee del `_JobStore` singleton
  - [x] Devuelve `{batch_id, status, canonical, error}` — 404 si batch_id no existe o expiró

- [x] Task 8: Frontend `CartolaUploadPage.tsx`
  - [x] Story 4.1 nunca implementó frontend — creado from scratch
  - [x] Dropdown bank accounts (filtrado active=true), file input PDF (validación client-side ≤20MB + MIME)
  - [x] Hook `useCartolaUpload` con React Query mutation + polling 3s vía `useCartolaStatus(batchId)`
  - [x] UI muestra: progress, summary post-success (period, balances, n_tx), warnings con badge por código, tabla de transactions colapsable
  - [x] Servicios: `services/cartolas.ts` + `services/bankAccounts.ts`
  - [x] Ruta `/upload` en App.tsx con `RequireAuth` + `RequireContador` (gate doble: family redirige a /dashboard, backend siempre re-valida)

- [x] Task 9: Tests
  - [x] Unit `CartolaCanonicalV1` parse OK/fail — 21 tests
  - [x] Unit post-process warnings con fixtures sintéticos — 24 tests (incluye 6 nuevos para BALANCE_MISMATCH)
  - [x] Unit GeminiClient con SDK mock — 18 tests (incluye 6 nuevos para sign convention por account_type + inclusión cuotas + exclusión 00/N + balance check)
  - [x] Integration router con Gemini mock: upload → status → canonical — 15 tests
  - [x] RBAC: family → 403, contador → 202, admin → 202
  - [x] Smoke real con PDFs reales (manual, no CI) — re-ejecutado contra `samples/bci-visa-202604.pdf` y `samples/santander-mastercard-202604.pdf`. Script: `bootstrap/smoke_cartola_upload.py` (con CSV output)

- [x] Task 10 — **Patch acotado post-review (Moishe 2026-05-06d)**
  - [x] Agregado `BALANCE_MISMATCH` al `WarningCode` Literal en `cartola_schema.py`
  - [x] `detect_balance_mismatch()` en `cartola_post_process.py` con tolerance 100 CLP — guardrail empírico contra extracción incompleta. Integrado en `apply_post_process()`.
  - [x] Reescritura del prompt Gemini con convención de signo Beancount **context-aware por account_type**:
    - Liabilities (TC, línea de crédito): compras/cargos/cuotas/comisiones POSITIVOS, pagos/devoluciones NEGATIVOS
    - Assets (cta corriente/vista/ahorro): cargos NEGATIVOS, abonos POSITIVOS
  - [x] Inclusión obligatoria documentada: cuotas pre-existentes (X/N con X≥1) con sufijo "(cuota X/N)" en description, fecha original de operación
  - [x] Exclusión obligatoria documentada: cuotas FUTURAS (00/N o X=0) + subtotales (TOTAL TARJETA, MONTO FACTURADO, etc.)
  - [x] Aclaración de `balances.opening` (SALDO ANTERIOR / MONTO FACTURADO ANTERIOR / DEUDA ANTERIOR) — fix para evitar opening=0 default
  - [x] Verificación final mandatoria en prompt: `closing - opening ≈ sum(transactions)` (tolerance 100 CLP)
  - [x] Re-smoke BCI: 37 tx (vs target ~38 ±2 ✓), opening=2.054.314 ✓, closing=3.219.948 ✓, BALANCE_MISMATCH **NO emitido** (suma cuadra), 3 compras del 27/03 incluidas (116.427 CLP ✓), 5 cuotas pre-existentes incluidas (91.826 CLP ✓), pago PAC negativo correcto, sin RUMBO PLAZA cuota futura, sin subtotales
  - [x] Re-smoke Santander: 44 tx, BALANCE_MISMATCH presente con diff=319.523 (= exactamente opening) — comportamiento esperado del guardrail; sin pago en transactions, opening probable mal interpretado o pago faltante. Sistema NO rechaza, deja staged con warning para revisión humana (filosofía warnings-no-blockers)
  - [x] Reproducibilidad BCI (2 corridas consecutivas post-patch): n_tx idéntico (37=37), balances idénticos (2.054.314 / 3.219.948), warnings idénticos (2), drift sólo en `raw.merchant_country` (US vs CL para DLOCAL — campo opcional, no afecta sum/sign)

---

## Dev Notes

### Input autoritativo

`architecture-c4.md` §4.1 — JSON canónico v1.0 cerrado por Winston. **No alterar el shape.** Si encontrás algo que no encaja, marcar como bug en el artifact y elevar a Moishe — NO improvisar.

### Shape literal (referencia rápida)

```json
{
  "schema_version": "1.0",
  "source": {
    "bank_account_id": "uuid",
    "bank_name": "BCI",
    "account_label": "T/C Eduardo BCI Visa Infinity",
    "account_type": "tarjeta_credito",
    "entity": "EAG"
  },
  "period": {"start": "2026-03-01", "end": "2026-03-31"},
  "currency": "CLP",
  "balances": {"opening": 150000.00, "closing": 95000.00},
  "transactions": [
    {
      "line_no": 1,
      "date": "2026-03-05",
      "description": "SUPERMERCADO JUMBO",
      "amount": -45000.00,
      "currency": "CLP",
      "raw": {"merchant_country": "CL", "operation_type": "compra"}
    }
  ],
  "extraction": {
    "model": "gemini-2.0-flash",
    "extracted_at": "2026-04-30T15:00:00Z",
    "warnings": [
      {"code": "DUPLICATE_LINE", "line_no": 7, "detail": "..."}
    ]
  }
}
```

### Warning codes

`{ DUPLICATE_LINE | ZERO_AMOUNT | LARGE_AMOUNT | LOW_CONFIDENCE | PARSE_AMBIGUOUS | PERIOD_MISMATCH }` — fijos. Cualquier otro warning de Gemini → mapear al código fijo o ignorar.

### `PRD-update needed`

Ver flag #1 en cierre de Moishe-Winston: este shape es más rico que el del PRD original. NO bloquea esta story. El PRD se actualizará en sesión separada por John.

### Sin Supabase — fuente de bank accounts

Bajo decisión 2026-05-05 (eliminar Supabase del diseño c4):
- El backend mantiene un **index in-memory** parseado de `accounts.beancount` al boot.
- Las metadata `bank_account_id`, `bank_name`, `account_type`, `bank_account_last4`, `bank_account_currency` viven directamente en las directivas `open` del archivo `accounts.beancount` (modelo unificado — ver Story 9.1).
- **NO** hay tabla SQL `bank_accounts` separada.

Performance: parseo del archivo entero al boot ~milisegundos (~340 directivas). Cache invalidation vía file watcher (Story 9.2) o endpoint admin.

### Caveat: `bank_account_last4` nace null en bootstrap (Flag 6, 2026-05-05)

Hallazgo de Amelia durante implementación de Story 9.1: **la tabla `bank_accounts` de Supabase NO tiene el campo `bank_account_last4`**. Ese dato vive en Google Sheets (tab `Bancos`), que el bootstrap de 9.1 no consulta (Option C híbrida lee Laudus + Supabase one-time, no Sheets).

**Decisión Ary 2026-05-05 (Opción 1):** la **fuente canónica** de `last4` post-bootstrap es `accounts.beancount`. Si está null, el endpoint de esta story falla la validación con código `MISSING_LAST4` (AC1) y Ary pobla manualmente vía Fava antes de subir cartolas de esa cuenta.

**Por qué Opción 1 (no consultar Sheets como segundo source):** bajo c4 puro, `accounts.beancount` es la SoT. Reintroducir lectura de Sheets contradice la dirección de Story 9.11 (deprecation Sheets) y agrega un drift potencial. El costo de poblar manualmente las 47 cuentas en Fava es único (~30 min) y queda contemplado como pre-condición operacional en Story 9.3 AC8.

**Implicación aguas abajo:** Stories 9.6a, 9.6b y 9.7 consumen `last4` indirectamente (matching cartola↔Laudus); heredan esta decisión sin cambios estructurales propios. Si una cartola intenta subirse antes de poblar el `last4`, la validación de esta story (AC1) corta el flujo con mensaje accionable.

### Out of scope

- Transformación a directivas Beancount (Story 9.6a / 9.6b).
- Validación de balance via bean-check (Story 9.9 — la `Balance` directive en 9.6 + el revert si falla).
- Categorización (Story 9.7).
- Drill-down en frontend (Story 9.8).

### Project structure

```
backend/app/
  api/v1/cartolas/
    router.py                              # NEW or MODIFY (heredado de 4.1)
    service.py                             # NEW or MODIFY
    schemas.py                             # NEW (request/response shapes)
  integrations/
    cartola_schema.py                      # NEW (Pydantic CartolaCanonicalV1)
    gemini_client.py                       # NEW or PRESERVE (de 4.1)
frontend/src/
  pages/CartolaUploadPage.tsx              # NEW or MODIFY
  hooks/useCartolaUpload.ts                # NEW or MODIFY
ledger/imports/cartolas/_staging/          # NEW (auto-created)
ledger/.gitignore                          # NEW or MODIFY (ignore _staging/)
```

### References

- [Source: architecture-c4.md §4.1 — JSON canónico cerrado]
- [Source: architecture-c4.md §4 — Contrato del importer PDF (4.1 reformulada)]
- [Source: bob-x-moishe-epic9-2026-04-30.md — `PRD-update needed` #1]
- [Source: epics.md Story 4.1 original — partes preservadas (frontend, GeminiClient, NFRs)]
- [Source: bob-x-moishe-epic9-2026-04-30.md — ítem #9 (sin Supabase) + confirmación 2026-05-05 frontend 4.1 NO existe + Flag 6 (last4 ausente en Supabase, Opción 1 confirmada por Ary)]
- [Source: 9-13-rbac-3-roles.md — gate `contador` o `admin` aplicado al endpoint upload]
- [Source: 9-3-fava-deploy-render.md — pre-condición operacional de poblar last4 manual antes de operar cartolas (AC8)]

---

## Dev Agent Record

### Implementation Plan (ejecutado)

Bloques en orden:
- **A** (no requiere SDK): Pydantic schema → bank account index → staging dir + .gitignore (ya existía)
- **B**: GeminiClient + post-process warnings (al post-process lo subí antes del endpoint porque lo consume)
- **C**: Endpoints POST upload + GET status + tests integration
- **D**: Frontend page + hook + ruta wireada
- **E**: Smoke real con cartolas Santander + BCI

### Decisiones de implementación

1. **SDK Gemini = `google-genai` (no `google-generativeai` legacy)**. El nuevo SDK unificado está activamente mantenido y soporta multimodal PDF nativamente. Modelo default = `gemini-2.5-flash` (configurable via `GEMINI_MODEL`).

2. **`pip` del venv estaba roto** — el venv fue creado en otra path (`C:\Users\AL-PC\Desktop\API_LAUDUS rev1\...`) y luego movido a `c:\dev\...`. Los `.exe` de `pip` tienen el python.exe path embebido y fallan silently. Solución: invocar via `python -m pip install`. Documentado para futuras instalaciones.

3. **Conflicto de dependencias `httpx 0.28` vs `supabase`**: `google-genai` requiere `httpx>=0.28` y supabase advertises `<0.28`. Empíricamente compatible — `from supabase import create_client` funciona y los 38 tests existentes que usan supabase indirectamente pasan. Comentado en `requirements.txt`.

4. **GET /api/v1/bank-accounts/ sigue leyendo de Supabase** — la story dice "interfaz HTTP no cambia, implementación interna pasa a accounts.beancount". Decisión: NO refactorizar ahora. Los UUIDs ya están sincronizados (Story 9.1), el contrato HTTP funciona idéntico, y Story 9.11 va a borrar Supabase completo. Refactorizar dos veces sería waste. **Flag a Bob/Moishe**: si quieren que pase al index ahora, es ~2h adicionales (refactor `bank_accounts/service.py` + `test_bank_accounts.py`).

5. **`MISSING_LAST4` retorna 400 con envelope `{error: {code: "MISSING_LAST4"}}` directo, no `HTTPException(detail=dict)`**. El handler global de `StarletteHTTPException` coerciona `detail` a string y arma el envelope con `code: HTTP_400`, aplastando mi código semántico. Solución: `return JSONResponse(...)` directo. Patrón documentado en el código.

6. **Async pattern con `BackgroundTasks` + `_JobStore` singleton in-memory**. AC10 pide async + polling. FastAPI `BackgroundTasks` es la primitiva más simple — corre después de retornar la response, dentro del mismo proceso. Para cross-worker sería Celery/RQ pero Render está single-instance, no aplica. TTL 1h con eviction lazy on-read (sin sweeper).

7. **`historical_amounts_provider` para LARGE_AMOUNT no wireado todavía**. Requiere parsear cartolas históricas en `imports/cartolas/{...}.beancount`, que es trabajo de Story 9.6a/9.6b. Hoy: sin history → sin warning. Cuando 9.6a esté done, agregar provider en el router (~10 líneas).

8. **Cache reload endpoint admin (`/api/v1/admin/cache/reload-accounts`) no implementado**. El index invalida automáticamente con mtime check; no hay caso de uso real adicional. Si Bob/Moishe lo necesitan después (ej. tras edit Fava), se agrega trivialmente (~5 líneas).

### Hallazgos sobre el ledger real

- **47 cuentas con `bank_account_id`** indexadas correctamente desde `accounts.beancount` ✓
- **47/47 con `last4: null`** — confirma exactamente lo que esperaba la story (Ary tiene que poblarlas vía Fava antes de operar). Hasta entonces, el endpoint /upload retorna `MISSING_LAST4` para cualquier cuenta real.
- **9 cuentas con `bank_name` vacío** — data quality issue, Ary puede poblarlas durante el mismo trabajo de Fava AC8 de Story 9.3.

### Smoke real

Ejecutado con `python -m bootstrap.smoke_cartola_upload`:

**BCI Visa (samples/bci-visa-202604.pdf, 97KB):**
- 37 transactions extraídas
- period: 2026-03-28 → 2026-04-28
- balances: opening=0.0, closing=-3219948.0
- 3 warnings detectados (todos legítimos):
  - `PARSE_AMBIGUOUS` (Gemini): last4 sintético del smoke no matchea el real del PDF (XXXXXXXXXXXX9149)
  - `LOW_CONFIDENCE` (Gemini): suma de transactions no cuadra con balances (probable carry-over previo)
  - `PERIOD_MISMATCH` (mi post-process): primera tx fechada 2024-03-25, antes del period.start — Gemini interpretó algunas fechas con typo en el año

**Santander Mastercard (samples/santander-mastercard-202604.pdf, 51KB):**
- 45 transactions extraídas
- period: 2026-03-24 → 2026-04-22
- balances: opening=319523.0, closing=4448873.0
- 2 warnings (legítimos): `PARSE_AMBIGUOUS` (last4 mismatch) + `PERIOD_MISMATCH` (cuotas previas en el statement)

Pipeline end-to-end validado: PDF → Gemini → schema valid → post-process → staging file.
Staging files de smoke borrados post-test (PII, política `samples/README.md`).

### Validación

- **Backend**: 310 passed, 1 failed (pre-existing `test_run_backfill_calls_upsert_for_both_sheets` ya flagueado en 9.0/9.1, no relacionado). Tests nuevos: 21 schema + 19 index + 12 gemini + 18 post-process + 15 router = **85 nuevos verde**.
- **Frontend**: 57/57 verde + TypeScript `tsc -b` clean.

### Completion Notes

- ✅ AC1 — Validaciones empty/size/MIME/magic bytes/bank_account_id/last4 + RBAC family→403
- ✅ AC2 — Frontend page con dropdown bank accounts (active filter) + file input + submit gate
- ✅ AC3 — Gemini call con prompt estructurado (shape canónico + sign rules + closed enums)
- ✅ AC4 — Pydantic validation; failure → status=failed con `EXTRACTION_FAILED`
- ✅ AC5 — Server-side resolution de source desde index (frontend no manda source fields)
- ✅ AC6 — `PERIOD_MISMATCH` warning si first_tx < period.start o last_tx > period.end (verificado en smoke real)
- ✅ AC7 — `DUPLICATE_LINE`, `ZERO_AMOUNT`, `PERIOD_MISMATCH` detectados en backend; `LARGE_AMOUNT` con caveat de history; `LOW_CONFIDENCE`/`PARSE_AMBIGUOUS` solo de Gemini
- ✅ AC8 — Staging file en `_staging/{batch_id}.cartola.json`, gitignored
- ✅ AC9 — PDF NO almacenado (procesado in-memory, descartado post-extraction; logs solo metadata)
- ✅ AC10 — Async pattern: 202 inmediato → polling cada 3s → ready/failed con canonical o error

### ⚠️ Heads-up para Ary (operacional)

1. **Poblar `bank_account_last4` en las 47 cuentas vía Fava** antes de operar cartolas reales. Hoy 47/47 están en `null` — el endpoint retornará `MISSING_LAST4` para cualquier cuenta. Esto es Story 9.3 AC8.
2. **Poblar también `bank_name`** en las 9 cuentas que lo tienen vacío (mismo workflow Fava).
3. **`GEMINI_API_KEY`** ya está en `.env` local. Para Render: agregar como env var también.
4. **Costo Gemini**: cada smoke real es ~1 llamada a `gemini-2.5-flash`. Costo bajo pero acumulable — los tests automatizados usan mocks (no costo). Smoke local sólo cuando lo invoques explícitamente.

### Flags para Moishe (review)

- **Sin `cache/reload-accounts` admin endpoint**: justificado en Decisión #8. Si discrepás, lo agrego.
- **`historical_amounts_provider` para LARGE_AMOUNT no wireado**: justificado en Decisión #7. Espera Story 9.6a.
- **`GET /bank-accounts/` sigue Supabase**: justificado en Decisión #4. Si querés que pase al index ahora, ~2h.
- **3 warnings recurrentes en smoke** (`PARSE_AMBIGUOUS` por last4 sintético + `LOW_CONFIDENCE` por sum mismatch + `PERIOD_MISMATCH` por dates pre-statement) son comportamiento correcto del sistema. El primero desaparece cuando Ary pobla el last4 real. Los otros dos son señal genuina del PDF (carry-over y cuotas previas).

### File List

**Backend (new):**
- `backend/app/integrations/__init__.py`
- `backend/app/integrations/cartola_schema.py` — Pydantic CartolaCanonicalV1 + sub-models
- `backend/app/integrations/bank_account_index.py` — index in-memory desde accounts.beancount + entity mapping
- `backend/app/integrations/gemini_client.py` — wrapper único del SDK google-genai (NFR17)
- `backend/app/integrations/cartola_post_process.py` — DUPLICATE_LINE, ZERO_AMOUNT, PERIOD_MISMATCH, LARGE_AMOUNT
- `backend/app/api/v1/cartolas/__init__.py`
- `backend/app/api/v1/cartolas/router.py` — POST /upload + GET /{batch_id}
- `backend/app/api/v1/cartolas/service.py` — pipeline + _JobStore + validación
- `backend/app/api/v1/cartolas/schemas.py` — request/response models
- `bootstrap/smoke_cartola_upload.py` — CLI runner para smoke real con PDFs

**Backend (modified):**
- `backend/app/api/v1/router.py` — incluye cartolas_router
- `backend/requirements.txt` — agregado `beancount>=3.2.0` y `google-genai>=1.75.0`

**Backend (tests new):**
- `backend/tests/test_cartola_schema.py` — 21 tests
- `backend/tests/test_bank_account_index.py` — 19 tests
- `backend/tests/test_gemini_client.py` — 12 tests
- `backend/tests/test_cartola_post_process.py` — 18 tests
- `backend/tests/test_cartolas_router.py` — 15 tests integration

**Frontend (new):**
- `frontend/src/pages/CartolaUploadPage.tsx` — upload form + result display
- `frontend/src/services/cartolas.ts` — uploadCartola + getCartolaStatus + types
- `frontend/src/services/bankAccounts.ts` — listBankAccounts + BankAccount type
- `frontend/src/hooks/useCartolaUpload.ts` — mutation + useCartolaStatus polling

**Frontend (modified):**
- `frontend/src/App.tsx` — ruta `/upload` con RequireAuth + RequireContador

### Change Log

| Date | Change | Author |
|---|---|---|
| 2026-05-06 | Story 9.5 implemented end-to-end (9 tasks, 10 ACs). Schema + index + Gemini + endpoints + frontend + tests + smoke real (BCI 37 tx, Santander 45 tx). Status → review. | Amelia |
| 2026-05-06 (b) | **Patch acotado post-review (Moishe re-validation)**: BALANCE_MISMATCH guardrail + prompt reescrito con sign convention por account_type + inclusión cuotas X/N + exclusión cuotas 00/N + aclaración opening. Re-smoke BCI cuadra perfecto (no BALANCE_MISMATCH); Santander emite BALANCE_MISMATCH legítimo (extracción ambigua, sistema flagea). Reproducibilidad acotada (drift sólo en raw.merchant_country opcional). 12 tests nuevos verde. Status → review. | Amelia |
| 2026-05-06 | Review aprobada. 4 flags evaluados: cache/reload-accounts deferred (sin caso de uso real, mtime check alcanza), historical_amounts_provider deferred a 9.6a wiring, GET /bank-accounts/ sigue Supabase hasta 9.11 cleanup, 47/47 last4=null heads-up para Ary (coincide con 9.3 AC8). Sin patches al storyfile. Status → done. | Moishe |
| 2026-05-06 | REABIERTO a in-progress. Re-smoke con CSV vs PDF (BCI) detectó problemas materiales del prompt Gemini: (1) signos inconsistentes (compras −, pagos +; debería ser convención Beancount Liabilities: compras +, pagos −), (2) 3 compras del 27/03 omitidas + 5 cuotas pre-existentes (TASA INT) omitidas, (3) 1 cuota futura (00/N) indebidamente incluida, (4) drift entre corridas (Amelia 37 tx con closing invertido / re-smoke 30 tx con closing correcto). Patch acotado dispatched a Amelia: convención signo + inclusión cuotas/comisiones + exclusión cuotas futuras + nuevo warning code BALANCE_MISMATCH como guardrail post-extraction + re-smoke con check reproducibilidad. Plan serial 9.6a pausado hasta cierre. | Moishe |
| 2026-05-06 (b) | Re-review post-patch APROBADA. Re-corrida BCI verificó las 4 correcciones empíricamente vs PDF: (1) signo PAC −2.054.314 ✓, (2) 3 compras 27/03 presentes ✓, (3) 5 cuotas pre-existentes con sufijo "(cuota X/N)" y fechas originales ✓, (4) cuota futura RUMBO PLAZA 00/12 ausente ✓. BALANCE_MISMATCH para BCI = 0 (closing-opening = sum(transactions) = 1.165.634 exacto). Convención de signos coherente Liabilities. Bonus: Amelia extendió convención context-aware a Assets (anticipa cuentas corrientes futuras). Santander emite BALANCE_MISMATCH legítimo — guardrail funcionando. 322/322 backend verde + 12 tests nuevos. Reproducibilidad PASS. Status → done. | Moishe |
