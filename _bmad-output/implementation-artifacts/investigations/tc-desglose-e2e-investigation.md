# Investigation: Desglose de TC end-to-end con cartola 2026 real

## Hand-off Brief

1. **What happened.** El desglose de TC corre end-to-end correctamente para el camino feliz (asientos a/b/c, apertura idempotente, bean-check verde), PERO el builder **descarta en silencio** los `operation_type` que no sean `compra/cuota/abono/pago` — en la cartola BCI 2026-04 real perdió `impuesto` (781) + `comisión` (6.014), subvaluando el pasivo `TC:Real` en exactamente 6.795 CLP y perdiendo ese gasto.
2. **Where the case stands.** Concluido. Causa raíz Confirmada (High): `tc_correction.py:135-153`, el `else: continue` salta toda op desconocida sin surfacearla (el comentario "queda para revisión/discrepancia" es aspiracional — nada la reporta). Reproducido en sandbox con datos reales.
3. **What's needed next.** Decidir tratamiento contable de impuesto/comisión/interés/seguro (son gasto/cargo real) con Valentina, luego story o quick-dev para mapearlos a asiento (a) + surfacear cualquier op no contabilizada. Severidad baja en pesos (0,6% acá) pero silenciosa y recurrente.

## Case Info

| Field            | Value                                                                      |
| ---------------- | -------------------------------------------------------------------------- |
| Ticket           | N/A (deriva del action item #3 de la retro de Epic 6)                      |
| Date opened      | 2026-06-26                                                                 |
| Status           | Concluded (causa raíz Confirmada)                                          |
| System           | win32 / Python backend FastAPI + Beancount; rama `main`                    |
| Evidence sources | código (tc_correction.py, cartolas/service.py), accounts.beancount, samples/, tests |

## Problem Statement

Epic 6 cerró con el "desglose de TC dormido". Lo bloqueante ya está hecho: cuentas `Liabilities:EAG:TC:Real:*` + `Equity:Apertura:TarjetasSinDetalle` declaradas (`1d6323b`), categorizador 9.7 wireado en `_build_importer` (`f166420`), `bank_account_id` en las cuentas-gasto. Falta **validar end-to-end** que al importar una cartola TC real el orquestador `correct_tc_cartola` genere los asientos (a) compras itemizadas, (b) reclasif del pago, (c) apertura, y que cuadre el §7 contra `_bmad-output/planning-artifacts/valentina-correccion-tc-cartolas-2026-06-20.md`.

## Evidence Inventory

| Source   | Status     | Notes     |
| -------- | ---------- | --------- |
| pipeline/importers/tc_correction.py | Available | Builder puro + orquestador completos. Stronghold. |
| backend/app/api/v1/cartolas/service.py | Available | `validate_balance` ramifica por `account_type`; `_build_importer` inyecta 9.7. |
| ledger/accounts.beancount | Available | 9 cuentas-gasto TC + 8 TC:Real + Equity:Apertura; stems calzan. |
| samples/*.pdf | Available | Cartolas TC 2026-04 reales: bci-visa-202604, santander-mastercard-202604, estado-de-cuenta (21..28). |
| imports/laudus/ (pagos para FX/lump USD) | Partial | Necesario solo para cartolas USD; no verificado aún que contenga el pago que cuadra la glosa. |
| last4 / bank_name en metadata de cuentas | Missing | `bank_name: ""` vacío y sin `last4` visible en el open de la cuenta-gasto. Alimenta slug + matching USD. |

## Investigation Backlog

| # | Path to Explore | Priority | Status | Notes |
| - | --------------- | -------- | ------ | ----- |
| 1 | Mapear cada sample PDF → `bank_account_id` registrado (¿qué tarjeta es cuál?) | High | Open | El upload necesita el hint correcto (account_type + bank_account_id). |
| 2 | Confirmar de dónde sale `last4` (resolver.get().last4) si no está en el open | High | Open | Si es None → slug usa "xxxx"; en USD afecta el matching. |
| 3 | Verificar que `imports/laudus/` tiene el pago que cuadra la glosa USD del estado | Medium | Open | Solo bloquea cartolas USD; CLP no lo necesita. |
| 4 | Correr §7 (no doble conteo) sobre la salida real y contra el diseño | High | Open | Núcleo de la verificación. test_tc_correction.py ya cubre el invariante en unit. |
| 5 | Decidir entorno: copia sandbox del ledger vs real (mutación + push + Gemini) | High | Open | Bloquea cualquier corrida real. Decisión de Ary. |

## Confirmed Findings

### Finding 1: El path TC está wireado punta a punta

**Evidence:** `backend/app/api/v1/cartolas/service.py:483` (branch `account_type == "tarjeta_credito"` → `correct_tc_cartola`); `pipeline/importers/tc_correction.py:237` (orquestador); `:113` (builder puro).

**Detail:** `validate_balance()` ramifica: TC postea la corrección, cuenta corriente reconcilia-sin-postear (modelo A 6.1). El orquestador lee el staged JSON `imports/cartolas/_staging/{batch_id}.cartola.json`, resuelve `expense_tc` vía `importer.resolver.resolve(bank_account_id)`, deriva `tc_real` con `tc_real_account()`, construye los asientos, valida cuadre (USD: FX vs BCCh ±5%), escribe `{slug}-tc.beancount` bajo lock + bean-check + git push.

### Finding 2: El categorizador real 9.7 está inyectado

**Evidence:** `backend/app/api/v1/cartolas/service.py:400-418` (`_build_importer` pasa `CategorizationService` como `category_predictor`; commit `f166420`).

**Detail:** Pipeline 9.7 (supra ≥30 / historical 1-29 / Suspense) corre sobre `_meta/categorization-history.jsonl`. Seams `smart_importer`/`gemini` sin adapter → esos stages se saltean (Suspense como default seguro).

### Finding 3: El andamiaje de cuentas existe y los stems calzan

**Evidence:** `ledger/accounts.beancount:897-985` (9 cuentas-gasto `Expenses:EAG:TC:<stem>-<code>`), `:2014-2070` (8 `Liabilities:EAG:TC:Real:<stem>` + `Equity:Apertura:TarjetasSinDetalle`); commit `1d6323b`.

**Detail:** La derivación pura `tc_real_account()` (`Expenses:EAG:TC:<stem>-<code>` → `Liabilities:EAG:TC:Real:<stem>`) tiene destino para 8 de 9 tarjetas. Amex 8083 (430011) no tiene `TC:Real` (omitida, cero actividad 2026). Cuentas-gasto traen `bank_account_id` + `bank_account_type: tarjeta_credito`.

## Missing Evidence

| Gap | Impact | How to Obtain |
| --- | ------ | ------------- |
| `last4` no visible en el open de la cuenta-gasto | El slug del archivo usa "xxxx" si es None; en USD el matching de FX no depende de él pero el slug sí desambigua CLP vs USD | Leer cómo `BankAccountResolver.get().last4` puebla last4 (¿otra fuente?) |
| Qué sample PDF corresponde a qué `bank_account_id` | Sin esto no se puede armar el hint de upload correcto | Inspeccionar los PDFs / preguntar a Ary |
| Pago Laudus que cuadra la glosa USD del estado | Cartola USD → bloqueante si falta (por diseño, no estima FX) | Grep `imports/laudus/` por la glosa USD del estado elegido |

## Source Code Trace

| Element | Detail |
| ------- | ------ |
| Entry point | `backend/app/api/v1/cartolas/service.py:421` `validate_balance()` |
| Trigger | PATCH cartola validate-balance con un staged JSON cuyo `source.account_type == "tarjeta_credito"` |
| Branch | `service.py:483` → `correct_tc_cartola()` (`tc_correction.py:237`) |
| Builder | `tc_correction.py:113` `build_tc_correction_entries` (asientos a/b/c) |
| Related files | reconcile.py (rama cuenta corriente), matching_engine.load_laudus_entries (FX/lump USD), fx_calculator (cordura BCCh), categorization/service.py (9.7) |

## Confirmed Findings (corrida sandbox 2026-06-26)

### Finding 4: El camino feliz funciona end-to-end

**Evidence:** corrida `correct_tc_cartola("58431cba…", importer, sandbox)` → `status=corrected`, `purchases=34`, `payments=1`, `opening_emitted=True`, bean-check verde, `git_commit_sha=None` (sin push, `IMPORTER_GIT_ENABLED` off). Archivo `Bci-xxxx-Tc1027VisaInfinity-2026-04-tc.beancount`.

**Detail:** Resolver mapea `e919b1db…` → `Expenses:EAG:TC:Tc1027VisaInfinity-430005` → `Liabilities:EAG:TC:Real:Tc1027VisaInfinity`. Asiento (c) apertura: `Equity:Apertura +2.054.314 / TC:Real −2.054.314` (una vez, guard idempotente OK). Asiento (b) pago: `Expenses:EAG:TC −2.054.314 / TC:Real +2.054.314` (saca el lump de Laudus). Asiento (a): 34 compras itemizadas a `Expenses:EAG:Suspense` (el 9.7 sin historial usa Suspense default — esperado, no defecto).

### Finding 5 (CAUSA RAÍZ): operation_types fuera de {compra,cuota,abono,pago} se descartan en silencio

**Evidence:** `pipeline/importers/tc_correction.py:135-153`. `_PURCHASE_OPS={compra,cuota,abono}`, `_PAYMENT_OPS={pago}`; el `else: continue` (línea 151-153) salta cualquier otra op. Cartola BCI real: `impuesto` "IMPUESTO DECRETO LEY 3475 TASA" (781) + `comision` "COBRO ADM MENSUAL" (6.014) descartadas. `operation_type` es libre en `raw` (sin constraint de schema, `cartola_schema.py`).

**Detail:** Verificación numérica del §7 (cuadre del pasivo): `TC:Real` generado = −3.213.153; esperado −(closing) = −3.219.948; **diff = 6.795 = impuesto + comisión EXACTO**. Doble impacto: (1) el pasivo `TC:Real` queda subvaluado → no calza con el cierre real del estado; (2) esos 6.795 de gasto real (comisión bancaria) + cargo (impuesto) **desaparecen de los libros** (no van a ningún `Expenses`). bean-check no lo pesca (cada asiento balancea internamente). El comentario "queda para revisión/discrepancia" es aspiracional: el `result` no cuenta ni surfacea las líneas saltadas. Prevalencia: BCI 2/37, Santander 0/45 → issuer-dependiente; podría ser mayor con `interes`/`seguro`/comisiones anuales.

## Conclusion

**Confidence:** High (causa raíz Confirmada en `path:line`, reproducida determinísticamente con datos reales en sandbox).

El desglose de TC está correctamente wireado y el camino feliz produce los asientos a/b/c esperados con bean-check verde. La única falla: **el builder solo contabiliza 4 `operation_type` y descarta el resto en silencio**, lo que subvalúa el pasivo real y pierde gasto cuando el estado trae impuesto/comisión (cargos reales y recurrentes en BCI). El §7 de gasto del diseño (Σcompras = consumo) se sostiene; el que se rompe es la completitud del pasivo (`TC:Real` ≠ closing). El diseño de Valentina nunca enumeró impuesto/comisión, así que es gap de diseño + implementación, no una regresión.

## Recommended Next Steps

### Fix direction

1. **Decisión contable (Valentina):** impuesto/comisión/interés/seguro son cargo/gasto real → deben ir a asiento (a) con una cuenta de gasto adecuada (¿`Expenses:EAG:TC:Comisiones`/`Impuestos` o categorización normal?). Esto restaura el cuadre `TC:Real = −closing`.
2. **Implementación (story o quick-dev):** ampliar `_PURCHASE_OPS` (o un mapeo op→cuenta) para cubrir las ops de cargo; y como mínimo **surfacear en el `result` toda línea con op no contabilizada** (count + razón) para que nunca se caiga en silencio.

### Diagnostic

- Confirmar el universo real de `operation_type` que emite Gemini sobre las ~15 cartolas de `samples/` antes de fijar el mapeo (evita otro drop silencioso de una op no vista — ej. `interes`, `seguro`, `avance`).

## Reproduction Plan

```
# sandbox seguro (sin push): IMPORTER_GIT_ENABLED unset
cp -r ledger <sandbox>
# parchar staging BCI: source.bank_account_id = e919b1db-be7d-430c-9f40-60fc58ae2bcb
venv/Scripts/python -c "_build_importer(<sandbox>); correct_tc_cartola('58431cba…', importer, <sandbox>)"
# inspeccionar Bci-xxxx-Tc1027VisaInfinity-2026-04-tc.beancount → TC:Real = -3.213.153 (≠ -3.219.948)
```

## Side Findings

- `bank_name: ""` vacío en las cuentas-gasto TC (`accounts.beancount:904`) y `last4 = None` (`resolver.get().last4`): el slug salió `Bci-xxxx-…`. No rompe (slug usa `model.source.bank_name`), pero el `xxxx` es ruido y, en USD, conviene confirmar que el matching no dependa de last4.
- Las 34 compras cayeron a `Expenses:EAG:Suspense` por falta de historial de categorización (9.7) — esperado en un ledger sin correcciones previas, no defecto. En prod con historial poblado, mejora.
