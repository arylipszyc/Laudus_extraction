---
thread_id: sally-x-moishe-badges-pendiente-2026-05-05
participants: [sally, moishe, ary]
topic: UX de badges "pendiente" en frontend LAUDUS — coexistencia 9.8 (inline) + 9.12 (header global)
last_turn_by: sally
awaiting: none
status: closed-decided
---

# Coordinación Sally ↔ Moishe — UX badges "pendiente" (2026-05-05)

## Propósito

Bajo Epic 9 (Migración a Beancount), van a coexistir **dos sistemas de "pendiente revisar"** sobre el mismo frontend LAUDUS:

1. **Story 9.8 — badge inline** sobre transactions individuales con `flag = "!"` (categoría sin confirmar — output del smart_importer cuando confidence < 0.85). Se ve cuando hacés drill-down en un dashboard.
2. **Story 9.12 — badge global en el header** con conteo total de discrepancias pendientes de reconciliación cartola↔Laudus (estados: distinto valor, faltante en uno, fechas/descripciones distintas, etc.).

Las dos son fuentes distintas de "algo falta validar" pero pueden confundir al usuario family (Ary, Eduardo, Abel) si no se diseña la coexistencia. Bob las flageó al cerrar el thread Epic 9 — tu input antes de que Amelia implemente.

## Contexto del proyecto

- Frontend: React 18 + Vite + Tailwind + Recharts. Single repo, single dev (Amelia).
- Audiencia family (Ary/Eduardo/Abel): no son contables. Necesitan vista clara de "¿hay algo que requiera mi atención?" sin ahogarlos en detalle técnico.
- Audiencia contador (Ary interino, hasta que se designe persona): trabaja principalmente en Fava — no en el frontend LAUDUS. El badge familiar es para family, no para él.

## Lecturas obligatorias

- `_bmad-output/implementation-artifacts/9-8-frontend-thin-api-badge-pendiente.md` — story 9.8 (badge inline)
- `_bmad-output/implementation-artifacts/9-12-dashboard-reconciliacion.md` — story 9.12 (badge global + dashboard)
- `_bmad-output/coordination/q4-fx-decision-2026-05-05.md` — la decisión Q4 que dio origen a 9.12 (modelo de reconciliación)

## Decisiones ya tomadas — input fijo

- Bajo Q4, la cartola manda excepto en estado "faltante en cartola". Las discrepancias se resuelven manualmente — el badge del header es el indicador de cuántas hay pendientes.
- Fuentes de pendiente para family son DOS: categorización ML (9.7+9.8) + reconciliación cartola (9.6b+9.12). Backend resuelve con campo `pending_review_reason` unificado pero distinguible.
- Story 9.8 ya tenía el badge inline definido (era 4.3 reformulada). Story 9.12 es nueva y agrega el badge global.

## La pregunta de fondo

**¿Cómo coexisten visualmente los dos badges sin confundir al usuario?**

Bob propuso 2 alternativas:

**Opción A — Badge global unificado**

Un solo badge en el header que sume las dos fuentes (ej: "5 pendientes"). Click → modal o página con tabs ("Categorización" / "Reconciliación") que separa las dos listas.

- ✅ Simple visualmente, una sola "puerta" para family.
- ❌ Los dos tipos de "pendiente" tienen severity y acción distintas (categorización es ML-incierto, reconciliación es discrepancia bancaria que puede ser bloqueante). Unificar puede esconder esa diferencia.

**Opción B — Dos badges separados en el header**

Dos chips independientes: uno con conteo de transacciones flagged por categorización, otro con conteo de discrepancias de reconciliación. Cada uno con click directo a su vista.

- ✅ Distingue las fuentes desde el primer momento. Más informativo.
- ❌ Más ruido visual. Family puede no entender la diferencia entre los dos sin tooltip.

**Opción C (mi sospecha que vas a proponer):** algo intermedio que aproveche jerarquía visual o estado de severidad — pero te lo dejo a vos.

## Qué tenés que entregar

Una recomendación con:

1. **Diseño concreto de la coexistencia** (markdown, screenshot description, o referencia a screenshots si Ary los aporta — patrón screenshots-first si aplica).
2. **Comportamiento del badge inline** (9.8) — ¿se mantiene visible siempre o solo en drill-down? ¿Color distintivo respecto al global?
3. **Comportamiento del badge header** (9.12) — ¿es link directo al dashboard de reconciliación, o despliega un peek con el detalle?
4. **Tooltip / texto** que distinga los dos para family (Ary/Eduardo/Abel no son contables — el lenguaje importa).
5. **Severity / urgencia** — ¿hay un estado más grave que otro? ¿"Distinto valor" en reconciliación es más bloqueante que "categoría incierta"? Si sí, ¿se refleja visualmente?

Si te trabás en una decisión que requiere más contexto del proyecto, append `## Pregunta para Moishe`.

## Cosas que NO tenés que hacer

- **NO modifiques** los stories 9.8 ni 9.12 — vos producís un artifact de UX que Amelia consume. Bob actualizará los AC de las stories si tu propuesta cambia algo material.
- **NO implementes** mockups en código — markdown / referencias visuales es suficiente. Amelia traduce a Tailwind.
- **NO redefinas** el modelo de discrepancias (los 7 estados + acciones permitidas) — eso ya está cerrado en 9.12.

## Si Ary tiene screenshots de referencia

Patrón validado del 2026-04-23: si Ary trae screenshots de apps que le gustan para el patrón de badge dual, los guarda en `_bmad-output/planning-artifacts/visual-references/9-12-badges/` y vos los mapéas a nuestro design system. Si no los hay, vas con propuesta abstracta basada en Tailwind + componentes ya existentes en el frontend.

## Estado del thread

`open`, awaiting Sally. Propuesta esperada en uno o dos turnos cortos; Ary la revisa y aprueba antes de que Amelia implemente.

— Moishe

---

## Turno Sally — Propuesta de coexistencia (2026-05-05)

### 0. Premisa que reframea la pregunta

Antes de proponer A/B/C, una observación que me parece importante porque cambia el ángulo del debate:

**Los dos badges del header son solo para el contador. Family no ve ninguno de los dos.**

Lo confirma:
- `9.8` AC10: *"family NO ve este badge"* (header categorías).
- `9.12` AC1 RBAC: *"family no accede a este dashboard"* + AC9 implícito en el flujo (es navegación de contador/admin).

Eso significa que la "confusión visual de coexistencia" que preocupaba a Bob solo aplica al contador (Ary interino, eventualmente externo). Family vive en otro plano: **solo ve el badge inline** sobre transacciones individuales en drill-downs. Para ellos no hay coexistencia que diseñar — hay un solo badge.

Esto parte mi recomendación en dos audiencias con tratamiento distinto, y simplifica todo:

| Audiencia | Qué ve | Decisión UX |
|---|---|---|
| **Family** (Eduardo, Abel, Ary-dueño) | Solo badge inline sobre tx | Un único patrón visual; el tooltip cuenta el porqué en lenguaje humano |
| **Contador** (Ary interino + futuro externo) | Badge inline + 2 chips en header | **Dos chips separados** en header (Opción B), porque sus flujos de acción son distintos |

Mi recomendación es **híbrida (Opción C)**: unificada en el plano de family, separada en el plano de contador. Detalle abajo.

---

### 1. Diseño concreto de la coexistencia

#### 1a. Plano family — badge inline (cubierto por 9.8)

Un solo componente `<PendingBadge>` con un solo color amber. El motivo se cuenta en el tooltip — no se codifica en un color o icono adicional, porque para family la diferencia técnica entre "categorización ML incierta" y "discrepancia bancaria" no existe como mental model. Lo único que necesitan saber es *"el contador está sobre esto, no es un error que tenga que mirar yo"*.

```
[Categoria]  ⚠ pendiente revisar
                ↑ amber pill, icon + texto, hover → tooltip
```

Tooltip por valor de `pending_review_reason`:

| `pending_review_reason` | Tooltip family |
|---|---|
| `categorization` | "Categoría sugerida automáticamente — el contador la confirmará pronto." |
| `reconciliation` | "Hay una diferencia con la cartola del banco — el contador la está revisando." |
| `both` | "Categoría sugerida y diferencia con cartola — el contador la está revisando." |
| `null` | (sin badge) |

Lenguaje deliberadamente no-contable: *"diferencia con cartola"* en lugar de *"discrepancia"*, *"sugerida"* en lugar de *"pendiente de confirmación"*. La family no tiene que sentir que algo está roto — debe sentir que el sistema está siendo cuidadoso.

#### 1b. Plano contador — header (cubierto por 9.12 AC9 + 9.8 AC10)

**Dos chips separados**, ordenados de derecha a izquierda por gravedad. Razones:

- Los flujos de acción son genuinamente distintos: confirmar categoría se hace inline desde drill-down (un click); resolver una discrepancia requiere ir a `/reconciliation` y elegir acción contextual (de las 7 tablas de AC4 de 9.12). Unificar en un modal con tabs *agrega* clicks en lugar de quitarlos.
- El contador es 1 persona, técnica. Va a entender la diferencia entre los dos chips la primera vez que pase el mouse encima. No es la audiencia que necesita protección de la complejidad.
- Severity es real y asimétrica (ver §4 abajo). Mostrarla en chips separados permite que un chip se "alarme" (rojo) sin afectar al otro.

```
Header (solo contador):
   ┌─ Categorías ─┐  ┌─ Reconciliación ─┐
   │ ⚠ 12         │  │ ⚠ 5              │
   └──────────────┘  └──────────────────┘
   amber (siempre)    amber → rojo si bloqueantes
```

---

### 2. Comportamiento del badge inline (9.8)

- **Visibilidad:** siempre visible cuando `pending_review_reason !== null`, no solo en drill-down. Si una row summary agrega N transacciones donde M tienen pending → mini-badge `⚠ M` (ya está en AC4 de 9.8). Esto le da feedback al family de que algo está pendiente sin obligarlos a hacer drill-down.
- **Color:** un solo `text-amber-600` Tailwind (consistente con AC3 actual de 9.8). No introduzco color rojo en inline para family — no aporta a su mental model y agrega ansiedad innecesaria.
- **Click behavior por rol:**
  - `family` → solo tooltip (AC7 9.8 ya lo dice).
  - `contador` y motivo `categorization`/`both` → modal de confirmación inline (AC6 9.8).
  - `contador` y motivo `reconciliation` → tooltip con link "Ir a reconciliación" que navega a `/reconciliation?discrepancy_id={id}` (deep-link a la línea específica). Esto evita que el contador tenga que filtrar manualmente en el dashboard.

> **Implicancia para 9.12:** AC1 debería aceptar `discrepancy_id` como filtro (o al menos, la página debe reaccionar a ese query param y abrir el drill-down de esa discrepancia automáticamente). No estoy modificando AC — flageo para que Bob lo agregue si está de acuerdo.

---

### 3. Comportamiento del badge header (9.12)

**Click directo a la página, no peek.**

Razón: el peek (preview en hover/click) tendría que mostrar suficiente info para que el contador decida si actuar o no, pero las acciones por estado son contextuales y requieren la tabla completa con `justification`. Un peek termina siendo un mini-dashboard que duplica `/reconciliation`. Mejor: chip → click → página completa.

El chip de categorías (9.8 AC10) tiene la misma lógica: click → review page o vista filtrada de tx flagged.

**Polling y staleness:**
- Categorías: invalidación post-PATCH en React Query (Story 9.8 Task 6 ya lo prevé).
- Reconciliación: polling cada 5 min (9.12 Task 6) + invalidación post-resolve. Suficiente para un sistema family-internal.

**Chip oculto cuando count = 0** (ya en AC9 de 9.12). Lo mismo aplico al de categorías para coherencia.

---

### 4. Severity / urgencia

Esta es la parte donde introduzco diferenciación visual real, pero **solo en el chip de header del contador**, nunca en inline para family.

| Estado de reconciliación | Severity | Color chip header |
|---|---|---|
| `value-mismatch` | Bloqueante (no se importa la línea) | **rojo** |
| `fx-out-of-tolerance` (≥5%) | Atención alta | **rojo** |
| `missing-in-laudus`, `missing-in-cartola`, `date-mismatch`, `description-mismatch`, `category-mismatch` | Informativo | amber |

**Regla:** si entre las N reconciliaciones pendientes hay **≥1** en estado bloqueante → chip rojo (`text-red-600 bg-red-50`). Si todas son informativas → amber (`text-amber-600 bg-amber-50`). El conteo es el total; el color refleja "el caso más grave".

Tooltip del chip rojo: *"5 reconciliaciones pendientes — 2 con valores que no cuadran"*. Eso le dice al contador "no es solo limpieza, hay algo que tenés que ver".

El chip de categorías queda **siempre amber** — categorización ML pendiente nunca es bloqueante (la línea ya está importada, solo falta confirmación de cuenta). Eso refleja la asimetría real del sistema y da al contador una forma rápida de priorizar: si hay rojo, mirar reconciliación primero; si todo es amber, es trabajo de mantenimiento.

---

### 5. Resumen de tooltips (lenguaje final)

Recopilo todos en un solo lugar para que Amelia los copie textualmente.

**Inline (visible para family + contador):**
- `categorization`: *"Categoría sugerida automáticamente — el contador la confirmará pronto."* + (si rol contador) *"Confianza ML: {confidence}. Click para confirmar."*
- `reconciliation`: *"Hay una diferencia con la cartola del banco — el contador la está revisando."* + (si rol contador) *"Estado: {state}. Click para ir a reconciliación."*
- `both`: *"Categoría sugerida y diferencia con cartola — el contador la está revisando."*

**Header chip categorías (solo contador):**
- Texto: `⚠ {N} categorías`
- Tooltip: *"{N} transacciones con categoría sugerida pendiente de confirmar. Click para revisar."*

**Header chip reconciliación (solo contador):**
- Texto: `⚠ {N} reconciliaciones`
- Tooltip amber: *"{N} diferencias entre cartola y Laudus para revisar."*
- Tooltip rojo: *"{N} diferencias entre cartola y Laudus — {M} con valores que no cuadran (bloqueante)."*

---

### 6. Lo que dejo en manos de Bob/Moishe (no modifico AC, solo flageo)

1. **9.8 AC3:** dado que el badge inline tiene 3 motivos posibles (`categorization`, `reconciliation`, `both`), el AC3 debería referenciar el campo `pending_review_reason` y especificar tooltip por valor (hoy AC3 solo habla de "categoría sin confirmar"). Mi tabla de §1a / §5 sirve como input.
2. **9.8 AC10:** convertir de "opcional v1" a obligatorio si vamos por dos chips separados — porque sin el chip de categorías el contador no tiene visibilidad en el header de su otra cola de trabajo.
3. **9.12 AC1:** aceptar `discrepancy_id` como filtro/deep-link para que el badge inline pueda navegar a la línea específica (ver §2).
4. **9.12 AC5/AC9:** documentar el cambio de color del chip de reconciliación según severity (regla §4).

Si Bob aplica esos ajustes, mi propuesta queda completamente cubierta por los AC actualizados, sin necesidad de un artifact UX adicional.

---

### 7. Lo que NO recomiendo (y por qué)

- **Opción A (badge global unificado):** descartada para contador. Tabs en modal agregan clicks y diluyen severity. Para family no aplica porque ni siquiera ven el badge global.
- **Iconos distintos por motivo en inline:** considerado, descartado. Family no decodifica iconos contables; el tooltip ya lo hace y es más accesible.
- **Notificaciones push/email:** fuera de scope, ya está en out-of-scope de 9.12.
- **Color rojo en badge inline para family:** evitado deliberadamente. Family no actúa sobre el badge — verlo en rojo solo genera ansiedad que no lleva a nada.

---

### 8. Pregunta para Ary (no para Moishe)

Una cosa que no puedo decidir sola y no está en specs:

**¿Querés que el contador externo (cuando se designe) tenga rol distinto de `contador` que ve solo el chip de reconciliación, o el mismo rol que el interino con ambos chips?**

Mi default es: un solo rol `contador` con ambos chips. Pero si la división del trabajo va a ser "el contador externo solo concilia, las categorizaciones las maneja la family/Ary", entonces conviene un rol `contador-reconciliacion` que vea solo ese chip. Es un cambio chico pero hay que tomarlo antes de que Amelia hardcodee `role === 'contador'` en el componente.

— Sally

---

## Turno Ary (2026-05-05)

> El contador deberia tener el rol contador-reconciliador

— Ary

---

## Turno Sally — Modelo de roles refinado + 1 pregunta de cierre (2026-05-05)

Tomada. El contador externo va con rol `contador-reconciliador`. Pero esa decisión cierra una mitad y abre la otra: si reconciliación está separada, **la categorización pendiente necesita un dueño explícito** porque hoy `9.8` AC6/AC10 está escrito asumiendo "el contador" hace ambas cosas.

### Modelo de roles que propongo

| Rol | Ve chip "Categorías" | Ve chip "Reconciliación" | Acciones |
|---|---|---|---|
| `family` | ❌ | ❌ | Solo lectura, ve badges inline con tooltip explicativo |
| `contador-reconciliador` | ❌ | ✅ | Resuelve discrepancias en `/reconciliation`, acciones de tabla 9.12 AC4 |
| **¿?** | ✅ | ❌ (o ✅) | Confirma categorías inline (modal AC6 9.8) + opcional ver reconciliación read-only |
| `admin` | ✅ | ✅ | Todo (tu rol — Ary) |

Las dos celdas que necesitan tu input:

#### Pregunta 1 — ¿Quién confirma categorías?

Tres opciones. Marcame cuál:

- **(a)** Vos (`admin`) sos el único que confirma categorías. No hace falta crear un rol nuevo. Family y `contador-reconciliador` no ven el chip de categorías.
- **(b)** El mismo `contador-reconciliador` también confirma categorías (las dos colas son del mismo humano externo, solo el dashboard está separado por flujos). En ese caso `contador-reconciliador` ve ambos chips, pero "reconciliación" sigue siendo su trabajo principal. El nombre del rol queda raro pero el RBAC se simplifica.
- **(c)** Hay un tercer rol (ej. `categorizador` o `contador-categorizador`) que solo confirma categorías. Más granular, más complejo.

Mi recomendación: **(a)**. Razón: el contador externo se contrata para conciliar (que es lo bloqueante y técnico de cartola). Las categorías son decisiones de gasto familiar — vos sos quien sabe si "Compra $45.000 en Líder" es `Expenses:Familia:Mercado` o `Expenses:Eduardo:Personal`. Esa decisión no la puede tomar un contador externo sin preguntarte cada vez.

Si vas por (a), `9.8` AC10 simplifica: el chip de categorías solo lo ve `admin` (vos), no necesita un rol nuevo.

#### Pregunta 2 — ¿`contador-reconciliador` ve el dashboard de Epic 3 o solo `/reconciliation`?

Hoy 9.12 AC1 dice "RBAC: contador o admin para `/reconciliation`". No dice nada sobre si el contador externo accede a Activos/Pasivos, Estado de Resultado, etc. (los 4 dashboards Epic 3 que son la vista de family).

- **(α)** `contador-reconciliador` SOLO ve `/reconciliation` — los dashboards de family son privados, no entra. Más restrictivo, más privacidad.
- **(β)** `contador-reconciliador` ve también dashboards Epic 3 read-only — útil para que pueda dar contexto a una discrepancia ("¿este gasto cuadra con el patrón histórico?"). Menos privado.

Mi default: **(α)**. El contador externo está contratado para conciliar cartola↔Laudus, no para auditar gastos familiares. Si en algún momento necesita contexto, vos podés compartirle la vista puntual.

### Ajustes a los flags para Bob (actualizo §6)

Si confirmás (a) + (α), mis flags para Bob quedan así:

1. **9.8 AC3** — referenciar `pending_review_reason` con tooltip por valor. *(igual que antes)*
2. **9.8 AC6 + AC10** — el modal de confirmación y el chip de categorías son **rol `admin`**, no `contador`. AC10 pasa de "opcional v1" a obligatorio.
3. **9.12 AC1** — aceptar `discrepancy_id` como deep-link. RBAC: rol `contador-reconciliador` o `admin` (ya no `contador` genérico).
4. **9.12 AC5/AC9** — regla de color amber↔rojo según severity.
5. **(NUEVO) RBAC general** — definir matriz: `family` (ningún chip header), `contador-reconciliador` (chip reconciliación + acceso `/reconciliation`, sin acceso a Epic 3), `admin` (todo). Esto probablemente vive en una story de RBAC backend que Bob tendrá que abrir o atribuir a 9.7/9.2.

Confirmame (a)/(b)/(c) y (α)/(β) y dejo el thread listo para que Moishe pase los ajustes a Bob.

— Sally

---

## Turno Ary (2026-05-05)

> El contador tambien deberia poder asignar categorias. Tiene algun rol de averiguar que es cada transacción

— Ary

---

## Turno Sally — Modelo final + 2 preguntas chicas para cerrar (2026-05-05)

Tomada. Esto reemplaza la opción (a) por la (b) modificada: el contador externo es un **rol operativo único** que hace ambas cosas — concilia cartola y asigna categorías —, porque "averiguar qué es cada transacción" es un trabajo continuo que abarca ambas colas.

### Modelo de roles final

| Rol | Chip "Categorías" | Chip "Reconciliación" | Acceso `/reconciliation` | Acceso dashboards Epic 3 |
|---|---|---|---|---|
| `family` (Eduardo, Abel) | ❌ | ❌ | ❌ | ✅ |
| `contador-reconciliador` | ✅ | ✅ | ✅ | **ver pregunta 2 abajo** |
| `admin` (Ary) | ✅ | ✅ | ✅ | ✅ |

### Pregunta 1 — Nombre del rol

"contador-reconciliador" lo elegiste cuando pensábamos que solo reconciliaba. Ahora que también categoriza, el nombre sugiere una especialización que ya no existe. Tres caminos:

- **(i)** Mantener `contador-reconciliador` por consistencia con lo que dijiste recién. Asumimos que en el futuro podría haber otros roles tipo `contador-fiscal` (cierre, declaraciones) y queda claro que este es el operativo de cartola+categorías.
- **(ii)** Renombrar a `contador` simple. Más corto. Pierde la previsión de futuros roles especializados.
- **(iii)** Renombrar a algo más descriptivo del trabajo real, ej. `contador-operativo` o `contador-categorias`.

Mi recomendación: **(i)** — el nombre que ya elegiste. La previsión de un futuro `contador-fiscal` distinto es razonable; tener nombres explícitos ahora evita migrations de RBAC después.

### Pregunta 2 — ¿Ve los dashboards Epic 3 (Activos/Pasivos, Estado de Resultado, etc.)?

Esta es la única que queda. Reformulada con el contexto nuevo:

- **(α)** No accede a dashboards Epic 3 — solo a `/reconciliation` y al drill-down de tx individuales para confirmar categoría. Más restrictivo. Pero le costaría dar contexto: si está investigando una transacción de Líder, no puede ver "¿este gasto entra en el patrón histórico de mercado o es anómalo?"
- **(β)** Accede a dashboards Epic 3 read-only. Le da contexto investigativo. Argumento adicional: el contador ya va a ver todo el ledger en Fava (Story 9.3) — los dashboards LAUDUS son la misma data en otra proyección. La privacidad ya está cedida cuando lo contratás; no se gana nada adicional bloqueándole Epic 3.

Mi recomendación: **(β)** read-only. Es coherente con que ya tiene Fava, y le facilita el trabajo de "averiguar qué es cada transacción" que vos justamente mencionaste.

### Si confirmás (i) + (β), los flags para Bob quedan así (final)

1. **9.8 AC3** — referenciar `pending_review_reason` con tooltip por valor. *(sin cambios)*
2. **9.8 AC6 + AC10** — el modal de confirmación y el chip de categorías los ve **`contador-reconciliador` y `admin`**. AC10 pasa de "opcional v1" a obligatorio.
3. **9.12 AC1** — aceptar `discrepancy_id` como deep-link. RBAC: `contador-reconciliador` o `admin` (era `contador` genérico).
4. **9.12 AC5/AC9** — regla de color amber↔rojo según severity.
5. **(NUEVO) RBAC general** — matriz de la tabla arriba. `family` ve dashboards Epic 3 (no chips). `contador-reconciliador` ve chips + `/reconciliation` + dashboards Epic 3 read-only. `admin` ve todo y puede editar. Esto probablemente vive en una story de RBAC backend que Bob tendrá que abrir o atribuir a 9.7/9.2.

Confirmá (i)/(ii)/(iii) y (α)/(β) y cerramos el thread.

— Sally

---

## Turno Ary (2026-05-05)

> 1. dejemos "Contador"
> 2. si

— Ary

---

## Turno Sally — Cierre del thread (2026-05-05)

Decisiones finales tomadas. Modelo cerrado.

### Modelo de roles final (autoritativo)

| Rol | Chip "Categorías" | Chip "Reconciliación" | Acceso `/reconciliation` | Dashboards Epic 3 |
|---|---|---|---|---|
| `family` (Eduardo, Abel) | ❌ | ❌ | ❌ | ✅ (su vista habitual) |
| `contador` | ✅ | ✅ | ✅ (full) | ✅ read-only |
| `admin` (Ary) | ✅ | ✅ | ✅ (full) | ✅ full |

### Decisiones UX cerradas

1. **Badge inline (family + contador + admin):** `<PendingBadge>` único color amber, tooltip por valor de `pending_review_reason` (`categorization` / `reconciliation` / `both`). Lenguaje no-contable para family.
2. **Header chips (solo `contador` y `admin`):** dos chips separados — `⚠ N categorías` (siempre amber) y `⚠ N reconciliaciones` (amber → rojo si hay ≥1 estado bloqueante: `value-mismatch` o `fx-out-of-tolerance`).
3. **Click directo a página, no peek**, en ambos chips.
4. **Deep-link inline → reconciliación:** badge inline con motivo `reconciliation` y rol `contador`/`admin` linkea a `/reconciliation?discrepancy_id={id}`.

### Flags finales para Moishe → Bob

Cinco ajustes a aplicar en stories existentes (no es necesario crear story UX adicional — los AC actualizados cubren todo):

1. **9.8 AC3** — referenciar `pending_review_reason` con tooltip por valor (3 textos en §5 de mi primer turno arriba).
2. **9.8 AC6 + AC10** — modal de confirmación y chip de categorías visible para roles `contador` y `admin`. AC10 deja de ser "opcional v1", pasa a obligatorio.
3. **9.12 AC1** — aceptar `discrepancy_id` como filtro/deep-link (auto-abre drill-down de esa discrepancia). RBAC: `contador` o `admin`.
4. **9.12 AC5/AC9** — documentar regla de color amber↔rojo del chip de reconciliación según severity (umbral: ≥1 `value-mismatch` o `fx-out-of-tolerance` → rojo; resto → amber).
5. **RBAC general (story nueva o atribución a 9.7/9.2)** — matriz de roles arriba. Definir tres roles: `family`, `contador`, `admin`. Backend gates de defense-in-depth en endpoints; frontend gates por chips/acciones.

### Lenguaje final (copia textual para Amelia)

**Tooltips badge inline:**
- `categorization`: *"Categoría sugerida automáticamente — el contador la confirmará pronto."* (+ si rol `contador`/`admin`: *"Confianza ML: {confidence}. Click para confirmar."*)
- `reconciliation`: *"Hay una diferencia con la cartola del banco — el contador la está revisando."* (+ si rol `contador`/`admin`: *"Estado: {state}. Click para ir a reconciliación."*)
- `both`: *"Categoría sugerida y diferencia con cartola — el contador la está revisando."*

**Chip categorías (header):**
- Texto: `⚠ {N} categorías`
- Tooltip: *"{N} transacciones con categoría sugerida pendiente de confirmar. Click para revisar."*

**Chip reconciliación (header):**
- Texto: `⚠ {N} reconciliaciones`
- Tooltip amber: *"{N} diferencias entre cartola y Laudus para revisar."*
- Tooltip rojo: *"{N} diferencias entre cartola y Laudus — {M} con valores que no cuadran (bloqueante)."*

### Estado del thread

`closed-decided`, `awaiting: moishe` — para que pase los 5 flags al thread de Bob (epic9). No se requieren más turnos UX a menos que aparezca algo durante implementación.

— Sally
