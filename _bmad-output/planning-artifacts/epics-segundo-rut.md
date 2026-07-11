---
stepsCompleted: [step-01-validate-prerequisites, step-02-design-epics, step-03-create-stories, step-04-final-validation]
workflowStatus: complete
completedAt: '2026-07-10'
inputDocuments:
  - _bmad-output/planning-artifacts/discovery-segundo-rut-intake-2026-06-30.md
  - _bmad-output/planning-artifacts/valentina-clasificacion-rut2-fondo-comun-2026-06-30.md
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/planning-artifacts/architecture-c4.md
---

# family-office-eag — Segundo RUT (Fondo Común FFCC/JAB) — Epic Breakdown

## Overview

Este documento descompone en epics y stories la incorporación del segundo libro de Laudus (RUT placeholder `12.345.678-2`, Fondo Común de la rama JAB/FGK) como entidad hermana de EAG en el mismo ledger Beancount. Extiende el sistema existente; no lo reemplaza. El epic breakdown original del MVP (FR1–FR44) vive en `epics.md` y no se modifica.

**Arquitectura ya decidida (2026-06-30):** un solo código, un solo ledger, RUT2 como entidad hermana (no fork, no hija de EAG, sin auth nueva). Dos sub-entidades dentro del libro: **FFCC** (Fondo Común, raíces 1–4) y **JAB** (rama JAB/FGK, raíces 6–8).

**Numeración:** los FRs continúan desde FR44 del PRD original para mantener unicidad global.

## Requirements Inventory

### Functional Requirements

**1. Consolidación por grupos (guardrail — precondición de todo lo demás)**
- FR45: El sistema reemplaza el supuesto "EAG = todas las cuentas" por grupos de consolidación explícitos; el reporte/balance de EAG consolida únicamente [EAG + Jocelyn + Jeannette + Johanna + Jael] y no absorbe cuentas de otras entidades.
- FR46: El libro RUT2 forma su propio grupo de consolidación [FFCC, JAB], separado del grupo EAG; ningún reporte cruza grupos salvo pedido explícito futuro (vista combinada = fuera de alcance).

**2. Entidades y frontend**
- FR47: Los usuarios pueden filtrar dashboards y reportes por las entidades nuevas del libro RUT2 (FFCC, JAB y/o su grupo consolidado) desde el selector de entidad existente; las entidades quedan registradas en VALID_ENTITIES/FilterContext.

**3. Plan de cuentas RUT2**
- FR48: El árbol de cuentas de RUT2 (357 cuentas, 308 hojas) se crea en accounts.beancount derivado del plan real de Laudus, con el mapeo mecánico raíz→Beancount confirmado por Valentina (1=Assets, 2=Liabilities, 3=Income, 4=Expenses para FFCC; 6=Assets, 7=Income, 8=Expenses para JAB), y queda pre-creado ANTES de importar cualquier asiento.
- FR49: Existe una cuenta de Equity de apertura para el libro RUT2 (el plan no tiene raíz de patrimonio) de modo que el balance cierre tras importar la apertura, análogo a `Equity:Apertura` de EAG.

**4. Importador Laudus multi-libro**
- FR50: La entidad/libro es un parámetro explícito de la corrida de import (companyVATId, credenciales, subdirectorio destino); la entidad NUNCA se deriva de strings devueltos por Laudus.
- FR51: El importador rutea asientos por índice (entidad, código) en lugar de solo código, de modo que los 18 códigos en colisión (misma numeración, cuenta distinta) jamás posteen a cuentas de EAG.
- FR52: Antes de escribir, el importador verifica que el nombre de empresa devuelto por Laudus coincide con la entidad esperada de la corrida (Laudus no falla ante RUT equivocado); la validación NO usa dígito verificador (el RUT es placeholder con DV inválido por diseño).
- FR53: El sistema importa el histórico contable de RUT2 desde la fecha de corte confirmada por el contador, incluyendo el asiento de apertura ("Saldo anterior") ruteado a la cuenta de Equity de apertura.

**5. Reporte de gastos RUT2**
- FR54: Los usuarios pueden ver un reporte de gastos de RUT2 en dos niveles: (a) sub-entidad FFCC vs JAB; (b) grupos por encabezado numérico — FFCC: 41 Gastos Generales, 43 Gastos Fijos Oficina; JAB: 81 Casas, 83 Aviones, 85 Yates, 87 Gastos Personales — derivados mecánicamente de la jerarquía embebida en la numeración (8→81→811).
- FR55: El reporte de RUT2 presenta las tarjetas de crédito de JAB/FGK (871005, 873005) como gasto lumpeado con la limitación marcada (estado 1, igual que EAG); el desglose por cartola queda explícitamente fuera de alcance.

**6. Validación y confianza**
- FR56: El sistema reconcilia los saldos importados de RUT2 peso-por-peso contra un ancla de validación conocida (saldo bancario real o balance de Laudus a fin de mes, provista por el contador) antes de dar por buena la importación.

### NonFunctional Requirements

- NFR20: Aislamiento entre libros — ninguna corrida de import de RUT2 modifica cuentas, asientos ni saldos de EAG; los reportes de EAG son idénticos peso-por-peso antes y después de introducir el guardrail de consolidación (0 diffs de regresión).
- NFR21: `bean-check` sale en 0 tras cada paso que escribe al ledger (creación del árbol, apertura, cada import).
- NFR10 (heredado): las fallas de sync/import se loggean con detalle completo y no producen datos parciales o corruptos en silencio.
- NFR13 (heredado): el pipeline de import mantiene log append-only de cada corrida (timestamp, registros procesados, altas/updates, errores).
- NFR8 (heredado): credenciales de Laudus para el segundo libro se manejan igual que las existentes — nunca hardcodeadas ni commiteadas.

### Additional Requirements

Del análisis técnico (arquitectura c4 + sonda verificada 2026-06-30):

- `bql_queries.py`: reemplazar `_CONSOLIDATED_ENTITY="EAG"` por `CONSOLIDATION_GROUPS` explícito — es el ítem #1 del work breakdown y DEBE hacerse antes de meter cualquier dato de RUT2 (hoy "EAG" matchea todo el ledger).
- `beancount_writer.py` (`load_account_index`): el índice `{code→cuenta}` pasa a `{(entidad, code)→cuenta}` con entidad = parámetro de la corrida.
- `account_mapping.py`: separar el mapa en `categoria1→tipo-de-raíz` (compartido) vs `entidad = parámetro del import`; aguas abajo la entidad se deriva del path (2º segmento), no de strings de Laudus.
- `report_builder.py`: los prefijos 411/413/415/430 y labels son EAG-específicos → el reporte de RUT2 necesita plantilla propia parametrizada por entidad/grupo.
- `bank_account_id`: UUIDs internos por cuenta bancaria los minteamos nosotros en accounts.beancount (no vienen de Laudus).
- Mismas credenciales de Laudus (`administrador`) + swap de `companyVATId` cambia de libro — verificado con sonda read-only.
- Ingesta de cartolas PDF y desglose de TC de RUT2: DIFERIDOS — dependen de respuestas del contador (bancos, disponibilidad de cartolas) y de la decisión futura estilo Epic 6. No son parte de este breakdown.
- Vista combinada EAG+RUT2 ("a veces juntos"): futuro opcional, trivial una vez que los grupos son explícitos — no construir hasta que se pida.

**Dependencias externas abiertas (no bloquean el diseño de epics, sí bloquean stories específicas):**
- Contador: fecha desde la cual importar histórico; apertura/saldos iniciales; ancla de validación; lista de cuentas bancarias con banco/moneda/tipo.
- Valentina/contador: ¿FGK y JAB son una sub-entidad o dos?; confirmación raíz 4 y raíz 8 como P&L separados.
- Ary: label corto definitivo de las entidades en el sistema (FFCC / JAB / nombre del grupo del libro) — se fija al ejecutar la story 11.2.

### UX Design Requirements

No hay documento UX para este alcance. La única superficie visible nueva es la entidad adicional en el selector existente y el reporte de gastos de RUT2 reutilizando el patrón del reporte de EAG.

### FR Coverage Map

- FR45: Epic 11 — Grupos de consolidación explícitos (EAG deja de ser "todo el ledger")
- FR46: Epic 11 — Grupo RUT2 [FFCC, JAB] separado del grupo EAG
- FR47: Epic 11 — Entidades nuevas en VALID_ENTITIES/FilterContext y selector
- FR48: Epic 12 — Árbol de cuentas RUT2 pre-creado con mapeo mecánico por raíz
- FR49: Epic 12 — Cuenta de Equity de apertura del libro RUT2
- FR50: Epic 12 — Entidad/libro como parámetro explícito de la corrida de import
- FR51: Epic 12 — Índice (entidad, código) en el importador
- FR52: Epic 12 — Assert de nombre de empresa antes de escribir
- FR53: Epic 12 — Import de histórico + apertura (bloqueada por respuestas del contador)
- FR54: Epic 13 — Reporte de gastos dos niveles FFCC/JAB × grupos numéricos
- FR55: Epic 13 — TC lumpeada marcada en el cuerpo del reporte
- FR56: Epic 12 — Reconciliación contra ancla = criterio de cierre del epic (bloqueada por respuestas del contador)

Transversales: NFR20 (aislamiento, 0 diffs EAG) y NFR21 (bean-check verde) aplican como criterios de aceptación en Epics 11 y 12.

## Epic List

### Epic 11: Consolidación por grupos — blindar EAG y registrar las entidades nuevas
Los reportes de EAG dejan de asumir "EAG = todas las cuentas" y pasan a grupos de consolidación explícitos; FFCC y JAB quedan registradas como entidades válidas y visibles en el selector. Valor: garantía verificable de que nada de lo que venga después contamina los números de EAG (0 diffs peso-por-peso pre/post).
**FRs covered:** FR45, FR46, FR47
**Nota de secuencia operativa:** al arrancar este epic se envía la Sección 1 del intake al contador (paralelo, no bloqueante) — sus respuestas solo bloquean FR53 y FR56 del Epic 12.

### Epic 12: El libro del Fondo Común en el ledger — importación multi-libro validada
El árbol de cuentas de RUT2 (308 hojas) se pre-crea en el ledger; el importador Laudus se vuelve multi-libro (entidad como parámetro, índice entidad+código, assert de empresa) y trae el histórico + apertura. Valor: los números del Fondo Común están en el sistema, cuadran peso-por-peso, y son navegables por los dashboards existentes filtrando por entidad.
**FRs covered:** FR48, FR49, FR50, FR51, FR52, FR53, FR56
**Precondición interna (primera story del epic):** cerrar la clasificación con Valentina — ¿FGK y JAB una o dos sub-entidades?, ¿raíces 4 y 8 P&L separados?, convención de la cuenta de Equity de apertura — ANTES de pre-crear el árbol, para no reconstruir 308 cuentas.
**Definition of Done del epic:** no cierra sin reconciliación peso-por-peso contra el ancla de validación (FR56), con fallback definido: si el contador no provee saldo bancario, se usa el balance de Laudus a fin de mes.

### Epic 13: Reporte de gastos del Fondo Común (FFCC / JAB)
Reporte de gastos con plantilla propia de RUT2 en dos niveles: FFCC (41 Gastos Generales / 43 Gastos Fijos Oficina) vs JAB (81 Casas / 83 Aviones / 85 Yates / 87 Gastos Personales), derivado mecánicamente de la jerarquía embebida en la numeración. Las TC de JAB/FGK (871005, 873005) se muestran como gasto lumpeado con la limitación marcada en el cuerpo del reporte, no en nota al pie. Valor: responde "¿en qué gasta el Fondo Común y en qué gasta JAB/FGK?" — la misma pregunta que el reporte de EAG.
**FRs covered:** FR54, FR55

**Dependencias entre epics:** cadena natural 11 → 12 → 13; cada epic cierra con valor propio y no requiere el siguiente para funcionar. La numeración salta el Epic 8 (reservado para email/notificaciones) y los Epics 9–10 ya ejecutados.

## Epic 11: Consolidación por grupos — blindar EAG y registrar las entidades nuevas

Los reportes de EAG dejan de asumir "EAG = todas las cuentas" y pasan a grupos de consolidación explícitos; FFCC y JAB quedan registradas como entidades válidas y visibles en el selector. Valor: garantía verificable de que nada de lo que venga después contamina los números de EAG. Nota operativa: al arrancar este epic se envía la Sección 1 del intake al contador (paralelo, no bloqueante).

### Story 11.1: Grupos de consolidación explícitos en el motor de reportes

As Ary (dueño),
I want que los reportes consolidados de EAG se deriven de un grupo explícito de entidades en vez del supuesto "EAG = todas las cuentas",
So that agregar el Fondo Común (o cualquier entidad futura) al ledger jamás contamine mis números de EAG.

**Acceptance Criteria:**

**Given** el ledger actual (EAG + Jocelyn, Jeannette, Johanna, Jael),
**When** se genera cualquier reporte, balance o dashboard consolidado de EAG tras reemplazar `_CONSOLIDATED_ENTITY` por `CONSOLIDATION_GROUPS`,
**Then** el resultado es idéntico peso-por-peso al comportamiento previo (0 diffs de regresión — NFR20),
**And** la suite de tests y bean-check pasan en verde (NFR21).

**Given** una cuenta de prueba bajo un namespace ajeno al grupo EAG (ej. `Assets:FFCC:Test`),
**When** se genera el reporte consolidado de EAG,
**Then** esa cuenta no aparece ni altera ningún total (FR45).

**Given** la definición `CONSOLIDATION_GROUPS`,
**When** se consulta el grupo del libro RUT2,
**Then** resuelve explícitamente a [FFCC, JAB], separado del grupo EAG (FR46),
**And** las consultas por entidad individual (ej. Jocelyn) siguen funcionando sin cambios.

### Story 11.2: Entidades del Fondo Común seleccionables en el frontend

As usuario (owner o contador),
I want ver y seleccionar las entidades del Fondo Común (FFCC, JAB) en el selector de entidad existente,
So that cuando sus datos entren al ledger pueda navegarlos desde la misma UI de siempre.

**Acceptance Criteria:**

**Given** la decisión de Ary sobre los nombres cortos definitivos de las entidades (propuesta actual: FFCC y JAB),
**When** se ejecuta esta story,
**Then** los labels quedan fijados aquí — para rutas de cuenta, `VALID_ENTITIES` y selector — y las stories posteriores los usan sin cambios.

**Given** las entidades nuevas registradas en `VALID_ENTITIES` y `FilterContext`,
**When** abro el selector de entidad en cualquier dashboard,
**Then** FFCC y JAB aparecen como opciones válidas (FR47),
**And** EAG sigue siendo la entidad por defecto.

**Given** que FFCC/JAB aún no tienen datos en el ledger,
**When** selecciono una de ellas,
**Then** el dashboard muestra un estado vacío limpio (sin errores, sin números de otras entidades).

## Epic 12: El libro del Fondo Común en el ledger — importación multi-libro validada

El árbol de cuentas de RUT2 se pre-crea en el ledger; el importador Laudus se vuelve multi-libro y trae el histórico + apertura. Definition of Done del epic: reconciliación peso-por-peso contra el ancla de validación (FR56), con fallback = balance de Laudus a fin de mes. Stories 12.4 y 12.5 bloqueadas por respuestas del contador; el resto avanza con lo que ya entregó la sonda.

### Story 12.1: Cerrar la clasificación contable con Valentina

As Ary (dueño),
I want la clasificación contable del libro RUT2 cerrada y firmada con Valentina antes de construir nada,
So that el árbol de 308 cuentas se construya una sola vez y el reporte final responda la pregunta de negocio correcta.

**Acceptance Criteria:**

**Given** los tres pendientes contables abiertos (¿FGK y JAB son una o dos sub-entidades?; ¿raíces 4 y 8 son P&L separados?; convención de la cuenta de Equity de apertura),
**When** Valentina y/o el contador los resuelven,
**Then** queda documentada la decisión de cada uno en un artefacto versionado en planning-artifacts,
**And** el grupo de consolidación RUT2 se ajusta si FGK resulta ser entidad aparte.

**Given** el plan real de 357 cuentas,
**When** se firma el mapeo raíz→(root Beancount, entidad),
**Then** el artefacto cubre las 7 raíces (1/2/3/4 FFCC, 6/7/8 JAB) sin cuentas sin destino.

### Story 12.2: Importador multi-libro — entidad como parámetro, índice (entidad, código), assert de empresa

As operador de la importación (Ary o dev),
I want que el importador Laudus exija la entidad/libro como parámetro explícito y rutee por (entidad, código),
So that sea estructuralmente imposible que asientos del Fondo Común se posteen a cuentas de EAG en silencio.

**Acceptance Criteria:**

**Given** una corrida de import sin entidad, companyVATId o subdirectorio destino explícitos,
**When** se ejecuta,
**Then** falla con error claro antes de leer o escribir nada (FR50).

**Given** los 18 códigos en colisión (mismo código, cuenta distinta entre libros),
**When** se importa un asiento de RUT2 con uno de esos códigos,
**Then** rutea a la cuenta de RUT2 vía índice `{(entidad, código)→cuenta}`, nunca a la homónima de EAG (FR51).

**Given** que Laudus devuelve datos de otro libro sin fallar ante un companyVATId equivocado,
**When** el importador arranca una corrida,
**Then** verifica que el nombre de empresa devuelto coincide con la entidad esperada y aborta sin escribir si no coincide (FR52),
**And** la verificación NO valida dígito verificador (RUT placeholder con DV inválido por diseño).

**Given** el libro EAG con el importador refactorizado,
**When** corre el import habitual de EAG,
**Then** el resultado es idéntico al comportamiento previo (0 regresiones, suite verde).

### Story 12.3: Pre-crear el árbol de cuentas de RUT2 con Equity de apertura

As contador (usuario del sistema),
I want el plan de cuentas completo del Fondo Común pre-creado en el ledger según la clasificación firmada,
So that cualquier import posterior tenga destino correcto y nada caiga en cuentas de EAG ni en cuarentena masiva.

**Acceptance Criteria:**

**Given** el mapeo firmado en 12.1 y el plan real extraído de Laudus (308 hojas),
**When** se genera el subárbol en `accounts.beancount`,
**Then** cada hoja existe bajo `{Root}:{Entidad}:{slug}-{código}` según su raíz (1=Assets, 2=Liabilities, 3=Income, 4=Expenses para FFCC; 6=Assets, 7=Income, 8=Expenses para JAB) (FR48),
**And** las cuentas bancarias llevan `bank_account_id` (UUID minteado por nosotros) en metadata.

**Given** que el plan de RUT2 no tiene raíz de patrimonio,
**When** se crea el subárbol,
**Then** existe una cuenta de Equity de apertura para el libro, con la convención definida en 12.1 (FR49).

**Given** el ledger con el subárbol nuevo,
**When** corre la validación,
**Then** `bean-check` sale en 0 (NFR21),
**And** los reportes de EAG quedan idénticos peso-por-peso (NFR20).

### Story 12.4: Importar histórico y apertura del Fondo Común

> ⏳ Bloqueada por contador: fecha de corte del histórico y forma de la apertura.

As contador (usuario del sistema),
I want el histórico contable del Fondo Común importado al ledger desde la fecha de corte confirmada,
So that los números de FFCC/JAB existan en el sistema y sean navegables como los de EAG.

**Acceptance Criteria:**

**Given** la fecha de corte y la apertura confirmadas por el contador,
**When** corre la importación multi-libro contra el libro RUT2,
**Then** los asientos quedan en cuentas de RUT2 desde esa fecha y el asiento de apertura ("Saldo anterior") rutea a la cuenta de Equity de apertura (FR53).

**Given** el ledger post-import,
**When** se compara contra el estado pre-import,
**Then** no existe ningún asiento nuevo bajo cuentas de EAG (NFR20),
**And** `bean-check` sale en 0 (NFR21).

**Given** cada corrida de import,
**When** termina (éxito o falla),
**Then** queda registrada en el log append-only con timestamp, registros procesados y errores (NFR13, NFR10).

### Story 12.5: Reconciliación peso-por-peso contra el ancla de validación

> ⏳ Bloqueada por contador: ancla de validación. Fallback definido: balance de Laudus a fin de mes. **Esta story es el criterio de cierre del epic.**

As Ary (dueño),
I want los saldos importados del Fondo Común reconciliados peso-por-peso contra un dato real conocido,
So that pueda confiar en los números de RUT2 igual que confío en los de EAG.

**Acceptance Criteria:**

**Given** el ancla provista por el contador (saldo bancario real o, en su defecto, balance de Laudus a fin de mes),
**When** se reconcilian los saldos importados a esa fecha,
**Then** cuadran al peso, o cada discrepancia queda documentada con explicación aceptada (FR56).

**Given** los dashboards existentes,
**When** filtro por FFCC o JAB (o el grupo del libro),
**Then** los saldos y movimientos mostrados coinciden con lo reconciliado,
**And** el drill-down a transacciones individuales funciona.

**Given** el resultado de la reconciliación,
**When** se presenta para el cierre del epic,
**Then** el Epic 12 solo se declara cerrado con la reconciliación en PASS (DoD del epic).

## Epic 13: Reporte de gastos del Fondo Común (FFCC / JAB)

Reporte de gastos con plantilla propia de RUT2 en dos niveles, derivado mecánicamente de la jerarquía embebida en la numeración del plan de cuentas. Una sola story: la plantilla parametrizada es el trabajo real; la marca de TC lumpeada (FR55) es una fila más de esa misma plantilla.

### Story 13.1: Reporte de gastos de RUT2 en dos niveles

As Ary (dueño),
I want un reporte de gastos del Fondo Común agrupado por sub-entidad y por categoría de activo,
So that vea en qué gasta el FFCC y en qué gasta JAB/FGK (casas, aviones, yates, gastos personales), igual que veo los gastos de EAG.

**Acceptance Criteria:**

**Given** los datos de RUT2 importados y validados (Epic 12 cerrado),
**When** abro el reporte de gastos para el libro RUT2 en un período,
**Then** veo el nivel 1 separado en FFCC vs JAB,
**And** el nivel 2 agrupa por encabezado numérico: FFCC → 41 Gastos Generales, 43 Gastos Fijos Oficina; JAB → 81 Casas (con sus propiedades), 83 Aviones, 85 Yates, 87 Gastos Personales (FR54),
**And** la agrupación se deriva mecánicamente de la jerarquía de códigos (8→81→811), sin clasificación manual.

**Given** las cuentas de TC de JAB/FGK (871005, 873005) registradas como gasto lumpeado,
**When** aparecen en el reporte,
**Then** se muestran con la limitación marcada visiblemente en el cuerpo del reporte — no en nota al pie — indicando que es el pago mensual sin desglose (FR55, estado 1 igual que EAG).

**Given** el reporte de gastos de EAG existente,
**When** se introduce la plantilla parametrizada de RUT2,
**Then** el reporte de EAG sigue funcionando sin cambios (0 regresiones).
