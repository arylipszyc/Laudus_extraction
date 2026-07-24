# Story brief — Doble-click en transacción del reporte → abre el asiento completo en Fava

**Autora:** Valentina 💰 · 2026-07-21 · **Para:** el dev
**Pedido de Ary:** al hacer doble-click en una fila de transacción del reporte Ingresos/Gastos, abrir el
**asiento completo** (todas las patas) en **Fava**, con la posibilidad de editarlo.

---

## 1. Pregunta de negocio

El reporte muestra **una sola pata** de cada asiento (el gasto). El usuario quiere ver el asiento
completo — las dos (o N) patas, contra qué se pagó, la glosa por línea — sin salir a buscarlo a mano.
Ejemplo real que lo motivó: el pago de la 0858 es un asiento de 15 patas (banco + varias tarjetas +
ControlYLiquidación); desde el reporte solo se ve la pizca de 430009. Ver el asiento entero habría
respondido "¿contra qué se pagó?" al instante.

## 2. Decisión de diseño: reusar Fava, NO construir un editor en la app

Fava (servicio `laudus-fava`, ya en prod) **ya muestra el asiento completo y permite editar con red de
seguridad** (valida con `bean-check` antes de aceptar). En vez de construir eso en la app — riesgoso en un
libro que es espejo de Laudus — el reporte hace **deep-link a Fava** en el asiento correspondiente.

## 3. Alcance de ESTA story

- Doble-click (o un botón/ícono) en una fila de transacción del reporte Ingresos/Gastos (drill-down,
  `IncomeExpensesDrilldown.tsx`) → abre **Fava en el asiento de esa transacción**, en **pestaña nueva**.
- **Solo lectura + edición nativa de Fava** (Fava maneja la edición). La app no edita.

## 4. Trabajo técnico

### 4.1 Backend — exponer la ubicación del asiento
`_ledger_entries` (`backend/app/services/bql_queries.py`, ~L244) hoy devuelve `lineid: None` y no expone
dónde vive el asiento. Agregar por fila, desde `entry.meta`:
- `filename` — **repo-relative** (ej. `ledger/imports/laudus/2026-06.beancount`), NO el path absoluto del
  clon del backend. Hay que stripear el ledger-root del backend.
- `lineno` — `entry.meta["lineno"]`.

(Ambos ya están en la metadata de cada entry de Beancount; solo hay que exponerlos y normalizar el path.)

### 4.2 Frontend — armar el link y abrir Fava
- La fila del drill-down ya tiene `tx_id`; ahora tendrá `filename` + `lineno`.
- Construir la URL de Fava al **source/editor** en ese `filename:lineno` y abrir con `target="_blank"`.
- **La URL base de Fava viene de config** (env/settings del frontend), NO hardcodeada (Fava es servicio
  aparte, con basic-auth y su propio dominio). Ej. `VITE_FAVA_URL`.
- Fava abre el asiento en su editor de source (ahí se ve completo y es editable). El dev confirma la ruta
  exacta de Fava para saltar a `file:line` (Fava tiene editor de source por archivo/línea).

## 5. 🚩 Guardrails contables (CRÍTICO — que el dev NO se los salte)

### 5.1 Solo contador/admin
Fava es **contador-only** (basic-auth, la familia NO entra). El affordance de doble-click debe aparecer
**solo para rol `contador`/`admin`** (`useHasRole`). Para la familia: no mostrarlo (o, fase 2, un panel
de solo-lectura del asiento dentro de la app, sin Fava).

### 5.2 Editar un asiento de Laudus en Fava NO es durable — advertirlo
El ledger es **espejo de Laudus** para los asientos `source: "laudus-erp"`. Fava edita el archivo directo,
PERO **el próximo sync del importer regenera esos archivos (`replace`) y pisa el cambio.** Regla por fuente
(la misma doctrina de corrección del proyecto — se corrige con asientos, no editando el original):

| Fuente del asiento | Editar en Fava |
|---|---|
| `laudus-erp` (espejo) | **NO durable** — el sync lo pisa. Corrección real = asiento de ajuste en `manual/`. |
| `cartola-tc` | Editable, pero re-importar la cartola lo resetea (ya hay alarma para eso). |
| `manual/` | Durable — son asientos nuestros. |

**Recomendación:** cuando la fila sea `source: "laudus-erp"`, el tooltip/label del affordance debería
decir algo como *"ver en Fava (asiento de Laudus — no editar en el lugar; corregir con asiento de
ajuste)"*. Así el usuario no cae en la trampa de editar un espejo.

### 5.3 Path-mapping entre clones (principal riesgo técnico)
El backend y Fava tienen **clones separados** del mismo repo. El deep-link debe resolver al path que
**Fava** entiende. Si Fava usa paths absolutos de SU clon, el `filename` repo-relative del backend hay que
mapearlo al root de Fava. Confirmar cómo Fava referencia los archivos (absoluto vs repo-relative) antes de
fijar el formato del link. Como ambos clonan el mismo repo, los paths repo-relative deberían calzar.

## 6. Edge cases
- Fila sin `filename`/`lineno` (datos viejos cacheados, o entradas sintéticas) → **sin affordance**
  (fail-safe, mismo criterio que el ícono de comentarios de 7.1b).
- El asiento puede vivir en `imports/laudus/`, `imports/cartolas/` o `manual/` — el `filename` lo resuelve
  solo.
- Frescura: el clon de Fava puede estar un poco atrás del backend; aceptable (documentar que Fava refleja
  el último deploy/refresh de Fava).

## 7. Fuera de alcance (fase 2, otra story)
- **Panel de solo-lectura del asiento DENTRO de la app** (para la familia, que no tiene Fava). Mostraría
  todas las patas + glosa por línea (`desc`, ya existe en la metadata) sin salir a Fava.
- **Edición guiada por fuente en la app:** para `laudus-erp`, en vez de "editar", un botón "crear asiento
  de corrección" que abra un asiento de ajuste en `manual/`. Nunca editar el espejo en el lugar.

## 8. Verificación (DoD)
- Doble-click en una fila conocida (ej. el pago 0858, je 5624) abre Fava mostrando ese asiento con todas
  sus patas.
- El affordance NO aparece para rol familia.
- Una fila sin ubicación no rompe (no muestra affordance).
- El link usa la URL de Fava de config, no hardcodeada.
