---
story: 9.5e
title: Rediseño prompt Gemini → CSV liviano + wrapping server-side
status: ready-for-dev
epic: 9
depends_on: [9.5c]
blocks: [9.6a]   # 9.6a queda blocked-by-9-5e hasta cierre + re-corrida 9.5c ≥90% verde
parallelizable_with: [9.2, 9.3, 9.4, 9.6b, 9.7, 9.8, 9.9, 9.11, 9.12]
---

# Story 9.5e — Rediseño prompt Gemini → CSV liviano + wrapping server-side

## Story

As Ary (single operator del Family Office),
I want que `gemini_client.py` pida un output liviano (header JSON + CSV simple) en vez del JSON canónico forzado, y que el ensamblaje del `CartolaCanonicalV1` se haga en Python server-side con `BankAccountEntry` autoritativo,
so that la extracción Gemini suba del **0% verde sostenido** (medido empíricamente por Ary en 9.5c smoke 2026-05-19) a **≥90% verde** sobre los 14 PDFs reales de `samples/`, desbloqueando 9.6a (importer beangulp) y por transitividad 9.7 (smart_importer), sin parchear 9.5 ni inflar 9.5d (retry).

## Context

Decisión Ary 2026-05-19 (coord file `_bmad-output/coordination/9-5c-hallazgo-prompt-2026-05-19.md` + memory `project_epic9_validacion_cartolas`):

- 9.5c entregó tooling + 37 tests verde. Ary corrió el smoke real (11/14 PDFs procesados + 2 parciales antes de Ctrl+C deliberado): **0 PDFs VERDE, ~4 ROJO (BALANCE_MISMATCH), ~6 AMARILLO**.
- **Hallazgo central**: el prompt elaborado de Story 9.5 está **degradando** el output de Gemini, no mejorándolo. Evidencia A/B empírica:
  - Gemini web sin contexto + prompt corto pidiendo CSV → output limpio en **3 segundos**.
  - Pipeline 9.5 con prompt 3-5 KB + schema forzado → PARSE_AMBIGUOUS + BALANCE_MISMATCH; a veces excluye transactions para "asegurar el cuadre" (caso documentado: `estado-de-cuenta (26).pdf` con warning literal *"La transacción 'MONTO CANCELADO' por $-4.825.462 fue excluida... para asegurar la conciliación de saldos"* — Gemini **manipula los datos** para complacer al balance check). ~60 segundos por PDF.
- Fuentes específicas de contaminación detectadas en el prompt 9.5:
  1. **Sign convention block** (Liabilities/Assets) — Gemini invierte signos.
  2. **Instrucción "asegurar que el balance cuadre"** — Gemini excluye transactions.
  3. **Forzar `currency=CLP` por contexto** cuando el PDF es multi-currency → PARSE_AMBIGUOUS masivo.
  4. **`response_schema` + `response_mime_type=application/json`** → ~40% del output va en estructura JSON anidada (`{`, `}`, `[`, `]`, keys repetidas), infla a ~4500 tokens para 92 tx.
  5. **Sin streaming** → 30-40s en token generation para PDFs con 90+ tx.
- **Insight arquitectónico (Ary)**: mover la complejidad de Gemini → Python. Gemini sólo transcribe el PDF a CSV liviano; el wrapper Python arma el `CartolaCanonicalV1` con el `BankAccountEntry` autoritativo. Beneficios esperados: 3-5× más rápido, ~50% menos tokens, Gemini libre para contenido (no estructura), validación Pydantic post-Gemini.

**Decisiones de diseño (sesión Bob ↔ Ary 2026-05-19):**

- **Amount = una sola columna con signo "natural" del PDF** (NO `debit`/`credit` separados). Las cartolas de tarjeta de crédito chilenas emiten `amount` con signo positivo/negativo, no dos columnas. Gemini transcribe el signo **tal como aparece en el PDF**, sin invertir, sin inferir convención bancaria. El wrapper Python **no aplica inversión speculative** — la hipótesis empírica (validada por BCI en 9.5 cierre 2026-05-06) es que los PDFs chilenos ya emiten signos compatibles con la convención Beancount esperada (Liabilities: consumo positivo, pago negativo; Assets: depósito positivo, cargo negativo).
- **Output Gemini = header JSON + separator `---` + CSV body**, single call. Header JSON contiene: `period_start, period_end, currency, opening_balance, closing_balance`. CSV body contiene columnas exactas: `date, description, amount, currency`.
- **Multi-currency** (BCI 9149 y Santander 0858 reales): el wrapper construye **una sola** `CartolaCanonicalV1` con `currency` top-level = lo que Gemini detectó como dominante en el header + `transactions[].currency` por línea (el schema ya lo soporta: `cartola_schema.py:69`). Si hay mix → emite warning `PARSE_AMBIGUOUS` con detail `"multi-currency: N tx en {set}"`.
- **Prompt seed**: el prompt corto que Ary usó en Gemini web (~25 palabras pidiendo "CSV de transacciones + período + moneda + monto facturado anterior + del período") es **señal direccional empírica** ("un prompt corto sin contaminación funciona"), NO texto literal. El prompt final lo diseña Amelia en Task 0 (spike), iterando contra 3 PDFs representativos con el tooling de 9.5c.

## Acceptance Criteria

**AC1 — Prompt nuevo en `gemini_client.py` libre de contaminación**

**Given** el rediseño del prompt
**When** Amelia escribe el nuevo `_build_prompt()` en `backend/app/integrations/gemini_client.py`
**Then** el prompt **NO** contiene:
- Sign convention block (Liabilities vs Assets) — eliminado completo.
- "Asegurar que el balance cuadre" / "Verificá ANTES de devolver: closing - opening = sum(transactions)" — eliminado.
- Forzar `currency` top-level por contexto de cuenta — el prompt NO impone moneda; Gemini la transcribe del PDF.
- Schema canónico anidado con ejemplo de 30+ líneas — eliminado.
**And** el prompt **SÍ** contiene:
- Instrucción explícita: transcribir el signo del amount **tal como aparece en el PDF**, sin invertir, sin inferir convención bancaria.
- Lista de columnas exactas del CSV: `date, description, amount, currency`.
- Lista de campos exactos del header JSON: `period_start`, `period_end`, `currency`, `opening_balance`, `closing_balance`.
- Separator literal `---` entre header y CSV body.
- Hint de fecha en formato ISO 8601 (YYYY-MM-DD); el wrapper server-side absorbe variabilidad (ver Task 0 decisión).
**And** el prompt resultante mide **≤ 1500 bytes** (`len(prompt.encode("utf-8"))`), medido en un test unitario. Métrica proxy de "el prompt no tiene contaminación residual" — el prompt corto de Gemini web (~200 bytes) es el norte; 1500 bytes da margen para columnas + separator + instrucciones de signo y formato.

---

**AC2 — `GeminiClient.extract_pdf()` devuelve string cruda, sin schema forzado**

**Given** la llamada al SDK Gemini en `backend/app/integrations/gemini_client.py`
**When** se construye el `GenerateContentConfig`
**Then** `response_mime_type="text/plain"` (en vez de `application/json`).
**And** **NO** se pasa `response_schema`.
**And** `temperature=0.0` se preserva (determinismo).
**And** la firma de `extract_pdf()` cambia a `extract_pdf(self, pdf_bytes: bytes) -> str` — devuelve la string cruda del response. Los kwargs antiguos (`bank_account_id`, `bank_name`, `account_label`, `account_type`, `currency`, `last4`) **se eliminan** porque el prompt nuevo es agnóstico de cuenta; el call site en `service.py` se ajusta en AC4.
**And** si `response.text` está vacío → `GeminiExtractionError` (igual que hoy).

---

**AC3 — Nuevo módulo `csv_to_canonical.py` que arma `CartolaCanonicalV1`**

**Given** la string cruda de Gemini (formato `<header JSON>\n---\n<csv body>`) y el `BankAccountEntry` autoritativo
**When** se llama `csv_to_canonical(raw: str, entry: BankAccountEntry) -> CartolaCanonicalV1`
**Then** la función vive en `backend/app/integrations/csv_to_canonical.py` (NUEVO archivo).
**And** parsea el header como JSON: extrae `period_start`, `period_end`, `currency`, `opening_balance`, `closing_balance`. Si el JSON está mal formado o falta algún campo → `CsvParseError("HEADER_INVALID", detail)`.
**And** parsea el body como CSV (módulo `csv` de stdlib) con header obligatorio en la primera fila del body; columnas exactas: `date, description, amount, currency`. Cualquier desviación (faltante, extra, typo) → `CsvParseError("CSV_HEADER_INVALID", detail)`. Permitir orden cualquiera, pero los 4 nombres exactos.
**And** **NO aplica inversión de signo**. El signo emitido por Gemini se preserva en `transactions[].amount`. La hipótesis (validada por BCI 9.5 cierre 2026-05-06: convención Liabilities natural, `closing - opening = sum(tx)` exacto) es que los PDFs chilenos ya emiten signos compatibles. Si la re-corrida 9.5c post-9.5e muestra signos inconsistentes para algún banco específico, se documenta como TODO en Completion Notes y se evalúa en iteración posterior — **NO** se agrega lógica de inversión speculative.
**And** la firma incluye los stamps de extracción como kwargs explícitos: `csv_to_canonical(raw: str, entry: BankAccountEntry, *, model: str, extracted_at: datetime) -> CartolaCanonicalV1`. Esto evita que el caller tenga que hacer `model_copy` sobre un modelo ya validado (cleaner que el dict-manipulation pattern actual de `service.py:240-242`).
**And** construye el `CartolaCanonicalV1` con:
- `source` = `resolve_source_dict(entry)` (reusar `service.py:179`).
- `schema_version = "1.0"`.
- `period.start = period_start`, `period.end = period_end`.
- `currency` top-level = del header JSON (lo que Gemini detectó como dominante).
- `balances.opening = opening_balance`, `balances.closing = closing_balance`.
- `transactions[].line_no` = `enumerate(..., start=1)`.
- `transactions[].currency` = de la columna `currency` del CSV (puede diferir del top-level → multi-currency).
- `transactions[].raw = {}` (vacío; campo opcional en el schema).
- `extraction.model = model`, `extraction.extracted_at = extracted_at` (de los kwargs).
**And** si hay tx con `currency != currency_top_level` → emite `CartolaWarning(code="PARSE_AMBIGUOUS", detail="multi-currency: {N} tx en {sorted_set}")` en `extraction.warnings`. Este warning sobrevive a `apply_post_process` (que preserva warnings preexistentes con dedupe — ver `cartola_post_process.py:137`).
**And** valida vía `CartolaCanonicalV1.model_validate(...)` antes de devolver. Si Pydantic rechaza → propaga `ValidationError` (igual flujo actual).

---

**AC4 — `service.py:process_upload_sync` adapta el call site sin cambiar firma pública**

**Given** la pipeline existente en `backend/app/api/v1/cartolas/service.py:214-253`
**When** Amelia adapta el cuerpo de `process_upload_sync`
**Then** la firma pública de `process_upload_sync` **NO cambia** (sigue siendo `batch_id, pdf_bytes, bank_account_entry, gemini, historical_amounts_provider, staging_dir`).
**And** el cuerpo:
1. Llama `raw_str = gemini.extract_pdf(pdf_bytes)` — nueva firma (AC2).
2. Llama `canonical = csv_to_canonical(raw_str, bank_account_entry, model=gemini.model, extracted_at=datetime.now(timezone.utc))` (AC3). Los stamps de extracción se pasan acá — preserva el patrón "server-side decide model + extracted_at, no Gemini" sin requerir `model_copy` post-validate.
3. Llama `enriched = apply_post_process(canonical, historical_amounts=history)` — `cartola_post_process.detect_balance_mismatch` queda como **única fuente de verdad** del balance check; preserva warnings preexistentes (multi-currency PARSE_AMBIGUOUS emitido por el wrapper). **Sin cambios en `cartola_post_process.py`**.
4. Llama `write_staging_file(enriched, batch_id, staging_dir)` (sin cambios).
**And** en `run_job` (`service.py:256-291`): se agrega `except CsvParseError as exc: _job_store.set_failed(batch_id, "EXTRACTION_FAILED", f"{exc.code}: {exc.detail}")` con el mismo patrón que `GeminiExtractionError`.
**And** los endpoints HTTP, response shapes, y job-store API quedan idénticos.

---

**AC5 — Re-corrida 9.5c con el prompt nuevo: gate ≥90% verde**

**Given** los 14 PDFs en `samples/` con currency overrides (las 5 categorías identificadas por Ary en 9.5c smoke 2026-05-19: BCI 9149 CLP, BCI 9149 USD, Santander 8996 CLP, Santander 8996 USD, Santander 0858 CLP/USD)
**When** Ary corre `python -m bootstrap.validate_cartolas_batch samples/ --runs 3` post-implementación de 9.5e
**Then** el `report.md` generado en `_bmad-output/validation-runs/{timestamp}/` muestra `Gate 9.6a (≥90% verde): PASS`.
**And** Ary registra en el Change Log de este storyfile: % verde, % amarillo, % rojo, decisión tomada (dispatch 9.6a directo / iterar prompt / debug específico). Lo completa **Ary leyendo el reporte post-corrida**, NO el dev agent durante implementación.
**And** si el primer pase post-implementación da <90% verde → **no es failure del dev agent**. Es señal para iterar el prompt (Task 0 spike re-corre con variaciones). El AC se marca cumplido **sólo cuando** la corrida final muestra ≥90% verde (puede requerir 2-3 iteraciones del prompt).

---

**AC6 — NO romper 9.5 ni el shape canónico ni los endpoints HTTP**

**Given** la suite de tests backend de Story 9.5 (322 verde reportados en cierre 2026-05-06) + endpoints `/api/v1/cartolas/upload` + `/api/v1/cartolas/jobs/{batch_id}`
**When** Amelia termina 9.5e
**Then** los 322 backend tests existentes siguen verdes **sin modificar lo que cada test verifica**. Los tests que mockean `GeminiClient.extract_pdf` se actualizan: el mock devuelve la string format nueva (`<header_json>\n---\n<csv_body>`) en vez del dict canónico. NO cambiar los assertions de cada test.
**And** `CartolaCanonicalV1` schema (`backend/app/integrations/cartola_schema.py`) **NO se modifica**.
**And** los endpoints HTTP NO cambian: misma URL, misma request shape (multipart con `pdf` + `bank_account_id`), misma response shape (`{batch_id, status}` + polling). El cambio es 100% interno: `GeminiClient` + nuevo `csv_to_canonical.py` + ajuste del cuerpo de `process_upload_sync`.
**And** los tests del prompt en `backend/tests/test_gemini_client.py` se reescriben para validar el prompt nuevo (≤1500 bytes, sin strings prohibidos). Reemplazo, no eliminación bulk.

---

**AC7 — Tests unitarios para `csv_to_canonical` sin tocar Gemini**

**Given** el módulo nuevo de AC3
**When** Amelia agrega tests
**Then** los tests viven en `backend/tests/test_csv_to_canonical.py` (NUEVO).
**And** cubren al menos:
- Happy path: header JSON válido + CSV con 3-5 tx → `CartolaCanonicalV1` válido.
- Header JSON malformado (sintaxis JSON inválida) → `CsvParseError("HEADER_INVALID")`.
- Header JSON con campo faltante (ej. sin `opening_balance`) → `CsvParseError("HEADER_INVALID")`.
- CSV con columna faltante → `CsvParseError("CSV_HEADER_INVALID")`.
- CSV con columna extra → `CsvParseError("CSV_HEADER_INVALID")`.
- Multi-currency (mix CLP + USD en mismo PDF) → canonical válido + warning `PARSE_AMBIGUOUS` con detail correcto.
- Fecha en formato no-ISO según decisión Task 0 (`DD/MM/YYYY` aceptada con conversión, **o** rechazada con `CsvParseError("DATE_FORMAT_INVALID")` — la decisión queda documentada en el coord file del spike y reflejada en este test).
- Amount con separadores de miles chilenos (`"1.234.567"`) → parseado correctamente a `Decimal(1234567)`.
- Amount con signo negativo (`"-50000"`) → preservado tal cual en `transactions[].amount`.
- CSV con sólo header (0 tx) → canonical válido con `transactions=[]`; balance check del post-process (no del wrapper) emite `BALANCE_MISMATCH` si `opening ≠ closing`.
**And** ningún test instancia `GeminiClient` (guard AST, mismo patrón que `test_validate_cartolas_batch.py:test_no_gemini_in_tests`).
**And** los tests corren con `pytest backend/tests/test_csv_to_canonical.py` sin red ni API key.

---

## Tasks / Subtasks

- [ ] **Task 0: Prompt discovery spike** (AC1, AC5) — **antes** de cablear código.
  - [ ] Iterar 1-2 variaciones del prompt baseline contra 3 PDFs representativos: 1 BCI tarjeta CLP, 1 Santander 0858 multi-currency, 1 PDF "off-convention" (`estado-de-cuenta (NN).pdf`).
  - [ ] Para cada variación: correr 3× con `bootstrap/validate_cartolas_batch.py --pdf X --runs 3` y medir verde/amarillo/rojo + tokens output (proxy: `len(staging_file_json)`).
  - [ ] Elegir el prompt ganador empíricamente: mayor % verde entre los 3 PDFs spike; desempate por menor latencia / tokens.
  - [ ] **Decidir formato fecha**: ¿Gemini emite ISO directo, o el wrapper convierte `DD/MM/YYYY` server-side? Recomendación Bob = wrapper convierte (mismo principio que sign convention: el server absorbe variabilidad de Gemini). Documentar elección.
  - [ ] Documentar variaciones probadas + ganador + decisión fecha en `_bmad-output/coordination/9-5e-prompt-spike-{date}.md`.

- [ ] **Task 1: Rewrite `_build_prompt()` + adapt `extract_pdf()`** (AC1, AC2)
  - [ ] Reemplazar el cuerpo de `_build_prompt(hint: _BankAccountHint) -> str` por el prompt ganador del spike.
  - [ ] Eliminar `_sign_convention_block()` + constante `_LIABILITY_TYPES` (ambas dejan de usarse). Si Amelia prefiere conservarlas como dead code reversible, marcar con docstring `"DEPRECATED 9.5e — kept for rollback only, NOT used by _build_prompt"` y dejarlas. Default: eliminar.
  - [ ] Cambiar firma `extract_pdf(self, pdf_bytes: bytes) -> str` (sin los 6 kwargs de cuenta).
  - [ ] Cambiar `response_mime_type="application/json"` → `"text/plain"`. Verificar que no exista `response_schema` (no aparece en el código actual; defensive check).
  - [ ] Ajustar docstring + type hints.
  - [ ] Test del tamaño: `assert len(_build_prompt(hint).encode("utf-8")) <= 1500`.
  - [ ] Test de ausencia de strings prohibidos: lista exacta = `["Liabilities", "Assets", "Pago Automático", "cuota X/N", "PARSE_AMBIGUOUS", "BALANCE_MISMATCH", "balances.closing", "sum(transactions)", "Verificá ANTES"]`. Cada uno se chequea contra el output de `_build_prompt(...)`. Lista conservadora — son strings inequívocamente del prompt 9.5 viejo, improbables en un prompt liviano correcto.

- [ ] **Task 2: Crear `backend/app/integrations/csv_to_canonical.py`** (AC3)
  - [ ] Excepción nueva: `class CsvParseError(Exception)` con atributos `code: str` y `detail: str`.
  - [ ] Función pública `csv_to_canonical(raw: str, entry: BankAccountEntry, *, model: str, extracted_at: datetime) -> CartolaCanonicalV1`.
  - [ ] Helper `_split_header_and_body(raw: str) -> tuple[dict, str]` — parte por línea literal `---` (whitespace permitido al inicio/final de esa línea).
  - [ ] Helper `_parse_csv_body(body: str) -> list[dict]` — `csv.DictReader` con validación de columnas exactas.
  - [ ] Helper `_normalize_amount(raw: str) -> Decimal` — maneja separadores de miles chilenos (`"1.234.567"` o `"1.234.567,89"`) + signo negativo + paréntesis si aparece.
  - [ ] Helper `_normalize_date(raw: str) -> date` — según decisión Task 0 (ISO directo, **o** conversión DD/MM con inferencia de año desde `period_start` del header).
  - [ ] **NO** importar `GeminiClient`. Módulo puro: `(str, BankAccountEntry) → CartolaCanonicalV1`.

- [ ] **Task 3: Adapt `service.py:process_upload_sync`** (AC4)
  - [ ] Reemplazar `raw_dict = gemini.extract_pdf(pdf_bytes=..., bank_account_id=..., ...)` por `raw_str = gemini.extract_pdf(pdf_bytes)`.
  - [ ] Reemplazar el bloque `raw_dict["source"] = ...` + `raw_dict.setdefault(...)` + `CartolaCanonicalV1.model_validate(raw_dict)` por `canonical = csv_to_canonical(raw_str, bank_account_entry)`.
  - [ ] Mantener el override server-side de `extraction.model` y `extraction.extracted_at` (post-`csv_to_canonical`, pre-`apply_post_process`). Misma semántica que hoy.
  - [ ] En `run_job`: agregar `except CsvParseError as exc: _job_store.set_failed(batch_id, "EXTRACTION_FAILED", f"{exc.code}: {exc.detail}")`. Logger.error análogo a `GeminiExtractionError`.

- [ ] **Task 4: Tests `csv_to_canonical`** (AC7)
  - [ ] `backend/tests/test_csv_to_canonical.py` con los 10+ casos listados en AC7.
  - [ ] Guard AST: ningún test instancia `GeminiClient`.
  - [ ] Fixtures sintéticas: armar strings `"<header_json>\n---\n<csv_body>"` a mano (sin tocar Gemini).

- [ ] **Task 5: Actualizar tests existentes que mockean `extract_pdf`** (AC6)
  - [ ] Identificar todos: `grep -rn "extract_pdf" backend/tests/`.
  - [ ] Cambiar el `return_value` del mock de dict canónico a string format nueva.
  - [ ] NO cambiar lo que cada test verifica.
  - [ ] Suite completa: `pytest backend/tests/` → 322 viejos verde + tests nuevos verde.

- [ ] **Task 6: Smoke real 14 PDFs** (AC5 — manual por Ary)
  - [ ] Completion Notes con instrucciones operativas: comando exacto, currency overrides para los 14 PDFs, dónde leer el reporte.
  - [ ] Ary lee `report.md`, registra en el Change Log de este storyfile.
  - [ ] Si <90% verde → iterar Task 0 (sólo el prompt; Tasks 1-5 quedan estables) y re-correr. NO marcar AC5 hasta ≥90%.

---

## Dev Notes

### Reuso obligatorio — NO reimplementar

- `BankAccountEntry` (`backend/app/integrations/bank_account_index.py`) — passthrough, sin cambios.
- `CartolaCanonicalV1`, `CartolaSource`, `CartolaPeriod`, `CartolaBalances`, `CartolaTransaction`, `CartolaWarning`, `CartolaExtraction` (`backend/app/integrations/cartola_schema.py`) — **sin cambios**. Shape final intacto.
- `apply_post_process` y `detect_balance_mismatch` (`backend/app/integrations/cartola_post_process.py:75,129`) — **única fuente de verdad** del balance check. **NO** duplicar lógica en el wrapper.
- `BALANCE_MISMATCH_TOLERANCE_CLP` — importar (no duplicar).
- `resolve_source_dict` (`backend/app/api/v1/cartolas/service.py:179`) — reusar tal cual para armar `source`.
- `write_staging_file` (`service.py:193`) — sin cambios.
- Tooling de medición: `bootstrap/validate_cartolas_batch.py` (37 tests verde, 9.5c entregada). NO modificar; es el único oráculo que decide AC5.

### Anti-patrón explícito: sign convention speculative

**NO agregar lógica de inversión de signo en `csv_to_canonical.py`** salvo que la re-corrida 9.5c lo justifique empíricamente con datos. Hipótesis (validada por BCI 9.5 cierre 2026-05-06: `closing - opening = sum(tx)` exacto, signos consistentes con convención Liabilities natural): los PDFs chilenos ya emiten signos compatibles. Si un banco específico viola esto post-9.5e → tratarlo como bug específico documentado, no como guard prematuro.

### Anti-patrón explícito: prompt verboso

Si el prompt ganador de Task 0 mide >1500 bytes, **NO** subir el límite del test. Re-iterar el prompt — la métrica de tamaño es proxy de "contaminación residual". El prompt corto de Gemini web (~200 bytes) es el norte; 1500 bytes ya da margen razonable.

### Decisión pendiente — formato fecha (Task 0 la cierra)

Dos opciones:
- **(a) ISO directo**: prompt agrega 1 línea ("emite fechas en YYYY-MM-DD"); parser server-side simple. Riesgo: Gemini puede ignorar el hint y emitir DD/MM igual.
- **(b) Wrapper convierte**: prompt no menciona formato; parser server-side maneja `DD/MM/YYYY`, `DD-MM-YY`, `DD/MM` (con inferencia de año desde `period_start` del header). Más robusto.

**Recomendación Bob: (b)** — mismo principio que sign convention: el server absorbe variabilidad de Gemini. Amelia confirma o pivotea durante el spike.

### Decisión pendiente — multi-currency dominante (definida acá)

`CartolaCanonicalV1.currency` (top-level) es enum cerrado `Literal["CLP", "USD", "EUR"]`. Resolución:
- Top-level = lo que Gemini detectó como dominante en el header JSON.
- Per-tx = de la columna `currency` del CSV.
- Si top-level ≠ moneda de ≥1 tx → warning `PARSE_AMBIGUOUS` con detail `"multi-currency: N tx en {sorted_set}"`.
- Si el header dice `CLP` pero el 100% de las tx son USD → el wrapper **no** "corrige" el top-level. Emite warning y deja la decisión operacional al operador via 9.6b matching downstream. Out of scope: detección de top-level "incorrecto" — eso es hipotético 9.5f si aparece como issue real.

### Estructura del repo después de 9.5e

```
backend/app/integrations/
  gemini_client.py                   # MODIFIED — prompt nuevo + response_mime_type=text/plain + extract_pdf devuelve str
  csv_to_canonical.py                # NEW — wrapper Gemini-output → CartolaCanonicalV1
  cartola_schema.py                  # SIN CAMBIOS
  cartola_post_process.py            # SIN CAMBIOS
  bank_account_index.py              # SIN CAMBIOS
backend/app/api/v1/cartolas/
  service.py                         # MODIFIED — process_upload_sync llama csv_to_canonical
backend/tests/
  test_gemini_client.py              # MODIFIED — tests del prompt nuevo (≤1500 bytes, sin strings prohibidos)
  test_csv_to_canonical.py           # NEW — 10+ tests del wrapper
  test_cartolas_router.py            # MODIFIED — mocks de extract_pdf devuelven string nueva
  test_cartolas_service.py           # MODIFIED — idem
  (otros que mockean extract_pdf)    # MODIFIED — idem
_bmad-output/coordination/
  9-5e-prompt-spike-{date}.md        # NEW — coord file del spike Task 0
```

### Out of scope

- **Streaming response** — el SDK Python actual no streamea; `generate_content_stream` es scope de 9.5f si vale la pena.
- **Parallelism cross-PDF** — secuencial; mejora futura.
- **Prompt caching de Google** — feature SDK; mejora futura.
- **Cambios al `CartolaCanonicalV1` schema** — preserva compat con 9.6a. Si el spike sugiere agregar `raw` data útil per-tx → evaluar **post-9.6a verde**, no acá.
- **Detección automática de bank_account desde contenido del PDF** — Story 9.5b (parqueado, depende de last4 poblado en 9.3 AC8).
- **Retry con feedback a Gemini** — Story 9.5d **superseded por 9.5e** (retry sobre un prompt malo da resultados malos × 2). Si post-9.5e la corrida muestra <90% pero el problema es robustez de Gemini (no prompt) → 9.5d se re-evalúa como Story nueva con scope distinto.
- **Validación de "top-level currency incorrecto" en multi-currency** — fuera de scope; tratar via 9.6b matching o 9.5f si aparece como issue real.

### Referencias

- Coord file autoritativo: `_bmad-output/coordination/9-5c-hallazgo-prompt-2026-05-19.md`
- Storyfile 9.5c (smoke real + staging evidence): `_bmad-output/implementation-artifacts/9-5c-validation-tooling-extraccion-ml.md`
- Storyfile 9.5 (predecesor con el prompt actual): `_bmad-output/implementation-artifacts/9-5-pdf-upload-gemini-json-canonico.md`
- Shape canónico autoritativo: `_bmad-output/planning-artifacts/architecture-c4.md` §4.1
- Tooling de medición: `bootstrap/validate_cartolas_batch.py` + `backend/tests/test_validate_cartolas_batch.py`
- Staging evidence smoke 2026-05-19 (33 archivos preservados): `_bmad-output/validation-runs/2026-05-19-135748/staging/`
- Memory: `project_epic9_validacion_cartolas` (hallazgo + decisión 9.5e)

---

## Dev Agent Record

### Agent Model Used

<!-- to fill in by dev agent on dispatch -->

### Debug Log References

<!-- to fill in by dev agent -->

### Completion Notes List

<!-- to fill in by dev agent -->

### File List

<!-- to fill in by dev agent -->

### Change Log

| Date       | Author                       | Change                                                                                                                                                                                                                                                                  |
|------------|------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 2026-05-19 | Bob (claude-opus-4-7[1m])    | Story creada. Base: coord file `9-5c-hallazgo-prompt-2026-05-19.md` + decisiones de diseño Ary durante sesión Bob 2026-05-19 (amount-con-signo único columna, header JSON + `---` + CSV, multi-currency con warning, prompt seed empírico no literal, spike en Task 0). |
