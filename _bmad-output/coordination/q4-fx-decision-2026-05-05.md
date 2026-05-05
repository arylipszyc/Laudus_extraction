---
thread_id: q4-fx-decision-2026-05-05
participants: [ary, moishe]
topic: Q4 — Fuente de FX para conversión USD↔CLP en el ledger Beancount
last_turn_by: moishe
awaiting: archived
status: closed
---

# Sesión Q4 — FX (cierre 2026-05-05)

## Contexto

Q4 quedó en parking al cierre del thread Winston (2026-04-30). Observación de Ary que la disparó:

> Laudus convierte todo a CLP en su ledger antes de exponerlo, así que importar usando una fuente externa de FX (mindicador.cl) rompe la cuadratura — la fuente correcta debería ser el FX embebido en cada JE de Laudus.

Esta sesión cierra Q4 con verificación empírica + decisión.

## Verificación empírica (probe-fx.py)

Query directo al endpoint `accounting/ledger` de Laudus para 2024-01-01 → 2026-05-05 (8263 líneas):

| `currencyCode` | Líneas | `parityToMainCurrency` |
|---|---|---|
| `"CLP"` | 8091 | siempre 1.0 |
| `""` (vacío) | 172 | siempre 0.0 |
| **non-CLP** | **0** | — |

**Conclusión empírica:** la observación de Ary era correcta en lo macro pero el mecanismo concreto es más extremo. Laudus **no guarda** el `currencyCode` ni el `parityToMainCurrency` originales para JEs USD. El contador entra el cargo USD ya convertido a CLP, y Laudus pierde toda info original. Los campos `currencyCode` + `parityToMainCurrency` existen en el schema pero están desperdiciados para movimientos USD.

Las 172 líneas con `currencyCode=""` son saldos sintéticos de apertura del rango (`description = "Saldo anterior"`, `journalEntryId = 0`, todas en el primer día del rango consultado). NO son JEs reales — la API las inyecta cuando consultás un rango que arranca después del JE 140. Caveat técnico defensivo para el importer: filtrar `journalEntryId = 0`.

**Implicancia de la verificación:**
- Opción B (FX embebido en JE de Laudus) → ❌ no viable. No hay FX embebido.
- Opción C (B + mindicador) → ❌ por extensión.
- Opciones viables → A (CLP-only) o D (cartola-derived FX).

Probes en `_bmad-output/spike-beancount/probe-fx.py` y `probe-empty-currency.py`.

## Decisión

**Opción D: FX derivada por cross-check cartola ↔ Laudus.**

### Engine FX

- **TC USD (Citi, Amex internacional, etc.):** cartola PDF como source de USD original, Laudus como source de CLP del contador. Matching línea-por-línea. FX implícita = `CLP_laudus / USD_cartola` por línea.
- **non-TC USD (Julius Baer Inversiones, transferencias USD, etc.):** matching 1:1 trivial. El contador anota una transacción Laudus por movimiento USD real, sin agregación → cuando hay cartola/comprobante USD, cross-check directo.
- **Pre-2026:** todo CLP-only (Opción A para histórico). No reconstruir USD original retroactivo a menos que aparezca necesidad de uso real.

### Variable de control

- BCCh end-of-month (dólar observado del Banco Central) como referencia.
- Threshold = **5%** desviación entre FX implícita derivada y BCCh.
- Out-of-tolerance → **flag, no abort.** La línea se importa con `fx_deviation_pct` y queda en el dashboard de discrepancias para review manual.

### Sistema de reconciliación cartola ↔ Laudus

**Estados de matching por línea de cartola:**

| Estado | Comportamiento | Sistema de verdad |
|---|---|---|
| Match perfecto | Import limpio | Cartola (USD) + Laudus (CLP) coinciden |
| **Distinto valor** | **NO importa** — bloqueante | — |
| Faltante en Laudus | Importa desde cartola con flag | Cartola |
| Faltante en cartolas | Importa desde Laudus CLP-only con flag | Laudus (sin USD original) |
| Distinta fecha | Importa con flag | **Cartola manda** |
| Distinta descripción | Importa con flag | **Cartola manda** |
| Distinta categoría | Importa con flag | Cartola sugiere; smart_importer revisa |

**Principios:**
- Cartola siempre manda (excepto en estado "faltante en cartolas").
- Toda línea flagueada: metadata Beancount + entrada en store de discrepancias.
- Dashboard de discrepancias pendientes — Ary/contador resuelve manualmente, ledger se re-emite.

**Ubicación del store de discrepancias:**
- Append-only JSONL en `ledger/_meta/cartola-discrepancies.jsonl` (audit trail full).
- Mirror operativo en tabla Supabase `cartola_reconciliation` (lectura rápida para dashboard).
- Ambos se actualizan sincronizados cuando se resuelve una discrepancia.

### Storage del FX en Beancount

Cada Transaction TC USD lleva metadata + price annotation:

```beancount
2026-04-15 * "Amazon"
  fx_source: "derived-cartola-citi-202604"
  fx_implied: "950.45"
  fx_bcch: "948.20"
  fx_deviation_pct: "0.24"
  Liabilities:EAG:TC:Citi    -100.00 USD @@ 95045.00 CLP
  Expenses:EAG:OnlinePurchases  95045.00 CLP
```

Plugin `implicit_prices` deriva las price directives de las transactions automáticamente. `prices.beancount` queda como placeholder vacío en el repo (referenciado en `main.beancount` por consistencia).

### Bootstrap (Story 9.1) destrabe

**9.1 sale de `execution-blocked-by-q4`.** Razón: pre-2026 va CLP-only, así que la cuadratura del bootstrap es trivial (CLP=CLP, diff exacta = 0 por construcción). AC8 simplifica a verificación CLP↔CLP sin lógica FX.

## Implicancias en stories — para Bob aplicar

Detalladas en append a `bob-x-moishe-epic9-migracion-beancount-2026-04-30.md`. Resumen:

| Story | Cambio |
|---|---|
| 9.1 | Destrabe — sale `execution-blocked-by-q4`, AC8 simplifica, filtro defensivo `journalEntryId=0` |
| 9.4 | Simplifica — todo CLP-only, borrar lógica "FX embebido". Filtro `journalEntryId=0` |
| 9.5 | Sin cambios |
| 9.6 | Scope ampliado — además de directivas, motor de matching + emisión de discrepancias. Bob decide si splittear en 9.6a/9.6b |
| 9.10 | Reformula — cron mensual end-of-month que fetcha BCCh observado, propósito = sanity check de FX derivadas |
| **NUEVA 9.12** | Dashboard de reconciliación — vista de transacciones flagueadas por estado, accionable, con resolución manual + re-emit |
| 9.8 | Sin cambios — el badge de "pendiente revisar" sigue siendo su responsabilidad; 9.12 es la vista detalle |

## Patches al artifact arquitectura

`architecture-c4.md §2.4` reescrita en este mismo cierre — Opción D reemplaza mindicador. Misma sesión.

## Estado

`closed`. No requiere más turnos. El trabajo derivado vive en el thread de Bob (re-abierto) y en sprint-status.yaml.

— Moishe
