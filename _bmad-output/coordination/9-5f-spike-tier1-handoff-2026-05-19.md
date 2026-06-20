# 9.5f — Spike Tier 1: handoff a Amelia

**Fecha:** 2026-05-19
**De:** Mary (research) → Amelia (dev)
**Research fuente:** [research/technical-gemini-web-vs-api-pdf-extraction-research-2026-05-19.md](../planning-artifacts/research/technical-gemini-web-vs-api-pdf-extraction-research-2026-05-19.md)
**Status:** ready-for-dev (no requiere story formal de Bob — son 4 cambios quirúrgicos a una sola función)

---

## Contexto en 1 párrafo

Smoke test actual `validate_cartolas_batch.py` da **0% verde sostenido** en 14 PDFs × 3 corridas con `gemini-2.5-flash`. La extracción en la web de Gemini sobre los mismos PDFs es aceptable. El research identificó **4 hipótesis con evidencia oficial dura** (incluyendo respuestas de Google staff), todas controlables vía API y todas no probadas en el código actual. Este spike aplica las 4 en un solo PR y mide impacto.

## Lo que YA verifiqué (no repetir)

- ✅ El smoke `bootstrap/validate_cartolas_batch.py` es el eval determinista — usalo como gate, no armes uno nuevo.
- ✅ `thinking_budget` no se pasa en `GenerateContentConfig` → default es `dynamic` (ON). Descarté como root cause; **NO tocar**.
- ✅ La llamada API vive en [backend/app/integrations/gemini_client.py:326-334](../../backend/app/integrations/gemini_client.py#L326-L334).
- ✅ Prompt vive en `_build_prompt` (líneas 91-276 del mismo archivo). **NO tocar prompt en este spike** (regla del research).

## Cambios exactos (los 4 de Tier 1)

Todos en [backend/app/integrations/gemini_client.py:326-334](../../backend/app/integrations/gemini_client.py#L326-L334). Bloque actual:

```python
config = types.GenerateContentConfig(
    response_mime_type="application/json",
    temperature=0.0,
)
response = self._client.models.generate_content(
    model=self._model,
    contents=[prompt, pdf_part],
    config=config,
)
```

Bloque objetivo:

```python
config = types.GenerateContentConfig(
    response_mime_type="application/json",
    temperature=0.1,                 # ← cambio 1: Google staff recomienda ≥0.1, T=0.0 anti-pattern documentado
    max_output_tokens=32768,         # ← cambio 2: descartar truncamiento silencioso (2.5 Flash necesita más que 2.0)
)
response = self._client.models.generate_content(
    model=self._model,
    contents=[pdf_part, prompt],     # ← cambio 3: PDF primero, instrucción al final (4 docs oficiales convergen)
    config=config,
)
```

**Cambio 4 (no de código, de verificación):** correr una vez con `GEMINI_MODEL=gemini-2.5-pro` para descartar/confirmar si el modelo es root cause. **NO commitear el switch** — sólo medir y dejar evidencia en el report. (Box midió +10pp en PDFs y +13pp en multi-field para Pro vs Flash 2.5.)

## Procedimiento

1. **Branch:** `spike/9-5f-tier1-gemini-api-params`.
2. **Baseline antes de cambiar nada:** correr `python -m bootstrap.validate_cartolas_batch samples/ --runs 3 --keep-staging` y guardar el `report.md` resultante como `_bmad-output/coordination/9-5f-spike-tier1-handoff-2026-05-19-baseline.md` (copy del report).
3. **Aplicar los 3 cambios de código de un PR único.**
4. **Re-correr el smoke** mismo comando. Guardar el nuevo report como `_bmad-output/coordination/9-5f-spike-tier1-handoff-2026-05-19-after.md`.
5. **Medición flash vs pro:** correr `GEMINI_MODEL=gemini-2.5-pro python -m bootstrap.validate_cartolas_batch samples/ --runs 3 --keep-staging`. Guardar como `..._after-pro.md`. (Esta corrida es **cara** — pro cuesta ~5x flash; vale la pena por la señal de root cause.)
6. **Diff de resultados** en `_bmad-output/coordination/9-5f-spike-tier1-results-2026-05-19.md` con tabla `baseline | after-flash | after-pro` × `% verde | n_verde | n_amarillo | n_rojo | drift_fields top-5`.

## Criterios de éxito y branching

| Escenario | Acción |
|---|---|
| **after-flash ≥90% verde** | Mergear el PR. Cerrar spike. Tier 2 NO necesario. |
| **after-flash ∈ [30%, 90%)** | Mergear el PR igual (mejora directa). Escalar a Tier 2: A/B JSON-en-prompt vs `response_mime_type`, y/o migrar reglas estables a `system_instruction`. Pingear a Mary para nuevo handoff. |
| **after-flash < 30% pero after-pro ≥90%** | NO mergear T=0.1 / orden / max_tokens todavía. Abrir story formal con Bob: cambio de modelo default a 2.5-pro tiene implicancias de costo. Decisión de Ary. |
| **after-flash < 30% y after-pro < 90%** | Spike falló. Pingear a Mary. Próximos candidatos: Tier 3 (rasterizar PDF a PNGs lado cliente — HN 43977047 + thread 191340 confirman ganancia). |

## Lo que NO tocar en este spike

- ❌ El prompt (`_build_prompt`). Es regla del research. Si se rompe la adherencia, no sabemos si fue parámetros o prompt.
- ❌ `thinking_config`. Ya verificado default = dynamic ON.
- ❌ `response_schema` (migrar a Pydantic). Eso es Tier 2 si Tier 1 no llega.
- ❌ Rasterización de PDF → imágenes. Eso es Tier 3.

## Por qué NO requiere story formal de Bob

- Cambios sobre 1 sola función pública (`extract_pdf`), 0 cambios de shape, 0 cambios de prompt, 0 cambios de API pública del client.
- AC verificables vía script existente (`validate_cartolas_batch.py`), sin tests nuevos.
- Reversible en 1 commit si falla.
- El research ya hizo el trabajo de evidencia. No hay decisión de producto pendiente — sólo aplicar lo recomendado y medir.

Si esto sale verde, la story 9.5e (prompt liviano server-side) probablemente no es necesaria, o cambia de scope. Coordinar con Bob antes de continuar con 9.5e.

## Referencia rápida — evidencia detrás de cada cambio

| Cambio | Evidencia primaria | Confidence |
|---|---|---|
| `temperature` 0.0 → 0.1 | Google staff Krish_Varnakavi1 (2025-06-04) en [discuss.ai.google.dev/86131](https://discuss.ai.google.dev/t/gemini-flash-thinking-pro-end-with-meaningless-character-when-temperature-is-0/86131) | high |
| `max_output_tokens=32768` | [discuss.ai.google.dev/100175](https://discuss.ai.google.dev/t/2-5-flash-stopped-delivering-true-json-structures/100175) — 2.5 Flash necesita más que 2.0 | medium-high |
| `contents=[PDF, prompt]` | 4 docs oficiales (document-processing, vertex-ai/document-understanding, prompting_with_media, prompting-strategies) convergen | high |
| Probar pro vs flash | Box benchmark 2025-11 + Cloud blog 2025-05 (positioning Pro para extracción precisa) | medium-high |
