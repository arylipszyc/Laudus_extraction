---
story: 9.5h
title: Validators deterministas + switch a gemini-3.5-flash (Path #1)
status: done
epic: 9
depends_on: [9.5c, 9.5f, 9.5g]
blocks: [9.6a]   # 9.6a desbloqueado 2026-05-31 — re-corrida ≥90% verde alcanzada (13/14 = 92.9%).
parallelizable_with: [9.2, 9.3, 9.4, 9.6b, 9.7, 9.8, 9.9, 9.11, 9.12]
---

# Story 9.5h — Validators deterministas + switch a gemini-3.5-flash (Path #1)

## Story

As Ary (single operator del Family Office),
I want que el pipeline de extracción use `gemini-3.5-flash` por default, que los warnings espurios (PARSE_AMBIGUOUS sobre-emitido + PERIOD_MISMATCH por cuotas pre-existentes) dejen de bloquear el verde, y que un retry acotado absorba los fallos transitorios de Gemini (línea omitida ocasional + JSON truncado ocasional),
so that la validación de cartolas suba del **85.7% verde** medido en el spike 9.5g a **≥90% verde** (objetivo ~100%) sobre los 14 PDFs reales de `samples/`, desbloqueando 9.6a (importer beangulp) sin reescribir el prompt entero (9.5e superseded) ni inflar el scope a retry-sobre-prompt-malo (9.5d superseded).

## Context

Sale directamente de los spikes 9.5f (Tier 1 SDK params) y 9.5g (comparación de modelos). Coord files autoritativos:

- `_bmad-output/coordination/9-5f-spike-tier1-results-2026-05-20.md`
- `_bmad-output/coordination/9-5g-spike-flash-3-5-results-2026-05-20.md`

**Hallazgos del spike (medidos, no asumidos):**

1. **`gemini-3.5-flash` es el ganador claro.** Sobre 14 PDFs × 3 runs con los params Tier 1 ya commiteados en el branch `spike/9-5f-tier1-gemini-api-params` (T=0.1, max_output_tokens=32768, `contents=[pdf_part, prompt]`): **95% de los runs con `diff=0` exacto** (iguala a `gemini-2.5-pro`), 5× más barato que Pro, 37% menos latencia, sólo 2 runs con BALANCE_MISMATCH (vs 4 de Pro). El default actual `gemini-2.5-flash` daba ~76% diff=0. **La extracción de Flash 3.5 es matemáticamente correcta** — el problema NO es la extracción.

2. **El cuello del 85.7% al 100% son 2 fuentes de ruido + 2 fallos transitorios** (ver reporte `_bmad-output/validation-runs/9-5g-after-flash-3-5/report.md`):
   - **PARSE_AMBIGUOUS espurio**: emitido por Gemini en ~41/42 runs porque el prompt 9.5 se lo pide explícitamente ("PARSE_AMBIGUOUS: estructura del PDF inusual" — `gemini_client.py:206`). Es ruido: los PDFs no tienen estructura genuinamente ambigua, Gemini lo emite religiosamente.
   - **PERIOD_MISMATCH espurio**: emitido por el post-process (`cartola_post_process.py:50`) cuando una transacción tiene `date < period.start`. Causa principal: cuotas pre-existentes X/N con `date = fecha de operación original` (legítimamente anterior al período de la cartola — ver instrucción del prompt `gemini_client.py:140-142`). La transacción SÍ pertenece a la cartola (se cobra ahora); sólo su fecha es histórica.
   - **2 PDFs rojos inestables** (cada uno 2/3 runs OK):
     - `bci-visa-202604.pdf`: opening/closing idénticos en los 3 runs; en 1/3 runs Gemini **omitió 1 transacción** de ~$33.943 → `BALANCE_MISMATCH` (el detector funcionó correctamente). 2/3 runs perfectos con 37 tx.
     - `santander-mastercard-202604.pdf`: 2/3 runs perfectos (45 tx, diff=0); en 1/3 runs el **output JSON se cortó** (`Unterminated string at char 2948`, ~37% del largo esperado — corte temprano transitorio, NO el cap de 32k tokens).

3. **Ambos fallos transitorios son no-sistemáticos** — cada PDF sale limpio en 2/3 draws independientes. No hay nada roto; es no-determinismo del modelo que golpea ~1/3 de las veces.

**Decisión Ary 2026-05-28 (esta sesión):** apuntar a un valor más alto **sin bajar el gate**. Atacar las 4 causas en su raíz: switch de modelo + silenciar 2 warnings espurios en su fuente + retry acotado sobre fallo transitorio. El classifier de medición (`validate_cartolas_batch.py`) **NO se toca** — silenciamos en la fuente, no gameamos el oráculo.

**Por qué el retry ahora SÍ (vs 9.5d superseded):** 9.5d se descartó porque era "retry sobre un prompt malo → resultado malo × 2". Acá el modelo ya es bueno (95% diff=0); un retry sobre un fallo transitorio (línea omitida / JSON truncado) tiene alta probabilidad de salir limpio en un draw independiente. La propia nota de cierre de 9.5d previó este caso: *"si post-fix queda BALANCE_MISMATCH legítimo (Gemini robusto pero PDF ambiguo) → re-evaluar 9.5d como story nueva con scope distinto."*

## Acceptance Criteria

**AC1 — `gemini-3.5-flash` como `DEFAULT_MODEL` + params Tier 1 preservados**

**Given** `backend/app/integrations/gemini_client.py`
**When** Amelia ajusta la config del modelo
**Then** `DEFAULT_MODEL` (línea 16) cambia su default de `"gemini-2.5-flash"` a `"gemini-3.5-flash"`.
**And** el override por env var se preserva: `os.getenv("GEMINI_MODEL", "gemini-3.5-flash")` — permite forzar `gemini-2.5-pro` como upgrade reserve sin tocar código.
**And** los 3 params Tier 1 ya commiteados en el branch se **preservan** en el `GenerateContentConfig`: `temperature=0.1`, `max_output_tokens=32768`, y `contents=[pdf_part, prompt]` (PDF primero). NO revertir a baseline.
**And** un test unitario verifica que `GeminiClient(...).model == "gemini-3.5-flash"` cuando no hay env var, y que respeta `GEMINI_MODEL` cuando está seteada.

---

**AC2 — El prompt deja de instruir a Gemini a emitir PARSE_AMBIGUOUS por "estructura inusual"**

**Given** `_build_prompt()` en `gemini_client.py`
**When** Amelia identifica la(s) fuente(s) de PARSE_AMBIGUOUS espurio
**Then** **antes** de editar, Amelia inspecciona el `detail` de 3-4 warnings PARSE_AMBIGUOUS en el staging del run 9.5g (`_bmad-output/validation-runs/9-5g-after-flash-3-5/staging/`) para confirmar la fuente real (instrucción #12 genérica vs `last4_clause`).
**And** se elimina la instrucción que pide emitir `PARSE_AMBIGUOUS` por "estructura del PDF inusual" (instrucción #12, `gemini_client.py:203-207`). El código `LOW_CONFIDENCE` se preserva (es el único warning legítimo que Gemini debe emitir: línea genuinamente ilegible/ambigua).
**And** el `last4_clause` (`gemini_client.py:99-105`): si la inspección confirma que es fuente de PARSE_AMBIGUOUS masivo (porque los `last4` del índice no matchean o están null — 9.3 AC8 pendiente), se neutraliza hasta que los last4 estén poblados: bajar a `LOW_CONFIDENCE` o quitar la cláusula de emisión. Documentar la decisión en Completion Notes con la evidencia del staging.
**And** la instrucción #12 sigue enumerando los códigos que el **backend** detecta en post-process (DUPLICATE_LINE, ZERO_AMOUNT, LARGE_AMOUNT, PERIOD_MISMATCH, BALANCE_MISMATCH) con la nota "NO los emitas tú" — eso queda igual.
**And** un test del prompt verifica que `"PARSE_AMBIGUOUS"` ya NO aparece como instrucción de emisión activa para Gemini (puede seguir apareciendo en la lista de enums cerrados y en la lista de "los detecta el backend").

---

**AC3 — `detect_period_mismatch` excluye cuotas pre-existentes (sin apagar el check)**

**Given** `detect_period_mismatch()` en `backend/app/integrations/cartola_post_process.py:50`
**When** Amelia refina la lógica
**Then** la función **excluye del check** las transacciones identificables como cuotas pre-existentes X/N, cuya fecha es legítimamente anterior al período. La señal de "es cuota" se deriva del output del prompt actual (`gemini_client.py:142, 177-179`), en este orden de preferencia:
1. `tx.raw.get("operation_type") == "cuota"`, **o**
2. `tx.raw.get("cuotas")` presente (formato `"X/N"`), **o**
3. fallback: la `description` matchea el sufijo `" (cuota X/N)"` (regex `\(cuota \d+/\d+\)`).
**And** el check **se mantiene activo** para todas las demás transacciones: si una transacción NO-cuota tiene `date < period.start` o `date > period.end` → sigue disparando `PERIOD_MISMATCH` (atrapa años alucinados, tx asignadas al período equivocado). NO se borra el check.
**And** el cálculo de `first`/`last` para el check se hace **sobre el subconjunto no-cuota**. Si todas las transacciones son cuotas → no se emite PERIOD_MISMATCH (lista vacía tras filtrar).
**And** el `detail` del warning, cuando dispara, se mantiene informativo (fecha + límite del período).

---

**AC4 — Retry acotado sobre fallo transitorio en `process_upload_sync`**

**Given** `process_upload_sync()` en `backend/app/api/v1/cartolas/service.py:214-253`
**When** Amelia agrega el retry
**Then** el bloque extract → validate → post-process se envuelve en un loop de **máximo `MAX_EXTRACTION_ATTEMPTS` intentos** (constante de módulo, default `3`). Un intento se considera **fallido y reintentable** si:
- `gemini.extract_pdf(...)` levanta `GeminiExtractionError` (JSON truncado/inválido), **o**
- el `CartolaCanonicalV1` resultante (post `apply_post_process`) contiene un warning `BALANCE_MISMATCH`.
**And** en cada reintento se hace un **draw independiente** (nueva llamada a `extract_pdf`) — NO se le pasa el error de vuelta a Gemini (eso era 9.5d). El `temperature=0.1` ya da variación entre draws.
**And** el loop **corta apenas obtiene un resultado limpio** (sin `GeminiExtractionError` y sin `BALANCE_MISMATCH`). Devuelve ese resultado.
**And** si los `MAX_EXTRACTION_ATTEMPTS` intentos se agotan: devuelve el **mejor** resultado obtenido (el último canonical válido sin BALANCE_MISMATCH si lo hubo; si todos tuvieron BALANCE_MISMATCH, el último válido **con** su warning preservado). Un `BALANCE_MISMATCH` que persiste tras N intentos es legítimo (PDF genuinamente descuadrado, ej. Santander documentado en cierre 9.5) y se surfacea al operador vía warning, NO se oculta.
**And** si los N intentos levantan `GeminiExtractionError` (nunca hubo canonical válido) → se propaga `GeminiExtractionError` al `run_job` (mismo flujo de error actual, `service.py:280`).
**And** cada reintento loguea a nivel `warning` con `batch_id` + razón (`balance_mismatch` / `extraction_error`) + nº de intento. Sin loguear el PDF ni payloads sensibles.
**And** la firma pública de `process_upload_sync` y `run_job` **NO cambia**. Los endpoints HTTP, response shapes y job-store API quedan idénticos.

---

**AC5 — Re-corrida 9.5c con los 4 cambios: gate ≥90% verde (per-PDF estricto)**

**Given** los 14 PDFs en `samples/` con los currency overrides usados en el spike 9.5g
**When** Ary corre `python -m bootstrap.validate_cartolas_batch samples/ --runs 3` post-implementación de 9.5h
**Then** el `report.md` generado en `_bmad-output/validation-runs/{timestamp}/` muestra `Gate (≥90% verde): PASS`.
**And** el classifier de `validate_cartolas_batch.py` **NO se modifica** — el verde sube porque los warnings espurios dejaron de emitirse en la fuente (AC2, AC3) y los 2 inestables se estabilizaron vía retry (AC4), no porque se relajó el oráculo.
**And** Ary registra en el Change Log de este storyfile: % verde / amarillo / rojo, qué PDFs (si alguno) quedaron amarillo/rojo y por qué, y la decisión (dispatch 9.6a directo / iterar). Lo completa **Ary leyendo el reporte**, NO el dev agent durante implementación.
**And** si el primer pase da <90% verde → **no es failure del dev agent**. Es señal para diagnosticar el residual (¿warning no contemplado? ¿retry insuficiente? ¿DUPLICATE_LINE en estado-de-cuenta (24)?). El AC se marca cumplido **sólo cuando** la corrida final muestra ≥90% verde.

---

**AC6 — NO romper la suite existente ni el shape canónico ni los endpoints HTTP**

**Given** la suite backend de Story 9.5 (322 verde en cierre 2026-05-06) + endpoints `/api/v1/cartolas/upload` + `/jobs/{batch_id}`
**When** Amelia termina 9.5h
**Then** los tests existentes siguen verdes **sin cambiar lo que cada test verifica**. Los tests que mockean `extract_pdf` o que asumen emisión de PARSE_AMBIGUOUS/PERIOD_MISMATCH se actualizan **mínimamente** para reflejar AC2/AC3 (reemplazo puntual, no eliminación bulk).
**And** `CartolaCanonicalV1` y el resto de `cartola_schema.py` **NO se modifican**.
**And** los endpoints HTTP NO cambian: misma URL, misma request shape (multipart `pdf` + `bank_account_id`), misma response shape (`{batch_id, status}` + polling).
**And** la firma de `extract_pdf` **NO cambia** (sigue recibiendo los kwargs de cuenta) — 9.5h NO reescribe el prompt a CSV (eso era 9.5e, superseded). El prompt sigue produciendo el JSON canónico; sólo se le saca la instrucción de PARSE_AMBIGUOUS.

---

**AC7 — Tests unitarios para los validators refinados + el retry**

**Given** los cambios de AC3 (PERIOD_MISMATCH cuota-aware) y AC4 (retry)
**When** Amelia agrega tests
**Then** tests de `detect_period_mismatch` (en el archivo de tests existente de post-process):
- Cuota pre-existente con `date < period.start` identificada por `raw.operation_type="cuota"` → NO emite PERIOD_MISMATCH.
- Cuota identificada por `raw.cuotas="3/6"` → NO emite.
- Cuota identificada sólo por sufijo `" (cuota 3/6)"` en description (sin raw) → NO emite.
- Transacción NO-cuota con `date < period.start` → SÍ emite PERIOD_MISMATCH.
- Transacción NO-cuota con `date > period.end` → SÍ emite.
- Mix (1 cuota fuera de período + 1 compra normal dentro) → NO emite (la única fuera es cuota).
- Todas cuotas, todas fuera de período → NO emite.
**And** tests del retry (en el archivo de tests de service): con un `GeminiClient` mockeado que devuelve secuencias controladas:
- 1er intento BALANCE_MISMATCH, 2º intento limpio → devuelve el limpio, 2 llamadas a extract_pdf.
- 1er intento `GeminiExtractionError`, 2º intento limpio → devuelve el limpio.
- Los 3 intentos con BALANCE_MISMATCH → devuelve el último válido CON el warning preservado (no oculta, no levanta).
- Los 3 intentos `GeminiExtractionError` → propaga `GeminiExtractionError`.
- 1er intento limpio → 1 sola llamada (corta temprano, no reintenta).
**And** ningún test nuevo hace llamadas reales a Gemini ni requiere API key.

---

## Tasks / Subtasks

- [x] **Task 1: Switch de modelo + preservar Tier 1** (AC1)
  - [x] `DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")`.
  - [x] Verificar que `GenerateContentConfig` conserva `temperature=0.1`, `max_output_tokens=32768`, y `contents=[pdf_part, prompt]`.
  - [x] Test del default + override por env var.

- [x] **Task 2: Sacar PARSE_AMBIGUOUS espurio del prompt** (AC2)
  - [x] Inspeccionar `detail` de warnings PARSE_AMBIGUOUS en `_bmad-output/validation-runs/9-5g-after-flash-3-5/staging/` (3-4 ejemplos) para confirmar fuente.
  - [x] Eliminar la instrucción de emisión #12 (`gemini_client.py:203-207`) para PARSE_AMBIGUOUS; preservar LOW_CONFIDENCE.
  - [x] Decidir destino del `last4_clause` según evidencia (neutralizar si es fuente masiva con last4 null/no-match). Documentar en Completion Notes.
  - [x] Actualizar/reescribir el test del prompt que corresponda.

- [x] **Task 3: PERIOD_MISMATCH cuota-aware** (AC3)
  - [x] Helper `_is_preexisting_installment(tx) -> bool` con las 3 señales (raw.operation_type / raw.cuotas / regex sufijo description).
  - [x] Filtrar el subconjunto no-cuota antes de calcular `first`/`last`.
  - [x] Mantener el check activo para no-cuotas. Lista vacía si todas son cuotas.

- [x] **Task 4: Retry acotado en `process_upload_sync`** (AC4)
  - [x] Constante `MAX_EXTRACTION_ATTEMPTS = 3`.
  - [x] Loop: extract → overrides server-side → validate → post-process; reintentable si `GeminiExtractionError` o BALANCE_MISMATCH en el canonical.
  - [x] Corte temprano en resultado limpio; al agotar, devolver mejor resultado (warning preservado si persiste).
  - [x] Logging por reintento (batch_id + razón + intento), sin payloads.
  - [x] Firma pública intacta.

- [x] **Task 5: Tests** (AC7)
  - [x] Casos de `detect_period_mismatch` cuota-aware.
  - [x] Casos del retry con `GeminiClient` mockeado (secuencias controladas).
  - [x] Guard: sin llamadas reales a Gemini.

- [x] **Task 6: No-regresión** (AC6)
  - [x] `grep -rn "PARSE_AMBIGUOUS\|PERIOD_MISMATCH\|extract_pdf" backend/tests/` → ajustar mínimamente los tests afectados.
  - [x] `pytest backend/tests/` → suite verde (393 passed; fallos restantes pre-existentes/de entorno, ver Completion Notes).

- [x] **Task 7: Smoke real 14 PDFs + decisión de merge** (AC5 — completado 2026-05-31)
  - [x] Pass 1 (2026-05-29): 6/14 verde (42.9%), FAIL. Diagnóstico: PERIOD_MISMATCH dominante NO eran cuotas — eran tx normales 1-5 días antes de `period.start` (slop de corte de facturación TC chilenas). AC3 cuota-aware funcionó (verificado con BCI: cuotas 2024/2025 correctamente excluidas), pero atacó causa secundaria.
  - [x] Iteración (Ary 2026-05-29 → 2026-05-31): regla nueva en `detect_period_mismatch` — dispara sólo si ≥80% de tx no-cuota fuera del período. Coverage residual (años alucinados en pocas líneas) se mitiga vía UI post-upload (deferred — ver `deferred-work.md`).
  - [x] Pass 2 (2026-05-31): **13/14 verde (92.9%), gate ≥90% PASS**. Único amarillo: `estado-de-cuenta (24).pdf` con `DUPLICATE_LINE` — residual aceptable per Dev Notes.
  - [x] Merge del branch `spike/9-5f-tier1-gemini-api-params` → `main` + desbloqueo de 9.6a.

---

## Dev Notes

### Reuso obligatorio — NO reimplementar

- `apply_post_process` y los detectores de `cartola_post_process.py` — el único cambio es refinar `detect_period_mismatch`. NO duplicar lógica de balance en otro lado.
- `detect_balance_mismatch` (`cartola_post_process.py:75`) — **única fuente de verdad** del balance check. El retry de AC4 **lee** su resultado (¿hay warning BALANCE_MISMATCH?), no reimplementa el cálculo.
- `CartolaCanonicalV1` y `cartola_schema.py` — **sin cambios**.
- `resolve_source_dict`, `write_staging_file` (`service.py:179, 193`) — sin cambios.
- Tooling de medición `bootstrap/validate_cartolas_batch.py` + su `classify_pdf` — **NO modificar**. Es el oráculo que decide AC5; tocarlo invalidaría la medición.

### Anti-patrón explícito: gamear el classifier

El verde NO se sube relajando `classify_pdf` para que `diff=0 + warnings = VERDE`. Se sube **silenciando los warnings espurios en su fuente** (prompt + post-process). Razón: el classifier es el oráculo de medición; si lo aflojamos, perdemos la señal y el verde deja de significar "extracción limpia". Si tras AC2/AC3/AC4 algún warning legítimo distinto aparece y bloquea verde, se discute como hallazgo nuevo — no se silencia el classifier.

### Anti-patrón explícito: retry-con-feedback (9.5d)

El retry de AC4 hace **draws independientes** — NO le devuelve a Gemini "te faltó una línea, reintentá". Eso era 9.5d (superseded: retry sobre prompt malo = malo × 2). Acá el modelo es bueno; cada draw independiente tiene ~95% de salir limpio, así que 2-3 draws bastan para los casos transitorios.

### Por qué NO reescribir el prompt a CSV (9.5e superseded)

El spike 9.5g probó que con Flash 3.5 + JSON la extracción cuadra al 95%. El JSON truncado de Santander es un fallo **transitorio** (1/3 runs), no sistemático — el retry lo cubre con mucho menos riesgo que reescribir el pipeline a CSV (nuevo módulo `csv_to_canonical`, nuevo formato de prompt, 322 tests a re-mockear). 9.5e queda como evidencia histórica.

### Residual conocido: DUPLICATE_LINE en estado-de-cuenta (24)

`estado-de-cuenta (24).pdf` emite `DUPLICATE_LINE×12` (4 dupes × 3 runs) con `diff=0`. El spike sugiere que es **diseño legítimo del PDF** (líneas con mismo date+amount+description). DUPLICATE_LINE NO está en scope de 9.5h. Si ese PDF queda como único amarillo post-9.5h → 13/14 = 92.8% ≥90% PASS igual. Si Ary quiere cerrarlo a 14/14, se evalúa por separado (no bloquea esta story).

### Tabla de impacto esperado (sobre el run 9.5g)

| Fuente | PDFs afectados (9.5g) | Acción 9.5h | Efecto esperado |
|---|---|---|---|
| PARSE_AMBIGUOUS espurio | 14/14 (todos) | AC2 prompt | desaparece → destraba estado-23/26/27 (sólo tenían este) |
| PERIOD_MISMATCH por cuotas | ~10/14 | AC3 cuota-aware | desaparece para cuotas legítimas |
| BCI línea omitida 1/3 | bci-visa | AC4 retry | draw limpio → VERDE |
| Santander JSON truncado 1/3 | santander-mastercard | AC4 retry | draw limpio → VERDE |
| DUPLICATE_LINE | estado-24 | fuera de scope | queda amarillo (aceptable, 92.8% ≥90%) |

### Out of scope

- **Reescritura del prompt a CSV liviano** — 9.5e, superseded.
- **Cambios al classifier de medición** — ver anti-patrón arriba.
- **DUPLICATE_LINE** — residual aceptable; evaluar por separado si se busca 14/14.
- **Auto-detect de bank_account desde el PDF** — 9.5b (parqueado, depende de 9.3 AC8).
- **`gemini-2.5-pro` como default** — queda como upgrade reserve vía `GEMINI_MODEL` env var, no default (5× más caro, sin ganancia de calidad sobre Flash 3.5).
- **Streaming / prompt caching** — mejoras futuras del SDK.

### Referencias

- Spike Tier 1 (params SDK): `_bmad-output/coordination/9-5f-spike-tier1-results-2026-05-20.md`
- Spike Flash 3.5 (modelo ganador): `_bmad-output/coordination/9-5g-spike-flash-3-5-results-2026-05-20.md`
- Reporte con los 14 PDFs medidos: `_bmad-output/validation-runs/9-5g-after-flash-3-5/report.md` + `staging/`
- Storyfile 9.5e (CSV liviano, superseded — evidencia): `_bmad-output/implementation-artifacts/9-5e-prompt-gemini-csv-liviano-wrapping-server-side.md`
- Storyfile 9.5 (predecesor, prompt actual): `_bmad-output/implementation-artifacts/9-5-pdf-upload-gemini-json-canonico.md`
- Tooling de medición: `bootstrap/validate_cartolas_batch.py` + `backend/tests/test_validate_cartolas_batch.py`
- Branch con Tier 1 ya commiteado: `spike/9-5f-tier1-gemini-api-params`
- Memory: `project_epic9_validacion_cartolas`

---

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Claude Code dev-story)

### Debug Log References

- Suite backend: `venv/Scripts/python.exe -m pytest backend/tests/ --ignore=backend/tests/test_fava_edit_validator.py --ignore=backend/tests/test_validate_cuadratura.py` → **393 passed**.
- Tests focales: `test_gemini_client.py` 22/22, `test_cartola_post_process.py` 31/31, `test_cartolas_service.py` 5/5.

### Completion Notes List

**Tasks 1-6 (código) completas. Task 7 (smoke real + merge) PENDIENTE — manual por Ary (requiere API key Gemini real, fuera del alcance del dev agent).**

- **Task 1 (AC1):** `DEFAULT_MODEL` → `gemini-3.5-flash` ([gemini_client.py:16](backend/app/integrations/gemini_client.py#L16)). Params Tier 1 verificados intactos en `GenerateContentConfig` (T=0.1, max_output_tokens=32768, `contents=[pdf_part, prompt]`). Override por `GEMINI_MODEL` preservado (testeado vía subprocess para aislar la resolución en import time).
- **Task 2 (AC2):** Inspección del staging 9.5g reveló que el **100% de los PARSE_AMBIGUOUS venían del `last4_clause`**, NO de la instrucción #12. Causa: el tooling de smoke usa `last4="9999"` dummy ([validate_cartolas_batch.py:163-164](bootstrap/validate_cartolas_batch.py#L163-L164)) que no matchea ningún PDF real, y Gemini reportaba el mismatch en los 14. Decisión: (a) `last4_clause` queda como contexto informativo sin pedir emisión de warning (el match de cuenta es decisión del operador/server-side, no de Gemini); (b) instrucción #12 también deja de listar PARSE_AMBIGUOUS como emitible (sólo LOW_CONFIDENCE), por consistencia con AC2 aunque no fuera la fuente activa.
- **Task 3 (AC3):** `_is_preexisting_installment()` con 3 señales (raw.operation_type=="cuota" / raw.cuotas / regex `\(cuota \d+/\d+\)` en description). `detect_period_mismatch` filtra cuotas antes de calcular first/last; el check sigue activo para no-cuotas (atrapa años alucinados / tx fuera de período). Detail strings sin cambios → cero churn en tests existentes.
- **Task 4 (AC4):** Retry en `process_upload_sync` (max `MAX_EXTRACTION_ATTEMPTS=3`, draws independientes). Reintenta ante `GeminiExtractionError` o BALANCE_MISMATCH; corta en limpio; al agotar devuelve el mejor canonical válido (mismatch persistente se surfacea, no se oculta); si nunca hubo válido, propaga `GeminiExtractionError`. `ValidationError` NO se reintenta (propaga). Helper `_extract_and_enrich` factorizado. Firma pública intacta.
- **Task 6 (AC6):** Regresión detectada y arreglada: `test_extract_pdf_passes_pdf_bytes_to_sdk` asumía el orden viejo `contents=[prompt, pdf]` → actualizado al orden Tier 1 `[pdf_part, prompt]` (era uno de los 2 rojos que la memoria del spike anticipó). `CartolaCanonicalV1` y `cartola_schema.py` sin tocar. Endpoints HTTP y firma `extract_pdf` sin cambios.
- **Fallos NO causados por 9.5h (pre-existentes/entorno):** (1) `test_sync.py::test_run_backfill_calls_upsert_for_both_sheets` (`assert 2 == 1` en lógica de backfill de sheets, sin relación con cartolas — ya anotado en memory del spike); (2) collection errors en `test_fava_edit_validator.py` y `test_validate_cuadratura.py` (módulos `fava` y `beanquery` no instalados en el venv).

**Instrucciones para Task 7 (Ary):**
1. Asegurar `GEMINI_API_KEY` seteada y los 14 PDFs en `samples/`.
2. Correr: `venv/Scripts/python.exe -m bootstrap.validate_cartolas_batch samples/ --runs 3` con los mismos `--override` de currency/last4 del spike 9.5g (ver `9-5g-spike-flash-3-5-handoff-2026-05-20.md`). **Nota:** si los PDFs no tienen `--override` con last4 real, el tooling usa `9999` dummy — pero como 9.5h ya no emite PARSE_AMBIGUOUS por ese mismatch, deja de ser ruido.
3. Leer `report.md` en `_bmad-output/validation-runs/{timestamp}/`. Verificar `Gate (≥90% verde): PASS`.
4. Registrar % verde/amarillo/rojo + decisión en el Change Log.
5. Con ≥90%: mergear `spike/9-5f-tier1-gemini-api-params` a `main` y desbloquear 9.6a.

### File List

- `backend/app/integrations/gemini_client.py` (MODIFIED — DEFAULT_MODEL + prompt sin PARSE_AMBIGUOUS)
- `backend/app/integrations/cartola_post_process.py` (MODIFIED — `_is_preexisting_installment` + detect_period_mismatch cuota-aware)
- `backend/app/api/v1/cartolas/service.py` (MODIFIED — `MAX_EXTRACTION_ATTEMPTS`, `_has_balance_mismatch`, `_extract_and_enrich`, retry en process_upload_sync)
- `backend/tests/test_gemini_client.py` (MODIFIED — tests AC1/AC2 + fix orden contents)
- `backend/tests/test_cartola_post_process.py` (MODIFIED — 7 tests cuota-aware)
- `backend/tests/test_cartolas_service.py` (NEW — 5 tests del retry)

### Change Log

| Date       | Author                    | Change                                                                                                                                                                                                                                                                                  |
|------------|---------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 2026-05-28 | Claude (create-story)     | Story creada. Base: spikes 9.5f/9.5g (Flash 3.5 ganador + diagnóstico de los 2 PDFs inestables). Plan aprobado por Ary: switch a gemini-3.5-flash + silenciar PARSE_AMBIGUOUS (prompt) + PERIOD_MISMATCH cuota-aware (post-process) + retry acotado sobre fallo transitorio. Gate per-PDF estricto ≥90% (objetivo ~100%), classifier sin tocar. |
| 2026-05-28 | Claude (dev-story)        | Tasks 1-6 implementadas y testeadas (393 passed backend). Hallazgo: el PARSE_AMBIGUOUS espurio venía 100% del `last4_clause` + dummy `9999` del tooling, no de la instrucción #12 — ambas fuentes neutralizadas. Retry de 3 draws independientes en `process_upload_sync`. Status → review. Task 7 (smoke real ≥90% + merge) PENDIENTE: manual por Ary (requiere Gemini real). |
| 2026-05-28 | Claude (code-review)      | Adversarial 3-layer review (Blind Hunter, Edge Case Hunter, Acceptance Auditor). 0 bloqueantes, 3 patches aplicados, 1 decisión resuelta, 2 deferred, 7 dismissed. Patches: (a) `ValidationError` mid-loop no descarta `last_valid` previo, (b) X≥1 guard en `_is_preexisting_installment` (excluye cuotas futuras 0/N), (c) TODO + nota en 9.3 AC8 para re-habilitar check server-side last4-vs-PDF cuando los last4 estén poblados. +2 tests de cobertura (`test_validation_error_*`). 395 passed. AC1/AC3/AC4/AC6/AC7 plenamente cumplidos verificados contra el código. |
| 2026-05-31 | Claude (smoke iter)       | Smoke pass 1 = 6/14 verde (42.9%, FAIL). Diagnóstico: PERIOD_MISMATCH dominante (7/8 amarillos) era boundary slop de corte de facturación, no cuotas — la story diagnosticó mal el cuello del PERIOD_MISMATCH. Decisión Ary: regla 80% (dispara sólo ante catástrofe del LLM, no por slop de borde) + UI post-upload para revisar/corregir período (deferred). Iter aplicada en `detect_period_mismatch`. 397 passed. Smoke pass 2 = **13/14 verde (92.9%), gate PASS**. Único amarillo: `estado-de-cuenta (24).pdf` con DUPLICATE_LINE (residual aceptable per Dev Notes). Por banco: BCI 1/1, Santander 1/1, Desconocido 4/4, Banco de Chile 7/8. AC5 cumplido. Status → done. 9.6a desbloqueado. |

---

## Review Findings (code review — 2026-05-28, adversarial 3-layer)

**Alcance:** AC1–AC4, AC6, AC7 (AC5 = smoke manual, fuera de alcance). Suite: 393 passed; el único rojo (`test_sync.py::test_run_backfill_calls_upsert_for_both_sheets`) es pre-existente/de entorno, sin relación con 9.5h. **Sin hallazgos bloqueantes.** ACs verificados contra el código (no contra las Completion Notes): AC1, AC3, AC4, AC6, AC7 **plenamente cumplidos**; AC2 funcionalmente cumplido con 1 should-fix (decisión).

### Decision needed → RESUELTO (Ary 2026-05-28: tracking + re-habilitar en 9.3)
- [x] [Review][Decision] `last4_clause` neutralizado de forma **permanente** vs spec "hasta 9.3 AC8" (AC2) — **Resuelto vía Patch 3:** TODO agregado en [gemini_client.py `_build_prompt`](backend/app/integrations/gemini_client.py#L99-L110) + bullet en [9.3 AC8 Task 6](_bmad-output/implementation-artifacts/9-3-fava-deploy-render.md#L151) para re-evaluar un check server-side last4-vs-PDF cuando los last4 reales estén poblados. La detección de cuenta-equivocada quedó **diferida con tracking**, no descartada.

### Patch → APLICADOS (Ary 2026-05-28)
- [x] [Review][Patch] `ValidationError` en un intento posterior descarta un canonical válido previo [backend/app/api/v1/cartolas/service.py:288-298](backend/app/api/v1/cartolas/service.py#L288-L298) — **Aplicado:** `except ValidationError` dentro del loop → `break` si hay `last_valid` (devuelve ese con su warning), `raise` sólo si `last_valid is None`. No se reintenta (AC4) pero no descarta un resultado válido previo.
- [x] [Review][Patch] Cuotas futuras (X=0, "0/N") tratadas como pre-existentes [backend/app/integrations/cartola_post_process.py:23-48](backend/app/integrations/cartola_post_process.py#L23-L48) — **Aplicado:** `_INSTALMENT_DESC_RE` captura X; `_is_preexisting_installment` deriva X de `raw.cuotas`/sufijo y exige X≥1; `operation_type=="cuota"` queda como fallback sin X. Tests existentes verdes (393 passed).

> **Nota de cobertura → CERRADA:** se agregaron 2 tests en `test_cartolas_service.py`: `test_validation_error_after_valid_mismatch_returns_last_valid` (devuelve el último válido con warning) y `test_validation_error_first_attempt_propagates` (sin last_valid → propaga, no reintenta). Suite: **395 passed** (+2), único rojo pre-existente `test_sync.py` sin relación con 9.5h.

### Defer (residual / fuera de scope 9.5h)
- [x] [Review][Defer] Año alucinado en línea de cuota escapa PERIOD_MISMATCH [cartola_post_process.py:73-104](backend/app/integrations/cartola_post_process.py#L73-L104) — La exención de cuotas (AC3, by-design + testeada) crea un punto ciego: una cuota con año alucinado (ej. 2021-02-10 en cartola 2026-03) no dispara el check. El docstring dice "atrapa años alucinados" — sobre-promete para el subconjunto cuota. Mitigación posible (fuera de scope): bound absoluto de fecha que aplique aun a cuotas (ej. no más de N meses antes de period.start).
- [x] [Review][Defer] Retry sobre BALANCE_MISMATCH determinista gasta hasta 3× costo/latencia Gemini [service.py:280](backend/app/api/v1/cartolas/service.py#L280) — Un PDF genuinamente descuadrado (o una línea que el modelo omite consistentemente a T=0.1) corre los 3 draws síncronos y devuelve el mismo warning del intento 1. Optimización posible: early-break si el `detail` del mismatch se repite idéntico entre draws consecutivos.
