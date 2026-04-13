# Deferred Work

## Deferred from: code review of 1-4-role-based-access-control-rbac (2026-04-10)

- `decode_jwt` algorithm confusion (alg:none attack) — pre-existing in `backend/app/auth/service.py` from Story 1.3; should add explicit algorithm pinning on decode
- `lru_cache` on `get_repository` — stale Google Sheets connection not recoverable without process restart; pre-existing from Story 1.1
- `_parse_allowed_users` called on every login with no caching — pre-existing from Story 1.3; low risk for 2-3 users
- `useAuth` staleTime 5 min — role revocation not reflected for up to 5 min; pre-existing from Story 1.3; acceptable for MVP
- AC2 write endpoints not yet wired — `require_role` exists but not applied to any production endpoint; deferred until Epic 2 introduces financial write endpoints
- `require_role([])` empty list silently denies all authenticated users — acceptable edge case for MVP with no dynamic role config
- `allowed_roles` list parameter captured by reference in closure — should be `tuple` or `frozenset`; low risk
- `UserRole` enum defined separately in backend (`str`) and frontend (`'owner' | 'contador'`) — no single source of truth; acceptable for MVP, consider codegen in Phase 2
- `get_current_user` does not strip whitespace from cookie value — proxy-injected trailing space would return 401 with no diagnostic; low risk for internal deployment

## Deferred from: code review of 2-1-sync-api-endpoints-pipeline-integration (2026-04-11)

- Global mutable `_current_job` state not process-safe in multi-worker deployments — MVP design decision; Cloud Run uses 1 uvicorn worker; revisit when scaling
- `from sync import sync_api` deferred import is path-dependent — requires repo root in sys.path; by design per story spec
- Daemon thread killed on Cloud Run container restart → `_current_job` stuck at "running" — MVP acceptable; consider persisting job state to Sheets in Story 2.2
- `balance_sheet` and `ledger` share same `last_sync` value (both use `date_range.dateTo`) — by design; Story 2.2 introduces per-type sync tracking
- `last_sync` timestamp reflects data date range (`dateTo`), not sync execution time — by story spec design; semantic distinction deferred
- Silent exception swallowing in `_read_last_sync_date` — consistent with project-wide best-effort read pattern
- No rate limiting or cooldown on `POST /trigger` — MVP scope; 2-3 internal users
- Background thread not stored/joinable — correct for daemon fire-and-forget pattern in this context

## Deferred from: code review of 1-5-audit-log-backup-workflow-y-cloud-run-deployment (2026-04-10)

- Exception message leaked in 500 handler (`str(exc)` in JSON response) — pre-existing from Story 1.1; should be replaced with generic message in production hardening pass
- `JWT_SECRET` reused as both JWT signing key and session cookie signing key — pre-existing from Story 1.3; low risk for MVP with single secret
- Hardcoded fallback `"dev-secret-change-in-production"` in SessionMiddleware — pre-existing from Story 1.3; deployment checklist must ensure JWT_SECRET is set
- Secrets written to `.env` file on CI runner disk — pattern copied from pre-existing `sync-weekly.yml`; consider passing secrets as env vars directly to run step in security hardening pass
- Service account JSON written with single-quoted shell expansion — pattern copied from `sync-weekly.yml`; could break if JSON contains single quotes; consider `printf '%s'` or dedicated action
- Cron UTC offset comment ignores Chile DST (UTC-3 summer, UTC-4 winter) — LOW; cron itself is correct per spec; comment is an approximation
- Audit log is best-effort/not transactional (stdout → Cloud Logging) — architectural decision per spec; no retry or failure alert if Cloud Logging agent drops a message
- `GOOGLE_APPLICATION_CREDENTIALS` path hardcoded to `config/serviceAccountKey.json` in workflows — pattern from pre-existing `sync-weekly.yml`; acceptable for current CI setup

## Deferred from: code review of 2-2-incremental-sync-deduplicacion-y-confiabilidad (2026-04-11)

- `stats` delta (after - before) no distingue "added" vs "updated" — by design; upsert semantics; delta = rows netas nuevas, correcto para "added"
- `repo` capturado en thread closure podría tener auth expirada en producción — pre-existing `lru_cache` issue en `get_repository` deferred desde Story 1.1
- Sin test de race condition entre snapshot de conteo y sync externo concurrente — MVP scope, 1 worker uvicorn, 2-3 usuarios internos

## Deferred from: code review of 3-1-dashboard-api-endpoints (2026-04-11)

- `@lru_cache` on `get_repository` — stale Sheets credentials after expiry cause silent empty responses on all dashboard endpoints; pre-existing from Story 1.1; process restart required to recover
- No entity-level RBAC — any authenticated user (owner or contador) can read any entity's financial data; spec explicitly permits "all authenticated users can read" — deferred by design for MVP; revisit if multi-entity access control is required

## Deferred: Story 3.5 — Detalle de Tarjetas de Crédito (2026-04-13)

Story 3.5 deferred to Phase 2. Rationale:

- Credit card accountants record card payments as expense entries (not liability) in Laudus — this is a source-data classification error
- Correct fix requires two reclassifications: (1) Laudus payment entries → Caja vs. Deuda por Pagar (liability), (2) credit card statement movements → Deuda por Pagar vs. specific expense accounts
- Credit card statement data (cartolas) is not available in MVP — will be available in Phase 2 bank statement ingestion (FR20-FR27)
- Without cartola data, implementing the reclassification would create an incomplete fix and risk introducing new errors
- A frontend-only display reclassification was considered and rejected: while technically viable (Google Sheets is a read-only ERP mirror, not an authoritative ledger), the fix should be done correctly with both data sources present

**Phase 2 implementation note:** When cartolas become available, store them in a separate table. The income/expenses view should then: (a) exclude credit card payment entries from Laudus expense totals, (b) pull expense breakdown from cartola transactions mapped to their proper expense accounts.

## Deferred from: code review of 2-3-backfill-historico-ui-de-estado-de-sync (2026-04-11)

- Multi-worker job state not process-safe — pre-existing from Story 2.1; Cloud Run uses 1 uvicorn worker; revisit when scaling
- `repo` capturado en thread closure / lru_cache stale — pre-existing from Story 1.1
- Ledger backfill usa llamada única sin paginación — por diseño, misma semántica que sync_api(); deferred si API Laudus implementa paginación
- `str(exc)` expuesto en `/sync/status` error field — pre-existing from Story 2.1; reemplazar con mensaje genérico en hardening pass
- Global `_token` en laudus_service.py mutado sin lock — pre-existing; no race posible hoy (1 job a la vez); latente si arquitectura cambia
- `query_date` puede llegar como int serial de Sheets en `_read_balance_sheet_last_sync` — pre-existing from Story 2.2; low risk si siempre se escribe con USER_ENTERED
- `useSyncStatus` 60s poll sin backoff ni page visibility check — MVP scope; 2-3 usuarios internos; revisar en Epic 3
