# 9.5f — Spike Tier 1 Results + handoff a Research

**Fecha:** 2026-05-20
**De:** Amelia (dev) → Mary (research)
**Branch:** `spike/9-5f-tier1-gemini-api-params` (no mergeado, esperando decisión)
**Status:** Tier 1 ejecutado y medido — gate ≥90% verde **NO** alcanzado en ninguna corrida. Handoff a research para decidir Tier 2 / Tier 3 / nuevo enfoque.

---

## Executive summary

Las 3 corridas que el handoff de Mary pidió (baseline → after-flash con 3 cambios SDK → after-pro) se completaron. **0/14 verde en las tres**. Por las reglas de branching del handoff, esto cae en el escenario "after-flash < 30% y after-pro < 90% → spike falló, evaluar Tier 3".

Pero hay 3 hallazgos colaterales relevantes para el próximo research:

1. **Pro reduce rojos 75%** (8 → 2). Todos los amarillos de after-pro tienen `diff = 0.00` — el balance cuadra **exacto**. Las extracciones de Pro son correctas; lo único que impide el verde son los códigos de warning emitidos por Gemini.
2. **PARSE_AMBIGUOUS** aparece en **14/14** PDFs con Pro (siempre 3×, una por run). Es Gemini quien lo emite — no el post-process. Es la causa #1 de "no-verde". El prompt 9.5 le pide explícitamente que lo emita cuando hay ambigüedad; Gemini lo respeta religiosamente.
3. **`gemini-3.5-flash` SÍ existe** en `client.models.list()` (junto a `gemini-3-flash-preview`, `gemini-3.1-flash-lite`, `gemini-3.1-pro-preview`). El handoff de Mary asumía solo 2.5-flash y 2.5-pro. Hay candidatos no probados.

## Tabla comparativa

| Métrica | Baseline | After-flash (Tier 1) | After-pro |
|---|---|---|---|
| Modelo | gemini-2.5-flash | gemini-2.5-flash | gemini-2.5-pro |
| Config | T=0.0, contents=[prompt, pdf] | **T=0.1, max_output_tokens=32768, contents=[pdf, prompt]** | mismo que after-flash |
| 🟢 Verde | 0 (0.0%) | 0 (0.0%) | **0 (0.0%)** |
| 🟡 Amarillo | 6 (42.9%) | 6 (42.9%) | **12 (85.7%)** ⬆️ |
| 🔴 Rojo | 8 (57.1%) | 8 (57.1%) | **2 (14.3%)** ⬇️ |
| % "balance OK" (diff=0) | ~30% | ~30% | **~85%** ⬆️ |
| Tiempo activo total | ~70 min (con standby 10h) | 40 min | 45 min |
| Latencia avg/call | ~100s | ~58s | ~65s |
| Costo aprox | $0.13 | $0.13 | **$0.65** (~5× flash) |
| Gate ≥90% verde | FAIL | FAIL | FAIL |

**Reports completos:**
- `_bmad-output/validation-runs/9-5f-baseline/report.md` (+ staging/)
- `_bmad-output/validation-runs/9-5f-after-flash/report.md` (+ staging/)
- `_bmad-output/validation-runs/9-5f-after-pro/report.md` (+ staging/)

## Los 3 cambios aplicados (per handoff)

Diff `backend/app/integrations/gemini_client.py:326-334`:

```diff
 config = types.GenerateContentConfig(
     response_mime_type="application/json",
-    temperature=0.0,
+    temperature=0.1,
+    max_output_tokens=32768,
 )
 response = self._client.models.generate_content(
     model=self._model,
-    contents=[prompt, pdf_part],
+    contents=[pdf_part, prompt],
     config=config,
 )
```

**Cambio 4 (verificación pro vs flash)**: ejecutado vía `GEMINI_MODEL=gemini-2.5-pro` env var, NO commiteado.

**Cambio adicional fuera del scope original** (pero necesario para que el smoke termine): timeout per-call de 180s en `validate_cartolas_batch.py` (no toca `gemini_client.py`). El baseline original colgaba indefinidamente en una llamada SDK sin timeout. Diff:

```python
# bootstrap/validate_cartolas_batch.py:_run_pdf
ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
try:
    future = ex.submit(process_upload_sync, ...)
    canonical = future.result(timeout=PER_CALL_TIMEOUT_S)
finally:
    ex.shutdown(wait=False)
```

## Análisis profundo: por qué NO llegamos a verde

### Lo que SÍ funcionó con Pro

De los **12 PDFs amarillos** en after-pro, **los 12 tienen `diff=0.00`** exacto (3 runs cada uno, estable). Ejemplos:
- **BCI**: opening=2.054.314, closing=3.219.948, sum=1.165.634, diff=**0.00** — 3/3 runs idénticos.
- **Estado-26**: opening=4.825.462, closing=9.440.753, sum=4.615.291, diff=**0.00** — 3/3 idénticos. (Este era el PDF que Ary destacó como crítico.)
- **Estado-21**: opening=2.058.822, closing=17.045.465, sum=14.986.643, diff=**0.00** — 3/3 idénticos.

Es decir: **con Pro, la extracción es matemáticamente correcta** en 12 de 14 PDFs (y los 2 rojos son por inestabilidad, no por errores sistemáticos).

### Por qué siguen siendo amarillos: warnings

Pro emite/triggerea estos 3 warnings (definidos en `cartola_schema.py` líneas 22-30):

| Warning | Quién lo emite | Frecuencia en after-pro | Causa |
|---|---|---|---|
| `PARSE_AMBIGUOUS` | **Gemini** (vía prompt 9.5 instrucción explícita) | **14/14 PDFs** (3× cada uno = 42/42 runs) | El prompt 9.5 le dice: "warning PARSE_AMBIGUOUS cuando estructura del PDF inusual". Pro siempre lo emite, conservador. |
| `PERIOD_MISMATCH` | **Post-process** (`cartola_post_process.py:50`) | **9/14 PDFs** | Triggers cuando `first_tx.date < period.start` o `last_tx.date > period.end`. Causa principal: cuotas X/N pre-existentes con `date = fecha operación original` (anterior al período). |
| `DUPLICATE_LINE` | Post-process | 1/14 (estado-de-cuenta 24) | Líneas con mismo date+amount+description. Posiblemente diseño del PDF, no error de extracción. |

Por el `classify_pdf` de `validate_cartolas_batch.py:198-225`:
- Cualquier warning NO-`BALANCE_MISMATCH` → AMARILLO (no rojo, no verde).
- Tener `diff=0.00` no es suficiente para verde si hay warnings.

### Los 2 rojos de Pro

- **`santander-mastercard-202604.pdf`**: inestable. 2/3 runs con opening=17.045.465 correcto + diff=0. 1/3 con opening=319.523 + BALANCE_MISMATCH. Drift en `n_transactions, opening, sum_amounts`.
- **`74a660fc-...pdf`** (UUID): 2/3 OK con diff=0. 1/3 con BALANCE_MISMATCH. Drift similar.

En ambos casos: 67% de las runs estaban OK. Es inestabilidad, no error sistemático.

## Hipótesis para el research

Estas son hipótesis para investigar — NO recomendaciones cerradas:

### H1 — El problema NO es la extracción, son los warnings del prompt

Si la extracción cuadra exacto (`diff=0`) en 12/14 PDFs con Pro, el problema "0% verde" es de **diseño del clasificador y del prompt**, no de Gemini:

- El prompt 9.5 le pide a Gemini emitir `PARSE_AMBIGUOUS` cuando "estructura inusual". Esto es subjetivo; Pro lo emite **siempre**. Si quitamos esa instrucción del prompt, ¿desaparece?
- El post-process emite `PERIOD_MISMATCH` por cuotas X/N pre-existentes con fechas anteriores. ¿Vale ese check si las cuotas son legítimas? La lógica de `detect_period_mismatch` no sabe distinguir.
- El clasificador `classify_pdf` trata todos los warnings ≠ BALANCE_MISMATCH como "amarillo". ¿Tiene sentido si `diff=0`?

**Si la respuesta es "quitar warnings espurios" → Tier 2 según Mary** (migrar a `system_instruction`, o cambiar prompt para no emitir PARSE_AMBIGUOUS por default). Costo: bajo.

### H2 — Probar modelos más nuevos antes de Tier 3

`client.models.list()` muestra que hay 4 candidatos no probados en el spike:

```
gemini-3-flash-preview
gemini-3.1-flash-lite
gemini-3.1-flash-lite-preview
gemini-3.5-flash       ← Ary mencionó usar este en web
gemini-3.1-pro-preview
gemini-flash-latest    ← alias dinámico
```

Ary reportó (mismo prompt, mismos PDFs) que en Gemini web con flash obtiene resultados "perfectos" en una sola interacción. Mi suposición inicial fue que web usa flash 2.5; **Ary confirmó que usa "Flash 3.5"**. Si Gemini web sirve `gemini-3.5-flash` y la API SDK por default usa `gemini-2.5-flash`, **estamos comparando modelos distintos sin saberlo**.

Probar `gemini-3.5-flash` (con los 3 params de Tier 1 ya aplicados) sería 1 corrida más de medición. Costo: ~$0.13. Tiempo: ~40 min.

### H3 — Combinar Pro extraction + filtrado de warnings espurios

Si después de H1 y H2 sigue habiendo 0% verde, evaluar si el gate `≥90% verde` es la métrica correcta. Quizás el gate operacional debería ser `≥90% balance-OK (diff < tolerance)` independiente de warnings PARSE_AMBIGUOUS. En after-pro eso ya es **85.7%** y muy cerca del 90%.

### H4 — Tier 3 (per handoff Mary)

Si H1-H3 no llegan a 90% verde: rasterizar PDFs a PNGs cliente-side (HN 43977047 + thread 191340). Más esfuerzo, cambio de pipeline.

## Preguntas concretas para el research

1. **¿Existe `gemini-3.5-flash` como release público estable**, o es preview? ¿Tiene cost/latency profile distinto a 2.5-flash? Si Gemini web sirve 3.5-flash a usuarios logueados, ¿es accesible para producción server-side via API?
2. **¿`PARSE_AMBIGUOUS` viene del prompt 9.5 o de algún flag/feature del SDK?** Si re-leemos el prompt 9.5 con ojo crítico, ¿hay una instrucción que se pueda atenuar sin romper otros invariantes?
3. **¿El check `PERIOD_MISMATCH` para cuotas pre-existentes es un bug del post-process o un invariante intencional?** En tarjetas chilenas las cuotas X/N tienen fecha de operación original (puede ser cualquier mes anterior). El check actual las flaggea siempre como mismatch. ¿Sale del scope del check?
4. **¿Pro como default es viable económicamente?** Si producción procesa ~50 cartolas/mes, costo extra ≈ ~$30/mes vs flash. ¿Es aceptable para el caso de uso?
5. **Alternativa SDK: `genai.Client(http_options={"timeout_seconds": ...})`** — ¿existe forma de pasar timeout per-call vía SDK en vez de mi workaround con `ThreadPoolExecutor`?

## Archivos de referencia

**Generados en este spike:**
- `_bmad-output/coordination/9-5f-spike-tier1-handoff-2026-05-19.md` — handoff original de Mary
- `_bmad-output/coordination/9-5f-spike-tier1-handoff-2026-05-19-baseline.md` — report baseline copiado (per request de Mary)
- `_bmad-output/coordination/9-5f-baseline-stdout.log`, `9-5f-after-flash-stdout.log`, `9-5f-after-pro-stdout.log` — stdout logs
- `_bmad-output/validation-runs/9-5f-baseline/report.md` + staging
- `_bmad-output/validation-runs/9-5f-after-flash/report.md` + staging
- `_bmad-output/validation-runs/9-5f-after-pro/report.md` + staging

**Branch:**
- `spike/9-5f-tier1-gemini-api-params` (local, no pushed)
- Cambios: `backend/app/integrations/gemini_client.py` (3 params) + `bootstrap/validate_cartolas_batch.py` (timeout wrapper)

**Spike anterior (9.5e, no aplicado — evidencia):**
- `_bmad-output/coordination/9-5e-prompt-spike-{A..H}-{ts}/` — 8 variaciones de prompt iterativo, 63 calls totales. Aprendizaje colateral: el wording exacto de los labels ("Monto Facturado Anterior" vs lista de alternativas) cambia drásticamente el output de Gemini.
- `_bmad-output/coordination/9-5e-thinking-spike-{ts}/` — verificación que thinking_budget ya estaba activo por default.
- `_bmad-output/coordination/9-5e-web-prompt-spike-{ts}/` — replica del prompt literal que Ary usa en web → confirma que con prompt corto (170 bytes) Gemini API encuentra openings correctos.
- `bootstrap/spike_9_5e_prompt_{a..h}.py`, `bootstrap/spike_9_5e_thinking.py`, `bootstrap/spike_9_5e_web_prompt.py` — scripts throwaway, mantenerlos hasta cierre de 9.5f.

## Lo que NO se hizo (per acuerdo con Ary 2026-05-20)

- No se mergeó el branch (esperando decisión post-research).
- No se cambió el `DEFAULT_MODEL` a pro (decisión de costo pendiente).
- No se tocó el prompt (regla del research original de Mary).
- No se ejecutó Tier 2 ni Tier 3.

## Próximo paso solicitado

Que Mary (o el research que se invoque) revise este resultado + las 5 preguntas concretas y produzca:

1. Recomendación sobre `gemini-3.5-flash` u otro modelo nuevo a probar (H2).
2. Posición sobre si los warnings PARSE_AMBIGUOUS / PERIOD_MISMATCH son "ruido" eliminable (H1, H3).
3. Decisión sobre Tier 2 vs Tier 3 vs cambio de gate.

---

| | |
|---|---|
| Autor | Amelia (claude-opus-4-7[1m]) |
| Fecha | 2026-05-20 |
| Duración del spike | 19-20 May, 2 sesiones |
| Total Gemini calls gastados | ~135 (42 baseline + 42 after-flash + 42 after-pro + ~9 verificaciones) |
| Costo aprox total | ~$1.05 |
