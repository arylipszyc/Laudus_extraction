# Story 7.1: El owner (rol `family`) crea un comentario sobre una transacción — FR36

Status: review

<!-- Depende de 7.0 (módulo owner_comments + ancla + persistencia). No arrancar antes de que 7.0 esté done. -->

## Story

As a **owner del family office (rol `family`)**,
I want **dejar un comentario sobre una transacción específica del ledger (ej. "¿qué es este cargo?" sobre un movimiento de una cartola)**,
so that **pueda pedirle al contador que aclare o corrija ese movimiento sin tener que mandarle un mail suelto ni describirle de memoria de qué transacción hablo — el comentario queda pegado a la transacción, con su contexto**.

> **Primer endpoint de ESCRITURA para el rol `family`.** Hasta hoy `family` es solo-lectura (todos los writes son `contador/admin`). Esta story materializa el cambio de postura RBAC que 7.0 ratificó: `family` puede escribir **comentarios** (nunca asientos). Ver ADR de 7.0.

## Contexto

7.0 dejó el módulo `owner_comments` con: el writer JSONL (`owner-comments.jsonl`), la captura de ancla de 3 capas (`build_anchor`: `tx_id` + `ledger_git_sha` + `anchor_key` + `tx_snapshot`), y el helper de persistencia bajo lock (`persist_and_commit`). Esta story expone el **endpoint de creación** y la **acción de UI** para que el owner cree un hilo raíz sobre una transacción. La respuesta del contador (7.2) y la resolución (7.3) son stories aparte; acá solo se **crea** el comentario raíz.

## Acceptance Criteria

1. **AC1 — El owner crea un comentario sobre una transacción.**
   Given una transacción existente en el ledger (identificada por su `tx_id`),
   When el owner llama `POST /api/v1/comments` con `{tx_id, body}` (body ≥ 1 char, no vacío),
   Then el sistema captura el ancla vía `build_anchor(tx_id, entries, ledger_root)` (7.0 AC4), arma el comentario raíz con `build_comment(...)` (autor = email/rol del JWT), lo appendea a `owner-comments.jsonl` y lo commitea+pushea vía `persist_and_commit` (7.0 AC6), y devuelve `{thread_id, comment_id, created_at}` (201).

2. **AC2 — RBAC: `family`, `contador` y `admin` pueden crear; nadie más.**
   Given el endpoint,
   Then usa `require_role(["family","contador","admin"])`. Un JWT sin rol válido → 401; un rol fuera de la lista → 403 con log `RBAC_DENIED` (comportamiento de `require_role`, `dependencies.py:60`). **Este es el primer write que admite `family`** — verificar explícitamente en test que un `family` obtiene 201 (no 403).

3. **AC3 — Comentar sobre una tx inexistente falla limpio.**
   Given un `tx_id` que no resuelve contra los `entries` actuales,
   When se llama `POST /api/v1/comments`,
   Then `build_anchor` levanta el error de "tx no encontrada" → 404 (no 500), y **nada** se escribe al JSONL ni se commitea.

4. **AC4 — El comentario guarda el ancla completa de 3 capas + snapshot.**
   Given un comentario creado,
   Then la línea persistida contiene `tx_id`, `ledger_git_sha`, `anchor_key`, `tx_snapshot` (`date`, `amount`, `currency`, `account`, `narration`), `author_email`, `author_role`, `body`, `ts`, `thread_id`, `comment_id`. (Es lo que hace que 7.2/7.4 puedan re-resolver el ancla tras un re-import.)

5. **AC5 — Atomicidad: si el commit/push falla, no queda un comentario "a medias".**
   Given `persist_and_commit`,
   Then el orden y el manejo de error son consistentes con el proyecto: si `git_commit_push` falla real (no el no-op de git deshabilitado), el error se propaga → el endpoint devuelve 500 con detalle. (El append local ya ocurrió dentro del lock; el riesgo de doble-escritura en retry es el mismo boundary conocido de `commit_reconciliation`/`git_commit_push` y se documenta, no se resuelve acá.)

6. **AC6 — Acción de UI para el owner: comentar desde el detalle/lista de una transacción.**
   Given una vista donde el owner ve transacciones (ej. el reporte de gastos o el detalle de una tx),
   When el owner elige "Comentar" sobre una fila,
   Then aparece un input de comentario; al enviarlo, llama `POST /api/v1/comments` con el `tx_id` de esa fila y muestra confirmación (sin toast, estilo Cards/badges del proyecto). La acción es visible para `family` (a diferencia de los chips de categorización/reconciliación que se ocultan para `family`).

7. **AC7 — Tests + sin regresiones.**
   Backend: `family` crea → 201 + línea en el JSONL con ancla completa (AC2, AC4); `tx_id` inexistente → 404 sin escritura (AC3); rol inválido → 403; body vacío → 422. Frontend: component test de la acción de comentar (input, submit, confirmación). `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` + `npx tsc --noEmit` verdes, 0 regresiones nuevas.

## Tasks / Subtasks

- [x] **Task 1 — Módulo API `owner_comments`** (AC1, AC2, AC3, AC5)
  - [x] `backend/app/api/v1/owner_comments/` (`router.py` + `service.py` + `schemas.py` + `__init__.py`), registrado en `backend/app/api/v1/router.py` (junto a los `include_router`). `router = APIRouter(prefix="/comments", tags=["owner-comments"])`.
  - [x] `POST /comments` con `require_role(["family","contador","admin"])`, `ledger: LedgerService = Depends(get_ledger_service)`. Service: `create_comment(tx_id, body, user_email, user_role, entries, ledger_root)` → `build_anchor` → `build_comment` → `persist_and_commit`. Mapear "tx no encontrada" → 404.
  - [x] Schemas: `CreateCommentRequest{tx_id: str, body: str}` (validar `body` no vacío vía `StringConstraints(strip_whitespace, min_length=1)` → 422 serializable), `CreateCommentResponse{thread_id, comment_id, created_at}`.

- [ ] **Task 2 — Frontend: acción de comentar** (AC6) — **DIFERIDA a story 7.1b** (decisión Ary 2026-07-09)
  - Bloqueo destapado al implementar: ninguna vista del owner expone el `tx_id` de beancount que el endpoint necesita. El reporte de gastos (`/reportes`) es una **descarga** de Excel (sin filas); el único detalle de tx que el owner ve (drill-down de Ingresos/Gastos) identifica filas por `journalentryid`/`lineid` (modelo Laudus/dashboard), **no** por el `tx_id` de beancount. Ese `tx_id` solo se expone hoy en Categorización (contador/admin). Enganchar el botón requiere decidir vista + trabajo extra → se difiere a una story dedicada, idealmente junto con la UI de leer hilos (7.2/7.4). Ver `7-1b-frontend-comentar-owner.md`.

- [x] **Task 3 — Tests** (AC7)
  - [x] `backend/tests/test_owner_comments_api.py`: `family` 201 + JSONL con ancla; `tx_id` inexistente 404; body vacío 422; sin-auth/rol-desconocido 401. Ledger fixture inline + `monkeypatch.delenv("IMPORTER_GIT_ENABLED")`. (Nota: el "403" del AC7 es **inalcanzable** en este endpoint — la allowlist son los 3 roles válidos, así que un token sin auth válida cae en 401, no 403. Se testea el 401 real.)
  - [ ] Frontend component test del botón/input de comentario — **DIFERIDO a 7.1b** (junto con Task 2).

## Dev Notes

### Piezas de 7.0 que esta story consume (no reimplementar)

| Pieza | De dónde | Uso |
|---|---|---|
| `build_anchor(tx_id, entries, ledger_root)` | `owner_comments` (7.0 AC4) | captura ancla + snapshot + git sha; 404 si el tx_id no resuelve |
| `build_comment(...)` / `append_comment` | `owner_comments_writer` (7.0 AC1) | arma y appendea el comentario raíz |
| `persist_and_commit(mutate, msg, ledger_root)` | `owner_comments` (7.0 AC6) | lock → append → git (sin bean-check) |

### Infra reusada del proyecto (verificada)

- `require_role(["family","contador","admin"])` — `backend/app/dependencies.py:60`. **Ojo:** es el **primer** uso que incluye `family` en un endpoint de escritura; los demás writes (`transactions/router.py:46`, `reconciliation/router.py:75`) son `["contador","admin"]`. Intencional (ADR 7.0).
- `get_ledger_service` / `ledger.entries()` — `dependencies.py:18`; `transactions/router.py:35` (`_entries` con manejo de `LedgerUnavailableError` → 503). Reusar ese wrapper.
- Registro de router — `backend/app/api/v1/router.py` (patrón de `reconciliation`, `transactions`, `tc_reconciliation`).
- Servicio frontend — patrón `fetch`+`credentials:'include'` de `frontend/src/services/reconciliation.ts`.

### Por qué el owner comenta sobre `tx_id` (y no sobre otra cosa)

El `tx_id` es el identificador que ya viaja al frontend en las vistas de transacciones (categorización, reporte). El owner ve una fila, toca "comentar", y el front manda ese `tx_id`. 7.0 se encarga de que ese `tx_id` — aunque cambie en un re-import — se pueda re-resolver después vía `anchor_key`. Esta story no re-resuelve nada (solo crea); la re-resolución la hace 7.2/7.4 al leer.

### Anti-alcance (explícito)

- **No** hay respuesta del contador acá (es 7.2). El comentario raíz queda abierto sin respuesta.
- **No** hay resolución acá (es 7.3).
- **No** hay notificación acá (es 7.4). Crear el comentario no dispara ningún chip todavía — eso lo agrega 7.4 leyendo el JSONL.
- **No** line-item (diferido en 7.0).

### Testing standards

- `pytest` en `backend/tests/`, `PYTHONUTF8=1`, venv `./venv/Scripts/python.exe`. Fixtures de ledger inline (`parse_string`). `monkeypatch.delenv("IMPORTER_GIT_ENABLED")` → git no-op.
- Frontend `vitest` + `npx tsc --noEmit` verde.

### References

- [Source: _bmad-output/implementation-artifacts/7-0-spike-ancla-persistencia-comentarios.md] — módulo, ancla, persistencia, RBAC posture.
- [Source: backend/app/dependencies.py:60] — `require_role` (primer write de `family`).
- [Source: backend/app/api/v1/transactions/router.py:35] — `_entries`/`get_ledger_service` a reusar.
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 7] — FR36.

## Decisiones de diseño para Ary (RESUELTAS 2026-07-09)

1. **¿Dónde vive la acción "Comentar" en la UI del owner?** → **En la fila del reporte de gastos** (`/reportes`, `ReportesPage`). Ary eligió el default: botón de comentario por fila en la vista que el owner ya usa, sin crear página nueva.
2. **¿`body` con límite máximo / markdown?** → **Texto plano, sin límite duro** en el MVP (validar solo no-vacío). Sin markdown/adjuntos. (Decisión técnica tomada por la dev.)

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Amelia / dev-story)

### Completion Notes List

- **Backend entregado y verde (parte sustantiva de la story: primer endpoint de escritura para `family`).** `POST /api/v1/comments` orquesta el módulo habilitador de 7.0 sin reimplementar nada: `build_anchor` (ancla 3 capas + snapshot, 404 si el `tx_id` no resuelve) → `build_comment` → `persist_and_commit` (lock + git, sin bean-check). AC1, AC2 (RBAC family/contador/admin), AC3 (404 sin escritura), AC4 (ancla completa persistida), AC5 (atomicidad heredada de `persist_and_commit`) MET.
- **AC2 — el "403" es estructuralmente inalcanzable acá.** La allowlist del endpoint son los 3 roles válidos (`family`/`contador`/`admin`), y `get_current_user` ya rechaza (401) cualquier rol fuera de ese set. Por eso la rama 403 de `require_role` nunca dispara para este endpoint; el test valida el 401 real (sin cookie / rol desconocido). El mecanismo 403 de `require_role` ya está cubierto en `test_rbac.py`.
- **`body` vacío → 422:** se validó con `StringConstraints(strip_whitespace=True, min_length=1)` en vez de un `field_validator` que levante `ValueError` — este último mete el objeto excepción en el `ctx` del error de pydantic v2 y **rompe el serializador JSON del middleware de errores** (visto en el primer run rojo). La restricción estándar da un error serializable y de paso recorta el body.
- **AC6 (frontend) DIFERIDO a story 7.1b — decisión Ary 2026-07-09.** Gap destapado al implementar: ninguna vista del owner expone el `tx_id` de beancount. El reporte de gastos es una descarga (sin filas); el drill-down de Ingresos/Gastos usa `journalentryid`/`lineid` (modelo Laudus), no el `tx_id` de beancount que exige el ancla; ese `tx_id` solo vive hoy en Categorización (contador/admin). La UI de comentar se hará junto con la de leer hilos (7.2/7.4) para no construir algo que se rehace. Story stub: `7-1b-frontend-comentar-owner.md`.
- **Tests:** 7 nuevos en `test_owner_comments_api.py`. Suite backend **738 passed / 1 xfailed / 0 failed** (+7, 0 regresiones). `venv/Scripts/python.exe -m pytest backend/tests` con `PYTHONUTF8=1`.

### File List

- `backend/app/api/v1/owner_comments/__init__.py` (nuevo)
- `backend/app/api/v1/owner_comments/schemas.py` (nuevo)
- `backend/app/api/v1/owner_comments/service.py` (nuevo)
- `backend/app/api/v1/owner_comments/router.py` (nuevo)
- `backend/app/api/v1/router.py` (modificado — registra `owner_comments_router`)
- `backend/tests/test_owner_comments_api.py` (nuevo)

## Change Log

- 2026-07-09 — Backend de 7.1 implementado (endpoint `POST /comments`, primer write de `family`). 7 tests, 738 backend passed. Frontend (AC6) diferido a 7.1b por gap de `tx_id` en vistas del owner (decisión Ary). Status → review.
