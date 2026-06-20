---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments: []
workflowType: 'research'
lastStep: 6
research_type: 'technical'
research_topic: 'Técnicas SOTA para extracción de datos de PDFs financieros desestructurados (cartolas bancarias y de inversión) vía cloud APIs'
research_goals: 'Evaluar si conviene reemplazar el stack actual (gemini-3.5-flash con prompting) por alternativas mejores — OCR especializado, layout/document models, o Document AI APIs dedicadas'
user_name: 'Ary'
date: '2026-06-10'
web_research_enabled: true
source_verification: true
---

# Research Report: technical

**Date:** 2026-06-10
**Author:** Ary
**Research Type:** technical

---

## Research Overview

Esta investigación técnica evalúa el estado del arte (2025–2026) en extracción de datos desde PDFs financieros desestructurados —cartolas bancarias y de inversión— vía cloud APIs, con el objetivo de decidir si conviene **reemplazar el stack actual del proyecto** (`gemini-3.5-flash` con prompting + validadores deterministas). El alcance se amplió, a pedido, para cubrir también lectura de PDF en general (contratos, reportes, papers, formularios, escaneados).

El hallazgo central es contraintuitivo y decisivo: **el research no justifica reemplazar el stack — lo valida.** Los tres clouds (AWS, Azure, Google) convergieron en *extracción LLM con schema en lenguaje natural*, exactamente el approach que el proyecto ya prototipó; ningún Document AI dedicado lee cartola chilena out-of-the-box; y Gemini lidera price/performance en tablas densas evitando el modo de falla de Claude de omitir tablas. La palanca real de mejora no es cambiar de vendor sino **profundizar capas que el proyecto ya empezó**: regression gate sobre golden set, reconciliación más fina (fila-por-línea, inter-cartola, inversión), y HITL UI — más optimización de costo (batch −50%, tier-0 born-digital).

La metodología combinó 10 subagentes de investigación con búsqueda web y verificación de fuentes, cubriendo seis ejes (panorama de stack, integración, arquitectura, implementación, reconciliación, governance), con niveles de confianza explícitos y mapeo directo al código real del proyecto. El resumen ejecutivo completo, el veredicto de decisión y el roadmap están en la **Síntesis Técnica y Conclusiones** al final del documento.

---

<!-- Content will be appended sequentially through research workflow steps -->

## Technical Research Scope Confirmation

**Research Topic:** Técnicas SOTA para extracción de datos de PDFs financieros desestructurados (cartolas bancarias y de inversión) vía cloud APIs
**Research Goals:** Evaluar si conviene reemplazar el stack actual (gemini-3.5-flash con prompting) por alternativas mejores — OCR especializado, layout/document models, o Document AI APIs dedicadas

**Technical Research Scope:**

- Panorama de enfoques (2025–2026) — LLMs multimodales, Document AI dedicadas, layout-aware models, OCR+VLM pipelines
- Precisión / accuracy — tablas densas, multi-página, layouts variables entre emisores, benchmarks públicos
- Costo y latencia — por-página/por-token, batch vs real-time
- Patrones de integración — APIs, salida estructurada (JSON schema), grounding/bounding boxes
- Veredicto para reemplazo — cuándo Gemini-LLM gana vs Document AI especializado vs híbrido

**Research Methodology:**

- Current web data with rigorous source verification
- Multi-source validation for critical technical claims
- Confidence level framework for uncertain information
- Comprehensive technical coverage with architecture-specific insights

**Scope Confirmed:** 2026-06-10

---

## Technology Stack Analysis — Panorama de Enfoques (2025–2026)

> Nota de método: varias fuentes están fechadas a mediados de 2026 y referencian model IDs forward-dated (Gemini 3.x, GPT-5.x, Claude Opus 4.8 / "Fable 5", MinerU2.5, PaddleOCR-VL 1.6). Se preservan tal cual fueron citadas, con el flag de confianza correspondiente. Los **patrones** (capacidades, pricing, failure modes) son los hallazgos durables; los **decimales exactos** de benchmarks son indicativos.

### El espectro: tres campos arquitectónicos

El panorama de extracción de documentos se divide hoy en tres enfoques, y los benchmarks ya los comparan head-to-head:

1. **Herramientas pipeline (modulares):** detector de layout → OCR → modelo de estructura de tablas. Ej.: Docling, Marker, Unstructured, PP-StructureV3, Nougat. Históricamente las más fuertes en estructura, hoy siendo superadas.
2. **VLMs especializados (expert document models):** un solo modelo vision-language end-to-end entrenado para parsear documentos. Ej.: MinerU2.5, PaddleOCR-VL, dots.ocr, olmOCR-2, Granite-Docling. **Este campo es hoy SOTA en los benchmarks principales.**
3. **LLMs multimodales generales:** Gemini, GPT, Claude. Cada vez más competitivos, pero en tablas densas quedan _por debajo_ de los mejores VLMs especializados, aunque _por encima_ de las pipeline tools viejas.

_Hallazgo transversal 2025–2026: la brecha entre "usá Gemini/GPT directo" y herramientas dedicadas se achicó fuerte; pero para **tablas densas específicamente**, las herramientas de tabla dedicadas y los VLMs especializados siguen liderando por unos pocos puntos TEDS._
_Source: OmniDocBench leaderboard (https://github.com/opendatalab/OmniDocBench) · LlamaIndex saturation analysis (https://www.llamaindex.ai/blog/omnidocbench-is-saturated-what-s-next-for-ocr-benchmarks)_

### LLMs multimodales cloud (el campo de tu stack actual)

**Google Gemini** — líder actual de price/performance en tablas densas.
- Visión PDF nativa: texto, charts, **tablas**, hasta 1000 páginas / 50 MB; 258 tokens/página; en Gemini 3 el texto extraído nativo no se cobra (solo modalidad imagen). `media_resolution` (low/medium/high) regula costo vs fidelidad.
- Salida estructurada vía JSON Schema (enum, min/max, required, etc.); puede combinarse con tools. **No** hay bounding-box a nivel de schema (el grounding espacial es una capacidad de visión aparte).
- Pricing: Gemini 3 Flash ≈ $0.50 in / $3 out por 1M tokens; **Batch API 50% off**; File API gratis (≤50 MB/1000 pp, retención 48h).
- _Source: https://ai.google.dev/gemini-api/docs/document-processing · https://ai.google.dev/gemini-api/docs/structured-output · https://ai.google.dev/gemini-api/docs/gemini-3 · https://ai.google.dev/gemini-api/docs/batch-api_

**OpenAI GPT** — el más fuerte en grounding espacial y JSON estricto.
- **Bounding boxes** vía JSON schema estricto en grid 0–999 (origen top-left) — diferenciador real para localización de celdas.
- `reasoning_effort` (high/xhigh), `detail="original"`, `verbosity="high"` recomendados para tablas densas. Strict JSON Schema garantiza adherencia (sin keys faltantes / enums inválidos).
- Posición en benchmark de tablas: GPT-5 mini 7.14/10 — mid-pack, por debajo de Gemini. Excelente en PDFs de texto limpio (98% invoices, Koncile), token-hungry.
- _Source: https://developers.openai.com/api/docs/guides/structured-outputs · https://developers.openai.com/cookbook/examples/multimodal/document_and_multimodal_understanding_tips · https://www.koncile.ai/en/ressources/claude-gpt-or-gemini-which-is-the-best-llm-for-invoice-extraction_

**Anthropic Claude** — el mejor en _razonamiento_ financiero downstream y consistencia de JSON; el **más débil en extracción cruda de tablas densas**.
- PDF nativo: cada página como imagen + texto extraído; límites 32 MB / 600 pp (100 en modelos de 200k). En Bedrock, el entendimiento visual del PDF **requiere citations activadas** o cae silenciosamente a texto-solo.
- **Dos límites críticos para cartolas:** (1) **Citations + Structured Outputs son incompatibles → error 400** (forzás elegir uno, o diseño de dos pasadas); (2) Citations solo funcionan sobre texto extraíble — **cartolas escaneadas no son citables**, justo donde más importa verificar.
- En el benchmark independiente de tablas, Claude Sonnet 4.6 = 7.02/10 (el más bajo de los API models), con modo de falla de **omitir tablas enteras**.
- _Source: https://platform.claude.com/docs/en/build-with-claude/pdf-support · https://platform.claude.com/docs/en/build-with-claude/citations_

### Document AI cloud dedicadas (servicios purpose-built)

**AWS Textract (+ Bedrock Data Automation):**
- Sin modelo prebuilt "bank statement" standalone; la vía práctica son **Queries** (preguntas NL pre-entrenadas, incluyen bank statements) + Tables, o `AnalyzeLending` (orientado a mortgage). Determinista (misma entrada → misma salida), ventaja de compliance.
- Pricing (por 1k pp, us-west-2): OCR $1.50; Tables $15; Queries $15; Forms+Tables+Queries $70; AnalyzeLending $70; Custom Queries adapter $25.
- **Customización:** Custom Queries adapter, mínimo 5+5 samples. Dirección 2025–2026 = **Bedrock Data Automation (BDA)**: blueprints LLM para bank statements y 1099-B (inversión), schema en lenguaje natural, grounding visual + confidence; ~$0.010/página (low-confidence, verificar), cap de 20 pp/doc en custom extraction (jun 2025).
- _Source: https://aws.amazon.com/textract/pricing/ · https://docs.aws.amazon.com/textract/latest/dg/best-practices-adapters.html · https://aws.amazon.com/blogs/machine-learning/process-financial-documents-using-amazon-bedrock-data-automation/_

**Microsoft Azure → Content Understanding (el cambio de cabecera):**
- Document Intelligence tiene `prebuilt-bankStatement.us` (v4.0 GA, **US-only, en-us**) con schema que mapea limpio a un ledger (Date/Description/DepositAmount/WithdrawalAmount/Begin+EndBalance) — pero **US-tuned**, una cartola chilena (español, RUT, CLP) está fuera de distribución.
- **Azure Content Understanding** (GA API `2025-11-01`) absorbe DI: **LLM-powered, BYO model** (hasta GPT-5.x), schema **declarativo** (descripciones de campo = prompts, sin labeling/training), nesting hasta 7 niveles / 1000 campos, tablas multi-página como objeto único. Confidence + grounding (bbox) toggleables. **El mejor fit entre los tres para cartolas chilenas** (definís semántica en español en el schema prompt).
- _Source: https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/bank-statement · https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/whats-new · https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/concepts/prebuilt-analyzers_

**Google Cloud Document AI:**
- Bank Statement Parser prebuilt = ML clásico, **inglés, US/EU only** → cartola chilena fuera de alcance. $0.75/documento.
- La vía real en GCP es **Custom Extractor (Gemini-powered, generativo)**: out-of-the-box, mejora con few-shot de tan poco como **10 documentos etiquetados**, 60+ idiomas (aunque "inglés es el oficialmente soportado para GenAI extraction" — español probable pero no garantizado, flag). $30/1k pp.
- _Source: https://docs.cloud.google.com/document-ai/docs/processors-list · https://cloud.google.com/document-ai/pricing_

### VLMs especializados / OCR open-source (contexto SOTA, mayormente self-host)

- **Docling + TableFormer / Granite-Docling (IBM):** TableFormer entrenado en 1M+ tablas (incl. financieras); **97.9% cell accuracy** en tablas complejas. Granite-Docling en **FinTabNet TEDS 0.96–0.97** — el número _purpose-built financiero_ más fuerte hallado, y open-source/self-hostable. Ganó test independiente de tablas (Procycons). _Source: https://research.ibm.com/blog/docling-generative-AI · https://procycons.com/en/blogs/pdf-data-extraction-benchmark/_
- **MinerU2.5, PaddleOCR-VL (0.9B), dots.ocr (1.7B), olmOCR-2:** tope de OmniDocBench entre VLMs especializados (95–96 composite, Table TEDS ~93). Corren baratos pero requieren GPU/self-host. _Source: https://github.com/opendatalab/OmniDocBench_
- **Hosted table-specialists:** Reducto (premium, RD-TableBench self-published 90.2 avg), Mistral OCR API (el más barato $1–2/1k pp, tablas más débiles ~71 TEDS). _Source: https://reducto.ai/blog/rd-tablebench · https://www.codesota.com/ocr/mistral-ocr-3_

### Benchmarks (las varas de medición)

- **OmniDocBench** (CVPR 2025) — benchmark general dominante; métricas: edit-distance (texto), **TEDS (tablas)**, CDM (fórmulas). **CAVEAT crítico: está saturado** (top models >94%), sobre-pondera papers académicos, **carece de presentaciones financieras complejas** → un score alto NO garantiza fidelidad en tablas financieras densas. _Source: https://github.com/opendatalab/OmniDocBench · https://www.llamaindex.ai/blog/omnidocbench-is-saturated-what-s-next-for-ocr-benchmarks_
- **FinTabNet** — el benchmark estándar de **tablas financieras** (S&P 500 annual reports, headers multinivel, celdas merged). Usado con TEDS. _Source: https://arxiv.org/pdf/2303.00716_
- **arXiv 2603.18652 "Beyond String Matching"** (~abr 2026) — 21 parsers, 451 tablas, LLM-as-judge validado vs humanos. Ranking de extracción de tablas: **Gemini 3 Pro 9.55 · Gemini 3 Flash 9.50 ($0.57/100pp) · Mistral OCR 3 8.89 · dots.ocr 8.73 · GPT-5 mini 7.14 · Claude Sonnet 4.6 7.02**. Caveat: data **sintética**, no cartolas reales. _Source: https://arxiv.org/abs/2603.18652_
- **RD-TableBench (Reducto)** — 1000 tablas complejas. Vendor-published (flag de sesgo). Por-proveedor: Reducto 90.2 > Azure DI 82.7 > Textract 80.9 > Google DocAI **64.6** (notablemente débil en tablas complejas). _Source: https://reducto.ai/blog/rd-tablebench · https://aimultiple.com/invoice-ocr_

### Especializadas vs LLMs generales — la pregunta central

- **En parsing general (OmniDocBench):** los mejores VLMs especializados (MinerU2.5 ~95.75) le ganan al mejor LLM general (Gemini 3 Pro ~92.91) por ~3 pts overall y ~4 pts en Table TEDS; ambos aplastan a las pipeline tools (Marker 78.44). _Source: https://github.com/opendatalab/OmniDocBench (números forward-dated, indicativos)_
- **En tablas complejas (RD-TableBench):** herramientas de tabla dedicadas le ganan a GPT-4o prompteado directo.
- **En invoices / extracción de campos (KV):** los **LLMs generales ganan** (Claude/GPT/Gemini > Textract/Azure/Google DocAI), porque el problema es semántico más que estructural. _Source: https://aimultiple.com/invoice-ocr · https://www.businesswaretech.com/blog/research-best-ai-services-for-automatic-invoice-processing_
- **El patrón de producción emergente (híbrido):** OCR/herramienta barata sobre el ~80% fácil + LLM multimodal sobre el ~20% degradado/complejo → "costo nivel-Textract en el 80%, accuracy nivel-LLM en el 20%". _Source: https://llms.reducto.ai/best-llm-ready-document-parsers-2025 · https://aimultiple.com/invoice-ocr_

### Failure modes para tablas financieras (síntesis — relevante a reconciliación)

- **Errores confiados silenciosos / números alucinados:** estructural en transformers. Un test sobre cartolas bancarias reales (SprintHive 2026) encontró que _todos_ los frontier models cometieron el mismo error de clasificación de transacción y **ninguno marcó incertidumbre**. _Source: https://www.sprinthive.com/post/3-vital-insights-for-fraud-heads-and-ctos-on-llms-in-ai-onboarding_
- **Tablas/filas omitidas:** Claude Sonnet 4.6 y olmOCR son bimodales — omiten tablas enteras (pérdida total silenciosa de datos). _Source: https://arxiv.org/abs/2603.18652_
- **Desalineación de columnas / errores de dígitos:** FinCriticalED (arXiv 2511.14998) confirma dificultad con reconocimiento preciso de dígitos y alineación, degradando en multi-página.
- **Scans vs PDFs de texto:** split claro — Gemini mejor en scans (94%), GPT mejor en texto (98%), Claude el más débil en scans (90%).
- **Implicación de arquitectura:** una capa de **verificación/reconciliación determinista** (balance = saldo previo + Σmovimientos, cross-check de totales) es obligatoria con cualquier vendor. Coincide con tu hallazgo del prototipo de gastos (diff=0 vía función determinista sobre ledger-entries).

### Veredicto preliminar para tu caso (cartolas CL + inversión, cloud OK)

- Ningún prebuilt bank-statement de AWS/Azure/Google maneja layouts chilenos (español/CLP/RUT) — todos son US/EN-locked.
- La dirección 2025–2026 de los tres clouds **converge en extracción LLM con schema en lenguaje natural** (Azure Content Understanding, Google Custom Extractor sobre Gemini, AWS BDA). Es decir: el approach que tu prototipo ya probó (Gemini + prompting) es exactamente hacia donde migraron los servicios "dedicados".
- Gemini 3 Flash lidera price/performance en tablas densas y tiene el mejor perfil de completitud (>70% de tablas perfectas, evita el modo de omisión de Claude). Esto **valida tu elección actual de gemini-flash** más de lo que la cuestiona.
- La palanca de mejora más probable no es cambiar de vendor sino: (a) salida estructurada con JSON schema estricto, (b) capa de reconciliación determinista, (c) considerar un híbrido con un table-specialist (Docling/Reducto) o grounding/bbox (GPT) solo para el subconjunto difícil.

_Confianza: ALTA en specs/pricing oficiales y mecánica de cada API. MEDIA en rankings de benchmarks (sintéticos o forward-dated). BAJA en claims de marketing de vendors (Box, SprintHive, Reducto self-published). GAP principal: no existe benchmark público independiente sobre cartolas chilenas/custodios reales — el research siguiente debería pesar esto._

---

## Análisis Ampliado — Lectura de PDF en General (texto + tablas no estructuradas, cualquier dominio)

> Ampliación del scope: más allá de cartolas financieras, esto cubre lectura de PDF en general (contratos, reportes, papers, formularios, manuales, escaneados). El principio organizador no es "qué vendor" sino **qué tipo de PDF tenés enfrente** — esa decisión domina todo lo demás.

### La decisión que manda sobre todas: born-digital vs escaneado

Antes de elegir herramienta, hay una bifurcación que define el costo, la latencia y la calidad de todo el pipeline:

- **Born-digital (PDF con capa de texto):** el texto está embebido. Las librerías deterministas lo leen directo, gratis, en milisegundos, sin alucinar. Cubre una fracción grande de contratos, reportes y papers modernos.
- **Escaneado (imágenes de páginas, sin capa de texto):** las librerías deterministas devuelven vacío/basura. Necesitás OCR (clásico o VLM) para reconstruir el texto pixel a pixel.
- **Cómo detectar:** extraer texto con PyMuPDF y medir caracteres por página; si está por debajo de un umbral (~100 chars) y la página es mayormente imagen → es scan. Investigación CCpdf (arXiv 2304.14953) clasificó 1-de-5 docs como born-digital con exactamente esta heurística, ahorrándose el OCR.
- **El patrón router de 2026:** correr la extracción barata primero, medir, y enrutar solo las páginas pobres en texto a OCR/VLM. Posts reportan reducciones de costo de 60x por enrutar en vez de mandar todo a un LLM.
- _Source: https://arxiv.org/pdf/2304.14953 · https://ocrmypdf.readthedocs.io/en/latest/introduction.html · https://parsli.co/blog/real-cost-llm-ocr-document-extraction_

### Capa 1 — Librerías deterministas (texto + layout), gratis y locales

Todas leen la capa de texto existente; ninguna hace reconocimiento de píxeles (born-digital only).

| Librería | Velocidad | Accuracy texto | Licencia | Nota |
|---|---|---|---|---|
| **PyMuPDF** (fitz) | ~0.1s, ~180 pp/s | 96% | **AGPL-3.0** | El más rápido; AGPL obliga a disclosure en SaaS (o licencia comercial) |
| **pypdfium2** | ~0.1s | **97%** | BSD/Apache | Mejor accuracy + licencia permisiva; API de bajo nivel |
| **Tika/PDFBox** | ~0.2s | 95% | Apache-2.0 | Estándar JVM; **no reconstruye tablas** (maintainers lo dicen explícito) |
| **pdfminer.six** | ~5.8s | 89% | MIT | Motor de layout puro-Python; base de pdfplumber |
| **pdfplumber** | ~9.5s | (layout) | MIT | Control fino de tablas; la opción MIT cuando AGPL no sirve |

_Source: https://github.com/py-pdf/benchmarks · https://arxiv.org/html/2410.09871v1 · https://cwiki.apache.org/confluence/pages/viewpage.action?pageId=109454066_

### Extracción de tablas determinista — lattice vs stream

La distinción mecánica central (válida conceptualmente para todas estas herramientas):

- **Lattice** = tablas con **líneas dibujadas**. Detecta segmentos de línea, encuentra intersecciones, reconstruye la grilla. Excelente en tablas con bordes; **falla sin gridlines**.
- **Stream** = tablas **sin bordes**, inferidas por whitespace/alineación. Frágil: se rompe con columnas ragged, celdas multi-línea, celdas merged.

| Herramienta | Fuerte en | Límite |
|---|---|---|
| **Camelot** (lattice+stream) | Mejor en tablas con bordes; output más limpio | Born-digital; débil en tablas legales/messy (0.39 F1) |
| **Tabula** (Java/JVM) | Buena detección stream/borderless | Parsing más débil que Camelot |
| **pdfplumber** `extract_table()` | Máximo control, tunable | El más lento; sufre con celdas merged |
| **PyMuPDF** `find_tables()` | Rápido (~45 pp/s), algoritmo portado de pdfplumber | **Solo tablas con bordes**; borderless/multipágina/merged necesitan código custom |

_Hallazgo de benchmark: las herramientas tradicionales ganan en tablas limpias con líneas; las learning-based (TATR/Table Transformer) ganan en tablas científicas/complejas. Elegir mal el parser es la fuente de error dominante (scores de 2.10 a 9.55 en el mismo corpus)._
_Source: https://camelot-py.readthedocs.io/en/master/user/how-it-works.html · https://arxiv.org/html/2410.09871v1 · https://arxiv.org/html/2603.18652v1_

### Para RAG / Markdown — toolkits encima del parser

Cuando el objetivo es convertir PDF messy (texto + tablas + figuras) en Markdown/JSON/chunks limpios:

- **PyMuPDF4LLM:** PyMuPDF → Markdown con reading-order y multi-columna. Conveniencia de serialización, no mejor detector de tablas (hereda AGPL + bordered-only).
- **Docling (IBM):** open-source Apache, convierte PDF/DOCX/PPTX/… a Markdown/JSON. Layout (DocLayNet) + tablas (TableFormer). Independiente Procycons: **97.9% cell accuracy en tablas jerárquicas complejas**, ganó el estudio. Chunking semántico nativo para RAG. Caveat: otro test (CodeCut) lo halló lento y alucinando en tablas densas — depende del tipo de doc.
- **Marker (Datalab):** PDF→Markdown, layout-perfect; flag `--use_llm` sube accuracy con costo API. Alta calidad pero lento (20x más que LlamaParse en un test).
- **MarkItDown (Microsoft):** liviano, muchos formatos → Markdown. **Sin OCR por defecto; rompe tablas feo** (columna por columna). Sirve para Office born-digital limpio, no para PDFs complejos.
- **Unstructured.io:** partición en elementos semánticos (Title/Table/…); `hi_res` extrae tablas (`text_as_html`), `fast` no. Mejor historia de metadata+chunking para RAG. Independiente: 100% en tablas simples, **~75% en complejas**. $10/1k pp.
- **LlamaParse (LlamaIndex):** API, V2 con tiers (Fast 1 / Agentic 10 / Agentic Plus 45 créditos por pp; 1000 créditos = $1.25). Rápido; **débil en multi-columna y tablas merged** (interleaving de columnas que rompe retrieval RAG). Cloud-only (sensibilidad de datos).
- **Mistral OCR 3 (API):** $2/1k pp (-50% batch). Self-reported 96.6% tablas / 88.9% manuscrito; el pick de price/performance entre APIs.
- **Reducto / Extend / LandingAI / Chunkr:** premium/agénticos. **LandingAI ADE** destaca por **grounding a nivel de celda** (bbox a texto/tabla/figura) — best-in-class para citación/auditoría en RAG.
- _Source: https://procycons.com/en/blogs/pdf-data-extraction-benchmark/ · https://www.llamaindex.ai/blog/introducing-llamaparse-v2-simpler-better-cheaper · https://mistral.ai/news/mistral-ocr-3/ · https://landing.ai/agentic-document-extraction_

### OCR para escaneados — clásico vs VLM

- **Clásico (Tesseract + OCRmyPDF):** OCRmyPDF agrega una capa de texto al scan para que las librerías deterministas funcionen después. Tesseract anda bien en texto impreso limpio a buen DPI (~95%, gratis, offline, determinista) pero **falla en multi-columna (junta columnas), tablas (no asocia filas/columnas), manuscrito (~0), y scans degradados** (basura silenciosa).
- **VLM (el vuelco de 2025):** los VLMs end-to-end (imagen de página → Markdown/JSON estructurado en una pasada) desplazaron el pipeline clásico OCR→layout→parse como default para docs visualmente ricos o messy. **Hasta superan a modelos HTR dedicados en manuscrito moderno en inglés** (GPT-4o ~1.69% CER, primer VLM general que le gana a Transkribus). Pero más débiles en manuscrito no-inglés/histórico — relevante para español cursivo.
- _Source: https://parsli.co/blog/llm-ocr-vs-traditional-ocr · https://arxiv.org/pdf/2503.15195 · https://www.ubicloud.com/blog/end-to-end-ocr-with-vision-language-models_

### Lo que los VLMs todavía NO resuelven (fronteras reales)

- **Charts/figuras — extracción numérica precisa:** leer ≠ extraer datos exactos. ChartQAPro (1948 Qs) tope ~55.8%; subtarea más dura (stacked bars) ~59%. **No confíes en VLMs para valores exactos de gráficos densos sin validación.** _Source: https://arxiv.org/pdf/2504.05506_
- **Documentos largos — razonamiento cross-página:** MMLongBench-Doc (135 PDFs, avg 47.5 pp, 33% cross-page) → mejor LVLM (GPT-4o) solo **44.9% F1**. No tires 200 páginas en una sola llamada esperando razonamiento confiable. _Source: https://arxiv.org/abs/2407.01523_
- **Alucinación en datos densos:** el modo de falla dominante es **fabricar detalles** en scans pobres y tablas densas — no texto garbled. Open-source más susceptible que closed.
- **Reproducibilidad:** aun con temp=0 + seed, los endpoints hosted **no son deterministas** (rounding de batched-inference, drift de infra). Anthropic no expone seed; el seed de OpenAI es best-effort. Mitigar con: pin de versión, temp=0, JSON schema, y N-sample en campos críticos. _Source: https://www.keywordsai.co/blog/llm_consistency_2025_

### Benchmarks generales de document-understanding

| Benchmark | Mide | Estado |
|---|---|---|
| **DocVQA** | QA sobre doc de una página | Saturado (Qwen3-VL ~97%) |
| **OmniDocBench** | Parsing PDF (layout+reading-order+tablas, TEDS) | **Saturado** (>94%); pobre en docs financieros complejos |
| **ChartQAPro** | Parse + extracción + razonamiento de charts | Difícil (~56% tope) |
| **OCRBench v2** | Bilingüe EN/CN, 31 escenarios | Frontera viva; closed > open |
| **MMLongBench-Doc** | Docs largos multimodales, cross-página | **Lejos de resuelto** (~45%) |

_Patrón: los benchmarks de página única e impresa están saturados; la frontera real es contexto largo, charts duros, y subtareas finas de OCR._

### Patrones de producción recomendados (2025–2026) — transversales a cualquier PDF

1. **Salida estructurada con JSON Schema siempre** (responseSchema/structured outputs) — reduce varianza y fallos de parseo; con fallback regex.
2. **Grounding / bounding boxes** para trazabilidad — Gemini emite `box_2d` normalizado 0–1000; ancla cada campo a una región de página (auditoría + revisión humana).
3. **Routing híbrido** — texto nativo/OCR barato para lo limpio; reservar VLM para regiones visualmente complejas (tablas, charts, manuscrito, scans pobres). El multi-stage layout→crop→recognize (MinerU2.5, PaddleOCR-VL) es SOTA por encima del end-to-end puro.
4. **Loop agéntico verify/self-correct** para docs complejos — plan → extract → verify (cell-level en tablas) → correct (patrón LandingAI ADE / Gemini Agentic Vision).
5. **Docs largos = retrieval visual + VLM por página** — ColPali/ColQwen embeben screenshots de página, recuperan, y el VLM razona sobre las páginas recuperadas.
6. **Human-in-the-loop por confianza/costo-de-corrección** — enrutar campos de baja confianza a revisión; medir con correction-cost (KIEval), no exact-match.
7. **Capa de verificación determinista** para datos numéricos (la misma lección que tu prototipo de gastos diff=0).

### Cheatsheet de decisión (general)

- **PDF born-digital + tablas simples/ausentes + layout regular** → librería determinista (PyMuPDF/pypdfium2 + Camelot/pdfplumber). Gratis, instantáneo, determinista. **No traigas un LLM.**
- **Born-digital + tablas complejas (merged/borderless) o RAG** → Docling / Marker / Unstructured hi_res.
- **Escaneado limpio impreso** → OCRmyPDF+Tesseract, luego deterministas.
- **Escaneado degradado / manuscrito / layout variable / charts** → VLM (Gemini/GPT/Claude) o VLM especializado (MinerU/PaddleOCR-VL), con structured output + verificación.
- **Premium accuracy + grounding/auditoría** → Reducto / LandingAI ADE.

_Confianza: ALTA en la bifurcación born-digital/scan, ranking de librerías, mecánica lattice/stream, y que los benchmarks de página única están saturados (múltiples fuentes independientes + docs oficiales). MEDIA en scores exactos de tablas (single-source o forward-dated). BAJA en self-reported de vendors (Reducto, Mistral, LandingAI, Marker). GAP: faltan benchmarks independientes específicos de español/LatAm y de contratos/manuales/formularios (la mayoría de los neutrales son financieros/sustainability/engineering)._

---

## Capas de Reconciliación — Estado Actual vs Gaps (aplicado al codebase)

> Análisis sobre el código real del proyecto (no genérico). Conclusión central: la reconciliación determinista que la literatura recomienda como "capa no-negociable" **ya está construida** para cartolas. Lo que sigue distingue lo que existe de lo que sería genuinamente nuevo, para roadmap.

### Lo que ya existe

1. **Consistencia intra-cartola** — [`cartola_post_process.py`](../../../backend/app/integrations/cartola_post_process.py), pure functions sobre `CartolaCanonicalV1` en el momento de extracción:
   - **`detect_balance_mismatch`** ([:117](../../../backend/app/integrations/cartola_post_process.py#L117)) — el invariante fuerte: `sum(transactions) == closing − opening` (tolerancia 100 CLP). Cuando Gemini omite/alucina una línea, la aritmética deja de cerrar y dispara `BALANCE_MISMATCH`. **Esta es exactamente la "capa de reconciliación determinista" que el research recomienda — ya está.**
   - `detect_duplicate_lines` (DUPLICATE_LINE), `detect_zero_amounts` (ZERO_AMOUNT), `detect_period_mismatch` (PERIOD_MISMATCH, ratio ≥80%), `detect_large_amount_warnings` (LARGE_AMOUNT, >3× promedio histórico).
2. **Cuadratura vs fuente externa** — [`validate_cuadratura.py`](../../../bootstrap/validate_cuadratura.py): Beancount vs Laudus, diff=0 CLP exacto. Ground-truth independiente, pero **agregado y solo en fechas de corte**, no por cartola.

### Los gaps (puntos ciegos de lo actual)

El check actual valida los **extremos** (closing − opening) y el **agregado**. Eso deja tres puntos ciegos:

| Gap | Qué atrapa que hoy NO | Requisito | Dominio |
|---|---|---|---|
| **Saldo corrido por línea** (`saldo[i] == saldo[i-1] + monto[i]`) | *Cuál* línea está mal (no solo "algo no cierra"); + dos errores que hoy se compensan en la suma agregada | La cartola imprime columna de saldo por fila | Cartolas TC / cuenta corriente |
| **Continuidad inter-cartola** (`opening_mes == closing_mes_anterior`, misma cuenta) | Una cartola **entera** faltante/duplicada o hueco de período — invisible al check intra-cartola | Tener la cartola previa de la misma cuenta | Cross-document |
| **Invariantes no-aritméticos** (`qty × precio == valor`; `Σ holdings == total`) | Errores en cartolas de **inversión/custodios**, que no tienen opening/closing de caja del cual colgar la ecuación actual | Schema de holdings, no de movimientos | Cartolas de inversión |

### Insight de diseño

La reconciliación actual funciona **porque la cartola trae un invariante aritmético adentro** (opening/closing/movimientos que deben cerrar). Por eso el approach LLM es seguro en este dominio: el modelo puede alucinar, pero la aritmética lo delata. **Los PDFs generales (contratos, tablas sueltas) NO traen ese invariante** → ahí no hay reconciliación determinista posible y hay que apoyarse en grounding/confidence/revisión humana. Las cartolas son el caso fácil precisamente porque se auto-verifican; los gaps de arriba son extensiones del mismo principio (verificar fila-por-fila, mes-contra-mes, y con una ecuación distinta para inversión).

**Roadmap:** registrado en [`deferred-work.md`](../../implementation-artifacts/deferred-work.md) → "Deferred from: technical research — reconciliación cartolas (2026-06-10)".

---

## Integration Patterns Analysis — Cómo enchufar cada opción al pipeline

> "Integración" acá no es REST/microservicios genérico, sino la plomería real de extracción: cómo subís el PDF, sincrónico vs async, el contrato de datos (JSON schema), trazabilidad (grounding), confianza, reintentos, y governance (residencia de datos/PII). Esto es lo que cambia el costo de operación entre quedarte con Gemini-LLM o migrar a un Document AI dedicado.

### Subida del documento — cómo ingiere el PDF cada servicio

| Servicio | Modo | Límites | Retención |
|---|---|---|---|
| **Gemini** | File API (URI reusable) o inline base64 | File API 2 GB/archivo, 20 GB/proyecto; inline hasta 100 MB; PDF 50 MB / 1000 pp | File API **48h auto-delete** (TTL no configurable) |
| **OpenAI** | Files API (`purpose=user_data`) o base64 | 50 MB/archivo, 50 MB/request; extrae texto **+ imagen** por página (sube tokens) | No auto-expira (sin TTL oficial claro) |
| **Anthropic** | Files API (beta header) o base64 | 32 MB / **100 pp**; página = imagen + texto | **Retiene hasta que borres** (DELETE explícito) |
| **AWS Textract** | sync (1 página) o **async vía S3** | multipágina **obliga** S3 + async | JobId 7 días |
| **Azure DI/CU** | `urlSource` (Blob+SAS) o `base64Source` | async por defecto | resultId vía Operation-Location |
| **Google Doc AI** | online (40 MB) o **batch vía GCS** | >40 MB / multi-doc → batch | LRO → output en GCS |

_Source: https://ai.google.dev/gemini-api/docs/document-processing · https://developers.openai.com/api/docs/guides/file-inputs · https://docs.anthropic.com/en/docs/build-with-claude/files · https://docs.aws.amazon.com/textract/latest/dg/api-async.html_

### Sync vs async/batch — qué patrón te toca

- **LLMs (Gemini/GPT/Claude) en chat:** sincrónico para un doc dentro de los límites. El **batch es opcional** (Gemini Batch: JSONL, 24h, **-50% costo**, polling por `state` o webhooks `batch.succeeded`). Async = decisión de costo/throughput, no obligación.
- **Textract:** multipágina **obliga** async — `StartDocumentAnalysis` → JobId → **SNS/SQS** (AWS dice explícito: **no hagas polling de `Get`**, está throttleado; escuchá la cola) → `GetDocumentAnalysis` paginado (1000/page, NextToken).
- **Azure/Google:** patrón LRO — 202 + `Operation-Location`, GET hasta `succeeded`; Doc AI batch deja output en GCS.
- _Implicación para tu caso:_ con Gemini, una cartola de pocas páginas es **una llamada sincrónica simple** — sin infra de colas. Migrar a Textract te mete S3 + SNS + SQS solo para esperar el resultado. Es complejidad operativa real que hoy no tenés.
- _Source: https://ai.google.dev/gemini-api/docs/batch-api · https://docs.aws.amazon.com/textract/latest/dg/api-async.html_

### El contrato de datos — JSON Schema (la garantía varía MUCHO)

| Servicio | Garantía | Detalle clave |
|---|---|---|
| **OpenAI** strict | **Constrained decoding** — no puede omitir key, tipo errado ni enum inválido | Exige `additionalProperties:false` + **todas las props en `required`** (opcional = union con `null`). Límites subidos jul-2025 (5000 props, 5 niveles). Schema se cachea |
| **Anthropic** | JSON válido garantizado (GA nov-2025) vía `output_config.format` o strict tool-use | **Incompatible con citations → error 400.** No soporta `minimum/maximum`, regex compleja, recursión. PII fuera del schema (se cachea 24h) |
| **Gemini** `responseSchema` | **Solo sintáctico** — JSON bien formado, NO semánticamente correcto | Subconjunto de OpenAPI 3.0. `propertyOrdering` importa (2.0). Docs: validá antes de usar |
| **Azure CU / Google Doc AI / AWS BDA** | Schema **declarativo en lenguaje natural** (nombre + descripción = prompt) | Confianza/grounding opt-in (Azure `estimateFieldSourceAndConfidence`); confidence 0–1 nativa |

_Best practice transversal: `additionalProperties:false` en todo, enums para categóricos (tipo cuenta, signo), y campo-no-encontrado como `null` explícito (no omitir) — en strict mode de OpenAI/Claude omitir está prohibido. Versioná el schema (`schema_version` const) para reproducibilidad de auditoría y para aprovechar el cache._
_Source: https://developers.openai.com/api/docs/guides/structured-outputs · https://platform.claude.com/docs/en/build-with-claude/structured-outputs · https://ai.google.dev/gemini-api/docs/structured-output_

### Trazabilidad — grounding / bounding boxes

- **LLMs:** Gemini `box_2d` (0–1000 normalizado, + máscaras de segmentación en 2.5); OpenAI grid 0–999. **Caveat clave: el bbox del LLM es predicho, no geométrico** — la comunidad reporta coordenadas imprecisas en GPT/GPT-4V.
- **Document AI dedicadas:** Textract/Azure/Google/LandingAI devuelven **geometría determinista de la capa OCR** + confidence por campo — más confiable para auditoría. **LandingAI ADE da bbox a nivel de celda** (best-in-class para UI de revisión).
- _Patrón de audit trail:_ guardar `{value, bbox, page, confidence, schema_version}` por campo → UI que resalta la región fuente al lado del valor extraído.
- _Source: https://ai.google.dev/gemini-api/docs/image-understanding · https://docs.aws.amazon.com/textract/latest/dg/API_AnalyzeDocument.html · https://landing.ai/blog/breakthrough-table-extraction-with-dpt%E2%80%912-agentic-document-extraction-by-landingai_

### Confianza — el gap que más pesa para tu decisión

- **Document AI dedicadas exponen confidence calibrada por campo** (Textract 0–100, Azure/Google 0–1, BDA por campo). **Los LLMs generales (Gemini/GPT/Claude) NO.** Un LLM que dice "85% de confianza" casi nunca acierta el 85% real sin maquinaria de calibración.
- **Workarounds para fabricar confianza desde un LLM:** self-consistency (N muestras, frecuencia de acuerdo ≈ confianza; CISC baja ~40% las muestras necesarias), o logprobs (OpenAI los expone; Gemini/Claude casi no → self-consistency es más portable).
- **Patrón de umbral (guía Azure):** tres tiers — **alta → straight-through; media → revisión humana; baja → reject/reprocess**. Calibrar por campo con un piloto.
- _Implicación directa:_ tu pipeline Gemini **no tiene confidence nativa** — pero ya la suplís con **validadores deterministas cross-field** (BALANCE_MISMATCH = tu señal de "confianza"). Ese es exactamente el surrogate que la literatura recomienda para LLMs sin confidence. Un Document AI te daría confidence per-field "gratis", pero a costa de toda la complejidad de migración.
- _Source: https://arxiv.org/html/2502.06233v1 · https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/concept/accuracy-confidence_

### Reintentos — el loop validación→retry (y cuándo NO reintentar)

Tres clases de error que deben tratarse distinto (síntesis; tu deferred-work 9.5h ya tocó esto):

1. **Transitorios** (429/5xx/timeout) → backoff exponencial + jitter, honrar `Retry-After`. Lib: Tenacity.
2. **Corregibles por el LLM** (campo faltante, formato malo) → re-prompt con el error del validador como feedback, reintentos acotados (Instructor `max_retries`, norma ~3). Default de la lib es 0.
3. **Fallas deterministas de negocio** (BALANCE_MISMATCH por descuadre real del source) → **early-break, a cola humana.** Reintentar acá quema costo/latencia sin cambiar el resultado.
- _Esto valida tu ítem de deferred-work 9.5h ("retry sobre BALANCE_MISMATCH gasta 3× — early-break si el detail se repite"): es exactamente la clase 3. La literatura lo respalda._
- _Source: https://cookbook.openai.com/examples/how_to_handle_rate_limits · https://python.useinstructor.com/learning/validation/retry_mechanisms/_

### Idempotencia & confiabilidad

- **Textract `ClientRequestToken`** (7 días) → mismo token = mismo JobId, no re-corre, sin SNS duplicado: exactly-once de submission. **OpenAI** `Idempotency-Key` (mismatch → 409). SNS/SQS es at-least-once → el consumidor deduplica por JobId.
- _Para tu caso:_ la idempotencia importa para no re-procesar (ni re-cobrar) la misma cartola subida dos veces — hoy resoluble con un hash del archivo en el staging, sin necesidad de las primitivas del vendor.

### Governance — residencia de datos & PII (family office, datos sensibles)

- **Gemini — el fork crítico:** la **free AI Studio tier ENTRENA con tus datos ❌** (inaceptable para cartolas). El **paid Gemini Developer API NO entrena**; **Vertex AI** agrega residencia regional (EU) + VPC-SC/Private Service Connect → **para datos sensibles, Vertex es el camino, nunca AI Studio gratis.**
- **OpenAI:** no entrena (API); retención default **30 días** para abuse-monitoring (salvo ZDR enterprise); residencia no-US requiere aprobación.
- **Anthropic:** API nunca entrena; ZDR e ISO/SOC2; US-based (para residencia regional, vía Bedrock o Vertex).
- **Hyperscaler Document AI (mejor postura de soberanía):** Textract/Azure/Google corren **dentro de tu tenancy/región**, sin entrenar, con VPC endpoints, BAA/SOC/ISO.
- _Para Ary:_ si seguís con Gemini, **verificá que estás en paid API o Vertex, no en AI Studio gratis.** Y dado el contexto regulatorio del proyecto (Ley 19.628/21.719), la elección de región y el opt-out de training son decisiones de compliance — consultables con Yosef.
- _Source: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/data-residency · https://platform.claude.com/docs/en/manage-claude/api-and-data-retention · https://openai.com/business-data/_

### Lectura de integración para tu decisión de stack

- **Quedarte con Gemini-LLM** = integración más simple: una llamada sincrónica, schema JSON, tus validadores deterministas como confidence, retry de 3 clases. La complejidad que te falta es marginal (idempotencia por hash, governance Vertex).
- **Migrar a un Document AI dedicado** te daría confidence calibrada + grounding geométrico "gratis", pero te suma async/colas (Textract), o un schema declarativo nuevo (Azure CU / Google Custom Extractor) — y ninguno maneja cartola chilena out-of-the-box, así que igual entrenás/prompteás.
- **El híbrido sensato** (si querés grounding/confidence para auditoría sin migrar todo): Gemini para la interpretación semántica + un table-specialist o LandingAI ADE solo cuando necesites bbox a nivel de celda para revisión humana. Pero eso es optimización, no requisito.

_Confianza: ALTA en mecánica de APIs (file/async/idempotencia/schema), docs oficiales fetched jun-2026. ALTA en el gap de confidence (LLM no calibrada vs Document AI sí) y en la incompatibilidad citations⊥structured-outputs de Claude. MEDIA en números de rate-limit por tier (verificar en consola). GAP: TTL de OpenAI Files y adecuación de residencia Chile (Ley 21.719) sin cerrar — la segunda es decisión legal, no técnica._

---

## Architectural Patterns and Design — Patrones SOTA mapeados a tu sistema

> En vez de un catálogo genérico, esto mapea las arquitecturas de referencia de IDP en producción (AWS GenAI IDP Accelerator, Azure Foundry, Google Doc AI, paper Kungfu.ai) sobre tu pipeline real de cartolas. Hallazgo central: **tu arquitectura ya implementa el "espinazo canónico" de IDP**; lo que falta es marginal y, en su mayoría, justificadamente diferido.

### El espinazo canónico de IDP (convergencia de los 3 clouds)

Los tres clouds + vendors convergen en la misma descomposición de 6 etapas:

`ingest/validate → classify/route → extract → assess (confidence) → validate (reglas deterministas) → HITL (gated) → persist/export`

Decisión de diseño clave del AWS GenAI IDP Accelerator: **"assess" (confidence probabilística) y "validate" (reglas deterministas) son etapas SEPARADAS** — la validación "opera post-extracción" y permite enforcar restricciones "independientemente de la confianza del modelo". Extracción probabilística y validación determinista deliberadamente desacopladas.
_Source: https://github.com/aws-solutions-library-samples/accelerated-intelligent-document-processing-on-aws · https://aws.amazon.com/blogs/machine-learning/accelerate-intelligent-document-processing-with-generative-ai-on-aws/_

### Tu pipeline real vs el espinazo

| Etapa SOTA | Tu implementación | Estado |
|---|---|---|
| Ingest/validate | [`validate_upload_inputs`](../../../backend/app/api/v1/cartolas/service.py#L129) — magic bytes `%PDF`, size 20MB, content-type, cuenta registrada | ✅ Sólido (valida antes de gastar en Gemini) |
| Classify/route | account_type resuelto server-side → prompt condicional (sign convention pasivo/activo) | ✅ Equivalente |
| Extract | [`gemini_client.extract_pdf`](../../../backend/app/integrations/gemini_client.py#L302) — una llamada sync, `response_mime_type=json`, temp 0.1 | ✅ Simple y correcto |
| Provenance/canonical | server-side stamps ([service.py:243](../../../backend/app/api/v1/cartolas/service.py#L243)) — **NO confía** en source/model/extracted_at de Gemini, los sobrescribe | ✅ Higiene de procedencia ejemplar |
| Schema validation | `CartolaCanonicalV1.model_validate` (Pydantic) | ✅ Contrato tipado |
| Validate (determinista) | [`apply_post_process`](../../../backend/app/integrations/cartola_post_process.py) — BALANCE_MISMATCH etc., **desacoplado** de la extracción | ✅ Exactamente la separación AWS |
| HITL gated | staging JSON reviewable; UI de edición de período **diferida** (deferred-work 9.5h) | ⚠️ Substrato listo, UI pendiente |
| Persist/export | beancount import + [`validate_cuadratura`](../../../bootstrap/validate_cuadratura.py) vs Laudus | ✅ Reconciliación a system-of-record |

### Patrones SOTA que YA tenés (y que pagan a cualquier escala)

1. **Staging canónico** — [`write_staging_file`](../../../backend/app/api/v1/cartolas/service.py#L196) persiste `CartolaCanonicalV1` a `_staging/{batch_id}.cartola.json` antes de tocar el ledger. Es exactamente el patrón "normalized intermediate representation, reviewable before commit to system of record" (EIP canonical model + paper Kungfu.ai). Schema versionado (`schema_version: "1.0"`).
2. **Validación determinista que gatea la persistencia** — extracción probabilística → validadores deterministas → solo persiste limpio. La separación que AWS hace explícita como dos etapas.
3. **Retry acotado con la taxonomía de 3 clases** — [`process_upload_sync`](../../../backend/app/api/v1/cartolas/service.py#L254) hace exactamente lo que la literatura recomienda:
   - **Transitorio** (`GeminiExtractionError` / `BALANCE_MISMATCH`) → hasta 3 draws independientes, corta al primero limpio.
   - **Determinista de shape** (`ValidationError`) → **NO reintenta** (problema determinista).
   - **Falla de negocio persistente** (BALANCE_MISMATCH tras 3) → surfacea como warning, **no lo oculta** (best result obtained).
   - Esto es la taxonomía transient/correctable/deterministic-break, implementada antes de que el research la nombrara.
4. **Privacy-aware logging** — los logs registran path y batch_id, nunca el payload del PDF.

### Los gaps (en orden de valor, casi todos opcionales a tu escala)

1. **Tier-0 born-digital (la única palanca arquitectónica de fondo):** hoy mandás el PDF directo a Gemini-visión. Si las cartolas son born-digital (PDFs de portal bancario con capa de texto), el patrón "document-anchoring" (olmOCR) sugiere extraer el texto determinista primero y pasárselo a Gemini **junto** con el PDF — baja alucinación de dígitos y costo. Es la misma conclusión de la discusión costo-vs-confianza de arriba: no cambia el modelo, mejora la entrada. _Source: https://arxiv.org/html/2502.18443v1_
2. **Grounding / bbox ausente:** la llamada a Gemini no pide `box_2d`, así que el canonical no ancla cada valor a su región en la página. Para la UI de revisión humana (HITL) eso ayuda. Opcional; suma complejidad.
3. **HITL review UI:** el staging JSON es el substrato correcto, pero la UI de revisar/corregir está diferida (deferred-work 9.5h). Es el siguiente eslabón natural, no un rediseño.
4. **Idempotencia por hash:** re-subir la misma cartola crea un `batch_id` nuevo. SOTA sugiere hashear el contenido para re-ingesta idempotente. Menor a tu escala; ya anotado como no-process-safe en deferred-work.
5. **Job store in-memory:** process-local (OK en Render single-instance; un restart pierde jobs in-flight, aunque el staging file persiste). Ya conocido y diferido.

### El veredicto anti-over-engineering (importante)

El subagente lo marcó explícito: **para pocos usuarios y decenas-cientos de PDFs born-digital, una arquitectura síncrona simple es la decisión correcta.** Las máquinas pesadas de las arquitecturas de referencia —Step Functions, colas SQS/Celery, 3 microservicios, extracción dual-y-comparar (Azure), loops agénticos completos— **se justifican por throughput GPU-bound de alto volumen que vos no tenés.** No estás sub-construido: estás correctamente dimensionado.

Los dos patrones que pagan a cualquier escala —**staging canónico** y **validación-determinista-gatea-persistencia**— ya los tenés. El loop agéntico full (plan→extract→verify→correct de LandingAI/Reducto) gana en tablas complejas / multi-página / scans messy; para una cartola born-digital de tabla única donde un one-shot ya valida contra reglas deterministas, es over-engineering — y tu "retry acotado" ya es la versión correcta y barata de esa idea (corrección de 1 paso, no un agente).

_Confianza: ALTA en el espinazo canónico de 6 etapas (múltiples fuentes cloud primarias coinciden) y en la separación extract/validate (explícita en la referencia AWS). ALTA en que tu arquitectura ya lo implementa (leído del código). ALTA en el anti-over-engineering para bajo volumen (consenso + guía explícita FastAPI). MEDIA en el patrón staging-canónico como "well-architected" nombrado (se ensambla de idempotencia + provenance + grounding, ningún cloud lo nombra así). GAP: no existe un "Well-Architected lens" formal dedicado a IDP — la guía vive como solution accelerators y blogs, no como pilares WAF._

---

## Implementation Approaches and Technology Adoption

### Testing & evaluación de extracción no-determinista

El consenso 2025–2026 es un **modelo de dos pistas**, que mapea limpio a lo que ya tenés:

- **Unit tests deterministas (mockear el modelo)** — el grueso de CI. Testeás tu lógica de parsing/validación/schema con fixtures de JSON fijo, sin llamar a la API. Tus validadores deterministas ([cartola_post_process](../../../backend/app/integrations/cartola_post_process.py), testeados en `test_cartola_post_process.py`) y `test_gemini_client.py` (mockeado) ya viven acá. ✅
- **Evals (modelo real contra golden set)** — corren **out-of-band**, no en cada commit (cuestan plata y son lentos). Mides accuracy sobre un set held-out de cartolas etiquetadas. Tu `validate_cartolas_batch` + el smoke gate ≥90% son la semilla de esto. ✅
- _Source: https://www.techment.com/blogs/llm-regression-testing · https://www.comet.com/site/blog/llm-evaluation-frameworks/_

**Métricas que importan para extracción (KIE):**
- Field-level precision/recall/F1 + exact-match — baseline.
- **Correction-cost (KIEval)** — conceptualiza el error como **costo de corrección humana** = nº de ediciones (substitución/adición/deleción) para igualar el ground-truth. Mapea perfecto a cartolas: monto errado = 1 substitución; fila de transacción omitida = 1 adición. **Candidato a KPI principal** — alinea la métrica con el trabajo real del operador, mejor que F1 abstracto. _Source: https://arxiv.org/abs/2503.05488_
- Gateá sobre accuracy **agregada** (%), no pass/fail por-doc — exactamente tu regla del smoke gate ≥90% / la regla 80%.

**Tooling de eval para tu stack:** **DeepEval** es el mejor fit — integración nativa pytest, code-first Python, métricas custom (G-Eval). Pareás eso (gate en CI) con **Langfuse** (observabilidad + versionado de prompts) si querés trazar extracciones en prod. **No necesitás** una plataforma pesada (Braintrust) a tu escala.
_Source: https://www.deepeval.com/ · https://langfuse.com/_

### Adopción incremental / migración (tu ventaja: batch, no real-time)

- **Shadow mode** es "la técnica más importante en migración de modelos": corrés el approach nuevo en paralelo, **logueás pero no servís**, y comparás. Pero como tu pipeline **no es real-time**, tenés una ventaja enorme: **re-corrés cartolas históricas por el challenger offline** y diffeás contra el canonical guardado. Eso *es* tu shadow mode, casi gratis vs dual-serving en vivo.
- **Backfill/re-extracción:** cuando mejorás el pipeline, re-extraés el archivo y diffeás contra el `_staging/{batch_id}.cartola.json` guardado; gateás el swap en que la accuracy agregada no regresione.
- **Evitá big-bang:** la migración "falla catastróficamente" en sistemas probabilísticos porque "tu prompt estaba implícitamente afinado a las rarezas del modelo que reemplazás" — el prompt en [gemini_client](../../../backend/app/integrations/gemini_client.py#L91) (sign convention, cuotas, exclusiones) es exactamente eso.
- _Source: https://tianpan.co/ (Model Migration Playbook, 2026)_

### Optimización de costo (palancas concretas, multiplicativas)

1. **Batch API −50%** — extracción de cartolas no es real-time → win obvio (JSONL, 24h, expira 48h). Los docs ya referencian `gemini-3.5-flash` (tu default en 9.5h). _Source: https://ai.google.dev/gemini-api/docs/batch-api_
2. **Tier-0 born-digital skip** — la mayoría de cartolas son born-digital con capa de texto válida; extraerla con PyMuPDF es CPU-only, sub-segundo, ~gratis, y **preserva la estructura de tabla que la visión pierde**. Regla híbrida: extracción nativa → quality check → llamar a Gemini solo en páginas degradadas/escaneadas. _(Caveat: el blog PyMuPDF es vendor-authored — validá en tus cartolas chilenas.)_ _Source: https://pymupdf.io/blog/pdf-native-vs-vision-models-gemini-3 · https://arxiv.org/abs/2502.18443_
3. **Early-break en falla determinista** — no reintentar una extracción que falló un check determinista que el retry no puede arreglar. Tu "retry acotado" 9.5h es el instinto correcto; el ítem de deferred-work (early-break si BALANCE_MISMATCH se repite) lo cierra.
4. **Model right-sizing** — flash por defecto, escalar a pro solo en falla de validación / baja confianza (champion=flash, challenger-on-failure=pro).

### Riesgo: quedarse vs migrar / vendor lock-in

- **Riesgos reales de single-vendor (Gemini):** deprecación de modelo, cambios de pricing, **drift de accuracy en updates silenciosos**, prompt soldado a las rarezas de un vendor.
- **Mitigaciones dimensionadas para equipo chico (hacé estas, salteá el resto):**
  1. **Single point of contact** — todas las llamadas a Gemini por un módulo (ya lo tenés: [`GeminiClient`](../../../backend/app/integrations/gemini_client.py), NFR17). Esto hace un swap futuro *operativamente factible* sin reescribir callers. **Es el 80/20 — NO necesitás un LLM gateway/router completo.**
  2. **Golden-set regression gate antes de CUALQUIER upgrade de modelo** (incluido point-release silencioso) — tu mejor defensa contra drift. **Pineá la versión del modelo explícitamente** y tratá un auto-upgrade como cambio que debe pasar el gate.
  3. **Abstracción multi-provider = opcional, diferila.** Para un equipo chico con pipeline andando, abstracción single-vendor limpia + regression gate captura ~90% de la protección al ~10% del costo.
- **Cuándo NO migrar:** un pipeline probabilístico andando no se toca como un bump de librería. No migres sin un trigger concreto: una mejora de accuracy/costo **probada en tu golden set**, una deprecación anunciada, o un cambio de pricing. **La abstracción es el hedge; no tenés que ejercerlo.**
- _Source: https://www.truefoundry.com/blog/vendor-lock-in-prevention · https://tianpan.co/_

## Technical Research Recommendations

### Implementation Roadmap (orden por ROI, para equipo chico)

1. **Golden-set regression gate (DeepEval en pytest/CI)** — el cambio de mayor ROI. Gateá prompt-edits y model-bumps sobre field-accuracy + correction-cost. Convierte tu smoke gate manual en un gate automático y reproducible. **Prerequisito para tocar el prompt o subir de modelo con seguridad.**
2. **Batch API (−50%)** para la extracción no-real-time.
3. **Tier-0 born-digital skip** — validar primero en tus cartolas reales si son born-digital; si lo son, baja costo y alucinación de dígitos sin cambiar modelo.
4. **Cerrar el early-break** del deferred-work 9.5h (BALANCE_MISMATCH repetido → no reintentar).
5. **Reconciliación de fila por línea + continuidad inter-cartola** (deferred-work reconciliación 2026-06-10) — sube la confianza sin migrar nada.
6. **HITL review UI** (deferred-work 9.5h) — sobre el staging JSON existente; el siguiente eslabón natural del espinazo IDP.

### Technology Stack Recommendation

**Quedate con Gemini-flash.** El research no encontró nada que justifique reemplazar el stack:
- Gemini lidera price/performance en tablas densas y evita el modo de omisión de Claude.
- Ningún Document AI dedicado lee cartola chilena out-of-the-box; todos migraron a *extracción LLM con schema NL* — tu approach.
- La interpretación semántica (ABONO→retiro, excluir subtotales/cuotas futuras) es donde el LLM gana, y tu prompt ya la codifica.
- Migrar sumaría complejidad operativa (colas, schema nuevo) sin ganar accuracy.

**El stack objetivo no es "otro modelo" sino "el mismo modelo + las capas que ya empezaste":** regression gate + reconciliación más fina + HITL UI + batch/tier-0 para costo.

### Success Metrics / KPIs

- **Field-accuracy agregada** sobre golden set (gate ≥90%, consistente con tu smoke actual).
- **Correction-cost** (ediciones/cartola) como KPI de negocio — tendencia a la baja.
- **Tasa de BALANCE_MISMATCH residual** post-retry (proxy de extracción incompleta).
- **Costo/cartola** (tras batch + tier-0) y **% de cartolas que requieren revisión humana**.

_Confianza: ALTA en el playbook shadow→canary y en los levers de costo Gemini (docs oficiales). ALTA en two-track testing y posicionamiento de tooling (múltiples fuentes 2025-26). ALTA en "no migrar pipeline andando sin trigger" (fuentes explícitas). MEDIA en claims del blog PyMuPDF (vendor, validar en cartolas propias) y matrices de eval-tools (parcialmente self-published). GAP: no existe benchmark público de extracción español/cartola chilena — tu golden set interno es el único ground truth, lo que refuerza la recomendación nº1 (construí el gate)._

---

# Síntesis Técnica y Conclusiones — Extracción de PDFs Financieros Desestructurados

## Executive Summary

La pregunta que abrió esta investigación —"¿vale la pena reemplazar nuestro stack de extracción (Gemini-flash + prompting) por algo mejor?"— tiene una respuesta clara y respaldada por evidencia: **no, y entender por qué es más valioso que la respuesta misma.** El panorama 2025–2026 muestra una convergencia que invierte la intuición: los servicios "dedicados" de Document AI de los tres hyperscalers (AWS Bedrock Data Automation, Azure Content Understanding, Google Custom Extractor) **abandonaron sus modelos prebuilt clásicos y migraron a extracción LLM con schema en lenguaje natural** — es decir, migraron hacia donde el proyecto ya estaba. Ninguno de ellos lee una cartola chilena (español, RUT, CLP) out-of-the-box; todos requieren entrenar o promptear, igual que el approach actual. Y en el eje que más importa —tablas densas— Gemini lidera price/performance y evita el modo de falla de Claude (omitir tablas enteras, una pérdida silenciosa de datos).

El segundo hallazgo es que **la ventaja del approach actual no es el costo sino la confianza, y esa confianza ya está construida.** Las cartolas se auto-verifican: traen un invariante aritmético (`saldo_final − saldo_inicial = Σ movimientos`) que un LLM puede alucinar pero no puede burlar — el descuadre lo delata. El proyecto ya implementa ese check determinista (`detect_balance_mismatch`), la separación extract-probabilístico / validate-determinista que las arquitecturas de referencia (AWS GenAI IDP) recién nombraron, el staging canónico reviewable antes de comprometer al ledger, y un retry acotado con la taxonomía correcta de tres clases de error. Para una herramienta interna de bajo volumen, esto no está sub-construido: está correctamente dimensionado — las máquinas pesadas (colas, microservicios, loops agénticos) se justifican por throughput GPU que el proyecto no tiene.

La conclusión estratégica es que **el roadmap óptimo no es "otro modelo" sino "el mismo modelo + las capas que el proyecto ya empezó":** un golden-set regression gate (la única defensa real contra el drift de accuracy en upgrades de modelo, y el prerequisito para tocar el prompt con seguridad), reconciliación más fina (fila-por-línea, continuidad inter-cartola, e invariantes de inversión para el scope futuro de custodios), una HITL review UI sobre el staging existente, y optimización de costo de bajo esfuerzo (batch −50%, tier-0 born-digital). La única decisión que no es técnica sino legal —residencia de datos y opt-out de training para cartolas sensibles bajo Ley 21.719— se delega a Yosef, con el check accionable inmediato de confirmar que el proyecto corre en paid API / Vertex AI y nunca en la free AI Studio tier (que entrena con los datos).

**Key Technical Findings:**

- **Convergencia de stack:** los tres clouds migraron a extracción LLM con schema NL — el approach del proyecto es el destino de la industria, no un punto de partida a abandonar.
- **Ningún prebuilt sirve para cartola chilena:** AWS/Azure/Google bank-statement parsers son US/inglés-locked; cualquier ruta exige promptear/entrenar.
- **Gemini lidera tablas densas** (9.50/10 en benchmark independiente) y evita la omisión de tablas de Claude; valida la elección actual.
- **La confianza > el costo:** el valor durable de la reconciliación determinista (ya construida) es correctitud, no ahorro; sobrevive a presupuesto infinito.
- **PDF general ≠ cartola:** los documentos sin invariante aritmético (contratos, tablas sueltas) no admiten reconciliación determinista → ahí mandan grounding/confidence/HITL. Las cartolas son el caso fácil por auto-verificarse.
- **Arquitectura ya SOTA-alineada** para bajo volumen; los gaps son marginales o ya diferidos.
- **GAP estructural:** no existe benchmark público de cartola chilena/español — el golden set interno es el único ground truth.

**Technical Recommendations (top 5, por ROI):**

1. **Golden-set regression gate (DeepEval en pytest/CI)** sobre field-accuracy + correction-cost — máxima prioridad; prerequisito para upgrades de modelo y edits de prompt seguros.
2. **Quedarse con Gemini-flash** — no migrar un pipeline andando sin un trigger probado en el golden set; mantener `GeminiClient` como single point of contact (el hedge ya existe).
3. **Optimización de costo:** batch API (−50%) + validar tier-0 born-digital en cartolas reales.
4. **Reconciliación más fina** (fila-por-línea, inter-cartola, inversión) — sube confianza sin migrar nada; registrada en deferred-work.
5. **HITL review UI** sobre el staging canónico existente — siguiente eslabón natural del espinazo IDP.

## Table of Contents

El documento está organizado en seis bloques de análisis (arriba) más esta síntesis:

1. **Technology Stack Analysis** — el espectro de enfoques (pipeline tools / VLMs especializados / LLMs generales), LLMs cloud, Document AI dedicadas, benchmarks, y el veredicto preliminar.
2. **Análisis Ampliado — Lectura de PDF en General** — born-digital vs escaneado, librerías deterministas, lattice vs stream, ecosistema RAG/Markdown, OCR clásico vs VLM, fronteras no resueltas, y benchmarks generales.
3. **Capas de Reconciliación — Actual vs Gaps** — mapeo al código real; lo que existe vs lo que sería nuevo; el insight del invariante aritmético.
4. **Integration Patterns Analysis** — subida de archivos, sync/async/batch, JSON schema como contrato, grounding, confidence, retry, idempotencia, governance.
5. **Architectural Patterns and Design** — el espinazo canónico IDP mapeado al pipeline del proyecto; patrones ya implementados; gaps; veredicto anti-over-engineering.
6. **Implementation Approaches and Technology Adoption** — testing no-determinista, adopción incremental, optimización de costo, riesgo stay-vs-migrate, y las recomendaciones/roadmap.

## Veredicto de decisión (la pregunta original)

> **¿Reemplazar el stack de extracción? No.** El research no encontró una alternativa que justifique la migración. El approach LLM con schema + validación determinista es el destino de la industria, no un punto de partida. Lo que falta para producción robusta no es cambiar de modelo, son **capas encima del modelo** — la mayoría ya empezadas o registradas en deferred-work.

**Disparadores que SÍ justificarían reconsiderar (monitorear):**
- Extensión a cartolas de inversión/custodios con tablas que Gemini falle de forma medible en el golden set.
- Un cambio de pricing o deprecación de modelo anunciado por Google.
- Un requisito de compliance que exija confidence calibrada per-field o geometría de grounding determinista para auditoría (ahí un Document AI dedicado o LandingAI ADE entra como capa, no como reemplazo).

## Methodology & Source Verification

- **Enfoque:** 10 subagentes de investigación en paralelo con búsqueda web y verificación, sobre seis ejes; síntesis mapeada al código real del proyecto (`gemini_client.py`, `cartola_post_process.py`, `cartolas/service.py`, `validate_cuadratura.py`).
- **Período:** estado del arte 2025–2026 (varias fuentes forward-dated a mediados de 2026; preservadas con flag de confianza).
- **Verificación:** claims críticos validados contra docs oficiales de vendors; benchmarks marcados como independientes vs self-reported; niveles de confianza ALTA/MEDIA/BAJA explícitos por sección.
- **Fuentes primarias clave:** docs oficiales Gemini/OpenAI/Anthropic; AWS/Azure/Google Document AI; benchmarks OmniDocBench, FinTabNet, RD-TableBench, arXiv 2603.18652 (tablas), MMLongBench-Doc (docs largos), KIEval (arXiv 2503.05488); AWS GenAI IDP Accelerator; paper Kungfu.ai (arXiv 2605.18818); playbooks de migración y eval tooling (DeepEval, Langfuse, promptfoo).

### Limitaciones y confianza

- **GAP estructural (todas las secciones lo marcan):** no existe benchmark público independiente de extracción de cartola chilena / español-LatAm / custodios reales. Todos los benchmarks son sintéticos, de invoices, o US-tuned. → el golden set interno es el único ground truth, lo que es en sí la justificación de la recomendación nº1.
- **Confianza BAJA** en claims de marketing de vendors (Box, SprintHive, Reducto/LandingAI self-published, PyMuPDF blog) — marcados inline.
- **Confianza MEDIA** en decimales exactos de benchmarks forward-dated y en números de rate-limit por tier (verificar en consola).
- **Fuera de scope técnico:** adecuación de residencia de datos a Ley 21.719 — decisión legal (Yosef).

## Conclusion & Next Steps

El proyecto llegó a esta investigación con la hipótesis de que quizás había algo mejor que Gemini-flash para leer cartolas. La evidencia dice que la pregunta correcta no era "¿qué modelo?" sino "¿qué capas encima del modelo?" — y que varias de esas capas (validación determinista, staging canónico, retry acotado, single point of contact) ya están construidas y bien dimensionadas. El siguiente paso de mayor ROI es **convertir el smoke gate manual en un golden-set regression gate automático**, que desbloquea con seguridad todo lo demás (upgrades de modelo, mejoras de prompt, optimización de costo). El roadmap completo, ordenado por ROI y enlazado a los ítems de deferred-work, está en la sección de Implementación.

---

**Fecha de completación:** 2026-06-10
**Período de investigación:** estado del arte técnico 2025–2026
**Verificación de fuentes:** todos los claims citados; confianza explícita por sección
**Nivel de confianza global:** ALTO en specs/arquitectura/veredicto; MEDIO en decimales de benchmarks; el gap de ground-truth chileno es el límite reconocido

_Este documento sirve como referencia técnica autoritativa sobre extracción de PDFs financieros desestructurados para el proyecto family-office-eag, y fundamenta la decisión de no reemplazar el stack actual sino profundizar las capas de confianza, costo y revisión sobre él._
