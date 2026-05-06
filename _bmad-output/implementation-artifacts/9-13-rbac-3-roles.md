---
story: 9.13
title: RBAC 3 roles (family / contador / admin)
status: done
epic: 9
depends_on: []
blocks: [9.8, 9.12]
---

# Story 9.13 — RBAC 3 roles (family / contador / admin)

## User Story

As Ary (admin),
I want a 3-role authorization model (`family` / `contador` / `admin`) implemented end-to-end (backend gates + frontend gates + JWT claims + role assignment),
So that family members see only their dashboards (no chips, no edits), the contador can categorize and reconcile but cannot administer infra, and I (admin) retain full control — replacing the current 2-role model (`owner` / `contador`) which conflates "ve todo" con "puede todo".

## Context

Story nueva derivada de la sesión Sally + Ary del 2026-05-05 (`sally-x-moishe-badges-pendiente-2026-05-05.md`). El modelo UX híbrido aprobado requiere distinguir entre **family** (solo ve dashboards Epic 3 con badges informativos), **contador** (categoriza + concilia + ve dashboards read-only) y **admin** (Ary, control total).

El RBAC actual (Story 1.4) tiene 2 roles: `owner` y `contador`. Bajo la matriz nueva:
- `owner` se renombra a `family` (semánticamente más preciso — Eduardo, Abel son family, no owners del sistema).
- `admin` se agrega como rol nuevo para Ary.
- El rol `contador` actual (que hoy hace todo) se redefine para que sea coherente con la matriz: puede categorizar + conciliar, ve dashboards Epic 3 read-only, NO administra infra ni gestiona usuarios.

**Por qué story propia (no distribuir a 9.2 + 9.8):** el RBAC es transversal — toca backend (gates en endpoints), frontend (chips/acciones por rol), JWT claims, asignación de rol al login OAuth, y un refactor del rol `contador` existente. Distribuirlo en 9.2 y 9.8 mezcla auth con dominio (BQL, badges) y deja el rol nuevo `admin` sin home claro. Story dedicada con matriz autoritativa = contrato único para que el resto del epic consuma.

**No es urgente para Amelia día 1** — las stories que dependen de 9.13 son 9.8 y 9.12, que están más adelante en el plan. Pero el refactor del rol `owner → family` debería pasar antes de que cualquier story de Epic 9 pinte producción para evitar JWT inconsistencies.

## Matriz de roles autoritativa

| Capability | `family` (Eduardo, Abel) | `contador` | `admin` (Ary) |
|---|---|---|---|
| Login OAuth + sesión | ✅ | ✅ | ✅ |
| Dashboards Epic 3 (Activos/Pasivos, Ingresos/Gastos, etc.) | ✅ (su vista habitual) | ✅ read-only | ✅ full |
| Drill-down con badges inline (Story 9.8 AC3) | ✅ (tooltip family) | ✅ (tooltip contador + clickeable) | ✅ (tooltip contador + clickeable) |
| Confirmar categoría inline (Story 9.8 AC6) | ❌ | ✅ | ✅ |
| Chip "Categorías pendientes" header (Story 9.8 AC10) | ❌ | ✅ | ✅ |
| Chip "Reconciliaciones pendientes" header (Story 9.12 AC9) | ❌ | ✅ | ✅ |
| Página `/reconciliation` (Story 9.12) | ❌ (HTTP 403) | ✅ full | ✅ full |
| Resolver discrepancias (`POST /reconciliation/.../resolve`) | ❌ | ✅ | ✅ |
| Subir cartolas PDF (`POST /api/v1/cartolas/upload`, Story 9.5) | ❌ | ✅ | ✅ |
| PATCH categoría (`PATCH /api/v1/transactions/{id}/category`, Story 9.7) | ❌ | ✅ | ✅ |
| Acceso a Fava UI (basic auth separado, Story 9.3) | ❌ | ✅ (credencial compartida) | ✅ |
| Sync trigger manual (`POST /api/v1/sync/trigger`) | ❌ | ✅ | ✅ |
| Endpoints admin (`/api/v1/admin/*` — cache reload, etc.) | ❌ | ❌ | ✅ |
| Gestión de usuarios y roles (asignar rol a un email) | ❌ | ❌ | ✅ (manual vía DB / config) |

## Acceptance Criteria

**AC1 — Tipo `UserRole` actualizado a 3 valores**

**Given** el código actual define `export type UserRole = "owner" | "contador"`
**When** se aplica este story
**Then** `UserRole` (frontend `frontend/src/types/auth.ts` y backend equivalente Pydantic) pasa a `"family" | "contador" | "admin"`
**And** todas las ocurrencias de `"owner"` en código (TypeScript + Python + tests) se renombran a `"family"`
**And** se agrega `"admin"` como valor válido en el enum/Literal

---

**AC2 — Migración de claims JWT existentes (`owner` → `family`)**

**Given** los JWTs emitidos por el OAuth flow (Story 1.3) hoy contienen `"role": "owner"`
**When** se aplica este story
**Then** la lógica de asignación de rol al login (`backend/app/auth/oauth.py` o equivalente — donde se decide el rol según el email) cambia a:
  - Emails de family (Eduardo, Abel) → `"family"`
  - Email del contador → `"contador"`
  - Email de Ary (`ary.lipszyc@ammy.cl`) → `"admin"`
**And** los emails-rol mapping vive en config (env var `RBAC_ROLE_MAPPING` JSON o tabla equivalente) — NO hardcoded en código
**And** un usuario con email no-mapeado recibe 403 al intentar login (sin rol asignado = sin acceso)
**And** el `_VALID_ROLES` frozenset en `dependencies.py` se actualiza a `frozenset({"family", "contador", "admin"})`
**And** JWTs viejos con `"role": "owner"` siguen funcionando durante una ventana de migración (TTL del JWT, ~24h): el middleware acepta `"owner"` como alias de `"family"` y loguea warning `LEGACY_ROLE_OWNER_DETECTED`

---

**AC3 — Backend: `require_role()` aplicado según matriz**

**Given** la matriz autoritativa (sección arriba)
**When** se aplican los gates a los endpoints
**Then** los siguientes endpoints están protegidos con `Depends(require_role([...]))`:

| Endpoint | Roles permitidos |
|---|---|
| `POST /api/v1/cartolas/upload` (9.5) | `contador`, `admin` |
| `GET /api/v1/cartolas/{batch_id}` (9.5) | `contador`, `admin` |
| `PATCH /api/v1/transactions/{tx_id}/category` (9.7) | `contador`, `admin` |
| `GET /api/v1/categorization/pending` (9.8 chip) | `contador`, `admin` |
| `GET /api/v1/reconciliation/discrepancies` (9.12) | `contador`, `admin` |
| `GET /api/v1/reconciliation/discrepancies/{id}/history` (9.12) | `contador`, `admin` |
| `POST /api/v1/reconciliation/discrepancies/{id}/resolve` (9.12) | `contador`, `admin` |
| `GET /api/v1/reconciliation/count` (9.12 chip) | `contador`, `admin` |
| `POST /api/v1/sync/trigger` (9.4 on-demand) | `contador`, `admin` |
| `POST /api/v1/admin/cache/reload-accounts` (9.5 cache invalidation) | `admin` |
| Endpoints de dashboards Epic 3 (`/balance-sheets`, `/ledger-entries`, etc.) | `family`, `contador`, `admin` (los 3 leen; sin gate restrictivo) |

**And** todos los endpoints sin gate explícito requieren al menos `Depends(get_current_user)` (autenticación, no autorización por rol)

---

**AC4 — Frontend: gates por rol en componentes nuevos**

**Given** los componentes nuevos de Stories 9.8 y 9.12 referencian la matriz
**When** se renderean
**Then** `useAuth()` expone `user.role` con valores `"family" | "contador" | "admin"` (no más `"owner"`)
**And** los componentes/rutas siguientes están gated:

| Componente / Ruta | Visible para |
|---|---|
| `<PendingCategorizationChip />` (9.8 AC10) | `contador`, `admin` |
| `<PendingReconciliationBadge />` (9.12 AC9) | `contador`, `admin` |
| Modal "Confirmar categoría" (9.8 AC6) | `contador`, `admin` |
| Click navega a `/reconciliation` desde badge inline (9.8 AC3) | `contador`, `admin` |
| Ruta `/reconciliation` (9.12) | `contador`, `admin` (otros → 403 page o redirect) |
| Sidebar item "Subir cartola" (9.5 + Story 1.4 ya tenía gate análogo) | `contador`, `admin` |
| Sidebar item "Sync ahora" (si existe — operacional) | `admin` |

**And** badges informativos inline (9.8 AC3 con tooltip family) son visibles para los 3 roles
**And** dashboards Epic 3 son visibles para los 3 roles sin cambios

---

**AC5 — Defense-in-depth: backend siempre valida (no confiar en frontend)**

**Given** un usuario `family` modifica el JWT manualmente o invoca endpoints directos via curl
**When** llama a un endpoint protegido por `contador` o `admin`
**Then** recibe HTTP 403 con `{"error": {"code": "FORBIDDEN", "message": "Insufficient permissions"}}`
**And** el evento se loguea como `RBAC_DENIED` con `{user_email, user_role, endpoint, required_roles}`

---

**AC6 — `family` ve dashboards y badges, NO ve chips ni acciones**

**Given** un usuario logueado como `family` (Eduardo, Abel)
**When** navega cualquier página del frontend
**Then** ve los 4 dashboards de Epic 3 idénticos a hoy
**And** ve badges inline de "pendiente revisar" en transacciones flagged (Story 9.8 AC3) con tooltip family (lenguaje no-contable)
**And** NO ve chips en el header (ni "Categorías pendientes" 9.8 AC10 ni "Reconciliaciones pendientes" 9.12 AC9)
**And** NO ve ítems de sidebar destinados a contador/admin (subir cartola, sync, reconciliación)
**And** click sobre badges inline NO dispara modales ni navegación — solo tooltip informativo

---

**AC7 — `contador` puede confirmar categorías Y conciliar (sin admin)**

**Given** un usuario logueado como `contador`
**When** usa el sistema
**Then** ve los chips header (categorías + reconciliaciones) y los dashboards read-only
**And** puede confirmar categorías inline (9.8 AC6), navegar a `/reconciliation` (9.12), resolver discrepancias (9.12 AC3), subir cartolas PDF (9.5)
**And** Ary aclaró explícitamente: el contador **también puede asignar categorías** ("tiene algún rol de averiguar qué es cada transacción") — esto ya está cubierto por el PATCH category endpoint (AC3 de esta story)
**And** NO puede invocar endpoints `admin` (sync trigger manual, cache reload) — recibe 403

---

**AC8 — `admin` (Ary) tiene capacidades full**

**Given** Ary logueado como `admin`
**When** usa el sistema
**Then** todo lo de `contador` está disponible
**And** además: endpoints `/api/v1/admin/*` (cache reload, fx-bcch refetch, etc.), gestión de roles (vía edit del config `RBAC_ROLE_MAPPING`)
**And** la sidebar muestra ítems extra de admin (si aplica)

---

**AC9 — Tests E2E por rol**

**Given** los 3 roles definidos
**When** corren los tests
**Then** existen tests que verifican (al menos un caso por rol):
  - `family` → 200 en `/balance-sheets`, 403 en `/cartolas/upload`, 403 en `/reconciliation/discrepancies`, 403 en `/sync/trigger`
  - `contador` → 200 en `/balance-sheets`, 200 en `/cartolas/upload`, 200 en `/reconciliation/discrepancies`, 200 en `/sync/trigger`
  - `admin` → 200 en todos los anteriores
**And** los tests existentes de Story 1.4 (que usaban `owner`) se actualizan a `family`
**And** se agregan al menos 3 tests nuevos para `admin` (uno por endpoint admin-only)

---

**AC10 — Documentación + comunicación a usuarios existentes**

**Given** el rol `owner` desaparece y se reasignan emails
**When** se deploya
**Then** existe `docs/rbac-3-roles.md` con: matriz autoritativa, mapping email → rol vigente, instrucciones para Ary sobre cómo asignar/cambiar un rol (editar `RBAC_ROLE_MAPPING`)
**And** Ary informa a los family members que el sistema sigue funcionando igual (no hay cambio visible para ellos — su experiencia es idéntica salvo el badge inline informativo)
**And** la entrada en MEMORY referenciando "rol owner" se actualiza a "rol family"

---

## Tasks / Subtasks

- [x] Task 1: Renombrar `owner` → `family` y agregar `admin` en types
  - [x] Frontend: `frontend/src/types/user.ts` y `index.ts` → `export type UserRole = "family" | "contador" | "admin"`
  - [x] Backend: `backend/app/auth/schemas.py` → `UserRole = Literal["family", "contador", "admin"]` aplicado a `UserSession.role`
  - [x] Search-and-replace `"owner"` → `"family"` en `.ts`/`.tsx`/`.py` del repo (excepto shim legítimo en `dependencies.py` y `service.py`)
  - [x] Agregar `"admin"` al Literal

- [x] Task 2: Update `_VALID_ROLES` y `require_role()` en `dependencies.py`
  - [x] `_VALID_ROLES = frozenset({"family", "contador", "admin"})`
  - [x] `require_role()` factory acepta listas con los 3 roles (sin cambios estructurales)
  - [x] Log estructurado `RBAC_DENIED user_email=... user_role=... endpoint=... required_roles=...` para AC5

- [x] Task 3: Mapping email → rol vía config (AC2)
  - [x] Env var `RBAC_ROLE_MAPPING` (JSON) con priority sobre legacy `ALLOWED_USERS`
  - [x] Loader en `auth/service.py:get_role_for_email()` lookup el rol al login (preserva flow OAuth existente)
  - [x] Email no-mapeado → `get_role_for_email` retorna `None` → callback OAuth emite HTTP 403 (preservado de Story 1.3)
  - [x] Fallback `ALLOWED_USERS` mantenido para no breakear deploy actual durante el cutover

- [x] Task 4: Compatibility shim para JWTs viejos (AC2)
  - [x] `_LEGACY_ROLE_ALIAS = {"owner": "family"}` en `dependencies.py:get_current_user`
  - [x] Log warning `LEGACY_ROLE_OWNER_DETECTED email=... legacy_role=owner mapped_to=family`
  - [x] Ventana de migración = TTL del JWT (`JWT_EXPIRE_HOURS`, default 8h) — documentado en `docs/rbac-3-roles.md`
  - [x] Normalización en input también: `_LEGACY_ROLE_NORMALIZE` en `service.py` para tolerar `"owner"` en env vars

- [x] Task 5: Aplicar `require_role()` a endpoints según AC3
  - [x] **Sync trigger** (`POST /api/v1/sync/trigger`) → `[contador, admin]` (decisión Ary 2026-05-06; diverge de la matriz original que pedía admin-only — Ary aclaró que contador también necesita poder iniciar sync)
  - [x] **Admin endpoints** (`POST /api/v1/admin/fx-bcch/refetch`) → `[admin]` (era `owner`, ahora estricto admin)
  - [x] **Bank accounts CRUD** (`POST/PATCH /api/v1/bank-accounts`) → `[contador, admin]` (admin hereda capacidades contador)
  - [x] **Plan de cuentas sync** (`POST /api/v1/plan-de-cuentas/sync`) → `[contador, admin]`
  - [ ] **Cartolas/upload, transactions/category, categorization/pending, reconciliation/*, admin/cache/reload-accounts**: endpoints aún no existen — los implementan stories 9.5/9.7/9.8/9.12 con la matriz como contrato. NO bloquea esta story (consumidores aguas abajo).

- [x] Task 6: Frontend gates en componentes (AC4)
  - [x] Helper `useHasRole(roles: readonly UserRole[]): boolean` en `frontend/src/hooks/useHasRole.ts`
  - [x] Sidebar: items "Cargar Cartola" + "Reconciliación" gated a `[contador, admin]`
  - [ ] Componentes nuevos de 9.8 + 9.12 (chips, modales, ruta `/reconciliation`): consumirán `useHasRole` cuando se implementen — el helper queda expuesto. NO bloquea esta story.

- [x] Task 7: Tests (AC9)
  - [x] Backend: 14 tests RBAC nuevos en `test_rbac.py` cubriendo matriz 3 roles + shim legacy + log RBAC_DENIED
  - [x] Backend: 5 tests nuevos en `test_auth.py` para `RBAC_ROLE_MAPPING` (priority, fallback, legacy normalize, invalid JSON, unmapped email)
  - [x] Backend: tests existentes refactorizados (`test_admin_fx_bcch.py`, `test_sync.py`, `test_dashboard.py`, `test_bank_accounts.py`, `test_plan_de_cuentas.py`) — `owner` → `family` + tests nuevos para admin donde corresponde
  - [x] Frontend: `Sidebar.test.tsx` con 3 tests (family / contador / admin) — visibilidad de items por rol

- [x] Task 8: Documentación (AC10)
  - [x] `docs/rbac-3-roles.md` con matriz, email mapping, instrucciones admin, shim, defense-in-depth, out of scope
  - [x] Heads-up a Ary documentado en Completion Notes: necesita coordinar re-login con Eduardo/Abel cuando deploye (decisión 2026-05-06)
  - [ ] MEMORY index: no contenía referencias al rol `owner`, no requiere update

---

## Dev Notes

### Input autoritativo

`sally-x-moishe-badges-pendiente-2026-05-05.md` — modelo UX híbrido + matriz roles 3-tier. `bob-x-moishe-epic9-migracion-beancount-2026-04-30.md` — Flag 5 (decisión: story dedicada para RBAC). `1-4-role-based-access-control-rbac.md` — patrón existente `require_role()` que se preserva.

### Por qué story dedicada (no 9.2 / 9.8)

El RBAC es transversal: backend gates + frontend gates + JWT claims + role assignment + refactor del rol existente. Distribuirlo desfocaliza 9.2 (que es BQL) y 9.8 (que es UX badges); además deja `admin` sin home. Costo: 1 story extra. Beneficio: matriz autoritativa única + tests aislados + cambios al rol gestionados en 1 lugar.

### Refactor del rol `contador` existente

Hoy `contador` (en Story 1.4) tiene poder full sobre escrituras financieras. Bajo la matriz nueva, `contador` queda capado:
- ✅ Sigue pudiendo: confirmar categorías, conciliar, subir cartolas, ver dashboards, acceder a Fava.
- ❌ Pierde: sync trigger manual, endpoints admin (que hoy puede no existir o estar abiertos — esta story los introduce y los gate a admin).

Si Ary considera que el contador externo necesita más capacidades en algún punto, abrir story de ajuste de matriz.

### Compatibilidad con Fava (Story 9.3)

Fava tiene su propio basic auth (Story 9.3 — credencial compartida única). Esto NO se modifica acá. Family no accede a Fava (basic auth es solo para contador + admin). El rol del JWT del LAUDUS frontend NO se propaga a Fava — son dos sistemas de auth separados que comparten política.

### Email mapping

Vive como env var `RBAC_ROLE_MAPPING` (JSON). Ejemplo:
```json
{
  "ary.lipszyc@ammy.cl": "admin",
  "eduardo@eag.cl": "family",
  "abel@eag.cl": "family",
  "contador.externo@firma.cl": "contador"
}
```
Cuando se asigna nuevo contador externo, Ary edita el env var en Render dashboard + restartea. Sin DB migration. Coherente con la dirección "infra como código + minimum stateful".

### Defense-in-depth

Toda gate en frontend tiene su contraparte en backend. **Frontend gates son UX (no security)** — el ataque vector real es alguien modificando el JWT o llamando endpoints directos. Todos los tests AC9 ejercitan la capa backend para asegurar que el gate sirve si el frontend se bypassea.

### Out of scope

- OAuth provider switch (sigue Google OAuth de Story 1.3 — no se cambia).
- Two-factor auth — futuro si Ary lo decide.
- Granular permissions (más allá de rol) — overkill para 3 usuarios + 1 admin.
- Audit log de acciones por rol (vamos con `RBAC_DENIED` en logs por ahora; si Ary necesita audit profundo, abrir story aparte).
- Rotación periódica de credenciales del contador externo.
- UI de gestión de roles (admin lo edita vía env var, no hay página).

### Project structure

```
backend/app/
  dependencies.py                          # MODIFY (_VALID_ROLES, require_role)
  auth/
    oauth.py                               # MODIFY (lookup rol via RBAC_ROLE_MAPPING)
    legacy_role_shim.py                    # NEW (compat owner → family — TTL 24h)
  models/auth.py                           # MODIFY (UserRole literal)
frontend/src/
  types/auth.ts                            # MODIFY (UserRole)
  hooks/useAuth.ts                         # MODIFY (expose role)
  hooks/useHasRole.ts                      # NEW (helper)
  components/Sidebar.tsx                   # MODIFY (filtrar items por rol)
docs/
  rbac-3-roles.md                          # NEW
```

### References

- [Source: sally-x-moishe-badges-pendiente-2026-05-05.md — modelo UX híbrido + matriz autoritativa 3 roles]
- [Source: bob-x-moishe-epic9-migracion-beancount-2026-04-30.md — Flag 5 + decisión story dedicada (votos Ary + Bob alineados)]
- [Source: 1-4-role-based-access-control-rbac.md — patrón `require_role()` que se preserva + extiende]
- [Source: 9-8-frontend-thin-api-badge-pendiente.md — consumidor del gate (chips + acciones)]
- [Source: 9-12-dashboard-reconciliacion.md — consumidor del gate (página + endpoints)]

---

## Dev Agent Record

### Implementation Plan (ejecutado)

8 tasks en orden secuencial. Backend foundation primero (types + dependencies + service), luego endpoints, luego frontend, luego tests, luego docs.

### Decisiones de implementación

1. **Sync trigger queda en `[contador, admin]`** (no admin-only como pedía la matriz original). Decisión Ary 2026-05-06 durante implementación: el contador necesita poder iniciar syncs. Documentado en `docs/rbac-3-roles.md` y flageado a Moishe en coord file. No re-abierto: Ary aclaró explícitamente.

2. **`bank_accounts` y `plan_de_cuentas` CRUD** pasan a `[contador, admin]` (antes solo `contador`). Razón: bajo nueva matriz `admin` por definición hereda todas las capacidades de `contador`. Sin esto, Ary perdería acceso a estos endpoints después del refactor.

3. **`RBAC_ROLE_MAPPING` con fallback a `ALLOWED_USERS`**. AC2 pide la nueva env var como SoT, pero el deploy en Render todavía usa `ALLOWED_USERS`. El fallback evita un breaking en producción mientras Ary actualiza el env var en Render dashboard. Cuando Ary haga el cutover, puede borrar `_parse_allowed_users()` (es deuda técnica acotada, documentada).

4. **Normalización `"owner" → "family"` en dos capas**:
   - **Input** (env vars): `_LEGACY_ROLE_NORMALIZE` en `service.py` tolera `"owner"` en `ALLOWED_USERS` o `RBAC_ROLE_MAPPING` (operador olvidado de actualizar config).
   - **JWT decode**: `_LEGACY_ROLE_ALIAS` en `dependencies.py` mapea JWTs viejos minted antes del refactor.
   - Ambas emiten log de auditoría. Ambas se borran post-cutover.

5. **Endpoints aguas abajo NO los bloquean stories 9.5/9.7/9.8/9.12**. La matriz es contrato — cuando esas stories implementen los endpoints respectivos, simplemente aplicarán `Depends(require_role([...]))` con los roles indicados en AC3. No requiere coordinación adicional con esta story.

6. **`useHasRole` simple, no más componentes gated** que Sidebar. La matriz dice que componentes nuevos de 9.8/9.12 (chips, modales, página `/reconciliation`) usan el helper, pero esos componentes aún no existen — los crean las stories aguas abajo. Esta story expone el helper + lo prueba con Sidebar como caso de uso real.

### Validación

- **Backend tests**: 246 passed / 1 failed. La única falla es `test_run_backfill_calls_upsert_for_both_sheets` en `test_sync.py` — pre-existing failure ya flageado en stories 9.0 y 9.1 (no relacionado con RBAC). Subset de archivos afectados por el refactor: 102/102 verde (test_rbac, test_auth, test_admin_fx_bcch, test_bank_accounts, test_plan_de_cuentas, test_dashboard).
- **Frontend tests**: 57/57 verde (incluyendo 3 nuevos en `Sidebar.test.tsx`).
- **TypeScript**: `tsc -b` compila sin errores.

### Completion Notes

- ✅ AC1 — `UserRole` ahora es `Literal["family", "contador", "admin"]` en backend (Pydantic) y TypeScript.
- ✅ AC2 — `RBAC_ROLE_MAPPING` implementado + JWT shim 24h + log `LEGACY_ROLE_OWNER_DETECTED`.
- ✅ AC3 — endpoints existentes gated. Endpoints aguas abajo (no implementados aún) tienen contrato documentado en matriz.
- ✅ AC4 — `useHasRole` hook + Sidebar refactorizada.
- ✅ AC5 — Defense-in-depth: log estructurado `RBAC_DENIED` con todos los campos requeridos. Cubierto por test `test_rbac_denied_logs_structured_event`.
- ✅ AC6 — Family no ve items contador en Sidebar. Tests verifican esto.
- ✅ AC7 — Contador puede `[contador, admin]` endpoints (sync + bank + plan + nuevos). NO puede admin endpoints (verificado por test).
- ✅ AC8 — Admin hereda todas las capacidades + acceso exclusivo a `/api/v1/admin/*`.
- ✅ AC9 — Tests E2E por rol en `test_rbac.py` (3 endpoints × 3 roles + shim + log) + tests refactorizados en suites existentes.
- ✅ AC10 — `docs/rbac-3-roles.md` creado.

### ⚠️ Heads-up para Ary (operacional, post-deploy)

1. **Actualizar env var `RBAC_ROLE_MAPPING` en Render** antes de re-loguear users:
   ```json
   {"ary.lipszyc@ammy.cl": "admin", "eduardo@eag.cl": "family", "abel@eag.cl": "family", "<contador-email>": "contador"}
   ```
   Mientras no se actualice, el sistema sigue leyendo `ALLOWED_USERS` (compat shim) — pero `"owner"` se normaliza a `"family"`, así que vos perdés acceso `admin` hasta que actualices el mapping.

2. **Coordinar re-login con Eduardo/Abel**: el JWT shim mantiene sesiones activas funcionando como `family` por la ventana TTL (~8h). Después necesitan re-loguearse para obtener un JWT con la taxonomía nueva. Vos coordinás directo con ellos (decisión cerrada: yo no escribo docs ni mails).

3. **Borrar shim post-cutover** (opcional, deuda técnica acotada): cuando todos los JWTs legacy expiren, podés borrar `_LEGACY_ROLE_ALIAS` de `dependencies.py` y `_LEGACY_ROLE_NORMALIZE` de `service.py`. Sin urgencia.

### Divergencia respecto a la story original (para review de Moishe)

- **Sync trigger** = `[contador, admin]` en vez de admin-only. Decisión Ary durante implementación 2026-05-06. Si Moishe considera que la matriz autoritativa debe actualizarse en la story file, queda a su discreción patchear AC3 / AC8 / matriz autoritativa en este file.

### File List

**Backend (modified):**
- `backend/app/auth/schemas.py` — agregado `UserRole` Literal, aplicado a `UserSession.role`
- `backend/app/auth/service.py` — agregado `_parse_rbac_role_mapping()`, `_normalize_role()`, `_LEGACY_ROLE_NORMALIZE`; `get_role_for_email()` ahora prefiere `RBAC_ROLE_MAPPING` con fallback a `ALLOWED_USERS`
- `backend/app/dependencies.py` — `_VALID_ROLES` actualizado a 3 roles, agregado `_LEGACY_ROLE_ALIAS` shim, `require_role()` emite log `RBAC_DENIED`
- `backend/app/api/v1/admin/router.py` — `fx-bcch/refetch` ahora `require_role(["admin"])` (era `["owner"]`)
- `backend/app/api/v1/sync/router.py` — `sync/trigger` ahora `require_role(["contador", "admin"])` (era `["contador"]`)
- `backend/app/api/v1/bank_accounts/router.py` — endpoints CRUD ahora `["contador", "admin"]`
- `backend/app/api/v1/plan_de_cuentas/router.py` — `sync` endpoint ahora `["contador", "admin"]`

**Backend (tests modified):**
- `backend/tests/test_rbac.py` — refactorizado completo: 14 tests cubren matriz 3 roles, shim legacy, log RBAC_DENIED
- `backend/tests/test_auth.py` — 5 tests nuevos para `RBAC_ROLE_MAPPING`; refactor `owner` → `family` en tests existentes
- `backend/tests/test_admin_fx_bcch.py` — `_owner_cookie()` → `_admin_cookie()`; tests verifican que family/contador reciben 403
- `backend/tests/test_sync.py` — `owner_token()` → `family_token()`; agregado `admin_token()` + `test_sync_trigger_admin_returns_triggered`
- `backend/tests/test_dashboard.py` — `owner_token()` → `family_token()`
- `backend/tests/test_bank_accounts.py` — `_owner_cookie()` → `_family_cookie()`
- `backend/tests/test_plan_de_cuentas.py` — `_owner_cookie()` → `_family_cookie()`

**Frontend (modified):**
- `frontend/src/types/user.ts` — `UserRole = 'family' | 'contador' | 'admin'`
- `frontend/src/types/index.ts` — `UserRole` actualizado
- `frontend/src/components/layout/Sidebar.tsx` — usa `useHasRole(['contador', 'admin'])` en vez de check directo

**Frontend (new):**
- `frontend/src/hooks/useHasRole.ts` — helper `useHasRole(roles: readonly UserRole[]): boolean`
- `frontend/src/components/layout/Sidebar.test.tsx` — 3 tests RBAC matrix

**Docs (new):**
- `docs/rbac-3-roles.md` — matriz, mapping, instrucciones admin, shim, defense-in-depth

### Change Log

| Date | Change | Author |
|---|---|---|
| 2026-05-06 | Story 9.13 implemented end-to-end (8 tasks, 10 ACs). Backend gates + frontend gates + JWT shim + email mapping + tests + docs. Status → review. | Amelia |
| 2026-05-06 | Review aprobada. Patch matriz autoritativa: sync trigger pasa a `[contador, admin]` (refleja decisión Ary durante implementación). Cambios en matriz línea 46 + AC3 tabla + AC8 + AC9 contador test. Status → done. | Moishe |
