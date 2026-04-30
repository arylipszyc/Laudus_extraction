---
title: Research de viabilidad — Beancount como motor accounting de LAUDUS
author: Mary (BMAD Business Analyst)
date: 2026-04-30
audience: Ary (product owner) — vía Moishe (orchestrator)
type: viability research (no implementation plan)
status: complete
artifact_for: decision pivot total / híbrido / status quo
sources: official only (beancount.github.io/docs, github.com/beancount/*, beancount.io)
---

# Research — Beancount como motor accounting de LAUDUS

## Pregunta de fondo

No es *"¿Beancount es buena tecnología?"*. Es: **¿valió la pena haber construido un motor accounting a mano cuando existe uno open source maduro y específico — y, dado que ya construimos parte, el costo del pivot ahora es menor que el costo de seguir?**

Spoiler: la pregunta tiene dos respuestas distintas según cómo se mire LAUDUS. Mantengo el spoiler para la sección 6.

---

## 1. Qué es Beancount realmente

**Beancount open source (Martin Blais, GPL-2.0)** es un sistema *plain-text accounting*: el "DB" son archivos `.beancount` versionados en git, donde cada transacción se escribe como una directiva double-entry textual. El código carga los archivos en memoria, valida con `bean-check`, consulta con `bean-query` (BQL — un SQL-like con `SELECT/FROM/WHERE` + statements especializados `BALANCES` y `JOURNAL`), y reporta vía `bean-report`. Multi-currency es first-class. La estructura de cuentas es un árbol con **5 raíces fijas: Assets, Liabilities, Equity, Income, Expenses**, separadas por `:` (ej: `Assets:BCI:CtaCorriente`).

**Salud del proyecto (verificado en repo oficial 2026-04-30):** release `3.2.2` el 2026-04-30 mismo, soporte Python 3.14 enero 2026, adaptador DuckDB abril 2026, ~6.4k commits, 5.5k stars. Activo. **Bus factor real = 1**: Martin Blais figura como autor único; no hay co-maintainers visibles. Para uso productivo se asume ese riesgo.

**Tooling oficial:**
- `bean-check` — validación de integridad double-entry.
- `bean-query` / `beanquery` — BQL interactivo.
- **Fava** (`github.com/beancount/fava`) — UI web oficial. Auto-genera Income Statement, Balance Sheet, Trial Balance, Net Worth chart, breakdowns por cuenta, drill-down click-a-cuenta. Activo, separado del core. **No tiene auth ni multi-user nativo** — se pone detrás de un reverse proxy con basic auth si hace falta.
- `smart_importer` — hooks de ML para sugerir categorías sobre transacciones **ya extraídas**. **No parsea PDF.** Trabaja sobre CSV/OFX que ya tienen estructura.

**Distinción crítica — Beancount.io es OTRO producto.** Es un servicio comercial separado (hosted Fava + AI bookkeeping + apps móviles, $14.99–$499.99/mes). No está oficialmente asociado a Martin Blais. Para este research evalúo **Beancount OSS self-hosted**, que es lo que tiene sentido para un family office privado. Beancount.io aparece como referencia comparada cuando suma valor.

---

## 2. Qué de LAUDUS cubriría Beancount nativamente

Mapeo concreto, story por story:

| LAUDUS | Beancount equivalente | Veredicto |
|---|---|---|
| **Plan de cuentas (293 cuentas, hoja `PlanCuentas` con `account_number, account_name, cat1, cat2, cat3`)** | Árbol de Accounts bajo 5 raíces. Mapeo no es 1:1 — Beancount **rechaza** un plan que no esté bajo Assets/Liabilities/Equity/Income/Expenses. Una cuenta chilena `1101 Caja` se traduce a `Assets:Caja`; `5101 Sueldos` a `Expenses:Sueldos`. El `account_number` se preserva como **metadata** (`code:`) en la directiva `open`. Cat1/2/3 ya son el árbol — quedan codificados en el path. | Mapeable, pero **requiere reclasificar manualmente las 293 cuentas a una de las 5 raíces.** No es derivable automáticamente desde el shape actual (`account_type` está NULL para todas en Supabase). |
| **Bank accounts (47 cuentas en hoja `Bancos`, 4 tipos: tarjeta_credito / cta_corriente / linea_credito / cta_inversiones; CLP+USD)** | Cada bank account es una `Account` propia (`Assets:Banco:BCI:CtaCorriente:Eduardo`, `Liabilities:TC:Visa:Eduardo`). Multi-currency con commodity declarada (`CLP`, `USD`). Tarjetas de crédito como `Liabilities` es semánticamente correcto — corrige la práctica actual de tratarlas como gasto. | Cubierto nativamente y **mejor modelado** que el approach actual (que necesita la tabla `bank_accounts` separada precisamente porque el plan no distinguía). |
| **Sync Sheets→DB (Epic 2: Balance Sheet + Ledger desde Laudus ERP, dedupe por PK, incremental, backfill 2021)** | Beancount no tiene "sync" — su input son archivos `.beancount` versionados en git. El Laudus ERP seguiría siendo source of truth fiscal; necesitamos un *importer* custom que tome la salida del ERP y emita directivas Beancount. Dedupe se logra con metadata `id:` única por entry. | Reemplazable, pero **el importer Laudus→Beancount es código nuevo a escribir** — no existe. Y la operación pasa de "DB que se sincroniza" a "archivos que se generan + commitean en git". Implicancia operativa: Eduardo nunca tocará un `.beancount`, pero Ary sí cuando haga ajustes. |
| **Dashboards (Epic 3: balance, ingresos/gastos, estado resultado, variación patrimonial, filtros por entidad/fecha, drill-down)** | **Fava cubre todo esto out-of-the-box.** Income Statement y Balance Sheet auto-generados, filter bar por cuenta/fecha/etiqueta, drill-down click-a-cuenta hasta journal level. Net Worth chart. Multi-entidad se modela con sub-accounts (`Assets:Eduardo:...`, `Assets:Jocelyn:...`) o archivos separados con `include`. | **Cubierto al 80–90%.** Lo que se pierde: el look específico que diseñamos en Recharts y el reporte HTML semanal que mandás a Eduardo (Fava no lo genera, es interactivo no estático). Lo que se gana: 4 vistas que ya teníamos + Trial Balance + Holdings + Net Worth chart "gratis". |
| **Audit log + RBAC (Stories 1.4, 1.5)** | **No hay equivalente nativo.** El "audit log" en Beancount es git history sobre los `.beancount`. RBAC no existe — Fava es single-user. Se delega al sistema operativo / reverse proxy / VPN. | **Gap concreto.** En el approach actual tenemos `get_current_user()` + audit middleware en cada endpoint. Para Eduardo (read-only) + Ary (read-write) + Abel, hay que poner Fava detrás de nginx con basic auth o OAuth proxy. Funciona, pero pierde granularidad por mutación. |
| **Reporte semanal HTML a Eduardo (viernes)** | BQL puede emitir tablas; `bean-report` produce salidas. No hay "generar HTML semanal y mandarlo por mail" out-of-the-box. | Custom code igual. |

**Subtotal honesto:** Beancount + Fava cubren **el corazón accounting + dashboards + multi-currency + drill-down**. Lo que NO cubren: ingestión PDF, reporte HTML semanal, auth multi-user, sync con un ERP externo.

---

## 3. Qué NO cubre Beancount (y queda como custom)

El insight de Ary es correcto: **la diferenciación de LAUDUS es la ingestión de cartolas PDF con Gemini (Story 4.1)**. Eso no es accounting — es OCR + extracción estructurada + categorización LLM.

- **PDF→transacciones:** Beancount no lo tiene. `smart_importer` **no** parsea PDF (verificado en doc oficial: "only works by appending onto incomplete single-legged postings"). Hay que construir un importer custom que tome PDF → Gemini → directivas `.beancount`. **Esto es exactamente el código que ya estás por escribir en Story 4.1**, solo que el output cambia de filas Supabase a líneas en un `.beancount`.
- **Categorización con feedback loop (FR31, 30 correcciones → categoría primaria):** `smart_importer` cubre la idea de aprender de correcciones, pero su modelo de aprendizaje es probabilístico genérico, no un threshold fijo de 30. Se adapta o se reescribe.
- **Reporte HTML semanal a Eduardo:** custom igual, en cualquier escenario.
- **Multi-user con RBAC granular:** custom, vía proxy o capa propia sobre Fava.
- **Validación de balance opening + Σ = closing antes de persistir:** Beancount ya valida double-entry rigurosamente — si cuadrás contra una `balance` directive en la fecha de cierre, te avisa. **Esto sería más fuerte que la validación actual**, no menos.

---

## 4. Tres approaches comparados

### a) Status quo — seguir construyendo Epic 4–5+ sobre el motor propio

- *Gana:* velocidad inmediata, cero re-trabajo Phase 2, control total UI.
- *Pierde:* seguís codeando a mano lo que Beancount hace gratis (BQL, validación double-entry, Fava). Cada vista nueva = React + endpoint + service + tests.
- *Esfuerzo:* la trayectoria conocida.

### b) Pivot total — Beancount source of truth; Sheets/Supabase desaparecen

- *Gana:* sistema accounting probado, validación double-entry, Fava cubre dashboards + extras, BQL ad-hoc, audit = git.
- *Pierde:* Phase 2 Supabase (Story 4.0 entera) se descarta. Sync Laudus→Sheets se reemplaza por importer Laudus→Beancount. UI React → Fava + extensiones.
- *Esfuerzo:* **meses, no semanas.** Reclasificar 293 cuentas a 5 raíces, escribir importer Laudus, importer PDF→Beancount, montar Fava + auth, replicar reporte HTML, migrar histórico 2021.

### c) Híbrido — tres variantes

**c1) Beancount engine de validación/reporting batch; el stack actual mantiene persistencia + UI + ingestión.** Snapshot Supabase+Sheets → `.beancount` → `bean-check` + BQL.
- *Gana:* validación rigurosa sin tocar el stack; BQL ad-hoc.
- *Pierde:* dos sources-of-truth, riesgo de drift.
- *Esfuerzo:* bajo-medio. Phase 2 sigue como está.

**c2) Beancount engine + UI custom + ingestión PDF custom.** Supabase → `.beancount` versionados; el frontend React sigue, llama a un wrapper que parsea Beancount.
- *Gana:* unifica source of truth.
- *Pierde:* tenés que escribir un loader Beancount→React API. **Es reinventar Fava sin adoptarlo.**
- *Esfuerzo:* alto. Lo peor de ambos mundos.

**c3) Híbrido invertido — Fava + extensiones.** Beancount + Fava de base para dashboards e investigación; lo custom es el importer PDF (que iba a ser custom igual), el reporte HTML semanal y el auth proxy multi-user.
- *Gana:* máximo apalancamiento OSS, mínimo código custom.
- *Pierde:* dependencia de Fava, se pierden los dashboards Recharts ya hechos.
- *Esfuerzo:* medio. Más que c1, mucho menos que pivot total.

---

## 5. Riesgos del pivot

- **Costo hundido Phase 2.** Story 4.0 cerró hace 3 días (commit `4eb7f78`). En **pivot total y c2/c3**, ese trabajo se descarta casi entero (schema Supabase, SupabaseRepository, sync plan_de_cuentas, módulos plan_de_cuentas y bank_accounts). En **c1**, sobrevive.
- **Bus factor 1.** Martin Blais es el único maintainer público. Si él pausa el proyecto, te quedás vos parchando. La salida posible es leer/escribir vos mismo el formato `.beancount` (es texto, parser propio en una tarde) — el lock-in es bajo precisamente por ser plain-text.
- **Curva de aprendizaje contable para Ary.** Beancount usa vocabulary contable más estricto que el actual: "postings", "directives `open` / `balance` / `pad`", "commodities", "ambiguous boolean". Sos product owner, no contador formal — vas a tener que internalizar más teoría. Contrapeso: el rigor te protege de errores que el approach actual no detecta.
- **Lock-in operativo.** Eduardo no se entera (sigue recibiendo HTML por viernes). Ary sí — pasa de "edito en Sheets" a "edito en `.beancount` y commiteo".
- **Multi-entidad + multi-currency.** Beancount los soporta, pero el modelado decide muchas cosas downstream. Si lo armás mal al inicio, refactor caro.

---

## 6. Recomendación + confianza

**Recomendación: Híbrido c3 (Fava + extensiones). Confianza: media-alta.**

Razonamiento:
1. **Pivot total no se justifica** mientras sigamos en stage early de Phase 2. El descarte del trabajo Phase 2 ya hecho (Story 4.0) es absorbible, pero el costo de migrar histórico, montar importer Laudus, y reentrenar tu mental model es alto y los beneficios marginales sobre c3 son chicos.
2. **Status quo es defendible solo si valorás el control total de UI por encima de ahorrar meses de código.** Para un family office privado de 3 usuarios, esa valoración es difícil de sostener: cada feature accounting que escribís a mano, Fava ya la tiene mejor.
3. **c3 es el sweet spot** porque: (a) la única pieza que era diferenciadora de LAUDUS — la ingestión PDF con Gemini — sigue siendo custom igual y no cambia; (b) los dashboards "gratis" de Fava reemplazan 4 stories de Epic 3 que ya hiciste pero que no son tu ventaja competitiva; (c) Beancount valida double-entry rigurosamente, lo que te elimina una clase entera de bugs futuros que el approach actual no detecta. El costo de Story 4.0 que se descarta es real pero acotado.

**Si la respuesta de Ary es "no me convence c3, dame otra opción":** la siguiente mejor es **c1 (Beancount como engine de validación/reporting batch)** — preserva todo el Phase 2 y solo agrega rigor.

**Top 3 incógnitas que erosionan mi confianza:**
1. **¿Cuánta visibilidad/customización necesita el reporte HTML semanal a Eduardo?** Si es muy específico y vos lo querés interactivo en algún momento, Fava puede no alcanzar y volvés a UI custom.
2. **¿Qué tan rígido es el plan de cuentas chileno actual de 293 cuentas frente a las 5 raíces de Beancount?** El mapeo es plausible pero no lo verifiqué cuenta por cuenta. Hay riesgo de cuentas que no caen limpias en Assets/Liabilities/Equity/Income/Expenses (típicamente cuentas de orden, contingencias, transferencias entre entidades). Una sesión de 1–2h con el plan real lo aclara.
3. **¿Auth multi-user vía reverse proxy es aceptable para Eduardo + Abel?** Si necesitás roles más finos que "todos ven todo", c3 requiere capa custom y se acerca más a c2 en costo.

Esas tres son lo que profundizaría antes de aprobar el pivot.

---

## Apéndice — referencias verificadas

- Beancount docs: https://beancount.github.io/docs/ — TOC con Language Syntax, Double Entry, Options, Query Language, Importing External Data, Plugins.
- Beancount repo: https://github.com/beancount/beancount — release 3.2.2 (2026-04-30), GPL-2.0, autor Martin Blais.
- Fava: https://github.com/beancount/fava + https://beancount.github.io/fava/ — UI oficial, Income Statement / Balance Sheet / Trial Balance / Net Worth / drill-down auto-generados.
- smart_importer: https://github.com/beancount/smart_importer — v1.2 (2025-10-17), ML hooks post-extracción; **no parsea PDF**.
- BQL: https://beancount.github.io/docs/beancount_query_language/ — SQL-like, SELECT/FROM/WHERE + BALANCES / JOURNAL specialized statements.
- Beancount.io (comercial, separado): https://beancount.io/ — hosted Fava + AI bookkeeping, $14.99–$499.99/mes. No oficialmente asociado a Martin Blais.
