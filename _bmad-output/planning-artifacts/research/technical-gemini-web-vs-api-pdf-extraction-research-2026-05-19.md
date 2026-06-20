---
stepsCompleted: [1]
inputDocuments: []
workflowType: 'research'
research_type: 'technical'
research_topic: 'Gemini Web vs API — discrepancia en extracción de PDF (cartolas bancarias)'
research_goals: 'Entender causas de degradación API vs web, identificar antecedentes documentados, recomendar próximos pasos accionables'
user_name: 'Ary'
date: '2026-05-19'
web_research_enabled: true
source_verification: true
---

# Research Report: Gemini Web vs API — Discrepancia en Extracción de PDF

**Date:** 2026-05-19
**Author:** Ary
**Research Type:** Technical
**Context:** Family Office EAG — Epic 9 — extracción de cartolas bancarias chilenas a JSON canónico

---

## Brief original

Investigar por qué Gemini (interfaz web — gemini.google.com / AI Studio) produce mejores extracciones que Gemini API sobre el mismo PDF de cartolas bancarias chilenas (BCI, Santander, otros), y si hay antecedentes documentados de esta discrepancia.

**Hecho observado:** Smoke test 14 PDFs × 3 corridas en API → 0% verde sostenido. Mismo PDF en web → extracción aceptable.

**Stack API exacto:** `google-genai` SDK, `gemini-2.5-flash`, `response_mime_type=application/json`, `temperature=0.0`, sin system_instruction, sin tools, sin thinking_config, PDF nativo vía `types.Part.from_bytes`, prompt ~270 líneas en español.

---

## Resumen ejecutivo

1. **La comparación web vs API NO es apples-to-apples a partir de Dic-2025.** El default del app Gemini cambió a Gemini 3 Flash en Dic-2025 y a Gemini 3.5 Flash en May-2026 (rollout global). La API está corriendo `gemini-2.5-flash` explícito. Buena parte del gap puede explicarse solo por **modelo distinto**, no por surface. `[high-confidence]` — TechCrunch 2025-12-17 + gemini.google/release-notes.

2. **`temperature=0.0` es un anti-pattern documentado por Google staff**, con síntomas reproducibles (loops, whitespace infinito, repetición) específicamente en `gemini-2.5-flash` con `response_mime_type=application/json`. Recomendación oficial: subir a ≥0.1. `[high-confidence]` — Google staff response en discuss.ai.google.dev/86131 (2025-06-04) + doc Gemini 3.

3. **`response_mime_type=application/json` + 2.5 tiene regresión documentada vs 2.0** (issue oficial `googleapis/python-genai#706` cerrada sin respuesta sustantiva). Benchmark independiente de Castillo: `response_schema` empeoró 5/6 tareas vs JSON-in-prompt en 1.5 Flash, patrón que persiste según issues 2.5. `[high-confidence]`.

4. **El orden actual de `contents=[prompt, PDF]` está invertido respecto a la recomendación oficial**: 4 docs Google (document-processing, vertex-ai/document-understanding, prompting_with_media, prompting-strategies) convergen en "PDF primero, instrucción al final". Cambio de bajo esfuerzo, alta evidencia. `[high-confidence]`.

5. **La discrepancia web-vs-API en sí es un patrón conocido**, no caso aislado. Issue oficial `google-gemini/cookbook#907` reporta exactamente lo mismo (mismo prompt + misma imagen produce outputs distintos AI Studio vs SDK). Staff de Google la etiquetó "off-topic:model quality" sin resolver.

**Bottom line para decidir próximos pasos**: invertir esfuerzo en hipótesis 1-4 (todas controlables vía API) antes de asumir que "la web es mejor". Hay 3 fixes de bajo costo y alta evidencia que no se han probado todavía (Tier 1 abajo).

---

## 1. Causas plausibles rankeadas por evidencia

### Tier A — high confidence, evidencia oficial

#### A.1 Modelo distinto entre web y API
- **Hipótesis:** la web NO está sirviendo `gemini-2.5-flash`; sirve Gemini 3 Flash (Dic-2025) o Gemini 3.5 Flash (rollout global May-2026), posiblemente con ruteo a Pro tier para usuarios pagos.
- **Evidencia:** TechCrunch 2025-12-17 "Google launches Gemini 3 Flash, makes it the default model in the Gemini app"; gemini.google/release-notes "May 2026: Gemini 3.5 Flash rolled out globally"; free tier "varying access to 3.1 Pro" → ruteo dinámico opaco.
- **Aplicabilidad al caso (test 2026-05-19):** el modelo en la web probablemente es ≥Gemini 3 Flash, no 2.5 Flash. Box benchmark midió Gemini 3 Flash > Gemini 2.5 Flash por **+10pp en PDFs, +13pp en docs multi-field** (cartolas son multi-field por excelencia).
- **Confidence:** high para "modelo distinto"; medium para "qué versión exacta servía la web ese día".

#### A.2 `temperature=0.0` documentado como anti-pattern
- **Hipótesis:** `temperature=0.0` causa degradación reproducible en 2.5 Flash + JSON mode (loops, whitespace infinito, output truncado).
- **Evidencia:**
  - Google staff Krish_Varnakavi1 (2025-06-04) respondiendo a discuss.ai.google.dev/86131: recomienda explícitamente **subir a `temperature=0.1`**.
  - discuss.ai.google.dev/143931: 2.5 Flash en loop infinito de repetición con `temperature=0` + JSON estructurado.
  - Doc oficial Gemini 3 (`/docs/prompting-strategies`): *"we strongly recommend keeping the temperature at its default value of 1.0. Changing the temperature (setting it below 1.0) may lead to unexpected behavior, such as looping or degraded performance."*
  - discuss.ai.google.dev/94561 reporta "whitespace y dashes excesivos" con T=0 en 2.5 Flash.
- **Aplicabilidad:** Stack actual usa exactamente `temperature=0.0`. Cambio trivial.
- **Confidence:** high (Google staff lo dijo).

#### A.3 `response_mime_type=application/json` con 2.5 tiene regresión documentada
- **Hipótesis:** el modo JSON constreñido degrada la calidad de extracción en familia 2.5 vs 2.0; el constrained decoding sacrifica reasoning para garantizar shape.
- **Evidencia:**
  - `googleapis/python-genai#706` (2025-04-19) — oficial — "Inconsistent Structured outputs/json mode between 2.0 and 2.5". Cerrada sin respuesta sustantiva.
  - `google-gemini/cookbook#1028` — "API doc states model: gemini-2.5-flash-image supports Structured Output, but it doesn't".
  - `BerriAI/litellm#10134` — third-party reproduce el patrón.
  - Castillo benchmark (2024-12-27) en 1.5 Flash: JSON-Schema peor que NL prompt en 5/6 tasks; root cause documentado: **el SDK ordena alfabéticamente las keys del schema, rompiendo chain-of-thought**.
- **Aplicabilidad:** stack actual usa `response_mime_type=application/json` sin `response_schema`. Workaround conocido: pedir JSON en el prompt y parsear manualmente (JSON-Prompt).
- **Confidence:** high para "regresión existe"; medium para "es root cause del caso de Ary".

#### A.4 Orden `contents=[prompt, PDF]` invertido respecto a recomendación oficial
- **Hipótesis:** PDF debe ir antes del prompt en `contents`. La estructura actual penaliza reasoning sobre PDFs.
- **Evidencia (4 docs oficiales convergen):**
  - `ai.google.dev/gemini-api/docs/document-processing`: *"If using a single page, place the text prompt **after** the page."*
  - `cloud.google.com/vertex-ai/.../document-understanding`: *"place the PDF **before** the text prompt"*.
  - `ai.google.dev/gemini-api/docs/prompting_with_media`: *"Put your image first for single-image prompts."*
  - `ai.google.dev/gemini-api/docs/prompting-strategies`: *"supply all the context first. Place your specific instructions or questions at the very end of the prompt."*
- **Aplicabilidad:** stack actual = `[prompt_string, types.Part.from_bytes(pdf_bytes, mime_type="application/pdf")]` → orden invertido.
- **Confidence:** high.

### Tier B — medium-high confidence

#### B.1 Flash es subóptimo para docs densos multi-field
- **Hipótesis:** la elección de `flash` (vs `pro`) está alineada con costo, no con la task. Google posiciona Pro para extracción precisa, Flash para filtro/clasificación de alto volumen.
- **Evidencia:**
  - Cloud blog Google 2025-05: Pro = *"deep data analysis, extracts key insights from dense documents like legal contracts or medical records"*; Flash = *"high-volume scenarios"*. Caso citado Moody's: Flash filtra, **Pro extrae**.
  - Box benchmark 2025-11: Gemini 3 Flash supera a 2.5 Flash por +10pp en PDFs y **+13pp cuando se extraen dozens of fields from single files** — descripción exacta de cartolas.
  - llm-stats.com: FACTS Grounding gap Flash vs Pro ≈1.5pp (general); el gap relevante vive en long-context multi-field, donde Box midió +10pp.
  - discuss.ai.google.dev/106516: en 50 tests con "long and complicated system instruction", Flash falla ~10, Pro falla 2-3.
- **Aplicabilidad:** spike de 2.5-pro vs 2.5-flash en eval set es trivial.
- **Confidence:** medium-high.

#### B.2 Truncamiento silencioso por `max_output_tokens`
- **Hipótesis:** 2.5 Flash necesita más tokens de output que 2.0; el default puede recortar el JSON sin error explícito, dejándolo malformado o incompleto (signos invertidos pueden venir de "vio solo media tabla").
- **Evidencia:** discuss.ai.google.dev/100175 (2025-08-26) — usuario resuelve regresión de JSON en 2.5 Flash subiendo el budget de output. Mensaje literal: *"el budget de tokens necesario en 2.5 es bastante mayor que en 2.0"*.
- **Aplicabilidad:** stack actual no parece estar seteando `max_output_tokens` explícito → default. Cartola con 50+ transactions probablemente excede 8k tokens de output.
- **Confidence:** medium-high; muy fácil de verificar.

#### B.3 Web hace orquestación dinámica con temperatures variables
- **Hipótesis:** gemini.google.com hace múltiples llamadas internas (extracción T=0, generación T=1, etc.). La API hace una sola llamada con T fija → distinta arquitectura, no comparable.
- **Evidencia:** Notas Google citadas en Agent C: *"Google manages the temperature dynamically during processes like Pro Search, for example using a temperature of 0.0 while extracting data from a webpage, but a 1.0 while writing the final summary."*
- **Aplicabilidad:** explica parte del gap pero no es accionable en API sin replicar el pipeline.
- **Confidence:** medium.

### Tier C — medium confidence

#### C.1 Prompt monolítico sin `system_instruction`
- **Hipótesis:** las ~270 líneas de reglas en user turn tienen peor adherencia que si fueran system_instruction. Best practice oficial las separa.
- **Evidencia:** docs oficiales prescriben "persona + reglas conversacionales + guardrails" en `system_instruction` (Live API best practices 2026-05-11; Prompt design strategies 2026-04-28). **Pero Google NO publica benchmark cuantitativo** del delta.
- **Confidence:** medium (mejora alineada con doc, magnitud no medida).

#### C.2 Resolución de imagen al renderizar PDF
- **Hipótesis:** la API resizea páginas a max 3072×3072 / 258 tokens; Vertex usa tiling ~1800 tokens. Tipografía chica en cartolas (signos +/-, comas decimales) puede perderse a baja resolución.
- **Evidencia:**
  - discuss.google.dev/191340 — staff Google (marckevin) confirma Vertex tiling ~1800 tok vs AI Studio API resize a ~384px (~258 tok).
  - `media_resolution` control existe en Gemini 3, **NO en 2.5** — no podés forzar alta resolución en 2.5-flash.
  - HN 43977047 (caso PDF español en 2.5 Pro): conversión a JPG por página mejoró sustancialmente.
- **Aplicabilidad:** spike de "PDF nativo vs PDF→PNG cliente" para validar.
- **Confidence:** medium (evidencia mayormente comunitaria + 1 staff oficial confirmando tiling diff).

### Tier D — low confidence / especulativo

#### D.1 System prompt + `pcontext` oculto en Gemini app
- Leak Substack (Gerhardson) — 6 system prompts embebidos en JS de gemini.google.com.
- Aplica a `gemini.google.com`, no a AI Studio.
- Explica "tono" / orientación a tarea, **no signos invertidos**.
- Confidence: low-medium.

#### D.2 Thinking budget diferencia
- Doc oficial: en `gemini-2.5-flash`, thinking dinámico (`thinkingBudget=-1`) está **default-on en API también** si no seteás nada. Ary dice "sin thinking_config explícito" → default = dynamic ON.
- ⚠️ **Esto significa que thinking probablemente NO es la diferencia entre web y API en este caso.** Verificar el código real (¿se pasa `thinking_budget=0` en algún lado?).
- Confidence: low como root cause; verificar en código.

---

## 2. Antecedentes documentados

### GitHub issues (oficial / first-tier)
- [`google-gemini/cookbook#907`](https://github.com/google-gemini/cookbook/issues/907) — 2025-08-20 — "Gemini 2.5 Flash Model Inconsistency Between API and Online Interface". Mismo prompt + misma imagen → distintos resultados AI Studio vs SDK. **Es exactamente el patrón de Ary.** Google etiquetó "off-topic:model quality", sin resolver. `[high-confidence]`
- [`googleapis/python-genai#706`](https://github.com/googleapis/python-genai/issues/706) — 2025-04-19 — JSON mode 2.5 degrada vs 2.0. Cerrada sin respuesta sustantiva. `[high-confidence]`
- [`google-gemini/cookbook#1028`](https://github.com/google-gemini/cookbook/issues/1028) — docs claiman structured output que el modelo no entrega.
- [`BerriAI/litellm#10134`](https://github.com/BerriAI/litellm/issues/10134) — third-party reproduce el patrón de regresión JSON.
- [`googleapis/python-genai#319`](https://github.com/googleapis/python-genai/issues/319) — `response_schema` recursivo no soportado.

### Foros oficiales Google (discuss.ai.google.dev / discuss.google.dev)
- [thread/70615](https://discuss.ai.google.dev/t/different-output-in-ai-studio-and-api/70615) — 2025-03-06 — "Different Output In AI Studio and API". Staff Google sugiere "match hyperparameters" — no resuelve. `[high-confidence]`
- [thread/83830](https://discuss.ai.google.dev/t/significant-differences-in-behavior-between-gemini-models-and-ai-studio/83830) — 2025-05-19 — 2.5-flash-preview-04-17 funciona en AI Studio, "escupe garbage" vía SDK con mismos hiperparámetros. Sin respuesta oficial.
- [thread/86131](https://discuss.ai.google.dev/t/gemini-flash-thinking-pro-end-with-meaningless-character-when-temperature-is-0/86131) — Google staff recomienda subir T≥0.1. `[high-confidence]`
- [thread/100175](https://discuss.ai.google.dev/t/2-5-flash-stopped-delivering-true-json-structures/100175) — root cause: max_output_tokens default insuficiente para 2.5 Flash. `[high-confidence]`
- [thread/94561](https://discuss.ai.google.dev/t/gemini-2-5-flash-quality-degradation-based-on-internal-evals/94561) — "if i ran the same query 100 times, 10 times it works, 90 times it does not".
- [thread/106516](https://discuss.ai.google.dev/t/gemini-flash-2-5-preview-not-following-instructions/106516) — Flash falla más que Pro en instruction-following con prompts largos.
- [thread/143931](https://discuss.ai.google.dev/t/gemini-2-5-flash-gets-stuck-in-infinite-token-repetition-during-structured-json-output-litellm/143931) — loops en JSON estructurado.
- [discuss.google.dev/191340](https://discuss.google.dev/t/gemini-vision-on-vertex-ai-vs-ai-studio/191340) — staff Google confirma Vertex tiling 1800tok vs AI Studio 258tok. `[high-confidence]`

### HN / blogs técnicos con experimentos
- [HN 42953665](https://news.ycombinator.com/item?id=42953665) — fintech reemplazó OCR con Gemini, 96% accuracy, **caveats: non-determinismo a low temperature, "LLC→IIC" errors inaceptables para financial data**.
- [HN 43977047](https://news.ycombinator.com/item?id=43977047) — PDF español en 2.5 Pro: nativo malo, **convertir a JPG por página = casi perfecto**.
- [Castillo benchmark](https://dylancastillo.co/posts/gemini-structured-outputs.html) — 2024-12-27 — JSON-Schema empeora 5/6 tasks vs NL-prompt. Causa documentada: SDK ordena keys alfabéticamente, rompiendo CoT.
- [Box blog 2025-11](https://blog.box.com/gemini-3-flash-sets-new-standard-accuracy-unstructured-data-extraction) — Gemini 3 Flash supera a 2.5 Flash +10pp en PDFs, +13pp en multi-field.
- [Cloud blog 2025-05](https://cloud.google.com/blog/products/ai-machine-learning/gemini-2-5-pro-flash-on-vertex-ai) — Google posiciona Pro para extracción precisa, Flash para filtro.
- [TechCrunch 2025-12-17](https://techcrunch.com/2025/12/17/google-launches-gemini-3-flash-makes-it-the-default-model-in-the-gemini-app/) — Gemini 3 Flash = default app.
- [gemini.google/release-notes](https://gemini.google/release-notes/) — May 2026 = Gemini 3.5 Flash global rollout; free tier ruteo dinámico ("varying access").

### Docs oficiales relevantes (referencia)
- [/docs/document-processing](https://ai.google.dev/gemini-api/docs/document-processing) — native vision, 258 tok/página, prompt después del PDF.
- [/docs/structured-output](https://ai.google.dev/gemini-api/docs/structured-output) — `response_schema` recomendado primario; schema-less válido como fallback.
- [/docs/thinking](https://ai.google.dev/gemini-api/docs/thinking) — dynamic thinking default ON en 2.5 Flash.
- [/docs/prompting-strategies](https://ai.google.dev/gemini-api/docs/prompting-strategies) — "place specific instructions at the very end of the prompt".
- [/docs/system-instructions](https://ai.google.dev/gemini-api/docs/system-instructions) — persona/reglas/guardrails en system.

---

## 3. Diferencias verificables web vs API (aplicables al caso)

| Dimensión | Web (gemini.google.com / AI Studio) | API actual (stack de Ary) | Confidence |
|---|---|---|---|
| **Modelo servido** | Gemini 3 Flash (Dic-2025) → Gemini 3.5 Flash (May-2026); ruteo dinámico a Pro en tier pago | `gemini-2.5-flash` explícito | high |
| **System prompt inyectado** | `pcontext` + personas ocultas (gemini.google.com); AI Studio expone campo vacío opt-in | Ninguno — todo va en user turn | medium-high |
| **Tools default-on** | Grounding/search habilitable por toggle visible o ruteo; thinking on por default | `tools=[]`; thinking default = dynamic ON (no off) | high |
| **PDF preprocessing** | App con limits 100MB/10 archivos sugiere pipeline distinto; no documentado explícito | Native vision, resize 768×768–3072×3072, 258 tok/página, sin control de resolución en 2.5 | medium |
| **Temperature** | App orquesta dinámicamente (T=0 para extract, T=1 para summary) | T=0.0 fijo, anti-pattern documentado | high |
| **JSON shape** | Modelo libre, parsea prosa en respuesta | `response_mime_type=application/json` (constrained, regresión documentada en 2.5) | high |
| **Orden contents** | N/A (chat UI) | `[prompt, PDF]` — invertido respecto a 4 docs oficiales | high |
| **`max_output_tokens`** | Manejado internamente | Probablemente default (8192); 2.5 Flash necesita más que 2.0 | medium-high |

---

## 4. Recomendaciones accionables

### Tier 1 — bajo esfuerzo, alta evidencia (ejecutar primero, en orden)

1. **Subir `temperature` de 0.0 → 0.1** — Google staff lo recomienda oficialmente. Cambio de 1 línea. Si funciona, descarta el sospechoso #1.
2. **Invertir orden `contents` a `[PDF_part, prompt_string]`** — 4 docs oficiales lo recomiendan. Cambio de 1 línea.
3. **Setear `max_output_tokens` explícito a 16384 o 32768** — descartar truncamiento silencioso. Cambio de 1 línea.
4. **Verificar en código que `thinking_budget` no está siendo seteado a 0 implícitamente** — el default es dynamic ON; si en algún lado se está pasando 0, perdés thinking. (Inspección, no cambio.)

> **Si después de Tier 1 ya el smoke test pasa de 0% verde a algo no trivial, frenar y medir antes de seguir.**

### Tier 2 — medio esfuerzo, evidencia media-alta

5. **Spike `gemini-2.5-pro` vs `gemini-2.5-flash`** con mismo prompt y eval set. Box midió +10pp en PDFs y +13pp en multi-field. Si Pro pasa el bar y Flash no, decisión de modelo se vuelve sobre costo, no sobre técnica.
6. **A/B test: `response_mime_type=application/json` (actual) vs JSON-en-prompt + parseo manual** — Castillo midió que JSON-Schema empeora; reproducir en cartolas. Si JSON-en-prompt gana → estás peleando contra el constrained decoder.
7. **Migrar reglas estables a `system_instruction`**, dejar user turn = `[PDF_part, "Extraé esta cartola al JSON canónico definido en system."]`. Alineado con docs oficiales. Magnitud no medida — validar con eval set.

### Tier 3 — más esfuerzo, validar si Tier 1+2 no cierran el gap

8. **Spike: rasterizar PDF a PNG/JPG por página lado cliente, mandar como `image/png`** — HN 43977047 + thread 191340. Esquiva el parser interno de PDF + da control de resolución que 2.5 no expone.
9. **Spike: Vertex AI en lugar de Gemini API directa** — tiling ~1800 tok/imagen vs 258 tok. Cambio infra mayor; valida primero el spike 8 que es más barato.
10. **Spike: probar `gemini-3-flash` directo** si ya está disponible en API (verificar models page) — la web probablemente está corriendo este modelo; reducir gap de comparación.

### Tier 4 — cross-cutting (hacer ahora aunque no cierre nada)

11. **Construir eval set determinista** (los 14 PDFs × N corridas con `random_seed` si está disponible) **antes** de tocar más nada. Sin esto, cada cambio de Tier 1-3 es opinión. Esto es prerequisito para todos los spikes.

**Ranking sugerido del próximo spike (Story 9.5e):** Tier 1 (1+2+3+4) en un solo PR, medir con eval. Si verde → fin. Si rojo → Tier 2.5 (cambiar a Pro), después Tier 2.6 (JSON-en-prompt vs response_mime_type). Tier 3 solo si los anteriores no llegan al SLA.

---

## 5. Gaps de información

Cosas que NO se pudieron determinar sin acceso a infra interna Google:

- **Qué modelo exacto sirvió la web de Gemini el día del test del usuario (2026-05-19).** Release notes dicen "rollout global Gemini 3.5 Flash en May 2026" sin fecha exacta. Free tier tiene "varying access" a Pro.
- **Si AI Studio "Get code" produce realmente la misma llamada que la web ejecuta.** Cookbook#907 sugiere que NO, pero Google no confirma.
- **Si la API clampea internamente `temperature=0.0` a un epsilon** — evidencia indirecta de no-determinismo a T=0, pero no doc oficial.
- **Pipeline interno exacto de PDF en gemini.google.com vs API** — limits distintos (100MB/10 archivos app vs 50MB/1 archivo API) sugieren pipelines distintas, pero el cómo no está documentado.
- **Umbral concreto de "prompt largo" en 2.5 Flash** donde degrada instruction-following. Reportes comunitarios consistentes, ningún número oficial.
- **Resolución default exacta para PDFs en 2.5 Flash** — doc da rango 768×768 a 3072×3072, no especifica default. `media_resolution` control no existe en 2.5.
- **Si `oneOf` está soportado en `response_schema`** — no aparece en la lista de keywords soportadas; `anyOf` sí (desde 2025-11). Tratar como no soportado.
- **Impacto medible de prompt en español vs inglés** para parsing de docs en español — sin doc oficial, sin benchmark.
- **Tabla numérica DocVQA/ChartQA/TextVQA del Gemini 2.5 tech report** (arxiv 2507.06261) — PDF 9.7MB no parseó vía WebFetch; abstract confirma que existe.
- **Costo exacto del thinking budget en 2.5 Flash extracción real** — pricing no separa "thinking rate"; reports comunitarios hablan de ~5.8x output cost, no oficial.

---

## Anexo: Fuentes consultadas

### Docs oficiales Google
- https://ai.google.dev/gemini-api/docs/document-processing
- https://ai.google.dev/gemini-api/docs/structured-output
- https://ai.google.dev/gemini-api/docs/prompting-strategies
- https://ai.google.dev/gemini-api/docs/system-instructions
- https://ai.google.dev/gemini-api/docs/live-api/best-practices
- https://ai.google.dev/gemini-api/docs/thinking
- https://ai.google.dev/gemini-api/docs/tools
- https://ai.google.dev/gemini-api/docs/code-execution
- https://ai.google.dev/gemini-api/docs/media-resolution
- https://ai.google.dev/gemini-api/docs/files
- https://ai.google.dev/gemini-api/docs/prompting_with_media
- https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.5
- https://ai.google.dev/gemini-api/docs/ai-studio-quickstart
- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/pricing
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/document-understanding
- https://cloud.google.com/blog/products/ai-machine-learning/gemini-2-5-pro-flash-on-vertex-ai
- https://cloud.google.com/blog/products/ai-machine-learning/expanding-gemini-2-5-flash-and-pro-capabilities
- https://blog.google/innovation-and-ai/technology/developers-tools/gemini-api-structured-outputs/
- https://developers.googleblog.com/en/gemini-api-and-ai-studio-now-offer-grounding-with-google-search/
- https://developers.googleblog.com/en/start-building-with-gemini-25-flash/
- https://gemini.google/release-notes/
- https://gemini.google/overview/canvas/

### GitHub issues
- https://github.com/google-gemini/cookbook/issues/907
- https://github.com/google-gemini/cookbook/issues/1028
- https://github.com/googleapis/python-genai/issues/706
- https://github.com/googleapis/python-genai/issues/319
- https://github.com/BerriAI/litellm/issues/10134
- https://github.com/google-gemini/gemini-cli/issues/13787
- https://github.com/google-gemini/deprecated-generative-ai-python/issues/745
- https://github.com/langchain-ai/langchain-google/issues/474
- https://github.com/Fosowl/agenticSeek/issues/409

### Foros oficiales (discuss.ai.google.dev)
- https://discuss.ai.google.dev/t/different-output-in-ai-studio-and-api/70615
- https://discuss.ai.google.dev/t/significant-differences-in-behavior-between-gemini-models-and-ai-studio/83830
- https://discuss.ai.google.dev/t/different-responses-in-ai-studio-and-api-for-fine-tuned-gemini-1-0-model/6247
- https://discuss.ai.google.dev/t/gemini-2-0-flash-returning-different-result-for-the-same-prompt/80893
- https://discuss.ai.google.dev/t/structured-output-poor-consistency/72304
- https://discuss.ai.google.dev/t/gemini-2-5-flash-quality-degradation-based-on-internal-evals/94561
- https://discuss.ai.google.dev/t/2-5-flash-stopped-delivering-true-json-structures/100175
- https://discuss.ai.google.dev/t/gemini-flash-thinking-pro-end-with-meaningless-character-when-temperature-is-0/86131
- https://discuss.ai.google.dev/t/gemini-2-5-flash-gets-stuck-in-infinite-token-repetition-during-structured-json-output-litellm/143931
- https://discuss.ai.google.dev/t/gemini-2-5-flashs-extremely-long-inputs-are-highly-unstable/87952
- https://discuss.ai.google.dev/t/gemini-flash-2-5-preview-not-following-instructions/106516
- https://discuss.ai.google.dev/t/inconsistent-gemini-output-with-identical-input-even-at-temperature-0/98096
- https://discuss.google.dev/t/gemini-vision-on-vertex-ai-vs-ai-studio/191340
- https://support.google.com/gemini/thread/379487030
- https://support.google.com/gemini/thread/340196124/system-prompt-handling-in-gemini

### Blogs / HN / benchmarks
- https://dylancastillo.co/posts/gemini-structured-outputs.html
- https://blog.box.com/gemini-3-flash-sets-new-standard-accuracy-unstructured-data-extraction
- https://news.ycombinator.com/item?id=42953665
- https://news.ycombinator.com/item?id=43977047
- https://techcrunch.com/2025/12/17/google-launches-gemini-3-flash-makes-it-the-default-model-in-the-gemini-app/
- https://jonathangerhardson.substack.com/p/google-geminis-pcontext-prompt-leaked
- https://medium.com/@alexefimenko/i-read-the-system-prompts-leaks-for-claude-gemini-and-chatgpt-here-is-what-i-found-340131ab7bb0
- https://medium.com/google-cloud/best-practices-for-prompt-engineering-with-gemini-2-5-pro-755cb473de70
- https://llm-stats.com/models/compare/gemini-2.5-flash-vs-gemini-2.5-pro
- https://arxiv.org/abs/2507.06261
- https://www.datastudios.org/post/google-gemini-pdf-uploading-pdf-reading-capabilities-text-extraction-accuracy-layout-support-and
