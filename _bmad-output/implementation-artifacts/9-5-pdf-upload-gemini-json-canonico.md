---
story: 9.5
title: PDF upload + extracción Gemini → JSON canónico (era 4.1a)
status: ready-for-dev
epic: 9
depends_on: []
blocks: [9.6]
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
**When** el endpoint se llama por un usuario `contador`
**Then** valida: tamaño ≤ 20MB (NFR3), MIME = `application/pdf`, `bank_account_id` existe en `bank_accounts` (Supabase)
**And** si alguna validación falla → HTTP 400 con `{"error": {"code": "VALIDATION_FAILED", ...}}`
**And** un usuario `family` recibe HTTP 403 (sin cambios vs RBAC)

---

**AC2 — Frontend de upload selecciona bank_account_id ANTES del upload**

**Given** la pantalla `CartolaUploadPage.tsx` (preservada de Story 4.1 original)
**When** el contador navega
**Then** ve un dropdown de bank accounts activos (de `GET /api/v1/bank-accounts/?active_only=true`) — uno seleccionable
**And** ve un file input para PDF
**And** el botón "Subir" se deshabilita si falta cualquiera

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
**Then** los campos `source.bank_name`, `source.account_label`, `source.account_type`, `source.entity` se resuelven server-side leyendo `bank_accounts` (Supabase)
**And** se incluyen en el JSON canónico devuelto (frontend + 9.6 no necesitan re-resolver)

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

- [ ] Task 1: Pydantic model `CartolaCanonicalV1`
  - [ ] Crear `backend/app/integrations/cartola_schema.py`
  - [ ] Definir las clases: `CartolaCanonicalV1`, `CartolaSource`, `CartolaPeriod`, `CartolaBalances`, `CartolaTransaction`, `CartolaTransactionRaw`, `CartolaExtraction`, `CartolaWarning`
  - [ ] Schema literal del artifact §4.1
  - [ ] `Literal` types donde aplica (`account_type`, `currency`, `code` de warning)
  - [ ] Tests unitarios: schemas válidos pasan, inválidos rechazan con detalle

- [ ] Task 2: GeminiClient prompt
  - [ ] Si `GeminiClient` ya existe (de Story 4.1 original): adaptar prompt al shape v1.0
  - [ ] Si no existe: crear `backend/app/integrations/gemini_client.py` con SDK + auth via `GEMINI_API_KEY` env var
  - [ ] Prompt incluye: shape ejemplo + listas válidas para `account_type` + warning codes + reglas de signo (negativo = outflow)
  - [ ] Test con un PDF real de muestra (al menos un BCI Visa Infinity Eduardo) → validar que el shape devuelve valid

- [ ] Task 3: Endpoint `POST /api/v1/cartolas/upload`
  - [ ] Crear (o adaptar) `backend/app/api/v1/cartolas/router.py` y `service.py`
  - [ ] Multipart parsing con FastAPI `File` + `Form`
  - [ ] Validaciones AC1
  - [ ] RBAC: `require_role(["contador"])`
  - [ ] Async pattern con job_id tracking en memoria (singleton dict) — TTL 1 hora

- [ ] Task 4: Resolución bank account → entity (AC5)
  - [ ] Lookup en Supabase `bank_accounts` por `id`; join lateral con `plan_de_cuentas` para `account_name`
  - [ ] Mapear a `entity` aplicando tabla §2.3 (Categoria1 de plan_de_cuentas → Entity)

- [ ] Task 5: Post-process warnings (AC6 + AC7)
  - [ ] Detección de `DUPLICATE_LINE`, `ZERO_AMOUNT`, `PERIOD_MISMATCH` (lógica pura sobre el JSON)
  - [ ] `LARGE_AMOUNT`: leer cartolas previas de la misma `bank_account_id` (de archivos `imports/cartolas/{...}.beancount`) y calcular promedio histórico. **Si no hay history (primer upload de esa cuenta): skip con warning meta `NO_HISTORY` opcional.**
  - [ ] Asegurar que warnings de Gemini se preservan (no sobrescribir)

- [ ] Task 6: Staging file (AC8)
  - [ ] Path: `ledger/imports/cartolas/_staging/{batch_id}.cartola.json`
  - [ ] `_staging/` gitignored — agregar a `.gitignore` del repo (o `ledger/.gitignore`)
  - [ ] Verificar que el directorio existe en startup (auto-create)
  - [ ] La promoción a archivo `.beancount` definitivo es trabajo de Story 9.6 (no de esta)

- [ ] Task 7: Endpoint `GET /api/v1/cartolas/{batch_id}` (status)
  - [ ] Lee del job_id tracker en memoria
  - [ ] Devuelve `{"status": "processing|ready|failed", "canonical": {...} | null, "error": "..." | null}`

- [ ] Task 8: Frontend `CartolaUploadPage.tsx`
  - [ ] Si existe: adaptar para mostrar warnings extraction (badge por warning code) y shape canónico
  - [ ] Si no existe: crear con: dropdown bank_accounts (active only), file input PDF (≤ 20MB validado client-side también), botón "Subir", spinner mientras polling, summary post-success
  - [ ] Polling con `useCartolaUpload.ts` cada 3s (preservar de 4.1 original si existe)

- [ ] Task 9: Tests
  - [ ] Unit: `CartolaCanonicalV1` parse OK / fail
  - [ ] Unit: post-process warnings (fixtures sintéticos)
  - [ ] Integration con Gemini mock: upload → JSON canónico válido
  - [ ] Integration con PDF real (manual smoke; no en CI por costo Gemini)
  - [ ] RBAC: family → 403, contador → 200

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

### Out of scope

- Transformación a directivas Beancount (Story 9.6).
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
