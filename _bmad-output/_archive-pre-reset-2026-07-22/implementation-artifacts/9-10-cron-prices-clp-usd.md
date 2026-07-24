---
story: 9.10
title: Cron BCCh end-of-month — sanity check FX derivada
status: done
epic: 9
depends_on: []
blocks: [9.6b]
---

# Story 9.10 — Cron BCCh end-of-month (sanity check FX)

## User Story

As the system,
I want a monthly cron job that, on the last day of each month at 23:59 (Chile time), fetches the Banco Central de Chile (BCCh) "dólar observado" rate for that end-of-month and appends it to `ledger/_meta/fx-bcch-eom.jsonl`,
So that Story 9.6b can validate the implied FX derived from cartola↔Laudus matching against an authoritative reference (threshold 5%), and out-of-tolerance lines get flagged for manual review.

## Context

**Status anterior:** `blocked-by-q4`. **Q4 cerrada el 2026-05-05** con Opción D (FX cartola-derivada). Esta story queda destrabada y reformulada.

### Cambio de propósito (vs versión original)

**Antes:** cron diario que fetcha FX y popula `prices.beancount` con price directives generales.

**Ahora:**
- Cron **mensual** end-of-month (no diario).
- Storage en **JSONL** (`ledger/_meta/fx-bcch-eom.jsonl`), no en `prices.beancount`.
- Propósito = **sanity check** de la FX derivada en 9.6b (matching cartola↔Laudus). NO es la fuente primaria de FX para el ledger.
- Las price directives reales del ledger derivan de las Transactions vía plugin `implicit_prices` (ver 9.6b AC8 + AC2). `prices.beancount` queda como **placeholder vacío** en el repo, referenciado en `main.beancount` por consistencia formal.

### Sin Supabase

Storage = **single source JSONL** en `ledger/_meta/fx-bcch-eom.jsonl`. **NO hay tabla Supabase** (decisión 2026-05-05 eliminar Supabase del diseño c4). Story 9.6b consulta el JSONL directo cuando calcula `fx_deviation_pct`.

## Acceptance Criteria

**AC1 — Cron schedule mensual end-of-month**

**Given** un Render Cron Job llamado `laudus-prices` está configurado
**When** revisás su schedule
**Then** corre con expression `59 23 28-31 * *` con `TZ=America/Santiago`
**And** el script en código verifica que es **el último día del mes** antes de proceder (Render no tiene cron expression nativa para "último día de mes" — se delega al script)
**And** si NO es último día del mes (ej.: 28 de feb que no es último) → exit 0 sin fetch ni write

---

**AC2 — Fetch BCCh dólar observado**

**Given** el script invoca el endpoint del Banco Central
**When** se hace el GET
**Then** consulta el endpoint oficial BCCh API (`https://api.bcentral.cl/dataservices/api/series/...` — el dev confirma la URL exacta de la serie "dólar observado" al implementar)
**And** parsea el response JSON para extraer el rate del día (último día del mes en curso)
**And** maneja errores: timeout, 5xx, schema inesperado → log error + retry hasta 3 veces con backoff
**And** si todos los retries fallan → log fatal + exit ≠ 0 (se reintenta automáticamente al siguiente run, o manual via on-demand endpoint)

---

**AC3 — Append a `fx-bcch-eom.jsonl`**

**Given** el fetch fue exitoso con rate `X CLP/USD`
**When** se escribe
**Then** se appendea una línea a `ledger/_meta/fx-bcch-eom.jsonl` con shape:
```json
{
  "schema_version": "1.0",
  "year_month": "2026-04",
  "rate_clp_per_usd": 950.45,
  "fetched_at": "2026-04-30T23:59:30-03:00",
  "source": "bcch-dolar-observado",
  "bcch_date": "2026-04-30"
}
```
**And** el archivo es append-only — nunca se sobrescriben líneas
**And** dedup por `year_month` (si ya existe entrada para ese mes, log warning + skip — no duplicar)

---

**AC4 — `prices.beancount` permanece vacío**

**Given** el cron corre mensualmente
**When** completa
**Then** `prices.beancount` en el repo NO se modifica — sigue siendo placeholder vacío referenciado en `main.beancount`
**And** las price directives reales del ledger derivan automáticamente de las Transactions con `@@` notation via plugin `implicit_prices` (responsabilidad de 9.6b, no de esta story)

---

**AC5 — Endpoint on-demand (opcional)**

**Given** Ary necesita correr el fetch manualmente (ej.: re-fetch tras un error o agregar mes pasado faltante)
**When** invoca `POST /api/v1/admin/fx-bcch/refetch?year_month=2026-04` (RBAC admin only)
**Then** el backend dispara el mismo script de fetch para ese mes específico
**And** la response es síncrona: `{"status": "fetched", "rate": 950.45, "year_month": "2026-04"}` o `{"status": "skipped", "reason": "already-exists"}`

---

**AC6 — Smoke test post-deploy**

**Given** el cron está deployado en Render
**When** se dispara una corrida manual desde Render dashboard (último día del mes simulado)
**Then** completa en < 30 segundos
**And** la línea aparece en `ledger/_meta/fx-bcch-eom.jsonl` correctamente formada
**And** `git log` sobre `ledger/_meta/` muestra el commit con mensaje `[fx-bcch] eom 2026-04: 950.45 CLP/USD`

---

**AC7 — Backfill de meses pasados (opcional v1)**

**Given** el ledger arranca con histórico desde 2021 pero el cron solo aplica desde el momento de deploy
**When** Story 9.6b necesita validar transactions USD pre-2026 o de meses pre-deploy
**Then** **no aplica** — pre-2026 va CLP-only por decisión Q4 (no se calcula FX implícita), y meses post-deploy se llenan progresivamente
**And** si Ary quiere backfillar manualmente meses 2026 anteriores al deploy: usar el endpoint on-demand (AC5) iterando por mes
**And** documentar que entradas faltantes en JSONL → 9.6b emite flag `fx-bcch-missing` (AC3 de 9.6b)

---

## Tasks / Subtasks

> **Cambio de alcance 2026-05-05 (Ary):** Story entregada bajo **Opción D — endpoint on-demand only**. La automatización vía Render Cron Job + git push queda **deferred** para una fase posterior. Razón: complejidad infra alta (deploy SSH key, git config en container, persistent disk) para algo que se ejecuta 12 veces al año. Ary dispara manualmente hasta entonces. AC1 + AC6 quedan parciales (código listo, deploy de cron pendiente). Tasks 1, 4 absorbidas / deferred.
>
> **Cambio de fuente 2026-05-05 (Ary):** Se reemplaza BCCh API oficial (requiere registro) por **mindicador.cl** (proxy público gratis sin auth). El rate publicado es idéntico al de BCCh — diferencia 0% bajo el threshold de sanity de 5%. Endpoint: `GET https://mindicador.cl/api/dolar/DD-MM-YYYY`.

- [x] Task 1: ~~Script `pipeline/importers/prices_run.py` con check "es último día del mes"~~ → **deferred** (no aplica bajo Opción D — el endpoint dispara manual con `year_month` explícito).

- [x] Task 2: Cliente mindicador.cl (`pipeline/integrations/mindicador_client.py`)
  - [x] Función `fetch_dolar_observado(target_date) -> Optional[float]`
  - [x] Endpoint mindicador.cl con format `DD-MM-YYYY`
  - [x] Retries 3x backoff exponencial (5s, 10s, 15s)
  - [x] Tests con mock — 8 casos (publicación, no-publicación, schema raro, retry, fail tras retries, valor no numérico, format URL)

- [x] Task 3: JSONL writer + dedup (AC3) — en `pipeline/importers/fx_bcch_eom.py`
  - [x] Función `_append_jsonl(jsonl_path, record)` (auto-mkdir parents)
  - [x] Pre-check `_find_existing(jsonl_path, year_month)` con tolerancia a líneas malformadas
  - [x] Append-only nunca reescribe
  - [x] **Sin git commit + push** (deferred junto con cron — el JSONL queda en el filesystem del backend; commit manual hasta cron Render)

- [x] Task 4: ~~Render Cron Job config~~ → **deferred** (Fase 2 — Ary configura cuando provisione SSH deploy key).

- [x] Task 5: Endpoint on-demand `POST /api/v1/admin/fx-bcch/refetch` (AC5)
  - [x] `backend/app/api/v1/admin/router.py` (NEW package)
  - [x] RBAC: `require_role(["owner"])` — interpretación de "admin" del story file (sistema actual tiene `owner`+`contador`, sin rol `admin` separado)
  - [x] Param query `year_month=YYYY-MM`
  - [x] Validaciones future/current → 400; `NoPublicationFoundError` → 502

- [x] Task 6: Tests
  - [x] Unit cliente mindicador (8 casos)
  - [x] Unit orquestador: validaciones (8 casos), iterador hacia atrás (4 casos), persistencia + dedup (5 casos)
  - [x] Integration endpoint: RBAC (3) + behavior (5) — 8 casos
  - [x] **Smoke real contra mindicador.cl ejecutado** (no en suite CI por costo de red): `2026-04-30 → 901.76 CLP/USD`, dedup verificado.
  - **Total: 34 tests, todos verde.**

- [x] Task 7: Documentación
  - [x] `pipeline/importers/README.md` con sección fx-bcch-eom (uso vía endpoint + CLI, garantías, shape JSONL, divergencia mindicador, deferred cron)
  - [x] Runbook: cómo backfillar mes faltante via endpoint on-demand (un mes a la vez)

---

## Dev Notes

### Input autoritativo

`q4-fx-decision-2026-05-05.md` — decisión Q4 + reformulación 9.10. `architecture-c4.md §2.4` — versión actualizada Q4. `bob-x-moishe-epic9-2026-04-30.md` — ítem #6 (9.10 reformula) + ítem #9 (sin Supabase).

### Por qué BCCh y no mindicador.cl

Originalmente Winston había recomendado mindicador.cl (público, sin auth). Q4 cierre (2026-05-05) cambió a **BCCh API oficial** porque:
- BCCh es la fuente oficial del "dólar observado" (lo que el SII usa para reportes).
- Mindicador.cl es un proxy — agregable, pero menos autoritativo.
- BCCh API requiere registro pero es gratuito.

**Verificar al implementar:** la URL exacta de la serie "dólar observado" puede haber cambiado. El dev confirma con la documentación BCCh actual.

### Volumen y costo

- 12 entradas por año (1 por mes) — costo storage trivial.
- Cron Render mensual — costo ínfimo ($0-1/mes).
- Persistent disk: el mismo del importer Laudus (Story 9.4) puede compartirse — o disk dedicado pequeño, ambos OK.

### Por qué JSONL y no SQL

Decisión 2026-05-05: eliminar Supabase del diseño c4. Storage = archivos en repo + git como SoT. JSONL es ideal para data temporal serie con append-only semantics.

Performance para 9.6b lookup: leer todo el JSONL al boot del backend, indexar por `year_month` en memoria. Para ~5 años × 12 meses = 60 entradas → trivial.

### Project structure

```
pipeline/
  importers/
    prices_run.py                          # NEW (script principal del cron)
    README.md                              # MODIFY (sección fx-bcch)
  integrations/
    bcch_client.py                         # NEW (cliente API)
backend/app/api/v1/admin/router.py          # MODIFY (endpoint refetch)
ledger/_meta/
  fx-bcch-eom.jsonl                        # NEW (creado por bootstrap 9.1, populated por esta story)
ledger/prices.beancount                    # placeholder vacío (Story 9.1 lo crea, esta story NO lo toca)
```

### Out of scope

- UF (Unidad de Fomento) — no aparece en data Laudus (verificado 2026-05-05). Si aparece uso real más adelante, abrir story aparte.
- Cron diario — Q4 cerrada con cron mensual. Si se necesitara FX intra-mes para algún caso, se gestiona vía endpoint on-demand.
- `prices.beancount` populado — derivación automática vía plugin `implicit_prices` (responsabilidad de 9.6b).

### References

- [Source: q4-fx-decision-2026-05-05.md — decisión Opción D + reformulación 9.10]
- [Source: architecture-c4.md §2.4 — versión Q4]
- [Source: bob-x-moishe-epic9-2026-04-30.md — ítem #6 + ítem #9]
- [Source: 9-6b-matching-cartola-laudus-discrepancias.md — consumidor del JSONL]
- [External: https://si3.bcentral.cl/Indicadoressiete/secure/Indicadoresdiarios.aspx — referencia visual; el dev usa la API oficial]
