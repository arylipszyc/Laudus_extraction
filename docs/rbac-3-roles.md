# RBAC — 3 Roles (Story 9.13)

## Authoritative role matrix

| Capability | `family` | `contador` | `admin` |
|---|---|---|---|
| Login OAuth + sesión | ✅ | ✅ | ✅ |
| Dashboards Epic 3 (lectura) | ✅ | ✅ read-only | ✅ |
| Drill-down con badges inline | ✅ tooltip family | ✅ clickeable | ✅ clickeable |
| Confirmar categoría inline (9.8 AC6) | ❌ | ✅ | ✅ |
| Chip "Categorías pendientes" header (9.8 AC10) | ❌ | ✅ | ✅ |
| Chip "Reconciliaciones pendientes" header (9.12 AC9) | ❌ | ✅ | ✅ |
| Página `/reconciliation` (9.12) | ❌ HTTP 403 | ✅ | ✅ |
| Resolver discrepancias (`POST /reconciliation/.../resolve`) | ❌ | ✅ | ✅ |
| Subir cartolas PDF (`POST /api/v1/cartolas/upload`, 9.5) | ❌ | ✅ | ✅ |
| PATCH categoría (`PATCH /api/v1/transactions/{id}/category`, 9.7) | ❌ | ✅ | ✅ |
| Acceso a Fava UI (basic auth separado, 9.3) | ❌ | ✅ | ✅ |
| Sync trigger manual (`POST /api/v1/sync/trigger`) | ❌ | ✅ | ✅ |
| Endpoints admin (`/api/v1/admin/*` — fx-bcch refetch, cache reload, etc.) | ❌ | ❌ | ✅ |
| Gestión de usuarios y roles | ❌ | ❌ | ✅ (manual via env var) |

> **Divergencia respecto a la story original:** la matriz autoritativa de la story 9.13 indicaba que `POST /api/v1/sync/trigger` debía ser `admin`-only. Por decisión de Ary durante implementación (2026-05-06), el sync trigger es `[contador, admin]` — el contador necesita poder iniciar syncs. El resto de endpoints `/api/v1/admin/*` permanecen admin-only.

## Email → role mapping

Vive como env var `RBAC_ROLE_MAPPING` (JSON). Cuando el email del usuario que se loguea no está mapeado, el OAuth flow devuelve **HTTP 403** y no emite JWT.

### Ejemplo:

```bash
RBAC_ROLE_MAPPING='{"ary.lipszyc@ammy.cl": "admin", "eduardo@eag.cl": "family", "abel@eag.cl": "family", "contador.externo@firma.cl": "contador"}'
```

### Compatibilidad

- Si `RBAC_ROLE_MAPPING` está vacío o ausente, el sistema cae en el env var legacy `ALLOWED_USERS` (formato `email:role,email:role`). Esto evita un breaking durante el cutover.
- El valor `"owner"` (legacy) en cualquiera de las dos env vars se normaliza a `"family"` automáticamente.

### Cómo asignar / cambiar un rol (admin)

1. Editar la env var `RBAC_ROLE_MAPPING` en Render dashboard (Settings → Environment).
2. Restartear el servicio.
3. El usuario afectado debe re-loguearse para refrescar su JWT.

> **Nota:** no hay UI de gestión de roles. La asignación es deliberadamente manual (3 usuarios + 1 admin → overkill cualquier otra cosa).

## JWT migration shim (24h window)

Los JWTs minted antes del refactor 9.13 contienen `"role": "owner"`. El middleware acepta `"owner"` como alias de `"family"` y emite un log `LEGACY_ROLE_OWNER_DETECTED`. Al expirar el TTL del JWT (configurado en `JWT_EXPIRE_HOURS`, default 8h), el shim ya no se activa porque los nuevos JWTs salen con la taxonomía nueva.

Cuando todos los JWTs legacy expiraron (ventana de migración cerrada), Ary puede borrar `_LEGACY_ROLE_ALIAS` de `backend/app/dependencies.py` y `_LEGACY_ROLE_NORMALIZE` de `backend/app/auth/service.py`.

## Defense-in-depth

Toda gate frontend tiene su contraparte backend. Los gates frontend son **UX only** — el ataque vector real es alguien modificando el JWT o llamando endpoints directos via curl. El backend siempre re-valida con `Depends(require_role([...]))` y emite log estructurado `RBAC_DENIED user_email=... user_role=... endpoint=... required_roles=...` ante cualquier 403.

## Out of scope (Story 9.13)

- OAuth provider switch (sigue Google OAuth de Story 1.3)
- Two-factor auth
- Granular permissions (más allá de rol)
- Audit log de acciones por rol
- UI de gestión de roles

## References

- Story file: [_bmad-output/implementation-artifacts/9-13-rbac-3-roles.md](../_bmad-output/implementation-artifacts/9-13-rbac-3-roles.md)
- Coord file (Bob ↔ Moishe): [_bmad-output/coordination/bob-x-moishe-epic9-migracion-beancount-2026-04-30.md](../_bmad-output/coordination/bob-x-moishe-epic9-migracion-beancount-2026-04-30.md)
- Decisión origen (Sally + Ary): [_bmad-output/coordination/sally-x-moishe-badges-pendiente-2026-05-05.md](../_bmad-output/coordination/sally-x-moishe-badges-pendiente-2026-05-05.md)
- Patrón base (Story 1.4): [_bmad-output/implementation-artifacts/1-4-role-based-access-control-rbac.md](../_bmad-output/implementation-artifacts/1-4-role-based-access-control-rbac.md)
