# Story 12.1: Cerrar la clasificación contable con Valentina

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Ary (dueño),
I want la clasificación contable del libro RUT2 cerrada y firmada con Valentina antes de construir nada,
so that el árbol de ~309 cuentas hoja se construya una sola vez y el reporte final responda la pregunta de negocio correcta.

## Acceptance Criteria

1. **Given** los dos pendientes contables abiertos del análisis 2026-06-30 (¿raíces 4 y 8 son P&L separados?; convención de la cuenta de Equity de apertura) — FGK/JAB ya resuelto por Ary 2026-07-10: una sola sub-entidad,
   **When** Valentina los resuelve,
   **Then** queda documentada la decisión de cada uno en un artefacto versionado en `_bmad-output/planning-artifacts/`, con fecha y fuente de cada decisión.
   > Estado real al crear esta story: raíces 4/8 YA respondidas por Valentina (2026-07-11, §5 del doc de contexto) — el artefacto las FORMALIZA. La convención de Equity de apertura es la única decisión genuinamente abierta.

2. **Given** el plan real de 357 cuentas (JSON persistido 2026-07-10),
   **When** se firma el mapeo raíz→(root Beancount, entidad),
   **Then** el artefacto cubre las 7 raíces (1/2/3/4 = FFCC, 6/7/8 = JAB) sin cuentas sin destino — verificado MECÁNICAMENTE contra el JSON (357/357 cuentas con raíz ∈ {1,2,3,4,6,7,8}, conteos por raíz y por sub-entidad que cierran).

3. **Given** que la story 12.3 consumirá este artefacto para generar el subárbol en `accounts.beancount`,
   **When** el artefacto queda firmado,
   **Then** contiene todo lo que 12.3 necesita sin re-derivar nada: mapeo por raíz, convención Equity de apertura (nombre de cuenta Beancount completo), labels de entidad (FFCC/JAB, grupo FondoComun — ya congelados por 11.2), las 2 cuentas TC marcadas (871005/873005), y el conteo autoritativo de hojas (309 según el JSON; los docs de planning dicen 308 — el artefacto fija el número correcto y anota la deriva).

## Tasks / Subtasks

- [x] Task 1: Consolidar las decisiones YA tomadas en borrador del artefacto (AC: 1, 3)
  - [x] Extraer del doc de Valentina 2026-07-11 (§5) la resolución de raíces 4/8: P&L separados como estructura de reporte; conceptualmente todo se financia del FFCC (raíz 4 = administrar el fondo, raíces 6–8 = gasto de la rama FGK)
  - [x] Registrar FGK/JAB = UNA sub-entidad (decisión Ary 2026-07-10, intake Sección 1-bis ítem C)
  - [x] Registrar labels congelados por 11.2 y ratificados vía Excel: entidades `FFCC` / `JAB`, grupo `FondoComun` (fuente: `backend/app/services/bql_queries.py` CONSOLIDATION_GROUPS + Excel devuelto 357/357 "SI", doc Valentina 2026-07-11 §6)
  - [x] Registrar las 2 únicas cuentas TC del libro: 871005 (JAB — probablemente SIN uso, verificar por movimientos al importar) y 873005 (FGK — activa, ~3 tarjetas en una cuenta), como gasto lumpeado estado-1 igual que EAG

- [x] Task 2: Cerrar la convención de Equity de apertura con Valentina (AC: 1, 3) — LA decisión abierta
  - [x] Invocar a Valentina (skill `agent-contadora`, patrón ya establecido en el proyecto) con el contexto de esta story para que adjudique la convención
  - [x] Insumos de la decisión (ver Dev Notes → "Precedente EAG y restricción técnica"): (a) EAG NO usa Equity para la apertura de Laudus — el JE "Saldo anterior" es self-balancing vía `Liabilities:EAG:Apertura-211005`; (b) el plan RUT2 TIENE `211005 Apertura` en raíz 2 (FFCC) → probablemente mismo mecanismo; (c) JAB NO tiene raíz de Pasivo ni Patrimonio → si su apertura necesita contrapartida, requiere cuenta Equity propia; (d) restricción técnica congelada por 11.1: toda Equity nueva DEBE llevar entidad como 2º segmento del path (ej. `Equity:FFCC:Apertura`) — la lista de namespaces sin entidad está congelada para el grupo EAG
  - [x] La convención firmada debe especificar: nombre(s) de cuenta Beancount completo(s), cuándo se usa (apertura FFCC / apertura JAB / plug residual), y la advertencia de Valentina 2026-07-11 §5: el monto puede ser un plug grande, NO interpretarlo como patrimonio real hasta la revisión post-import

- [x] Task 3: Verificación mecánica de cobertura contra el JSON (AC: 2)
  - [x] Script descartable (scratchpad, NO commitear al producto) que lee `_bmad-output/planning-artifacts/rut2-plan-cuentas-laudus-2026-07-10.json` y verifica: total = 357 cuentas; toda cuenta tiene raíz ∈ {1,2,3,4,6,7,8} (cero huérfanas); hojas = 309 (cuenta sin descendiente por prefijo); FFCC (raíces 1–4) = 118 y JAB (raíces 6–8) = 239; distribución por raíz: 1=30, 2=4, 3=11, 4=73, 6=16, 7=4, 8=219
  - [x] Volcar la tabla de conteos verificados al artefacto (evidencia de "sin cuentas sin destino")

- [x] Task 4: Escribir y versionar el artefacto firmado (AC: 1, 2, 3)
  - [x] Crear `_bmad-output/planning-artifacts/clasificacion-contable-rut2-firmada-{{date}}.md` con: (1) mapeo raíz→(root Beancount, entidad) — tabla de 7 filas; (2) decisiones firmadas con fecha y fuente (raíces 4/8, FGK/JAB, Equity apertura, labels); (3) tabla de cobertura verificada (Task 3); (4) TC marcadas; (5) nota de deriva 308→309 hojas; (6) sección explícita "Qué consume 12.3 de este doc"
  - [x] Referenciar (no duplicar) la doble pregunta de negocio del reporte que 13.1 debe contemplar (Valentina 2026-07-11 §5): (a) en qué gasta el fondo y en qué gasta FGK, por activo; (b) cuánto repartió el fondo y a quién (retiros por persona)
  - [x] Commitear el artefacto (acuerdo de retro Epic 6/7: commitear al cerrar cada story)

## Dev Notes

### Naturaleza de la story — leer primero

**Story SIN código de producto.** El entregable es UN artefacto markdown versionado en planning-artifacts que 12.3 consume para generar ~309 cuentas una sola vez. No se toca `backend/`, `frontend/`, `ledger/`, ni tests. No aplica bean-check (no se escribe al ledger). La "suite verde" de esta story = la verificación mecánica del Task 3.

**El epic fue redactado el 2026-07-10; los insumos maduraron después.** Estado real:
- ✅ Excel de clasificación DEVUELTO por Ary 2026-07-11: 357/357 filas confirmadas "SI", 2 TC marcadas (871005/873005), cero correcciones → mapeo mecánico y labels RATIFICADOS por el dueño
- ✅ Raíces 4/8 como P&L separados: respondido por Valentina 2026-07-11 (§5 del doc de contexto)
- ✅ FGK/JAB una sub-entidad: decidido por Ary 2026-07-10
- ⏳ Convención Equity de apertura: ÚNICA decisión abierta (Task 2)

Por project-context, la convención de Equity es decisión técnico-contable → se auto-aprueba con la recomendación de Valentina, sin gate de Ary. No detenerse a preguntar.

### Inventario de insumos (rutas exactas)

| Insumo | Ruta | Qué aporta |
|---|---|---|
| Plan RUT2 persistido | `_bmad-output/planning-artifacts/rut2-plan-cuentas-laudus-2026-07-10.json` | 357 cuentas reales de Laudus (accountId, accountNumber, name); fuente de la verificación mecánica |
| Clasificación técnica Valentina | `_bmad-output/planning-artifacts/valentina-clasificacion-rut2-fondo-comun-2026-06-30.md` | Mapeo raíz→Beancount, landmine TC, pendientes originales |
| Contexto de negocio Valentina | `_bmad-output/planning-artifacts/valentina-contexto-fondo-comun-jab-2026-07-11.md` | §5 resuelve raíces 4/8 y orienta Equity; §6 registra el Excel devuelto; watchlist post-import (NO ejecutarla ahora) |
| Intake con respuestas de Ary | `_bmad-output/planning-artifacts/discovery-segundo-rut-intake-2026-06-30.md` (Sección 1-bis) | Decisiones A–H de Ary 2026-07-10 (apertura = primeros asientos del libro; ancla = Laudus correcto) |
| Excel devuelto | `_handoff/Plan-Cuentas-RUT2-para-clasificar-2026-07-10.xlsx` | Ratificación 357/357 del dueño (citar, no re-procesar) |
| Epic breakdown | `_bmad-output/planning-artifacts/epics-segundo-rut.md` | FR48/FR49 y ACs de 12.3 que este artefacto alimenta |

### Precedente EAG y restricción técnica (núcleo del Task 2)

**Cómo cierra la apertura en EAG hoy:** el JE 140 de Laudus ("Saldo anterior") es **self-balancing vía `Liabilities:EAG:Apertura-211005`** — la cuenta 211005 "Apertura" del plan de EAG, espejo fiel de Laudus. NO se usa una cuenta Equity para la apertura del import de Laudus. Evidencia: `ledger/opening-2021.beancount` (comentario líneas 7–13, archivo vaciado a propósito), `ledger/imports/laudus/2021-01.beancount:11`, `ledger/accounts.beancount:309`. La única Equity de apertura que existe es `Equity:Apertura:TarjetasSinDetalle` (arrastre TC pre-2026, mecanismo de cartolas — otro dominio, no confundir).

**El plan RUT2 tiene el mismo patrón:** raíz 2 (PASIVO, FFCC) contiene 4 cuentas y es "prácticamente vacía (solo 211005 Apertura)" per Valentina 2026-06-30. Hipótesis de trabajo: la apertura de FFCC se importa self-balancing vía `Liabilities:FFCC:Apertura-211005` igual que EAG, y la cuenta Equity de FR49 queda como respaldo/plug si el libro no cierra (hipótesis de Valentina: "probablemente no hay apertura real" — contadores usan Laudus solo para gastos). **JAB no tiene raíz 2 ni patrimonio** → si aparecen saldos de apertura del lado JAB, necesitan contrapartida Equity propia. Valentina adjudica la forma final; el artefacto la firma.

**Restricción técnica NO negociable (congelada por 11.1, patch de code-review incluido):** toda cuenta Equity nueva DEBE llevar la entidad como 2º segmento del path — ej. `Equity:FFCC:Apertura`, `Equity:JAB:Apertura` — para que `_group_pattern` la asigne mecánicamente al grupo FondoComun. Los namespaces de Equity SIN entidad (`Equity:Apertura:*`, `Equity:Reconciliation:*`) son lista congelada que consolida al grupo EAG. Fuente: `backend/app/services/bql_queries.py:42-45` (`_ENTITYLESS_EQUITY_NAMESPACES`) y líneas 30–40 (`CONSOLIDATION_GROUPS`). Una Equity de RUT2 sin segmento de entidad se consolidaría en EAG en silencio = exactamente la contaminación que Epic 11 blindó.

**Convención de path para hojas (la usa 12.3, el artefacto debe ser consistente):** `{Root}:{Entidad}:{slug}-{código}` — ej. `Assets:FFCC:CajaUs-111003`, `Expenses:JAB:...-871005`. Fuente: AC de 12.3 en epics-segundo-rut.md + patrón existente en `ledger/accounts.beancount` (ej. `Liabilities:EAG:Apertura-211005`).

### Datos verificados del plan (para el Task 3 — no re-derivar, verificar)

Verificado 2026-07-11 contra el JSON al crear esta story: **total=357, hojas=309** (hoja = sin descendiente por prefijo de accountNumber). Distribución por raíz: 1→30, 2→4, 3→11, 4→73 (FFCC=118); 6→16, 7→4, 8→219 (JAB=239). Cero cuentas fuera de las 7 raíces. **Deriva documental:** el epic y FR48 dicen "308 hojas" (conteo de la sonda 2026-06-30); el JSON re-bajado 2026-07-10 da 309. El artefacto fija 309 como autoritativo y anota la deriva para que 12.3 no "corrija" contra el número viejo.

### Qué NO hacer (scope guard)

- NO crear cuentas en `accounts.beancount` — eso es 12.3 (consume este artefacto)
- NO tocar el importador ni `account_mapping.py` / `beancount_writer.py` — eso es 12.2
- NO diseñar el reporte de gastos RUT2 — eso es 13.1 (solo referenciar la doble pregunta de negocio)
- NO ejecutar la watchlist contable de Valentina 2026-07-11 §4 (retiros como CxC, ingresos ausentes, Reñaca, aviones/yates fantasma) — decisión Ary: post-import
- NO mintear `bank_account_id` — eso es 12.3 (los UUIDs los minteamos al crear las cuentas)
- NO pedir nada al contador — decisión Ary 2026-07-10: el contador ya no bloquea nada

### Inteligencia de stories previas (Epic 11)

- **11.1** (`11-1-grupos-consolidacion-explicitos.md`, done): estableció `CONSOLIDATION_GROUPS` y el aislamiento case-sensitive `(?-i:)`. Su TRAP #1 documentado: cuentas Equity sin segmento de entidad quedan fuera de un patrón ingenuo por grupo → por eso la restricción de path de Equity de arriba ES bloqueante para la convención que firme Valentina.
- **11.2** (`11-2-entidades-fondo-comun-frontend.md`, done): fijó los labels DEFINITIVOS `FFCC`/`JAB`/`FondoComun` en `VALID_ENTITIES` + selector, gate de labels resuelto vía el Excel ratificado — esta story NO re-abre labels, los cita como cerrados.
- Patrón de artefactos de Valentina: los 11 docs `valentina-*.md` en planning-artifacts salen del skill `agent-contadora`; mantener el mismo formato (fecha, contexto, decisión, evidencia).

### Project Structure Notes

- Artefacto de salida en `_bmad-output/planning-artifacts/` (patrón `clasificacion-contable-rut2-firmada-{{date}}.md`) — mismo directorio que sus insumos; sin conflictos de estructura.
- Script de verificación en el scratchpad de la sesión (descartable); si se prefiere reproducibilidad, el patrón del proyecto es `_bmad-output/planning-artifacts/_forense_*.py` (precedente: auditoría inversiones 2026-06-20) — a criterio del dev, NO en `backend/`.

### References

- [Source: _bmad-output/planning-artifacts/epics-segundo-rut.md#Story 12.1] — story y ACs originales; FR48/FR49
- [Source: _bmad-output/planning-artifacts/valentina-clasificacion-rut2-fondo-comun-2026-06-30.md] — mapeo mecánico, landmine TC, pendientes
- [Source: _bmad-output/planning-artifacts/valentina-contexto-fondo-comun-jab-2026-07-11.md#5] — resolución raíces 4/8 + orientación Equity; #6 Excel devuelto
- [Source: _bmad-output/planning-artifacts/discovery-segundo-rut-intake-2026-06-30.md#Sección 1-bis] — decisiones Ary A–H
- [Source: backend/app/services/bql_queries.py:30-45] — CONSOLIDATION_GROUPS + restricción Equity con entidad en el path
- [Source: ledger/opening-2021.beancount:7-13; ledger/imports/laudus/2021-01.beancount:11] — precedente apertura EAG self-balancing vía Liabilities:EAG:Apertura-211005

## Dev Agent Record

### Agent Model Used

claude-fable-5 (dev-story) + skill `agent-contadora` (Valentina) para la adjudicación del Task 2.

### Debug Log References

- Verificación mecánica Task 3: `verify_rut2_plan.py` (scratchpad de la sesión, descartable). Resultado PASS: 357 cuentas / 0 huérfanas / 0 duplicados / 309 hojas / FFCC 118 / JAB 239 / distribución 1→30, 2→4, 3→11, 4→73, 6→16, 7→4, 8→219 / TC 871005 y 873005 existen y son hojas.

### Completion Notes List

- Story SIN código de producto, ejecutada según Dev Notes: no se tocó `backend/`, `frontend/`, `ledger/` ni tests; "suite verde" = verificación mecánica PASS del Task 3.
- **Task 2 (LA decisión abierta):** Valentina adjudicó la convención de Equity de apertura (invocada vía skill `agent-contadora`, auto-aprobada por project-context como decisión técnico-contable): (1) apertura FFCC = self-balancing vía `Liabilities:FFCC:Apertura-211005` (espejo Laudus, precedente EAG, SIN Equity); (2) Equity de respaldo una por sub-entidad: `Equity:FFCC:Apertura` (plug residual) y `Equity:JAB:Apertura` (contrapartida de todo lo del lado JAB, que no tiene Pasivo ni Patrimonio); (3) entidad como 2º segmento obligatoria (restricción 11.1), namespaces sin entidad prohibidos; (4) regla nueva de la adjudicación: el plug nunca cruza entidades (protege el per-entity de 11.2); (5) advertencia plug-grande-≠-patrimonio propagada; (6) metadata para 12.3 especificada (cat1=PATRIMONIO, cat2/3 vacías, code sintético por (entidad,code), sin bank_account_id, declaración directa en accounts.beancount — precedente TC:Real).
- **Artefacto firmado:** `clasificacion-contable-rut2-firmada-2026-07-11.md` con las 8 secciones (mapeo 7 raíces, 5 decisiones con fecha+fuente, convención Equity completa, cobertura verificada, TC marcadas, deriva 308→309 fijando 309 autoritativo, doble pregunta de negocio referenciada para 13.1, sección "Qué consume 12.3").
- Hallazgo extra volcado al artefacto (útil para 12.3, no estaba en los conteos esperados): hojas por raíz 1→26, 2→1, 3→9, 4→63, 6→12, 7→2, 8→196 (FFCC 99 / JAB 210); la única hoja de raíz 2 es justamente 211005 Apertura.
- Decisión de adjudicación registrada también en el sanctum de Valentina (`_bmad/memory/agent-contadora/MEMORY.md` + `sessions/2026-07-11.md`) para continuidad entre sesiones.
- Se commitea junto con el artefacto su insumo citado `valentina-contexto-fondo-comun-jab-2026-07-11.md` (estaba sin trackear — las referencias del artefacto deben resolver en el repo).

### File List

- `_bmad-output/planning-artifacts/clasificacion-contable-rut2-firmada-2026-07-11.md` (nuevo — EL entregable)
- `_bmad-output/planning-artifacts/valentina-contexto-fondo-comun-jab-2026-07-11.md` (insumo citado, se versiona junto al artefacto; creado en sesión previa, sin cambios de contenido)
- `_bmad-output/implementation-artifacts/12-1-clasificacion-contable-valentina.md` (story file — secciones permitidas)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status de la story)
- `_bmad/memory/agent-contadora/MEMORY.md` (modificado — convención adjudicada)
- `_bmad/memory/agent-contadora/sessions/2026-07-11.md` (modificado — registro de la adjudicación)

## Change Log

- 2026-07-11: Story 12.1 implementada completa (dev-story). Convención Equity de apertura adjudicada por Valentina; verificación mecánica PASS (357/309/118/239); artefacto firmado `clasificacion-contable-rut2-firmada-2026-07-11.md` escrito y versionado. Status → review.
