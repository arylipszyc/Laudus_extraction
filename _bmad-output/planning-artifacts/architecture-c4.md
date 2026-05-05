---
title: Arquitectura c4 — Beancount engine + Fava (contador) + LAUDUS frontend (family)
author: Winston (BMAD Architect)
date: 2026-04-30
audience: Ary (product owner) — vía Moishe (orchestrator) — input para Bob (SM) preparando epic de migración
status: draft-1 (pending decisiones de Ary en open questions)
supersedes_partially: _bmad-output/planning-artifacts/architecture.md (Phase 2 sección — el resto se preserva)
inputs:
  - _bmad-output/planning-artifacts/research-beancount-pivot-2026-04-30.md
  - _bmad-output/coordination/mary-x-moishe-beancount-pivot-2026-04-30.md
  - _bmad-output/coordination/winston-x-moishe-c4-arquitectura-2026-04-30.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/epics.md
  - _bmad-output/spike-beancount/{generate.py, eag.beancount}
---

# Arquitectura c4 — LAUDUS sobre motor Beancount

## 0. Marco del documento

**Qué es esto:** diseño concreto e implementable de la variante c4 que Ary aprobó el 2026-04-30 — Beancount como motor accounting + dos UIs (Fava para el contador, frontend LAUDUS actual para family) + dos importers (Laudus ERP, cartolas PDF vía beangulp + Gemini).

**Qué NO es:** plan de implementación story-by-story (eso es Bob/SM), ni reescritura del PRD (las tensiones están marcadas como `PRD-update needed`), ni el mapeo cuenta-por-cuenta de las 293 cuentas chilenas (eso es trabajo del bootstrap script en F0).

**Decisiones tomadas como input fijo (Ary + Moishe ya las cerraron — no se discuten acá):**

- Beancount OSS self-hosted como source of truth.
- Fava como UI del contador. Frontend LAUDUS actual (React/Vite + Recharts) como UI de family — sin cambios visuales.
- Backend FastAPI thin lee el ledger en memoria y expone JSON al frontend vía queries BQL.
- `pipeline/sync.py` se reformula como importer Laudus → directivas `.beancount` (preserva auth, retry, paginación).
- Story 4.1 se splitea en 4.1a (PDF → JSON canónico) + 4.1b (JSON → directivas vía beangulp).
- Story 4.0 (Supabase Phase 2): superseded por 9.1 — los registries pasan a vivir como metadata en `accounts.beancount` (modelo unificado: las 47 bank_accounts NO son registry separado, viven como metadata extra opcional sobre las cuentas del plan que aplican). El bootstrap (9.1) se hidrata vía **Option C híbrida**: Laudus API (datos contables base) + Supabase one-time read (taxonomía Categoria1/2/3 + metadata bancaria), con cross-check obligatorio. Después del bootstrap, `accounts.beancount` es source of truth; Supabase queda en standby hasta cierre de 9.11.

---

## 1. Topología del sistema (c4)

### 1.1 Componentes y sus roles

| Componente | Rol | Tecnología | Deploy |
|---|---|---|---|
| **Repo de código** | FastAPI backend + React frontend + scripts (importers, bootstrap, reporte semanal) | Python 3.12+, Node 20+, Vite, FastAPI | GitHub repo actual `LAUDUS_Backup` |
| **Ledger Beancount** | Source of truth financiero — archivos `.beancount` versionados | Beancount 3.2+, plain-text en git | Subfolder `ledger/` del mismo repo (ver §1.4 Open Q1) |
| **Backend thin (FastAPI)** | Carga ledger en memoria, expone JSON via BQL al frontend, recibe uploads PDF, orquesta importers on-demand | FastAPI + `beancount.loader` + `beanquery` | Render web service `laudus-backend` (existente, se modifica) |
| **Frontend LAUDUS** | UI family (Ary, Eduardo, Abel) — dashboards Recharts + drill-down + filtros | React/Vite + React Query + Recharts | Render static `laudus-frontend` (existente, sin cambios visuales) |
| **Fava** | UI contador — Income Statement, Balance Sheet, Trial Balance, Net Worth, BQL ad-hoc, drill-down | Fava (oficial Beancount) detrás de basic auth | Render web service `laudus-fava` (NUEVO) |
| **Importer Laudus ERP** | Pull diario API Laudus → directivas Beancount → `ledger/imports/laudus/` | Reusa `pipeline/services/{ledger,balance_sheet}_service.py` + writer Beancount nuevo | Render Cron Job `laudus-importer` (NUEVO) — alternativa: GitHub Action existente, ver Open Q3 |
| **Importer cartolas PDF** | On-demand: PDF → Gemini extract (4.1a) → JSON canónico → beangulp transform (4.1b) → directivas | beangulp + GeminiClient (existente) | Endpoints en `laudus-backend` (no servicio separado) |
| **`accounts.beancount` (registry unificado)** | Source of truth post-bootstrap de las 293 cuentas del plan + metadata bancaria (`bank_account_*`) embebida en las cuentas que son bancarias. Editable vía Fava UI o PR al repo. | Beancount directives en archivo plain-text | Versionado en `LAUDUS_Backup` repo |

### 1.2 Diagrama de flujo (texto-ASCII)

```
                                ┌──────────────────────────────────┐
                                │  Laudus ERP API (externa)        │
                                └─────────────┬────────────────────┘
                                              │ pull diario
                                              ▼
   ┌────────────────────────┐       ┌──────────────────────────────┐
   │  PDF cartolas (input)  │──────▶│  Importer Laudus (cron)      │
   │  via UI upload         │       │  → directivas Beancount       │
   └────────┬───────────────┘       └──────────┬───────────────────┘
            │ on-demand                        │ git commit + push
            ▼                                  ▼
   ┌────────────────────────┐       ┌──────────────────────────────┐
   │  Backend FastAPI thin  │──────▶│  ledger/  (Beancount files)  │
   │  - 4.1a Gemini extract │ write │  ├── main.beancount          │
   │  - 4.1b beangulp xform │       │  ├── accounts.beancount      │
   │  - bean-check pre-write│       │  ├── prices.beancount        │
   │  - BQL queries         │ read  │  ├── opening-2021.beancount  │
   │  - audit + auth + RBAC │       │  └── imports/                │
   └─┬───────────────────┬──┘       │      ├── laudus/YYYY-MM.bc   │
     │                   │          │      └── cartolas/{bank}-…   │
     │ JSON              │ shared   └──────┬───────────────────────┘
     │                   │ ledger          │ shared ledger (read-only watcher)
     ▼                   ▼                 ▼
   ┌──────────────────┐ ┌────────────────────────────┐
   │ Frontend LAUDUS  │ │  Fava (contador)           │
   │ (Recharts, family│ │  - Income/Balance Sheet    │
   │ dashboards)      │ │  - BQL workbench           │
   └──────────────────┘ │  - drill-down              │
                        │  basic auth (proxy)         │
                        └────────────────────────────┘

    ┌──────────────────────┐         ┌──────────────────────────┐
    │  Laudus API          │         │  Supabase (one-time)     │
    │  - 293 cuentas base  │         │  - taxonomía Categoria   │
    │  - hierarchy + code  │         │  - metadata bank_account │
    └────────────┬─────────┘         └─────────────┬────────────┘
                 │      ambos leídos UNA vez       │
                 │      por bootstrap (9.1) +      │
                 │      cross-check obligatorio    │
                 └────────────────┬────────────────┘
                                  ▼
                    accounts.beancount (modelo unificado:
                    cuentas plan + bank metadata embebida)
                                  ▲
                      leído por backend + importers
                      (parsea archivo, cached in-memory)
```

### 1.3 Concurrencia entre Fava + thin API + importers

**Verificación empírica (de Moishe, registrada en coord file):** Fava usa `watchfiles` para reload automático cuando un `.beancount` cambia; el thin API hace lo mismo. Cada proceso mantiene su copia en memoria; no hay locks de OS.

**Política de escritura (estricta — clave para que la concurrencia siga siendo no-problema):**

- **Cada writer escribe a SU zona, nunca a `main.beancount` directamente.** Solo el bootstrap inicial escribe `main.beancount`; después es un "índice" inmutable que solo hace `include`s.
  - Importer Laudus → `ledger/imports/laudus/YYYY-MM.beancount` (un archivo por mes)
  - Importer cartolas → `ledger/imports/cartolas/{bank}-{account_last4}-{YYYY-MM}.beancount` (un archivo por cartola)
  - Edits manuales del contador (vía Fava o vía editor sobre el repo) → `ledger/manual/YYYY-MM.beancount` (zona libre con disclaimer "todo lo escrito acá pasa por review en PR")
- **`main.beancount` solo contiene:** declaración de options + `include`s a las subzonas + price directives chicas que se mantienen consolidadas. No transacciones.
- **`accounts.beancount`** centraliza todas las directivas `open` (las 293 cuentas + bank accounts). Es el único archivo que escriben tanto el importer Laudus como el contador (este último vía PR si descubre cuenta nueva). Concurrencia controlada porque: (a) el importer escribe sólo si la cuenta no existe; (b) bean-check pre-commit evita duplicados.
- **`prices.beancount`** lo escribe sólo el price-fetcher (cron). Read-only para todos los demás.

**Validación pre-commit:** todo writer corre `bean-check ledger/main.beancount` antes de hacer `git commit + push`. Si falla: rollback (no commit), error a sync log.

**Race condition residual:** dos importers ejecutándose simultáneamente sobre el mismo persistent disk podrían pisarse al hacer `git push`. Mitigación simple: lock file `ledger/.import.lock` con timeout 5min. Importer Laudus es cron diario (1 sola ejecución), importer PDF es on-demand (improbable concurrencia con cron). Lock file resuelve el caso degenerado.

### 1.4 Estructura del repo de ledger — recomendación

**Recomendación: subfolder `ledger/` en el mismo repo `LAUDUS_Backup`.** Razón: solo developer, Render solo lee un repo, CI/CD ya configurado. Dar acceso al contador al ledger se resuelve con un acceso de read-only al repo (o sólo a Fava — más probable, ver §6).

Si en el futuro el contador necesita commit access independiente, se extrae el `ledger/` a repo propio `LAUDUS_ledger` y el backend lo clona como dependencia. Cambio mecánico, no arquitectónico. **Open Q1 abajo.**

### 1.5 Estructura de archivos `ledger/`

```
ledger/
├── main.beancount                 # entry point — solo options + includes + price refs
├── accounts.beancount             # todas las directivas `open` (293 cuentas + bank accounts)
├── opening-2021.beancount         # saldos iniciales 2021 (pad+balance — ver §2.6)
├── prices.beancount               # price directives CLP↔USD (auto-fetched)
├── imports/
│   ├── laudus/
│   │   ├── 2021-01.beancount      # JE histórico mensual desde Laudus
│   │   ├── 2021-02.beancount
│   │   └── ...
│   ├── cartolas/
│   │   ├── bci-eduardo-1234-2026-03.beancount
│   │   ├── santander-jocelyn-5678-2026-03.beancount
│   │   └── ...
│   └── _new-accounts-pending.beancount   # cuentas Laudus nuevas pendientes review
├── manual/                         # edits del contador via Fava o PR
│   └── 2026-04.beancount
├── _meta/
│   ├── categorization-history.jsonl   # log de correcciones para FR31 (30-threshold)
│   └── import-log.jsonl               # quién/cuándo/qué corrió cada importer
└── .import.lock                    # lock file (transitorio)
```

**Regla de inclusión en `main.beancount`:**

```beancount
;; main.beancount — solo includes, nunca transactions
option "title" "LAUDUS — EAG Family Office"
option "operating_currency" "CLP"

include "accounts.beancount"
include "opening-2021.beancount"
include "prices.beancount"
include "imports/laudus/*.beancount"
include "imports/cartolas/*.beancount"
include "manual/*.beancount"
```

Nota: Beancount soporta globs en `include`. Verificado en doc oficial.

---

## 2. Esquema concreto de directivas Beancount para LAUDUS

### 2.1 Naming convention de cuentas

**Patrón:** `{Root}:{Entity}:{Group}:{Slug(name)}-{account_number}`

donde:

- `{Root}` ∈ {`Assets`, `Liabilities`, `Equity`, `Income`, `Expenses`} — derivado del mapeo de `Categoria1` (ver §2.3).
- `{Entity}` ∈ {`EAG`, `Jocelyn`, `Jeannette`, `Johanna`, `Jael`} — derivado de `Categoria1` (los Categoria1 ya distinguen entidad).
- `{Group}` opcional — usado para bank accounts (`Bancos`, `Inversiones`, `TC`, `LineaCredito`) y para cuentas que tengan agrupación natural en Categoria2.
- `{Slug(name)}-{account_number}` — slug ASCII del `accountName` Laudus + sufijo `-{account_number}` para garantizar unicidad. Replica del spike (`generate.py:54-58`), ya validado.

**Ejemplos:**

```
Assets:EAG:Bancos:BancoBci-111005                       # cta corriente BCI EAG
Assets:Jocelyn:Bancos:BancoBci28980981Jocelyn-...       # cta corriente BCI Jocelyn
Liabilities:EAG:TC:VisaInfinityEduardo-2150XX           # tarjeta crédito Eduardo (NEW pattern)
Expenses:EAG:CombustibleVehiculos-413044                # gasto operativo
Income:EAG:RetirosIndumotora-310011                     # ingreso EAG
Equity:EAG:OpeningBalances                              # equity inicial
```

**Metadata estándar en cada `open`:**

```beancount
2021-01-01 open Assets:EAG:Bancos:BancoBci-111005 CLP
  code: "111005"                          ; account_number Laudus (estándar Beancount)
  laudus_account_name: "Banco BCI - 10160175"
  laudus_categoria1: "ACTIVO EAG"
  laudus_categoria2: "Banco / Caja"       ; si existe en el plan
  laudus_categoria3: ""
  bank_account_id: "uuid-…"               ; identificador estable (UUID generado durante bootstrap 9.1) — usado por importer cartolas para routing
```

### 2.2 Multi-entidad: sub-cuenta por entidad (NO archivos separados)

**Decisión:** sub-cuenta (`Assets:EAG:...` vs `Assets:Jocelyn:...`), no archivos `include` por entidad.

**Razón:**
- BQL filtering por entidad es trivial (`WHERE account ~ "^Assets:Jocelyn"`) y match con la UX existente.
- Reportes consolidados (suma del family office) se obtienen sin truco — solo no filtrar por entidad.
- Fava reconoce el primer nivel post-root como agrupación natural — el contador ve `EAG`, `Jocelyn`, … como nodos en el tree view sin configuración extra.
- Archivos separados con `include` complican la migración multi-entity de cuentas de transferencia inter-family (que existen en el ledger actual).

### 2.3 Mapeo Categoria1 → (Root, Entity)

Tabla de mapeo (replicada del spike y verificada cuenta-por-cuenta en bootstrap):

| Categoria1 (Laudus) | Beancount Root | Entity |
|---|---|---|
| `ACTIVO EAG` | `Assets` | `EAG` |
| `PASIVO` | `Liabilities` | `EAG` |
| `INGRESOS` | `Income` | `EAG` |
| `GASTOS - EGRESOS` | `Expenses` | `EAG` |
| `DISPONIBLE {NOMBRE}` (Jocelyn/Jeannette/Johanna/Jael) | `Assets` | `{NOMBRE}` |
| `EGRESOS {NOMBRE}` | `Expenses` | `{NOMBRE}` |
| `INGRESOS {NOMBRE}` | `Income` | `{NOMBRE}` |
| **(no existe en Laudus actual)** | `Equity` | `EAG` o por entidad — solo opening balances |

**Cuentas que NO caen en este mapeo (riesgo identificado por Mary, Top 3 incógnita #2):** cuentas de orden, contingencias, transferencias inter-entidad. **Acción de bootstrap:** generar reporte de cuentas con `account_type = NULL` o `Categoria1` no mapeado, presentarlo a Ary para reclasificar manualmente antes de F0. Ver §7 plan de migración.

### 2.4 Multi-currency (CLP + USD) — Q4 cerrada 2026-05-05

> **Cierre Q4 supersede la versión original de esta sección.** Coord file: `_bmad-output/coordination/q4-fx-decision-2026-05-05.md`. La verificación empírica de Laudus mostró que el ERP no preserva `currencyCode` ni `parityToMainCurrency` originales para JEs USD — el contador entra el cargo ya convertido a CLP. La Opción "FX embebido en JE de Laudus" no es viable. La Opción "mindicador.cl externo" rompe cuadratura. Decisión: Opción D — FX derivada de cartola.

**Decisiones:**

- `option "operating_currency" "CLP"` (CLP es el reporting currency primario).
- USD se declara como commodity y se usa first-class en transactions (`-450.00 USD @@ 427702.50 CLP`).
- Tarjetas de crédito en USD (Citi, Amex internacional) y cuentas USD (Julius Baer Inversiones, transferencias USD) llevan postings en USD; el frontend muestra valor original + CLP convertido.
- **Engine FX — Opción D (cartola-derived):**
  - **TC USD:** cartola PDF como source de USD original, Laudus como source de CLP del contador. Matching línea-por-línea cartola ↔ JE Laudus. `fx_implied = CLP_laudus / USD_cartola` por línea.
  - **non-TC USD:** matching 1:1 trivial — una transacción Laudus por movimiento USD real, cross-check directo cuando hay cartola/comprobante.
  - **Pre-2026:** CLP-only (Opción A para histórico). Bootstrap importa todo histórico sin USD original. Reconstrucción retroactiva solo si aparece necesidad de uso real.
- **Variable de control:** BCCh end-of-month como referencia. Threshold 5% desviación entre `fx_implied` y BCCh. Out-of-tolerance → flag (`fx_deviation_pct`), no abort.
- **Sistema de reconciliación con estados explícitos:** match perfecto, distinto valor (NO importa — bloqueante), faltante en Laudus, faltante en cartola, distinta fecha, distinta descripción, distinta categoría. Cartola manda excepto en "faltante en cartolas". Detalle de comportamiento en coord file Q4.
- **Storage discrepancias:** append-only JSONL en `ledger/_meta/cartola-discrepancies.jsonl` (single source — Story 9.12 dashboard lee directo desde acá vía backend, sin mirror SQL).
- **Storage FX por Transaction:** metadata Beancount (`fx_source`, `fx_implied`, `fx_bcch`, `fx_deviation_pct`) + `@@` notation USD-CLP. Plugin `implicit_prices` deriva price directives automáticamente.
- **`prices.beancount`** queda como placeholder vacío referenciado en `main.beancount` (consistencia formal). El precio de cada transacción USD vive en su propia annotation `@@`, no en directivas standalone.
- **Cron BCCh end-of-month** (Story 9.10 reformulada): fetcha el dólar observado del cierre del mes para alimentar `fx_bcch` en la validación. Propósito = sanity check, no fuente de FX general.
- **UF**: no aparece en data Laudus (verificado 2026-05-05). Fuera de scope hasta que aparezca uso real.

### 2.5 Bank accounts (47 cuentas — los 4 tipos)

| `bank_accounts.account_type` | Beancount Root | Group | Ejemplo |
|---|---|---|---|
| `cta_corriente` | `Assets` | `Bancos` | `Assets:EAG:Bancos:BancoBci-111005` |
| `cta_inversiones` | `Assets` | `Inversiones` | `Assets:EAG:Inversiones:JuliusBaer-XXXXX` |
| `tarjeta_credito` | `Liabilities` | `TC` | `Liabilities:EAG:TC:VisaInfinityEduardo-XXXXX` |
| `linea_credito` | `Liabilities` | `LineaCredito` | `Liabilities:EAG:LineaCredito:BancoBci-XXXXX` |

**Importante (`PRD-update needed` #1):** las tarjetas de crédito pasan a `Liabilities` — esto es semánticamente correcto y es lo que hace que Beancount valide los pagos a TC como movimientos `Asset:Bancos → Liability:TC` (pago) en lugar de `Asset:Bancos → Expense:Pago-TC` (mal modelado actual). El estado de resultado y el balance van a reflejar mejor la posición real. Ary debería confirmar con su contadora actual antes de cerrarlo.

### 2.6 Equity inicial 2021

**Decisión:** `pad` + `balance` directives, NO importar el JE 140 entry-by-entry.

**Forma:**

```beancount
;; opening-2021.beancount
2021-01-01 open Equity:EAG:OpeningBalances CLP, USD

2021-01-01 pad Assets:EAG:Bancos:BancoBci-111005 Equity:EAG:OpeningBalances
2021-01-01 balance Assets:EAG:Bancos:BancoBci-111005 X.XX CLP

;; … una pareja pad+balance por cada cuenta de balance al 2021-01-01
```

**Razón:** más limpio, el equity inicial queda explícito y trazable en una directiva por cuenta. Pierde el detalle del JE 140 — pero ese detalle no aporta operativamente (es un asiento de apertura, no movimientos reales). El JE 140 queda referenciado en metadata si Ary quiere preservarlo:

```beancount
2021-01-01 pad Assets:EAG:Bancos:BancoBci-111005 Equity:EAG:OpeningBalances
  source_je: "140"
  source_je_number: "..."
```

### 2.7 Plugins necesarios

```beancount
plugin "beancount.plugins.implicit_prices"   ; auto-prices desde transactions con cost
plugin "beancount.plugins.check_commodity"   ; validar que cada commodity esté declarada
;; NO usamos auto_accounts — queremos que abrir cuenta sea explícito
```

### 2.8 Metadata Laudus preservada (traceability)

Convención de campos en cada Transaction generada por importer Laudus:

```beancount
2021-01-26 * "Acevedo Ltda - Combustible"
  id: "63"                              ; journalentryid Laudus (idempotencia → §3.3)
  je_num: "JE-2021-0063"                ; journalentrynumber (display)
  source: "laudus-erp"                  ; quién generó esto
  Assets:EAG:Bancos:BancoBci-111005       -65690.00 CLP
  Expenses:EAG:CombustibleVehiculos-413044  65690.00 CLP
```

`id:` es la metadata estándar de Beancount para identificadores únicos. El importer hace dedup leyendo todos los `id` existentes en `imports/laudus/` antes de escribir.

---

## 3. Contrato del importer Laudus ERP

### 3.1 Reuso vs reescritura del `pipeline/sync.py` actual

| Componente actual | Estado en c4 |
|---|---|
| `pipeline/config/laudus_config.py` (auth, endpoints) | **Preservado intacto** |
| `pipeline/services/{ledger,balance_sheet}_service.py` (fetch + paginación + retry token) | **Preservado intacto** — provee data raw |
| `pipeline/utils/dates.py` | **Preservado intacto** |
| `pipeline/models.py` (BALANCE_HEADERS, LEDGER_HEADERS, map functions, enrich functions) | **Preservado parcialmente** — `map_ledger_row` se reusa para normalizar JE; los `enrich_*` que dependen de Sheets se reescriben para leer la metadata de `plan_de_cuentas` directo desde `accounts.beancount` (parseado al boot, cached in-memory) |
| `pipeline/utils/gspread_utils.py` (upsert, replace, safe_write) | **Descartado** — el writer es Beancount ahora |
| `pipeline/sync.py` orquestación | **Reescrito** (simple — pipeline equivalente con writer Beancount) |

**Componente nuevo:** `pipeline/writers/beancount_writer.py` — toma JE Laudus normalizadas y emite directivas. Resuelve cuenta destino vía registry `plan_de_cuentas` + tabla de mapeo §2.3.

### 3.2 Schedule

**Recomendación: Render Cron Job diario a las 02:00 hora Chile.** Razón: data Laudus se cierra al fin del día contable; intra-día no aporta. **Open Q3 abajo:** decidir si se preserva el botón "trigger sync" actual del frontend (Story 2.1) — recomendación: sí, mantenerlo como override on-demand (ya implementado, $0 costo preservar).

### 3.3 Idempotencia

**Mecanismo:** dedup por metadata `id:` = `journalentryid` Laudus.

**Algoritmo del importer:**

1. Pull JE de Laudus desde `from_date = max(date) en imports/laudus/*.beancount` (incremental).
2. Para cada JE: si `id:{journalentryid}` ya existe en cualquier archivo de `imports/laudus/`, skip.
3. Agrupar JE por mes (`date.strftime("%Y-%m")`).
4. Para cada mes nuevo o modificado: regenerar `imports/laudus/YYYY-MM.beancount` (write-and-replace, no append — es idempotente y simplifica).
5. Pre-commit: `bean-check`. Si falla, rollback (no commit), error a sync log.
6. Commit + push.

### 3.4 Cuentas nuevas

Si el importer Laudus encuentra `account_number` que no está en `accounts.beancount`:

1. **NO** abre la cuenta automáticamente.
2. Genera entry tentativo en `imports/laudus/_new-accounts-pending.beancount`:

   ```beancount
   ;; PENDING REVIEW — generated by importer at 2026-04-30T02:15
   ;; account_number: 415099 — accountName: "Nueva cuenta operativa"
   ;; categoria1: "GASTOS - EGRESOS" → tentative root: Expenses, entity: EAG
   ;; YOU MUST review this and either:
   ;;   (a) move the `open` to accounts.beancount, OR
   ;;   (b) re-tag the JE in Laudus to a known account, then re-run import
   2026-04-30 open Expenses:EAG:NuevaCuentaOperativa-415099 CLP
     code: "415099"
     laudus_account_name: "Nueva cuenta operativa"
     status: "PENDING_REVIEW"
   ```

3. Las JE que referencian esa cuenta van a `imports/laudus/YYYY-MM.beancount` con un `tag #pending-account` para que Fava las muestre filtradas.
4. `bean-check` pasa porque la cuenta está abierta (en `_new-accounts-pending.beancount`).
5. Email/log al admin: "N cuentas nuevas pendientes review en `_new-accounts-pending.beancount`".

Alternativa simpler que descartamos: auto-abrir bajo `Expenses:EAG:_Pending-{slug}`. La descartamos porque crea cuentas zombi que después nadie limpia. Mejor friction explícita.

### 3.5 Output + commit

- Cada run del importer modifica/crea archivos en `imports/laudus/`.
- `bean-check ledger/main.beancount` pre-commit. Si falla → rollback, no commit, log error.
- Commit con mensaje estructurado: `[importer-laudus] sync 2026-04-30: +12 JE, 0 dedup, 1 pending account`.
- Push a `main` (branch operacional, no PR — es un solo dev). En el momento que el contador se incorpore como segundo escritor, podemos cambiar a PRs automáticos (Open Q2).

### 3.6 Validación post-import

- `bean-check` valida double-entry, accounts abiertos, currency declarations.
- Adicionalmente: el importer corre BQL queries de "smoke test" — totales mensuales por cuenta no cambian más de X% respecto al mes anterior. Si cambian: warning (no bloqueante), email a Ary.

---

## 4. Contrato del importer PDF (Story 4.1 reformulada)

### 4.1 Story 4.1a — Extracción → JSON canónico

**Propósito:** desacoplar la extracción de Gemini (que es lo único que cambia por bank format) del transform a Beancount (que es estable). Permite a Bob preparar 4.1a en paralelo a que Winston cierre el resto.

**JSON canónico — shape definitivo (input para 4.1b, output del endpoint `POST /api/v1/cartolas/upload`):**

```json
{
  "schema_version": "1.0",
  "source": {
    "bank_account_id": "9f3a-…-uuid-de-bank_accounts",
    "bank_name": "BCI",
    "account_label": "T/C Eduardo BCI Visa Infinity",
    "account_type": "tarjeta_credito",
    "entity": "EAG"
  },
  "period": {
    "start": "2026-03-01",
    "end":   "2026-03-31"
  },
  "currency": "CLP",
  "balances": {
    "opening": 150000.00,
    "closing": 95000.00
  },
  "transactions": [
    {
      "line_no": 1,
      "date": "2026-03-05",
      "description": "SUPERMERCADO JUMBO",
      "amount": -45000.00,
      "currency": "CLP",
      "raw": {
        "merchant_country": "CL",
        "operation_type": "compra"
      }
    }
  ],
  "extraction": {
    "model": "gemini-2.0-flash",
    "extracted_at": "2026-04-30T15:00:00Z",
    "warnings": [
      { "code": "DUPLICATE_LINE", "line_no": 7, "detail": "same date+amount+desc as line 4" },
      { "code": "ZERO_AMOUNT",    "line_no": 12, "detail": "amount = 0" }
    ]
  }
}
```

**Reglas de campos (importantes para 4.1b y para el frontend de upload):**

- `bank_account_id`: UUID estable generado durante el bootstrap 9.1 (Option C híbrida) y embebido como metadata en la cuenta correspondiente de `accounts.beancount`. Es lo que ata la cartola a una bank account específica → determina cuenta destino Beancount + entity. **El frontend lo selecciona ANTES del upload** (dropdown de bank accounts activos, servido por backend que filtra cuentas con metadata `bank_account_id`).
- `entity`, `bank_name`, `account_label`, `account_type`: derivados del `bank_account_id` (resueltos server-side al recibir el upload leyendo metadata de `accounts.beancount` — el frontend no los manda, pero quedan en el JSON canónico para que 4.1b no tenga que volver a parsear el ledger).
- `period.start` / `period.end`: ISO 8601, derivados por Gemini del PDF + sanity-check con la fecha de la primera/última transacción.
- `currency` (top-level): currency del statement. Cada transaction puede tener `currency` propia (caso TC USD con cargos en CLP — raro pero posible).
- `transactions[].amount`: **SIGNED**. Negativo = outflow para el holder (compra/cargo); positivo = inflow (pago, devolución). La interpretación exacta depende de `account_type` y se resuelve en 4.1b (ver §4.2).
- `transactions[].line_no`: orden estable desde el PDF — usado por 4.1b para generar narration secundaria si la `description` está vacía, y por el frontend para sort estable.
- `transactions[].raw`: passthrough de campos bank-specific que el extractor encontró útil preservar (debugging y futuras reglas de categorización). NO obligatorio.
- `extraction.warnings[].code` ∈ {`DUPLICATE_LINE`, `ZERO_AMOUNT`, `LARGE_AMOUNT`, `LOW_CONFIDENCE`, `PARSE_AMBIGUOUS`} — código fijo por warning para que el frontend lo presente.

**Validación schema:** Pydantic model `CartolaCanonicalV1` en `backend/app/integrations/cartola_schema.py`. Si Gemini devuelve algo que no parsea, rechazo limpio (NFR12 / NFR19).

**`PRD-update needed` #2:** este shape difiere del shape simple del PRD original (que solo tenía `opening_balance`, `closing_balance`, `currency`, `transactions[]`). Está enriquecido con `source`, `period`, `extraction.warnings`, `line_no`. John (PM) debería actualizar la sección "Gemini Integration — PDF Extraction" del PRD/architecture original para reflejar el contrato real. No bloquea Bob — el contrato manda.

### 4.2 Story 4.1b — JSON canónico → directivas vía beangulp

**Clase beangulp — esqueleto:**

```python
# pipeline/importers/cartola_pdf_importer.py
import beangulp
from beancount.core import data, amount, position
from decimal import Decimal

class CartolaPdfImporter(beangulp.Importer):
    """beangulp Importer: ingests cartola_canonical_v1 JSON → Beancount entries."""

    def __init__(self, bank_account_resolver, category_predictor):
        self._resolver = bank_account_resolver       # bank_account_id → Beancount account name
        self._predictor = category_predictor         # CategorizationService (§4.3)

    def identify(self, file):
        # File is the canonical JSON written by 4.1a (not the original PDF).
        # 4.1a runs server-side, dumps JSON to a staging file, then 4.1b reads it.
        if not file.name.endswith(".cartola.json"):
            return False
        try:
            doc = json.loads(file.read())
            return doc.get("schema_version", "").startswith("1.")
        except Exception:
            return False

    def account(self, file):
        doc = json.loads(file.read())
        return self._resolver.resolve(doc["source"]["bank_account_id"])

    def extract(self, file, existing_entries=None):
        doc = json.loads(file.read())
        account_target = self._resolver.resolve(doc["source"]["bank_account_id"])
        currency = doc["currency"]
        entries = []

        # Optional: opening balance directive (asserts on close, not on open, for TC)
        if doc["source"]["account_type"] == "tarjeta_credito":
            # TC opening balance is an existing liability; we trust the prior batch closed correctly
            # We DO emit a `balance` assertion at period.end (post-postings) to enforce statement match
            pass

        for tx in doc["transactions"]:
            date = parse_date(tx["date"])
            narration = tx["description"] or f"line {tx['line_no']}"
            tx_amount = Decimal(str(tx["amount"]))
            tx_currency = tx.get("currency", currency)

            # Predict category (Stage 1 historical → Stage 2 Gemini → fallback Suspense)
            category_account, match_source = self._predictor.predict(
                description=narration,
                amount=tx_amount,
                bank_account_id=doc["source"]["bank_account_id"],
            )

            # Postings:
            #   For TC (Liability):  outflow tx (negative) → +amount on Liability (debt grows),  -amount on Expense
            #     Beancount sign convention: Liability +, Expense + (debit) for purchases.
            #     A purchase of 45000 → Liabilities:TC + 45000, Expenses:Cat + 45000  (sums to 0 across roots)
            #   For cta_corriente: outflow → Asset -, Expense +
            postings = self._build_postings(
                account_target=account_target,
                category_account=category_account,
                amount=tx_amount,
                currency=tx_currency,
                account_type=doc["source"]["account_type"],
            )

            meta = data.new_metadata(file.name, tx["line_no"], {
                "source": "cartola-pdf",
                "bank_account_id": doc["source"]["bank_account_id"],
                "match_source": match_source,           # 'historical' | 'gemini' | 'pending'
                "category_status": "suggested" if match_source != "pending" else "pending",
                "extraction_model": doc["extraction"]["model"],
            })
            entries.append(data.Transaction(
                meta=meta, date=date, flag="*", payee=None,
                narration=narration, tags=set(), links=set(), postings=postings,
            ))

        # Closing balance assertion (FR22 — opening + Σ tx = closing, enforced by Beancount)
        # Use a `balance` directive at period.end + 1 day to assert the new balance.
        end_plus_one = parse_date(doc["period"]["end"]) + timedelta(days=1)
        balance_amount = Decimal(str(doc["balances"]["closing"]))
        entries.append(data.Balance(
            meta=data.new_metadata(file.name, 0, {"source": "cartola-pdf-closing"}),
            date=end_plus_one, account=account_target,
            amount=amount.Amount(balance_amount, currency),
            tolerance=None, diff_amount=None,
        ))
        return entries
```

**Pasos clave:**

1. `identify()` corre sobre el JSON canónico (no el PDF) — el PDF se procesa antes en 4.1a y se descarta (NFR — no PDF storage).
2. `account()` retorna la cuenta destino derivada del registry.
3. `extract()` emite una `Transaction` por cada línea + una `Balance` directive al final (esto activa la validación `bean-check` automática del closing balance).
4. **Balance validation (FR22-25)** se delega a Beancount: la `Balance` directive falla en `bean-check` si los movimientos no cuadran. El frontend de validación (Story 4.2) recibe el resultado de `bean-check` post-import como gate. Si falla y el contador override con justificación, el importer agrega metadata `override_justification: "..."` a la directiva `Balance` y la convierte en una `pad` automática **(Beancount tiene pad-then-balance precisamente para este caso).**
5. Sin partial state: si `bean-check` falla y no hay override, el archivo `imports/cartolas/{...}.beancount` no se commitea (queda como "draft" en zona staging del backend hasta resolverse).

### 4.3 Categorización con feedback loop (FR31)

**Decisión:** mantener el threshold de 30 correcciones del PRD original como **regla complementaria** sobre `smart_importer`, no reemplazo.

**Diseño:**

- Almacén de correcciones: `ledger/_meta/categorization-history.jsonl` (append-only, una línea por corrección con timestamp + description pattern + corrected_category + original_suggestion).
- `CategorizationService.predict(description, amount, bank_account_id)`:
  1. Normalizar description (uppercase, strip merchant noise, conservar core).
  2. Stage 1 — exact-match histórico: lookup en `categorization-history.jsonl` por description normalizada. Si ≥ 30 correcciones a la misma `corrected_category` → retornar esa con `match_source="historical-30+"` (FR31 cumplido).
  3. Stage 1.5 — match parcial histórico: si entre 1 y 29 correcciones consistentes → retornar con `match_source="historical"` (igual al spec actual de Story 5.1, sin el 30-threshold rule).
  4. Stage 2 — `smart_importer` con modelo entrenado sobre history (más robusto que match exacto, opcional, configurable).
  5. Stage 3 — Gemini fallback con lista cerrada de los 85 expense accounts (igual al spec actual).
  6. Si todo falla → `Expenses:EAG:Suspense` con `category_status="pending"`, frontend lo agrupa como "Pendiente de categorizar".

**`PRD-update needed` #3:** decidir si el threshold-30 se preserva literalmente, se relaja, o se reemplaza por la curva probabilística de smart_importer. Recomendación operativa: **mantener el threshold-30 como regla "supra"** (cuando un patrón se corrigió 30 veces, deja de ser sugestión y pasa a categoría primaria; smart_importer sirve para casos < 30). Ary tiene la última palabra.

**Storage de correcciones:** `categorization-history.jsonl` en el repo de ledger es la fuente. El `CategorizationService` mantiene un cache LRU en el backend para no leer el archivo en cada predicción. Cuando el contador confirma una corrección desde el frontend (`PATCH /api/v1/transactions/{tx_id}/category`), se appendea una línea al jsonl + se actualiza el cache.

---

## 5. Backend FastAPI thin — diseño de endpoints

### 5.1 Carga del ledger en memoria

**Estrategia:** singleton lazy-loaded con file watcher.

```python
# backend/app/services/ledger_service.py
from beancount import loader
from watchfiles import awatch

class LedgerService:
    def __init__(self, main_path: str):
        self._main_path = main_path
        self._entries = None
        self._errors = None
        self._options = None
        self._loaded_at = None
        self._lock = asyncio.Lock()

    async def load(self):
        async with self._lock:
            self._entries, self._errors, self._options = loader.load_file(self._main_path)
            self._loaded_at = datetime.utcnow()

    async def get_entries(self):
        if self._entries is None:
            await self.load()
        return self._entries

    async def watch_and_reload(self):
        async for changes in awatch(os.path.dirname(self._main_path), recursive=True):
            if any(p.endswith(".beancount") for _, p in changes):
                await self.load()
```

**Costo:** ledger inicial 2021-2026 con ~50K JE: load ≈ 2-4s, RAM ≈ 100-200MB. Aceptable para 1 servicio Render. Watcher reload: incremental on demand.

### 5.2 Endpoints — mapeo desde architecture.md actual

| Endpoint actual (Phase 1+2) | c4 Endpoint | Implementación |
|---|---|---|
| `GET /api/v1/balance-sheets?entity=&date_range=` | **igual** | BQL: `BALANCES FROM ... AT date WHERE account ~ "^Assets:{Entity}|^Liabilities:{Entity}|^Equity:{Entity}"` |
| `GET /api/v1/ledger-entries?entity=&date_range=&account=` | **igual** | BQL: `SELECT date, account, narration, position WHERE ...` |
| `GET /api/v1/income-statement` | **NEW** (era render local) | BQL income statement query |
| `GET /api/v1/equity-variation` | **NEW** | BQL equity over time |
| `GET /api/v1/sync/status` | **igual** (cambia source) | lee `ledger/_meta/import-log.jsonl` (último run de cada importer) |
| `POST /api/v1/sync/trigger` | **igual** | dispara importer Laudus on-demand (subprocess o Render API) |
| `POST /api/v1/cartolas/upload` (multipart PDF + bank_account_id) | **igual contrato** | corre 4.1a sync, retorna `{ batch_id, canonical }` |
| `PATCH /api/v1/cartolas/{batch_id}/validate-balance` | **igual** | el contador valida → llama 4.1b → bean-check + commit |
| `GET /api/v1/categorization/pending` | **igual contrato** | reads del ledger: tx con metadata `category_status: pending` |
| `PATCH /api/v1/transactions/{id}/category` | **NEW semantics** | edita la directiva en el `.beancount` correspondiente: cambia el posting account + appendea a `categorization-history.jsonl` + commit |
| `POST /api/v1/transactions/bulk-confirm` | **igual** | versión bulk de lo anterior |
| `GET /api/v1/plan-de-cuentas/` | **igual contrato** | parsea metadata de `accounts.beancount` (cached in-memory al boot, invalidado por watcher cuando cambia archivo) |
| `POST /api/v1/plan-de-cuentas/sync` | **NEW semantics** | sync Laudus → detecta cuentas nuevas → emite `open` directive en `accounts.beancount` (con bean-check pre-commit). Modelo unificado, sin seed CSV intermedio. |
| `GET /api/v1/bank-accounts/` | **igual contrato** | parsea entries de `accounts.beancount` filtrando las que tienen metadata `bank_account_id` (modelo unificado — son las mismas cuentas del plan, no registry separado) |
| `POST /api/v1/bank-accounts/` | **NEW semantics** | toma una cuenta del plan existente y la enriquece con metadata bancaria (`bank_account_id` UUID generado, `bank_name`, `account_type`, `account_last4`). Si la cuenta no existe en el plan, abrir primero via `plan-de-cuentas/sync`. |

### 5.3 Auth + RBAC

**Sin cambios.** Story 1.4 (RBAC con `get_current_user()`) se preserva. Roles:

- `family` (era `owner`) — read-only sobre todos los GET; sin acceso a `/api/v1/cartolas/*`, `/sync/trigger`, `PATCH transactions`. **Nota:** Eduardo/Abel siguen viendo el frontend LAUDUS, no Fava.
- `contador` — todos los endpoints, incluido upload/validate/categorize.
- `admin` (= Ary) — todo lo anterior + puede editar registries (bank_accounts, plan_de_cuentas).

**Audit log:**
- Mutaciones de upload, validate, categorize → log estructurado append-only en `ledger/_meta/audit-log.jsonl`. Mantener separado del ledger contable mismo.
- `git log` sobre `ledger/` da auditoría completa de qué cambió en data financiera (quién mergeó qué directiva, cuándo).
- Combinado: el audit log "operacional" (acciones HTTP) + git history (cambios de data) cubren NFR13/FR5 con MÁS rigor que el approach actual.

### 5.4 Fava — endpoint y auth

**Fava NO es un endpoint del backend FastAPI.** Es un servicio Render aparte con:
- Imagen Docker custom: `python:3.12-slim` + `pip install fava beancount` + entry `fava /ledger/main.beancount --port $PORT --host 0.0.0.0`.
- Reverse proxy con basic auth: nginx sidecar, o Render's built-in protection — cualquiera funciona (Fava no tiene auth nativa, ya verificado).
- Persistent disk montado en `/ledger` con `git pull` periódico (cada 60s) para refresh.
- **Open Q5 abajo:** ¿auth basic auth con un único par contador@ammy.cl / password alcanza, o necesitamos integrarlo con Google OAuth?

---

## 6. Deployment en Render

### 6.1 Servicios

| Servicio Render | Tipo | Notas |
|---|---|---|
| `laudus-backend` | web (docker) | existente — modificar Dockerfile para añadir beancount + beanquery + watchfiles + clone ledger en startup |
| `laudus-frontend` | static | existente — sin cambios |
| `laudus-fava` | web (docker) | NUEVO — beancount + fava + nginx con basic auth |
| `laudus-importer-laudus` | cron | NUEVO — corre `python -m pipeline.importers.laudus_run` diario 02:00 |
| `laudus-prices` | cron | NUEVO — corre `python -m pipeline.importers.prices_run` diario 18:00 (post-cierre BCCh) |

### 6.2 Storage del ledger

**Recomendación: persistent disk en cada servicio (backend + fava + importer) + git como source of truth.**

Flujo:
1. En build/deploy de cada servicio: `git clone <repo> /ledger`.
2. En startup: `cd /ledger && git pull` (catch-up).
3. Backend/fava: read-only sobre el disk.
4. Importers: write + `git commit + push` (con deploy key con permiso de write).
5. Webhook GitHub → Render webhook → cada servicio hace `git pull` cuando hay nuevo push (Fava recoge cambios del importer Laudus en < 1 min).

Alternativa rechazada: shared volume entre servicios. Render no lo soporta cleanly entre servicios distintos. Git-as-coordination es más simple y resiliente.

### 6.3 Secrets

**Nuevos:**
- `BEANCOUNT_REPO_URL` — URL del repo (si extraemos a repo separado; si no, mismo `LAUDUS_Backup` con deploy key restringido a `ledger/`)
- `BEANCOUNT_DEPLOY_KEY` — SSH key con write access para los importers
- `FAVA_BASIC_AUTH_USER` / `FAVA_BASIC_AUTH_PASSWORD` (o reemplazar por OAuth proxy si Open Q5 lo decide así)
- `BCCH_API_URL` — endpoint Banco Central para dólar observado end-of-month (Story 9.10 reformulada bajo Q4)

**Preservados:** todos los actuales (`LAUDUS_USERNAME/PASSWORD`, `GOOGLE_CLIENT_ID/SECRET`, `GEMINI_API_KEY` (cuando se sume), `ALLOWED_USERS`, `JWT_SECRET`).

**Preservados durante 9.1 only (one-time read):** `SUPABASE_URL/KEY` — bajo Option C híbrida, el bootstrap los lee una vez para hidratar la taxonomía Categoria1/2/3 + metadata bancaria, con cross-check contra Laudus API. Después de 9.1 done, el path c4 no los usa más.

**Removidos en c4 post-9.1:** los registries pasan a `accounts.beancount` (modelo unificado, sin entidad separada para bank_accounts); reconciliation y FX BCCh viven en `ledger/_meta/*.jsonl`. El servicio Supabase queda en standby hasta cierre de 9.11; durante la transición el código legacy puede seguir leyéndolo, pero el path c4 no lo toca.

**Removidos eventualmente (al deprecate Sheets, F4):** `GOOGLE_SHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON`. Hasta entonces se mantienen para que el `pipeline/sync.py` legacy (Sheets) corra en paralelo durante la transición.

---

## 7. Plan de migración — fases gruesas

### 7.1 F0 — Bootstrap del ledger (1 sprint)

**Objetivo:** generar `ledger/main.beancount` válido (`bean-check` limpio) con histórico desde 2021 + saldos iniciales + 293 cuentas mapeadas.

**Pasos:**
1. Script `bootstrap/generate_accounts.py` — bajo **Option C híbrida**: lee 293 cuentas base de Laudus API (código, nombre, jerarquía contable) + lee Supabase one-time para taxonomía (Categoria1/2/3) + metadata bancaria sobre las 47 cuentas que aplican. Hace cross-check obligatorio entre ambas fuentes. Genera `accounts.beancount` con metadata embebida (`laudus_categoria1/2/3`, `bank_account_id` en las que aplica, etc.) bajo modelo unificado (sin registry separado para bank_accounts). Reporta cuentas no mapeables (Categoria1 desconocido o NULL) — Ary las reclasifica manualmente. **Esta es la incógnita #2 de Mary, se cierra acá.**
2. Script `bootstrap/generate_opening_balances.py` — pad+balance al 2021-01-01 desde balance sheet 2021-01.
3. Script `bootstrap/import_laudus_history.py` — pull + write de toda la historia 2021-now via importer Laudus modo full-backfill.
4. `bean-check` debe pasar limpio. Diff con dashboards actuales (Sheets-based) — totales por entidad/mes deben coincidir ± tolerancia 0.5%.

### 7.2 F1 — Thin API + frontend feature-flagged (1 sprint)

**Objetivo:** el frontend LAUDUS puede leer del backend Beancount-based sin notar la diferencia.

**Pasos:**
1. Implementar endpoints BQL (§5.2) con la misma forma JSON que los actuales (snake_case, ISO 8601, etc.).
2. Feature flag `USE_BEANCOUNT_ENGINE` en backend — si true, endpoints leen del ledger; si false, leen de Sheets (fallback path legacy).
3. Validación de paridad: dashboard contra dashboard, mes por mes, entity por entity. Discrepancias ≠ 0 — investigar y corregir mapeo de cuentas.
4. Cuando paridad es 100% para período de validación → switch flag a true en producción.

### 7.3 F2 — Fava deploy + workflow contador (½ sprint)

**Objetivo:** el contador puede usar Fava para revisar/editar el ledger.

**Pasos:**
1. Servicio Render `laudus-fava` deployado con basic auth.
2. Sesión 1-1 con el contador (pendiente, Ary debe asignar el rol primero) — recorrida de Fava: filtros, balances, drill-down, BQL básico.
3. Definir flujo de edición: ¿el contador edita directamente vía Fava beta editor, o vía PR sobre el repo? Recomendación inicial: **vía PR** durante el primer mes (audit trail claro), después evaluar.

### 7.4 F3 — Importer Laudus en producción (½ sprint)

**Objetivo:** dejar de sync a Sheets, dejar al importer Laudus → `.beancount` como único source.

**Pasos:**
1. Importer Laudus en cron Render. Sheets sync legacy queda corriendo en paralelo durante 1 mes (mirror).
2. Validación cada lunes: diff Sheets vs `.beancount` mes pasado → 0 discrepancia.
3. Tras 1 mes ok → desactivar Sheets sync. Sheets queda read-only como archivo histórico.

### 7.5 F4 — Importer PDF (Story 4.1a + 4.1b)

**Objetivo:** stories del epic Phase 2 originales pero con el contrato c4.

**Pasos:** dispatch normal a Bob/SM. Stories 4.1a y 4.1b paralelas (4.1a no depende de Winston, ya tiene shape definido; 4.1b sí depende de §4.2).

### 7.6 F5 — Categorización + dashboard integration (Stories 4.3, 5.x reformuladas)

**Objetivo:** completar Phase 2 sobre c4.

**Pasos:** stories 5.1 (CategorizationService), 5.2 (review UI), 5.3 (drill-down) — todas adaptadas para leer/escribir desde el ledger directamente.

### 7.7 Costo hundido Story 4.0 — superseded por 9.1 (decisión 2026-05-05)

Versión inicial (2026-04-30) preservaba los registries de Story 4.0 en Supabase. Cierre Q4 (2026-05-05) cazó la inconsistencia: bajo c4 puro Beancount + archivos es la única source of truth. Decisión Ary: eliminar Supabase del diseño completamente. Story 4.0 pasa a **100% costo hundido**.

Posteriormente (misma fecha, sesión directa Bob ↔ Ary) se cerraron 2 decisiones complementarias que afinan el modelo:

- **Option C híbrida para bootstrap (Story 9.1):** el seed inicial NO viene de un export único de la Sheet. Viene de combinar **Laudus API** (datos contables base — código, nombre, jerarquía) con **Supabase one-time read** (taxonomía Categoria1/2/3 + metadata bancaria), con cross-check obligatorio entre ambas fuentes. Razón: ejercitamos el conector Laudus de paso (smoke test del que va a usar 9.4 semanal) y aprovechamos la taxonomía existente en Supabase sin re-trabajo manual.
- **Modelo unificado de cuentas:** las 47 bank_accounts no son un registry separado de las 293 cuentas del plan — viven como **metadata extra opcional** (`bank_account_id`, `bank_name`, `account_type`, `account_last4`) en las cuentas del plan que son bancarias. Razón: la relación es 1:1 (cada cuenta del plan que es bancaria tiene una y solo una cuenta física), no N:1. Tener dos registries era artefacto del modelo Supabase relacional, no necesidad de modelado bajo Beancount.

| Story 4.0 deliverable | Estado en c4 (post 2026-05-05) |
|---|---|
| Migration `001_phase2_initial_schema.sql` (4 tablas) | **Descartada** — las 4 tablas se desprecian. Servicio Supabase queda en standby hasta cierre 9.11. Durante 9.1, Supabase se lee one-time como input al cross-check. |
| `SupabaseRepository` | **Descartada** — el código se borra cuando 9.1+9.5 reemplazan los call sites. |
| `plan_de_cuentas` (registry de 293) | **Migra a `accounts.beancount`** — vía Option C híbrida durante 9.1. |
| `bank_accounts` (registry separado de 47) | **Disuelto en modelo unificado** — la metadata bancaria pasa a vivir embebida en las cuentas del plan que son bancarias. Sin entidad separada. |
| `bank_accounts` CRUD endpoints | **Cambia semántica** — pasa de "CRUD sobre tabla bank_accounts" a "enriquecer/leer metadata bancaria sobre cuentas del plan en `accounts.beancount`". Interfaz HTTP estable. |
| Módulos `backend/app/api/v1/{plan_de_cuentas, bank_accounts}/` | **Sobreviven con implementación nueva** — parsing Beancount + cache in-memory + emit `open` directives + enriquecimiento de metadata. |

**Veredicto honesto post-2026-05-05:** Story 4.0 fue **0% productiva** bajo c4 final. ~1-2 días de trabajo descartado, producto del arrastre silencioso del costo hundido al cuestionar el diseño. Lección documentada en MEMORY: cuando se preserva infraestructura por costo hundido sin cuestionar si el nuevo diseño la necesita, se acumula deuda silenciosa.

### 7.8 Riesgo de drift durante transición

**Período crítico:** F1 + F3 (~3 sprints) donde Sheets y `.beancount` co-existen.

**Mitigaciones:**
1. **Single writer por dataset.** Durante F1: importer Laudus escribe a Sheets (legacy) Y a `.beancount` (nuevo). Mismo source (Laudus API), dos sinks → consistencia automática.
2. **Validación diff semanal.** Cron que compara totales mes-pasado: Sheets vs Beancount BQL. Email si discrepancia > 0.5%.
3. **Feature flag granular.** Cada dashboard view tiene su flag `USE_BEANCOUNT_FOR_{view}` — switch incremental, no big-bang.
4. **Ary no edita Sheets manualmente durante F1-F3.** Edits van directo al `.beancount`. (PRD-update needed: documentar este constraint operativo durante migración).

---

## 8. Open questions / decisiones pendientes antes de implementar

Listadas honestas. Cada una indica quién la cierra y por qué afecta.

1. **Repo del ledger — subfolder vs separado.**
   - Recomendación Winston: subfolder `ledger/` en `LAUDUS_Backup` (simpler para dev solo).
   - Cierra: Ary. Si planea dar al contador commit access independiente del backend code, entonces extraer a `LAUDUS_ledger`. Si Fava + PR vía GitHub web le alcanza, subfolder está bien.
   - Costo de cambiar después: bajo (mover archivos + actualizar deploy keys).

2. **Workflow del contador para edits — Fava editor directo vs PRs.**
   - Recomendación Winston: **PRs durante primer mes**, después evaluar. Fava beta editor escribe sin git context y puede romper bean-check sin warning visible.
   - Cierra: Ary, idealmente tras conversar con el contador asignado.
   - Bloquea: F2 (deploy de Fava). Default seguro = empezar sin permitir edits y habilitarlos cuando el flujo esté claro.

3. **Schedule importer Laudus — solo cron, solo on-demand, o ambos.**
   - Recomendación Winston: ambos. Cron diario 02:00 + botón frontend (preserva Story 2.1 ya implementada).
   - Cierra: Ary. Default = ambos.

4. **Fuente de tipo de cambio CLP/USD (y UF si aplica).**
   - Recomendación Winston: mindicador.cl (público, sin auth, BCCh dólar observado). UF sólo si la operación familiar lo usa — ¿hay accounts en UF en el plan de 293?
   - Cierra: Ary (verificar plan + decidir source).

5. **Auth de Fava — basic auth simple o Google OAuth proxy.**
   - Recomendación Winston: basic auth para empezar (simple). Si family va a usar Fava (no creo, va con LAUDUS frontend), entonces oauth-proxy.
   - Cierra: Ary. Define quiénes acceden a Fava. Si solo el contador → basic auth alcanza.

6. **Threshold-30 de FR31 — preservar literal o reemplazar por probabilístico.**
   - Recomendación Winston: preservar literal como regla "supra" sobre smart_importer/historical match.
   - Cierra: Ary (eventualmente con la contadora). `PRD-update needed`.

7. **Tarjetas de crédito como `Liabilities` (semánticamente correcto) vs preservar el modelo actual.**
   - Recomendación Winston: `Liabilities` (corrige bug semántico).
   - Cierra: Ary tras consulta con la contadora actual. Cambia el shape del estado de resultado y del balance — debe quedar OK con quien firma estados financieros. `PRD-update needed`.

8. **Reporte HTML semanal a Eduardo — script BQL Python en backend o lambda externa.**
   - Recomendación Winston: script Python en backend (`scripts/weekly_report.py`) corriendo como Render cron viernes 17:00. Reusa el LedgerService + plantilla HTML actual.
   - Cierra: Ary. Default = script en backend.

9. **Cuentas que no mapean a Categoria1 — qué hacer con cuentas de orden, contingencias, transferencias inter-entidad.**
   - Recomendación Winston: bootstrap script en F0 emite reporte de cuentas problemáticas; Ary las reclasifica manualmente uno-por-uno. Para transferencias inter-entidad, abrir cuentas paralelas `Equity:Transfer-{src}-{dst}` o usar tags `#transfer-{src}-{dst}`.
   - Cierra: Ary durante F0. Es la incógnita #2 de Mary.

10. **Deprecation timeline de Sheets como source of truth.**
    - Recomendación Winston: F4 (post-importer Laudus en prod + 1 mes de paridad). Sheets queda como archivo read-only histórico para siempre (cuesta $0).
    - Cierra: Ary tras revisar paridad de F1.

---

## 9. Cosas que NO están resueltas en este documento (out-of-scope explícito)

- Aplicación cuenta-por-cuenta del mapeo §2.3 a las 293 cuentas (es trabajo del bootstrap F0 — patrón está, ejecución no).
- Redacción de stories del epic de migración (es trabajo de Bob/SM, después de que Ary cierre las open Qs).
- Cambios al PRD (3 `PRD-update needed` marcados — pasan a John/PM en sesión separada).
- Diseño UI específico de la pantalla de upload + categorization review (es trabajo de Sally/UX si Ary lo dispara — acá solo definí el contrato data; la UX está cubierta por Story 4.1/5.2 originales).
- Performance budgets por endpoint (NFR1 dice < 3s; el ledger en memoria + BQL típicas devuelven en < 200ms para queries normales; verificación empírica viene en F1).

---

## 10. Resumen para Bob (SM) — qué está listo para preparar stories

**Bloqueado:** las 10 Open Questions §8. Ary cierra → Bob despacha.

**Desbloqueado y listo (para que Bob arme el epic):**
- Story 4.1a: shape JSON canónico §4.1 cerrado. Bob puede preparar la story sin esperar nada más de Winston.
- Story F0-bootstrap: §7.1 y §2 dan todo el patrón. Faltan las decisiones Ary, después es script puro.
- Story F1-thin-api: §5 da el endpoint mapping completo.
- Story F4-importer-laudus: §3 da el contrato completo.
- Stories de Fava + cron prices: §6 da deployment, §2.4 da el contrato de prices.

Todo lo demás (4.1b, 4.2, 4.3, 5.x, F2, F3, F5) tiene un dispatcher específico en este documento. Bob los puede preparar cuando Ary haya cerrado las Qs que aplican a cada uno.
