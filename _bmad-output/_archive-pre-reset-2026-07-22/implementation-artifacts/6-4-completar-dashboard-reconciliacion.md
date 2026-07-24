# Story 6.4: Completar el dashboard de reconciliación (FR34)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **contador del family office**,
I want que **el dashboard de reconciliación (cartola ↔ Laudus) tenga el historial de cada diferencia, filtros por mes/cuenta, feedback de éxito, y el input de categoría para confirmar una diferencia como gasto real**,
so that **pueda revisar y resolver las diferencias de punta a punta desde la UI — incluyendo anotar un gasto faltante (el flujo de 6.3) — sin editar archivos ni adivinar el estado**.

> **Contexto:** el motor (9.6b), el backend de resolución (9.12) y la anotación-on-aprobación (6.3) ya están **done y en main**. 9.12 dejó varios defers de **frontend** (UX pasó a backlog) y 6.3 difirió a esta story el **input de categoría** para `confirm-cartola-only` (decisión Ary Q5). Esta story cierra esos defers → el reporte de reconciliación (FR34) queda usable end-to-end. **El backend ya soporta casi todo** (endpoints `history`, filtros, `category_account`/`git_commit_sha` en el resolve); el grueso es wirear la UI.

## Contexto — qué está hecho y qué falta

| Pieza | Backend | Frontend | Gap de 6.4 |
|---|---|---|---|
| Listado de discrepancias + summary | ✅ `GET /discrepancies` | ✅ tabla + chips de estado | — |
| Resolver/escalar | ✅ `POST .../resolve` | ✅ selector de acción + justificación | feedback de éxito (AC6) |
| **Anotar gasto (`confirm-cartola-only`)** | ✅ 6.3 (`category_account`, `git_commit_sha`, 422 atómico) | ❌ no manda `category_account` | **input de categoría (AC1)** |
| **Historial de una discrepancia** | ✅ `GET /history/{id}` | ❌ `getHistory` es **dead code** | **wirear historial en el drill-down (AC2)** |
| **Filtros `year_month` / `bank_account_id`** | ✅ params soportados | ❌ solo se envía `state` | **dropdowns en la UI (AC3)** |
| Deep-link `?discrepancy_id=` | ✅ | ⚠️ se **reabre solo** al resolver | **fix `useEffect` (AC4)** |
| Badge de pendientes (`/count`) | ✅ | ⚠️ desaparece en error → parece "0" | **surface error/stale (AC5)** |
| Moneda de la celda Laudus | ❌ `build_discrepancy` no emite `laudus.currency` | ⚠️ hardcodea CLP | **emitir + usar moneda (AC7)** |
| Estados FX `fx-bcch-missing`/`fx-implausible` | ⚠️ solo `escalate` (patch de review) | ⚠️ solo `escalate` | **decisión de producto (AC8, ver Preguntas)** |

## Acceptance Criteria

**AC1 — Input de categoría (dropdown con autocompletado) para `confirm-cartola-only` (movido de 6.3, Q5; decisión Ary Q1 = dropdown autocompletado).**
Given el drill-down de una discrepancia `missing-in-laudus` con la acción `confirm-cartola-only` seleccionada,
When el contador la confirma,
Then la UI ofrece un **dropdown con autocompletado** de cuenta de categoría (`Expenses:...`, **opcional**), poblado desde el plan de cuentas, y envía la cuenta elegida como `category_account` en el resolve. Si se deja vacío, la tx entra a `Suspense` y queda pendiente en `/categorizacion` (decisión Ary Q2 de 6.3) — hint que lo explique. El campo solo aparece para esa acción/estado.
**Requiere endpoint nuevo:** hoy NO existe un endpoint que liste el plan de cuentas (Categorización/CuentasPendientes usan input de texto plano). Agregar `GET /api/v1/accounts?root=Expenses` (o similar) que parsee los `open` de `accounts.beancount` y devuelva las cuentas `Expenses:*` (reusar el parseo de `cuentas_pendientes/service.py:_real_opens`). El autocompletado filtra sobre esa lista en el cliente.

**AC2 — Historial de la discrepancia en el drill-down (AC6 de 9.12).**
Given el panel de detalle (drill-down) de una discrepancia abierto,
Then se muestra su **historial completo** vía `GET /api/v1/reconciliation/history/{id}` (`getHistory`, hoy definido pero nunca llamado): la entry original + todas las líneas de resolución/escalation, en orden de archivo, con acción + autor + fecha + justificación.

**AC3 — Filtros de `year_month` y `bank_account_id` en la UI (completa AC5 de 9.12).**
Given el dashboard,
Then hay controles para filtrar por **mes** (`year_month`) y por **cuenta bancaria** (`bank_account_id`) — el backend (`GET /discrepancies`) y el service TS ya los aceptan; hoy la página solo envía `state`. Los chips de estado siguen funcionando combinados con los nuevos filtros (el summary se mantiene coherente).

**AC4 — El deep-link no reabre el drill-down al resolver.**
Given una visita con `?discrepancy_id=<uuid>` (deep-link desde el badge/otra vista),
When el contador resuelve o cierra ese item,
Then el drill-down **no se reabre solo**. (Hoy `setSelected(match)` se llama en el cuerpo del render — `ReconciliationPage.tsx:30-33` — y como el backend sigue devolviendo el item por el branch de `discrepancy_id`, se reabre. Mover a `useEffect` keyed en `deepLinkId`/`data` con un flag "ya auto-abrí".)

**AC5 — El badge de reconciliación distingue error de "0 pendientes".**
Given `PendingReconciliationBadge` y una falla transitoria de `GET /count`,
Then la UI **no oculta** la alerta como si fuera "0 pendientes" — surface un estado de error/stale (mantener el último valor conocido o un indicador). Una falla de red no debe silenciar la alerta bloqueante hasta el próximo poll.

**AC6 — Feedback de éxito/atomicidad al resolver.**
Given un resolve exitoso,
Then la UI muestra confirmación clara y refresca la lista + el badge. Para `confirm-cartola-only` que **anota** (escribe al ledger), reflejar que se contabilizó (usar `git_commit_sha` de la respuesta cuando viene). Si el backend devuelve **422** (`AnnotationFailed`: bean-check rojo), mostrar el detalle y dejar claro que **la discrepancia sigue abierta** (no se cerró).

**AC7 — Moneda correcta en la celda Laudus + nombre de cuenta (cosméticos; decisión Ary Q3 = hacerlos, no diferir).**
Given una fila cuya contraparte Laudus está en una moneda ≠ CLP,
Then la tabla muestra el monto Laudus con su **moneda real** (hoy `fmt(d.laudus?.amount)` hardcodea CLP → símbolo equivocado en filas USD): el backend emite `laudus.currency` (`_laudus_dict`/`build_discrepancy` en `pipeline/importers/reconcile.py`) y la celda lo usa.
And la tabla/drill-down muestra el **nombre de la cuenta bancaria** en vez del UUID (`bank_account_id`): resolver `bank_account_id → label` en el cliente joineando con `GET /api/v1/bank-accounts/` (que ya devuelve los labels y que la página igual carga para el filtro de cuenta de AC3) — **sin** tocar el backend para el label.

**AC8 — Estados FX `fx-bcch-missing` / `fx-implausible`: se DIFIERE (decisión Ary Q2).**
9.6b emite estos dos estados pero no están en `ACTIONS_BY_STATE`; el patch de review de 9.12 ya permite `escalate` para cualquier estado (sin dead-end). **Decisión Ary 2026-06-24: dejarlos en `escalate`-only por ahora y agregar acciones específicas a medida que aparezcan en la práctica (cuando un caso real lo pida).** Esta AC NO requiere código en 6.4 — solo queda documentada. NO marcarlos blocking.

**AC9 — Tests + sin regresiones.**
Backend: si se implementa AC7, test de que `build_discrepancy`/el reconcile emiten `laudus.currency`. Frontend: si el repo tiene harness de componentes (existe `Sidebar.test.tsx` → vitest), tests de los flujos clave (se envía `category_account`; el historial se renderiza; los filtros disparan el fetch con los params; el deep-link no reabre). Si no hay harness para páginas, **verificación manual documentada** en Completion Notes + 0 regresión en `backend/tests` (suite verde salvo los 2 rojos pre-existentes de `test_fava_edit_validator`).

### Fuera de scope

- **Editar asientos Laudus existentes** (`value-mismatch`/`accept-cartola`, soft-mismatch) → story futura (igual que en 6.3).
- **Cierre de período "reconciliado completo" (FR35)** → Story 6.5.
- Bulk-resolve, export, búsqueda por texto, ordenamiento de columnas → no pedidos; no entran salvo que Ary los pida.
- Action-sets específicos para `fx-bcch-missing`/`fx-implausible` → diferidos (decisión Ary Q2); se agregan cuando aparezca un caso real.

## Tasks / Subtasks

- [x] **Task 0 — Endpoint del plan de cuentas (para el autocompletado)** (AC1)
  - [x] `GET /api/v1/accounts?root=Expenses` (router/service nuevos o en un módulo existente): parsea los `open` de `accounts.beancount` y devuelve las cuentas que matchean el root. Reusar `cuentas_pendientes/service.py:_real_opens` (ya parsea los opens). Tests backend.

- [x] **Task 1 — Dropdown de categoría con autocompletado para `confirm-cartola-only`** (AC1, AC6)
  - [x] `reconciliation.ts`: agregar `category_account?: string | null` al body de `resolveDiscrepancy()` (hoy solo `{action, justification}`, ~53-68) y `git_commit_sha?: string | null` al tipo de respuesta. Service nuevo para `GET /accounts`.
  - [x] `ReconciliationPage.tsx` (drill-down, ~153-165): cuando `action === "confirm-cartola-only"`, mostrar un **dropdown con autocompletado** de cuenta `Expenses:...` (opcional) poblado desde `GET /accounts?root=Expenses`, filtrado en cliente, + hint de Suspense. Enviar `category_account`. (Componente de autocompletado nuevo — coordinar con el UX de Sally.)
  - [x] Manejar la respuesta: éxito (confirmación + sha si vino) y el **422** de `AnnotationFailed` (mensaje + discrepancia sigue abierta).

- [x] **Task 2 — Historial en el drill-down** (AC2)
  - [x] `ReconciliationPage.tsx`: en el panel de detalle, llamar `getHistory(discrepancy_id)` (ya existe en `reconciliation.ts:47-51`, hoy dead code) con React Query y renderizar las entries (original + resoluciones) en orden, con acción/autor/fecha/justificación.
  - [x] Tipar la respuesta del history (`{ discrepancy_id, entries }`) en `reconciliation.ts` (hoy `entries: unknown[]`).

- [x] **Task 3 — Filtros `year_month` + `bank_account_id` en la UI** (AC3)
  - [x] `ReconciliationPage.tsx`: agregar controles de mes y cuenta; pasar los params a `getDiscrepancies()` (ya los acepta, `reconciliation.ts:32-39`) y a la query key. Mantener los chips de estado coherentes (el summary no debe romperse al combinar filtros).
  - [x] Para el dropdown de `bank_account_id`: derivar la lista de las discrepancias visibles o de un endpoint de cuentas (ver patrón existente; si no hay uno barato, usar los valores presentes en el dataset).

- [x] **Task 4 — Fix deep-link reabre + feedback** (AC4, AC6)
  - [x] Mover el `setSelected(match)` del cuerpo del render (`ReconciliationPage.tsx:30-33`) a un `useEffect` keyed en `deepLinkId`/`data` con un flag de "ya auto-abrí" para que resolver/cerrar no reabra.
  - [x] Feedback de éxito al resolver (toast/inline) + refrescar lista y badge (la invalidación de `['reconciliation']`/`['reconciliation-count']` ya existe).

- [x] **Task 5 — Badge no desaparece en error de `/count`** (AC5)
  - [x] `PendingReconciliationBadge.tsx`: distinguir `isError`/stale de `data === 0`. No retornar `null` ante error transitorio; mantener último valor conocido o mostrar indicador. (Mismo eje que el defer de 9.12 en `deferred-work.md`.)

- [x] **Task 6 — Cosméticos: moneda Laudus + nombre de cuenta** (AC7) — *backend + frontend*
  - [x] Backend: `_laudus_dict`/`build_discrepancy` (`pipeline/importers/reconcile.py`) emiten `laudus.currency` (verificar si `LaudusEntry` ya la trae; si no, derivarla del posting). Test en `test_reconcile*.py`.
  - [x] Frontend: la celda Laudus usa `fmt(d.laudus?.amount, d.laudus?.currency)` (no hardcodear CLP). Y resolver `bank_account_id → label` joineando con `GET /bank-accounts/` (ya cargado para el filtro de AC3) → mostrar nombre de cuenta, no UUID. **Sin** tocar el backend para el label.

- [x] **Task 7 — Estados FX `fx-bcch-missing`/`fx-implausible`** (AC8) — ⏭️ **DIFERIDO (decisión Ary Q2):** quedan en `escalate`-only; se agregan acciones específicas cuando aparezca un caso real. Sin código en 6.4.

- [x] **Task 8 — Tests + verificación** (AC9)
  - [x] Backend: test de `laudus.currency` si se hizo Task 6. Correr `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` → 0 regresiones nuevas.
  - [x] Frontend: si hay harness (vitest, ver `Sidebar.test.tsx`), component tests de los flujos clave. Si no, documentar verificación manual (build + recorrido del flujo) en Completion Notes.

### Review Findings (code-review 2026-06-24)

Capas: Blind Hunter + Edge Case Hunter + Acceptance Auditor. Auditor: **8/8 ACs PASS** (AC8 diferido limpio, sin código huérfano). Sin findings CRITICAL/HIGH reales tras triage.

- [x] [Review][Patch] Deep-link se descarta de más al cerrar una fila abierta manualmente [frontend/src/pages/ReconciliationPage.tsx:59] — APLICADO: `closeSelected` ahora solo descarta el deep-link si lo que se cierra/resuelve ES el item del deep-link (`selected.discrepancy_id === deepLinkId`); cerrar otra fila solo limpia `manualSelected`. Sigue cumpliendo AC4 (no reabre el resuelto).
- [x] [Review][Patch] `fmt()` puede romper el render con una moneda inválida/vacía [frontend/src/pages/ReconciliationPage.tsx:19-20] — APLICADO: `fmt` valida que la moneda sea código de 3 letras (`/^[A-Z]{3}$/`); si no, cae a CLP. Sin más `RangeError` por moneda vacía/no-ISO.
- [x] [Review][Defer] `list_accounts` usa `startswith(root)` no segmentado + `root` sin allow-list [backend/app/api/v1/accounts/service.py:20] — deferred. `?root=` vacío devuelve TODO el plan de cuentas; un prefijo parcial podría colisionar. Detrás de RBAC y solo nombres de cuenta (read-only); el front siempre manda "Expenses". Hardening de validación = decisión de diseño, no daño actual.

**Descartados como ruido (10):** category "stale" entre acciones (el guard `annotates` solo manda `category_account` cuando el campo está visible; preservar el input es correcto); query `bank-accounts` sin surface de error (degrada a UUID, aceptable); `accounts.ts` "salta el wrapper de api" (falso positivo — todo el service layer usa `fetch` crudo); `listAccounts` asume array (lo cubre el default `= []`); teclado del autocomplete `active=-1`/desync (guardado por `&& matches[active]`, se resetea a 0 al tipear); `known` case-sensitive (las cuentas Beancount SON case-sensitive, exacto es correcto); `git_commit_sha.slice` (backend devuelve SHA real o null); index como React key en historial (lista read-only append-only); badge muestra dato stale tras fallo de poll (tradeoff explícito de AC5); fecha de escalación vacía (el backend siempre escribe `resolved_at`).

**Nota (no patch):** `setTimeout(onResolved, 1500)` en `onSuccess` no se cancela; si el usuario cierra y abre OTRA discrepancia dentro de 1.5s, el timer viejo cerraría la nueva. Escenario muy estrecho; el fix limpio (mover a `useEffect` con cleanup) agrega complejidad de deps. Anotado por si molesta en uso real.

## Dev Notes

### Estado actual de los archivos que se tocan (leídos para esta story)

**`frontend/src/pages/ReconciliationPage.tsx` (~186 líneas):**
- Header + chips de estado por `summary.by_state` (~42-51).
- Tabla: Fecha | Estado | Cartola (`fmt(amount, currency)`) | Laudus (`fmt(amount)` ← **CLP hardcodeado**, ~75) | Descripción | FX dev% | acción (~59-83).
- Drill-down lateral (~86-171): secciones Cartola/Laudus/FX, **selector de acción** (`ACTIONS_BY_STATE[state] ?? ['escalate']`, ~153-158), **textarea de justificación** (~159-162), botón confirmar (~165), error de `mutation` (~164). **No hay historial.**
- **Deep-link**: `setSelected(match)` en el cuerpo del render (~30-33) → bug de reabrir (AC4).
- Resolve manda solo `{action, justification}` (~127) → falta `category_account` (AC1).

**`frontend/src/services/reconciliation.ts` (~69 líneas):**
- `getDiscrepancies({state, year_month, bank_account_id, discrepancy_id})` (~32-39) — todos los params ya soportados.
- `getHistory(id)` (~47-51) — **definido, nunca usado** (AC2).
- `resolveDiscrepancy()` body `{action, justification}` (~53-68) — falta `category_account`; la respuesta tipa solo `{status}` (el backend ya devuelve `git_commit_sha`).
- `ACTIONS_BY_STATE` (~20-28) — espejo del backend; `missing-in-laudus → [confirm-cartola-only, escalate]`.

**Backend (ya done en 6.3, NO tocar salvo AC7/AC8):**
- `reconciliation/models.py`: `ResolveRequest.category_account` + `ResolveResponse.git_commit_sha` ya existen.
- `reconciliation/service.py:resolve()`: anota antes de cerrar; `AnnotationFailed`→422; `confirm-cartola-only` sobre `missing-in-laudus` escribe a `manual/`.
- `reconciliation/router.py`: `history`, `count`, `discrepancies`, `resolve` listos.

### Piezas a reusar (NO reescribir)

| Pieza | Ubicación | Uso |
|---|---|---|
| `getHistory(id)` | `frontend/src/services/reconciliation.ts:47` | AC2 (hoy dead code) |
| Patrón de input de categoría (texto `Expenses:...`) | `frontend/src/pages/CategorizacionPage.tsx:59-66` | AC1 (no hay dropdown de cuentas aún) |
| React Query + invalidación `['reconciliation']`/`['reconciliation-count']` | `ReconciliationPage.tsx:92-93` | AC4/AC6 |
| `fmt(amount, currency)` | helper de formato de la página | AC7 |
| `_laudus_dict` / `build_discrepancy` | `pipeline/importers/reconcile.py:47`, `discrepancy_writer.py:23` | AC7 (emitir `laudus.currency`) |
| `ACTIONS_BY_STATE` / `BLOCKING_STATES` | `reconciliation/service.py:18,15` + frontend | AC8 |

### Anti-regresión

- El **resolve de 6.3** ya está testeado (`test_reconciliation_annotate.py`, 8 tests) y en prod. Tocar el frontend NO debe cambiar el contrato del endpoint. `category_account` es **opcional** (Suspense default) — no convertirlo en obligatorio en la UI (rompería la decisión Q2 de 6.3).
- Los chips de estado (summary) cuentan por estado **sin** aplicar el filtro `state` (para no perder los demás chips al filtrar) — preservar ese comportamiento al sumar los filtros `year_month`/`bank_account_id` (AC3).
- AC7 toca `build_discrepancy` (compartido con 9.6b/6.1) — agregar `laudus.currency` debe ser aditivo (no romper el dedup ni los tests de `test_reconcile*.py`).

### Testing standards

- Backend: pytest en `backend/tests/`, `PYTHONUTF8=1` + `venv/Scripts/python.exe` (gotcha Windows). Patrón de fixture de reconcile en `test_reconcile_cartola.py` / `test_reconciliation_annotate.py`.
- Frontend: harness mínimo hoy (solo `Sidebar.test.tsx` → vitest). Para una story de página, lo realista es **build + verificación manual** del flujo, más component tests si el harness lo permite sin montar medio mundo. **No prometer** cobertura E2E que la infra no soporta (regla del proyecto: no mentir sobre completitud).
- Deploy: frontend es estático en Render (sin Vercel — [[project_deploy_render_no_vercel]]).

### Project Structure Notes

- Frontend: `frontend/src/pages/ReconciliationPage.tsx` + `frontend/src/services/reconciliation.ts` + `frontend/src/components/.../PendingReconciliationBadge.tsx`.
- Backend (solo AC7/AC8): `pipeline/importers/reconcile.py`, `pipeline/importers/discrepancy_writer.py`, `backend/app/api/v1/reconciliation/service.py`.
- Beancount = fuente única; sin Supabase/Sheets/flags (cleanup c4 9.16).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic-6] — Story 6.4 scope (líneas 1079-1080): defers de 9.12 + input de categoría movido de 6.3.
- [Source: _bmad-output/implementation-artifacts/9-12-dashboard-reconciliacion.md] — ACs y defers de UX del dashboard (historial AC6, filtros AC5, badge, FX states).
- [Source: _bmad-output/implementation-artifacts/6-3-aprobar-diferencia-anotar-beancount.md] — backend de anotación, `category_account` opcional (Q2), `git_commit_sha`, `AnnotationFailed`→422; Q5 difirió el input de categoría a esta story.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — defers de 9.12 (historial dead code, deep-link reopen, badge, filtros, FX action-sets, moneda Laudus, label, concurrencia).
- [Source: docs/reconciliation-dashboard.md] — comportamiento documentado + tabla de action-sets por estado.
- [Source: frontend/src/pages/ReconciliationPage.tsx, frontend/src/services/reconciliation.ts] — estado actual del frontend.
- [Source: backend/app/api/v1/reconciliation/{service,models,router}.py] — backend done (6.3).
- [Source: memoria project_epic6_reconciliacion_next] — modelo A, decisiones Q1-Q5 de 6.3.

## Decisiones de diseño (resueltas con Ary 2026-06-24)

1. **Input de categoría (AC1) = dropdown con autocompletado** (no texto plano). Requiere el endpoint nuevo del plan de cuentas (Task 0), porque hoy no existe.
2. **Estados FX `fx-bcch-missing`/`fx-implausible` (AC8) = DIFERIDOS.** Quedan en `escalate`-only; se agregan acciones cuando aparezca un caso real (no spec especulativa). Sin código en 6.4.
3. **Cosméticos (AC7) = SÍ se hacen** (no se difieren): `laudus.currency` (backend emite + front usa) y `bank_account_label` (front joinea con `GET /bank-accounts/`, sin tocar backend).
4. **UX por Sally = SÍ.** El layout del historial, los filtros, y el dropdown de autocompletado pasan por una pasada de UX de Sally **antes** del dev. Esta story queda `ready-for-dev` pero el dev arranca con el spec de UX de Sally como input.

## UX Spec (Sally, 2026-06-24)

> Diseño aterrizado sobre el componente real (`ReconciliationPage.tsx`, Tailwind + shadcn). **Restricción clave:** el kit UI tiene solo `button`, `card`, `skeleton` — NO hay toast/combobox. Todo se resuelve con esos + Tailwind plano, **sin dependencias nuevas** (regla de simplicidad del proyecto). El drill-down lateral mide 420px y scrollea.

### Principio rector
La tarea primaria del contador es **resolver una diferencia**. Todo lo nuevo (historial, filtros, categoría) debe **apoyar** esa decisión sin tapar el botón de acción. Orden de lectura en el drill-down: *contexto → decisión → evidencia histórica*. La acción siempre por encima del fold.

### AC3 — Barra de filtros (arriba de los chips de estado)
- **Layout:** una fila nueva ENTRE el subtítulo y los chips de estado. Dos `<select>` compactos + un link "Limpiar":
  `[ Mes: Todos ▾ ]  [ Cuenta: Todas ▾ ]   (· Limpiar filtros)`
- Estilo de cada select = el del selector de acción que ya existe (`border rounded-md px-3 py-2 bg-background text-sm`). Etiqueta inline a la izquierda (`text-xs text-muted-foreground`).
- **Mes:** opciones derivadas de los `year_month` presentes en el dataset (orden desc), + "Todos los meses" (default). 
- **Cuenta:** opciones desde `GET /bank-accounts/` mostrando el **label** (no el UUID); value = `bank_account_id`; + "Todas las cuentas" (default).
- Los **chips de estado quedan debajo**, sin cambios — combinan con los filtros (el summary refleja el scope mes/cuenta; los chips de estado siguen visibles aunque den 0, para no perder la navegación).
- "Limpiar filtros" aparece solo si hay algún filtro activo (incluido el chip de estado).
- **Empty state filtrado:** cuando los filtros no dan resultados, el Card vacío dice *"No hay diferencias para este filtro."* + botón `Limpiar filtros`. (Distinto del 🎉 "No hay diferencias para revisar" cuando de verdad no hay nada.)

### AC1 — Autocompletado de categoría (drill-down, solo `confirm-cartola-only`)
- **Dónde:** dentro del bloque de acción, ENTRE el `<select>` de Acción y la textarea de justificación. Renderiza **solo** si `action === 'confirm-cartola-only'`.
- **Componente (custom, liviano):** un input de texto + popover de resultados filtrados (no hay Combobox en el kit). Estructura:
  - `label`: **"Categoría del gasto (opcional)"**.
  - input con `placeholder="Buscar cuenta… (ej. Expenses:EAG:Super)"`, ícono de lupa opcional, botón ✕ para limpiar cuando hay valor.
  - al tipear (≥1 char) se abre un `<ul>` absolute (max-h-48 overflow-auto, `border rounded-md bg-card shadow`) con las cuentas `Expenses:*` que matchean (substring, case-insensitive) desde `GET /accounts?root=Expenses`.
  - cada opción: `px-3 py-1.5 text-sm hover:bg-accent cursor-pointer`, resalta el match.
  - **Teclado (accesibilidad, Norman aprobaría):** ↑/↓ navegan, Enter selecciona, Esc cierra. `role="listbox"`/`option`, `aria-activedescendant`.
  - seleccionar rellena el input y cierra el popover.
- **Validación suave:** se permite confirmar con el campo vacío (→ Suspense) o con una cuenta de la lista. Si el texto no matchea ninguna cuenta y no está vacío → borde ámbar + hint *"cuenta no reconocida — se validará al guardar"* (el backend igual valida; un 422 con cuenta inválida se maneja en AC6). No bloquear el submit por esto.
- **Hint (clave para Q2 de 6.3):** debajo del input, `text-xs text-muted-foreground`:
  *"Si lo dejás vacío, el gasto entra como pendiente y lo categorizás después en Categorización."*

### AC2 — Historial de la discrepancia (drill-down)
- **Dónde:** AL FINAL del drill-down, DESPUÉS del bloque de acción (la decisión va primero; el historial es evidencia de apoyo). Separado por un divider sutil (`border-t pt-4`) y un título **"Historial"**.
- **Datos:** `GET /api/v1/reconciliation/history/{id}` (hoy dead code). Render como **timeline vertical** (línea + dots):
  - **Primer ítem (origen):** *"Detectada"* + `ts` formateado + el estado inicial. Dot neutro.
  - **Ítems siguientes** (resoluciones/escalations, en orden): acción en negrita legible (mapear: `confirm-cartola-only`→"Confirmada como gasto", `escalate`→"Escalada", etc.), `resolved_by` + fecha en `text-xs text-muted-foreground`, y la **justificación** en una línea `italic` truncada a 2 líneas (`line-clamp-2`) con expandir al click. Dot ámbar (escalada) / verde (resuelta).
- **Estados:** loading = `<Skeleton>` de 3 líneas (el kit ya tiene `skeleton.tsx`); si solo existe el origen (sin resoluciones), mostrar solo *"Detectada {ts}"* — no un vacío frío.
- Tipar la respuesta del history en `reconciliation.ts` (hoy `entries: unknown[]`).

### AC6 — Feedback de éxito + manejo del 422 (sin toasts)
- **Éxito (banner inline, no toast):** al resolver OK, en vez de cerrar el drill-down de inmediato, mostrar **1.5–2s** un banner verde dentro del panel: `bg-green-50 text-green-700 rounded-md px-3 py-2 text-sm` →
  - acción normal: *"✓ Diferencia resuelta."*
  - anotación (`git_commit_sha` presente): *"✓ Gasto anotado en el ledger ({sha corto})."* (mostrar primeros 7 chars del sha, `font-mono`).
  - luego cerrar + invalidar queries (lo que ya hace `onResolved`).
- **Botón confirmar:** label dinámico — *"Anotando…"* cuando es `confirm-cartola-only` en vuelo, *"Confirmando…"* el resto.
- **Error 422 (`AnnotationFailed`, bean-check rojo):** NO cerrar el drill-down. Banner rojo (`bg-red-50 text-red-600`) con el detalle del backend + una línea fuerte: *"La diferencia sigue ABIERTA — no se contabilizó."* Así el contador corrige la categoría y reintenta sin perder el contexto. (Distinguir del 400 de validación, que es el mismo estilo pero sin el "sigue abierta".)
- El `mutation.error` actual (línea 164) se reemplaza por este manejo diferenciado por status.

### Cosméticos (AC7) — nombre de cuenta + moneda
- **Tabla y drill-down:** mostrar el **nombre de la cuenta** (label de `/bank-accounts/`) en vez del `bank_account_id` UUID. En la tabla puede ir como columna o en el tooltip de la fila; mínimo, en el drill-down (sección "Detalle") como subtítulo: *"{label} · {year_month}"*.
- **Celda Laudus:** `fmt(d.laudus?.amount, d.laudus?.currency)` para que las filas USD no muestren símbolo CLP.
- **Bonus barato (opcional):** el componente `Section` genérico hoy vuelca llaves crudas (`line_no`, `amount`…). Si sobra tiempo, mapear a etiquetas legibles (Fecha, Monto, Glosa) y formatear montos/fechas — mejora mucho la legibilidad del drill-down. No bloqueante.

### Notas de interacción transversales
- **Mobile/narrow:** el drill-down de 420px fixed funciona en desktop (el uso real del contador). No se diseña mobile en esta story.
- **Consistencia:** reusar `Chip`, `StateBadge`, `Card`, `Button`, `Skeleton` existentes. El autocompletado y el timeline son los únicos componentes nuevos — mantenerlos como helpers locales en `ReconciliationPage.tsx` (o extraer si crecen), no una librería.
- **Foco:** al abrir el drill-down, foco al primer control accionable; Esc cierra el panel.

### Handoff a dev
Con este spec, las 4 ACs de interacción quedan especificadas sin ambigüedad. El único componente con riesgo de scope es el autocompletado (Task 0 + Task 1) — está acotado a input+popover+teclado, sin dependencias. El resto reusa lo que ya hay.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (dev-story, 2026-06-24). UX spec por Sally (embebido arriba).

### Debug Log References

- Backend: `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` → **574 passed, 1 xfailed, 2 failed**. Los 2 rojos (`test_fava_edit_validator`) son PRE-EXISTENTES (ajenos). 0 regresiones nuevas.
- Frontend: `npx tsc -b` (typecheck) **exit 0**; `npx eslint <archivos tocados>` **exit 0**; `npx vite build` **exit 0**; `npx vitest run` → **60 passed** (4 files, +3 nuevos en `ReconciliationPage.test.tsx`).

### Completion Notes List

**Implementado (las 8 ACs; AC8 diferida por decisión Ary):**
- **Task 0 (AC1):** endpoint nuevo `GET /api/v1/accounts?root=Expenses` (`backend/app/api/v1/accounts/`) — parsea los `open` del ledger, excluye `:PendingReview:`. Monté el router en `api/v1/router.py`. 3 tests unitarios.
- **Task 1 (AC1):** dropdown de categoría con autocompletado (`CategoryAutocomplete`, componente local) en el drill-down, solo para `confirm-cartola-only`; teclado (↑/↓/Enter/Esc), borde ámbar + hint si la cuenta no se reconoce, hint de Suspense. `reconciliation.ts`: `category_account` en el body + `git_commit_sha` en la respuesta + `ResolveHttpError` (conserva el status). Service nuevo `accounts.ts`.
- **Task 2 (AC2):** `HistoryPanel` con timeline (`getHistory`, antes dead code) — origen + resoluciones/escalations, dots por tipo, Skeleton en loading.
- **Task 3 (AC3):** barra de filtros (`<input type="month">` para mes — mapea directo a `year_month`; `<select>` de cuenta desde `/bank-accounts/`); "Limpiar filtros"; empty-state diferenciado.
- **Task 4 (AC4, AC6):** deep-link DERIVADO del estado (sin effect ni ref — patrón `manualSelected ?? deepLinkMatch`, `deepLinkDismissed` al cerrar) → ya NO se reabre al resolver. Banner de éxito (verde, con sha corto si anota) + 422 (rojo, "sigue ABIERTA", no cierra el panel).
- **Task 5 (AC5):** `PendingReconciliationBadge` distingue `isError && !data` (chip neutro "no se pudo cargar") de "0 pendientes" (oculto).
- **Task 6 (AC7):** backend emite `laudus.currency` (`LaudusEntry.currency` + `load_laudus_entries` + `_laudus_dict`); el front usa la moneda real en la celda Laudus y muestra el **nombre de la cuenta** (join con `/bank-accounts/`) en vez del UUID.
- **Task 7 (AC8):** DIFERIDA (decisión Ary Q2) — `fx-bcch-missing`/`fx-implausible` quedan en `escalate`-only, sin código.

**Decisiones Ary (al arrancar):** Q1 dropdown autocompletado (→ endpoint nuevo); Q2 estados FX diferidos; Q3 cosméticos SÍ (moneda + nombre de cuenta); Q4 UX por Sally (spec embebido).

**Desviaciones/notas:** el lint de React 19 prohíbe `setState` en effect Y tocar refs en render → el deep-link se resolvió derivando el estado (sin effect/ref), que es el patrón idiomático y de paso más limpio. Frontend sin toasts → feedback con banners inline.

### File List

- `backend/app/api/v1/accounts/__init__.py` (A), `accounts/service.py` (A), `accounts/router.py` (A) — endpoint del plan de cuentas.
- `backend/app/api/v1/router.py` (M) — monta el accounts router.
- `pipeline/importers/matching_engine.py` (M) — `LaudusEntry.currency` + `load_laudus_entries` la captura.
- `pipeline/importers/reconcile.py` (M) — `_laudus_dict` emite `currency`.
- `backend/tests/test_accounts_service.py` (A) — 4 tests (list_accounts + laudus currency).
- `frontend/src/services/reconciliation.ts` (M) — `category_account`/`git_commit_sha`, `HistoryEntry`, `ResolveHttpError`.
- `frontend/src/services/accounts.ts` (A) — `listAccounts`.
- `frontend/src/pages/ReconciliationPage.tsx` (M) — filtros, autocompletado, historial, feedback, deep-link fix, cosméticos.
- `frontend/src/pages/ReconciliationPage.test.tsx` (A) — 3 component tests.
- `frontend/src/components/layout/PendingReconciliationBadge.tsx` (M) — estado de error.

### Change Log

- 2026-06-24: Story 6.4 implementada (Tasks 0-6, 8; Task 7 diferida por decisión Ary). Backend: endpoint de cuentas + `laudus.currency`. Frontend: filtros, autocompletado de categoría, historial, feedback éxito/422, fix deep-link, cosméticos, badge. 574 backend passed + 60 frontend passed; 0 regresiones nuevas; typecheck/lint/build verdes.
