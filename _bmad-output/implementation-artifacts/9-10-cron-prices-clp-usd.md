---
story: 9.10
title: Cron prices CLP/USD (BLOCKED-BY-Q4)
status: blocked-by-q4
epic: 9
depends_on: []
blocks: [9.1-execution]
---

# Story 9.10 — Cron prices CLP/USD

## ⚠ Status: BLOCKED-BY-Q4

> Esta story NO se prepara con AC + tasks completas hasta que Q4 (fuente de FX) esté cerrada en sesión dedicada Ary + Moishe.

## User Story (provisional)

As the system,
I want a daily cron job that fetches CLP↔USD exchange rates from a canonical source and appends them to `ledger/prices.beancount`,
So that USD-denominated transactions in the ledger have prices for consolidation to CLP.

## Why blocked

Decisión Q4 en parking (cierre Moishe-Winston, 2026-04-30):

> Ary observó que **Laudus convierte todo a CLP en su ledger antes de exponerlo**, así que importar usando una fuente externa de FX (mindicador.cl) rompe la cuadratura — la fuente de FX correcta no es externa sino el FX embebido en cada JE de Laudus (probable campo `exchangerate` o derivable backwards de monto USD/CLP). Esto se aborda en sesión dedicada antes de F0 ejecución.

Hasta que esa sesión cierre con una decisión, **no se puede definir** ni el AC ni las tasks de esta story:
- No sabemos si la fuente es mindicador.cl, BCCh API directo, FX embebido en Laudus, o una combinación.
- No sabemos si UF aplica (depende de qué cuentas la usan en el plan de 293).
- No sabemos qué se hace con el histórico — re-fetch FX o derivar backwards.

## Provisional placeholder AC (a re-escribir post-Q4)

**AC0 — Q4 cerrada antes de implementar**

**Given** una sesión dedicada Ary + Moishe documentada en un coord file
**When** la decisión sobre fuente de FX queda cerrada
**Then** Bob (SM) re-escribe esta story con AC concretos
**And** se mueve el status a `ready-for-dev`

---

## Próximos pasos

1. Moishe agenda sesión Q4 con Ary.
2. Cierre de Q4 → coord file con decisión + ajuste a `architecture-c4.md` §2.4.
3. Bob re-prepara esta story con AC + tasks.
4. Si la decisión es "FX embebido en Laudus": esta story podría ser absorbida por Story 9.4 (importer Laudus extrae FX por JE) y este archivo quedar superseded.

## References

- [Source: bob-x-moishe-epic9-2026-04-30.md — Q4 en parking]
- [Source: architecture-c4.md §2.4 — Multi-currency (CLP + USD), pendiente ajuste post-Q4]
