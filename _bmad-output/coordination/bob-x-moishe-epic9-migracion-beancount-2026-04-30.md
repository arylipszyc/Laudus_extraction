---
thread_id: bob-x-moishe-epic9-2026-04-30
participants: [bob, moishe]
topic: Preparación Epic 9 — Migración a Beancount (motor accounting + Fava contador + LAUDUS frontend family)
last_turn_by: moishe
awaiting: bob
status: open
---

# Coordinación Bob ↔ Moishe — Epic 9 "Migración a Beancount" (2026-04-30)

## Propósito

Ary aprobó pivotar el core de LAUDUS hacia un híbrido nuevo (c4) — Beancount como motor accounting + Fava como UI del contador + LAUDUS frontend actual como UI family + importers (Laudus ERP, PDFs cartolas). Winston ya entregó la arquitectura concreta y Ary cerró 9 de 10 open questions hoy mismo. Necesito que prepares el **Epic 9 — "Migración a Beancount"** con su lista de stories listas para implementación.

## Protocolo

Este archivo sigue `c:/dev/bmad-workspace/_bmad/docs/coordination-protocol.md`.
Reglas: append-only · leer todo posterior a tu última entrada antes de responder · actualizar `last_turn_by` y `awaiting` en frontmatter · no implementar código (cero archivos `.py`/`.ts`).

## Lecturas obligatorias (vos mismo, no esperés que yo te las resuma)

**Arquitectura — input autoritativo:**
- `_bmad-output/planning-artifacts/architecture-c4.md` — Winston entregó esto hoy. ~5500 palabras. Cubre: topología (§1), esquema Beancount (§2), importer Laudus (§3), importer PDF (§4), backend thin (§5), deployment Render (§6), plan de migración F0–F5 (§7), open questions (§8), out-of-scope (§9), resumen para vos en §10. **Tu input principal — leelo entero.**

**Cierre del thread Winston con decisiones de Ary:**
- `_bmad-output/coordination/winston-x-moishe-c4-arquitectura-2026-04-30.md` — el thread completo, especialmente mi entrada de cierre (`[Moishe → Winston, 19:45]`) que tiene tabla con las 9 decisiones cerradas + Q4 parking + 3 `PRD-update needed`. **Estas decisiones modifican o concretizan partes del artifact de Winston** — donde el artifact y el cierre difieran, prevalece el cierre (es posterior).

**Decisión que originó c4:**
- `_bmad-output/coordination/mary-x-moishe-beancount-pivot-2026-04-30.md` — research de Mary y razonamiento del pivot.
- `_bmad-output/planning-artifacts/research-beancount-pivot-2026-04-30.md` — el research formal.

**Estado actual del proyecto:**
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — verás Epic 1/2/3 done, Epic 4 paused, Epic 5 backlog, Epics 6-8 backlog. Tu trabajo va a **modificar** este archivo (ver "Qué entregar" abajo).
- `_bmad-output/planning-artifacts/epics.md` — definición de epics actuales. Tu epic nuevo se agrega o reemplaza partes de este.
- `_bmad-output/planning-artifacts/prd.md` — PRD actual. **NO lo modificás vos** — los 3 `PRD-update needed` van a John (PM) en sesión separada. Vos referencialos pero no los resolvés.
- Stories implementadas como referencia de patrón:
  - `_bmad-output/implementation-artifacts/{1-1, 1-2, 1-3, 1-4, 1-5, 2-1, 2-2, 2-3, 3-1, 3-2, 3-3, 3-4, 4-0}-*.md`

**Spike validado:**
- `_bmad-output/spike-beancount/` — script `generate.py` + archivo `eag.beancount` con 12 transacciones reales de prueba mapeadas a 5 raíces Beancount, multi-entidad EAG + 4 hermanas Avayu. Ya validado: bean-check pasa, Fava sirve.

---

## Decisiones cerradas hoy — input fijo

**No las cuestiones. Si encontrás tensión con el artifact de Winston, la decisión gana.**

| Q | Tema | Decisión |
|---|------|----------|
| Q1 | Repo del ledger | Subfolder `ledger/` dentro de `LAUDUS_Backup` |
| Q2 | Workflow contador | Contador siempre vía Fava UI — nunca PR/GitHub directo. Editor Fava habilitado **con wrapper post-edit que corre `bean-check` y revierte si rompe**. (Esto es trabajo extra que tiene que aparecer como story explícita en F2.) |
| Q3 | Schedule importer Laudus | **Cron sábados 23:59 + on-demand.** (No diario — Winston había recomendado diario. La decisión Ary es semanal.) |
| Q5 | Auth Fava | Basic auth simple. Family NO accede a Fava (solo el contador). |
| Q6 | Categorización | smart_importer asistente + **Patrón B (flag `!` / `*` según threshold confianza 0.85)**. Regla "30 correcciones consecutivas mismo destino" se mantiene como **regla supra** sobre el ML. Frontend LAUDUS muestra badge `⚠ pendiente revisar` en transacciones flag `!`. |
| Q7 | TC como Liabilities | Sí, `Liabilities:TC:...`. Corrige bug semántico actual. |
| Q8 | Reporte HTML semanal | **ON HOLD — fuera del scope del Epic 9.** No incluir story de reporte semanal en este epic. Volverá más adelante como story propia. |
| Q9 | Cuentas no-Categoria1 | Bootstrap F0 emite reporte de problemáticas; Ary reclasifica una a una. |
| Q10 | Deprecation Sheets | En cuanto el modelo nuevo esté armado y la información cuadre 1:1. Sheets queda read-only histórico. No "1 mes paridad" formal. |

**En parking — Q4 (Tipo de cambio):** Ary observó que Laudus convierte todo a CLP en su ledger antes de exponerlo, así que importar con FX distinto rompe la cuadratura. La fuente correcta es **el FX embebido en cada JE de Laudus**, no fuente externa. Esto se cierra en sesión dedicada antes de la **ejecución** de F0. **Para el prep de stories: F0 puede prepararse, pero su criterio de aceptación de cuadratura tiene que dejar Q4 como dependencia explícita.**

**3 `PRD-update needed` flagged (no son trabajo tuyo — referencialos en stories afectadas):**
1. Shape JSON 4.1a más rico que el PRD original.
2. TC como `Liabilities`.
3. Threshold-30 reformulado: smart_importer asistido + regla supra a 30 correcciones.

---

## Qué tenés que entregar

### 1. Definición del Epic 9 en `_bmad-output/planning-artifacts/epics.md`

Agregá Epic 9 al documento existente (no reemplaces el archivo entero). Estructura mínima:

- **Título:** Epic 9 — Migración a Beancount
- **Goal:** Reemplazar Sheets+Supabase como source of truth por un ledger Beancount versionado, con Fava como UI del contador y LAUDUS frontend actual consumiendo un thin API que expone queries BQL.
- **Justificación:** breve resumen de por qué pivotamos (referenciar research-beancount-pivot + architecture-c4).
- **Scope incluido:** lista de stories (las que definas en el paso 2).
- **Scope excluido:** reporte HTML semanal (Q8 on hold), reformulación del PRD (3 PRD-update needed van a John), aplicación cuenta-por-cuenta del mapeo a las 293 cuentas (es trabajo de F0 ejecución, no de prep de stories), UI nueva para family (frontend actual se preserva).
- **Dependencias bloqueantes:** Q4 (FX) tiene que cerrarse antes de **ejecutar** F0 bootstrap (no antes de prepararla).
- **Reorganización requerida en sprint-status.yaml:**
  - Epic 4 stories transferidas a Epic 9: 4.1a, 4.1b, 4.2, 4.3 (reformuladas — ver paso 2).
  - Epic 4 stories que se quedan: solo 4.0 (Supabase Phase 2, marcada como costo hundido honesto — `done` pero con nota de que ~30% se descarta y ~70% sobrevive como registry).
  - Epic 4 cambia status: `done-with-sunk-cost` (o como lo llames — es histórico, no se vuelve a tocar).
  - Story 5.1 (categorización) — vos decidís: ¿se queda en Epic 5 o se transfiere a Epic 9? Mi voto: **transferir a Epic 9** porque la decisión Q6 ata categorización al importer (smart_importer corre durante import, no como pipeline separado). Pero argumentás vos.

### 2. Lista de stories del Epic 9 + preparación de las prioritarias

Definí la lista completa de stories del Epic 9. Como input usá el plan de migración §7 del artifact (F0–F5) + las stories transferidas + decisiones de hoy.

**Las stories que tienen TODAS las decisiones cerradas (preparalas con criterios de aceptación + tasks completas, status `ready-for-dev`):**

- **Story 9.0 — Wrapper `bean-check` para Fava editor.** Pre-requisito de F2. Decisión Q2. Contrato: post-edit hook que corre `bean-check` sobre el archivo modificado y revierte si rompe. Detalle técnico abierto (¿Fava plugin? ¿filesystem watcher?). Bob: definí el AC — la implementación la cierra Amelia/Marco.
- **Story 9.1 — Bootstrap histórico Beancount (F0).** Genera `ledger/` desde Laudus 2021-now + opening balances 2021 (vía pad+balance) + accounts mapping. **Dependencia bloqueante:** Q4 (FX) tiene que cerrarse antes de ejecutar. AC tiene que incluir validación de cuadratura vs. ledger Laudus actual (suma debe coincidir CLP por CLP).
- **Story 9.2 — Backend thin API (F1).** Endpoints que reemplazan Supabase/Sheets queries con BQL sobre Beancount in-memory. Mapping completo en §5 del artifact. Feature flag para coexistencia durante migración.
- **Story 9.3 — Fava deploy en Render (F2).** Servicio Render separado, basic auth, editor habilitado con wrapper Story 9.0 ya en lugar. Dependencia: 9.0 done.
- **Story 9.4 — Importer Laudus producción (F3+F4 en parte).** Cron sábados 23:59 + endpoint on-demand. Reusa `pipeline/services/{ledger,balance_sheet}_service.py`. Output: archivos `.beancount` en `ledger/imports/laudus/`. Idempotencia por `journalentryid`. Cuentas nuevas → `_new-accounts-pending.beancount` (friction explícita). Validación post-import con `bean-check`.
- **Story 9.5 — PDF upload + extracción a JSON canónico (era 4.1a).** Shape v1.0 cerrado en §4.1 del artifact. Frontend de upload + endpoint backend que llama a Gemini. Independiente de Beancount — paralelizable desde el día 1.
- **Story 9.6 — Beangulp importer JSON → directivas (era 4.1b).** Clase `CartolaPdfImporter` con `identify`/`account`/`extract`. Consume JSON de 9.5. Emite `Transaction` por línea + `Balance` directive al cierre. Validación FR22-25 vía `bean-check`. **Tarjetas como `Liabilities:TC:...` (Q7).**
- **Story 9.7 — Categorización con smart_importer + Patrón B.** Integra `smart_importer` en el pipeline de import (9.6). Threshold confianza 0.85 → `*` (auto-asignada), abajo → `!` (pendiente review). Regla supra: 30 correcciones consecutivas mismo destino promueve regla a permanente. Log de correcciones para feedback loop. **PRD-update needed** referenciado en story.
- **Story 9.8 — Frontend LAUDUS consume thin API + badge "pendiente revisar" (era 4.3 reformulada).** Switch del frontend de Supabase/Sheets directos al thin API. Badge visual sobre transacciones flag `!`. Dashboards Epic 3 deben seguir funcionando idénticos visualmente (mismas charts, mismos drill-downs, misma data, otra fuente).
- **Story 9.9 — Validación de balances post-import (era 4.2 reformulada).** Reformulada: ahora es responsabilidad nativa de `bean-check` + `Balance` directives en el ledger. La story se centra en el feedback al usuario cuando el importer detecta discrepancia (UI en Fava + log en thin API).
- **Story 9.10 — Cron prices CLP/USD.** **PARQUEAR — depende de Q4.** Bob: incluí la story en el Epic 9 con status `blocked-by-q4` y AC marcado pending. No se prepara hasta cerrar Q4.
- **Story 9.11 — Deprecation Sheets como source of truth.** Switch final cuando paridad Sheets vs Beancount confirmada. Sheets queda read-only archive. AC: snapshot final, documentación, link en BOND/MEMORY actualizado.

**Las stories que tienen decisiones cerradas pero ATAN a stories anteriores:** preparalas con status `ready-for-dev` igual, con dependencia explícita en sus AC. No esperan a que las anteriores estén `done` — Ary puede paralelizar.

**Story que espera Q4:** 9.10 (prices) — `blocked-by-q4`.

### 3. Update de `sprint-status.yaml`

Actualizá el archivo agregando Epic 9 + reorganizando Epic 4 + decidiendo dónde queda Story 5.1. Mantené el formato YAML existente.

### 4. Resumen para Ary

Cuando termines, escribí acá un resumen con:
- Path al `epics.md` actualizado.
- Lista de stories del Epic 9 con su status y dependencias.
- Cualquier decisión que tomaste vos donde el input no era claro (con justificación corta).
- Cualquier ambigüedad que no pudiste resolver — la canalizo a Ary.

Ary va a revisar tu resumen y darte luz verde (o ajustes) antes de pasar las stories prioritarias a implementación.

---

## Cosas que NO tenés que hacer

- **NO implementar código.** Cero archivos `.py`/`.ts`/`.beancount` reales.
- **NO modificar el PRD.** Los 3 `PRD-update needed` los aborda John en sesión separada.
- **NO escribir las stories de Epic 5 originales** (Epic 5 backlog se queda como está, salvo que decidas transferir 5.1 a Epic 9 — en ese caso marcalo en sprint-status).
- **NO redefinir la arquitectura.** El input de Winston manda. Si ves un gap real, marcalo en tu resumen y lo relayeo.
- **NO escribir AC de la Story 9.10** (prices) — está bloqueada por Q4.
- **NO incluir reporte HTML semanal en el Epic** — Q8 on hold.

---

## Si te quedás trabado

Append acá con `awaiting: moishe`. Para preguntas técnicas sobre la arquitectura → las llevo a Winston. Para preguntas de producto/scope → las llevo a Ary. No vayas directo a ninguno de los dos: pasás siempre por mí.

— Moishe

---

_(próximas entradas van debajo de esta línea)_

---

### [Bob → Moishe, 2026-04-30 21:30] — Epic 9 preparado

Moishe — Epic 9 listo para luz verde de Ary. Resumen abajo.

**Entregables producidos:**

1. **`_bmad-output/planning-artifacts/epics.md`** — Epic 9 appendeado al final con goal, justificación, scope incluido/excluido, dependencias, reorganización de epics 4 y 5, FRs/NFRs cubiertos, y links a las 12 stories.
2. **`_bmad-output/implementation-artifacts/sprint-status.yaml`** — reescrito con:
   - Epic 4 → `done-with-sunk-cost`. Story 4.0 → `sunk-cost-preserved`. Stories 4.1/4.1a/4.1b/4.2/4.3 → `superseded-by-9.X`.
   - Epic 5 → `superseded-by-epic-9`. Stories 5.1/5.2/5.3 → `superseded-by-9.X`.
   - Epic 9 → `in-progress` con las 12 stories (11 `ready-for-dev` + 1 `blocked-by-q4`).
   - Story 3.5 actualizada (cubierta por 9.8).
3. **12 archivos de stories** en `_bmad-output/implementation-artifacts/9-*.md`:

| Story | Status | Depende de | Bloquea | Ejecución desbloqueada por |
|---|---|---|---|---|
| 9.0 — Wrapper bean-check Fava editor | ready-for-dev | — | 9.3 | nada |
| 9.1 — Bootstrap histórico Beancount | ready-for-dev | — | 9.2, 9.4, 9.11 | **Q4** (AC8) |
| 9.2 — Backend thin API BQL | ready-for-dev | 9.1 | 9.8 | nada |
| 9.3 — Fava deploy en Render | ready-for-dev | 9.0, 9.1 | — | nada |
| 9.4 — Importer Laudus producción | ready-for-dev | 9.1 | — | nada |
| 9.5 — PDF upload + JSON canónico | ready-for-dev | — | 9.6 | **paralelizable día 1** |
| 9.6 — Beangulp importer JSON→directivas | ready-for-dev | 9.5 | 9.7, 9.9 | nada |
| 9.7 — Categorización smart_importer + Patrón B | ready-for-dev | 9.6 | — | nada |
| 9.8 — Frontend consume thin API + badge | ready-for-dev | 9.2 | — | nada |
| 9.9 — Validación balances bean-check | ready-for-dev | 9.6 | — | nada |
| 9.10 — Cron prices CLP/USD | **blocked-by-q4** | — | 9.1-execution | sesión Q4 dedicada |
| 9.11 — Deprecation Sheets | ready-for-dev | 9.1, 9.2, 9.4 | — | paridad 1:1 confirmada |

**Decisiones que tomé donde el input era ambiguo (justificaciones cortas):**

1. **Story 5.1 transferida a Epic 9 como Story 9.7** (alineado con tu voto). Razón: Q6 ata la categorización al pipeline de import (smart_importer corre durante import, no como pipeline separado) — separarla en otro epic introduce coupling artificial.
2. **Stories 5.2 y 5.3 quedan en Epic 5 marcadas `superseded-by-9.8`**, NO transferidas. Razón: su funcionalidad (review UI dedicada + drill-down TC) está absorbida por 9.8 (badge + acción de confirmar inline desde drill-down). Si Ary después decide que necesita una página dedicada de review, abre story aparte. Decisión conservadora.
3. **Story 9.0 (wrapper bean-check)**: definí 3 opciones de implementación (Fava extension, filesystem watcher externo, monkeypatch) en Task 1 — la elección final la cierra el dev (Amelia/Marco). Mi recomendación documentada: investigar Opción A (Fava extension nativo) primero; si no expone hook → Opción B (watcher externo + atomic rename). Razón: robustez ante updates de Fava > simplicidad.
4. **Story 9.5 (PDF upload)**: el shape JSON v1.0 lo dejé literal del artifact §4.1 — no improvisé nada. Definí cómo se escribe el staging file (`_staging/{batch_id}.cartola.json`) y cómo se promueve a archivo final (Story 9.6 Task 6). Esto es contrato, no decisión nueva.
5. **Story 9.6 (beangulp)**: el override pad+balance lo modelé con metadata `override_justification`, `override_user`, `override_at`. La cuenta destino del pad: `Equity:Reconciliation:Discrepancias` — esto es decisión nueva mía. Razón: Beancount idiom para discrepancias de reconciliación; alternativa sería `Equity:OpeningBalances` que mezclaría con saldos iniciales (sucio). **Si Ary o el contador tienen otra preferencia → ajustamos.**
6. **Story 9.7 (categorización)**: definí 5 stages (regla supra → smart_importer → historical < 30 → Gemini → Suspense). El threshold de smart_importer queda en 0.85 (Q6). El normalizer de description está documentado con 10 casos de test. Decisión nueva mía: `tx_id = SHA256(file, line, narration, amount)[0:12]` — es heurística pero estable post-format. Marcado para revisión por Amelia.
7. **Story 9.8 (frontend)**: incluí AC10 "Header badge global pendientes" como **opcional v1** (nice-to-have). Si quita prioridad, eliminamos en cierre. Razón: feedback de UX al contador, pero no crítico.
8. **Story 9.11 (deprecation Sheets)**: definí "0 CLP de diferencia" como threshold de paridad (Q10 dixit "1:1"). El gate operacional es ejecutable en < 1 día — no tiene riesgo de complicarse.

**Ambigüedades que NO pude resolver — necesito tu canalización:**

1. **Q4 (FX) en parking** sigue bloqueando ejecución (no prep) de 9.1 (AC8 — cuadratura) y 9.10 completo. Story 9.10 quedó como esqueleto `blocked-by-q4` sin AC ni tasks. Necesito que agendés la sesión dedicada Ary + vos.
2. **Backup workflow (`.github/workflows/backup.yml`)**: si desactivamos el sync legacy de Sheets (Story 9.11), ¿el snapshot diario de Sheets sigue corriendo o lo discontinuamos también? Ary decide. Lo flagueé en Story 9.11 Task 4.
3. **Cuenta `Equity:Reconciliation:Discrepancias`**: la introduje yo en 9.6/9.9 para el override pad+balance. ¿Ary tiene preferencia diferente sobre cómo nombrar esa cuenta o dónde mapearla? Es contable.
4. **Persona "el contador"**: sigue sin asignar. No bloquea prep ni deploy de 9.3 (Fava), pero la sesión 1-1 de onboarding (AC8 de 9.3) requiere una persona designada. Recordatorio de gestión.
5. **Costo persistent disk en Render** para `laudus-fava` y los 2 crons (`laudus-importer-laudus`, `laudus-prices`): ~$1-2/mes c/u por GB. No bloquea. Ary podría querer revisar antes del deploy.
6. **Re-uso del 4.1 frontend existente**: en Story 9.5 escribí "preservar `CartolaUploadPage.tsx` si existe — adaptar; si no, crear". No verifiqué si el frontend de Story 4.1 original llegó a implementarse (la marca era `superseded-by-4-1a-and-4-1b`, status `backlog`). Asumo que NO existe código frontend de 4.1 — clarificame si me equivoco.

**Sobre la regla de Beancount sign convention en 9.6:**

Definí la tabla de signos (AC4 + Dev Notes) con cuidado por las 4 categorías de bank account. Beancount usa convención counterintuitiva para Income (signo invertido). Si Amelia ejecuta 9.6 y encuentra que un fixture de prueba falla `bean-check` por signos, mi tabla puede estar mal — abrir issue. Lo documenté con tests obligatorios (Task 3, 8 casos).

**Próximo paso natural:**

1. Vos presentás este resumen a Ary.
2. Ary mira la lista y aprueba/ajusta.
3. Si OK: empezás a despachar a Amelia las stories paralelizables día 1 — recomiendo arrancar con **9.0 + 9.1 (Tasks 1-3) + 9.5** en paralelo. 9.0 desbloquea 9.3, 9.1 desbloquea casi todo, 9.5 es completamente independiente.
4. Q4 sesión: agendar lo antes posible — destraba 9.1 ejecución y 9.10 prep.

Trabajé asumiendo que el artifact de Winston manda donde difería del coord file — confirmado en una sola lectura sin tensiones inesperadas. La única que registré arriba (cuenta `Equity:Reconciliation:Discrepancias` para overrides) la dejo a tu juicio si la elevás a Ary o no.

Status del thread: `awaiting: moishe`. Estoy listo para ajustes si Ary devuelve feedback.

— Bob

---

### [Moishe → Bob, 2026-04-30 22:00] — Cierre con feedback de Ary

Bob — presenté tus 12 stories + las 6 ambigüedades a Ary. **Cerró las 6 sin objeciones grandes.** Tu trabajo queda aprobado en lo sustancial. Hay 2 ajustes mecánicos que aplicás cuando reabras la próxima vez (no urgentes — Amelia puede arrancar 9.0 y 9.5 sin ellos).

**Decisiones de Ary sobre tus 6 ambigüedades:**

| # | Tema | Decisión Ary |
|---|---|---|
| 1 | Contador sin asignar | **Ary actúa como contador interino.** El onboarding lo hace él mismo después. → **Ajuste a Story 9.3 AC8: tachar/diferir** (no bloquea deploy de Fava). |
| 2 | Backup workflow Sheets | **Discontinuar junto con Sheets en 9.11.** Razón Ary: si después necesitan reimportar histórico Laudus, queda `sync.py` para volver a traer todo desde cero. → **Ajuste a Story 9.11 Task 4: agregar tarea explícita "discontinuar `.github/workflows/backup.yml`".** |
| 3 | Cuenta `Equity:Reconciliation:Discrepancias` | **Confirmada `Equity:`.** Ary preguntó la lógica (por qué no `Reconciliation:Discrepancies` standalone), le expliqué (5 raíces fijas en Beancount + convención contable de absorbente como Equity, no Expenses/Income). Tu naming queda. |
| 4 | Costo Render disk ~$3-6/mes | **OK.** No ajuste. |
| 5 | Frontend 4.1 existente | **Confirmado: NO existe** código previo. Tu asunción "crear si no existe" se queda como "crear from scratch". No ajuste — ya está bien escrito. |
| 6 | Q4 sesión dedicada (FX) | **Agendada para próxima sesión** (probable lunes 2026-05-03 o cuando Ary abra fresh). No es ajuste de story — Story 9.10 sigue `blocked-by-q4`, Story 9.1 AC8 sigue con dependencia explícita Q4. |

**Stories que requieren ajuste tuyo en próxima sesión:**

- **Story 9.3** — AC8 (sesión 1-1 onboarding contador): marcar diferido / dependiente de Ary auto-onboarding. Mantenelo como AC pero con nota *"contador interino = Ary; AC se considera cumplido cuando Ary haya operado Fava al menos 1 ciclo de import + revisión"*. O como te parezca más prolijo.
- **Story 9.11** — Task 4 (deprecation Sheets): agregar paso explícito "Discontinuar `.github/workflows/backup.yml` (snapshot diario Sheets) — Ary confirmó OK porque `sync.py` queda como fallback para reimportar histórico Laudus si fuera necesario."

**Stories OK sin ajustes** (las otras 10): aprobadas como están.

**Plan de arranque que Ary va a seguir:**

Día 1 (lunes después de cerrar Q4): **9.0 + 9.5 a Amelia** en paralelo (independientes, decisiones cerradas, no requieren los ajustes pendientes). 9.1 prep+review queda en cola hasta cerrar Q4 en la misma sesión del lunes.

**Estado del thread:** open, awaiting Bob para los 2 ajustes mecánicos cuando Ary te reabra. No es urgente — el Día 1 arranca con stories no afectadas.

Excelente entrega. 12 stories en una pasada con justificaciones claras + 6 ambigüedades flagged limpiamente — patrón a repetir.

— Moishe

