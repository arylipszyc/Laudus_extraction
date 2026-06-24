# Deferred Work

## Deferred from: code review of 6-3-aprobar-diferencia-anotar-beancount (2026-06-24)

- git push falla tras bean-check verde en `annotate_discrepancy` → estado parcial + doble conteo ([pipeline/importers/reconcile.py:196-211]) — `commit_reconciliation` escribe el archivo `manual/`, pasa bean-check, y recién entonces hace `git_commit_push` SIN try/except. Si el push lanza (deploy-key rechazada, red), la excepción escapa con el archivo YA escrito (rollback sólo cubre bean-check rojo), la discrepancia queda abierta (no se appendea resolución) y el caller recibe 500. Un retry pasa el guard `_resolved_ids` (no hubo resolución) y appendea una SEGUNDA copia de la tx → gasto duplicado, justo la clase de fuga silenciosa que 10.2 tapó. Pre-existing: boundary write/git de `commit_reconciliation` (mismo class deferido en 6.1). Fix durable = commit+resolution atómico, o dedup por `ref_discrepancy_id` ya presente en el archivo antes de appendear.
- read-modify-write fuera del lock → lost update concurrente ([pipeline/importers/reconcile.py:269]) — `annotate_discrepancy` hace `existing = out_file.read_text()` y concatena ANTES de llamar a `commit_reconciliation`, que es quien toma el lock. Dos `confirm-cartola-only` concurrentes sobre la misma cuenta+mes leen el mismo `existing`, cada uno computa `existing + su_entry`, serializan en el lock y el 2º write pisa al 1º → se pierde una entry (bean-check pasa igual). Baja probabilidad (un contador) pero es clase silent-loss. Fix = mover el read dentro del lock (requiere extender la API de `commit_reconciliation` a modo append).

## Deferred from: code review of 6-1-wiring-promote-reconcile (2026-06-22)

- TOCTOU: `reconcile_cartola` lee el staging fuera del lock ([pipeline/importers/reconcile.py:266]) — dos `validate_balance` concurrentes del mismo batch: el 2º pasó el `staging.exists()` de validate_balance pero el 1º ya hizo `unlink` antes del `read_text` → `FileNotFoundError` no mapeado → 500 en vez de 404. Concurrencia poco probable (un contador, un batch); fix = envolver el read en try/except → StagingNotFound.
- Lock retenido durante el `git push` ([pipeline/importers/reconcile.py:285-313]) — patrón pre-existente (idéntico a `promote`/`commit_reconciliation`). Un push lento/colgado bloquea otros importers hasta el timeout (60s) o stale (300s) del lock. El lock se libera en `finally`. Fix durable (cross-cutting): mover la red fuera del lock en los 3 sitios.
- `_rel` + `LEDGER_DISCREPANCIES` fuera del repo ([pipeline/importers/reconcile.py:276]) — si el override apunta a un path que no está bajo `root.parent`, `_rel` cae al basename y `git add <basename>` no stagea el archivo real → las discrepancias no se commitean y se pierden en el `git reset --hard` del refresh. Latente: el override no se usa en prod (default cae bajo el repo). Fix = pasar el path absoluto a `git_commit_push` o validar que esté bajo el repo.
- Cartola con `transactions=[]` + Laudus con asientos → muro de `missing-in-cartola` bloqueantes ([pipeline/importers/reconcile.py]) — una extracción vacía produce una pared de discrepancias bloqueantes en vez de rechazarse upfront. Comportamiento de diseño bajo modelo A; considerar un guard "cartola vacía → 400/aviso" si aparece en la práctica.

## Deferred from: code review of 9-8-frontend-thin-api-badge-pendiente (2026-06-17)

Nota: 9.8 es frontend parcial-por-diseño; el scope entregado (chip + página /categorizacion) está limpio y RBAC correcto. Defers de UX (pase a Sally) + el seam grande.

- AC6: la página /categorizacion usa input free-text para la cuenta de categoría en vez de un dropdown filtrado de Expenses ([frontend/src/pages/CategorizacionPage.tsx:58-67]) — AC6 pide "dropdown filtrado por root Expenses"; el texto libre es propenso a typos → bean-check 422. Cargar las cuentas Expenses (de accounts.beancount / plan-de-cuentas) y ofrecerlas como dropdown/autocomplete.
- El chip PendingCategorizationChip desaparece en error de fetch ([frontend/src/components/layout/PendingCategorizationChip.tsx:21-22]) — `data` undefined → count 0 → `return null`, indistinguible de "0 pendientes". Mismo patrón que el badge de 9.12. Bajo impacto (amber=no bloqueante) pero conviene surfacing de error/stale.
- No se muestra `confidence` ni tooltip diferenciado por `pending_review_reason` ([frontend/src/pages/CategorizacionPage.tsx:55]) — upstream: 9.7 `list_pending` no expone confidence (defer de 9.7); se muestra `current_match_source` como proxy. Ligado al defer de 9.7 (persistir el score en la meta del importer).
- SEAM grande (acknowledged, partial-by-design): badge inline ⚠ sobre los 4 dashboards Epic 3 (AC3-inline/AC4/AC5) + campo unificado `pending_review_reason` ("categorization"|"reconciliation"|"both"|null) — requiere exponer `category_status`/`match_source` en `ledger_entries_via_beancount` + cruzar con `cartola-discrepancies.jsonl` server-side + tocar las 4 páginas de dashboard + su drill-down. Integración cross-cutting de baja verificabilidad sin browser; el valor de revisión/confirmación ya está cubierto por /categorizacion + los chips del header. Si Ary lo pide, abrir story aparte.

## Deferred from: code review of 9-15-flip-balance-sheet-beancount (2026-06-17)

- colisión/ausencia de `code` en el parity ([scripts/parity_check_balance_sheet.py:48,82-84]) — opens sin meta `code` caen al bucket "" en `aggregate_balance` (conflando cuentas distintas) y `_account_roots` los saltea; dos opens con el mismo `code` → last-write-wins en la raíz. Dirección segura (tiende a clasificar como inesperado → bloquea, no false GO); las cuentas del plan tienen code único por construcción.
- `--as-of` se aplica uniforme a todas las entidades ([scripts/parity_check_balance_sheet.py:120,130]) — si dos entidades tienen distinto último snapshot, un `--as-of` único consulta Beancount AT esa fecha para ambas mientras la hoja de cada una refleja su propio cierre → diff forzado. El default per-entity (max query_date de cada hoja) lo evita; solo afecta el uso explícito de `--as-of` cross-entity.
- `get_repository().get_records` swallows errores → [] ([scripts/parity_check_balance_sheet.py:94]) — un fallo de fetch de la hoja (creds/red/tab ausente) devuelve [] en vez de raise, así el guard `except → exit 2` no dispara y el verdict puede ser engañoso. Mitigado parcialmente por el fail-safe de data-vacía agregado en review. Fix durable: validar que la hoja devolvió filas / que la entity es una de las 5 conocidas.
- 2da categoría de diffs esperados (fantasmas Sheets conocidos) no auto-clasificada ([scripts/parity_check_balance_sheet.py:63-73]) — `classify` solo marca esperados los diffs de cuentas `Liabilities` (TC reclass); un fantasma conocido en una cuenta de balance no-Liabilities saldría como "inesperado" y requeriría juicio manual. Aceptable: el bias flag-and-stop es correcto para un go/no-go; el humano investiga.

## Deferred from: code review of 9-14-migrar-bank-accounts-beancount (2026-06-17)

- create no puede setear `bank_account_last4` ([bank_accounts/service.py:80-87]) — el create escribe `bank_account_id/type/currency/[bank_name]` pero no `bank_account_last4`, que `BankAccountResolver` ([pipeline/importers/bank_account_resolver.py]) lee para el matching cartola↔cuenta. Una cuenta registrada por este endpoint queda con last4=None hasta poblarlo vía Fava (9.3). Fuera del schema 9.14, pero el matching de cartolas de esa cuenta nueva no andará hasta que se popule.
- create/update sin re-check bajo el lock (TOCTOU) ([bank_accounts/service.py:64-78,110-114]) — el 400/409 (create) y 404 (update) se evalúan sobre el snapshot `ledger.entries()` tomado al inicio del request, pero la mutación corre dentro del lock tras `_refresh_ledger_clone()`. En Render single-instance/single-worker el lock serializa; con multi-worker o cron concurrente el guard "ya registrada" podría bypassearse y duplicar `bank_account_id`. Sin constraint único que reemplace lo que enforceaba Supabase.
- orden lexicográfico de `account_number` ([bank_accounts/service.py:54]) — `out.sort(key=lambda b: b.account_number)` ordena el code como string; con codes uniformes (plan chileno 6 dígitos) lexicográfico == numérico y == el orden de la columna Supabase previa, así que no es regresión. Codes de ancho variable ordenarían mal.
- ciclos close/reopen acumulan línea en blanco ([beancount_promote.py] append_close/remove_close) — `append_close` antepone `\n`, `remove_close` solo borra la línea `close` → queda una línea en blanco huérfana. Cosmético, inocuo para bean-check.
- PATCH no puede resetear `bank_name` a null ([bank_accounts/service.py:119]) — `mutate` solo edita bank_name si `is not None`; mandar `{"bank_name": null}` se descarta. Se puede cambiar a "" pero no a null. Gap menor de producto.

## Deferred from: code review of 9-12-dashboard-reconciliacion (2026-06-17)

Nota: 9.12 es mayormente frontend con pase de UX explícito a Sally (Dev Notes). Los findings de frontend van acá; los 3 de backend se parchearon.

- AC6: el drill-down NO renderiza el historial de la discrepancia ([frontend/src/pages/ReconciliationPage.tsx] DrillDown) — `getHistory` existe en `services/reconciliation.ts` pero nunca se llama. AC6 pide mostrar el historial completo (vía endpoint AC2) en el panel. Prioridad alta del pase de UX.
- Deep-link reabre el drill-down / botón cerrar muerto ([ReconciliationPage.tsx:30-33]) — `setSelected(match)` se llama en el cuerpo del render; al resolver o cerrar un item deep-linked (`?discrepancy_id=`) se reabre solo (el backend lo sigue devolviendo por el branch de id, que ignora el filtro de resueltas). Debe ser `useEffect` keyed en deepLinkId/data con un flag de "ya auto-abrí".
- El badge de reconciliación desaparece en error de `/count` ([PendingReconciliationBadge.tsx]) — `data` undefined → `return null`, indistinguible de "0 pendientes". Una falla transitoria oculta la alerta bloqueante hasta el próximo poll (5min). Surface error/stale.
- Filtros `year_month`/`bank_account_id` no llegan desde la UI ([ReconciliationPage.tsx:26] solo manda `state`) — el backend y el service TS los soportan, pero la página no expone los dropdowns. AC5 (filtros por bank/year_month/threshold) medio-cableado.
- `fx-bcch-missing`/`fx-implausible` sin action set propio ni clasificación blocking ([reconciliation/service.py] ACTIONS_BY_STATE/BLOCKING_STATES) — tras el patch de review son escalables (no dead-end), pero falta decidir sus acciones de resolución reales y si cuentan como bloqueantes (chip rojo). Decisión de producto + semántica FX; coordinar con 9.6b.
- `bank_account_label` (shape AC1) nunca se popula — 9.6b `build_discrepancy` no lo emite y el backend no lo deriva; cosmético (la tabla muestra por cuenta, no label).
- Celda Laudus en la tabla hardcodea CLP ([ReconciliationPage.tsx:75] `fmt(d.laudus?.amount)` sin currency) — filas FX/USD muestran símbolo de moneda equivocado.
- `resolve` sin lock ante concurrencia ([reconciliation/service.py] resolve + append_resolution) — bajo riesgo en deploy single-instance Render; dos resolves simultáneos del mismo id podrían appendear dos líneas (mitigado parcialmente por el chequeo de idempotencia agregado en review).

## Deferred from: code review of 9-9-validacion-balances-bean-check (2026-06-17)

- staging opening/closing se sobrescribe antes de promote y persiste mutado en fallo ([cartolas/service.py:419-422]) — AC1 manda actualizar el staging si los balances enviados difieren del canónico, pero si promote falla (discrepancia sin override) los balances extraídos originales se pierden. Revertir-en-fallo (snapshot+restore) es nice-to-have para idempotencia de reintentos.
- 404 StagingNotFound usa shape `{detail:{...}}` mientras el resto usa `{error:{...}}` ([cartolas/router.py:162-164] vs [frontend/src/services/cartolas.ts]) — el frontend lee `data.error` y cae a "UNKNOWN: HTTP 404" en vez del mensaje "staging no existe o expiró". Path raro (staging expirado).
- tolerancia frontend `abs(discrepancia) < 0.5` vs bean-check exacto ([frontend/src/components/BalanceValidationPanel.tsx]) — para CLP (entero) 0.5 ≈ ==0, pero una cartola USD con residuo sub-peso muestra "✓ cuadra", habilita confirmar sin override y el server la rechaza 400 → dead-end. Alinear la tolerancia (estricta en el cliente, o tolerante en el server).
- campos numéricos vacíos en el panel coercen a 0 (`Number.parseFloat(x || '0')`) ([frontend/src/components/BalanceValidationPanel.tsx]) — limpiar el campo closing computa la discrepancia como si fuera 0 y puede habilitar confirmar; el backend rechaza el Decimal vacío (422) pero el frontend no valida los campos numéricos.
- `batch_id` se interpola al path del staging sin validar formato UUID ([cartolas/service.py:413]) — el sufijo `.cartola.json` + el manejo de path params de FastAPI bloquean el traversal en la práctica; agregar validación de formato es defense-in-depth.
- justificación de override con `"` o newline rompería la sintaxis beancount del pad meta ([cartola_pdf_importer.py] convert_balance_to_pad) — auto-limitado (bean-check rechaza el render → BeanCheckFailed tras el fix de review), no corrompe un archivo committeado, pero conviene escapar/validar el string antes de renderizarlo.

## Deferred from: code review of 9-7-categorizacion-smart-importer-patron-b (2026-06-17)

- AC9 `list_pending` incompleto ([transactions/service.py:46-70]) — devuelve lista plana (no agrupada por `bank_account_id → period` como pide AC9) y sin los campos `currency` ni `current_confidence`. El frontend 9.8 ya consume el shape actual; `current_confidence` requiere persistir el score en la meta del importer (hoy `category_predictor` solo propaga match_source/flag, descartó confidence en el adapter a 9.6a).
- Cache key del CategorizationService = solo `normalize(description)` ([categorization/service.py:66-72]) — ignora `amount` y `bank_account_id`, que SÍ consumen los seams smart_importer/Gemini. Inerte hoy (seams no wireados; supra/historical son description-only). Al instalar smart_importer/Gemini, la cache key debe incluir amount+bank_account_id o servirá la categoría del primer tx con esa descripción.
- normalizer: descripciones que normalizan a cadena vacía colapsan juntas ([categorization/normalizer.py:24-31]) — all-numeric ("123456789") y "REF <folio>" → "". history descarta la key vacía y resuelven a suspense igual, así que el impacto es bajo. Además `_TRAILING_DIGITS` solo quita el último grupo de dígitos (folios internos se retienen). Robustez de agrupación.
- history._load crashea ante una línea JSON válida no-objeto ([categorization/history.py:52-59]) — `json.loads("123")` u `["a"]` pasa el `except JSONDecodeError` y luego `.get` lanza AttributeError, matando la carga del índice. Defensivo: el archivo lo escribe siempre `build_record` (objeto).
- regla supra sin desempate determinista ([categorization/history.py:64-70]) — `most_common(1)` ante empate exacto (30 correcciones a catA y 30 a catB) elige por orden de inserción. Spec-compliant (30 a la misma cat satisface AC2), solo nondeterminismo cosmético del tie-break.
- `meta["filename"]` subscript duro en update_category/bulk_confirm ([transactions/service.py:145,193]) — una Transaction `!` sin meta `filename` lanzaría KeyError (500) en vez de un error limpio. Las entries cargadas del ledger siempre traen filename; bajo riesgo.

## Deferred from: code review of 9-6b-matching-cartola-laudus-discrepancias (2026-06-17)

- `je_id=""` colapsa discrepancias — `load_laudus_entries` ([matching_engine.py:88]) usa `str((e.meta or {}).get("id", ""))`; dos asientos Laudus sin meta `id` colapsan a `je_id=""` y, combinado con missing-in-cartola (`line_no` None), comparten dedup key `(batch, None, "")` → solo se escribe la primera. Robustez; depende de si el importer 9.4 puebla `id`.
- `load_laudus_entries` descarta el `_err` del parser ([matching_engine.py:78]) — un `.beancount` Laudus con error de sintaxis produce entries parciales/vacíos en silencio → falsos missing. Bajo riesgo (9.4 hace bean-check de su output antes de escribir).
- Round-trip float de montos/FX en el JSONL ([reconcile.py:31-32]) — `_num` hace `float(Decimal)`; los montos CLP son enteros pero `fx.implied`/`fx.deviation_pct` reintroducen imprecisión binaria (p.ej. 948.2000001) en datos de auditoría. El JSONL es para el dashboard 9.12 (display), no para aritmética del ledger.
- `category_account` = solo el leg más grande ([matching_engine.py:86]) — `max(others, key=abs(units))` descarta los legs menores de un asiento Laudus con gasto dividido (split); afecta la comparación de category-mismatch y la emisión de missing-in-cartola. Raro en el volumen real del proyecto.

## Deferred from: code review of 9-11-deprecation-sheets (2026-06-17)

- Dashboards balance-sheet (Activos/Pasivos) sin smoke test post Sheets→read-only — AC7 los excluye explícitamente; tras AC5 (read-only manual) los dashboards que aún leen Sheets quedan sin cobertura de regresión. Pertenece a la story del flip del balance-sheet (out-of-scope de 9.11).

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

- **Carga de template a nivel de módulo falla en import** — `with open(TEMPLATE) as _f: json.load(_f)` en `report_builder.py` corre al importar el módulo; si `template_order.json` falta o está corrupto, el import revienta y tumba todo el endpoint (no solo el request). Introducido por el cleanup del code-review previo (no por la Story 10.2). Decisión deliberada (el archivo se shippea con el código, siempre presente); si alguna vez se vuelve generado/externo, envolver en carga lazy con manejo de error. **[RESUELTO 2026-06-16]** — code-review high-effort lo movió a `_load_template()` lazy + `lru_cache`; un template ausente/corrupto ahora falla solo `GET /reportes/gastos`, no el boot.

## Deferred from: code review high-effort de fix/reportes-ui-ocultar-header-sync (2026-06-16)

Code-review de alto esfuerzo del branch grande/mixto (Epic 9 backend + Epic 10 reportes + sync 2.4). 8 de 10 findings se arreglaron in-place con tests (suite verde, 494 passed). Estos 2 quedan como STORY por requerir decisión de diseño/producto, no fix quirúrgico. Ambos viven en el path Beancount **dormante** (flags `USE_BEANCOUNT_ENGINE_*` en `false` en prod).

- **STORY — Reporte stale bajo el engine Beancount (migración).** Con `USE_BEANCOUNT_ENGINE_LEDGER=true`, el sync corre el importer Beancount (`pipeline/importers/laudus_run.run_import`) que escribe SOLO archivos `.beancount`; nunca reconstruye la pestaña `ledger_final` de Sheets. Pero `report_builder.build_report` lee su data de `get_records("ledger_final")` (Sheets). ⇒ al flipear el flag en prod, "Sincronizar ahora" en ReportesPage actualiza Beancount pero el reporte sigue leyendo `ledger_final` viejo → sirve data stale en silencio. CONFIRMADO por verificación cruzada (`sync/service.py:163` corta al path Beancount y retorna; `laudus_run` no toca Sheets). **Decisión Ary 2026-06-16: loguear como story de migración**, decidir durante el flip del flag. Opciones: (a) `report_builder` lee del ledger Beancount vía BQL cuando el flag está on; ó (b) el importer también reconstruye `ledger_final`. Bloquea: flipear `USE_BEANCOUNT_ENGINE_LEDGER` en prod sin esto = reportes congelados. Ref: finding #4 del review.

- **STORY/INVESTIGAR — Divergencia `date_from` en balance sheet entre engines.** El path BQL (`bql_queries.balance_sheet_via_beancount:62-74`) ignora `date_from` (saldo point-in-time a `date_to`, correcto para un balance) mientras el path Sheets (`dashboard/service.py:33-34`) filtra snapshots por `query_date ∈ [date_from, date_to]`. **Investigación de frontend (2026-06-16) resolvió la pregunta de alineación:** el front (`useBalanceSheet` → `dashboard.ts:17` → `BalanceSheetPage.tsx:99` `groupRecords`) envía `date_from` pero NUNCA lo usa para seleccionar snapshot; agrupa por prefijo de `account_number` y suma, sin filtrar por `is_latest` ni dedup por `query_date`. ⇒ (1) la semántica BQL (1 fila por cuenta, point-in-time) es la CORRECTA y la que el front asume — **el finding #5 se resuelve a favor de "BQL queda como está, sin cambio"**. (2) PERO la investigación destapó un riesgo MAYOR latente en el path Sheets (prod): si `balance_sheet_eag` acumula múltiples snapshots por cuenta (un `query_date` por sync mensual) y el preset 'year' manda `date_from`=inicio-de-año, el path Sheets devolvería N snapshots por cuenta y `BalanceSheetPage` los SUMA → balance multi-contado. Verificar si `balance_sheet_eag` realmente acumula snapshots históricos o solo el último; si acumula, es un bug de prod visible (totales inflados) que merece story propia. Ref: finding #5 del review.

## Deferred from: code review of 6-2-desglose-tc-usd-fx (2026-06-23)

Code-review de 3 capas (Blind Hunter + Edge Case Hunter + Acceptance Auditor) del branch `feat/6-2-desglose-tc`. Las 2 decisiones de diseño y los 2 patches se manejan en la sesión; estos 5 quedan deferidos por ser reales pero no críticos (la mayoría falla-segura = bloqueo visible, no corrupción silenciosa).

- **Regex de glosa frágil** [tc_correction.py:52]. `_GLOSA_USD_RE = USD\s*([\d.]*\d,\d{2})` exige coma + exactamente 2 decimales, y `.search` toma el PRIMER token USD. Glosas sin centavos ("USD5.000"), enteras, o con múltiples tokens USD no matchean → `parse_glosa_usd` devuelve None → estado bloqueado falsamente. Falla segura (humano ve el bloqueo). El formato del dominio hoy es consistente ("USD26.188,93"), por eso se difiere.
- **Sin desempate por fecha en match de lump/FX** [tc_correction.py:219,84]. `_resolve_usd_lump` y `derive_statement_fx` devuelven el PRIMER pago Laudus que matchea el USD por glosa, en orden de archivo/carga, sin preferir la fecha más cercana. Dos pagos con el mismo USD dentro de la ventana (±75d) atan el lump CLP equivocado → asiento (b) reclasifica un CLP errado. Baja probabilidad (requiere USD duplicado en ventana).
- **Camino CLP sin verificar el lump contra Laudus** [tc_correction.py:291]. Para CLP, asiento (b) usa `lump = abs(línea cartola)` SIN matchear contra el pago CLP real de Laudus (supuesto documentado del dev: "CLP no matchea contra Laudus"). Si el pago Laudus difiere del MONTO CANCELADO de la cartola (comisiones, pago parcial, redondeo), queda un residual falso-gasto silencioso en `Expenses:EAG:TC:<code>` que rompe la propiedad §7 de no-doble-conteo. No hay cuadre para CLP (el check de residuo es solo USD).
- **Esquemas de respuesta incompatibles en `validate_balance`** [service.py:472]. El branch TC retorna `{status, currency, fx, purchases, payments, opening_emitted, residuo, reason, git_sha, batch_id}`; el branch reconcile retorna `{status, differences, blocking, matched, git_sha, override, batch_id}`. Discriminados solo por `account_type`. Un consumidor que lea `differences`/`matched` sin chequear el tipo hace KeyError para una TC. El frontend no está en este diff → verificar que maneje la forma TC antes de exponer el endpoint.
- **EUR mal ruteado al branch USD** [tc_correction.py:259]. `is_usd = currency != _CLP` mete EUR (valor válido del enum `cartola_schema`) al camino USD, que parsea con `_GLOSA_USD_RE` (solo "USD...") → nunca matchea → siempre bloqueado con mensaje USD engañoso. Fuera de scope (la spec es CLP+USD), pero conviene un guard explícito de moneda no soportada.

- **STORY — FX por traspaso USD→CLP (vía ii, spec §12.1)** [tc_correction.py:232,266]. `derive_statement_fx` solo implementa la vía (i): pago directo `Banco→Expenses:EAG:TC:...Us` cuya glosa USD == closing. La spec §12.1 lista una segunda vía: si el contador NO pagó la TC USD directamente sino que traspasó el monto a la TC en pesos, en Laudus hay un movimiento entre la TC USD y la TC CLP, y `FX = CLP que entra a la TC CLP / USD que sale de la TC USD`. Sin esta vía, un estado saldado por traspaso queda siempre bloqueado (falla SEGURA: avisa, no corrompe). **Decisión Ary 2026-06-23: story propia.** Bloqueante para implementar: NO hay un traspaso USD→CLP real en `imports/laudus/` para confirmar la representación del dato — en la vía (i) el USD no es un monto de cuenta sino que se lee de la glosa (los asientos Laudus son CLP); para el traspaso hay que confirmar si el USD vive en la glosa o en un posting denominado en USD antes de codear, o el FX sale silenciosamente errado. Implementar cuando aparezca una cartola USD real saldada por traspaso. Mecanismo esperado = espejo de `_resolve_usd_lump`/`derive_statement_fx` pero sobre el par de cuentas TC (CLP+USD) del traspaso.
