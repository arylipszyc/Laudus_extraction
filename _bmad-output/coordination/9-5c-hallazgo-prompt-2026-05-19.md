# 9.5c hallazgo crítico → propuesta Story 9.5e

**Fecha:** 2026-05-19
**Sesión:** Ary + Amelia (claude-opus-4-7[1m])
**Status:** Pendiente decisión de Bob (creación de Story 9.5e)

---

## Contexto

Story 9.5c (validation tooling) entregada con 37 tests verde y `bootstrap/validate_cartolas_batch.py` funcional. Ary corrió el smoke real con los 14 PDFs (con currency overrides correctos por categoría: BCI 9149 CLP/USD + Santander 8996 CLP/USD + Santander **0858** CLP/USD — quinta categoría descubierta durante la sesión y no mencionada en el dispatch original).

**11 PDFs procesados completos + 2 parciales antes de Ctrl+C por Ary** (cancelación deliberada tras detectar patrón sistemático). Resultado:

- **0 PDFs VERDE.**
- ~4 ROJO (BALANCE_MISMATCH).
- ~6 AMARILLO (PARSE_AMBIGUOUS / DUPLICATE_LINE / PERIOD_MISMATCH).
- 1 candidato hipotético a VERDE (`estado-de-cuenta (27).pdf`, sólo 3 transactions, parcial 1 run sin warnings).

Sin reporte `report.md` porque cancelamos antes del writer; los 33 staging files quedaron en `_bmad-output/validation-runs/2026-05-19-135748/staging/` como evidencia.

---

## Hallazgo central

**El prompt elaborado de Story 9.5 está degradando el output de Gemini, no mejorándolo.**

### Evidencia A/B empírica durante la sesión

| Setup | Output | Latencia |
|---|---|---|
| Gemini web, sin contexto, prompt: "extrae en CSV" | Limpio, sin errores | **3 segundos** |
| Pipeline 9.5 con prompt 3-5 KB | PARSE_AMBIGUOUS + BALANCE_MISMATCH + sometimes excluye transactions | **~60 segundos** |

### Fuentes específicas de contaminación detectadas

1. **Sign convention block (Liabilities Beancount).** Cuando el PDF es cuenta corriente o el contexto está mal, Gemini invierte signos.
2. **Instrucción de "asegurar que el balance cuadre".** Caso real documentado: `estado-de-cuenta (26).pdf` — Gemini emite warning literal "*La transacción 'MONTO CANCELADO' por $-4.825.462 fue excluida de la lista de transacciones para asegurar la conciliación de saldos*". Está **manipulando los datos** para complacer el balance check, lo opuesto al objetivo.
3. **Forzar `currency=CLP` por context cuando el PDF es USD.** Genera PARSE_AMBIGUOUS masivo + intentos de "ajuste" por parte de Gemini.
4. **Schema JSON canónico forzado** vía `response_mime_type=application/json` + `response_schema`. Gemini gasta ~40% del output en estructura (`{`, `}`, `[`, `]`, llaves de keys repetidas) en vez de data. Combinado con `raw: {...}` nested por tx, infla el output a ~4500 tokens para 92 tx.
5. **Output sin streaming.** SDK Python espera response completo. Para PDFs con 90+ tx, eso es ~30-40s solo en token generation.

### Insight arquitectónico (de Ary durante la sesión)

> "Yo le pedí la información en CSV [a Gemini web] y me la dio estructurada. ¿Por qué no le pedimos lo mismo y nosotros armamos los JSON en vez de que Gemini nos los pase armados?"

**Punto correcto.** Mover la complejidad de Gemini → Python es el patrón correcto:

```
Gemini → CSV simple (date, description, amount, currency) →
  wrapper Python → CartolaCanonicalV1 (Pydantic-validated) →
    staging .cartola.json
```

Beneficios:
- ~3-5x más rápido (estimado).
- ~50% menos tokens output.
- Gemini "libre" para producir contenido, no estructura.
- Validación de tipos sigue en Pydantic, pero post-Gemini.
- Warnings nested (`extraction.warnings`) los emite el wrapper, no Gemini.

Costos:
- Parser CSV tolerante (descriptions con comas escapadas, fechas variables).
- Una transformación más server-side.
- Re-corrida del smoke completo con prompt nuevo (~$ Gemini + tiempo).

---

## Propuesta concreta — Story 9.5e

**Título tentativo:** "Rediseño del prompt Gemini para extracción CSV liviana + wrapping server-side"

**Acceptance Criteria candidatos (Bob decide la versión final):**

- AC1: Nuevo prompt en `gemini_client.py` pide **CSV** (date, description, amount, currency, raw_optional) **sin sign convention, sin schema canónico forzado, sin instrucción de "asegurar cuadre"**.
- AC2: `response_mime_type` cambia a `text/csv` o `text/plain`. `response_schema` removido.
- AC3: Nuevo parser server-side `csv_to_canonical()` que toma el CSV de Gemini + el `BankAccountEntry` y produce un `CartolaCanonicalV1` válido. Sign convention (Liabilities) se aplica acá según `account_type`, NO en el prompt.
- AC4: `cartola_post_process.detect_balance_mismatch()` queda como única fuente de verdad del balance check (ya existe — sólo asegurar que el prompt nuevo NO le da hints a Gemini).
- AC5: Re-correr 9.5c con el prompt nuevo: gate ≥90% verde sobre los 14 PDFs. Esa es la métrica de done para 9.5e.
- AC6: NO romper `process_upload_sync` ni el job store ni los endpoints HTTP existentes — el cambio es interno al `GeminiClient` + agregar el parser. Tests de 9.5 (322 verde) deben seguir verdes.

**Out of scope de 9.5e** (no expandir):
- Streaming response (mejora futura).
- Parallelism cross-PDF (mejora futura).
- Prompt caching de Google (mejora futura).
- Cambios al `CartolaCanonicalV1` schema (mantener compat con 9.6a future).

**Dependencias:**
- Bob crea storyfile siguiendo el patrón de 9.5.
- Dispatch a Amelia para implementación.
- Re-corrida 9.5c es manual (Ary, ~15-30 min según velocidad post-fix).

---

## Impacto sobre el sprint

- **9.5c** queda en `review` con el hallazgo como entrega principal. El AC11 (smoke real) tiene data parcial documentada en storyfile + staging files preservados. Moishe valida si esa data es suficiente para approve, o requiere re-corrida después de 9.5e.
- **9.6a** movida a `blocked-by-9-5e` en sprint-status. No tiene sentido implementar el importer sobre extracciones que Gemini está corrompiendo.
- **9.5d** (retry con feedback) **descartar** o re-evaluar — el problema no es robustez de Gemini, es el prompt. Retry sobre un prompt malo da resultados malos × 2.
- **9.7** (smart_importer) sigue dependiendo de 9.6a → también blocked.

**Path crítico revisado:**
`9.5e (nueva) → 9.5c re-corrida → 9.6a → 9.7`

---

## Decisión que necesito de Bob

1. **¿Crear Story 9.5e** con los ACs propuestos arriba? (Sí/No/Modificar)
2. **¿Mantener 9.5d backlog** o descartarla como superseded-by-9.5e?
3. **¿9.5c queda en review o se cierra como done** con el hallazgo como entrega principal? (Tooling + 37 tests + descubrimiento del problema raíz son valor entregado, aunque el AC11 técnicamente no muestre 90% verde porque la causa raíz está fuera del scope del 9.5c).

---

## Referencias

- Storyfile 9.5c con Change Log expandido: `_bmad-output/implementation-artifacts/9-5c-validation-tooling-extraccion-ml.md`
- Staging files del smoke parcial: `_bmad-output/validation-runs/2026-05-19-135748/staging/` (33 archivos)
- Staging files de discovery: `_bmad-output/validation-runs/discovery-202605191300/staging/` (10 archivos)
- Tooling: `bootstrap/validate_cartolas_batch.py` (37 tests verde en `backend/tests/test_validate_cartolas_batch.py`)
- Memory: `project_epic9_validacion_cartolas` (actualizada con el hallazgo)
