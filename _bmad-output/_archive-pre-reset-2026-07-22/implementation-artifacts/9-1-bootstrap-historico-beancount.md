---
story: 9.1
title: Bootstrap histórico Beancount (F0)
status: done
epic: 9
depends_on: []
blocks: [9.2, 9.4, 9.11]
---

# Story 9.1 — Bootstrap histórico Beancount (F0)

## User Story

As a developer (Ary),
I want a script-driven bootstrap that generates a complete `ledger/` directory from Laudus history (2021 → now) with opening balances, account mapping (read directly from Laudus + one-time read of Supabase taxonomy), and `bean-check` clean,
So that we have a single Beancount source of truth ready for thin API + Fava + importers, we know exactly which accounts didn't map automatically, and the bootstrap doubles as a smoke test of the Laudus connector that Story 9.4 will use.

## Context

F0 del plan de migración (`architecture-c4.md` §7.1). Genera `ledger/main.beancount` válido (`bean-check` limpio) con:

- Las 293 cuentas mapeadas a árbol Beancount con **modelo unificado** (`accounts.beancount`): cada cuenta es una `open` directive; las cuentas bancarias llevan metadata adicional `bank_account_*` en la misma directiva. **NO hay registry separado de `bank_accounts`** — son subset del plan con metadata extra.
- Saldos iniciales 2021-01-01 vía `pad`+`balance` (`opening-2021.beancount`).
- Histórico 2021-now de Laudus normalizado a directivas Beancount (`imports/laudus/YYYY-MM.beancount`).

**Sin bloqueadores de ejecución.** Q4 (FX) cerrada el 2026-05-05 con Opción D (FX cartola-derivada). Pre-2026 va CLP-only por construcción → cuadratura del bootstrap es trivial (CLP=CLP, diff exacta = 0). USD original recién aparece en 9.6 (cartolas con matching).

### Decisión de fuentes — Option C híbrida (2026-05-05)

| Dato | Fuente |
|---|---|
| 293 cuentas: código + nombre + jerarquía contable Laudus | **Laudus API** (endpoint plan de cuentas — valida el conector que usará 9.4) |
| Categoria1/2/3 + metadata bancaria (`bank_account_type`, `bank_account_last4`, `bank_account_currency`, `bank_name`) | **Supabase one-time read** (taxonomía Ary cargada por Story 4.0; será apagado en 9.11) |
| Cross-check | Cada cuenta de Laudus debe tener match en Supabase. Mismatch → fail con reporte explícito |
| Histórico 2021-now JE | Laudus API (`accounting/ledger`) |

**Modelo unificado de cuentas:** una sola fuente, no hay tabla `bank_accounts` separada. Las 47 cuentas bancarias son cuentas del plan con campos extra opcionales. Razón: Story 4.0 introdujo `bank_accounts` como entidad relacional (artefacto del modelo Supabase). Bajo Beancount + git como SoT, la duplicación es innecesaria — relación 1:1 plan↔bank_account confirmada por Ary (escenario "varias cuentas comparten institución bancaria, cada una con su `last4` propio").

**Story 4.0 → `superseded-by-9-1`.** Los registries Supabase mueren cuando 9.1 emite `accounts.beancount`. El proyecto Supabase queda en standby (sin queries, costo ~0) hasta que 9.11 lo apague junto con Sheets.

## Acceptance Criteria

**AC1 — Estructura de archivos generada**

**Given** los scripts de bootstrap se ejecutan en orden
**When** el bootstrap completa
**Then** existe el directorio `ledger/` con los archivos:
```
ledger/main.beancount
ledger/accounts.beancount
ledger/opening-2021.beancount
ledger/prices.beancount             # vacío inicial — Story 9.10 popula vía cron BCCh
ledger/imports/laudus/YYYY-MM.beancount  (un archivo por mes desde 2021-01)
ledger/imports/laudus/_new-accounts-pending.beancount  # vacío si todas mapean
ledger/_meta/import-log.jsonl       # log de runs del importer Laudus
ledger/_meta/categorization-history.jsonl  # vacío inicial
ledger/_meta/cartola-discrepancies.jsonl   # vacío inicial — populated por 9.6
ledger/_meta/fx-bcch-eom.jsonl             # vacío inicial — populated por 9.10
```
**And** `main.beancount` contiene únicamente: `option` directives + `include`s a las subzonas (NO transactions). Template literal de §1.5 del artifact.

---

**AC2 — Mapeo de las 293 cuentas a árbol Beancount (modelo unificado)**

**Given** `bootstrap/generate_accounts.py` lee:
  - **Laudus API** (`plan_de_cuentas` endpoint) → datos base: `account_number`, `account_name`, `account_type` Laudus, jerarquía contable
  - **Supabase one-time read** → taxonomía Ary: `categoria1/2/3` + metadata bancaria (`bank_account_type`, `bank_account_last4`, `bank_account_currency`, `bank_name`)
  - Tabla §2.3 del artifact (mapeo Categoria1 → Beancount Root + Entity)

**When** el script corre
**Then** `accounts.beancount` contiene una directiva `open` por cada cuenta del plan (293 total — no hay registry separado de bank_accounts) con:
  - `account` siguiendo patrón `{Root}:{Entity}:{Group}:{Slug(name)}-{account_number}` (§2.1)
  - `commodities` apropiados (`CLP` para CLP-only, `CLP, USD` si la cuenta puede tener USD)
  - Metadata estándar siempre presente: `code:`, `laudus_account_name:`, `laudus_categoria1:`, `laudus_categoria2:`, `laudus_categoria3:`
  - Metadata bancaria sólo en cuentas bancarias (47 de las 293): `bank_name:`, `bank_account_type:`, `bank_account_last4:`, `bank_account_currency:`. Las cuentas no-banco no tienen estos campos (Beancount no se queja).
**And** las tarjetas de crédito mapean a `Liabilities:{Entity}:TC:...` (Q7 — corrige bug semántico actual)
**And** `bean-check` pasa limpio sobre solo `accounts.beancount` cargado en un main mínimo

---

**AC3 — Cross-check Laudus ↔ Supabase obligatorio**

**Given** el script `generate_accounts.py` corre con ambas fuentes (Laudus + Supabase one-time)
**When** se hace el cross-check por `account_number`
**Then** cada cuenta presente en Laudus debe tener match en Supabase
**And** si hay mismatches:
  - Cuentas en Laudus ausentes en Supabase → emiten línea en `bootstrap/report-mismatch-accounts.csv` (col: `account_number, account_name, source: "laudus-only"`)
  - Cuentas en Supabase ausentes en Laudus → emiten línea con `source: "supabase-only"` (probable: cuentas obsoletas o renombradas)
  - Diferencias de `account_name` entre fuentes → `source: "name-divergence"` con ambos valores
**And** el script falla con exit-code ≠ 0 si hay mismatches que no estén explícitamente whitelisteados — Ary los resuelve manualmente (Q9)
**And** la decisión "qué fuente gana en caso de diferencia de nombre" está documentada: **Laudus manda en datos contables base** (account_number, account_name, jerarquía); **Supabase manda en taxonomía Ary** (Categoria1/2/3, metadata bancaria)

---

**AC4 — Reporte de cuentas no-mapeables**

**Given** alguna cuenta cruzada tiene `Categoria1` desconocido o NULL en Supabase
**When** el script `generate_accounts.py` la encuentra
**Then** la cuenta NO se incluye en `accounts.beancount`
**And** se appendea a un reporte `bootstrap/report-unmapped-accounts.csv` con columnas: `account_number, account_name, cat1, cat2, cat3, reason, suggested_root, suggested_entity`
**And** el script imprime al final: "N cuentas no-mapeables encontradas — revisá `report-unmapped-accounts.csv` antes de ejecutar generate_opening_balances.py"
**And** el script falla con exit-code ≠ 0 si N > 0 — esto fuerza a Ary a reclasificarlas manualmente (Q9)

---

**AC5 — Opening balances 2021 vía pad+balance**

**Given** `bootstrap/generate_opening_balances.py` lee el balance sheet de Laudus al 2021-01-01
**When** el script corre
**Then** `opening-2021.beancount` contiene:
  - Una directiva `open Equity:EAG:OpeningBalances CLP, USD` con fecha 2021-01-01
  - Por cada cuenta de balance (Asset/Liability) con saldo ≠ 0 al 2021-01-01: una pareja `pad ... Equity:EAG:OpeningBalances` + `balance ...` (formato §2.6)
  - Metadata `source_je: "140"` + `source_je_number: "..."` en cada `pad` para preservar referencia al JE 140 de Laudus
**And** `bean-check` pasa limpio sobre `accounts.beancount + opening-2021.beancount`
**And** todos los saldos iniciales se emiten en CLP (pre-2026 CLP-only por decisión Q4)

---

**AC6 — Histórico 2021-now importado mes-por-mes**

**Given** `bootstrap/import_laudus_history.py` orquesta el importer Laudus en modo `full-backfill`
**When** el script corre desde `from_date=2021-01-02` (después del opening) hasta hoy
**Then** se genera un archivo `imports/laudus/YYYY-MM.beancount` por cada mes con JEs (write-and-replace, idempotente)
**And** cada `Transaction` tiene metadata: `id:` (= `journalentryid`), `je_num:` (= `journalentrynumber`), `source: "laudus-erp"`
**And** dedup por `id:` funciona en re-runs (correr el script dos veces produce el mismo output)
**And** el filtro defensivo descarta líneas con `journalEntryId = 0` (saldos sintéticos `"Saldo anterior"` que la API Laudus inyecta cuando se consulta un rango que arranca después del JE 140 — caveat documentado en `_bmad-output/spike-beancount/probe-empty-currency.py` del 2026-05-05)

---

**AC7 — Cuentas nuevas no-en-plan detectadas**

**Given** durante el import histórico aparece un `account_number` que no existe en `accounts.beancount`
**When** el importer Laudus la encuentra
**Then** NO abre la cuenta automáticamente
**And** appendea entry tentativo a `imports/laudus/_new-accounts-pending.beancount` (formato §3.4 del artifact)
**And** las JEs que la referencian mantienen `tag #pending-account` para poder filtrarlas en Fava

---

**AC8 — bean-check limpio sobre el ledger completo**

**Given** los pasos AC2-AC7 completaron sin errores
**When** se corre `bean-check ledger/main.beancount`
**Then** el comando retorna exit-code 0 (sin errores ni warnings bloqueantes)
**And** `bean-query ledger/main.beancount "SELECT count(*) FROM #" > 0` retorna conteos coherentes (todas las JE 2021-now contadas)

---

**AC9 — Cuadratura CLP↔CLP vs ledger Laudus**

**Given** Q4 cerrada con Opción D — pre-2026 CLP-only, FX en USD aparece recién en 9.6 (cartola matching)
**When** se corre el bootstrap completo y se compara el balance sheet generado por BQL `BALANCES FROM ... AT 2026-04-30` contra el balance sheet de Laudus al mismo corte (suma por cuenta + entidad + total)
**Then** la diferencia es **exactamente 0 CLP** por construcción (Laudus entrega todo en CLP, Beancount lo importa en CLP, sin lógica FX intermedia)
**And** si hay diferencia: el script imprime tabla detallada (cuenta, monto Laudus, monto Beancount, diff) y falla con exit-code ≠ 0
**And** la verificación es CLP↔CLP simple, sin lógica multi-currency

---

**AC10 — Costo bajo de re-bootstrap**

**Given** el script de bootstrap completo
**When** se corre desde cero (rm -rf ledger/ && bootstrap)
**Then** completa en < 30 minutos para 5 años de history (~50K JEs estimadas)
**And** el output es bit-idéntico run a run (deterministic — mismo input Laudus → mismo output, asumiendo Supabase y Laudus estables)

---

## Tasks / Subtasks

> **Status final 2026-05-05:** Tasks 1, 2, 3, 5, 6, 7 done. Task 4 deferred
> (depende de Story 9.4). Los AC que requieren history importada (AC6, AC7,
> AC10, parte de AC9) quedan parciales hasta que 9.4 cierre. Detalles abajo.

- [x] Task 1: Esqueleto del directorio `ledger/`
  - [x] `bootstrap/init_ledger_dir.py` idempotente — crea estructura + reescribe `main.beancount` siempre.
  - [x] Template de `main.beancount`: §1.5 + plugins (`implicit_prices`, `check_commodity`) + commodity directives `CLP` y `USD` (exigidas por `check_commodity`) + custom Fava extension de Story 9.0 (preservada).
  - [x] Placeholders `_init.beancount` en `imports/laudus/` y `imports/cartolas/` para que los globs `include` no se quejen cuando los directorios están vacíos.
  - [x] `bean-check` pasa exit 0 sobre el ledger inicial vacío + accounts placeholder.
  - [x] 5 unit tests verde.

- [x] Task 2: `bootstrap/generate_accounts.py` — Option C híbrido (AC2 + AC3 + AC4)
  - [x] **Lectura Laudus API:** endpoint descubierto al implementar — `POST /accounting/accounts/list` con body `{"fields": [...]}`. Campos disponibles: `accountId`, `accountNumber`, `name`, `notes`. **Laudus NO expone `account_type` ni jerarquía explícita** — la jerarquía se deriva del prefijo numérico del `accountNumber`.
  - [x] **Lectura Supabase one-time:** `SupabaseRepository.list_plan_de_cuentas()` + `list_bank_accounts()`.
  - [x] **Padding:** Laudus usa longitud variable (`"1"`, `"11"`, `"111"`, `"111005"`); Supabase usa todo padded a 6. Normalización Laudus → padded 6 (función `normalize_account_number`) habilita cross-check trivial.
  - [x] **Cross-check por `account_number` normalizado:** 293/293 matchean tras normalización. Estructurales (laudus-only/supabase-only) bloquean exit ≠ 0; name-divergences NO bloquean (policy "Laudus manda" — Ary 2026-05-05). Reportes separados.
  - [x] **Mapeo:** tabla §2.3 + §2.5 + Q7 (TC y línea de crédito → Liabilities). Slug ASCII Camel del `accountName`. Lógica en `bootstrap/account_mapping.py` + 21 unit tests verde.
  - [x] **Modelo unificado:** una directiva `open` por **cuenta hoja**. Decisión arquitectónica confirmada por Ary 2026-05-05: solo se abren las **255 hojas** (las 38 nodos raíz/categoría se reportan a `report-hierarchy-nodes.csv` para auditoría pero no se renderizan — Beancount infiere los grupos al ver tree view).
  - [x] **Cat1 unmapped:** detectó 9 cuentas con `Categoria1` no mapeable (`RESULTADOS` × 6 + `CUENTAS POR COBRAR {NOMBRE}` × 3). Ary confirmó mapeos 2026-05-05; entradas agregadas a la tabla `MAP_CATEGORIA1_TO_ROOT_ENTITY`. Re-corrida: 0 unmapped.
  - [x] Validado con `bean-check` exit 0 sobre `accounts.beancount` real + main F0.

- [x] Task 3: `bootstrap/generate_opening_balances.py` (AC5)
  - [x] `GET /accounting/balanceSheet/totals?dateTo=2021-01-01` — 12 cuentas con saldo al 2021-01-01.
  - [x] Saldo signed = `debitBalance - creditBalance` (positivo Assets, negativo Liabilities — convención Beancount nativa).
  - [x] Equity open + 12 pares pad+balance con metadata `source_je: "140"`.
  - [x] **Divergencia técnica obligatoria del story file:** las cuentas se abren al **2020-12-31**, los `pad` también al **2020-12-31**, los `balance` al **2021-01-01**. Beancount exige `pad-date < balance-date` para emparejar; la fecha original `2021-01-01` para pad+balance produce "Unused Pad entry" + balance fail. Documentado en `bootstrap/README.md`.
  - [x] Pre-2026 todo CLP (Q4 cerrada).
  - [x] 13 unit tests verde + smoke real exit 0.

- [ ] Task 4: Reescritura de `pipeline/sync.py` orquestación (AC6 + AC7) — **DEFERRED hasta Story 9.4**
  - El bootstrap real del histórico 2021-now requiere el importer Laudus de Story 9.4. No se implementó wrapper minimal — sin lógica concreta del importer, el wrapper sería ruido. Al cerrar 9.4: agregar `bootstrap/import_laudus_history.py` que orquesta el importer en modo `full-backfill`.
  - El **filtro defensivo journalEntryId=0** queda como contrato a aplicar en 9.4 (documentado en probe `_bmad-output/spike-beancount/probe-empty-currency.py`).

- [x] Task 5: Validación AC8 (bean-check global)
  - [x] `bean-check ledger/main.beancount` exit 0 sobre el ledger COMPLETO (255 cuentas hoja + 12 saldos iniciales + estructura F0). Verificado al cerrar Tasks 1, 2, 3.
  - [ ] `bean-query` smoke con count de transactions queda pendiente (sin transactions importadas todavía — la única "transacción" es la sample en `manual/2026-04.beancount` que sirve de fixture para los tests de Story 9.0).

- [x] Task 6: `bootstrap/validate_cuadratura.py` (AC9 parcial)
  - [x] Comparación CLP↔CLP por cuenta usando `beanquery`.
  - [x] **Cortes implementados:** solo `2021-01-01` (post-opening). **Cuadra exacto: 0 diferencias** sobre las 12 cuentas con saldo (smoke real verificado).
  - [ ] **Cortes deferred:** cierres anuales 2021-2025 + 2026-04-30 — requieren Task 4 (history importada) done. Constante `CUTOFF_DATES` en el script lista solo `["2021-01-01"]` por ahora; agregar las demás cuando 9.4 cierre.
  - [x] Reporte CSV `bootstrap/report-cuadratura-{YYYY-MM-DD}.csv` (gitignored).
  - [x] 6 unit tests verde.

- [x] Task 7: Documentación operativa
  - [x] `bootstrap/README.md` con: requisitos, orden de ejecución, outputs por script, convenciones implementadas (incluyendo padding, Laudus manda, Q7, fechas pad/balance), troubleshooting (Supabase pausado, missing commodity, glob vacío, mismatches, riesgo cuentas Laudus sin metadata Supabase), status post-bootstrap por AC.
  - [x] Disclaimer post-9.11 documentado.

---

## Dev Notes

### Input autoritativo

`_bmad-output/planning-artifacts/architecture-c4.md` — secciones §1.5 (estructura `ledger/`), §2 (esquema directivas), §3 (importer Laudus), §7.1 (plan F0), §7.7 (Story 4.0 superseded). **Donde el spike y el artifact difieran, el artifact prevalece.**

> **Nota:** el artifact menciona seed CSV en `bootstrap/seed/*.csv` como input al bootstrap. Esa decisión quedó superada el 2026-05-05 por **Option C híbrida** (Laudus API + Supabase one-time read, sin CSV intermedio en repo). Bob flagueó esto en el coord file para que Moishe patche el artifact en una pasada — esta story refleja el modelo nuevo.

### Decisión Option C híbrida (2026-05-05)

**Ary eligió C** sobre las alternativas A (seed CSV) y B (Supabase-only one-time):
- **Pro:** ejercita el conector Laudus (smoke test del endpoint que usará 9.4 semanal); fuente original real para datos contables base; sin fósiles confusos en repo.
- **Contra:** bootstrap depende de Supabase vivo (one-time). Mitigado: Supabase queda en standby hasta 9.11, costo ~0.

**Modelo unificado** (sin registry separado bank_accounts) confirmado por Ary el 2026-05-05 — relación 1:1 plan↔bank_account (escenario "varias cuentas comparten institución, cada una con su `last4` propio"), no es N:1 plan→cuenta-física.

### Gaps técnicos a confirmar al implementar

- **¿Laudus API expone metadata bancaria (`account_type`, `last4`, `currency`) por cuenta?** Si sí, el script puede preferir Laudus sobre Supabase para esos campos (más original). Si no, Supabase es la única fuente y se mantiene como está.
  - **Decisión documentada:** **Laudus manda en datos contables base** (account_number, account_name, jerarquía); **Supabase manda en taxonomía Ary** (Categoria1/2/3 + metadata bancaria). El dev resuelve al implementar y documenta la elección.

### Reuso de código existente

| Componente | Ruta | Uso en bootstrap |
|---|---|---|
| `pipeline/services/balance_sheet_service.py` | preservado | fetch del balance sheet 2021-01-01 |
| `pipeline/services/ledger_service.py` | preservado | fetch del ledger 2021-now |
| `pipeline/config/laudus_config.py` | preservado | auth + endpoints |
| `pipeline/utils/dates.py` | preservado | normalización de fechas |
| `backend/app/repositories/supabase_repository.py` | **uso transitorio** | lectura one-time de `plan_de_cuentas` durante bootstrap. Después de 9.1 OK + 9.11 ejecutado → código se borra junto con el módulo. |
| Spike `_bmad-output/spike-beancount/generate.py:54-58` | referencia | patrón de slug + mapeo Categoria1 |

### Plugins en `main.beancount`

```beancount
plugin "beancount.plugins.implicit_prices"
plugin "beancount.plugins.check_commodity"
;; NO usar auto_accounts — explicit opens only
```

### Project structure

```
bootstrap/                                 # NEW directorio top-level
  init_ledger_dir.py                       # Task 1
  generate_accounts.py                     # Task 2 — Laudus + Supabase one-time
  generate_opening_balances.py             # Task 3
  import_laudus_history.py                 # Task 4 (orquestador, llama a Story 9.4)
  validate_bootstrap.py                    # Task 5 (bean-check global + smoke queries)
  validate_cuadratura.py                   # Task 6 (CLP↔CLP)
  report-unmapped-accounts.csv             # output AC4 (gitignored)
  report-mismatch-accounts.csv             # output AC3 (gitignored)
  README.md                                # Task 7

ledger/                                    # NEW — generado por bootstrap, se commitea post-bootstrap OK
  main.beancount
  accounts.beancount                       # 293 cuentas con metadata unificada (modelo nuevo)
  opening-2021.beancount
  prices.beancount                         # vacío inicial — Story 9.10 popula
  imports/laudus/*.beancount
  imports/laudus/_new-accounts-pending.beancount
  _meta/import-log.jsonl
  _meta/categorization-history.jsonl
  _meta/cartola-discrepancies.jsonl        # vacío inicial — Story 9.6 popula
  _meta/fx-bcch-eom.jsonl                  # vacío inicial — Story 9.10 popula
```

### Decisión sobre commit del ledger generado

El output del bootstrap (`ledger/`) **se commitea al repo** tras AC8+AC9 OK. Es source of truth a partir de ese momento. Re-runs del bootstrap (rm -rf + regenerate) deben producir output bit-idéntico — esto se verifica con `git diff` post re-run en AC10.

### Tolerancia AC10 (re-bootstrap idempotente)

"Bit-idéntico" requiere: ordenar transactions por (date, journalentryid), ordenar cuentas alfabéticamente, ISO 8601 timestamps en metadata. Documentar cualquier source de no-determinismo (ej: orden de Python dict en Python 3.6-, no aplica en 3.12).

### Workflow post-bootstrap

Después de que 9.1 está done y mergeado:
- `accounts.beancount` es la **single source of truth** para cuentas.
- Cuentas nuevas detectadas por Story 9.4 → friction en `_new-accounts-pending.beancount` → Ary las promueve manualmente al `accounts.beancount` con su Categoria1/2/3 + metadata bancaria (vía Fava editor de Story 9.0/9.3).
- Supabase queda en standby (sin queries) hasta cierre de 9.11.

### Caveat retroactivo: `bank_account_last4` quedó null en bootstrap (Flag 6, 2026-05-05)

**Hallazgo post-cierre:** durante implementación, Amelia verificó que la tabla `bank_accounts` de Supabase **NO tiene el campo `bank_account_last4`**. Ese dato vive en Google Sheets (tab `Bancos`), que el bootstrap no consulta (Option C híbrida lee Laudus + Supabase one-time, no Sheets).

**Resultado en producción:** las 47 directivas `open` bancarias en `accounts.beancount` quedaron emitidas con `bank_account_last4: null` (o sin la metadata).

**Decisión Ary 2026-05-05:** **NO patchear el bootstrap** (esta story está done; sumar trabajo es churn). El poblado del `last4` queda como **pre-condición operacional manual** asignada a Story 9.3 AC8: Ary edita las 47 cuentas vía Fava antes de operar cartolas. Story 9.5 valida server-side (AC1 código `MISSING_LAST4`) y corta el flujo si falta — failure mode accionable.

**Alternativa descartada:** patch a `generate_accounts.py` para leer Sheets como tercer source. Razón: contradice la dirección de Story 9.11 (deprecation Sheets), agrega complejidad a un bootstrap done, y el costo de poblar manualmente es único (~30 min).

### References

- [Source: architecture-c4.md §1.5 — Estructura `ledger/`]
- [Source: architecture-c4.md §2 — Esquema directivas Beancount]
- [Source: architecture-c4.md §3 — Importer Laudus]
- [Source: architecture-c4.md §7.1 — Plan F0]
- [Source: architecture-c4.md §7.7 — Costo hundido Story 4.0 — superseded by 9.1]
- [Source: bob-x-moishe-epic9-2026-04-30.md — Q4 cierre + ítem #9 sin-Supabase + decisión Option C 2026-05-05]
- [Source: q4-fx-decision-2026-05-05.md — Q4 cierre formal]
- [Source: _bmad-output/spike-beancount/generate.py — patrón de mapeo validado]
- [Source: _bmad-output/spike-beancount/probe-empty-currency.py — caveat journalEntryId=0]
