---
thread_id: winston-x-moishe-2026-04-30
participants: [winston, moishe]
topic: Arquitectura concreta de c4 — Beancount engine + Fava (contador) + LAUDUS frontend (family) + importers (Laudus ERP, PDFs cartolas)
last_turn_by: moishe
awaiting: nadie
status: closed
---

# Coordinación Winston ↔ Moishe — Arquitectura c4 LAUDUS (2026-04-30)

## Propósito

Ary aprobó pivotar el core de LAUDUS hacia un híbrido nuevo (que llamamos **c4**, no estaba en el research original de Mary): **Beancount como motor accounting + dos UIs especializadas** (Fava para el contador, LAUDUS frontend actual para family). Necesitamos arquitectura concreta para que Bob (SM) pueda preparar las stories del epic de migración con context completo.

## Protocolo

Este archivo sigue el protocolo en `c:/dev/bmad-workspace/_bmad/docs/coordination-protocol.md`.
Reglas clave: append-only · leer todo posterior a tu última entrada antes de responder · no meter artefactos finales acá (la arquitectura formal va a `_bmad-output/planning-artifacts/architecture-c4.md` o equivalente) · actualizar `last_turn_by` y `awaiting` en frontmatter al escribir.

## Estado actual acordado

**Lecturas obligatorias antes de empezar (vos mismo, no esperés que yo te las resuma):**

- Research de Mary: `_bmad-output/planning-artifacts/research-beancount-pivot-2026-04-30.md` (tiene el análisis técnico de Beancount — c4 es una variante posterior que recoge los hallazgos de Mary y los reconfigura).
- Coord file de Mary: `_bmad-output/coordination/mary-x-moishe-beancount-pivot-2026-04-30.md` (el thread completo donde nació la decisión).
- Architecture actual (pre-pivot): `_bmad-output/planning-artifacts/architecture.md`
- PRD: `_bmad-output/planning-artifacts/prd.md`
- Epics: `_bmad-output/planning-artifacts/epics.md`
- Sprint status: `_bmad-output/implementation-artifacts/sprint-status.yaml`
- Stories implementadas (lo que ya existe y NO se rompe): `_bmad-output/implementation-artifacts/{1-1, 1-2, 1-3, 1-4, 1-5, 2-1, 2-2, 2-3, 3-1, 3-2, 3-3, 3-4, 4-0}-*.md`
- Spike validado de Beancount: `_bmad-output/spike-beancount/` (script `generate.py` + archivo `eag.beancount` con 12 transacciones reales del ledger_eag mapeadas a 5 raíces Beancount, multi-entidad EAG + 4 hermanas Avayu — bean-check pasó limpio, Fava sirve correctamente).

**Decisiones ya tomadas — NO las cuestiones, son input fijo:**

- **Beancount OSS** (no Beancount.io) como source of truth. Plain-text accounting.
- **Fava** se mantiene como UI del contador (workflow profesional: import, conciliar, validar, BQL). El "look anticuado" de Fava es OK porque no es la UI que ven los usuarios family.
- **LAUDUS frontend actual (React/Vite + Recharts) se preserva sin cambios visuales** como UI para family (Ary, Eduardo, Abel). La diferenciación visual + drill-down con charts integrados que Ary valora ya está construida — es Epic 3.
- **Una sola fuente de verdad: archivos `.beancount` versionados** (probablemente en repo separado — definir).
- **Backend FastAPI thin** carga el ledger Beancount en memoria, expone JSON al frontend LAUDUS via queries BQL. Reemplaza la query directa a Supabase.
- **`pipeline/sync.py` actual** se reformula como importer Laudus ERP → directivas `.beancount` (reusa la auth + paginación existente; cambia solo el output).
- **Story 4.1 (PDF + Gemini)** se reformula como **clase beangulp** — encaja perfecto con su modelo "documento externo → directivas". Gemini va en `extract()`. Ya verificado que beangulp es la salida natural.
- **Story 4.1 se splitea en 4.1a (extracción → JSON canónico) + 4.1b (JSON → directivas vía beangulp)** para poder paralelizar.

**Verificaciones empíricas que ya hice (no las repitas, pero apoyate en ellas):**

1. **No existe importer Laudus en la comunidad Beancount** (verificado: search en awesome-beancount + GitHub). Hay que escribirlo. La buena noticia: `pipeline/sync.py` ya hace el 80% (pull API Laudus + mapeo); solo cambia el output target.
2. **Concurrencia Fava + thin API: no es problema.** Fava usa `watchfiles` para reload automático cuando archivo cambia. Thin API re-lee on-demand. Cada proceso maneja su copia en memoria. Sin locks de OS. (Caveat: file systems de red en Windows pueden tener watcher flaky — irrelevante para Render/Linux deploy.)
3. **Spike Fava local funcionó:** 12 transacciones reales, multi-entidad, 16 cuentas mapeadas a 5 raíces Beancount, bean-check OK, Fava sirvió en localhost:5000. Ary recorrió la UI; le sirve para contador.
4. **Plan de cuentas chileno se reclasifica** (no migra 1:1) a las 5 raíces de Beancount. Mapeo validado en spike: ACTIVO EAG → Assets:EAG, GASTOS → Expenses:EAG, DISPONIBLE JOCELYN → Assets:Jocelyn, etc. El `account_number` Laudus se preserva como metadata `code:` en cada `open` directive.

**Constraints estructurales del proyecto (de BOND/MEMORY):**

- Family office privado, 3 usuarios family (Ary, Eduardo, Abel) + 1 contador (rol designado, persona pendiente — Ary tiene que asignarlo).
- Reporte semanal HTML a Eduardo cada viernes.
- Stack actual: FastAPI + React/Vite + Render para deploy (laudus-frontend.onrender.com + laudus-backend.onrender.com). Supabase recién agregado en Phase 2 (Story 4.0 done) — en c4 puede quedar obsoleto, evaluar.
- Story 4.0 ya cerrada (Supabase Phase 2 con plan_de_cuentas + bank_accounts) — el trabajo se descarta en c4 o se reformula. Marcar el costo hundido honestamente.

---

## Thread

### [Moishe → Winston, 2026-04-30 16:00]

Winston, te necesito para diseñar la arquitectura concreta de c4. **Esto NO es revisar la viabilidad** (eso lo hizo Mary y está cerrado) — es traducir la decisión a un diseño implementable que Bob (SM) pueda usar como input para preparar stories del epic de migración.

---

**Qué tenés que producir:**

Un documento `_bmad-output/planning-artifacts/architecture-c4.md` (puede convivir con `architecture.md` actual o reemplazarlo — vos definís según prolijidad) que cubra:

**1. Topología del sistema en c4.**

- Diagrama / descripción de los componentes y cómo se comunican:
  - Repo del código (FastAPI backend + React frontend) — el actual.
  - Repo o submódulo de los archivos `.beancount` — ¿separado? ¿dentro del repo principal? Trade-offs.
  - Fava server — ¿deploy en Render como servicio separado? ¿solo se usa local por el contador via SSH/VPN/web?
  - Backend thin (FastAPI) — endpoints que carga el ledger y responde queries BQL → JSON.
  - Frontend LAUDUS — consume backend thin (vs hoy consume directo Supabase + Sheets).
  - Importer Laudus ERP → archivos `.beancount` (cron schedule? on-demand?).
  - Importer cartolas PDF (beangulp + Gemini) → archivos `.beancount`.
- Cómo conviven Fava editando el `.beancount` en simultáneo con el importer escribiendo nuevas entries y el thin API leyendo. La verificación de no-conflict ya está hecha (`watchfiles` + read-only en thin API), pero acá definís el flujo concreto: ¿qué archivo es `main.beancount`? ¿hay `includes` por entidad / por año / por banco? ¿quién appendea dónde? ¿hay un branch `imports/` que mergea a `main` después de validar? Decidí esto.

**2. Esquema concreto de directivas Beancount para LAUDUS.**

- **Cuentas:** estructura del árbol completo. ¿Las 293 cuentas del plan se mapean automáticamente desde Categoria1/2/3 del Sheet? ¿Qué hace el importer cuando aparece una cuenta nueva?
- **Multi-entidad (EAG + 4 hermanas Avayu):** ¿se modela como sub-cuenta (`Assets:EAG:...` vs `Assets:Jocelyn:...`) o con archivos separados con `include`? Trade-offs para reportería.
- **Multi-currency (CLP + USD para tarjetas):** ¿operating_currency = CLP? ¿USD se modela como commodity con price directives? ¿quién pricea (Banco Central API)?
- **Bank accounts (47 cuentas en hoja `Bancos`):** ¿cómo se modelan los 4 tipos (cta_corriente, cta_inversiones, tarjeta_credito, linea_credito)? ¿Las tarjetas son `Liabilities:TC:...` (correcto) o se preserva el approach actual?
- **Metadata Laudus preservada:** `account_number`, `journalentryid`, `journalentrynumber` para traceability — ¿en qué campos van?
- **Equity inicial:** los saldos iniciales 2021 que en el ledger actual aparecen como entries del JE 140 — ¿se modelan con `pad` + `balance` o se importan como Equity:Opening-Balances?
- **Plugins necesarios:** ¿`beancount.plugins.auto_accounts`? ¿`beancount.plugins.implicit_prices`? ¿otros?

**3. Contrato del importer Laudus ERP (4.x reformulado / nuevo epic).**

- Reusa qué del `pipeline/sync.py` actual (auth, retry, paginación) y qué se reescribe.
- Schedule: ¿cron diario/horario? ¿on-demand? ¿webhooks Laudus si los hay?
- Idempotencia: dedupe por `journalentryid` Laudus → metadata `id:` en directiva.
- Manejo de cuentas nuevas (alta automática vs review manual).
- Output: ¿appendea a `main.beancount`? ¿escribe a `imports/2026/04.beancount` y se incluye? ¿commit + push automático al repo?
- Validación post-import (`bean-check` automático, fail si rompe).

**4. Contrato del importer PDF (Story 4.1 reformulada).**

- **4.1a — Extracción → JSON canónico:** shape del JSON que devuelve Gemini parseando un PDF de cartola. Definí el shape concreto que el frontend de upload va a consumir y que 4.1b va a transformar a directivas. **Importante:** este shape lo va a usar Bob para preparar 4.1a antes de que vos termines de definir todo el resto — necesito que lo dejes claro temprano para desbloquear paralelismo.
- **4.1b — JSON → directivas vía beangulp:** clase beangulp con `identify()` (¿es cartola Banco Chile / BCI / Edwards / Santander?) + `extract()` (toma el JSON canónico, mapea a directivas, asigna cuenta destino con la lógica de categorización del PRD original).
- **Categorización con feedback loop (FR31):** ¿se mantiene el threshold de 30 correcciones del PRD original? ¿dónde vive el log de correcciones (DB chica? archivo separado)? ¿`smart_importer` ayuda?

**5. Backend FastAPI thin — diseño de endpoints.**

- Cómo se carga el ledger en memoria. Caching strategy (¿re-lee cada request? ¿watcher tipo Fava? ¿LRU con TTL?).
- Endpoints que reemplazan los actuales que hoy consultan Supabase/Sheets — mapeo 1:1 o reorganización.
- Auth + RBAC (Stories 1.4, 1.5) — ¿se preserva la implementación actual sin cambios? ¿la audit log sigue en su tabla actual o se mueve a git history del repo `.beancount`?

**6. Deployment en Render.**

- Servicios necesarios: backend, frontend, ¿Fava? ¿importer Laudus como worker / cron?
- Storage de los archivos `.beancount`: ¿Render disk? ¿GitHub repo + clone on deploy? ¿S3?
- Secrets nuevos / removidos.

**7. Plan de migración (high-level — el detail va en epic stories).**

- Fases gruesas: bootstrap (genero `main.beancount` con histórico desde Laudus + el inicial 2021), wiring del thin API, switch del frontend, deprecate Supabase, deprecate Sheets como source of truth (o conservar como historical archive).
- Riesgo de drift durante la transición (dos sources of truth co-existiendo). Estrategia para minimizar.
- **Costo hundido explícito:** Story 4.0 (Supabase Phase 2) — qué se descarta literal, qué se reformula, qué sobrevive. Sin endulzar.

**8. Open questions / decisiones que tienen que cerrarse antes de implementar.**

Listalas honesto. Si hay algo que no podés decidir sin más data del proyecto, decilo y proponé cómo conseguirla.

---

**Cosas que NO tenés que hacer:**

- **No implementar código.** Esto es diseño. Cero archivos `.py`, cero diffs.
- **No reescribir el PRD.** Si hay tensiones entre el PRD actual y c4, marcalas como "PRD-update needed" — eso lo aborda John (PM) en una sesión propia después.
- **No diseñar el esquema completo de las 293 cuentas.** Definí el patrón / regla de mapeo. La aplicación concreta a las 293 cuentas es trabajo del bootstrap.
- **No entrar en preparación de stories.** Eso es Bob (SM), después de que vos cerrés.

---

**Si te quedás trabado:**

Escribí en este archivo (append-only) la pregunta concreta con `awaiting: moishe` o `awaiting: ary` según corresponda. Para preguntas técnicas verificables (ej: "¿beangulp soporta este patrón?") las verifico yo. Para preguntas de producto / negocio ("¿el contador necesita acceso de escritura a `.beancount` o solo lectura?"), las relayeo a Ary.

**Una nota especial sobre el shape del JSON canónico de 4.1a:** ese punto necesito que lo cierres temprano (en tu primera respuesta, idealmente) para desbloquear a Bob preparando Story 4.1a en paralelo a tu trabajo de arquitectura del resto. No tenés que tener TODA la arquitectura cerrada para definir ese shape — el shape es una decisión local.

Cuando termines, escribí acá un resumen de 6-10 bullets + path al artifact + listado de open questions. Yo lo presento a Ary, y si está OK pasamos a Bob para preparar el epic de migración.

— Moishe

---

_(próximas entradas van debajo de esta línea)_

---

### [Winston → Moishe, 2026-04-30 18:30]

Moishe — arquitectura c4 lista. Artifact completo en `_bmad-output/planning-artifacts/architecture-c4.md` (~5500 palabras + diagramas + tablas).

**Resumen ejecutivo (8 bullets):**

- **Topología cerrada.** 5 servicios Render (backend thin, frontend, Fava, importer Laudus cron, prices cron) + Supabase preservado como **registry de `plan_de_cuentas` + `bank_accounts`** (no como repositorio de cartolas). Storage de `.beancount`: subfolder `ledger/` del repo actual + persistent disk en cada servicio + git como source of truth coordinado. Concurrencia Fava + thin API + importers resuelta con write-zones disjuntas (`imports/laudus/`, `imports/cartolas/`, `manual/`) + `bean-check` pre-commit + lock file para race extremo. `main.beancount` solo contiene `include`s.

- **Esquema Beancount definido.** Patrón cuenta `{Root}:{Entity}:{Group}:{Slug}-{account_number}`. Multi-entidad como sub-cuenta (no archivos `include` por entidad — gana flexibilidad de filtros BQL). Mapeo Categoria1 → (Root, Entity) tabulado y heredado del spike. Bank accounts por tipo: TC → `Liabilities` (corrige bug semántico actual), cta_inversiones → `Assets:...:Inversiones:...`, etc. Multi-currency: CLP operating + USD commodity + price directives desde mindicador.cl. Equity inicial 2021 vía pad+balance (no entry-by-entry del JE 140).

- **JSON canónico de 4.1a — CERRADO.** Shape v1.0 documentado §4.1 con `source.bank_account_id` (FK a registry) + `period` + `currency` + `balances` + `transactions[]` con `line_no/date/description/amount(signed)/currency/raw` + `extraction.warnings[]`. Bob puede preparar 4.1a sin esperar nada más mío. El shape difiere del PRD original (más rico) — marcado como `PRD-update needed`.

- **4.1b cerrado.** Clase beangulp `CartolaPdfImporter` con `identify/account/extract` que consume el JSON canónico (no el PDF — el PDF se procesa antes en 4.1a y se descarta). Emite `Transaction` por línea + `Balance` directive al cierre del período → la validación FR22-25 la hace `bean-check` automáticamente. Override con justificación se mapea a `pad`+`balance` (idiomático Beancount).

- **Importer Laudus cerrado.** Reusa `pipeline/services/{ledger,balance_sheet}_service.py` y mapeo de `models.py` intacto; descarta `gspread_utils.py`; nuevo writer `pipeline/writers/beancount_writer.py`. Cron diario 02:00 + endpoint on-demand preservado (Story 2.1 sigue valiendo). Idempotencia por metadata `id:` = `journalentryid`. Cuentas nuevas → archivo `_new-accounts-pending.beancount` con friction explícita (no auto-abrir).

- **Costo hundido Story 4.0 honesto.** ~70% sobrevive (registries `plan_de_cuentas` + `bank_accounts` + sus endpoints CRUD + parte del SupabaseRepository). ~30% se descarta (tablas `cartola_batches` + `cartola_transactions` + métodos asociados). Mucho menor de lo que sería pivot total.

- **Plan de migración en 6 fases (F0-F5).** F0 bootstrap (genero histórico 2021-now + opening balances + accounts mapping; cierra incógnita #2 de Mary), F1 thin API + feature flag, F2 Fava deploy, F3 importer Laudus en prod (Sheets sync legacy queda 1 mes mirror, después read-only archive), F4 importer PDF (4.1a/4.1b), F5 categorización + dashboard integration. Riesgo de drift mitigado con single-writer pattern + diff semanal Sheets vs Beancount + feature flags granulares.

- **3 `PRD-update needed` flagged** (no bloquean, John los aborda después): (a) shape JSON 4.1a más rico que el PRD original; (b) tarjetas de crédito como Liabilities en lugar del modelo actual; (c) decisión sobre threshold-30 de FR31 (recomiendo preservar literal como regla supra sobre smart_importer).

**10 Open Questions para cerrar antes de implementar (§8 del artifact, ordenadas por prioridad de bloqueo):**

1. Repo del ledger: subfolder vs separado.
2. Workflow del contador: PR vs Fava editor directo (afecta F2).
3. Schedule importer Laudus: ambos cron+on-demand (recomendado) vs solo cron.
4. Fuente tipo de cambio CLP/USD (mindicador.cl recomendado) + UF si aplica.
5. Auth de Fava: basic auth vs OAuth proxy (depende de quiénes acceden).
6. Threshold-30 de FR31: preservar literal vs probabilístico.
7. TC como Liabilities: confirmar con la contadora actual (cambia balance + estado de resultado).
8. Reporte HTML semanal: script Python en backend cron (recomendado) vs lambda externa.
9. Cuentas que no mapean a Categoria1 (cuentas de orden, transferencias inter-entidad): trabajo de F0, pero requiere decisión Ary.
10. Deprecation timeline de Sheets como source: F4 + 1 mes paridad (recomendado).

**Lo que está desbloqueado para Bob ahora mismo (sin esperar a Ary):**
- Story 4.1a (shape JSON cerrado, paralelizable).
- Story F1 thin-api (mapping de endpoints completo §5).
- Story F4 importer Laudus (contrato completo §3).
- Story F0 bootstrap (patrón cerrado §2 + §7.1; aplicación a 293 cuentas = ejecución pura post-decisión Ary).

**Lo que espera decisión Ary antes de que Bob lo prepare:**
- Stories que tocan UX (4.2, 4.3, 5.2): esperan #2 (workflow contador) y #5 (Fava auth).
- Stories de categorización (5.1): esperan #6 (threshold-30).
- Stories de TC handling: esperan #7.

Tu siguiente paso natural: presentarle a Ary el resumen + las 10 Qs. Si alguna es técnica que prefieras verificar empíricamente (mindicador.cl, beangulp `Balance` directive como override, etc.) decime y lo resuelvo en un append acá; si son de producto/negocio (auth Fava, workflow contador, TC semantics) las relayeás vos.

— Winston

---

### [Moishe → Winston, 2026-04-30 19:45] — Cierre

Winston, presenté tu resumen + las 10 Qs a Ary y cerramos 9 de 10 en una sola sesión. Registro autoritativo de las decisiones:

**Cerradas (9):**

| Q | Tema | Decisión Ary |
|---|---|---|
| Q1 | Repo del ledger | **Subfolder `ledger/` en `LAUDUS_Backup`** (tu recomendación). |
| Q2 | Workflow contador | **Contador siempre vía Fava UI — nunca PR/GitHub directo.** Editor Fava habilitado **con wrapper post-edit que corre `bean-check` y revierte si rompe** (mi recomendación (b), Ary no objetó). |
| Q3 | Schedule importer Laudus | **Cron sábados 23:59 + on-demand.** Difiere de tu recomendación (cron diario 02:00) — Ary prefiere semanal. Ajustar §3.3. |
| Q5 | Auth Fava | **Basic auth** (tu recomendación). Implica que la family NO accede a Fava — confirmado. |
| Q6 | Categorización FR31 | **smart_importer activo + Patrón B (flag `!`/`*` por threshold de confianza 0.85).** Regla "30 correcciones consecutivas mismo destino" se mantiene como **regla supra** sobre el ML. Frontend LAUDUS muestra badge `⚠ pendiente revisar` en transacciones flag `!`. Difiere de tu recomendación (preservar 30 literal sin ML) — Ary quiso ML asistido. → `PRD-update needed` reformulado: "smart_importer asiste; threshold-30 manda". |
| Q7 | TC como Liabilities | **Sí, `Liabilities`** (tu recomendación). → `PRD-update needed`. |
| Q8 | Reporte HTML semanal | **ON HOLD — fuera del scope del epic de migración.** No diseñar, no incluir en deployment. Volverá como story propia más adelante. |
| Q9 | Cuentas no-Categoria1 | **Bootstrap F0 emite reporte de problemáticas; Ary reclasifica una a una** (tu recomendación). |
| Q10 | Deprecation Sheets | **En cuanto el modelo nuevo esté armado y la información cuadre 1:1.** Sheets queda como archivo histórico read-only. No espera "1 mes paridad" formal — Ary considera el mes parte natural del cuadre. |

**En parking — sesión dedicada (1):**

- **Q4 — Tipo de cambio.** Ary tiene una observación crítica que cambia el approach: **Laudus convierte todo a CLP en su ledger antes de exponerlo**, así que importar con un FX distinto al que ellos aplicaron rompe la cuadratura. La fuente de FX correcta no es mindicador.cl sino **el FX embebido en cada JE de Laudus** (probable campo `exchangerate` o derivable backwards de monto USD/CLP). Esto se aborda en sesión dedicada antes de F0 ejecución. Para tu arquitectura: el spike de F0 va a tener que extraer el FX desde los datos Laudus, no de fuente externa. Ajustá §2.4 (multi-currency) marcando esto.

**3 `PRD-update needed` consolidados para John (sesión separada):**

1. Shape JSON 4.1a más rico que el PRD original.
2. TC como `Liabilities`.
3. Threshold-30 reformulado: smart_importer asistido + regla supra a 30 correcciones (no es solo "preservar literal").

**Próximos pasos operativos:**

1. Cerramos este thread (status: closed). Si necesito clarificación técnica posterior, abro thread nuevo.
2. Despacho a **Bob (SM)** con coord file dedicado (`bob-x-moishe-epic9-2026-04-30.md`) para preparar el **Epic 9 — "Migración a Beancount"**. Ary decidió que es Epic 9 nuevo (no Epic 4-c4 renombrado) — Epic 4 queda como histórico con la story 4.0 marcada costo hundido y stories 4.1a/4.1b/4.2/4.3 transferidas a Epic 9.
3. Bob va a referenciar tu artifact `architecture-c4.md` como input autoritativo. Si encuentra ambigüedad la canaliza por mí, no directo a vos.

Excelente trabajo en una sola pasada. Cerrar 9/10 con la primera entrega es récord.

— Moishe
