---
stepsCompleted: [1]
inputDocuments:
  - _bmad-output/planning-artifacts/research/technical-gemini-web-vs-api-pdf-extraction-research-2026-05-19.md
  - _bmad-output/coordination/9-5f-spike-tier1-results-2026-05-20.md
  - _bmad-output/coordination/9-5c-hallazgo-prompt-2026-05-19.md
  - _bmad-output/implementation-artifacts/9-5e-prompt-gemini-csv-liviano-wrapping-server-side.md
workflowType: 'research'
research_type: 'technical'
research_topic: 'Herramientas y arquitecturas para extracción de cartolas bancarias chilenas en PDF — frontier LLMs + Document AI especializado (2026)'
research_goals: 'Determinar qué herramienta/modelo/arquitectura ofrece la mejor combinación de accuracy + costo + privacidad para extraer cartolas bancarias chilenas (BCI/Santander/Banco de Chile, mix CLP/USD, tarjetas + cuentas corrientes) a un JSON canónico, con eval determinista (gate ≥90% verde sobre 14 PDFs reales). El research previo (Gemini web vs API) cerró que el modelo es parte del problema; falta evaluar alternativas.'
user_name: 'Ary'
date: '2026-05-20'
web_research_enabled: true
source_verification: true
---

# Research Report: Herramientas para extracción de cartolas bancarias chilenas en PDF (2026)

**Date:** 2026-05-20
**Author:** Ary
**Research Type:** Technical
**Context:** Family Office EAG — Epic 9 — sucesor del research Gemini web vs API (2026-05-19) + spike 9.5f tier-1 (2026-05-20)

---

## Research Overview

### Estado a la fecha (qué probamos y qué medimos)

| Probado | Resultado | Métrica eval (14 PDFs × 3 runs) |
|---|---|---|
| Gemini 2.5 Flash (baseline) | 0% verde, 57% rojo | Gate ≥90% verde: FAIL |
| Gemini 2.5 Flash + Tier 1 SDK params (T=0.1, max_tokens=32768, contents=[PDF, prompt]) | 0% verde, 57% rojo | Sin mejora |
| Gemini 2.5 Pro + Tier 1 SDK params | 0% verde, 85.7% balance OK (`diff=0.00`) | 12/14 PDFs matemáticamente correctos; problema = warnings espurios |
| 8 spikes de variación de prompt (9.5e A–H) | Sin verde sostenido | El wording exacto del prompt cambia drásticamente el output |
| Prompt corto réplica de Gemini Web | Confirma que API encuentra openings correctos con prompt liviano | Inconsistente entre PDFs |

### Constraints del proyecto (fija el espacio de soluciones aceptable)

- **PDFs:** bancos chilenos (BCI, Santander, Banco de Chile), tarjetas de crédito + cuentas corrientes, mix CLP/USD, ~14 PDFs reales en `samples/` como eval set determinista.
- **Output target:** JSON canónico `CartolaCanonicalV1` con `transactions[]`, `balances.opening/closing`, `period.start/end`, `currency`, `extraction.warnings`.
- **Volumen:** ~50 cartolas/mes (single operator family office).
- **PII:** datos sensibles de transacciones reales. Hoy ya van a Gemini API; lo asumimos como baseline aceptable, pero queremos visibilidad del residency/retention de cada alternativa.
- **Stack:** Python backend, integración via SDK/HTTP. Hay eval determinista (`bootstrap/validate_cartolas_batch.py`).
- **Costo:** ~$1.05 gastados en 135 calls (3 corridas × 14 PDFs + verificaciones). Costo aceptable por cartola estimado: <$1.

### Goals del research

1. **Eje A — Frontier LLMs head-to-head**: Claude 4.7/4.6, GPT-5 vision, Gemini 3.5/3.1, Mistral OCR head-to-head sobre task de extracción de bank statements. Tabla accuracy/cost/latency + recomendación.
2. **Eje B — Document AI especializados**: Google Document AI (Bank Statement Parser), AWS Textract, Azure DI prebuilt `bankStatement`, Reducto, Unstructured.io, Mistral OCR, Rossum, Nanonets. ¿Existe servicio pre-entrenado que ya hace este task?
3. **Eje C**: arquitecturas híbridas (text-layer + LLM, two-pass extract+verify, multi-model voting, Open Banking).

---

## Executive Summary — qué hacer mañana (síntesis A+B+C)

Decisión arquitectónica recomendada, **cheap-first**, con cada paso medible contra el eval ya existente (`bootstrap/validate_cartolas_batch.py`):

### Path priorizado (probar en este orden, parar al primer "verde sostenido")

| # | Acción | Effort | Costo | Probabilidad de cerrar gate ≥90% | Justificación |
|---|---|---|---|---|---|
| **1** | **Quitar warnings espurios del prompt + agregar deterministic constraint validators post-extracción** (Pydantic `@model_validator`: balance reconcile por currency, period containment con excepción para `fecha_operacion` de cuotas, sum check). **Mantener Gemini 2.5 Pro.** | 1 día | $0 | **Alta** | Spike 9.5f ya midió **85.7% balance OK con Pro** (`diff=0.00` en 12/14). El gap es warnings espurios + post-process flaggeando cuotas legítimas. Eje C confirma: Plaid/Daloopa/Unstract usan exactamente este patrón — *"never let LLMs perform numerical extraction without deterministic verification"*. |
| **2** | **Re-correr el spike con Gemini 3.5 Flash** (drop-in upgrade del SDK actual; release 2026-05-19). | 2h | ~$0.15 | Media-alta | ExtractBench (arxiv feb 2026): Gemini Flash **lidera schema validity (71%) sobre Claude Opus/Sonnet y GPT-5/5.2** y supera al propio Pro — coincide con nuestro finding. 4× más rápido que la gen previa, costo similar. |
| **3** | **Instructor (Pydantic + retry) sobre el cliente Gemini**, con re-prompt automático cuando un validator falla, incluyendo el error específico en el feedback. | 2-3 días | marginal | Media-alta | Esto es "9.5d hecho bien" — re-prompt CON el error de constraint específico, no genérico. 11K stars, plug-in a `gemini_client.py`. |
| **4** | **Testear Mindee Bank Statement OCR API con los 14 PDFs** (único IDP cloud con processor dedicado + multi-país + español documentado + GDPR). | 3h, free trial | <$50 | Media | Si funciona, reemplaza el LLM por API determinista de costo predecible (~€44/mes). Si falla, descarta toda la familia "IDP especializado". |
| **5** | **POC Open Banking con Boufin** (cubre BCI + Santander + Banco de Chile explícitamente, Ley 21.521 SFA operativa). | 1 semana | requiere cotización | Alta (bypass arquitectónico) | **Cambia el contrato** — usuario provee credenciales bancarias en vez de subir PDF. Elimina el problema de extracción de raíz. Vale la pena explorarlo **en paralelo** a los pasos 1-3 si Ary acepta la fricción operacional. |

> **Si los pasos 1-2 cierran el gate** (probabilidad alta), problema resuelto sin pivot. **Si no**, los pasos 3-4 son cheap-tests con downside contenido. **Paso 5 es la apuesta arquitectónica** que vale la pena cotizar en paralelo aunque no cambies hoy.

### Lo que NO recomienda este research

- **Claude Opus 4.7**: caro (5× Sonnet), MRCR regresión documentada por Anthropic (78%→32% long-context), tokenizer nuevo +35% tokens.
- **GPT-5.5**: $5/$30 sin evidencia de superioridad sobre Gemini Flash para este task específico.
- **Mistral OCR 3 standalone**: fallo catastrófico documentado en bank statements (Docsumo: 0/120 preferencias; Reducto: 43% menos accurate que Gemini 2.0 Flash en docs financieros).
- **Google DocAI / AWS Textract / Azure DI `bankStatement`**: los 3 son **English-only / US-only** en sus prebuilt parsers — descartados por idioma, no por capacidad.
- **Rossum / IDPs enterprise**: minimum spend $5K+/año no se amortiza con 50 docs/mes.
- **Marker / Docling como pre-procesador (markdown → LLM)**: paper IEEE Big Data 2025 (arxiv 2509.04469) muestra **vision directa supera markdown intermediario** en docs financieros. Upside acotado, downside real (pérdida de info de layout).
- **Self-consistency N=3+ majority vote**: ya implícito en las 3 corridas del eval; si el bias es sistemático (que es la hipótesis del spike 9.5f), majority vote no lo arregla.

### Hallazgo arquitectónico clave que cambia el framing del problema

**El diagnóstico previo del proyecto (memo 9.5c "el prompt está degradando el output") es parcialmente correcto pero incompleto.** El spike 9.5f midió que **con Gemini Pro la extracción matemática es correcta en 12/14 PDFs**. Lo que falta para cerrar el gate ≥90% no es "extraer mejor", es **separar la extracción (LLM) de la validación (capa determinista)**. Patrón confirmado por Plaid (reducción de alucinación 65.2%→1.6%), Daloopa y Unstract. El `CartolaCanonicalV1` actual puede absorber esto sin schema change si se modela inspirado en **ISO 20022 CAMT.053** (CdtDbtInd CRDT/DBIT enum para signo + `booking_date`/`value_date` separados + currency per-transaction) — mata 3 clases de warning espurio por construcción.

### Bypass arquitectónico (no acción inmediata, pero merece evaluación paralela)

**Chile tiene Open Banking maduro y operativo en 2026.** Boufin lista explícitamente BCI + Santander + Banco de Chile + Falabella en su roster de bancos integrados. Ley 21.521 (Sistema Financiero Abierto) entra en full force julio 2026 (CMF propuso extensión a julio 2027). Esto es **un bypass real al problema de PDF extraction**, no una hipótesis lejana. Si Ary acepta que el usuario provea credenciales bancarias en vez de subir PDFs, el problema deja de existir. Recomendación: pedir cotización a Boufin en paralelo a los pasos 1-3, sin bloquear ningún trabajo.

---

<!-- Content will be appended sequentially through research workflow steps -->

## Eje A — Frontier LLMs head-to-head (2026)

**Fecha:** 2026-05-20 · **Scope:** comparar frontier multimodales para extraer cartolas bancarias chilenas (~10 págs, ~50 tx, mix CLP/USD, español) a JSON canónico, con eval determinista (gate ≥90% verde sobre 14 PDFs).

### Resumen ejecutivo (lo que importa primero)

Si tuviera que poner plata mañana:

1. **Gemini 3.5 Flash** (release 2026-05-19) — primer candidato a re-correr el spike, **mismo PDF pipeline ya integrado**, output 4× más rápido que la generación previa, ganó top spot en validez del schema en ExtractBench (71% válido vs ~60% del resto), y mantiene precio ($1.50/$9 per M) razonable para 50 cartolas/mes. Lo más cerca de un "drop-in upgrade" sin reescribir el cliente.
2. **Claude Sonnet 4.6** — el más confiable en structured outputs (99.8% schema compliance, segundo solo a OpenAI), con vision sólida sobre documentos densos. Si Gemini 3.5 Flash no cierra el gate, este es el siguiente. Costo ($3/$15) ~2× Gemini Flash pero todavía <$1/cartola.
3. **Mistral OCR 3** (specialized) — wildcard. $1–2 por **1000 páginas** (no tokens). Documented failure mode: "trata tabla entera como imagen, no extrae nada" en bank statements en el benchmark de Docsumo. Útil sólo si lo combinamos con un LLM en arquitectura híbrida (Eje C). Por sí solo NO resuelve el caso.

Lo que **NO** recomiendo como next step:

- **Claude Opus 4.7**: caro (5× Sonnet input, 5× Flash output), MRCR regresión de 78%→32% confirmada por Anthropic, vision excelente pero overkill por costo.
- **GPT-5.5**: PDF input nativo existe (`input_file` en Responses API), schema compliance líder, pero $5/$30 lo pone como el más caro de los tres frontier; sin evidencia clara de superioridad en español sobre Gemini.
- **Llama 4 Maverick/Scout**: DocVQA 94.4 es competitivo, pero no hay hosted API con privacy tier maduro; self-hosting introduce ops complexity que no se justifica para 50 cartolas/mes.

> **Hallazgo sorprendente / contra-hipótesis del proyecto:** ExtractBench (arxiv 2602.12247, frontier benchmark de Feb 2026) reporta que **Gemini Flash supera a Gemini Pro** en validez de schema (71% vs Pro inferior) y pass rate sobre extracciones complejas — coincide con nuestro propio finding del spike 9.5f donde Pro tenía 85.7% balance OK pero fallaba por warnings espurios. **No es seguro que un modelo "más grande" sea mejor para este task.**

---

### Tabla resumen (head-to-head)

| Modelo | Doc-ext accuracy (independiente) | Structured output compliance | $/cartola* (10p, 5k out) | Latencia | Privacy | Español | Ganador en… |
|---|---|---|---|---|---|---|---|
| **Gemini 3.5 Flash** | 71% schema validity (ExtractBench, lead) [M] | strong, mejorado nov 2025 (`additionalProperties` soportado) [M] | ~$0.07–0.15 | 289 tok/s output, TTFT 18.5s en AI Studio [M] | ZDR disponible on-request (Developer API), 24h TTL default [H] | ingest multilingüe 100+ idiomas, sin benchmark español-PDF público [L] | **velocidad + costo + schema** |
| **Gemini 3.1 Pro** | inferior a Flash en validez [M], lidera Video-MME y OmniDocBench [M] | bug `additionalProperties` SDK reportado dic 2025 [M] | ~$0.10–0.20 | más lento que Flash [M] | igual que Flash [H] | igual que Flash [L] | razonamiento largo |
| **Claude Opus 4.7** | 93.8% en doc-test con handwriting/stamps/tablas irregulares [M], FinanceBench 82.7% [H] | structured outputs (beta) | ~$0.30–0.60 (tokenizer +35% vs 4.6) [H] | 71 tok/s output [M] | enterprise tier ZDR estándar [H] | sin benchmark español-PDF público [L] | **vision densa + finance reasoning** |
| **Claude Sonnet 4.6** | 97.6% extracción "compleja" (vendor-aligned blog) [L], 98.2% invoice field-extraction (one benchmark) [L] | **99.8% schema compliance** (segundo a OpenAI) [M] | ~$0.15–0.30 | ~tier intermedio Anthropic [M] | enterprise tier ZDR estándar [H] | sin benchmark público [L] | **balance accuracy/costo/JSON** |
| **Claude Haiku 4.5** | sin benchmark específico de docs encontrado [L] | structured outputs disponible [M] | ~$0.05–0.10 | el más rápido de Anthropic [M] | enterprise tier ZDR estándar [H] | sin data [L] | budget Anthropic |
| **GPT-5.5** | 88.9% document understanding (vendor) [L] | schema compliance líder (OpenAI implementation) [M] | ~$0.30–0.60 | n/d en docs públicos [L] | enterprise ZDR estándar [H] | fuerte multilingüe histórico [M] | **schema compliance** |
| **Mistral OCR 3** | **bank statement fail documentado** (Docsumo, 0/120 preferencias) [H]; 74% win-rate vs OCR 2 (vendor) [L] | salida markdown estructurada, no schema | **$0.002/página** (10p ≈ $0.02) [H] | rápido (specialized) [M] | Azure AI Foundry hospedado [M] | 99%+ across 90+ langs (vendor) [L] | **OCR puro barato, NO single-shot extraction** |
| **Pixtral Large** | general multimodal, no specialized en docs [L] | tool use estándar [L] | similar a Mistral Large tier [M] | n/d [L] | igual Mistral [M] | igual [L] | general purpose |
| **Llama 4 Maverick** | **DocVQA 94.4**, ChartQA 90.0, MMMU 73.4 [M] | tool use estándar [L] | open-weights (variable según host) [M] | depende del host [L] | **self-host = control total**, hosted varies [M] | open multi [L] | open-weights, 10M ctx (Scout) |
| **Llama 4 Scout** | DocVQA 94.4, 10M context (recordbreaker) [M] | igual Maverick [L] | igual [M] | igual [L] | igual [M] | igual [L] | mega-context |

*Costo estimado: PDF de ~10 págs = ~15k–25k input tokens (extraído + imagen por página) + ~5k output. Calculado con pricing oficial mayo 2026.

**Leyenda confidence:** [H] high (fuente oficial primaria o benchmark independiente reproducido), [M] medium (single source o vendor-aligned con corroboración parcial), [L] low (claim sin verificación independiente o ausencia de benchmark específico).

---

### Por modelo — detalle

#### Claude Opus 4.7 (Anthropic, abr 2026)

- **PDF handling:** Claude extrae texto del PDF Y convierte cada página a imagen, ambos van al contexto. ~1.5k–3k tokens/página de texto más cost de imagen. Opus 4.7 es el primer modelo con high-res 2576px (3.75MP), vs 1568px previo — **3× más image tokens por página** ([docs.claude.com PDF support](https://docs.claude.com/en/docs/build-with-claude/pdf-support), [Vellum benchmark blog](https://www.vellum.ai/blog/claude-opus-4-7-benchmarks-explained)). [H]
- **Structured output:** beta de Structured Outputs activable via `anthropic-beta` header, schema-constrained ([platform.claude.com structured-outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)). [H] Garantiza forma, **no semántica** — sigue pudiendo alucinar valores correctos en formato. [H]
- **Benchmarks doc:** 93.8% en test compuesto (handwriting + stamps + tablas irregulares + escaneos low-res); 98.5% visual-acuity (vs 54.5% en 4.6); FinanceBench 82.7%; Finance Agent SOTA 64.4% ([MindStudio breakdown](https://www.mindstudio.ai/blog/claude-opus-47-benchmark-breakdown), [Anthropic blog](https://www.anthropic.com/news/claude-opus-4-7)). [M]
- **Costo:** $5/$25 per M (input/output). **Gotcha:** tokenizer nuevo en 4.7 consume hasta **35% más tokens** para el mismo texto vs 4.6 ([finout pricing](https://www.finout.io/blog/anthropic-api-pricing)). [H]
- **Latencia:** ~71 tok/s output (lento) [M].
- **Privacy:** enterprise zero-data-retention tier estándar Anthropic [H].
- **Español:** no encontré benchmark Spanish-PDF específico. Anthropic es históricamente sólido en multilingüe pero nadie publicó números cartolas-CL. [L]
- **Quirks:** **MRCR regression 78%→32%** — Anthropic admitió que está "phasing out MRCR" en favor de Graphwalks ([blog.wentuo.ai analysis](https://blog.wentuo.ai/en/claude-opus-4-7-long-context-regression-en.html)). Implica que long-context multi-needle retrieval (que SÍ aplica a cartolas largas con muchas transacciones) puede regresar vs 4.6. **Bandera amarilla para cartolas de 20+ páginas con 100+ transacciones.** [M]

#### Claude Sonnet 4.6 (Anthropic, feb 2026)

- **PDF handling:** mismo pipeline que Opus (text + page-image), vision menor que 4.7 (no tiene high-res 2576px upgrade). [H]
- **Structured output:** **99.8% schema compliance vía tool use** — número independiente segundo solo a OpenAI ([tokenmix.ai structured-output guide](https://tokenmix.ai/blog/structured-output-json-guide)). [M]
- **Benchmarks doc:** una source (vendor-aligned) reporta 97.6% accuracy en "complex layouts" y 98.2% field-extraction sobre 1000 invoices ([TokenMix](https://tokenmix.ai/blog/best-ai-for-document-processing), [Claude5 Hub](https://claude5.com/news/multimodal-ai-face-off-claude-gpt-4v-and-gemini-in-2026)). Tomar con sal — no es un benchmark estándar como ExtractBench. [L]
- **Costo:** $3/$15 per M. ~$0.15–0.30/cartola.
- **Privacy/Español:** igual que Opus.
- **Por qué es candidato #2:** mejor combinación schema-compliance + costo de Anthropic. Si Gemini 3.5 Flash falla en validez de JSON, Sonnet 4.6 es la apuesta más segura. [M]

#### Claude Haiku 4.5 (Anthropic, oct 2025)

- **PDF handling:** igual pipeline. Pero sin documentación de benchmarks doc-extraction recientes — Anthropic posicionó a Haiku como "fast, cheap" pero no publicó scores doc-specific reproducibles. [L]
- **Costo:** $1/$5 per M — el más barato de Anthropic. ~$0.05–0.10/cartola.
- **Decisión:** sin evidencia de doc-extraction performance, **no incluir en spike**. Si Sonnet 4.6 funciona excelente, podría ser fallback de costo, pero no validar primero. [L]

#### GPT-5.5 / GPT-5 (OpenAI, abr 2026 / ago 2025)

- **PDF handling:** **PDF input nativo** vía Responses API (`input_file` con URL o file ID). API extrae texto + page-images automáticamente y los envía al modelo en context ([OpenAI File Inputs docs](https://developers.openai.com/api/docs/guides/file-inputs), [OpenAI announcement](https://community.openai.com/t/direct-pdf-file-input-now-supported-in-the-api/1146647)). Max 50MB por file. [H]
- **Structured output:** OpenAI lleva la delantera en schema compliance ([tokenmix](https://tokenmix.ai/blog/structured-output-json-guide)). [M]
- **Benchmarks:** GPT-5.5 reporta 88.9% document understanding (vendor), arquitectura 32×32 patch grid mejora interpretación de docs alta resolución ([MindStudio GPT-5.5 review](https://www.mindstudio.ai/blog/gpt-5-5-review-agentic-model)). En ExtractBench, GPT-5/5.2 está entre los frontier evaluados (sin lead claro). [M]
- **Costo:** $5/$30 per M. **Más caro de los tres frontier evaluados**. Cached input -90%. [H]
- **Privacy:** ZDR estándar enterprise tier OpenAI [H].
- **Por qué no #1:** sin evidencia que justifique 2-3× el costo de Gemini Flash para este task específico. Si el cuello sale ser schema compliance puro (ej: el modelo genera JSON inválido sintácticamente), GPT-5.5 es el más seguro — pero ese no es nuestro problema actual (nuestro JSON es válido, los warnings son espurios y los balances fallan). [M]

#### Gemini 3.5 Flash (Google, may 2026)

- **PDF handling:** soporte nativo PDF + image + video + audio ([apidog Gemini 3.5 Flash](https://apidog.com/blog/what-is-gemini-3-5/)). Mismo pipeline que 2.5 (que ya usamos). [H]
- **Structured output:** la SDK Python `google-genai` tenía bug `additionalProperties` reportado dic 2025 que la API ya soporta desde nov 2025 ([GitHub issue 1815](https://github.com/googleapis/python-genai/issues/1815)) — verificar versión SDK al re-correr. [M]
- **Benchmarks:** 76.2% Terminal-Bench, 84.2% CharXiv Reasoning multimodal, 1656 Elo GDPval-AA, 83.6% MCP Atlas ([MarkTechPost launch](https://www.marktechpost.com/2026/05/20/google-introduces-gemini-3-5-flash-at-i-o-2026-a-faster-and-cheaper-model-for-ai-agents-and-coding/)). **Flash supera a Gemini 3.1 Pro en agentic/coding** — generation gap importante. [M]
- **ExtractBench (independiente):** "Gemini models achieve strongest overall results, with Flash leading on both validity (71%, 25/35) and pass rate (6.9%), notably outperforming the larger Pro" ([arxiv 2602.12247](https://arxiv.org/abs/2602.12247)). **Lead independiente sobre Claude 4.5 Opus/Sonnet y GPT-5/5.2 en validez de schema**. [H]
- **Costo:** $1.50 input / $9 output per M. Cached input $0.15/M (90% off). 3× más caro que 3 Flash Preview pero ~40% más barato que Gemini 3.1 Pro ([apidog pricing](https://apidog.com/blog/gemini-3-5-flash-pricing/)). [H]
- **Latencia:** 289 tok/s output (4× Claude Opus 4.7). TTFT 18.5s primer token en AI Studio (alto — verificar Vertex AI / direct API) ([artificialanalysis.ai providers](https://artificialanalysis.ai/models/gemini-3-5-flash/providers)). [M]
- **Privacy:** ZDR disponible on-request en Developer API, default 24h TTL in-memory cache ([Google ZDR docs](https://ai.google.dev/gemini-api/docs/zdr)). [H]
- **Quirks/Gotchas:**
  - Gemini 2.5 Pro tuvo "performance regression" documentada mid-2025 (context collapse, repetición). **Lección:** Google a veces silently downgrades modelos servidos. Pinear version exacta (`gemini-3.5-flash-05-2026`). [M]
  - SDK validation gotcha con `additionalProperties` — actualizar SDK. [M]
  - El "temperature=0 anti-pattern" de Gemini sigue vigente (greedy decoding hace que el modelo se atasque) — usar T≥0.1. [H]

#### Gemini 3.1 Pro (Google)

- **Benchmarks:** lidera OmniDocBench (estándar 2026 para document AI) y Video-MME ([gurusup ai-comparisons](https://gurusup.com/blog/ai-comparisons), [aimagicx benchmark breakdown](https://www.aimagicx.com/blog/claude-opus-4-6-vs-gpt-5-4-vs-gemini-3-1-benchmark-comparison-april-2026)). [M]
- **Pero:** **superada por 3.5 Flash en agentic/structured tasks** (ExtractBench y la propia documentación de Google). [H]
- **Costo:** $2/$12 per M.
- **Por qué no recomendar:** si el caso fuera razonamiento sobre docs muy largos, sería defensible. Para extracción estructurada de cartolas, Flash es mejor Y más barato. [M]

#### Mistral OCR 3 (Mistral, dic 2025)

- **PDF handling:** OCR specialized. Output markdown estructurado por defecto, no JSON schema-bound. [H]
- **Bank statement performance — RED FLAG:** Docsumo benchmark independiente (120 docs, 3 human reviewers): Mistral OCR **0/120 preferencias** vs Docsumo 116/120 y Landing AI 4/120. Caso documentado: "una tabla completa fue tratada como imagen, sin data extraída" ([Docsumo benchmark](https://www.docsumo.com/blogs/ocr/docsumo-ocr-benchmark-report)). [H]
- **Vendor claim:** 94.9% accuracy across diverse document types ([mistral.ai/news/mistral-ocr](https://mistral.ai/news/mistral-ocr)). Discrepancia fuerte con benchmark independiente — **trust the indep**. [H]
- **Costo:** $2/1000 páginas → $0.02/cartola. **Order of magnitude cheaper than LLM input**. Si funcionara, sería irresistible. [H]
- **Decisión:** **NO usar standalone para cartolas**. **SÍ explorable** en arquitectura híbrida (Eje C): Mistral OCR como pre-processor para markdown → LLM para JSON estructurado. Esto desacopla "leer la página" de "estructurar". [M]

#### Llama 4 Maverick / Scout (Meta)

- **Benchmarks doc:** DocVQA 94.4 (Maverick y Scout), ChartQA 90.0, MMMU 73.4 ([abhs.in Llama 4 benchmarks](https://www.abhs.in/blog/meta-llama-4-multimodal-open-source-benchmarks-2026)). Scout tiene **context 10M** — overkill para cartolas pero impresionante. [M]
- **Privacy:** ventaja teórica de self-hosting (control total de datos).
- **Costo real:** depende del host (Together, Groq, Fireworks). En Together AI Maverick ronda $0.27/$0.85 per M — barato.
- **Por qué no recomendar primero:** ops complexity (deploy, GPU, monitoring) no justificada para 50 cartolas/mes. Si el volumen crece 10×–100× y privacy es no-negociable, **reconsiderar**. [M]

---

### Hipótesis específicas a testear (en el eval set actual)

| # | Hipótesis | Qué cambiar | Métrica esperada | Apuesta |
|---|---|---|---|---|
| H1 | **Gemini 3.5 Flash cierra el gate (≥90% verde)** con el mismo prompt actual + Tier 1 params, sin tocar nada más | swap modelo `gemini-2.5-flash` → `gemini-3.5-flash-05-2026`, pinear version | balance OK ≥85%, verde ≥80% | **probable** (ExtractBench + nuestro propio finding sobre Pro) |
| H2 | **Gemini 3.5 Flash con structured-output schema** (response_schema con `additionalProperties:false`) elimina warnings espurios | activar `response_mime_type=application/json` + schema explícito (actualizar SDK >= versión post-nov 2025) | warnings espurios → 0 | **probable** si la SDK ya no rompe |
| H3 | **Claude Sonnet 4.6 con tool use + schema strict** mejora balance accuracy vs Gemini Flash | port adapter a Anthropic SDK, structured-outputs beta, mismo prompt traducido | balance OK ≥85%, schema compliance 99%+ | **probable**, costo 2× pero <$1/cartola |
| H4 | **Mistral OCR 3 → markdown → Gemini 3.5 Flash** (two-stage) mejora vs Gemini-only | pipeline nuevo: Mistral extrae markdown estructurado, Flash convierte a JSON canónico | balance OK ≥90%, costo ↓ vs solo Flash | **incierto** (Mistral falló bank-statements standalone — depende de si markdown intermediario salva el caso o lo empeora) |
| H5 | **Claude Opus 4.7 high-res vision** resuelve los 2 PDFs que Pro 2.5 no balanceó | swap a Opus 4.7, mismo prompt, verificar high-res image tokens | 14/14 balance OK | **incierto** (caro, MRCR regression preocupa si los PDFs son largos) |
| H6 | **GPT-5.5 con Responses API + structured output strict** rinde igual o mejor que Gemini 3.5 Flash | adapter nuevo OpenAI, file input PDF directo, structured output strict | balance OK ≥85% | **incierto** (sin evidencia de superioridad para el costo) |

**Recomendación de orden:** H1 → H2 → H3 → H4 (paralelo a H2/H3) → H5/H6 sólo si los anteriores fallan.

---

### Gaps de información (no pude cerrar)

1. **Benchmarks Spanish-PDF específicos**: ninguna fuente publicó accuracy de doc-extraction sobre español en cartolas/facturas latinas. Tendremos que medir nosotros mismos sobre los 14 PDFs reales del eval set. [Gap impact: alto — sin esto, los benchmarks generales son sólo proxies imperfectos.]
2. **Comparación independiente Claude vs Gemini sobre bank statements**: la única comparación cuantitativa encontrada (Vellum, Panth Softech) usa modelos previos (3.7 Sonnet, 2.5 Pro) y números vendor-aligned. **No hay aún un "ExtractBench for bank statements"** público. [Gap impact: medio — ExtractBench cubre financial reports y formularios, pero no cartolas.]
3. **GPT-5.5 latencia y costo real por cartola**: docs OpenAI no publican TTFT explícito; el cost por cartola es proyección desde token count típico. [Gap impact: bajo — order of magnitude está claro.]
4. **Mistral OCR 3 en español específicamente**: claim 99%+ across 90 langs es vendor; no encontré benchmark independiente para español. [Gap impact: medio — solo importa si H4 progresa.]
5. **Anti-patterns documentados específicos de Gemini 3.5 Flash**: el modelo tiene 1 semana al momento del research. Vamos a estar descubriendo gotchas en producción durante el primer mes. [Gap impact: medio.]
6. **MRCR regression de Opus 4.7 con PDFs largos de cartolas**: el benchmark MRCR es needles-in-haystack sintético, no PDF real. Si Opus 4.7 procesa bien tablas largas de transacciones a pesar del MRCR drop está por verificarse empíricamente. [Gap impact: bajo si H1/H2/H3 cierran el gate.]

---

### Bias disclosure

Soy un agente Anthropic. **El ranking arriba pone a Gemini 3.5 Flash primero**, no a Claude, porque:

1. **ExtractBench (benchmark independiente arxiv) muestra a Gemini Flash liderando en validez de schema** sobre Claude 4.5 Opus/Sonnet y GPT-5/5.2. [H]
2. **El finding propio del proyecto** (spike 9.5f) ya mostró que Gemini 2.5 Pro tiene 85.7% balance OK — el modelo encuentra los números, el problema era prompt/warnings. Cambiar a 3.5 Flash es el delta mínimo con upside esperado más alto.
3. **Costo + integración** ya hecha en Gemini API favorece reuso.

Si los benchmarks fueran ambiguos, sería honesto reportar Claude Sonnet 4.6 como #1 dado su schema-compliance líder. No lo son: Gemini Flash 3.5 tiene el mejor caso técnico medible.

### Sources

- [ExtractBench arxiv 2602.12247](https://arxiv.org/abs/2602.12247) — frontier extraction benchmark, feb 2026
- [Anthropic Claude Opus 4.7 launch](https://www.anthropic.com/news/claude-opus-4-7)
- [Anthropic Sonnet 4.6 launch](https://www.anthropic.com/news/claude-sonnet-4-6)
- [Anthropic Haiku 4.5 launch](https://www.anthropic.com/news/claude-haiku-4-5)
- [Claude PDF support docs](https://docs.claude.com/en/docs/build-with-claude/pdf-support)
- [Claude Structured Outputs docs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Claude Opus 4.7 MRCR regression analysis](https://blog.wentuo.ai/en/claude-opus-4-7-long-context-regression-en.html)
- [Claude Opus 4.7 benchmark breakdown — MindStudio](https://www.mindstudio.ai/blog/claude-opus-47-benchmark-breakdown)
- [Vellum Claude Opus 4.7 benchmarks](https://www.vellum.ai/blog/claude-opus-4-7-benchmarks-explained)
- [OpenAI File Inputs API docs](https://developers.openai.com/api/docs/guides/file-inputs)
- [OpenAI PDF input announcement (community)](https://community.openai.com/t/direct-pdf-file-input-now-supported-in-the-api/1146647)
- [OpenAI GPT-5.5 cookbook on document understanding](https://developers.openai.com/cookbook/examples/multimodal/document_and_multimodal_understanding_tips)
- [Gemini 3.5 Flash launch — MarkTechPost](https://www.marktechpost.com/2026/05/20/google-introduces-gemini-3-5-flash-at-i-o-2026-a-faster-and-cheaper-model-for-ai-agents-and-coding/)
- [Gemini 3.5 Flash pricing — apidog](https://apidog.com/blog/gemini-3-5-flash-pricing/)
- [Gemini Zero Data Retention docs](https://ai.google.dev/gemini-api/docs/zdr)
- [Gemini 2.5 Pro regression analysis — Google forum](https://discuss.ai.google.dev/t/analysis-of-performance-regression-in-gemini-2-5-pro/92026)
- [Gemini SDK additionalProperties bug](https://github.com/googleapis/python-genai/issues/1815)
- [Artificial Analysis — Gemini 3.5 Flash providers](https://artificialanalysis.ai/models/gemini-3-5-flash/providers)
- [Mistral OCR 3 launch](https://mistral.ai/news/mistral-ocr-3)
- [Mistral OCR pricing — VentureBeat](https://venturebeat.com/technology/mistral-launches-ocr-3-to-digitize-enterprise-documents-touts-74-win-rate)
- [Docsumo OCR benchmark report (Mistral bank-statement fail)](https://www.docsumo.com/blogs/ocr/docsumo-ocr-benchmark-report)
- [Llama 4 multimodal benchmarks — abhs.in](https://www.abhs.in/blog/meta-llama-4-multimodal-open-source-benchmarks-2026)
- [TokenMix structured output guide 2026](https://tokenmix.ai/blog/structured-output-json-guide)
- [TokenMix best AI for document processing 2026](https://tokenmix.ai/blog/best-ai-for-document-processing)
- [Vellum LLM vs OCR document data extraction](https://www.vellum.ai/blog/document-data-extraction-llms-vs-ocrs)
- [Anthropic API pricing guide — Finout](https://www.finout.io/blog/anthropic-api-pricing)

---

## Eje B — Document AI especializados (2026)

**Autor:** research agent técnico · **Fecha:** 2026-05-20 · **Scope:** servicios IDP/Document AI pre-entrenados o open source para extracción de bank statements, evaluados con la lente Family Office EAG (cartolas chilenas, mix CLP/USD, ~50/mes, output → `CartolaCanonicalV1`).

### TL;DR — Hallazgos críticos al frente

1. **NINGÚN servicio comercial con processor "bank statement" pre-entrenado tiene cobertura documentada de bancos chilenos.** Los dos candidatos obvios — Google Document AI Bank Statement Parser y Azure Document Intelligence `prebuilt-bankStatement` — son **explícitamente solo inglés / US**. Confidence: **high**. Esto destruye la hipótesis "hay un Stripe-de-cartolas que ya hace el task". ([Google processor docs](https://docs.cloud.google.com/document-ai/docs/processors-list), [Azure prebuilt bankStatement docs](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/bank-statement?view=doc-intel-4.0.0))
2. **AWS Textract Queries** (la única forma de hacer extracción guiada bank-statement-style en Textract) es **inglés-only** también. La capa OCR de Textract sí soporta español, pero la Queries feature no — exactamente la pieza que necesitamos. Confidence: **high**. ([AWS Textract FAQs](https://aws.amazon.com/textract/faqs/))
3. **Mindee** es el único IDP enterprise con un Bank Statement OCR API que claim entrenamiento sobre 50+ países, multi-language, ~95% accuracy en campos. Sin confirmación de bancos chilenos puntualmente — pero su benchmark dataset es "evolutivo" y semanal, lo que sugiere mejor chance que Google/Azure/AWS. Confidence: **medium**. ([Mindee Bank Statement OCR](https://www.mindee.com/product/bank-statement-ocr))
4. **Reducto** y **Mistral OCR 3** no son "bank statement parsers" — son parsers de documentos genéricos de alta calidad que devuelven markdown/JSON + tablas y requieren un LLM downstream para mapear a `CartolaCanonicalV1`. Útiles como **pre-procesador** en pipeline híbrido (Eje C), no como reemplazo end-to-end. Mistral además fue **derrotado por Gemini 2.0 Flash en benchmark independiente** sobre documentos financieros (43.4% menos accurate per Reducto). Confidence: **high para Mistral underperform, medium para Reducto en cartolas chilenas**. ([Reducto vs Mistral benchmark](https://reducto.ai/blog/lvm-ocr-accuracy-mistral-gemini), [OCR Arena leaderboard](https://www.ocrarena.ai/compare/mistral-ocr-v3/gemini-3-flash))
5. **Implicancia para la decisión de ingeniería:** no existe el "compralo y andate" para cartolas chilenas. Las dos rutas viables son: (a) **Mindee** API directa (probarlo con los 14 PDFs si su trial alcanza), (b) **Reducto/Marker como pre-procesador + LLM downstream** — mismo problema de LLM que ya tenemos, pero con input más limpio que un PDF raw, lo cual puede destrabar Gemini Pro que ya está en 85% balance OK.

> **Nota lateral relevante (no es IDP):** Chile tiene Open Banking maduro vía Boufin, Floid, API-Banca — extraen statements directo del banco con credenciales del usuario, no PDFs. Es una arquitectura completamente distinta y rompe el contrato actual (cliente sube PDF), pero si en algún momento se relaja, **elimina el problema de raíz**. Lo dejo flag. ([Boufin](https://www.boufin.com/), [Floid](https://www.floid.io/servicios/apis-bancarias-y-conciliaciones))

---

### Metodología

Para cada servicio, evalué en orden:

1. ¿Tiene processor pre-entrenado para bank statements? (no general OCR — el primer corte ya elimina mucho)
2. ¿Soporta español / bancos LATAM o solo en-US?
3. Shape del output vs nuestro `CartolaCanonicalV1`
4. Precio para 50 cartolas/mes × ~10 páginas = 500 páginas/mes
5. Privacy / residency / training opt-out (PII de transacciones reales)
6. Trial gratis para probar los 14 PDFs sin compromiso

Distingo **claim de vendor** vs **evidencia independiente** explícitamente. Cita con URL para todo claim cuantitativo. Confidence marcado por claim: **[H]** high, **[M]** medium, **[L]** low.

---

### Servicios cloud comerciales

#### 1. Google Document AI — Bank Statement Parser

| Dimensión | Valor | Confidence | Fuente |
|---|---|---|---|
| Pre-entrenado para bank statements | Sí, processor dedicado | [H] | [Google processor list](https://docs.cloud.google.com/document-ai/docs/processors-list) |
| Idiomas soportados | **English only** (`en`, `Latn`) | **[H]** | idem |
| Regiones disponibles | `us` y `eu` only | [H] | idem |
| Bancos LATAM / Chile | **No documentado, sin soporte explícito** | [H] | idem |
| Output schema | `account_number`, `account_type`, `bank_name`, `starting_balance`, `ending_balance`, `statement_start_date`, `statement_end_date`, `table_item.transaction_deposit/withdrawal/date/description` | [H] | idem |
| Pricing | **$0.75 por documento clasificado** | [H] | [GCP DocAI pricing](https://cloud.google.com/document-ai/pricing), [Dev Forum confirm](https://discuss.google.dev/t/document-ai-bank-statement-pricing-question/167576) |
| Costo 50 cartolas/mes | ~$37.50/mes | [H] | calc directo |
| Privacy / training | Google **no usa customer data** para entrenar; documentos cifrados con ephemeral key durante batch; Access Transparency soportado | [H] | [DocAI security docs](https://docs.cloud.google.com/document-ai/docs/security) |
| Page limits | Online: 15 págs / batch: 30 págs / imageless: 30 págs | [H] | processor list |
| Self-hosted | No | [H] | — |
| Trial | GCP free tier estándar ($300 credits 90 días) | [H] | gcp standard |

**Output shape vs `CartolaCanonicalV1`:** mapeo razonable — `transactions[]` viene de `table_item`, balances OK, period dates OK. Falta `currency` explícito (asume USD) y `warnings[]` (los inventás vos). Mapping effort: **bajo si funcionara**.

**Veredicto:** **DESCARTAR** sin testear. La barrera idiomática es absoluta — un processor entrenado en English-only sobre cartolas BCI/Santander en español va a fallar en todos los campos string (descripción, bank name, account type) y posiblemente en parseo de fechas DD/MM/YYYY vs MM/DD/YYYY. Probarlo es ~5h de setup + GCP project para confirmar lo que la doc ya dice.

#### 2. AWS Textract — AnalyzeDocument con Queries / bank statement use case

| Dimensión | Valor | Confidence | Fuente |
|---|---|---|---|
| Pre-entrenado para bank statements | **No hay processor dedicado**; Queries feature está "pre-trained on bank statements" pero es solo question-answering | [H] | [Textract Queries blog](https://aws.amazon.com/blogs/machine-learning/specify-and-extract-information-from-documents-using-the-new-queries-feature-in-amazon-textract/) |
| Idiomas — OCR layer | English, Spanish, German, Italian, French, Portuguese | [H] | [Textract FAQs](https://aws.amazon.com/textract/faqs/) |
| Idiomas — **Queries feature** | **English only** | **[H]** | idem |
| Bancos LATAM / Chile | No | [H] | derivado |
| Output shape | Para llegar a `CartolaCanonicalV1` necesitás: AnalyzeDocument (tables+forms) → custom logic Python → opcionalmente Bedrock LLM downstream. Equivale a "construir tu propio extractor sobre OCR limpio" | [H] | [aws-samples/textract-bank-statement-processor](https://github.com/aws-samples/textract-bank-statement-processor) |
| Pricing | AnalyzeDocument Tables+Forms: ~$0.065/page primeros 1M, Queries adicional $0.015/page. Para 500 páginas/mes: ~$40 | [H] | aws standard |
| Privacy | AWS BAA disponible, no training on customer data por default | [H] | aws standard |
| Self-hosted | No (cloud-only) | [H] | — |
| Trial | 1000 páginas free por mes durante 3 meses (free tier) | [H] | aws free tier |

**Veredicto:** **DESCARTAR** sin testear. Para extracción guiada bank-statement-style hay que usar Queries → solo inglés. Alternativa "table extraction + custom Python" no aporta nada sobre lo que ya hacen pdfplumber/Marker localmente (gratis).

#### 3. Azure AI Document Intelligence — Prebuilt `bankStatement`

| Dimensión | Valor | Confidence | Fuente |
|---|---|---|---|
| Pre-entrenado para bank statements | Sí: `prebuilt-bankStatement.us` GA v4.0 (2024-11-30) | [H] | [Azure prebuilt bankStatement](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/bank-statement?view=doc-intel-4.0.0) |
| Idiomas soportados | **`en-us` only** — modelo explícitamente "US" en el nombre | **[H]** | idem (literal: "supports the en-us locale") |
| Bancos LATAM / Chile | **No, modelo es US-specific por diseño** | [H] | idem |
| Output schema | `BankName`, `BankAddress`, `AccountHolderName/Address`, `StatementStart/EndDate`, `Accounts[].AccountNumber`, `Accounts[].AccountType`, `Accounts[].BeginningBalance`, transactions tables, check tables (nuevo en v4 GA) | [H] | [Azure schema GitHub](https://github.com/Azure-Samples/document-intelligence-code-samples/blob/main/schema/2024-11-30-ga/bank-statement.md) |
| Pricing | Prebuilt models: $10 per 1000 pages tier estándar | [H] | azure standard |
| Costo 500 páginas/mes | ~$5/mes | [H] | calc |
| Privacy | Azure compliance suite (SOC2, GDPR, HIPAA opt-in), no training on customer data | [H] | azure standard |
| Trial | Free tier F0: primeras 500 páginas/mes gratis, primeras 2 páginas por doc | [H] | azure standard |

**Veredicto:** **DESCARTAR** sin testear. El nombre del processor literalmente termina en `.us` y la doc dice `en-us` only. Aunque la capa OCR (Layout/Read) sí soporta español, el field extraction del bankStatement está entrenado sobre formatos US (Chase, BoA, Wells Fargo) que comparten muy poca estructura con BCI/Santander Chile. Microsoft no anunció (May 2026) plans para una variante LATAM.

#### 4. Reducto (reducto.ai)

| Dimensión | Valor | Confidence | Fuente |
|---|---|---|---|
| Pre-entrenado para bank statements | **No es processor dedicado** — es parser de documentos genérico con énfasis en tables/financial docs | [H] | [Reducto finance](https://reducto.ai/industries/finance) |
| Idiomas | 100+ languages, "mixed-language reports" | [M] (claim del vendor, no benchmark independiente para español) | idem |
| Bancos LATAM / Chile | No documentado | [H] | idem |
| Output shape | Markdown + tables + structured chunks. **Requiere LLM downstream** para mapear a `CartolaCanonicalV1` | [H] | [Reducto API docs](https://llms.reducto.ai/) |
| Accuracy reportada | RD-TableBench (creado por Reducto): table accuracy >20pp sobre baselines text-only. **Self-published**. Gemini 3 Flash ranking #1 en OCR Arena, Reducto no figura en top-15 de ese leaderboard | [M] para tables, [L] para "fin del task" | [RD-TableBench](https://reducto.ai/blog/rd-tablebench), [OCR Arena](https://www.ocrarena.ai/compare/mistral-ocr-v3/gemini-3-flash) |
| Pricing | $0.015/credit; primeros 15K credits free. Credit ≠ page exactamente (depende de operación). Estimado 500 páginas ≈ $7.5-15/mes según ops | [M] | [Reducto pricing](https://reducto.ai/pricing) |
| Privacy | "Zero data sharing" claim, Trust Center existe, no training on uploads | [M] (claims sin BAA público) | idem |
| Self-hosted | No documentado en pricing público (enterprise tier custom) | [M] | idem |
| Trial | 15K credits free en Standard plan → suficiente para 14 PDFs × 10 páginas × 3 corridas (~420 ops) con margen | [H] | idem |

**Veredicto:** **CANDIDATO TOP 3 para test, en modo "pre-procesador de pipeline híbrido"**. No reemplaza el LLM downstream pero limpia el input. La hipótesis: Gemini 2.5 Pro ya está en 85% balance OK con PDF raw; con markdown estructurado de Reducto + nuestro prompt actual, podría destrabar.

#### 5. Unstructured.io (open source + cloud)

| Dimensión | Valor | Confidence | Fuente |
|---|---|---|---|
| Pre-entrenado para bank statements | No, parser genérico open source | [H] | [Unstructured GitHub](https://github.com/Unstructured-IO/unstructured) |
| Idiomas | Heredados de Tesseract/PaddleOCR backend (español OK) | [H] | idem |
| Output shape | Elements (Title, NarrativeText, Table, ListItem) + HTML para tablas. **Requiere LLM downstream** | [H] | [Unstructured table extraction docs](https://docs.unstructured.io/examplecode/codesamples/apioss/table-extraction-from-pdf) |
| Pricing | Open source gratis self-hosted; cloud tier desde $1.25/1000 páginas hi-res | [H] | unstructured standard |
| Privacy | Self-hosted = total control. Cloud tier es US/EU | [H] | idem |
| Trial | Free open source pip install | [H] | idem |

**Veredicto:** **PIPELINE alternative a Reducto**. Si querés evitar pagar Reducto y aceptás más setup, Unstructured hi-res strategy es comparable. Misma arquitectura híbrida.

#### 6. Mistral OCR / Document AI

| Dimensión | Valor | Confidence | Fuente |
|---|---|---|---|
| Pre-entrenado para bank statements | No processor dedicado; menciona casos AML/KYC genéricos | [H] | [Mistral OCR 3 announcement](https://mistral.ai/news/mistral-ocr-3) |
| Idiomas | 99%+ accuracy en "11+ languages" — español listado | [H] | [VentureBeat coverage](https://venturebeat.com/technology/mistral-launches-ocr-3-to-digitize-enterprise-documents-touts-74-win-rate) |
| Output shape | Markdown enriquecido + HTML para tablas; JSON structured via Document AI Playground. **Requiere LLM downstream** | [H] | mistral docs |
| Accuracy reportada | Mistral self-published: 94.9% vs Gemini 2.0 Flash 88.49%. **Reducto's independent test: Mistral 43.4% LESS accurate que Gemini 2.0 Flash en brokerage research report**. OCR Arena: Gemini 3 Flash #1 (ELO 1717), Mistral OCR v3 #13 (ELO 1483) | **[H]** evidence de underperformance vs Gemini | [Reducto independent test](https://reducto.ai/blog/lvm-ocr-accuracy-mistral-gemini), [OCR Arena leaderboard](https://www.ocrarena.ai/compare/mistral-ocr-v3/gemini-3-flash) |
| Pricing | **$2 per 1000 pages**, batch API 50% off ($1 per 1000) | [H] | mistral news |
| Costo 500 páginas/mes | ~$1/mes (batch) o $0.50/mes — barato | [H] | calc |
| Privacy | Self-hosting **disponible** para enterprise; cloud zone EU disponible | [H] | mistral news |
| Trial | Document AI Playground gratis | [M] | idem |

**Veredicto:** **DESCARTAR como standalone**. La evidencia independiente lo pone debajo de Gemini Flash en docs financieros — y Gemini Flash ya falló nuestro gate (esto refuerza también el finding de Eje A sección Mistral OCR 3). Self-hosted es atractivo para privacy pero no compensa el accuracy gap. Coincide con el finding del Docsumo benchmark (Eje A): 0/120 preferencias en bank statements.

#### 7. Rossum (rossum.ai)

| Dimensión | Valor | Confidence | Fuente |
|---|---|---|---|
| Pre-entrenado para bank statements | Sí, IDP enterprise con bank statement entre casos publicados; Aurora Engine template-free | [M] | [Rossum IDP](https://rossum.ai/intelligent-document-processing/) |
| Idiomas | "Language-agnostic" claim del vendor | [M] (sin benchmark independiente para español LATAM) | [Rossum site](https://rossum.ai/) |
| Bancos LATAM / Chile | No documentado | [H] | — |
| Pricing | **Enterprise sales, no listed** — históricamente $5K-50K+/año mínimo | [M] | [Capterra Rossum alternatives](https://research.aimultiple.com/rossum-ai-competitors/) |
| Privacy | SOC2, GDPR; ahora propiedad de Coupa (M&A May 2026) | [H] | [Coupa acquisition](https://www.fintechfutures.com/m-a/coupa-acquires-rossum) |
| Trial | "Sign up for free trial" disponible | [H] | rossum site |

**Veredicto:** **DESCARTAR**. Enterprise IDP overkill para 50 docs/mes single-operator family office. El minimum committed spend de Rossum (estimado $5K+/año) destruye el ROI. La adquisición reciente por Coupa también introduce incertidumbre de roadmap.

#### 8. Nanonets

| Dimensión | Valor | Confidence | Fuente |
|---|---|---|---|
| Pre-entrenado para bank statements | Sí, [Bank Statement Model dedicado](https://nanonets.com/document-ocr/bank-statements) + custom training | [H] | nanonets site |
| Idiomas | 40+ idiomas incluyendo español | [M] (no specific Chile benchmark) | [Nanonets pricing](https://nanonets.com/pricing) |
| Bancos LATAM / Chile | No documentado específicamente, pero acepta custom training | [M] | idem |
| Pricing | **$0.30/page** extracción + $0.05/workflow step; Pro $999/mes para 10K páginas. **$200 credits free** al empezar | [H] | idem |
| Costo 500 páginas/mes | ~$150/mes en pay-as-you-go | [H] | calc |
| Privacy | SOC2, GDPR | [H] | idem |
| Self-hosted | On-prem enterprise option | [M] | idem |
| Trial | $200 free credits = ~667 páginas — alcanza cómodo para test | [H] | idem |
| Gotchas | Reviews mencionan "inconsistencia entre runs" y "difícil troubleshoot custom training" | [M] | g2 reviews |

**Veredicto:** **CANDIDATO TOP 3 para test**. Es uno de los pocos con (a) bank statement model dedicado, (b) español documentado, (c) trial free generoso, (d) custom training si el pre-trained no alcanza. El pricing es 4x Mindee a volumen alto pero irrelevante para 50/mes.

#### 9. Docparser / Parseur / Klippa (lightweight SaaS)

| Servicio | Bank statement | Español | Precio | Trial | Veredicto |
|---|---|---|---|---|---|
| **Parseur** | Sí, AI-powered OCR para bank statements; 60+ idiomas inc. español | Sí | $49/mes base | Free tier | Possible "good enough" para small volume; sin track record claro de Chile |
| **Docparser** | Sí, template-based historically; AI extraction añadido | Limitado (template-based necesita ajuste) | $32.50/mes (100 docs), $61.50/mes (250) | Trial | Template-based es frágil — 3 bancos × 2 layouts = 6 templates que mantener. **DESCARTAR** |
| **Klippa** | Sí, claim bank statement extraction; pricing no público (~€0.02/page reportado) | Sí, internacional | Contact sales | Demo | EU-based, GDPR strong. Possible candidato tier-2 |

**Veredicto general:** Parseur y Klippa entran como "tier 2 si Mindee/Nanonets fallan". Docparser descartado por modelo template-based frágil.

#### 10. Sensible Instruct / extract.ai

**Sensible Instruct:** Bank statement parsing publicado como caso de uso. Usa GPT-4 (no Gemini) bajo el capó como LLM driver + deterministic guardrails. ([Sensible bank statement page](https://www.sensible.so/extract/bank-statements)). 150+ pre-built configs incluyen bank statements. Pricing no listado público. Veredicto: candidato **medium**, similar a Mindee en aproximación pero menos claim de multi-país.

**extract.ai:** Sin información encontrada en search; no parece player relevante en May 2026.

#### 11. Mindee — Bank Statement OCR API

| Dimensión | Valor | Confidence | Fuente |
|---|---|---|---|
| Pre-entrenado para bank statements | Sí, Bank Statement OCR API dedicado, audit-grade | [H] | [Mindee Bank Statement OCR](https://www.mindee.com/product/bank-statement-ocr) |
| Idiomas | Multi-language, adapta automáticamente | [M] | idem |
| Bancos LATAM / Chile | "50+ countries in training dataset, evolving weekly" — sin lista explícita, no menciona Chile específicamente | [M] (claim del vendor) | idem |
| Accuracy reportada | ">95% en la mayoría de campos" sobre dataset evolutivo semanal | [M] (vendor self-report, no benchmark independiente vs Chile) | idem |
| Output shape | "Audit-grade precision, mapea layouts complejos a clean machine-readable" — JSON con date/amount/description/balance | [H] | idem |
| Pricing | Starter €44/mes (500 páginas), Business €584/mes (10K páginas) | [H] | [Mindee pricing](https://www.mindee.com/pricing) |
| Costo 500 páginas/mes | **€44/mes** exacto en Starter | [H] | calc |
| Privacy | GDPR-compliant, SOC2 Type II, DPA disponible, Europe processing zone forzable; **retention opt-out** (delete inmediato post-inference) | [H] | [Mindee data policies](https://docs.mindee.com/models/data-processing-policies) |
| Self-hosted | No documentado | [H] | — |
| Trial | Sandbox + free credits standard | [M] | mindee site |

**Veredicto:** **CANDIDATO TOP 1 para test**. Es el único IDP cloud con **bank statement processor dedicado + claim multi-país + español + pricing razonable + GDPR fuerte**. El test definitivo es subir 14 PDFs y medir. Si funciona, reemplaza el LLM por completo a costo predecible.

---

### Open source / self-hostable

#### 12. LayoutLMv3 / DocLayoutLM

Modelos open source de Microsoft Research. **XFUND benchmark** (multilingual forms incluye español) prueba que el modelo soporta español post-fine-tune. **Pero**: no hay fine-tune pre-existente para bank statements chilenos, así que necesitarías:

- Etiquetar ~100-500 cartolas manualmente
- Setup training infra (GPU)
- Mantener el modelo

Para 50 docs/mes single-operator es **overkill brutal**. **DESCARTAR** salvo que el proyecto crezca 10x. ([LayoutLMv3 GitHub](https://github.com/purnasankar300/layoutlmv3))

#### 13. Donut / Nougat (OCR-free)

Donut (NAVER/Clova) es fine-tuneable para extracción end-to-end sin OCR step. **Para bank statements requiere fine-tune custom** — no hay checkpoint pre-trained para cartolas chilenas. Nougat es para papers científicos, no aplica. ([Donut GitHub](https://github.com/clovaai/donut)). Mismo veredicto que LayoutLM: overkill para volumen.

Hay paper Dec 2024 **TabSniper** que ataca el problema específico de table detection en bank statements ([arxiv 2412.12827](https://arxiv.org/pdf/2412.12827)) — interesante como prior art pero requiere implementación.

#### 14. Surya OCR + table detection

Open source, 90+ idiomas inc. español, table recognition incorporado. GPL-3.0 license (cuidado en uso comercial). Excelente como **OCR layer para pipeline DIY** — comparable a Unstructured hi-res strategy pero con buena reputación para tablas multilingual. ([Surya GitHub](https://github.com/datalab-to/surya)).

Veredicto: **opción secundaria si decidís pipeline híbrido self-hosted**. No reemplaza el LLM.

#### 15. Marker / pdfplumber / PyMuPDF

Text-layer extractors livianos. **No son IDP**. Funcionan bien cuando el PDF tiene text layer (no scan). Para BCI/Santander Chile la mayoría de cartolas son PDFs nativos con text layer → pdfplumber/Marker extraen texto + tablas perfectamente, 3-5 seg/doc, 88-95% accuracy en extracción de tabla según [Practical Web Tools 2026 guide](https://practicalwebtools.com/blog/ai-pdf-processing-financial-documents-guide-2026).

Veredicto: **complementario, no candidato standalone**. Vale la pena medir cuánto se gana usando Marker → markdown → Gemini Pro vs PDF raw → Gemini Pro. Si el 15% que faltaba para gate ≥90% es ruido de OCR/layout, esto lo destraba.

---

### Tabla resumen comparativa

| Servicio | Bank-stmt pre-entrenado | Soporte español | $/mes (50 cartolas) | Privacy/residency | Open source / self-host | Setup effort | Recomendable para Chile |
|---|---|---|---|---|---|---|---|
| Google DocAI Bank Statement | Sí | **NO (en-only)** | ~$37/mes | GCP standard, no training | No | Bajo | **No — idioma** |
| AWS Textract + Queries | Solo Queries pre-trained | OCR sí; **Queries NO (en-only)** | ~$40/mes | AWS BAA | No | Medio | **No — feature crítica solo EN** |
| Azure DI prebuilt-bankStatement | Sí (.us) | **NO (en-us only)** | ~$5/mes | Azure compliance | No | Bajo | **No — US only** |
| Reducto | No (parser genérico) | Sí (claim, no benchmark CL) | ~$10/mes + LLM | Trust Center | No (enterprise) | Medio | **Maybe — pre-procesador** |
| Unstructured.io | No (OCR+layout) | Sí (Tesseract backend) | $0 self-host + LLM | Self-hosted = total | **Sí** | Medio-alto | **Maybe — pipeline DIY** |
| Mistral OCR 3 | No | Sí (claim) | <$1/mes + LLM | Self-hosted enterprise | Sí (enterprise) | Bajo | **No — underperforma Gemini** |
| Rossum | Sí, IDP enterprise | "Language-agnostic" | $5K+/año min | SOC2/GDPR | No | Alto (sales) | **No — overkill volumen** |
| Nanonets | Sí, Bank Statement Model | Sí (40+ idiomas) | ~$150/mes | SOC2, on-prem option | Sí (enterprise) | Bajo | **Sí — top 3** |
| Parseur | Sí | Sí (60+ idiomas) | $49/mes base | Standard SaaS | No | Bajo | **Tier 2** |
| Docparser | Template-based | Limitado | $32-133/mes | Standard SaaS | No | Medio (templates) | **No — templates frágiles** |
| Klippa | Sí | Sí (EU player) | ~€10/mes a volumen | GDPR strong | No (sales) | Medio | **Tier 2** |
| Sensible Instruct | Sí (config-driven) | Sí (GPT-4 driven) | Custom | SOC2 | No | Medio | **Tier 2** |
| **Mindee Bank Statement** | **Sí, dedicado** | **Sí, 50+ países** | **€44/mes (500 págs)** | **GDPR, SOC2, EU zone, delete-on-read** | No | Bajo | **Sí — top 1** |
| LayoutLMv3 / Donut | Requiere fine-tune | Post-training | Infra GPU | Self-hosted | Sí | **Alto** (etiquetar+train) | **No — overkill** |
| Surya OCR | Solo OCR+tables | Sí | Open source | Self-hosted | Sí (GPL-3) | Medio | **Pipeline DIY** |
| Marker / pdfplumber | No, text extraction | Sí (text layer) | Gratis local | Local | Sí | Bajo | **Complementario** |

---

### Top 3 candidatos a evaluar empíricamente con los 14 PDFs

#### #1 — Mindee Bank Statement OCR API

- **Por qué entra al top 3:** único IDP cloud con bank statement processor dedicado **+ multi-país documentado + español + GDPR fuerte + pricing flat predecible**. Es la respuesta más directa a la pregunta "¿hay un servicio pre-entrenado que ya hace esto?".
- **Qué probaría primero:** crear cuenta, subir 14 PDFs vía API/Studio, comparar output JSON contra `CartolaCanonicalV1` esperado. Si los `transactions[]` salen razonablemente y los balances cuadran, ganamos el task sin LLM.
- **Tiempo de test:** 2-3 horas (signup + integración mínima + correr 14 PDFs + análisis manual)
- **Costo de test:** €0 (free tier / sandbox), o €44 si requieren plan pago. Sub-$50 total.
- **Riesgo:** que los bancos chilenos no estén en su training dataset → balance/amounts OK pero descripciones rotas o transactions duplicadas. La métrica de gate ≥90% verde sigue siendo la verdad.

#### #2 — Nanonets Bank Statement Model

- **Por qué entra al top 3:** segundo IDP con processor dedicado + español + **opción de custom training** si el pre-trained no llega. El $200 free credits permite testear sin compromiso.
- **Qué probaría primero:** mismo flow que Mindee — 14 PDFs vía Studio web, comparar JSON output. Si el pre-trained falla pero los outputs parecen "casi" correctos, intentar custom training con ~10 PDFs etiquetados.
- **Tiempo de test:** 2-4 horas pre-trained, 1 día completo si custom training
- **Costo de test:** $0 con free credits ($200 alcanzan ~667 páginas)
- **Riesgo:** reviews mencionan inconsistencia entre runs y custom training "difícil troubleshoot" — fragilidad operacional alta para single-operator.

#### #3 — Pipeline híbrido: Marker (free local) o Reducto → Gemini 2.5 Pro

- **Por qué entra al top 3:** este es el **pivot ortogonal**. No es "otro processor", es la hipótesis de que el problema del 15% que nos falta para gate ≥90% es **input quality** (PDF raw es ruidoso para el LLM), no model capability. Gemini 2.5 Pro ya está en 85.7% balance OK. Si Marker/Reducto convierten el PDF a markdown bien estructurado con tablas explícitas, el mismo Pro puede llegar a verde.
- **Qué probaría primero:**
  1. Marker open source (gratis, local): correr los 14 PDFs → markdown
  2. Re-correr Gemini 2.5 Pro con el markdown como input en lugar del PDF binario
  3. Si mejora, comparar con Reducto cloud (markdown más limpio pero $-cost)
- **Tiempo de test:** Marker pipeline: 3-4 horas. Reducto add-on: +2 horas.
- **Costo de test:** Marker $0. Reducto: dentro de los 15K credits free (~$0).
- **Riesgo:** la conversión a markdown puede **perder información de layout** (columnas, alineación) que el LLM vision usa implícitamente. La hipótesis puede fallar.

---

### Descartados sin testear (y por qué)

| Servicio | Razón |
|---|---|
| Google DocAI Bank Statement Parser | English-only documentado; rendimiento esperado bajo sobre español |
| AWS Textract Queries | Queries (la única feature útil) es English-only |
| Azure prebuilt-bankStatement | Modelo nombrado `.us` por diseño, `en-us` only |
| Mistral OCR 3 (standalone) | Underperforma Gemini 2.0 Flash en benchmark independiente sobre docs financieros (Reducto + Docsumo); Gemini Flash ya falló nuestro gate ⇒ Mistral peor |
| Rossum | Enterprise IDP, minimum spend ~$5K+/año destruye ROI para 50 docs/mes |
| Docparser | Modelo template-based frágil para 3 bancos × N layouts |
| LayoutLMv3 / Donut / TabSniper | Requieren etiquetado + training; overkill para volumen single-operator |

---

### Gaps de info que no pude cerrar

1. **Mindee y Nanonets: cobertura de bancos chilenos específicos.** Ambos vendor pages dicen "multi-país" pero ninguno lista Chile/BCI/Santander Chile/Banco de Chile explícitamente. La única forma de cerrar este gap es **subir 14 PDFs y medir**. Recomiendo no extender más research — saltar a test empírico de Mindee directamente.
2. **Reducto vs Mistral en español específicamente.** Los benchmarks (OCR Arena, RD-TableBench) son mayormente en inglés. No encontré evaluación independiente cross-language para docs financieros LATAM.
3. **Sensible Instruct pricing real.** "Contact sales" sin tier público; sin signal claro si es viable para 50 docs/mes.
4. **Klippa €0.02/page** es reporte de tercero ([Klippa data extraction blog](https://www.klippa.com/en/blog/information/data-extraction-software/)), no pricing oficial publicado por Klippa.
5. **Open Banking chileno (Boufin/Floid/API-Banca)** — flagged como nota lateral pero no investigué a fondo. Si Ary considera relajar el contrato "cliente sube PDF" hacia "cliente da credenciales bank de read-only", este eje merece research propio y elimina el problema de extracción de raíz.

---

### Recomendación de siguiente paso (Eje B)

Antes de cualquier decisión arquitectónica, **pagar 3 horas de un test empírico de Mindee Bank Statement OCR con los 14 PDFs reales**. Es la opción con mejor combinación de:

- Processor dedicado al task exacto (no general OCR)
- Soporte multi-país claim creíble (50+ países, dataset evolutivo)
- Pricing predecible y bajo (€44/mes)
- Privacy fuerte (GDPR, EU zone forzable, retention opt-out)
- Trial accesible

Si Mindee pasa el gate ≥90% verde, **el problema desaparece** y reemplazamos el LLM por una API cara $0.10/doc por accuracy predecible. Si falla, tenemos data concreta para decidir entre Nanonets (#2) o pipeline híbrido (#3).

Si los 3 candidatos fallan después del test empírico, la conclusión de Eje B sería: **no existe (May 2026) un servicio Document AI especializado que resuelva cartolas chilenas off-the-shelf** ⇒ el camino correcto pasa por Eje A (mejor LLM) o Eje C (arquitectura híbrida con verificación), no por seguir buscando IDP vendors.

### Sources Eje B

- [Google Cloud Document AI processor list](https://docs.cloud.google.com/document-ai/docs/processors-list)
- [Google Cloud Document AI security docs](https://docs.cloud.google.com/document-ai/docs/security)
- [Google Cloud Document AI pricing](https://cloud.google.com/document-ai/pricing)
- [Google Dev Forum — DocAI bank statement pricing thread](https://discuss.google.dev/t/document-ai-bank-statement-pricing-question/167576)
- [Azure prebuilt bankStatement docs (v4.0 GA)](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/bank-statement?view=doc-intel-4.0.0)
- [Azure bank-statement schema GitHub](https://github.com/Azure-Samples/document-intelligence-code-samples/blob/main/schema/2024-11-30-ga/bank-statement.md)
- [AWS Textract FAQs](https://aws.amazon.com/textract/faqs/)
- [AWS Textract Queries blog](https://aws.amazon.com/blogs/machine-learning/specify-and-extract-information-from-documents-using-the-new-queries-feature-in-amazon-textract/)
- [aws-samples textract-bank-statement-processor](https://github.com/aws-samples/textract-bank-statement-processor)
- [Reducto pricing](https://reducto.ai/pricing)
- [Reducto finance industries page](https://reducto.ai/industries/finance)
- [Reducto RD-TableBench announcement](https://reducto.ai/blog/rd-tablebench)
- [Reducto independent Mistral vs Gemini benchmark](https://reducto.ai/blog/lvm-ocr-accuracy-mistral-gemini)
- [Reducto vs Google DocAI accuracy](https://llms.reducto.ai/reducto-vs-google-document-ai)
- [OCR Arena Mistral OCR v3 vs Gemini 3 Flash](https://www.ocrarena.ai/compare/mistral-ocr-v3/gemini-3-flash)
- [Unstructured.io GitHub](https://github.com/Unstructured-IO/unstructured)
- [Unstructured table extraction docs](https://docs.unstructured.io/examplecode/codesamples/apioss/table-extraction-from-pdf)
- [Mistral OCR 3 announcement](https://mistral.ai/news/mistral-ocr-3)
- [VentureBeat Mistral OCR 3 coverage](https://venturebeat.com/technology/mistral-launches-ocr-3-to-digitize-enterprise-documents-touts-74-win-rate)
- [Rossum IDP page](https://rossum.ai/intelligent-document-processing/)
- [Coupa acquires Rossum (Fintech Futures)](https://www.fintechfutures.com/m-a/coupa-acquires-rossum)
- [Rossum alternatives (Capterra/AIMultiple)](https://research.aimultiple.com/rossum-ai-competitors/)
- [Nanonets Bank Statement docs](https://nanonets.com/document-ocr/bank-statements)
- [Nanonets pricing](https://nanonets.com/pricing)
- [Parseur Bank Statements OCR](https://parseur.com/extract-data/bank-statements)
- [Klippa best bank statement extraction software](https://www.klippa.com/en/blog/information/bank-statement-extraction-software/)
- [Sensible bank statement extraction](https://www.sensible.so/extract/bank-statements)
- [Mindee Bank Statement OCR API](https://www.mindee.com/product/bank-statement-ocr)
- [Mindee pricing](https://www.mindee.com/pricing)
- [Mindee data processing policies](https://docs.mindee.com/models/data-processing-policies)
- [LayoutLMv3 GitHub](https://github.com/purnasankar300/layoutlmv3)
- [Donut (clovaai) GitHub](https://github.com/clovaai/donut)
- [TabSniper paper (arxiv 2412.12827)](https://arxiv.org/pdf/2412.12827)
- [Surya OCR GitHub](https://github.com/datalab-to/surya)
- [Practical Web Tools PDF processing 2026 guide](https://practicalwebtools.com/blog/ai-pdf-processing-financial-documents-guide-2026)
- [Boufin Chile Open Data API](https://www.boufin.com/)
- [Floid Chile banking APIs](https://www.floid.io/servicios/apis-bancarias-y-conciliaciones)

---

## Eje C — Arquitecturas y patrones de validación (2026)

**Autor:** research agent técnico · **Fecha:** 2026-05-20 · **Scope:** ortogonal a los Ejes A (qué LLM) y B (qué Document AI). Aquí la pregunta es **qué arquitectura envuelve al modelo** — pre-procesamiento determinista, multi-pass, validación constraint-based, frameworks de structured-output, schemas standard de bank statement, y la opción de **bypass arquitectónico** (Open Banking Chile). Eje C no propone "otro modelo": propone **otra forma de armar el pipeline** que puede destrabar el gate ≥90% que A y B no garantizaron.

### TL;DR — Hallazgos accionables al frente

1. **El paper independiente más relevante 2025-2026 (arxiv 2509.04469, IEEE Big Data 2025) concluye lo contrario de la hipótesis "C.1"**: en GPT-5 y Gemini 2.5 sobre invoices, **vision directa supera a markdown intermediario**. Replicado por Reducto y Parsli. **Antes de invertir en Marker/Docling como pre-procesador, asumir que el upside está acotado y testear sobre los 14 PDFs.** [H]
2. **Sin embargo**, el spike 9.5f del proyecto ya mostró que Gemini Pro tiene 85.7% balance OK — los números están. **El delta que falta NO es "el modelo no ve la tabla", es "el modelo agrega warnings espurios o se equivoca en signo/period"**. Eso lo cierra **validación constraint-based determinista post-extracción**, no un OCR pre-procesador. [H, derivado del propio finding]
3. **Patrón ganador documentado por Plaid, Daloopa, Unstract y multiple papers**: hybrid system = **LLM extrae + capa determinista verifica (reconciliación de balance + sum check + duplicates + período)**. Plaid reduce alucinaciones de 65.2% a 1.6% con regex + LLM-as-judge. **Esto es lo que falta en el pipeline actual.** [H]
4. **Two-pass mismo modelo (self-consistency / N=3 majority vote)** ya está implícito en las "3 corridas" del eval set actual. **Si el eval interno está mostrando inconsistencia entre runs**, una sola corrida con T=0.0 + structured output schema + constraint validator **probablemente da más mejora que N pases con voting**. [M]
5. **Instructor (Pydantic + retry) es el framework standard 2026** para esto, con 11K stars y 3M downloads/mes. Wraps Gemini/Anthropic/OpenAI con la misma API. **Plug-and-play para el adaptador `gemini_client.py` actual.** [H]
6. **Open Banking Chile YA está operativo** (Boufin cubre BCI + Santander + Banco de Chile + Falabella explícitamente). **Ley 21.521 SFA full entry en julio 2026** (CMF propuso extender a julio 2027 vía consulta). **Boufin tiene los 3 bancos del Family Office cubiertos.** Esto es el bypass arquitectónico real, no una hipótesis lejana. [H para Boufin coverage, H para Ley 21.521 timeline]
7. **ISO 20022 CAMT.053 es el schema standard mundial para bank statements** — sirve como modelo canónico que ya resuelve multi-currency (Entry.Amount con Ccy attribute), opening/closing balances (Balance type CODE), period (FrToDt). **Mapear `CartolaCanonicalV1` a un subset de CAMT.053 reduciría reinventar la rueda.** [H]
8. **No encontré (mayo 2026) ningún paper o repo público que ataque específicamente cuotas X/N + fecha operación anterior al período** del statement como patrón regional Latam. Es un gap real del estado del arte: **el manejo de cuotas latinoamericanas en bank statements no es un problema "resuelto" por nadie con benchmark público.** [H — ausencia de evidencia es evidencia]
9. **Repo open source potente que ya combina todo**: `sebastienrousseau/bankstatementparser` parsea 7 formatos (CAMT/PAIN/CSV/OFX/QFX/MT940/PDF), tiene **Golden Rule verification (opening + credits − debits == closing)**, multi-currency con grupos independientes, LLM fallback opt-in, redacción PII automática. **Estudiarlo como blueprint antes de escribir nuestra capa de validación.** [H]
10. **Recomendación de orden de testeo (cheap-first)**: (a) agregar **balance + sum + period constraint validators deterministas** post-extracción Gemini Pro → suprime warnings espurios sin tocar el modelo (1 día). (b) **Instructor + Pydantic schema + retry on validation fail** → 2-3 días, plug-in a `gemini_client.py`. (c) **Marker → Gemini Pro** como pre-procesador → 3-4 días, baja-confianza alta-upside. (d) si nada cierra, **POC Boufin para 1 banco** → 1 semana, decisión arquitectónica de fondo.

---

### C.1 — Pipeline híbrido: text-layer extractor → LLM estructurador

**La hipótesis:** PDFs bancarios chilenos son digitales con text layer nativo. Extraer markdown limpio con librería determinista y pasarlo (en vez del PDF binario) al LLM reduce el ruido visual y libera tokens para el structuring.

**El contra-hallazgo 2025:** [Multi-Modal Vision vs. Text-Based Parsing: Benchmarking LLM Strategies for Invoice Processing](https://arxiv.org/abs/2509.04469) (IEEE Big Data 2025) testeó 8 modelos (GPT-5, Gemini 2.5, Gemma 3) sobre 3 datasets de invoices con dos estrategias: imagen directa vs convertir a markdown primero. **Conclusión:** "native image processing generally outperforms structured approaches" — el LLM pierde info de layout cuando se aplana a markdown. [Confidence: H — paper aceptado peer-reviewed]. [Reducto blog](https://reducto.ai/blog/lvm-ocr-accuracy-mistral-gemini) llega a la misma conclusión empírica en docs financieros. [Parsli](https://parsli.co/blog/llm-ocr-vs-traditional-ocr) lo confirma como "real production answer is often hybrid: OCR for text + LLM for reasoning — but skip the markdown if the LLM can see".

**Implicancia para el proyecto:** la apuesta "Marker → markdown → Gemini Pro" tiene **upside acotado y downside real** (perder columnas/alineación que el vision encoder usa implícitamente). NO es una mejora gratis. **Tiene sentido testearla SOLO si combinás con vision** (mandar markdown + imagen al LLM), no como reemplazo.

#### Comparativa de libs (datos consolidados — pdfmux benchmark 2026, themenonlab 2026, jimmysong.io)

| Lib | License | Pipeline | Score pdfmux 2026 (200 PDFs) | Speed/page | Tablas | OCR scans | Español | Setup | Notas para cartolas CL |
|---|---|---|---|---|---|---|---|---|---|
| **Marker** (datalab-to/marker, ex VikParuchuri) | GPL-3.0 / commercial | Surya OCR + layout + LLM optional | **0.861** (#3) | 1–10 s/page (ML pipeline) | Buenas, preserva multi-tier headers con `<br>` | Sí (Surya backend) | Multi-lang declarado, sin benchmark español-CL específico | GPU recomendada para velocidad | Buen output, lento, license a revisar para uso comercial. **Tablas mejor preservadas que Docling** según codecut.ai |
| **Docling** (IBM DS4SD, opensource oct 2024) | MIT | Layout model + TableFormer | **0.877** (#2) | rápido vs Marker | "Aplana multi-tier headers" según codecut.ai | Sí | English primary, Granite-Docling experimental ar/zh/ja — **español no listado** | Bajo (pip install) | IBM-backed, MIT, **pero soporte español débil documentado** |
| **pdfmux** (cloud + lib, 2026) | Proprietary (lib uso) | Multi-pass propio | **0.905** (#1) | rápido | Mejor en cada métrica del benchmark | Sí | Multi-lang | API call | Vendor propio del benchmark — sesgo a considerar. Pero #1 reproducible. |
| **pdfplumber** | MIT | text extraction + table heuristics | n/d formal | <0.05 s/page | Aceptables en tablas bien-bordeadas | No (text-only) | Sí (text layer nativo) | Trivial | Standalone perfecto para PDFs nativos digitales (mayoría cartolas CL). **Fastest path.** |
| **PyMuPDF / PyMuPDF4LLM** | AGPL (commercial license requerida) | MuPDF C engine + markdown wrapper | n/d formal | 0.01–0.05 s/page | OK, no SOTA | OCR opt-in automático | Sí | Trivial pip | **License gotcha:** AGPL → si distribuís el producto necesitás license comercial Artifex. Para uso interno (Family Office EAG no distribuye) OK. |
| **Surya** (datalab-to/surya) | GPL-3 | OCR + layout + table detect | n/d formal | medio | Buenas | Sí (OCR ML) | 90+ idiomas inc español | GPU recomendada | Engine de Marker. GPL-3 same license caveat. |
| **MinerU** | Apache-2.0 | propio | 0.831 | medio | Aceptable | Sí | Multi-lang | medio | Alternativa chino popular, menos tracción occidental |

Fuentes: [pdfmux benchmark 2026 (200 PDFs, re-corrido abr 2026)](https://pdfmux.com/blog/pdfmux-vs-pymupdf-vs-marker-vs-docling/), [themenonlab open-source 2026 review](https://themenonlab.blog/blog/best-open-source-pdf-to-markdown-tools-2026), [codecut Docling vs Marker vs LlamaParse](https://codecut.ai/docling-vs-marker-vs-llamaparse/), [PyMuPDF4LLM docs](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/).

#### Recomendación C.1

**No** invertir en pipeline híbrido text-layer → markdown → LLM como primera apuesta. La evidencia 2025-2026 indica que **es ligero/neutro a negativo en accuracy vs vision directa** para docs financieros, y el problema del proyecto (warnings espurios + signo) no se resuelve cambiando el input format del LLM.

**Sí** considerar pdfplumber/PyMuPDF como **fast-path para pre-flight checks** (extraer texto, contar páginas, detectar moneda primaria, validar fechas del período en cover page) **antes** de mandar al LLM. Uso: gating barato + warnings determinados que reemplazan los espurios del LLM. ~30 min de implementación, valor inmediato.

Si en algún test se demuestra que vision pierde transactions en cartolas largas (>15 págs), **entonces** evaluar Marker o Docling como **complemento** (mandar texto + imagen, no reemplazo). [H para descartar como primera apuesta, M para pdfplumber fast-path]

---

### C.2 — Two-pass / multi-pass / extract-then-verify

**Patrones publicados (2025-2026):**

1. **Constraint validation post-extracción (DETERMINISTA — sin LLM)**. El más barato y más efectivo según fuentes independientes:
   - [Unstract 2026 guide](https://unstract.com/blog/guide-to-automating-bank-statement-extraction-and-processing/): "reconciliation-validated systems gate every analysis on transactions tying to opening and closing balance".
   - [Koncile guide](https://www.koncile.ai/en/ressources/extract-data-from-bank-statements-with-ocr): "if your statement shows 247 transactions in the PDF, you should have 247 rows in the extracted data".
   - [Daloopa LLM finance guide 2025](https://daloopa.com/blog/analyst-best-practices/practical-guide-using-llms-to-supercharge-your-financial-data-analysis): "never let LLMs perform numerical extraction without deterministic verification against source documents".
   - **Concreto para el proyecto:** `closing - opening == sum(amounts_signed)` por currency group, `all_dates ∈ [period.start, period.end]` (con excepción documentada para `fecha_operacion` de cuotas), `count(transactions) == header.count` si está en el PDF.

2. **Self-consistency (Wang et al. 2022, vigente 2025)** — same model, N samples, majority vote.
   - [Rephrase 2026](https://rephrase-it.com/blog/self-consistency-prompting-how-majority-vote-reasoning-beats): GSM8K subió de 51.7% a 68% con 30 paths @ T=1.0.
   - **Limitación documentada (Stanford HAI 2025):** self-consistency "perpetuated errors in 22% of legal reasoning cases where majority paths contained same logical flaw" ([emergentmind](https://www.emergentmind.com/topics/self-consistency-in-language-models)). Si el modelo tiene un bias sistemático (ej: siempre confunde signo de cargo) majority vote NO lo arregla.
   - **Aplicabilidad al proyecto:** marginal. Las 3 corridas del eval ya hacen esto implícitamente y el resultado es bajo. Subir N a 5-10 no parece justificar el costo si el bias es sistemático (que es la hipótesis).

3. **LLM-as-judge cross-model.** Modelo A extrae, modelo B verifica.
   - Caso publicado más concreto: [Plaid Income engine 2025](https://plaid.com/blog/meet-the-new-engine-behind-plaid-income/) usa LLM + regex + ML clasificadores en cascada para fraud detection en bank statements/paystubs, identificando 30+ señales.
   - [Triplet extraction from financial reports arxiv 2602.11886](https://arxiv.org/pdf/2602.11886): "hybrid verification combining regex matching with LLM-as-judge check reduced subject hallucination from 65.2% to 1.6%".
   - **Aplicabilidad:** **alta para warnings espurios**. Hipótesis concreta: Gemini Pro extrae JSON, **Claude Sonnet 4.6 lee solo `warnings[]` + 3 sample transactions y juzga "warning legítimo o espurio"**. Sub-prompt mínimo, costo marginal.

4. **Re-ask con context** (lo que el proyecto descartó como 9.5d).
   - Patrón: si validación falla, re-prompt al mismo modelo con el output anterior + diff de constraint violated. Equivalente a lo que hace **Instructor**.
   - **Re-evaluación:** lo descartado en 9.5d fue "re-prompting genérico". **Re-prompt CON el error de constraint específico** (ej: "el sum de transactions es 1,500,000 pero closing-opening es 1,499,000, revisar transactions") es categóricamente distinto y vale la pena probar. [M]

#### Frameworks (2026 state of the art)

| Framework | Approach | Pro | Contra | Recomendación |
|---|---|---|---|---|
| **Instructor** (567-labs, ex jxnl) | Post-gen validation + retry, Pydantic-driven | 11K stars, 3M dl/mes, multi-provider (OpenAI/Anthropic/Gemini/Mistral), retry feedback automático con error message | Paga full generation antes de validar; reintenta = +cost | **#1 pick para el proyecto**. Plug-in directo en `gemini_client.py`. Pydantic schema ya existe (`CartolaCanonicalV1`). |
| **Outlines** (dottxt-ai) | Constrained decoding (FSM/guidance) durante generación | Garantiza estructura válida sin retry | Solo funciona con providers que exponen logits (no Gemini API hoy, no Anthropic API hoy). Compilation slow en schemas complejos (40s–10min en JSONSchemaBench) | **No aplicable** mientras estés en API hosted Gemini/Anthropic |
| **Marvin** (PrefectHQ, v3.0 ene 2026) | Pydantic AI underneath + agentic workflows | DX limpia, multi-provider | Más liviano para 1-shot, mismo modelo subyacente que Instructor en términos de validation | Alternativa a Instructor; menos market share |
| **Guardrails AI** | Composable validators + re-prompt | Pre-built validators (PII, toxicity, schema) | Más oriented a content moderation que a structured-output retry; lo que querés está en Instructor más limpio | **No**, overkill |
| **Native Anthropic/Gemini/OpenAI structured outputs** | Provider-side constrained generation | Garantía de forma sintáctica del schema | **No garantiza semántica.** Los warnings espurios y errores de signo SIGUEN pasando con structured output activado. | **Sí, complementario** a Instructor. No reemplaza la validación de constraints. |
| **XGrammar** | Inference-server constrained decoding (vLLM/SGLang) | <40μs/token, near-zero overhead | "Cannot be used with API providers like OpenAI or Anthropic" — solo si self-hostás | **No** mientras uses API hosted |

Fuentes: [techsy.io best LLM structured 2026](https://techsy.io/en/blog/best-llm-structured-output-libraries), [Outlines vs Instructor comparison](https://github.com/dottxt-ai/outlines/discussions/917), [JSONSchemaBench arxiv 2501.10868](https://arxiv.org/pdf/2501.10868), [XGrammar paper](https://arxiv.org/pdf/2411.15100), [Marvin v3 release](https://github.com/PrefectHQ/marvin).

#### Recomendación C.2

**Orden de aplicación (cheap-first):**

1. **Deterministic constraint validators post-extracción** (1 día). Pydantic field validators + `@model_validator` cross-field: balance reconcile per currency, period containment, count check si header lo trae, signed amount sum. **Reemplaza warnings espurios con warnings determinados a partir de violaciones reales de constraint.** Esto sólo ya puede destrabar el gate ≥90% sin tocar el LLM.
2. **Instructor wrapper sobre Gemini con retry feedback** (2-3 días). Cuando un validator falla, Instructor re-prompts automáticamente al modelo con el error específico ("transactions sum es X pero closing-opening es Y, revisar tx en página N"). **Esto es 9.5d hecho bien.**
3. **LLM-as-judge cross-model para `warnings[]` específicamente** (opcional, 1-2 días extra). Gemini Pro extrae JSON; Claude Haiku 4.5 (barato) lee solo `warnings[]` y juzga "legítimo / espurio / borderline". Solo necesario si validators + retry no llegan a 90%.
4. **Self-consistency N=3 con majority vote** (último recurso, 2 días). Mismo modelo, 3 corridas, vote por número de transactions y per-tx amount. **Caro y arregla sólo bias no-sistemático.**

---

### C.3 — Patrones específicos bank statements (schemas, multi-currency, cuotas)

#### Schemas standard mundiales

**ISO 20022 CAMT.053** (Bank-to-Customer Statement) es el schema XML estándar global para statements. Está en producción en Europa (SEPA), expandiendo en US (NACHA migration), y es la "lingua franca" de bank-to-corporate communication. ([SEPAforCorporates guide](https://www.sepaforcorporates.com/swift-for-corporates/a-practical-guide-to-the-bank-statement-camt-053-format/), [ValidateFin reading guide](https://validatefin.com/en/blog/camt053-bank-statement)).

Elementos relevantes para nuestro modelo canónico:

| CAMT.053 element | Mapeo a `CartolaCanonicalV1` | Resuelve |
|---|---|---|
| `Stmt.Acct.Ccy` | `currency` | **moneda explícita** del statement |
| `Stmt.Bal[CdOrPrtry=OPBD]` | `balances.opening` | opening balance con type code |
| `Stmt.Bal[CdOrPrtry=CLBD]` | `balances.closing` | closing balance con type code |
| `Stmt.FrToDt.FrDtTm` / `.ToDtTm` | `period.start` / `period.end` | período del statement |
| `Stmt.Ntry` (Entry) | `transactions[]` | cada transaction es un Entry |
| `Ntry.Amt.Ccy` | `transactions[].currency` | **per-transaction currency** (resuelve multi-currency) |
| `Ntry.CdtDbtInd` (CRDT/DBIT) | `transactions[].sign` o convención | **signo explícito como enum** (CRDT=credit, DBIT=debit) — no positive/negative ambiguity |
| `Ntry.BookgDt` | `transactions[].booking_date` | fecha contable |
| `Ntry.ValDt` | `transactions[].value_date` | fecha valor (≠ booking — relevante para fecha operación de cuotas) |
| `Ntry.NtryDtls.TxDtls.Refs` | `transactions[].refs` | referencias de la transacción |
| `Ntry.NtryDtls.TxDtls.RltdDts.IntrBkSttlmDt` | fecha original de la operación (anterior al período) | **encaja perfectamente con el caso cuota X/N con fecha operación previa al período** |

**Recomendación:** **no migrar `CartolaCanonicalV1` a CAMT.053 completo** (es overkill XML para 50 docs/mes), pero **adoptar sus convenciones de fields críticos**:

- `currency` por statement Y `currency` por transaction (resuelve multi-currency CLP/USD sin warning espurio).
- `CdtDbtInd: "CRDT" | "DBIT"` en vez de signo positivo/negativo del amount → elimina ambigüedad de signo.
- `booking_date` + `value_date` + `original_operation_date` (opt) → cuotas con fecha operación previa al período no rompen `period.contains` constraint.
- Balance con `type_code: "OPBD" | "CLBD"` explícito.

Esto **alinea el modelo canónico con un standard mundial** + **mata 3 de las clases de warnings espurios** que el spike 9.5f reportó.

#### Cómo IDPs maduros manejan multi-currency / cuotas / fechas

- **Mindee** ([financial documents docs](https://docs.mindee.com/use-cases/extraction-models/financial-documents)): JSON con currency por transaction; soporta multi-currency dentro del mismo doc.
- **Veryfi** ([currencies list](https://www.veryfi.com/howto/supported-currencies/)): 90+ currencies incluyendo CLP, **per-transaction currency tag**. No documenta manejo específico de cuotas.
- **Plaid** ([bank statement uploads](https://plaid.com/docs/income/document-income/)): JSON parsing, optional, 45min max latency. Sin docs públicas de cuotas Latam.
- **Para cuotas X/N en credit card statements Latam**: BBVA Peru, Banco Macro Argentina, BCI Chile usan "fecha de operación" original + cuota actual de N. **No encontré (mayo 2026) ningún IDP comercial o paper público que ataque este patrón regional con benchmark.** Es un **gap real del estado del arte**. Lo único cerca: [arxiv 2510.23066 Multi-Stage Field Extraction with VLMs](https://arxiv.org/html/2510.23066v1) menciona "semantic normalization of terminology and currency units, integration of domain-specific lexicons to reduce variability across reporting styles among different languages and countries" — pero como recomendación, no como benchmark.

**Implicancia:** el proyecto va a tener que **modelar cuotas como un caso explícito en el schema** (probablemente un campo opcional `installment: {current: int, total: int, original_date: date}`) y **eximir `original_date` del período-contains constraint**. No hay "vendor que ya lo resolvió" para copiar.

#### Repo open source más relevante encontrado

**[sebastienrousseau/bankstatementparser](https://github.com/sebastienrousseau/bankstatementparser)** — parsea 7 formatos (CAMT.053, PAIN.001, CSV, OFX, QFX, MT940, PDF digital+scanned) a un modelo Transaction unificado. Implementa **Golden Rule verification: opening + credits − debits == closing** con status VERIFIED/DISCREPANCY/FAILED. Multi-currency statements reciben **verificación independiente por grupo de currency**. PDF pipeline en cascada: deterministic → text-LLM → vision-LLM con confidence score + `source_method` audit tag.

**Valor para el proyecto:** **leer su código antes de escribir la capa de validación constraint**. Es exactamente el patrón que C.2 recomienda, ya implementado, con golden rule + multi-currency-per-group manejado.

---

### C.4 — Open Banking Chile como bypass arquitectónico

Profundización del flag dejado por Eje B.

#### Estado regulatorio (mayo 2026)

- **Ley 21.521 (Ley Fintech)** publicada enero 2023. Crea el **Sistema de Finanzas Abiertas (SFA)** bajo supervisión CMF. ([Ley en BCN](https://www.bcn.cl/leychile/navegar?idNorma=1187323), [CMF norma SFA](https://www.cmfchile.cl/portal/prensa/615/w3-article-82737.html)).
- **Timing actual (2026):** "tres años después de la promulgación, con full entry del SFA en julio 2026". CMF propuso vía consulta pública **extender el deadline a julio 2027**. ([ElEcosistemaStartup análisis mayo 2026](https://ecosistemastartup.com/ley-fintech-chile-2026-42-startups-registradas-y-plazos-cmf/), [ElMostrador mayo 2026](https://www.elmostrador.cl/noticias/2026/05/06/la-ley-fintech-si-que-cambia-el-panorama-para-los-operadores-chilenos/)).
- **Status:** 37 autorizaciones CMF otorgadas, 42 entidades registradas. **No es vaporware** — está en operación con vendors live.

#### Vendors operativos (cobertura Chile)

| Vendor | Cobertura confirmada CL | Output shape | Pricing | Auth model | Notas |
|---|---|---|---|---|---|
| **Boufin** ([boufin.com](https://www.boufin.com/)) | **BCI, Santander, Banco de Chile, Falabella + servicios estatales** explícitamente listados ([códigos entidades doc](https://doc.boufin.com/docs/general/tef_entities/)) | JSON balances + transactions + account types | "Custom, contactar" — no publicado | Usuario consiente, sistema captura | **Los 3 bancos del Family Office cubiertos**. Doc API pública. |
| **Floid** ([floid.io](https://www.floid.io/)) | "principales bancos Chile", caso de éxito con BCI publicado ([caso BCI](https://www.floid.io/casos-de-exito/bci-y-floid-impulsan-la-consolidacion-de-saldos-con-360-connect)) | JSON consolidación de saldos | Custom, contactar | Open Finance, credenciales usuario | API CMF también disponible (para data oficial). |
| **Belvo** ([belvo.com](https://belvo.com/)) | "+90% bank accounts LATAM", Chile listado pero sin lista explícita de bancos en search results | JSON banking standard | Tier'd pricing por requests | Open Banking standard | Player LATAM-wide más grande, no Chile-specific |
| **API-Banca** ([client github](https://github.com/pablomarambio/apibanca-client)) | Cliente comunitario open source | depende del banco | self-host | varies | Más DIY que SaaS |

#### Trade-offs vs PDF pipeline

| Dimensión | PDF actual | Open Banking (Boufin) |
|---|---|---|
| Contrato con cliente | "subir PDF" — pasivo, conocido | "dar consentimiento a credenciales bancarias" — más fricción, requiere onboarding |
| Frescura de data | Mensual (al cierre del statement) | Diario / on-demand |
| Accuracy | actualmente 0% gate | esperada near-100% (data viene del banco directo) |
| PII risk | PDF con todos los datos en un blob | Credenciales bancarias (más sensible) — pero Boufin actúa como proxy con CMF compliance |
| Cuotas / multi-currency / cuotas X/N | a resolver en extracción | **resuelto por el banco originador** — formato bancario nativo |
| Costo | $0.10–0.30 por cartola en LLM | Suscripción mensual + per-request (no public) |
| Velocidad de deploy | 0 — ya está | POC: 2-4 semanas (signup, contract, integration) |
| Backup si OB falla | n/a | mantener PDF pipeline como fallback |

#### Casos publicados de family offices usando Open Banking

**No encontré casos públicos específicos de family offices chilenos usando Boufin/Floid.** El target documentado es bancos corporativos (BCI usa Floid para sus propios clientes corporativos) y fintechs. Es plausible que Family Office EAG sea uno de los primeros family offices en adoptarlo — **no hay precedente público que copiar, pero la tecnología es estable**. [M para la afirmación; H para la ausencia de precedente]

#### Recomendación C.4

**El Open Banking chileno NO es un sueño futurista — es producción 2026 con los 3 bancos cubiertos por Boufin.** El cuello no es técnico, es **comercial y de UX**:

- ¿El cliente (única operadora del family office) está dispuesta a conectar credenciales BCI/Santander/BdC vía Boufin?
- ¿Cuánto cuesta el plan más bajo de Boufin (tienen que cotizar)?

**Recomendación concreta:** **pedir cotización a Boufin** (1 email, 1 día turnaround) **antes** de invertir 1 semana más en spike de LLM. Si Boufin cuesta <$200/mes para 3 cuentas con todos los movimientos diarios, **el ROI vs seguir peleando el LLM es destructor para el LLM**. Si cuesta $2000/mes, queda como Plan B para volumen 10×.

---

### C.5 — Estado del arte académico / industrial 2025-2026

#### Papers relevantes (verificados)

| Paper | Año | Hallazgo más relevante para el proyecto |
|---|---|---|
| [Multi-Modal Vision vs Text-Based Parsing for Invoice Processing (arxiv 2509.04469, IEEE Big Data 2025)](https://arxiv.org/abs/2509.04469) | 2025 | **Vision directa ≥ markdown intermediario** en 8 modelos sobre 3 datasets invoices. Confirma sospecha de C.1. |
| [Multi-Stage Field Extraction of Financial Documents with OCR and Compact VLMs (arxiv 2510.23066)](https://arxiv.org/html/2510.23066v1) | 2025 | OCR + page retrieval + VLM compacto rinde bien en docs financieros multilingual scanned. Recomienda **semantic normalization de currency units** como gap. |
| [Structuring the Unstructured: Multi-Agent System for Financial KPIs (arxiv 2505.19197)](https://arxiv.org/pdf/2505.19197) | 2025 | "Single-shot inference pipelines lack transparency, fail to isolate errors, cannot iteratively refine outputs" — argumenta multi-pass. |
| [FinTagging arxiv 2505.20650](https://arxiv.org/html/2505.20650v1) | 2025 | Benchmark LLM-ready para extracción de SEC filings. Inglés US, no aplicable directo, útil como template eval. |
| [FinDVer (arxiv 2411.05764)](https://arxiv.org/pdf/2411.05764) | 2024 | Explainable claim verification over long financial docs — patrón verify-as-judge. |
| [FinRAGBench-V (arxiv 2505.17471)](https://arxiv.org/pdf/2505.17471) | 2025 | Multimodal RAG benchmark para finance. Útil si proyecto va hacia RAG. |
| [LLM-as-judge Opportunities & Challenges (ACL EMNLP 2025)](https://aclanthology.org/2025.emnlp-main.138.pdf) | 2025 | Survey de LLM-as-judge — apoya patrón cross-model verification. |
| [Spatial ModernBERT for Table/KV Extraction Financial Documents (arxiv 2507.08865)](https://arxiv.org/pdf/2507.08865) | 2025 | BERT especializado en tablas financieras at scale — alternativa self-hosted si volumen crece. |
| [Self-consistency limitations Stanford HAI 2025](https://www.emergentmind.com/topics/self-consistency-in-language-models) | 2025 | "22% legal reasoning errors perpetuated by majority paths" — limita upside de N-sampling. |
| [OmniDocBench CVPR 2025](https://openaccess.thecvf.com/content/CVPR2025/papers/Ouyang_OmniDocBench_Benchmarking_Diverse_PDF_Document_Parsing_with_Comprehensive_Annotations_CVPR_2025_paper.pdf) | 2025 | Benchmark PDF parsing 1651 págs, 10 doc types, 5 languages. Gemini 2.0/2.5 evaluados. Estándar 2026. |

#### Benchmarks "operativos"

- **OmniDocBench (CVPR 2025)** — estándar emergente, multi-language pero **financial subset chico**.
- **RD-TableBench (Reducto)** — vendor-published, table-focused.
- **JSONSchemaBench (arxiv 2501.10868)** — para structured output frameworks. Outlines #1 en compilación-time fail, XGrammar líder en throughput.
- **FinanceBench** — QA sobre 10-K, no extracción directa.
- **ExtractBench (arxiv 2602.12247, citado Eje A)** — el más relevante para nuestro task, frontier extraction.

#### Blogs/casos de fintechs (publicados)

- **Plaid Income engine**: hybrid LLM + regex + ML, 30+ fraud signals, **es el caso publicado más cercano a lo que queremos** ([Plaid blog](https://plaid.com/blog/meet-the-new-engine-behind-plaid-income/)).
- **Unstract guide 2026** ([guía bank statement](https://unstract.com/blog/guide-to-automating-bank-statement-extraction-and-processing/)): describe pipeline LLM + reconciliation gate + balance tie + count check.
- **Daloopa LLM finance guide 2025** ([Daloopa](https://daloopa.com/blog/analyst-best-practices/practical-guide-using-llms-to-supercharge-your-financial-data-analysis)): "never let LLMs perform numerical extraction without deterministic verification".
- **Parsli LLM-OCR vs Traditional OCR 2026** ([Parsli](https://parsli.co/blog/llm-ocr-vs-traditional-ocr)): "real production answer is often hybrid".

**No encontré (verificado vía search May 2026):**
- Mercury, Brex, Ramp engineering blogs específicos a parsing de bank statements de terceros.
- Casos publicados Family Office específicos con cualquier vendor de Document AI.
- Discusiones HN/Reddit con benchmarks reproducibles sobre cartolas LATAM.

---

### Síntesis cross-cutting con Ejes A y B

| Arquitectura C | Modelo A recomendado | IDP B aplicable | Cuándo aplica | Effort | Probabilidad cerrar gate ≥90% |
|---|---|---|---|---|---|
| **Vanilla A: LLM single-shot** (status actual) | Gemini 3.5 Flash | n/a | Caso base | 0 | bajo — el problema medido |
| **A + C.2 deterministic validators post** | Gemini 2.5 Pro o 3.5 Flash | n/a | Como **first patch**, sin cambiar modelo | 1 día | **alto** — ataca directo el problema medido (warnings espurios + signo) |
| **A + Instructor retry** | Gemini 3.5 Flash con structured output + Pydantic | n/a | Después de validators básicos | 2-3 días | alto — agrega retry semántico sobre validators |
| **A + LLM-as-judge cross-model** | Gemini Pro extrae + Claude Haiku 4.5 juzga warnings | n/a | Si validators+retry no cierran | 2 días extra | medio — caro pero específico al problema |
| **C.1 híbrido text-layer + A** | Marker/Docling → Gemini Pro | n/a | Última carta antes de IDP | 3-4 días | bajo-medio — paper independiente sugiere downside |
| **Eje B: Mindee IDP standalone** | n/a | Mindee Bank Statement | Si A+C no cierran, plan B | 2-3 hs test | medio — depende cobertura bancos CL |
| **C.4 Open Banking bypass** | n/a | Boufin | Si comercialmente viable | 2-4 semanas | **muy alto** — elimina extracción |

**El path con mejor expected value:** **A (Gemini 2.5 Pro actual) + C.2 validators deterministas + Instructor retry**, mientras en paralelo **se cotiza Boufin**. Si el path A+C cierra el gate, problema resuelto a costo marginal. Si Boufin cotiza <$200/mes, **pivot arquitectónico** que mata el problema sin importar el LLM.

---

### Hipótesis para testear con el eval set actual

Numerado para continuar la serie H1-H6 del Eje A.

| # | Hipótesis | Cambio concreto | Métrica esperada | Apuesta | Effort |
|---|---|---|---|---|---|
| H7 | **Validators deterministas post-extracción suprimen >80% de los warnings espurios** sin tocar el LLM | Pydantic `@model_validator` para balance reconcile per-currency + period containment + count check (si header lo trae) + cuotas exception | warnings espurios → 0; verde sube de 0% a ≥50% solo por suprimir falsos warnings | **muy probable** (problema medido) | 1 día |
| H8 | **Instructor + retry semántico con error message del validator** llega a balance OK 100% en los 2 PDFs que Pro 2.5 falló | wrap `gemini_client.py` en Instructor, pasar el validator error al retry, max 2 retries | balance OK 14/14, verde ≥90% | **probable** | 2-3 días |
| H9 | **LLM-as-judge cross-model con Claude Haiku 4.5 sobre `warnings[]`** reduce falsos warnings a <5% | Gemini Pro extrae; segundo call a Claude Haiku con prompt "given warnings list and 3 sample tx, mark each warning as legit/spurious/borderline" | warning precision >95% | **probable**, marginal sobre H7+H8 si esos cierran | 1-2 días |
| H10 | **Adoptar convenciones CAMT.053 en `CartolaCanonicalV1`** (`CdtDbtInd` enum, `currency` per-tx, `value_date` vs `booking_date`) elimina la clase entera de errores de signo y multi-currency | refactor del Pydantic schema + prompt update para emitir esos fields explícitamente | signo errors → 0; PARSE_AMBIGUOUS → 0 | **alto upside, breaking change** | 2 días refactor + re-test |
| H11 | **Marker → markdown + imagen → Gemini Pro** (no markdown solo) mejora vs PDF binario solo en cartolas multi-página | doble input al LLM: markdown text + PDF original | balance OK 14/14 si vision missing en cartolas largas | **incierto** (paper independiente sugiere upside acotado) | 3-4 días |
| H12 | **Boufin cubre los 3 bancos y cuesta <$200/mes** → reemplaza pipeline | email Boufin pidiendo cotización + POC con 1 banco | costo + accuracy mejor que API LLM | **muy alto upside si numbers cierran** | 1 día research + 2-4 semanas integración |

**Orden recomendado de test:** H7 → H8 → H10 (en paralelo) → H9 (si H7+H8 no cierran) → H12 (en paralelo a todo) → H11 (último recurso).

---

### Gaps de información

1. **Cuotas X/N en bank statements Latam: cero benchmarks públicos.** Ningún IDP ni paper ataca específicamente el patrón regional. Implicancia: vamos a estar en territorio inexplorado, **medir nosotros sobre los 14 PDFs es la única forma de validar**. [Impact: alto]
2. **Pricing Boufin / Floid no publicado.** Hay que pedir cotización para tener data de decisión. [Impact: alto para H12]
3. **Comportamiento real de Instructor sobre Gemini API en español**: la librería es robusta pero la mayoría de ejemplos son OpenAI/Anthropic + inglés. Posible gotcha sobre retry+context con cartolas largas en CLP. [Impact: medio]
4. **Vision-en-markdown loss para tablas multi-columna específicamente** (no general): no encontré benchmark cuantificado de "cuánta info de layout se pierde con Marker en bank statements vs vision directa". [Impact: medio para H11]
5. **Casos de Family Office adoptando Open Banking en Chile**: cero ejemplos públicos. No sabemos si hay obstáculos comerciales o de UX no-obvios al pedir credenciales bancarias a clientes. [Impact: medio para H12]
6. **Adopción real de CAMT.053 por bancos chilenos**: la teoría dice "lingua franca mundial"; en la práctica BCI/Santander/BdC Chile **no exponen CAMT.053 a clientes finales** (lo usan en SWIFT B2B). Adoptar sus *convenciones* en nuestro schema es viable; obtener archivos CAMT.053 nativos del banco probablemente no. [Impact: bajo, ya asumido]

---

### Conclusión Eje C

Eje C **sí aporta sobre A+B**, pero **NO en la dirección esperada por el research brief**. La hipótesis natural era "pipeline híbrido text-layer + LLM destraba el gate". La evidencia 2025-2026 (paper IEEE Big Data + Reducto + Parsli) sugiere lo contrario: vision directa ≥ markdown para docs financieros.

**El verdadero aporte de C es:**

1. **Validación constraint-based determinista post-extracción + framework retry (Instructor)** es el patrón que múltiples sources independientes (Plaid, Daloopa, Unstract, paper arxiv) confirman como ganador para finance. Es exactamente la pieza ausente del pipeline actual. **Probable que cierre el gate ≥90% sin cambiar el modelo.**
2. **Adoptar convenciones de schema CAMT.053** (CdtDbtInd enum, currency per-tx, fechas separadas booking/value/original) **mata por construcción** las clases de warning espurio que el spike 9.5f reportó. Refactor barato, alto upside.
3. **Open Banking Chile vía Boufin es production-ready hoy** y cubre los 3 bancos del Family Office. Es el bypass arquitectónico real. Cotizar a Boufin debería ser el siguiente Slack message del proyecto, no un siguiente research.

**Lo que C NO aporta:** un pipeline mágico de pre-procesamiento que arregla el LLM. La evidencia dice que esa hipótesis es probablemente neutra-a-negativa.

---

### Sources Eje C

#### Papers / academic

- [Multi-Modal Vision vs. Text-Based Parsing for Invoice Processing — arxiv 2509.04469 (IEEE Big Data 2025)](https://arxiv.org/abs/2509.04469)
- [Multi-Stage Field Extraction with OCR + VLMs — arxiv 2510.23066](https://arxiv.org/html/2510.23066v1)
- [Structuring the Unstructured: Multi-Agent System for Financial KPIs — arxiv 2505.19197](https://arxiv.org/pdf/2505.19197)
- [FinTagging benchmark — arxiv 2505.20650](https://arxiv.org/html/2505.20650v1)
- [FinDVer claim verification — arxiv 2411.05764](https://arxiv.org/pdf/2411.05764)
- [FinRAGBench-V multimodal RAG finance — arxiv 2505.17471](https://arxiv.org/pdf/2505.17471)
- [LLM-as-judge survey ACL EMNLP 2025](https://aclanthology.org/2025.emnlp-main.138.pdf)
- [Spatial ModernBERT financial documents — arxiv 2507.08865](https://arxiv.org/pdf/2507.08865)
- [Self-consistency Stanford HAI limitations 2025](https://www.emergentmind.com/topics/self-consistency-in-language-models)
- [OmniDocBench CVPR 2025](https://openaccess.thecvf.com/content/CVPR2025/papers/Ouyang_OmniDocBench_Benchmarking_Diverse_PDF_Document_Parsing_with_Comprehensive_Annotations_CVPR_2025_paper.pdf)
- [JSONSchemaBench structured outputs — arxiv 2501.10868](https://arxiv.org/pdf/2501.10868)
- [XGrammar engine — arxiv 2411.15100](https://arxiv.org/pdf/2411.15100)
- [Triplet extraction financial reports — arxiv 2602.11886](https://arxiv.org/pdf/2602.11886)

#### Frameworks / libs

- [Instructor (567-labs)](https://python.useinstructor.com/)
- [Instructor retrying docs](https://github.com/567-labs/instructor/blob/main/docs/concepts/retrying.md)
- [Outlines (dottxt-ai)](https://dottxt-ai.github.io/outlines/latest/)
- [Marvin (PrefectHQ) v3](https://github.com/PrefectHQ/marvin)
- [Guardrails AI review 2026](https://appsecsanta.com/guardrails-ai)

#### PDF extraction libs

- [Marker (datalab-to)](https://github.com/VikParuchuri/marker)
- [Docling (IBM DS4SD)](https://arxiv.org/pdf/2501.17887)
- [pdfmux 200-PDF benchmark 2026](https://pdfmux.com/blog/pdfmux-vs-pymupdf-vs-marker-vs-docling/)
- [Themenonlab best open source PDF→MD 2026](https://themenonlab.blog/blog/best-open-source-pdf-to-markdown-tools-2026)
- [Codecut Docling vs Marker vs LlamaParse](https://codecut.ai/docling-vs-marker-vs-llamaparse/)
- [PyMuPDF4LLM docs](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/)
- [Surya OCR](https://github.com/datalab-to/surya)
- [Reducto agentic enhancement](https://llms.reducto.ai/)
- [Parsli LLM-OCR vs Traditional](https://parsli.co/blog/llm-ocr-vs-traditional-ocr)

#### Bank statement schemas / standards

- [CAMT.053 practical guide (SEPAforCorporates)](https://www.sepaforcorporates.com/swift-for-corporates/a-practical-guide-to-the-bank-statement-camt-053-format/)
- [Reading CAMT.053 (ValidateFin)](https://validatefin.com/en/blog/camt053-bank-statement)
- [MT940 vs CAMT.053 format guide](https://invoicedataextraction.com/blog/mt940-camt053-bank-statement-format-guide)
- [Goldman Sachs CAMT.053 sample](https://developer.gs.com/docs/services/transaction-banking/camt-053-us-sample)
- [Deutsche Bank ISO 20022 transition](https://corporates.db.com/in-focus/Focus-topics/iso20022/blogs/transitioning-to-iso-20022-account-statements)
- [sebastienrousseau/bankstatementparser repo (7 formatos + Golden Rule)](https://github.com/sebastienrousseau/bankstatementparser)
- [ofxstatement (kedder)](https://github.com/kedder/ofxstatement)

#### Fintech production patterns

- [Plaid Income engine 2025](https://plaid.com/blog/meet-the-new-engine-behind-plaid-income/)
- [Plaid bank statement uploads API](https://plaid.com/docs/income/document-income/)
- [Daloopa LLM finance guide 2025](https://daloopa.com/blog/analyst-best-practices/practical-guide-using-llms-to-supercharge-your-financial-data-analysis)
- [Unstract bank statement automation 2026](https://unstract.com/blog/guide-to-automating-bank-statement-extraction-and-processing/)
- [Koncile bank statement OCR guide](https://www.koncile.ai/en/ressources/extract-data-from-bank-statements-with-ocr)

#### Open Banking Chile

- [Ley 21.521 texto oficial BCN](https://www.bcn.cl/leychile/navegar?idNorma=1187323)
- [CMF norma SFA prensa](https://www.cmfchile.cl/portal/prensa/615/w3-article-82737.html)
- [CMF Fintec educa](https://www.cmfchile.cl/educa/621/w3-propertyvalue-48145.html)
- [Análisis SFA mayo 2026 (ElEcosistemaStartup)](https://ecosistemastartup.com/ley-fintech-chile-2026-42-startups-registradas-y-plazos-cmf/)
- [Ley Fintech cambio panorama (ElMostrador may 2026)](https://www.elmostrador.cl/noticias/2026/05/06/la-ley-fintech-si-que-cambia-el-panorama-para-los-operadores-chilenos/)
- [Boufin entidades financieras (BCI/Santander/BdC/Falabella)](https://doc.boufin.com/docs/general/tef_entities/)
- [Boufin API docs](https://doc.boufin.com/api/)
- [Floid caso BCI Open Banking](https://www.floid.io/casos-de-exito/bci-y-floid-impulsan-la-consolidacion-de-saldos-con-360-connect)
- [Floid API CMF](https://www.floid.io/servicios/api-cmf)
- [API-Banca client github](https://github.com/pablomarambio/apibanca-client)
- [Belvo Chile coverage developer hub](https://developers.belvo.com/docs/institution)
