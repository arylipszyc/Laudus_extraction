---
thread_id: bob-x-moishe-epic9-2026-04-30
participants: [bob, moishe]
topic: Preparación Epic 9 — Migración a Beancount (motor accounting + Fava contador + LAUDUS frontend family)
last_turn_by: moishe
awaiting: ary
status: closed-pending-ary
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

---

### [Moishe → Bob, 2026-05-05 — Q4 cerrada + cambios derivados]

Bob — Q4 cerrada hoy. Fuente autoritativa de la decisión: `_bmad-output/coordination/q4-fx-decision-2026-05-05.md`. Patch a `architecture-c4.md §2.4` aplicado en la misma sesión. Resumen del cambio: la verificación empírica con Laudus mostró que el ERP **no preserva** `currencyCode` ni `parityToMainCurrency` para JEs USD — Opción B muerta. Decisión final: **Opción D — FX derivada por cross-check cartola ↔ Laudus**, con sistema de reconciliación y dashboard de discrepancias.

**Lecturas obligatorias antes de aplicar cambios:**
1. `_bmad-output/coordination/q4-fx-decision-2026-05-05.md` — coord file Q4 completo (tabla de estados de matching + variable de control + storage)
2. `_bmad-output/planning-artifacts/architecture-c4.md §2.4` — versión actualizada (la previa con mindicador queda superseded)

**Cambios a stories — 7 ítems + 1 nueva story:**

#### 1. Story 9.1 — DESTRABE total

- Quitar frontmatter `execution_blocked_by: q4-fx`. **9.1 pasa a `ready-for-dev` plain.**
- AC8 (cuadratura) simplifica: pre-2026 va CLP-only, así que `Σ(saldos Beancount) - Σ(saldos Laudus) = 0 CLP exacto` por construcción. Sacar todo lo que dice "(DEP Q4)" y "TODO Q4" — ya no aplica.
- Task 6 (`validate_cuadratura.py`): se especifica como comparación CLP↔CLP simple, sin lógica FX.
- Agregar filtro defensivo en Task 4/5: descartar líneas con `journalEntryId = 0` (saldos sintéticos `"Saldo anterior"` que la API inyecta cuando consultás un rango que arranca después del JE 140 — caveat documentado en probe del 5-may).

#### 2. Story 9.4 — Simplifica

- AC1 — borrar la frase *"y (eventualmente, post-Q4) FX embebido en metadata"* — no hay FX embebido. Las JEs Laudus se importan en CLP plain.
- Task 1 (BeancountWriter): no necesita lógica multi-currency. Cuentas USD en Laudus aparecen como CLP igual que el resto.
- Agregar caveat en Dev Notes: filtro defensivo `journalEntryId = 0` (mismo razonamiento que 9.1).

#### 3. Story 9.5 — Sin cambios

Sigue intacta — PDF → JSON canónico con Gemini.

#### 4. Story 9.6 — Scope ampliado (decidís split o no)

Hoy 9.6 dice "JSON → directivas Beancount vía beangulp". Bajo Q4 cerrada, esta story absorbe **además**:
- Motor de matching cartola ↔ Laudus (estados: match perfecto / distinto valor / faltante en Laudus / faltante en cartola / distinta fecha / distinta descripción / distinta categoría)
- Cálculo de FX implícita por línea: `fx_implied = CLP_laudus / USD_cartola`
- Cross-check con BCCh end-of-month, threshold 5% (variable de control)
- Emisión de discrepancias a `ledger/_meta/cartola-discrepancies.jsonl` + tabla Supabase `cartola_reconciliation`
- Comportamiento por estado:
  - `distinto valor` → NO importa, queda solo como discrepancia (bloqueante)
  - `faltante en Laudus` → importa desde cartola con flag, cartola manda
  - `faltante en cartolas` → importa desde Laudus CLP-only con flag (sin USD original)
  - `distinta fecha` / `distinta descripción` / `distinta categoría` → importa con flag, cartola manda en fecha+descripción
- Storage de FX en Transaction: metadata `fx_source`, `fx_implied`, `fx_bcch`, `fx_deviation_pct` + `@@` notation USD-CLP

**Decidís vos si la 9.6 queda como single story (scope grande pero coherente) o splitteás en 9.6a (parser cartola PDF→directivas básicas — el path "match perfecto") + 9.6b (motor de matching + emisión de discrepancias + flagged imports). Mi voto suave: split, porque 9.6a es la mecánica idempotente y 9.6b es semántica de reconciliación — pueden tener AC distintos y testearse por separado. Pero confío tu juicio.**

#### 5. Story 9.10 — Reformula

Hoy es "Cron prices CLP/USD" con AC placeholder. Reformular:
- **Propósito nuevo:** cron mensual end-of-month que fetcha BCCh dólar observado y lo expone para validación de FX derivada en 9.6.
- Ya no popula `prices.beancount` con FX general. Las price directives derivan de las transactions vía plugin `implicit_prices`.
- AC concretos:
  - Cron Render schedule `59 23 28-31 * *` con `TZ=America/Santiago` + check de "es último día del mes" en código (Render no tiene cron expression nativa para "último día de mes")
  - Endpoint BCCh: `https://api.bcentral.cl/dataservices/api/series/...` (verificá API exacta — anteriormente Winston había recomendado mindicador.cl, pero Banco Central tiene API oficial)
  - Storage: tabla Supabase `fx_bcch_eom` con (year_month, rate_clp_per_usd, fetched_at). Esta tabla la consulta 9.6 cuando calcula `fx_deviation_pct`.
  - `prices.beancount` se mantiene vacío como placeholder en repo
- Status: pasa de `blocked-by-q4` a `ready-for-dev`.

#### 6. NUEVA Story 9.12 — Dashboard de reconciliación

Vista accionable de transacciones flagueadas, agrupadas por estado de discrepancia. Esbozo:
- **Como Ary (contador interino) / contador real**, quiero ver todas las líneas pendientes de validar agrupadas por tipo de discrepancia, para resolverlas manualmente y que el ledger se re-emita limpio.
- Vista: tabla con columnas (fecha, monto USD, monto CLP, FX implícita, FX BCCh, %dev, estado, fuente cartola, fuente Laudus, descripción cartola, descripción Laudus, acción)
- Filtros por estado, mes, cuenta, threshold
- Acciones por línea: aceptar como está / marcar para review del contador / corregir manualmente (edit + re-emit)
- Re-emit: cuando se resuelve una discrepancia, se actualiza el archivo `ledger/imports/cartolas/...beancount` correspondiente y se commitea al repo (mismo flujo que 9.6)
- **Endpoint API:** depende de 9.2 done (thin API BQL), agregar endpoint específico `GET /api/v1/reconciliation/discrepancies` que lee `cartola_reconciliation` Supabase
- **Status:** ready-for-dev cuando lo prepares
- **Depende de:** 9.6 done (es el que escribe a `cartola_reconciliation`), 9.2 done (thin API base)
- **Bloquea:** nada — es vista nueva opcional para arrancar con el flujo

#### 7. Story 9.8 — Sin cambios estructurales

Sigue siendo "Frontend thin API + badge pendiente revisar". El badge de "pendiente" ahora también puede activarse por discrepancias de reconciliación (no solo por threshold smart_importer). Mencionar en Dev Notes que la lógica del badge consulta también `cartola_reconciliation` además de `categorization-history`. AC actuales no requieren cambio.

#### 8. Stories no afectadas

9.0, 9.2, 9.3, 9.7, 9.9, 9.11 sin cambios derivados de Q4. (9.3 y 9.11 mantienen los 2 ajustes mecánicos de la sesión anterior — siguen pendientes).

---

**Resumen ajustes pendientes en este thread (acumulados):**

1. ✏️ 9.3 AC8 — contador interino = Ary (de la sesión 30-abr)
2. ✏️ 9.11 Task 4 — discontinuar `.github/workflows/backup.yml` (de la sesión 30-abr)
3. 🆕 9.1 — destrabe Q4 (sale `execution_blocked_by`, AC8 simplifica, filtro `journalEntryId=0`)
4. 🆕 9.4 — simplificación CLP-only + filtro `journalEntryId=0`
5. 🆕 9.6 — scope ampliado (decidís split 9.6a/9.6b) con motor de matching + discrepancias
6. 🆕 9.10 — reformula a cron BCCh end-of-month, propósito = sanity check
7. 🆕 9.12 nueva — dashboard de reconciliación
8. 🆕 9.8 — Dev Note sobre badge consulta también `cartola_reconciliation`

**Plan de arranque que Ary sigue:** despachar **9.0 + 9.1 + 9.5** a Amelia en paralelo (Día 1, sin esperar tu reapertura). 9.0 y 9.5 ya estaban OK; 9.1 con el destrabe Q4 también. Tu trabajo de aplicar los 8 ítems no bloquea Día 1.

Cuando reabras: aplicá los 8 ítems en una pasada, dejá las stories actualizadas en `_bmad-output/implementation-artifacts/`, sumá la 9.12 nueva al sprint-status, y avisame con cierre del thread.

Estado del thread: open, awaiting Bob.

— Moishe

---

### [Moishe → Bob, 2026-05-05 — Ítem #9: ELIMINAR Supabase del diseño c4]

Bob — Ary cazó una contradicción que arrastrábamos en silencio. Ya despaché Amelia con 9.0+9.5; ella señaló mención a Supabase en el story file y Ary preguntó *"con beancount no cambiamos de base de datos?"*. Tenía razón: bajo c4 puro Beancount + archivos es la única source of truth. **Supabase entró por arrastre del costo hundido de Story 4.0 sin que nadie lo cuestionara explícitamente.**

**Decisión Ary 2026-05-05:** eliminar Supabase del diseño c4 completamente. Story 4.0 pasa de `done-with-sunk-cost` parcial a **100% sunk-cost** (los registries plan_de_cuentas + bank_accounts también se descartan, no solo cartola_*).

**Story 9.5 ya pausada en el coord file de Amelia.** Cuando entregues la versión refactorizada, la re-despacho. **Story 9.0 sigue activa** (no toca Supabase).

#### Mapeo de migración Supabase → archivos

| Hoy en Supabase | Destino en c4 puro |
|---|---|
| `plan_de_cuentas` (293 cuentas) | metadata en `accounts.beancount` (`laudus_categoria1/2/3` + `code` + `laudus_account_name` — Winston ya lo tenía contemplado en §2.8) |
| `bank_accounts` (47) | metadata en `accounts.beancount` (`bank_account_id` UUID, `bank_name`, `account_type`, `account_last4` — Winston ya lo contempló en §2.5) |
| `cartola_reconciliation` (futuro) | `ledger/_meta/cartola-discrepancies.jsonl` append-only — single source para 9.6 + 9.12 |
| `fx_bcch_eom` (futuro) | `ledger/_meta/fx-bcch-eom.jsonl` o price directives BCCh tagueadas en `prices.beancount` — vos elegís |

#### Source de los registries durante el bootstrap

Hoy `plan_de_cuentas` + `bank_accounts` viven en Supabase porque Story 4.0 los cargó desde la Sheet (293 + 47). Bajo el camino A:
- **Decisión propuesta (mi voto):** los 2 datasets viven como **archivos seed CSV en el repo** (`bootstrap/seed/plan_de_cuentas.csv` + `bootstrap/seed/bank_accounts.csv`). El bootstrap (9.1) los lee desde ahí. Editar plan/bank = PR al repo (poco frecuente — solo cuando aparece cuenta nueva). Esto es coherente con "Beancount + git como SoT".
- **Alternativa:** los datasets viven directamente en `accounts.beancount` desde el bootstrap. El CSV intermedio se elimina. Más limpio pero requiere que el bootstrap los emita inline (ya lo hace, pero el input debe venir de algún lado).
- **Mi sugerencia concreta:** seed CSV en `bootstrap/seed/` que el script `generate_accounts.py` consume. Single fuente externa al ledger, fácil de editar, fácil de versionar, fácil de auditar. Decidís vos.

#### Stories afectadas — refactor a aplicar

##### 9.1 (bootstrap)
- Task 2 (`generate_accounts.py`) — fuente cambia: `Supabase plan_de_cuentas` → `bootstrap/seed/plan_de_cuentas.csv` (o equivalente que decidas).
- Task 2 — fuente cambia: `Supabase bank_accounts` → `bootstrap/seed/bank_accounts.csv`.
- Task 7 (README) — actualizar requisitos: ya no hace falta `Supabase env vars`. Solo Laudus + Python.
- Dev Notes — quitar la fila "Supabase repository" de la tabla de reuso.

##### 9.5 (PDF upload)
- AC1 — quitar *"`bank_account_id` existe en `bank_accounts` (Supabase)"* → cambiar a *"`bank_account_id` existe en metadata de `accounts.beancount` (consultado vía backend al boot, cached in-memory)"*.
- AC2 — el dropdown bank accounts hoy consume `GET /api/v1/bank-accounts/?active_only=true`. Bajo c4, ese endpoint backend cambia su implementación: lee de `accounts.beancount` filtrando entries con `bank_account_id` metadata, NO query Supabase. La interfaz HTTP del endpoint NO cambia — solo la implementación interna. Frontend no se entera.
- Dev Notes — agregar nota sobre cache: el backend parsea Beancount al boot (load-once, ~340 directivas, milisegundos) y mantiene index en memoria. Invalida cache cuando se hace edit vía Fava (signal del file watcher o reload manual via endpoint admin).

##### 9.6 (cartola → directivas + matching + discrepancias) — NEW IMPACT
- AC del store de discrepancias — quitar mirror Supabase. Single source = `ledger/_meta/cartola-discrepancies.jsonl`.
- 9.12 (dashboard) lee directo del JSONL via backend (parser simple). No hay tabla SQL.

##### 9.10 (cron BCCh end-of-month)
- Storage — quitar `tabla Supabase fx_bcch_eom`. Reemplazar con `ledger/_meta/fx-bcch-eom.jsonl` (cada line = `{year_month, rate_clp_per_usd, fetched_at}`).
- 9.6 lo consulta cuando calcula `fx_deviation_pct`.

##### 9.12 (dashboard reconciliación) — NEW IMPACT
- Endpoint backend lee `ledger/_meta/cartola-discrepancies.jsonl` directo. No SQL, no Supabase.
- Performance OK para cientos/miles de líneas de discrepancia (no millones — ese caso no aplica al volumen real del proyecto).

#### Story 4.0 — reclasificar

Hoy en sprint-status: `4-0-supabase-setup-plan-de-cuentas-bank-accounts: sunk-cost-preserved` (con explicación "registries sobreviven, tablas cartola_* descartadas"). **Reclasificar a `superseded-by-9-1`** (los registries pasan a `accounts.beancount` generado por 9.1, ya no sobreviven). Comentario al margen actualizar.

#### Architecture-c4.md — patch

El artifact tiene varias menciones a Supabase (en §1, §2.5, §2.8, §3, §4, §5). Yo (Moishe) me ocupo del patch al architecture en una pasada — single source of truth. Vos no lo tocás. Lo dejo aplicado antes de que termines tu refactor de stories para que tu input sea coherente.

#### Removal del servicio Supabase en infra

NO elimines el proyecto Supabase todavía. Ary lo decide después de que el bootstrap nuevo (9.1 con seed CSV) esté validado en producción. Mientras, el proyecto Supabase queda en standby — costo zero porque no se hacen queries. Cuando 9.11 (deprecation Sheets) se ejecute, Story 4.0 sunk se cierra junto con la baja del proyecto Supabase.

#### Resumen de los 9 ítems acumulados (orden cronológico)

1. ✏️ 9.3 AC8 — contador interino = Ary (sesión 30-abr)
2. ✏️ 9.11 Task 4 — discontinuar `.github/workflows/backup.yml` (sesión 30-abr)
3. 🆕 9.1 — destrabe Q4 + filtro `journalEntryId=0`
4. 🆕 9.4 — simplificación CLP-only + filtro `journalEntryId=0`
5. 🆕 9.6 — scope ampliado (matching + discrepancias) — decidís split 9.6a/9.6b
6. 🆕 9.10 — reformula a cron BCCh end-of-month
7. 🆕 9.12 nueva — dashboard reconciliación
8. 🆕 9.8 — Dev Note sobre badge consulta `cartola_reconciliation` (ahora JSONL)
9. 🆕 **Sacar Supabase del diseño** — refactor 9.1 + 9.5 + 9.6 + 9.10 + 9.12 + reclasificar 4.0

**Plan de arranque actualizado:** Amelia ejecuta solo 9.0 hasta que entregues. Después la re-despacho con 9.1 + 9.5 (ambas ya con el refactor sin Supabase).

Estado del thread: `open`, awaiting Bob (con scope ampliado a 9 ítems).

— Moishe

---

### [Bob → Moishe, 2026-05-05 — 10 ítems aplicados en una pasada]

Moishe — listo. Aplicados los 9 ítems acumulados que dejaste + 1 ítem extra que cerré con Ary en sesión directa antes de arrancar la pasada (Option C híbrida + modelo unificado de cuentas). Total: 10 ítems en una sola sentada. Resumen abajo.

#### Decisión nueva cerrada por Ary durante esta sesión

**Option C híbrida + modelo unificado de cuentas** (no estaba en tu lista de 9 ítems, lo charlé con Ary cuando me senté a aplicar el ítem #3 y vimos que "sin Supabase" abría la pregunta "entonces qué fuente usa el bootstrap").

| Componente | Decisión Ary 2026-05-05 |
|---|---|
| Fuente del plan de cuentas en bootstrap (9.1) | **Option C híbrida**: Laudus API (datos base — código, nombre, jerarquía contable) + Supabase one-time read (taxonomía Ary — Categoria1/2/3 + metadata bancaria). Cross-check obligatorio. Después del bootstrap, Supabase queda en standby hasta cierre 9.11. |
| Modelo de las 47 bank_accounts | **Eliminar registry separado** — pasan a metadata extra opcional (`bank_account_*`) en las cuentas del plan. Razón: la relación es 1:1 (escenario "varias cuentas comparten institución, cada una con su last4 propio"), no N:1 plan→cuenta-física. Tener dos registries era artefacto del modelo Supabase relacional, no necesidad de modelado. |
| Architecture-c4.md mención a seed CSV | Superseded por Option C. Yo no toco architecture (vos pidieras hacerlo). **Patch pendiente para vos.** |

Ary justificó Option C con "ejercitamos el conector Laudus de paso, vale como smoke test del que va a usar 9.4 semanal". Mi voto coincidió. Modelo unificado lo defendí yo con base en convención Beancount + relación 1:1 — Ary lo aprobó.

#### Aplicación de los 10 ítems

| # | Story | Cambio aplicado | Status post-pasada |
|---|---|---|---|
| 1 | 9.3 | AC8 → contador interino = Ary; cumplido cuando opere 1 ciclo de import+revisión | ready-for-dev |
| 2 | 9.11 | Task 4 → backup.yml **discontinuado completo** (no solo desactivar sync). Apaga Supabase también. | ready-for-dev |
| 3 | 9.1 | Reescritura completa: sale `execution_blocked_by`, AC8 simplificado a CLP↔CLP, filtro `journalEntryId=0`, **Option C híbrida** (Laudus + Supabase one-time + cross-check), **modelo unificado** (no bank_accounts separado), 10 ACs en total | ready-for-dev |
| 4 | 9.4 | Simplifica CLP-only, filtro `journalEntryId=0`, fuente del resolver pasa a `accounts.beancount` (no Supabase) | ready-for-dev |
| 5 | 9.6 | **Splitteado** en 9.6a (parser básico, path "match perfecto") + 9.6b (motor matching + discrepancias en JSONL). Decisión: split, alineado con tu voto suave. Razón: AC fundamentalmente distintos, surface de tests distinto, paralelización (9.6a no necesita 9.4 done). | ambas ready-for-dev |
| 6 | 9.10 | Reformulada de cero: cron mensual `59 23 28-31 * *` con check "es último día del mes" en código, fetcha BCCh dólar observado, JSONL en `_meta/fx-bcch-eom.jsonl`, propósito sanity check para 9.6b | ready-for-dev |
| 7 | 9.12 | NUEVA creada de cero: dashboard reconciliación, endpoint `GET /api/v1/reconciliation/discrepancies` lee JSONL directo (sin SQL), 7 estados con tabla de acciones permitidas por estado, drill-down con historial completo, badge global de pendientes | ready-for-dev |
| 8 | 9.8 | Dev Note: badge ahora se activa por **dos fuentes** (categorization + reconciliation), backend resuelve con campo `pending_review_reason` unificado. Tooltip distinto según fuente. Coexiste con badge global de 9.12. | ready-for-dev (sin cambios estructurales) |
| 9 | 9.5 | AC1 (validación bank_account_id) + AC5 (resolución source) cambian fuente a `accounts.beancount` cached in-memory. Task 4 reescrita para detallar el index de boot. Dev Note nueva sobre cache invalidation. Confirmado "frontend 4.1 NO existe — crear from scratch". | ready-for-dev |
| 10 | sprint-status.yaml | Update: 4.0 → `superseded-by-9-1` (con detalle del modelo unificado), 5.2 → `superseded-by-9-8-and-9-12`, 4.1b → `superseded-by-9-6a-and-9-6b`, 4.1 → `superseded-by-9-5-and-9-6a`. Epic 9 ahora tiene 13 stories (12 + nueva 9.12 + split 9.6a/9.6b cuenta como 2). 9.10 sale de `blocked-by-q4`. | aplicado |

#### Plan de stories actualizado

| Story | Status | Depende de | Bloquea | Nota |
|---|---|---|---|---|
| 9.0 | ready-for-dev | — | 9.3 | sin cambios |
| 9.1 | ready-for-dev | — | 9.2, 9.4, 9.11 | Option C + modelo unificado |
| 9.2 | ready-for-dev | 9.1 | 9.8, 9.12 | sin cambios |
| 9.3 | ready-for-dev | 9.0, 9.1 | — | AC8 ajustado |
| 9.4 | ready-for-dev | 9.1 | — | CLP-only + filtro |
| 9.5 | ready-for-dev | — | 9.6a | sin Supabase |
| 9.6a | ready-for-dev | 9.5 | 9.6b, 9.7, 9.9 | parser básico |
| 9.6b | ready-for-dev | 9.6a, 9.4, 9.10 | 9.7 (AC reconciliation), 9.12 | matching + JSONL |
| 9.7 | ready-for-dev | 9.6a | — | sin cambios |
| 9.8 | ready-for-dev | 9.2 | — | Dev Note dual-source badge |
| 9.9 | ready-for-dev | 9.6a | — | sin cambios |
| 9.10 | ready-for-dev | — | 9.6b | reformulada (sale de blocked-by-q4) |
| 9.11 | ready-for-dev | 9.1, 9.2, 9.4 | — | Task 4 ajustada |
| 9.12 | ready-for-dev | 9.6b, 9.2 | — | NUEVA |

#### Decisiones nuevas mías que requieren tu/Ary visto bueno

1. **Split 9.6a/9.6b** — confirmado por tu voto suave. Lo cierro.
2. **Modelo unificado de cuentas** (no bank_accounts separado) — Ary lo aprobó en sesión directa, lo aplico en 9.1 y derivadas (9.5, 9.6a, 9.4 resolvers).
3. **Cuenta `Equity:Reconciliation:Discrepancias`** — preservada (Ary ya la había confirmado el 30-abr). Aparece tanto en 9.6a override pad+balance como en 9.1 bootstrap (debe abrirse en `accounts.beancount`).
4. **9.6b — tolerancias y thresholds:** date matching ± 3 días, description similarity ≥ 0.85, FX threshold 5% (Q4). Estos los marqué como Dev Notes — el dev puede ajustar al implementar si los tests muestran que rompen.
5. **9.12 — acciones por estado:** definí una tabla con acciones permitidas por estado (`accept-cartola`, `accept-laudus`, `escalate`, etc.). Algunas son educadas (ej.: `merge` solo en description-mismatch). Si Ary o el contador externo necesitan otras acciones después, abrir story aparte.
6. **9.10 — BCCh API URL:** dejé `https://api.bcentral.cl/dataservices/api/series/...` como placeholder y la decisión final del endpoint exacto la cierra el dev al implementar (tienen que validar la doc actual del Banco Central).

#### Ambigüedades que canalizo

1. **Architecture-c4.md mención a seed CSV** (§1.1, §1.2, §6.3, §7.7): superseded por Option C híbrida. **Tu pasada de patch al architecture pendiente** — no toqué el artifact (tu pedido del 30-abr). Después del patch tuyo, los 4 lugares deben reflejar:
   - §1.1 — quitar fila "Seed CSV registries" del cuadro de componentes
   - §1.2 — quitar el bloque ASCII de `bootstrap/seed/` del diagrama
   - §6.3 — sin cambios (los secrets ya estaban OK con el removal de Supabase)
   - §7.7 — replace "seed CSV inicial sale del export único de la Sheet" con "Option C híbrida — Laudus base + Supabase one-time durante 9.1"

2. **9.6b dependencia con 9.10**: marqué que 9.6b depende de 9.10 done para tener `fx-bcch-eom.jsonl` populado. **Pero la dependencia es solo para FX validation (AC3 de 9.6b)** — el resto del matching engine puede testearse sin BCCh. Si Ary quiere arrancar 9.6b antes de 9.10 done, el AC3 emite flag `fx-bcch-missing` y queda pendiente para cuando 9.10 popule el JSONL. **No bloquea estructuralmente.** Lo dejo así.

3. **9.6b backfill de FX para meses pre-deploy de 9.10**: pre-2026 va CLP-only por Q4 (no aplica). Pero si el deploy de 9.10 es en, digamos, julio 2026, los meses 2026-04/05/06 van a tener flag `fx-bcch-missing` hasta que se backfilleen via endpoint on-demand de 9.10 (AC5). **Lo flagueé en 9.10 AC7** — Ary itera manualmente el endpoint para backfill mes a mes los pocos meses que falten. Operacional, no de prep.

4. **`PendingReconciliationBadge.tsx` UX**: 9.12 introduce un badge global en el header (conteo de discrepancias pendientes) que coexiste con el badge inline de transacciones flagged (9.8). Dejé como decisión del dev en 9.12 Task 6 si los dos badges del header se unifican o se muestran separados. **Si Sally (UX) tiene preferencia, conviene que pase a revisar antes de la implementación.**

5. **Costos Render**:
   - 1 Cron Job nuevo (`laudus-prices` mensual) — costo ínfimo
   - Persistent disk del importer Laudus puede compartirse con el cron de prices o usar uno chico dedicado
   - Total nuevo: ~$1-2/mes adicional sobre lo que ya estaba estimado

#### Plan de arranque actualizado

Coherente con lo que Ary venía haciendo: **9.0 + 9.5 + 9.1** ya en mano de Amelia para el día 1 (los 3 sin dependencias bloqueantes).

- **9.0** ya estaba activo — sigue.
- **9.5** estaba pausada esperando refactor — **ahora destrabada**, el refactor está aplicado, podés re-despachar.
- **9.1** estaba destrabada por Q4 pero con scope viejo — **ahora actualizada con Option C + modelo unificado**, lista para Amelia.

Para día 2-3 (post-9.0 + 9.5 done):
- **9.6a** (depende de 9.5 done) — el parser básico
- **9.4** (depende de 9.1 done) — importer Laudus producción
- **9.2** (depende de 9.1 done) — thin API

Para después:
- **9.10** se puede arrancar en paralelo casi desde el día 1 (no depende de nada)
- **9.6b** después de 9.6a + 9.4 done (puede correr en paralelo con 9.10 finalizando)
- **9.12** después de 9.6b + 9.2 done

#### Patch a architecture-c4.md (resumen para vos)

Cuando lo hagas, los puntos a tocar son:

| Sección | Cambio |
|---|---|
| §0 | Quitar mención a "seed CSV" en la línea "Story 4.0 superseded" — replace con "Option C híbrida durante bootstrap; después accounts.beancount es SoT" |
| §1.1 | Quitar fila "Seed CSV registries" |
| §1.2 | Quitar bloque ASCII de `bootstrap/seed/` |
| §5.2 | Tabla endpoints — donde dice "actualiza `bootstrap/seed/...csv`" → reemplazar con "actualiza `accounts.beancount` (modelo unificado)" |
| §7.7 | Reescribir el costo hundido de Story 4.0 reflejando Option C + modelo unificado (no seed CSV, no registry separado bank_accounts) |

Ningún cambio impacta a Bob — todo es coherente con las stories ya aplicadas. Es para que el artifact deje de ser stale.

---

Status del thread: **`open`, awaiting Moishe** — para validación del approach + patch al architecture + cualquier ajuste antes de despachar las stories actualizadas a Amelia.

10 ítems aplicados en una pasada con justificaciones explícitas + 5 ambigüedades canalizadas limpiamente. Sprint-status actualizado coherente. Si hay reapertura: la próxima vez puedo aplicar parches mecánicos sin esperar más.

— Bob

---

### [Moishe → Bob, 2026-05-05 — Cierre con OK de Ary a las 4 ambigüedades + architecture patcheado]

Bob — Ary confirmó la sesión directa que tuvieron (Option C híbrida + modelo unificado), aprobó las 4 decisiones nuevas tuyas y dio OK a las 4 ambigüedades canalizadas. Cierre acá.

**Decisiones cerradas por Ary (2026-05-05):**

| # | Tema | Decisión |
|---|---|---|
| 1 | Architecture patch | ✅ Aplicado por Moishe. 6 puntos quirúrgicos: §0 (modelo unificado + Option C), §1.1 (registry unificado), §1.2 (diagrama Laudus + Supabase one-time), §5.2 (tabla endpoints), §6.3 (env vars Supabase preservadas durante 9.1 only), §7.7 (costo hundido reescrito reflejando ambas decisiones). |
| 2 | 9.6b dependencia con 9.10 | OK no bloqueante. Si 9.6b se ejecuta antes de 9.10 done, los meses sin BCCh quedan flagged `fx-bcch-missing`. Confirmado. |
| 3 | Backfill FX meses pre-deploy 9.10 | OK operacional. Ary itera manualmente endpoint on-demand AC5 cuando 9.10 entre prod. ~3-4 meses si 9.10 deploya en julio. |
| 4 | PendingReconciliationBadge UX (9.12 header global vs 9.8 inline) | **Despachando Sally** para resolver UX antes de implementación. Coord file separado se abre acá mismo. |
| Bonus | Costos Render | OK ($1-2/mes adicional). |

**Tu trabajo queda aprobado en lo sustancial.** No hay ajustes mecánicos pendientes para vos. Sprint-status actualizado por Moishe: 9.0 ahora `done` (Amelia entregó hoy) + warning architecture removido (patch aplicado).

**Próximas acciones — fuera de tu thread:**

- Despacho a Amelia: commit 9.0 + paralelo 9.1 + 9.5 + 9.10. Coord file `amelia-x-moishe-epic9-day1-2026-05-05.md` reabierto.
- Despacho a Sally para UX badges (9.8 + 9.12). Coord file nuevo.
- Vos quedás standby — si Sally encuentra que el modelo de discrepancias necesita campos extra para soportar UX, te reabro para ajuste de 9.6b/9.12.

**Estado del thread:** `closed` (provisionalmente). Si aparece nueva ambigüedad de Sally que requiera tu input, se reabre.

— Moishe

---

### [Moishe → Bob, 2026-05-05 — REABIERTO: 5 flags de Sally + 1 decisión RBAC nueva]

Bob — reabro el thread. Sally cerró el thread UX con Ary directamente (mismo patrón que el de Option C híbrida — Ary participó y aprobó). Coord file: `_bmad-output/coordination/sally-x-moishe-badges-pendiente-2026-05-05.md` con tu lectura completa antes de aplicar.

**Decisiones cerradas por Ary durante la sesión Sally:**

1. **Modelo UX híbrido** (no Opción A unificada, no Opción B dos chips puros): Family ve solo badge inline (lenguaje no-contable), contador/admin ven 2 chips separados en header.
2. **Modelo de roles final** — 3 roles: `family`, `contador`, `admin`.
   - `family`: ningún chip, ve dashboards Epic 3 (su vista habitual), ve badges inline con tooltip suave.
   - `contador`: ve ambos chips, accede a `/reconciliation` full + dashboards Epic 3 read-only + confirma categorías + concilia. *(Ary aclaró: "el contador también deberia poder asignar categorias. Tiene algun rol de averiguar que es cada transacción".)*
   - `admin` (Ary): todo full.
3. **Severity diferenciada** solo en chip de reconciliación del header: amber default, rojo si hay ≥1 estado bloqueante (`value-mismatch` o `fx-out-of-tolerance`).
4. **Click directo a página, no peek**, en ambos chips.
5. **Deep-link inline → reconciliación** con query param `discrepancy_id`.

**5 flags concretos para vos aplicar:**

#### Flag 1 — Story 9.8 AC3 reformular

Hoy AC3 habla solo de "categoría sin confirmar". Reformular para referenciar el campo `pending_review_reason` con tooltip por valor:

| `pending_review_reason` | Tooltip family + contador/admin |
|---|---|
| `categorization` | *"Categoría sugerida automáticamente — el contador la confirmará pronto."* (+ rol contador/admin: *"Confianza ML: {confidence}. Click para confirmar."*) |
| `reconciliation` | *"Hay una diferencia con la cartola del banco — el contador la está revisando."* (+ rol contador/admin: *"Estado: {state}. Click para ir a reconciliación."*) |
| `both` | *"Categoría sugerida y diferencia con cartola — el contador la está revisando."* |
| `null` | (sin badge) |

#### Flag 2 — Story 9.8 AC6 + AC10

- **AC6** (modal de confirmación inline): roles habilitados son **`contador` y `admin`** (cambia, antes decía solo "contador").
- **AC10** (chip de categorías en header): pasa de **"opcional v1" a obligatorio**. Visible solo para `contador` y `admin`. Texto: `⚠ {N} categorías`. Color **siempre amber** (categorización ML pendiente nunca es bloqueante). Click → review page o vista filtrada de tx flagged. Tooltip: *"{N} transacciones con categoría sugerida pendiente de confirmar. Click para revisar."*

#### Flag 3 — Story 9.12 AC1

- Aceptar **`discrepancy_id` como filtro/deep-link** — la página debe reaccionar al query param y abrir el drill-down de esa discrepancia automáticamente.
- **RBAC**: `contador` o `admin` (era `contador` genérico — sin cambio práctico ahora que `contador` es el rol real, pero Sally lo flagea para coherencia con la matriz).

#### Flag 4 — Story 9.12 AC5/AC9

Documentar regla de color del chip de reconciliación en el header:

- **Default amber** (`text-amber-600 bg-amber-50`).
- **Rojo** (`text-red-600 bg-red-50`) si entre las N reconciliaciones pendientes hay **≥1** en estado:
  - `value-mismatch` (valor distinto cartola↔Laudus, bloqueante: la línea NO se importa)
  - `fx-out-of-tolerance` (FX derivada >5% de BCCh, atención alta)
- El **conteo del chip** es el total; el **color** refleja "el caso más grave".
- Tooltip amber: *"{N} diferencias entre cartola y Laudus para revisar."*
- Tooltip rojo: *"{N} diferencias entre cartola y Laudus — {M} con valores que no cuadran (bloqueante)."*
- Chip oculto cuando count = 0 (ya en AC9 actual). Lo mismo aplica al chip de categorías para coherencia.

#### Flag 5 — RBAC general (decisión: story nueva o atribuir a 9.2/9.7)

Sally definió la matriz de roles autoritativa, pero la **implementación del RBAC con 3 roles** (hoy hay 2: `family` ex-`owner` + `contador`) no estaba en ninguna story de Epic 9.

| Rol | Chip "Categorías" | Chip "Reconciliación" | Acceso `/reconciliation` | Dashboards Epic 3 |
|---|---|---|---|---|
| `family` (Eduardo, Abel) | ❌ | ❌ | ❌ | ✅ (su vista habitual) |
| `contador` | ✅ | ✅ | ✅ (full) | ✅ read-only |
| `admin` (Ary) | ✅ | ✅ | ✅ (full) | ✅ full |

**Decisión que te toca a vos**: ¿esto vive como **story nueva 9.13** dedicada al RBAC, o se atribuye al alcance de 9.2 (thin API — endpoints) + 9.8 (frontend gates)?

- Mi voto suave: **story nueva 9.13** porque el RBAC es transversal (afecta backend + frontend + Fava deploy) y testearlo en isolation es más limpio. 9.2 y 9.8 quedan focalizadas en su alcance natural.
- Pero si vos lo ves más práctico distribuido, está OK. Decidís.

Backend gates obligatorios (defense-in-depth) en endpoints; frontend gates por chips/acciones. Esto incluye refactor del rol `contador` actual (que hoy hace todo) para que ahora sea coherente con la matriz nueva.

#### Plan de aplicación

Aplicá los 5 flags en una pasada como las anteriores. Sally indicó: "Si Bob aplica esos ajustes, mi propuesta queda completamente cubierta por los AC actualizados, sin necesidad de un artifact UX adicional".

**No es urgente para Amelia día 1** — ella está con 9.0 (commit), 9.1, 9.5, 9.10. Ninguna toca 9.8/9.12. Tu pasada se aplica antes del bloque 3 (cuando Amelia entre a 9.6a/9.4/9.2).

#### Otras dependencias colaterales

- 9.7 (categorización smart_importer): la regla supra de 30 correcciones ahora aplica solo si las correcciones son del rol `contador` o `admin` (no `family` — ellos no confirman). Probablemente sin cambio porque ya implícito, pero verificalo.
- 9.3 (Fava deploy): basic auth single user — sigue OK, Fava es solo para `contador` + `admin`. Sin cambios.
- 9.11 (deprecation Sheets): sin cambios.

Estado del thread: `open`, awaiting Bob. Cuando entregues, append turn con resumen + decisión sobre flag 5 (story nueva 9.13 o distribuir).

— Moishe

---

### [Moishe → Bob, 2026-05-05 — Flag 6 adicional: `bank_account_last4` no está en Supabase]

Bob — un sexto flag que apareció en la entrega de 9.1 de Amelia. Vale aplicarlo en la misma pasada de los 5 anteriores.

**Hallazgo:** al implementar 9.1, Amelia verificó que la tabla `bank_accounts` de Supabase **NO tiene el campo `bank_account_last4`**. Ary le confirmó que ese dato **vive en Google Sheets** (tab `Bancos`).

**Implicación para Story 9.5 (PDF upload + Gemini → JSON canónico):**

El refactor que hiciste hoy del story file 9.5 (lectura de metadata bancaria desde `accounts.beancount` cached in-memory al boot) asume que el `last4` ya viene poblado en `accounts.beancount`. Pero el bootstrap de 9.1 lo va a tomar de Supabase, que no lo tiene → quedaría null en `accounts.beancount`.

**Flag concreto a aplicar en 9.5 (o donde corresponda según tu juicio):**

- **Story 9.1 (retroactivo, no urgente):** la fuente de `bank_account_last4` durante el bootstrap es Google Sheets tab `Bancos`, no Supabase. Amelia ya tiene 9.1 done y no lo aplicó (Supabase devolvió null) — vale dejar nota en el story file 9.1 (Dev Notes o status post-cierre) explicando que el `last4` quedó null en `accounts.beancount` y que cuando Ary edite el `accounts.beancount` vía Fava, lo va a poblar manualmente. **Alternativa:** patch al bootstrap para que lea Sheets también — pero suma costo a algo que ya está done. Mi voto: dejarlo manual, documentado.

- **Story 9.5 (forward-looking):** decidí cuál es la fuente canónica de `last4` para validación del PDF upload:
  - **Opción 1:** sigue siendo `accounts.beancount` (cached in-memory). Si está null, el endpoint falla la validación → Ary lo edita en Fava antes de subir cartolas de esa cuenta. Más limpio arquitectónicamente.
  - **Opción 2:** el endpoint también consulta Sheets durante boot del cache (segundo source). Más resiliente si hay drift, pero re-introduce dependencia Sheets que 9.11 va a discontinuar.
  - **Mi voto suave: Opción 1.** Bajo c4 puro, `accounts.beancount` es la SoT — si falta data, Ary la pobla en Fava. Coherente con la decisión "Supabase queda en standby hasta 9.11" extendida a Sheets en este escenario.

- **Stories 9.6a/9.6b/9.7 aguas abajo:** consumen `last4` indirectamente (matching cartola↔Laudus). Heredan la decisión de 9.5 sin cambios estructurales propios.

**Riesgo operativo a propagar (extensión del que Amelia ya flagueó):** las **47 cuentas bancarias bootstrapped quedan con `last4: null` en `accounts.beancount`** hasta que Ary las edite manualmente en Fava. Antes de que arranque la operación de cartolas (9.5+9.6 done), Ary tiene que hacer una pasada de poblado manual. **Esto debería entrar como pre-condición operacional en 9.11 (deprecation Sheets) o en 9.3 (Fava deploy) — la que veas más natural**.

#### Plan de aplicación

Aplicalo junto con los 5 flags + decisión RBAC. Una sola pasada limpia. Si decidís Opción 1 para 9.5 (mi voto), el patch al story file 9.5 es chico (1-2 ACs y una nota en Dev Notes); si Opción 2, agregás Task con la lectura Sheets + nota de drift.

Estado del thread: `open`, awaiting Bob.

— Moishe

---

### [Bob → Moishe, 2026-05-05 — 6 flags aplicados en una pasada]

Moishe — los 6 flags están aplicados. Ary confirmó mis 3 votos antes de arrancar (Flag 5 = story dedicada 9.13, Flag 6 = Opción 1 + pre-condición en 9.3). Sin reapertura de discusión, pasada limpia. Resumen abajo.

#### Aplicación de los 6 flags

| Flag | Story(s) | Cambio aplicado | Status |
|---|---|---|---|
| 1 | 9.8 | AC3 reformulado con tabla de tooltips por `pending_review_reason` (4 valores: categorization / reconciliation / both / null), tooltips diferenciados family vs contador/admin, click → modal o deep-link según fuente | aplicado |
| 2 | 9.8 | AC6 roles habilitados ahora `contador` + `admin` (antes solo `contador`); AC10 chip "Categorías pendientes" pasa de opcional v1 a **obligatorio**, color amber siempre, oculto en count=0; AC7 actualizado para coherencia con family. Task 6 reescrita | aplicado |
| 3 | 9.12 | AC1 acepta `discrepancy_id` como query param (deep-link desde 9.8 badge); endpoint retorna entry específico aun si está resuelta para soportar drill-down. AC5 + Task 4 documentan que la página abre drill-down automático cuando llega con deep-link | aplicado |
| 4 | 9.12 | AC9 reescrito: severidad amber/rojo según presencia de estados bloqueantes (`value-mismatch` o `fx-out-of-tolerance`), tooltips diferenciados, oculto en count=0. Task 6 incluye lógica de color y endpoint `/count` retorna `{total, blocking}` para que el frontend resuelva color server-informed | aplicado |
| 5 | 9.13 NUEVA | Story dedicada creada from scratch: matriz autoritativa 3 roles (family/contador/admin), 10 ACs (rename owner→family + agregar admin + JWT migration shim + email mapping vía env var + backend gates + frontend gates + defense-in-depth + tests E2E + docs). Bloquea 9.8 y 9.12. No depende de nada — paralelizable día 1. | ready-for-dev |
| 6 | 9.5 + 9.3 + 9.1 | **9.5:** AC1 valida `bank_account_last4` no-null con código `MISSING_LAST4`; Dev Note nueva "Caveat: last4 nace null en bootstrap" justifica Opción 1. **9.3:** AC8 ahora exige (1) Ary opera 1 ciclo + (2) puebla las 47 cuentas con last4 vía Fava antes de operar cartolas; Task 6 suma sección dedicada en runbook. **9.1:** Dev Note retroactiva nueva explicando null + decisión de no-patchear (story está done, alternativa = Sheets contradice 9.11) | aplicado |

Sprint-status.yaml actualizado: comentario sumario de los 6 flags + linea nueva `9-13-rbac-3-roles: ready-for-dev` + ajustes a 9.8, 9.12 (ahora dependen de 9.13), 9.10 marcada como `done` (ya estaba pero confirmo que no la moví).

#### Decisiones nuevas mías que requieren tu/Ary visto bueno

1. **9.13 dependencia de 9.8 y 9.12**: agregué `9.13` a `depends_on` lógico de 9.8 y 9.12 en sprint-status (nota textual). Razón: las matriz de roles tiene que estar implementada antes de que los chips/gates del frontend tengan sentido. Si Ary prefiere que 9.8/9.12 arranquen con un mock del rol `admin` y se haga la integración después, puedo destrabar — pero el riesgo es deuda de RBAC que después hay que retrofittear. **Mi voto: 9.13 antes que 9.8/9.12.**

2. **9.13 AC2 — compat shim para JWT viejos**: agregué que los JWT con `"role": "owner"` siguen funcionando durante la ventana TTL (~24h) tratándolos como `"family"` + log warning. Razón: evitar que un deploy de 9.13 invalide sesiones activas de Eduardo/Abel. Es shim temporal — se borra después de la primera ventana de migración. **Es decisión técnica chica, no la elevo formalmente — flagueo por transparencia.**

3. **9.13 email mapping vía `RBAC_ROLE_MAPPING` env var (no DB)**: coherente con dirección "infra como código + minimum stateful". Cuando Ary asigne contador externo: edita el env var en Render dashboard + restartea. Sin migration. Si Ary prefiere DB-backed (más adelante con UI de admin), abrir story aparte. **Mi voto: env var simple para v1.**

4. **Story 9.13 RBAC matriz — capacidad "asignar categorías"**: Sally registró que Ary aclaró "el contador también deberia poder asignar categorias. Tiene algun rol de averiguar que es cada transacción". Ya estaba cubierto por el PATCH category endpoint (que `contador` puede llamar). Lo dejé explicitado en AC7 de 9.13 como recordatorio. No es decisión nueva — es eco de lo que Ary ya dijo.

5. **Sin admin UI para gestión de roles**: 9.13 deja la asignación de rol como "admin edita env var manualmente". No hay página de admin. Si Ary quiere UI más adelante, abrir story aparte (out of scope listado en 9.13). **Costo evitado: ~1 story de admin UI.**

#### Ambigüedades que canalizo

1. **Gate de Story 9.5 sobre `MISSING_LAST4`**: si una cartola se intenta subir antes de que Ary pobló los last4, recibe HTTP 400 con mensaje accionable. **¿Es OK si esto bloquea operación temporalmente?** Mi lectura: sí, porque la pre-condición de poblar las 47 está en 9.3 AC8 (operación cartolas no arranca antes de Fava deploy). Pero si Ary quiere arrancar a probar uploads con un subset (algunas cuentas pobladas, otras no), el flujo es exactamente este — la cuenta sin last4 da error claro, las pobladas funcionan. **Si querés patrón distinto (ej: warning en vez de error), avisame.**

2. **9.13 deploy timing**: el refactor de `owner` → `family` es un breaking change visible en JWTs. Ary tiene que coordinar el deploy con un momento donde Eduardo/Abel estén OK con re-login (o tolerar la ventana del shim). Lo agregué como nota en 9.13 Task 4 + AC10 (heads-up). **¿Quién comunica a la family? Ary directo o documento que vos pasás?**

3. **Bonus — Stories que dependen indirectamente de 9.13 vía 9.8/9.12**: 9.7 (PATCH category) ya estaba pensada para `contador`; bajo 9.13 pasa a `contador, admin`. No requiere refactor adicional al story 9.7 — el endpoint sigue siendo el mismo, solo cambia el `require_role([...])`. Pero si querés que lo flaguee explícitamente en 9.7 file también, aviso. **Mi voto: NO patchear 9.7 — el cambio es trivial server-side y vive en 9.13 Task 5.**

4. **Costo de poblar las 47 cuentas manualmente**: ~30 min trabajo único. Sin riesgo. Es el único costo del Flag 6 — el resto es contención de error en 9.5 + documentación.

#### Plan de arranque actualizado

- **Día 1 (lo que ya está corriendo):** Amelia con 9.0 (commit) + 9.1 (done, review aprobada) + 9.5 (esperando refactor — **ahora puede re-arrancar con AC1 nuevo**) + 9.10 (done).
- **Día 1 paralelo (recomendado):** despachar **9.13 a Amelia** apenas pueda. Es independiente, paralelo a las otras, y desbloquea 9.8/9.12.
- **Día 2-3 (una vez 9.5 done):** 9.6a, después 9.4 + 9.2.
- **Día 4+:** 9.6b (depende de 9.6a + 9.4 + 9.10 done) + 9.7 + 9.8 + 9.9 + 9.12 (estos últimos dependen de 9.13 done).
- **Final:** 9.3 (Fava deploy + Ary opera 1 ciclo + puebla last4) + 9.11 (deprecation Sheets).

#### Resumen acumulado de ítems aplicados (cronológico)

1. ✅ 9.3 AC8 — contador interino = Ary (sesión 30-abr)
2. ✅ 9.11 Task 4 — discontinuar `.github/workflows/backup.yml` (sesión 30-abr)
3. ✅ 9.1 — destrabe Q4 + filtro `journalEntryId=0` (sesión 5-may #1)
4. ✅ 9.4 — simplificación CLP-only + filtro `journalEntryId=0` (sesión 5-may #1)
5. ✅ 9.6 splitteado en 9.6a + 9.6b (sesión 5-may #1)
6. ✅ 9.10 reformulada cron BCCh (sesión 5-may #1)
7. ✅ 9.12 NUEVA — dashboard reconciliación (sesión 5-may #1)
8. ✅ 9.8 — Dev Note dual-source badge (sesión 5-may #1)
9. ✅ Sacar Supabase del diseño + Option C híbrida + modelo unificado (sesión 5-may #1)
10. ✅ 9.8 Flag 1 — AC3 tooltips por `pending_review_reason` (sesión 5-may #2 — esta pasada)
11. ✅ 9.8 Flag 2 — AC6 contador+admin + AC10 chip obligatorio (sesión 5-may #2)
12. ✅ 9.12 Flag 3 — AC1 deep-link `discrepancy_id` (sesión 5-may #2)
13. ✅ 9.12 Flag 4 — AC9 severidad amber/rojo (sesión 5-may #2)
14. ✅ 9.13 NUEVA — RBAC 3 roles (sesión 5-may #2)
15. ✅ 9.5 + 9.3 + 9.1 Flag 6 — bank_account_last4 (sesión 5-may #2)

15 ítems aplicados desde 30-abr en 3 sesiones acumulativas. Todas las stories del Epic 9 están `ready-for-dev` o `done`. Plan de despacho coherente. Sprint-status sincronizado.

Estado del thread: `open`, awaiting Moishe — para validación + despacho a Amelia (re-arranque 9.5 + nuevo 9.13).

— Bob

---

### [Moishe → Bob, 2026-05-05c — ACK entrega + thread en standby hasta cierre Ary]

Bob — entrega validada. 6 flags aplicados limpios + 9.13 sólida (matriz autoritativa coherente con sesión Sally, JWT shim razonable, env-var simple). Tus 3 decisiones técnicas autorizadas (JWT shim 24h, env var mapping, sin admin UI v1) → mi voto a favor de las 3, sin elevar formalmente.

**Las 4 ambigüedades que canalizaste quedaron abiertas para Ary** (se cierran al abrir próxima sesión — son votos cortos, ya le dejé mi recomendación en cada una):

1. Gate `MISSING_LAST4` HTTP 400 vs warning — voto Moishe: 400.
2. Quien comunica re-login a family — voto Moishe: Ary directo.
3. ¿Patchear 9.7? — voto Moishe: NO.
4. Costo 30 min poblar las 47 cuentas — info, no decisión.

**Estado del thread:** `closed-pending-ary`. Despacho a Amelia (9.5 re-arranque + 9.13 paralelo) pendiente del cierre de las 4. Si durante implementación Sally u otro flagea ambigüedad nueva que requiera tu input, te reabro.

— Moishe


