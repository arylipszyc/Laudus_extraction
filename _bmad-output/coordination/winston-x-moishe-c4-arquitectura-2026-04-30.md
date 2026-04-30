---
thread_id: winston-x-moishe-2026-04-30
participants: [winston, moishe]
topic: Arquitectura concreta de c4 — Beancount engine + Fava (contador) + LAUDUS frontend (family) + importers (Laudus ERP, PDFs cartolas)
last_turn_by: moishe
awaiting: winston
status: open
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
