# pipeline/importers — Imports y jobs hacia el ledger

Scripts y módulos que pueblan / actualizan el ledger Beancount.

---

## cartola_pdf_importer — Cartola JSON → directivas Beancount (Story 9.6a)

`beangulp.Importer` que consume el JSON canónico de Story 9.5
(`ledger/imports/cartolas/_staging/{batch_id}.cartola.json`) y produce un
`.beancount` por cartola, con una `Balance` directive al cierre que `bean-check`
valida (FR22-25). Parser básico del path "match perfecto" — **sin** reconciliación
cross-source (eso es 9.6b).

Piezas:
- [`cartola_pdf_importer.py`](cartola_pdf_importer.py) — `CartolaPdfImporter`, `_build_postings`, `convert_balance_to_pad`, `promote`.
- [`bank_account_resolver.py`](bank_account_resolver.py) — `bank_account_id` → cuenta Beancount, leyendo `accounts.beancount` (NO Supabase).
- [`category_predictor.py`](category_predictor.py) — hook de categorización; `NoopCategoryPredictor` (v1) manda todo a `Expenses:EAG:Suspense`/`pending`. Story 9.7 lo reemplaza.

### Convención de signo (verificada contra cartolas reales)

La cartola presenta saldos/montos en convención **natural de extracto**: para una TC,
`opening`/`closing` y cargos son POSITIVOS (deuda como número positivo), con
`opening + Σ amounts = closing`. Beancount usa liabilities crédito-normal (deuda
negativa). Por eso para cuentas **Liabilities** se niega el signo (`target = -amount`,
`balance = -closing`); para **Assets** se usa tal cual. Ambos postings suman 0.

> ⚠️ El storyfile AC4 describe los postings con signos que no balancean en beancount
> (sumarían 2×amount). La implementación sigue el gate real (AC5 = `bean-check` pasa),
> verificado con la aritmética de un sample real. Ver Completion Notes de 9.6a.

### Flujo

```
9.5 (Gemini)  →  _staging/{batch_id}.cartola.json
                      │  CartolaPdfImporter.extract()
                      ▼
              N Transaction + 1 Balance (cierre)
                      │  promote()  ── bean-check gate (Story 9.9) ──┐
                      ▼                                              │ OK
   imports/cartolas/{bank}-{last4}-{YYYY-MM}.beancount  + git commit (guarded)
```

`promote()` reusa el lock + `bean_check` + `git_commit_push` (guarded por
`IMPORTER_GIT_ENABLED`) de [`laudus_run.py`](laudus_run.py).

### Pendientes / dependencias

- **Categorización real** = Story 9.7 (acá solo el hook noop).
- **Override de Balance** (`convert_balance_to_pad`) lo dispara Story 9.9 desde el endpoint `/validate-balance`.
- **Endpoint de upload + trigger de promote** = wiring en `cartolas/router.py` (Story 9.5/9.9), fuera de 9.6a.

---

## laudus_run — Importer Laudus → Beancount (Story 9.4)

Orquestador [`laudus_run.py`](laudus_run.py). Toma JEs de la API Laudus y escribe
directivas en `ledger/imports/laudus/YYYY-MM.beancount`, valida con bean-check y
(en producción) commitea+pushea al repo del ledger.

### Modos

| Modo | Qué hace | from_date |
|------|----------|-----------|
| `incremental` (default) | JEs desde el día siguiente a la última fecha escrita hasta hoy; mergea por `id` (no pierde data) | auto |
| `backfill` | Regenera todos los meses desde `from_date` (mismo modo que el bootstrap 9.1) | requerido |

### Correr smoke local

```bash
# Incremental (git deshabilitado por default → solo escribe archivos, seguro)
PYTHONUTF8=1 python -m pipeline.importers.laudus_run

# Backfill desde 2021-01
IMPORTER_MODE=backfill IMPORTER_FROM_DATE=2021-01-01 PYTHONUTF8=1 python -m pipeline.importers.laudus_run
```

Requiere `LAUDUS_USERNAME`, `LAUDUS_PASSWORD`, `LAUDUS_COMPANYVATID` en `.env`.

### Variables de entorno

| Var | Default | Para qué |
|-----|---------|----------|
| `LEDGER_DIR` | `<repo>/ledger` | Raíz del ledger (en Render: persistent disk) |
| `IMPORTER_MODE` | `incremental` | Modo cuando se corre como `__main__` |
| `IMPORTER_FROM_DATE` | — | `from_date` para backfill |
| `IMPORTER_GIT_ENABLED` | `false` | `true` activa `git add/commit/push` |

### On-demand desde el backend

`POST /api/v1/sync/trigger` (Story 2.1, RBAC contador/admin) dispara este importer
**cuando `USE_BEANCOUNT_ENGINE_LEDGER=true`**; con el flag off sigue el path Sheets.
El resultado es visible vía `GET /api/v1/sync/status` (lee `_meta/import-log.jsonl`,
gated por `USE_BEANCOUNT_ENGINE_SYNC_STATUS` — Story 9.2 AC7).

### ⚠️ HANDOFF a Ary — requiere tus manos (Task 8 + AC10)

El código está listo; lo siguiente necesita el dashboard de Render + secrets:

1. **Render Cron Job `laudus-importer-laudus`** (AC3): type Cron Job; schedule
   `59 23 * * 6` con `TZ=America/Santiago` (sábados 23:59 Chile); command
   `python -m pipeline.importers.laudus_run`; persistent disk con git clone del ledger
   (setear `LEDGER_DIR` al mount); env vars `LAUDUS_*`, `BEANCOUNT_REPO_URL`,
   `BEANCOUNT_DEPLOY_KEY`, `IMPORTER_GIT_ENABLED=true`.
2. **Deploy key git** (AC9): SSH key con **write** access al repo del ledger →
   `BEANCOUNT_DEPLOY_KEY`. Sin esto el importer escribe pero no persiste al repo.
3. **Smoke post-deploy** (AC10): correr manual desde Render → completa < 10 min →
   `_meta/import-log.jsonl` con `success: true` → `git log` muestra el commit
   `[importer-laudus] sync …`.
4. **Activar flag** `USE_BEANCOUNT_ENGINE_LEDGER=true` cuando Beancount sea la fuente
   activa. Hasta entonces convive con Sheets (§7.8: `pipeline/sync.py` corre en paralelo).

**Limitación conocida:** al promover una cuenta de `_new-accounts-pending.beancount` a
`accounts.beancount`, las JEs viejas siguen apuntando a la cuenta de cuarentena hasta
que corras un **backfill**. El incremental solo re-resuelve JEs nuevas.

---

## fx-bcch-eom — Dólar observado de cierre de mes (Story 9.10)

Refetch idempotente del dólar observado del cierre de un mes. Lo escribe a
`ledger/_meta/fx-bcch-eom.jsonl` para que Story 9.6b lo use como variable de
control (sanity check) contra la FX implícita derivada del matching
cartola↔Laudus, threshold 5%.

### Fuente de datos

[mindicador.cl](https://mindicador.cl) — proxy público y gratuito de las
series del Banco Central de Chile. Endpoint:
`GET https://mindicador.cl/api/dolar/DD-MM-YYYY`. Sin auth, sin registro.

> **Divergencia del story file:** el story file 9.10 menciona
> `api.bcentral.cl` (BCCh oficial). Decisión Ary 2026-05-05: usar
> mindicador.cl para evitar registro/credenciales. mindicador toma el dato
> directamente de BCCh, así que el rate es idéntico bajo el threshold de
> sanity check (5%).

### Cómo correrlo

#### Vía endpoint admin (recomendado)

```bash
curl -X POST "https://<backend>/api/v1/admin/fx-bcch/refetch?year_month=2026-04" \
  -H "Cookie: access_token=<owner-jwt>"
```

Response success:
```json
{
  "status": "fetched",
  "year_month": "2026-04",
  "bcch_date": "2026-04-30",
  "rate_clp_per_usd": 901.76,
  "source": "mindicador-dolar-observado"
}
```

Response idempotente (segunda llamada para el mismo mes):
```json
{
  "status": "skipped",
  "year_month": "2026-04",
  "bcch_date": "2026-04-30",
  "rate_clp_per_usd": 901.76,
  "source": "mindicador-dolar-observado"
}
```

RBAC: solo rol `owner` (Ary). `contador` recibe 403.

#### Vía CLI (debugging local)

```bash
python -m pipeline.importers.fx_bcch_eom 2026-04
```

Imprime el JSON resultado por stdout. Exit 0 (success/skip), 2 (validation),
3 (sin publicación).

### Garantías

| Caso | Comportamiento |
|---|---|
| `year_month` futuro | HTTP 400 — "es futuro respecto a hoy" |
| `year_month` = mes en curso | HTTP 400 — "es el mes en curso, esperá al cierre" |
| Mes ya cargado | HTTP 200 con `status: skipped` y los datos existentes |
| Último día del mes cae fin de semana / feriado | Itera hacia atrás hasta 7 días buscando publicación |
| 7 días sin publicación | HTTP 502 — reportar a mantenimiento (no debería pasar) |
| Mindicador caído / timeout | 3 retries con backoff exponencial (5s, 10s, 15s) → HTTP 502 si todos fallan |

### Shape del JSONL

`ledger/_meta/fx-bcch-eom.jsonl` (append-only, commiteado al repo):

```json
{"schema_version": "1.0", "year_month": "2026-04", "rate_clp_per_usd": 901.76, "fetched_at": "2026-05-05T18:54:42+00:00", "source": "mindicador-dolar-observado", "bcch_date": "2026-04-30"}
```

- `year_month` — clave de dedup. Una entrada por mes calendario.
- `bcch_date` — fecha real con publicación (puede no coincidir con último día calendario).
- `fetched_at` — timestamp UTC del momento del fetch (auditoría).

### Cron (deferred)

Story 9.10 entrega **endpoint on-demand only**. La automatización vía Render
Cron Job queda para una fase posterior — un cron mensual thin (curl al
endpoint) sin git push automatizado ni deploy keys. Ary dispara manualmente
hasta entonces.

### Out of scope

- Backfill batch (un endpoint por mes — iterá manualmente si necesitás varios).
- UF (no aparece en data Laudus, ver Dev Notes story 9.10).
- Cron diario (Q4 cerrada con cron mensual).
- Populación de `prices.beancount` — derivación automática vía plugin
  `implicit_prices` de Beancount es responsabilidad de Story 9.6b.

---

## Matching engine + reconciliación cartola ↔ Laudus (Story 9.6b)

El parser básico (9.6a) emite el path "match perfecto". 9.6b agrega la **reconciliación
cross-source**: cruza cada línea de cartola contra el asiento Laudus del mismo período/cuenta,
clasifica en 7 estados, deriva la FX implícita de las líneas USD, valida contra BCCh y emite
un log append-only de discrepancias.

### Flujo

```
cartola JSON ─┐
              ├─► MatchingEngine.match() ─► [MatchResult]  (1 por línea cartola + Laudus sobrantes)
imports/laudus┘                                  │
                                                 ▼
                          ┌── USD + era FX (≥2026) ──► fx_calculator.calculate_fx() ──► FXResult
                          │                                                                │
                                                 ▼                                         ▼
                          reconcile.process_match_result(MatchResult, FXResult) ──► ProcessDecision
                                                 │                                         │
                          (emit? flag? discrepancias)                                      │
                                                 ▼                                         ▼
                          reconcile.reconcile_and_build() ──► (entries beancount, discrepancias)
                                                 │                                         │
                                                 ▼                                         ▼
                          imports/cartolas/{slug}.beancount            _meta/cartola-discrepancies.jsonl
```

### Los 7 estados (`matching_engine.py`)

| Estado | Emite Transaction | Flag | Discrepancia | Sistema de verdad |
|---|---|---|---|---|
| `perfect` | sí | `*` | no | ambos |
| `value-mismatch` | **NO** (bloqueante) | — | sí | resolución manual (9.12) |
| `missing-in-laudus` | sí (desde cartola) | `!` | sí | cartola |
| `missing-in-cartola` | sí (desde Laudus, CLP-only) | `!` | sí | Laudus |
| `date-mismatch` | sí (fecha de cartola manda) | `!` | sí | cartola |
| `description-mismatch` | sí (desc de cartola manda) | `!` | sí | cartola |
| `category-mismatch` | sí (`suggested_category` en meta) | `!` | sí | cartola sugiere |

Tolerancias: fecha ±3 días, similitud de descripción ≥ 0.85, monto exacto para CLP. USD no se
compara por monto (moneda distinta al CLP de Laudus) → matchea por fecha+desc y la FX se deriva.

### FX implícita (USD, era ≥ 2026-01-01)

`fx_implied = CLP_laudus / USD_cartola`. Se valida contra el dólar observado de cierre de mes
(`_meta/fx-bcch-eom.jsonl`, Story 9.10) con threshold 5%. Estados FX: `fx-out-of-tolerance`
(> 5% → flag `!` + discrepancia), `fx-bcch-missing` (9.10 no corrió ese mes), `fx-implausible`
(USD=0 o rate > 2000). El posting USD lleva price per-unit CLP → `implicit_prices` deriva la
price directive. **Pre-2026 es CLP-only** (sin lógica FX, AC9).

### Discrepancias (`_meta/cartola-discrepancies.jsonl`)

Append-only, fuente única (sin mirror Supabase). Dedup por `(batch_id, cartola_line_no,
laudus_je_id)` → re-correr el matching no duplica. La **resolución** (Story 9.12) se appendea
como línea nueva referenciando el `discrepancy_id` original (audit trail completo). Al resolver,
`reconcile.commit_reconciliation()` re-genera el archivo de cartola (write-and-replace) con
bean-check + git commit `[reconciliation] resolve {id}: {action}` bajo el mismo `.import.lock`.

### Resolver una discrepancia manualmente (runbook)

1. Leer `_meta/cartola-discrepancies.jsonl` (Story 9.12 dashboard lo sirve; o `grep` directo).
2. Decidir la acción (aceptar cartola / aceptar Laudus / ajuste manual).
3. 9.12 invoca `commit_reconciliation(file, nuevo_contenido, discrepancy_id, action, ledger_root)`
   → re-genera el `.beancount`, bean-check, commit + push.
4. La resolución queda registrada con `append_resolution(discrepancy_id, {...})`.
