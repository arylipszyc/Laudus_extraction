---
story: 9.1
title: Bootstrap histórico Beancount (F0)
status: ready-for-dev
epic: 9
depends_on: []
blocks: [9.2, 9.4, 9.11]
execution_blocked_by: q4-fx
---

# Story 9.1 — Bootstrap histórico Beancount (F0)

## User Story

As a developer (Ary),
I want a script-driven bootstrap that generates a complete `ledger/` directory from Laudus history (2021 → now) with opening balances, account mapping, and `bean-check` clean,
So that we have a single Beancount source of truth ready for thin API + Fava + importers, and we know exactly which accounts didn't map automatically.

## Context

F0 del plan de migración (`architecture-c4.md` §7.1). Genera `ledger/main.beancount` válido (`bean-check` limpio) con:

- Las 293 cuentas mapeadas a árbol Beancount (`accounts.beancount`).
- Saldos iniciales 2021-01-01 vía `pad`+`balance` (`opening-2021.beancount`).
- Histórico 2021-now de Laudus normalizado a directivas Beancount (`imports/laudus/YYYY-MM.beancount`).

**Bloqueador para EJECUTAR (no para PREPARAR):** Q4 (FX). Ary identificó que Laudus convierte todo a CLP en su ledger antes de exponerlo, así que importar usando una fuente externa de FX rompe la cuadratura — la fuente correcta es el FX embebido en cada JE de Laudus. Esta story se PREPARA ahora con AC completos; el AC de cuadratura declara explícitamente la dep Q4 cerrada antes de ejecutar.

## Acceptance Criteria

**AC1 — Estructura de archivos generada**

**Given** los scripts de bootstrap se ejecutan en orden
**When** el bootstrap completa
**Then** existe el directorio `ledger/` con los archivos:
```
ledger/main.beancount
ledger/accounts.beancount
ledger/opening-2021.beancount
ledger/prices.beancount             # vacío inicial — populated por Story 9.10
ledger/imports/laudus/YYYY-MM.beancount  (un archivo por mes desde 2021-01)
ledger/imports/laudus/_new-accounts-pending.beancount  # vacío si todas mapean
ledger/_meta/import-log.jsonl       # log de runs del importer Laudus
ledger/_meta/categorization-history.jsonl  # vacío inicial
```
**And** `main.beancount` contiene únicamente: `option` directives + `include`s a las subzonas (NO transactions). El template literal de §1.5 del artifact.

---

**AC2 — Mapeo de las 293 cuentas a árbol Beancount**

**Given** `bootstrap/generate_accounts.py` lee `plan_de_cuentas` (Supabase) + `bank_accounts` (Supabase) + tabla §2.3 del artifact
**When** el script corre
**Then** `accounts.beancount` contiene una directiva `open` por cada cuenta del plan (293 + 47 bank_accounts) con:
  - `account` siguiendo patrón `{Root}:{Entity}:{Group}:{Slug(name)}-{account_number}` (§2.1)
  - `commodities` apropiados (`CLP` para CLP-only, `CLP, USD` si la cuenta puede tener USD)
  - Metadata estándar: `code:`, `laudus_account_name:`, `laudus_categoria1:`, `laudus_categoria2:`, `laudus_categoria3:`, y `bank_account_id:` cuando aplica
**And** las tarjetas de crédito mapean a `Liabilities:{Entity}:TC:...` (Q7 — corrige bug semántico actual)
**And** `bean-check` pasa limpio sobre solo `accounts.beancount` cargado en un main mínimo

---

**AC3 — Reporte de cuentas no-mapeables**

**Given** alguna cuenta del plan tiene `Categoria1` desconocido o NULL
**When** el script `generate_accounts.py` la encuentra
**Then** la cuenta NO se incluye en `accounts.beancount`
**And** se appendea a un reporte `bootstrap/report-unmapped-accounts.csv` con columnas: `account_number, account_name, cat1, cat2, cat3, reason, suggested_root, suggested_entity`
**And** el script imprime al final: "N cuentas no-mapeables encontradas — revisá `report-unmapped-accounts.csv` antes de ejecutar generate_opening_balances.py"
**And** el script falla con exit-code ≠ 0 si N > 0 — esto fuerza a Ary a reclasificarlas manualmente (Q9)

---

**AC4 — Opening balances 2021 vía pad+balance**

**Given** `bootstrap/generate_opening_balances.py` lee el balance sheet de Laudus al 2021-01-01
**When** el script corre
**Then** `opening-2021.beancount` contiene:
  - Una directiva `open Equity:EAG:OpeningBalances CLP, USD` con fecha 2021-01-01
  - Por cada cuenta de balance (Asset/Liability) con saldo ≠ 0 al 2021-01-01: una pareja `pad ... Equity:EAG:OpeningBalances` + `balance ...` (formato §2.6)
  - Metadata `source_je: "140"` + `source_je_number: "..."` en cada `pad` para preservar referencia al JE 140 de Laudus
**And** `bean-check` pasa limpio sobre `accounts.beancount + opening-2021.beancount`

---

**AC5 — Histórico 2021-now importado mes-por-mes**

**Given** `bootstrap/import_laudus_history.py` orquesta el importer Laudus en modo `full-backfill`
**When** el script corre desde `from_date=2021-01-02` (después del opening) hasta hoy
**Then** se genera un archivo `imports/laudus/YYYY-MM.beancount` por cada mes con JEs (write-and-replace, idempotente)
**And** cada `Transaction` tiene metadata: `id:` (= `journalentryid`), `je_num:` (= `journalentrynumber`), `source: "laudus-erp"`
**And** dedup por `id:` funciona en re-runs (correr el script dos veces produce el mismo output)

---

**AC6 — Cuentas nuevas no-en-plan detectadas**

**Given** durante el import histórico aparece un `account_number` que no existe en `accounts.beancount`
**When** el importer Laudus la encuentra
**Then** NO abre la cuenta automáticamente
**And** appendea entry tentativo a `imports/laudus/_new-accounts-pending.beancount` (formato §3.4 del artifact)
**And** las JEs que la referencian mantienen `tag #pending-account` para poder filtrarlas en Fava

---

**AC7 — bean-check limpio sobre el ledger completo**

**Given** los pasos AC2-AC6 completaron sin errores
**When** se corre `bean-check ledger/main.beancount`
**Then** el comando retorna exit-code 0 (sin errores ni warnings bloqueantes)
**And** `bean-query ledger/main.beancount "SELECT count(*) FROM #" > 0` retorna conteos coherentes (todas las JE 2021-now contadas)

---

**AC8 — Cuadratura vs. ledger Laudus actual (DEP Q4)**

> **🔒 BLOCKED-BY-Q4** — este AC NO se valida en preparación; gating de ejecución solamente.

**Given** Q4 está cerrada — la fuente de FX para conversiones USD↔CLP es el campo embebido en cada JE de Laudus (`exchangerate` o derivable backwards)
**When** se corre el bootstrap completo y se compara el balance sheet generado por BQL `BALANCES FROM ... AT 2026-04-30` contra el balance sheet de Laudus al mismo corte (suma por entidad + total)
**Then** la diferencia por entidad es **0 CLP** (no es un % de tolerancia — es coincidencia exacta porque Laudus ya entrega todo en CLP)
**And** si hay diferencia: el script imprime tabla detallada (cuenta, monto Laudus, monto Beancount, diff) y falla con exit-code ≠ 0

---

**AC9 — Costo bajo de re-bootstrap**

**Given** el script de bootstrap completo
**When** se corre desde cero (rm -rf ledger/ && bootstrap)
**Then** completa en < 30 minutos para 5 años de history (~50K JEs estimadas)
**And** el output es bit-idéntico run a run (deterministic — mismo input Laudus → mismo output)

---

## Tasks / Subtasks

- [ ] Task 1: Esqueleto del directorio `ledger/`
  - [ ] Crear `bootstrap/init_ledger_dir.py` — crea estructura inicial vacía + `main.beancount` con includes solamente
  - [ ] Template de `main.beancount`: literal del artifact §1.5
  - [ ] Validar que `bean-check` pasa en directorio vacío + `main.beancount` con includes a archivos vacíos

- [ ] Task 2: `bootstrap/generate_accounts.py` (AC2 + AC3)
  - [ ] Leer `plan_de_cuentas` desde Supabase (registry sobreviviente de Story 4.0)
  - [ ] Leer `bank_accounts` desde Supabase
  - [ ] Aplicar tabla de mapeo §2.3 + §2.5 del artifact (Categoria1 → Root, Entity; account_type bank → Group)
  - [ ] Slug del `accountName`: ASCII, sin espacios, CamelCase. Reusar la lógica del spike (`spike-beancount/generate.py:54-58`).
  - [ ] Para cuentas con `Categoria1` desconocido o NULL: emitir línea en `report-unmapped-accounts.csv` con sugerencias heurísticas (ver §2.3 — cuentas de orden, contingencias, transferencias inter-entidad)
  - [ ] Si N unmapped > 0 → exit ≠ 0 con mensaje claro a Ary
  - [ ] Validar con `bean-check` solo sobre `accounts.beancount + main mínimo`

- [ ] Task 3: `bootstrap/generate_opening_balances.py` (AC4)
  - [ ] Llamar a Laudus API: `balance_sheet_service.fetch(date="2021-01-01")` (preserva auth/retry existentes)
  - [ ] Filtrar cuentas con saldo ≠ 0
  - [ ] Emitir directiva `open Equity:EAG:OpeningBalances CLP, USD` al 2021-01-01
  - [ ] Por cada cuenta: emitir `pad` + `balance` con metadata `source_je: "140"` (formato §2.6)
  - [ ] Tolerancia: cuentas con saldo en USD generan `balance` en USD; el `pad` consolida a CLP via plugin `implicit_prices` (validar que esto funciona con prices.beancount vacío — si no, fallback: emitir prices CLP=USD*1 con disclaimer en metadata, será sobrescrito tras Q4)

- [ ] Task 4: Reescritura de `pipeline/sync.py` orquestación (AC5 + AC6) — coordinar con Story 9.4
  - [ ] Esta story dispara la primera ejecución en modo `full-backfill`. La implementación del importer Laudus en sí es Story 9.4. Acá: `import_laudus_history.py` solo orquesta — llama al importer Laudus que está en producción tras 9.4.
  - [ ] Si 9.4 no está done todavía: `import_laudus_history.py` puede existir como wrapper minimal sobre el código futuro; agendar bootstrap real post-9.4.
  - [ ] Modo `full-backfill` corre desde 2021-01-02 hasta hoy, agrupa por mes, regenera cada `imports/laudus/YYYY-MM.beancount` write-and-replace.

- [ ] Task 5: Validación AC7 (bean-check global)
  - [ ] Correr `bean-check ledger/main.beancount` post-bootstrap
  - [ ] Capturar exit code; si ≠ 0 → imprimir errors completos + abort
  - [ ] Correr `bean-query` smoke test: count de transactions, count de cuentas, total assets EAG (sanity)

- [ ] Task 6: Validación AC8 (cuadratura vs Laudus) — **HOLD hasta Q4 cerrada**
  - [ ] No implementar la lógica concreta de comparación hasta saber qué fuente de FX usar. Cuando Q4 cierre, esta task se especifica con detalle.
  - [ ] Marcar el AC como pending en el story file con un `# TODO Q4` claro.

- [ ] Task 7: Documentación operativa
  - [ ] `bootstrap/README.md` con: requisitos (Python 3.12+, beancount, Supabase env vars, Laudus env vars), orden de ejecución, troubleshooting, comportamiento idempotente.
  - [ ] Documentar runtime esperado y cómo validar el output.

---

## Dev Notes

### Input autoritativo

`_bmad-output/planning-artifacts/architecture-c4.md` — secciones §1.5 (estructura `ledger/`), §2 (esquema directivas), §3 (importer Laudus), §7.1 (plan F0). **Donde el spike y el artifact difieran, el artifact prevalece.**

### Dependencia explícita Q4

AC8 (cuadratura vs Laudus) está **bloqueado por Q4**. Bob preparó esta story con el patrón completo y el AC declarado, pero la implementación de Task 6 espera la sesión dedicada FX entre Ary + Moishe. **No se ejecuta el bootstrap full hasta que Task 6 tenga implementación concreta.** Tasks 1-5 sí se pueden hacer ahora.

### Reuso de código existente

| Componente | Ruta | Uso en bootstrap |
|---|---|---|
| `pipeline/services/balance_sheet_service.py` | preservado | fetch del balance sheet 2021-01-01 |
| `pipeline/services/ledger_service.py` | preservado | fetch del ledger 2021-now |
| `pipeline/config/laudus_config.py` | preservado | auth + endpoints |
| `pipeline/utils/dates.py` | preservado | normalización de fechas |
| `backend/app/repositories/supabase_repository.py` | preservado | lectura de `plan_de_cuentas` + `bank_accounts` (registries) |
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
  generate_accounts.py                     # Task 2
  generate_opening_balances.py             # Task 3
  import_laudus_history.py                 # Task 4 (orquestador, llama a Story 9.4)
  validate_bootstrap.py                    # Task 5 (bean-check global + smoke queries)
  validate_cuadratura.py                   # Task 6 (TODO Q4)
  report-unmapped-accounts.csv             # output AC3 (gitignored)
  README.md                                # Task 7

ledger/                                    # NEW — generado por bootstrap, NO se commitea inicial pero sí post-bootstrap
  main.beancount
  accounts.beancount
  opening-2021.beancount
  prices.beancount
  imports/laudus/*.beancount
  imports/laudus/_new-accounts-pending.beancount
  _meta/import-log.jsonl
  _meta/categorization-history.jsonl
```

### Decisión sobre commit del ledger generado

El output del bootstrap (`ledger/`) **se commitea al repo** tras AC7+AC8 OK. Es source of truth a partir de ese momento. Re-runs del bootstrap (rm -rf + regenerate) deben producir output bit-idéntico — esto se verifica con `git diff` post re-run en AC9.

### Tolerancia AC9 (re-bootstrap idempotente)

"Bit-idéntico" requiere: ordenar transactions por (date, journalentryid), ordenar cuentas alfabéticamente, ISO 8601 timestamps en metadata. Documentar cualquier source de no-determinismo (ej: orden de Python dict en Python 3.6-, no aplica en 3.12).

### References

- [Source: architecture-c4.md §1.5 — Estructura `ledger/`]
- [Source: architecture-c4.md §2 — Esquema directivas Beancount]
- [Source: architecture-c4.md §3 — Importer Laudus]
- [Source: architecture-c4.md §7.1 — Plan F0]
- [Source: architecture-c4.md §7.7 — Costo hundido Story 4.0 — qué sobrevive]
- [Source: bob-x-moishe-epic9-2026-04-30.md — Q4 parking, Q9 cierre]
- [Source: _bmad-output/spike-beancount/generate.py — patrón de mapeo validado]
