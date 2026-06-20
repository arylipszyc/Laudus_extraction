# 9.5g — Spike Flash 3.5: handoff a Amelia

**Fecha:** 2026-05-20
**De:** Mary (research) → Amelia (dev)
**Research fuente:** [technical-herramientas-extraccion-cartolas-pdf-research-2026-05-20.md](../planning-artifacts/research/technical-herramientas-extraccion-cartolas-pdf-research-2026-05-20.md) §Executive Summary, Paso #2
**Status:** ready-for-dev (no requiere story formal — extiende el spike 9.5f con un cuarto punto de medición)
**Branch:** seguir en `spike/9-5f-tier1-gemini-api-params` (no abrir nueva)

---

## Contexto en 1 párrafo

El research A+B+C del 2026-05-20 identificó que **Gemini 3.5 Flash es GA desde 2026-05-19** (un día antes del spike 9.5f), con stable model ID `gemini-3.5-flash`, sin allowlist. ExtractBench (arxiv 2602.12247, feb 2026) reporta que **Gemini Flash lidera schema validity (71%) sobre Claude Opus/Sonnet, GPT-5/5.2 y supera al propio Gemini Pro** — coincide con el finding del spike 9.5f (Pro 85.7% balance OK pero falla por warnings). El SDK estaba en 2.4.0 cuando Amelia corrió `client.models.list()` el 19-05; ahora está confirmado en **2.5.0** en el venv del proyecto y `gemini-3.5-flash` responde al call directo. Este spike agrega una **cuarta corrida** al benchmark del 9.5f para tener data antes de decidir el Path #1 (validators deterministas).

## Lo que YA verifiqué (no repetir)

- ✅ `google-genai 2.5.0` instalado en venv del proyecto (`C:\dev\bmad-workspace-new\family-office-eag\venv`).
- ✅ Suite backend 376/378 verde tras upgrade (los 2 fallos son: test del spike 9.5f con orden de contents invertido + pre-existente `test_run_backfill_calls_upsert_for_both_sheets` — ambos no relacionados con este spike).
- ✅ Call directo a Flash 3.5 funciona: `c.models.generate_content(model='gemini-3.5-flash', contents='hello')` devuelve respuesta válida.
- ✅ Branch `spike/9-5f-tier1-gemini-api-params` ya tiene los 3 cambios Tier 1 aplicados (T=0.1, max_output_tokens=32768, contents=[pdf_part, prompt]) + timeout wrapper en `validate_cartolas_batch.py`.

## Cambios exactos (cero código nuevo)

**Cambio único:** correr el smoke con `GEMINI_MODEL=gemini-3.5-flash` env var. **No commitear** el switch — sólo medir, mismo patrón que `after-pro` en 9.5f.

## Procedimiento

1. **Verificar que estás en la branch del spike**: `git status` debe mostrar `spike/9-5f-tier1-gemini-api-params`.
2. **Correr el smoke con Flash 3.5**:
   ```bash
   GEMINI_MODEL=gemini-3.5-flash python -m bootstrap.validate_cartolas_batch samples/ --runs 3 --keep-staging \
     --override "estado-de-cuenta (21).pdf:Banco de Chile:9999" \
     --override "estado-de-cuenta (22).pdf:Banco de Chile:9999" \
     --override "estado-de-cuenta (23).pdf:Banco de Chile:9999" \
     --override "estado-de-cuenta (24).pdf:Banco de Chile:9999" \
     --override "estado-de-cuenta (25).pdf:Banco de Chile:9999" \
     --override "estado-de-cuenta (26).pdf:Banco de Chile:9999" \
     --override "estado-de-cuenta (27).pdf:Banco de Chile:9999" \
     --override "estado-de-cuenta (28).pdf:Banco de Chile:9999"
   ```
   (Usar los mismos overrides que en 9.5f para consistency. Si hay overrides nuevos para los UUIDs, mantenerlos.)
3. **Guardar el report**: mover el `_bmad-output/validation-runs/{timestamp}/` resultante a `_bmad-output/validation-runs/9-5g-after-flash-3-5/` (mismo patrón que 9.5f).
4. **Stdout log**: redirigir stdout a `_bmad-output/coordination/9-5g-after-flash-3-5-stdout.log`.
5. **Escribir results**: `_bmad-output/coordination/9-5g-spike-flash-3-5-results-2026-05-20.md` con tabla `baseline | after-flash (2.5) | after-pro | after-flash-3.5` × `% verde | n_verde | n_amarillo | n_rojo | % balance OK (diff=0) | latencia avg | costo aprox | PARSE_AMBIGUOUS count | PERIOD_MISMATCH count`. Reusar la estructura del file 9.5f-results.

## Criterios de éxito y branching

| Escenario | Acción |
|---|---|
| **after-flash-3-5 ≥90% verde** | Mergear el branch del spike (con Tier 1 + DEFAULT_MODEL=gemini-3.5-flash committeado). Cerrar spike. Path #1 (validators deterministas) ya no es necesario. |
| **after-flash-3-5 ∈ [85%, 90%) balance OK** | Mergear DEFAULT_MODEL=gemini-3.5-flash en el branch. Path #1 (validators deterministas) en story siguiente para cerrar el gap final. |
| **after-flash-3-5 < after-pro en balance OK** | NO mergear el switch. Flash 3.5 fue un downgrade para este task. Continuar con after-pro como baseline + dispatch directo de Path #1. |
| **after-flash-3-5 falla con error de API** | Logear el error exacto (status code, message). Pingear a Mary para decidir si esperar fix de Google o pivotar. |

## Lo que NO tocar en este spike

- ❌ El prompt (`_build_prompt`). Misma regla que 9.5f. Si se rompe la adherencia, no sabemos si fue modelo o prompt.
- ❌ Los 3 params Tier 1 ya aplicados (T=0.1, max_output_tokens=32768, orden contents). Mantenerlos para que el cambio sea **un solo eje** vs 9.5f.
- ❌ `cartola_post_process.py`. PERIOD_MISMATCH por cuotas X/N se ataca en Path #1, no acá.
- ❌ `validate_cartolas_batch.py` classifier. Se ataca en Path #1.

## Costo / tiempo estimado

- ~42 calls a `gemini-3.5-flash` ($1.50/$9 per M tokens) ≈ $0.15-0.30 total.
- ~40-45 min de wall time (similar a after-flash 9.5f).

## Por qué NO requiere story formal de Bob

- Cero cambios de código. Sólo env var.
- AC verificables vía script existente (`validate_cartolas_batch.py`).
- Reversible: si Flash 3.5 es peor, no se mergea nada.
- El research ya hizo el trabajo de evidencia (Executive Summary §Paso #2).

## Referencia rápida — evidencia detrás del cambio

| Cambio | Evidencia primaria | Confidence |
|---|---|---|
| Probar `gemini-3.5-flash` | ExtractBench (arxiv 2602.12247, feb 2026): "Gemini Flash leading on validity (71%, 25/35) and pass rate (6.9%), outperforming the larger Pro" | high |
| Mantener Tier 1 params | Spike 9.5f midió balance OK 85.7% con esos params + Pro — eliminar variables | high |
| Mantener prompt actual | Spike 9.5f resultados muestran que el prompt no es el cuello para Pro; los warnings espurios sí lo son (Path #1 los ataca) | medium-high |
