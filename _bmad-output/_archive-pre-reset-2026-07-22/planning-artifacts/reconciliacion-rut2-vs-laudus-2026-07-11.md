# Reconciliación peso-por-peso — Libro RUT2 (Fondo Común FFCC/JAB) vs Laudus

**Fecha:** 2026-07-11
**Story:** 12.5 — DoD del Epic 12
**Naturaleza:** validación read-only (NO escribe al ledger)
**Ancla:** balance de Laudus del libro RUT2 a fin de mes (decisión Ary 2026-07-10: Laudus se asume correcto)

---

## Veredicto

**PASS peso-por-peso.** El libro RUT2 en el ledger es espejo fiel de Laudus al corte primario: **0 discrepancias sobre 237 cuentas con saldo**, diff exacto 0 CLP por cuenta.

El Epic 12 queda **listo para cierre**, pendiente del gate de Ary (el flip de `epic-12 → done` es cierre de épica, no lo hace la story — ver project-context §Gates STOP).

---

## Corte usado

| Corte | Motivo | Resultado |
|---|---|---|
| **2026-06-30** (primario) | Último fin de mes COMPLETO. El libro está vivo hasta 2026-07-10, así que julio está a medias y no sirve de ancla. Fin de mes intermedio = sin el asiento de cierre/apertura anual de Laudus de por medio (TRAP #2). | **PASS, 0 diffs** |

Cortes anuales `YYYY-12-31` NO se agregaron: el "Comprobante de cierre/apertura" anual de Laudus (±402.430.179 sobre 211005, sonda 12.4) crea ambigüedad antes/después del asiento de cierre en un corte de fin de año. El ancla de fin de mes intermedio es más limpia y suficiente para el DoD.

---

## Tabla resumen

| Métrica | Valor |
|---|---|
| Cuentas reportadas por Laudus RUT2 (`balanceSheet/totals?dateTo=2026-06-30`) | 243 |
| Cuentas RUT2 con saldo ≠ 0 en Beancount (scopeado a FFCC/JAB) | 237 |
| **Discrepancias (diff ≠ 0)** | **0** |
| Total CLP de diffs | 0 |
| `amount_mismatch` | 0 |
| `account_not_in_rut2_tree` (señal de ruteo roto) | 0 |
| `beancount_only` (cuenta en ledger que Laudus no reporta) | 0 |

Las 6 filas de diferencia entre 243 (Laudus) y 237 (Beancount con saldo) son cuentas que Laudus lista con saldo 0 (rollups / cuentas inactivas, incl. la hoja `13` sin movimientos del TRAP #3) — no generan discrepancia.

**No hubo triage:** al ser 0 diffs, no hay discrepancias que clasificar ni explicaciones que documentar. PASS limpio.

---

## Evidencia

- **Reconciliador:** [bootstrap/reconcile_rut2.py](../../bootstrap/reconcile_rut2.py) — scopeado a RUT2 por 2º segmento del path ∈ {FFCC, JAB} (NO reusa los `load_account_index` globales last-wins — TRAP #1). Fetch con `login(get_book("RUT2"))` + `verify_book_identity` ("ACTIVO FFCC") antes de leer.
- **Test offline:** [backend/tests/test_reconcile_rut2.py](../../backend/tests/test_reconcile_rut2.py) — 9 tests (comparación, scoping por entidad, aislamiento de codes colisionados, normalización simétrica de la hoja "13").
- **CSV del corte:** `bootstrap/report-reconciliacion-rut2-2026-06-30.csv` — solo header (0 filas de diff). Es un output **gitignored** (`bootstrap/report-*.csv`): no vive en el repo, se regenera con el comando de abajo (determinista).

### Comando de reproducción

```
rm -f ledger/.main.beancount.picklecache
PYTHONUTF8=1 PYTHONPATH=. venv/Scripts/python -m bootstrap.reconcile_rut2 --cutoff 2026-06-30
```

Salida:
```
INFO Laudus balanceSheet/totals RUT2 2026-06-30: 243 cuentas
[OK] Reconciliación RUT2 2026-06-30: 0 diferencias sobre 237 cuentas con saldo  ->  bootstrap\report-reconciliacion-rut2-2026-06-30.csv
[OK] RUT2 cuadra peso-por-peso con Laudus en todos los cortes.
```

---

## Dashboards FFCC/JAB (AC2)

Los dashboards de balance por entidad coinciden peso-por-peso con lo reconciliado al corte:

| Entidad | Cuentas A/L/E en dashboard | Mismatches vs reconciliación | Drill-down |
|---|---|---|---|
| FFCC | 24 (20 con saldo ≠ 0 + 4 en 0) | **0** | 14.116 filas, 100% con `code`, 74 codes; filtro por cuenta trae solo esa cuenta |
| JAB | 9 (8 con saldo ≠ 0 + 1 en 0) | **0** | 24.294 filas, 100% con `code`, 169 codes; filtro por cuenta trae solo esa cuenta |

`last_sync` de ambos = 2026-06-30 (frescura del libro RUT2, aislada de EAG por `_freshness_pattern`, fix 12.4). Ninguna cuenta RUT2 sin `code` → el defer 11.2 ("cuenta sin code → drill-down trae el árbol entero") NO se activa para RUT2 (12.3 minteó `code` en todo el árbol).

---

## Gates anti-regresión (AC4)

| Gate | Resultado |
|---|---|
| `git status ledger/` limpio (0 escrituras) | **PASS** — el directorio `ledger/` quedó byte-idéntico (esta story solo lee) |
| Dump EAG consolidado + report_rows, fail-safe no-vacío | **PASS** — 56 cuentas / 19.989 filas (= baseline 12.4), `last_sync=2026-07-08` (frescura EAG intacta) |
| `bean-check ledger/main.beancount` | **exit 0** |
| Suite completa `pytest backend/tests pipeline` | **PASS** — 860 passed / 1 xfailed (baseline 851/1 + 9 tests nuevos, 0 regresiones) |

---

## Alcance / lo que NO cubre esta reconciliación

- **No reconcilia contra cartolas / saldos bancarios reales** — eso es la fase posterior, fuera del Epic 12 (decisión Ary 2026-07-10). Esta reconciliación garantiza que el sistema es espejo fiel de **Laudus**; la cuadratura contra el mundo real viene después.
- **No corrige nada** — el objetivo es el veredicto. Como el corte dio 0 diffs, no hubo nada que corregir.

---

## Code review (2026-07-11)

Review adversarial de 3 capas (Blind Hunter / Edge Case Hunter / Acceptance Auditor) → veredicto del Auditor **CONFORMANT** (AC1/AC3/AC4 PASS, TRAPs #1–#3 neutralizados, read-only garantizado estructuralmente). Se verificó empíricamente que el PASS **no es suerte del índice last-wins**: 0 colisiones de code normalizado sobre 311 opens FFCC/JAB. 3 patches de hardening del gate: test end-to-end del TRAP #3 (fila Laudus `"13"`→`"130000"`), guard `RuntimeError` anti-colisión en el índice, y validación de formato de `--cutoff`. Suite tras el review: **861 passed / 1 xfailed** (10 tests de reconciliación). El resultado de la reconciliación (0 diffs / 237 cuentas) no cambió.
