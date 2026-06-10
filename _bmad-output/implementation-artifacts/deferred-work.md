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

## Deferred from: code review of 4-0-supabase-setup-plan-de-cuentas-bank-accounts (2026-04-15)

- `replace_records` non-atomic and uses sentinel UUID delete-all — two-call delete+insert has data-loss window between calls; not called by any Phase 2 code; only implemented for DataRepository interface compliance
- `upsert_plan_de_cuentas` count pre-fetch race condition — synced/updated counts can be stale; get_records() swallows read errors and returns [] making new_count always equal len(records); counts are informational only, upsert itself is correct
- `cartola_batches.account_name` is a free-text VARCHAR, not FK to bank_accounts — no referential integrity enforcement; architecture decision for denormalized audit field in historical records
- `bank_accounts.account_number` FK has no ON UPDATE/ON DELETE action (RESTRICT by default) — renaming an account_number in plan_de_cuentas would fail if bank_accounts references it; account_numbers are stable in ERP; low risk
- DECIMAL columns without precision/scale — financial fields use bare DECIMAL; PostgreSQL unconstrained DECIMAL is precise; precision/scale can be added in later migration when ranges are known
- SupabaseRepository client instantiated per request — intentional per story spec dev note: "do not apply @lru_cache to SupabaseRepository"

## Deferred from: code review of story-9.5h (2026-05-28)

- Año alucinado en línea de cuota escapa PERIOD_MISMATCH — la exención de cuotas (AC3, by-design + testeada) deja sin check de año a las líneas clasificadas como cuota; una cuota con año alucinado (ej. 2021 en cartola 2026) no dispara PERIOD_MISMATCH. `cartola_post_process.py:73-104`. Mitigación fuera de scope: bound absoluto de fecha que aplique aun a cuotas.
- Retry sobre BALANCE_MISMATCH determinista gasta hasta 3× costo/latencia Gemini — un PDF genuinamente descuadrado corre los 3 draws síncronos y devuelve el mismo warning del intento 1. `service.py:280`. Optimización: early-break si el `detail` del mismatch se repite idéntico entre draws.

## Deferred from: smoke iteration of story-9.5h (2026-05-29)

- **UI post-upload para revisar y corregir el período extraído** — decisión Ary 2026-05-29 al iterar 9.5h: el check PERIOD_MISMATCH se relajó a una regla de ratio ≥80% (sólo dispara ante una catástrofe — LLM leyó mal el mes/año). El coverage residual (años alucinados en pocas líneas, 1-2 tx fuera del período por hallucination, period.start/end mal-extraído por unos días) se mitiga afuera del post-process: el operador debe poder **ver el período extraído + ajustarlo** después del upload. Pertenece a la capa UI (frontend cartolas) + endpoint API (PATCH período en el canonical staged). Probablemente nueva story en epic 9 (UI/UX cartolas) o ítem de 9.6a/9.6b si el importer expone el JSON canónico para revisión.

## Deferred from: technical research — reconciliación cartolas (2026-06-10)

Origen: research técnico de extracción de PDFs ([planning-artifacts/research/technical-extraccion-pdfs-financieros-desestructurados-research-2026-06-10.md](../planning-artifacts/research/technical-extraccion-pdfs-financieros-desestructurados-research-2026-06-10.md), sección "Capas de Reconciliación"). El check determinista actual (`detect_balance_mismatch`, `cartola_post_process.py:117`) valida los **extremos** (`sum(tx) == closing − opening`, tol. 100 CLP) y el **agregado**. Tres extensiones que cubren sus puntos ciegos, en orden de valor:

- **Saldo corrido por línea** — validar `saldo[i] == saldo[i-1] + monto[i]` fila a fila cuando la cartola imprime columna de saldo por movimiento (común en TC y cuenta corriente CL). Es estrictamente más fuerte que el check actual de extremos: (a) **localiza cuál** línea está mal en vez de solo "algo no cuadra", y (b) atrapa dos errores que hoy se compensan en la suma agregada (ej. dígito transpuesto en una línea + otro inverso → la suma pasa, el corrido no). Nuevo detector en `cartola_post_process.py`; requiere que el schema canónico capture el saldo-por-fila (hoy `CartolaTransaction` no lo trae — revisar `cartola_schema.py`). Aplica solo a cartolas con esa columna; las que no la tienen siguen con el check de extremos.
- **Continuidad inter-cartola** — validar `opening_mes == closing_mes_anterior` para la misma `bank_account_id`. Atrapa una cartola **entera** faltante o duplicada, o un hueco de período — invisible al post-process intra-cartola actual (que solo ve un documento a la vez). Vive fuera de `cartola_post_process` (necesita estado cross-document: la cartola previa de la cuenta); encaja como check en el importer/staging (9.6a/9.6b) o un validador batch tipo `validate_cuadratura`.
- **Invariantes no-aritméticos para cartolas de inversión** — las cartolas de custodios/inversión no tienen opening/closing de caja del cual colgar la ecuación actual. Su invariante es otro: `qty × precio == valor_mercado` por holding y `Σ holdings == total_portfolio`. Requiere un schema canónico distinto (holdings, no movimientos) y un detector aparte. Recién relevante cuando Epic 9 (o posterior) extienda la ingesta a cartolas de inversión — hoy fuera de scope, pero el research confirmó que es target (cartolas bancarias **+ de inversión**).

**Nota de discoverability:** considerar un comentario-ancla en `detect_balance_mismatch` (`cartola_post_process.py:117`) que apunte a este ítem, siguiendo el patrón ya usado en `detect_period_mismatch` (que referencia "deferred-work.md → review/edit period post-upload").

## Deferred from: code review of reporte de gastos (2026-06-10)

Code-review de alto esfuerzo del feature "reporte de gastos". El defecto mayor (cuenta nueva = plata invisible) se escaló a `sprint-change-proposal-2026-06-10.md` (Epic 10 + refinamiento 9.11). Estos nits NO se aplicaron y quedan acá:

- **route-string-sniffing en `DashboardLayout.tsx`** — `useLocation().pathname.startsWith('/reportes')` computa el flag `minimal` y lo pasa al `Header` para ocultar filtros/barra de sync. Acopla un layout compartido a un string de ruta; renombrar/anidar `/reportes` o agregar otra ruta con el mismo trato rompe en silencio. Bajo impacto para 1-2 rutas; si crecen, mover `/reportes` a su propio layout/route config. `frontend/src/components/layout/DashboardLayout.tsx:11`.
- **3 pasadas sobre el ledger en `report_builder.py`** — `_laudus_by_code` (2 pasadas: is_income + idx), el loop cat1/cat2, y la comprehension de `tc_codes` recorren `rows` por separado, re-parseando fecha cada vez. Se podrían unificar en una sola pasada. Eficiencia; despreciable a escala family-office (~18K filas), por eso no se tocó la lógica validada diff=0. `backend/app/api/v1/reportes/report_builder.py:90`.

## Deferred from: code review of 10-2-guard-cuentas-sin-categorizar (2026-06-10)

- **Carga de template a nivel de módulo falla en import** — `with open(TEMPLATE) as _f: json.load(_f)` en `report_builder.py` corre al importar el módulo; si `template_order.json` falta o está corrupto, el import revienta y tumba todo el endpoint (no solo el request). Introducido por el cleanup del code-review previo (no por la Story 10.2). Decisión deliberada (el archivo se shippea con el código, siempre presente); si alguna vez se vuelve generado/externo, envolver en carga lazy con manejo de error.
