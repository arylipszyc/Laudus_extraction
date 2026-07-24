---
title: 'Desglose TC: contabilizar todo operation_type (nunca dropear en silencio)'
type: 'bugfix'
created: '2026-06-27'
status: 'done'
baseline_commit: '95b3707954b71386cb741c20895fe312fca5a086'
context:
  - '{project-root}/_bmad-output/planning-artifacts/valentina-correccion-tc-cartolas-2026-06-20.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** El builder de corrección TC solo contabiliza `operation_type ∈ {compra, cuota, abono, pago}`
y **descarta el resto en silencio** (`else: continue`, [tc_correction.py:152](pipeline/importers/tc_correction.py#L152)).
Un barrido de 304 cartolas muestra la fuga: 630 líneas `None`, 76 pagos automáticos (PAT/cargo), 74
cargos bancarios (impuesto/comisión), 1 nota de crédito. Cada línea dropeada pierde **los dos lados**
del asiento: el pasivo `TC:Real` queda corto Y ese gasto desaparece de los libros.

**Approach:** Normalizar `operation_type` (sinónimos + `None` por signo) y rutear la contrapartida del
asiento (a) por tipo, con una **red de seguridad**: toda línea emite asiento contra `TC:Real`, y lo no
reconocido va a `Suspense` y se **reporta** en `result.unmapped` — nunca se descarta. Band-aid en el
builder; NO se toca el prompt de extracción 9.5.

## Boundaries & Constraints

**Always:**
- Toda línea (salvo monto 0) emite asiento (a) que toca `Liabilities:EAG:TC:Real:<x>` por `-monto×fx`,
  de modo que `Σ postings a TC:Real == −closing` para un estado CLP totalmente mapeado.
- Cargos bancarios (`impuesto`/`comision`/`interes`/`seguro`/`mantencion`) → cuenta FIJA
  `Expenses:EAG:GastosBancarios-430003` (NO pasan por el categorizador 9.7).
- `avance` → `Assets:EAG:Caja-111001` (CLP) / `Assets:EAG:CajaUs-111003` (USD), NO es gasto.
- Lo no reconocido → asiento (a) contra `Expenses:EAG:Suspense` **+ contar en `result.unmapped`**.

**Ask First:**
- Si aparece un `operation_type` que sugiera una 6ª categoría de routing (p.ej. un tipo de cargo nuevo
  que no encaje en consumo/cargo-bancario/avance/abono/pago) → HALT, no inventar destino.

**Never:**
- No tocar el prompt de extracción 9.5 (la normalización es band-aid en el builder, §11).
- No crear cuentas nuevas (las 4 destino ya existen en `accounts.beancount`, verificado 2026-06-27).
- No bajar `SUPRA_THRESHOLD` ni cambiar el comportamiento del categorizador 9.7.
- Fuera de scope: los colores/confianza y el frontend `/categorizacion` (Goal B, diferido a
  `deferred-work.md`).

## I/O & Edge-Case Matrix

| Scenario | Input (`raw.operation_type`, `amount`) | Expected Behavior | Error Handling |
|----------|----------------------------------------|-------------------|----------------|
| Compra/cuota | `compra`/`cuota`, + | asiento (a): `TC:Real −clp` / `Expenses:<cat>` (vía 9.7) `+clp` | N/A |
| None positivo | `None`, + | normaliza a `compra` → categorizado | N/A |
| None negativo | `None`, − | normaliza a `abono` → asiento (a) invertido por signo | N/A |
| Pago automático | `COMPRAS P.A.T.`/`pat`/`compra_automatica`/`cargo_automatico`, + | normaliza a `compra` → categorizado | N/A |
| Cargo bancario | `impuesto`/`comision`/`interes`/`seguro`/`mantencion` | asiento (a): `TC:Real` / `GastosBancarios-430003` (FIJO) | N/A |
| Nota de crédito | `nota_credito`, − | normaliza a `abono` → invertido | N/A |
| Avance | `avance` | asiento (a): `TC:Real` / `Caja-111001` (CLP) o `CajaUs-111003` (USD) | N/A |
| Pago | `pago`, − | asiento (b) reclasif. (sin cambio respecto a hoy) | N/A |
| No reconocido | `xyz` (libre) | asiento (a): `TC:Real` / `Suspense` + append a `result.unmapped` | nunca dropea |
| Monto cero | cualquiera, 0 | se salta (sin asiento) | N/A |

</frozen-after-approval>

## Code Map

- `pipeline/importers/tc_correction.py` -- builder `build_tc_correction_entries` (loop a reescribir, [L135-L160](pipeline/importers/tc_correction.py#L135-L160)) + orquestador `correct_tc_cartola` (counts [L341-L344](pipeline/importers/tc_correction.py#L341-L344))
- `pipeline/importers/categorization/service.py` -- `predict()` del 9.7 (consumido tal cual por `category_for`; sin cambios en Goal A)
- `backend/app/integrations/cartola_schema.py` -- `CartolaTransaction.raw` es libre (sin enum) y `currency` es per-tx (para elegir Caja CLP/USD del avance)
- `ledger/accounts.beancount` -- confirma `GastosBancarios-430003`, `Caja-111001`, `CajaUs-111003`, `Suspense` ya abiertas (L890, L11, L18, L1997)
- `backend/tests/test_tc_correction.py` -- patrón de tests; los fixtures `_bean_check` (L34) y `_ORCH_ACCOUNTS` (L232) deben sumar las 3 cuentas nuevas usadas

## Tasks & Acceptance

**Execution:**
- [x] `pipeline/importers/tc_correction.py` -- añadir constantes (`BANK_CHARGES_ACCOUNT`, `CAJA_CLP`, `CAJA_USD`, `SUSPENSE_ACCOUNT`), los sets de routing, y `_normalize_op(raw, amount) -> str` (sinónimos→canónico; `""`/`None`→`compra` si `amount>0` else `abono`; `nota_credito`→`abono`; no reconocido→`""`). Case-insensitive sobre el raw -- clasificación canónica previa al dispatch.
- [x] `pipeline/importers/tc_correction.py` -- reescribir el loop de `build_tc_correction_entries`: dispatch por op normalizado (consumo→`category_for`; cargo→`GastosBancarios`; avance→Caja por `tx.currency`; abono→invertido; `pago`→(b) sin cambio; desconocido→`Suspense`). Añadir out-param `unmapped: list | None = None` y append `{"line", "op", "monto"}` para desconocidos. La metadata guarda el op normalizado (o el raw si fue desconocido) -- nunca `continue` salvo `clp==0`.
- [x] `pipeline/importers/tc_correction.py` -- en `correct_tc_cartola`: pasar `unmapped=[]` al builder y exponer `result["unmapped"]`; normalizar los counts `purchases`/`payments` con `_normalize_op` para que sigan siendo honestos -- el contador ve qué quedó sin mapear.
- [x] `backend/tests/test_tc_correction.py` -- un test por fila de la matriz (None±, PAT/cargo_automatico, impuesto+comision→`GastosBancarios`, avance→Caja, no-reconocido→`Suspense`+`unmapped`, invariante `TC:Real==−closing` para CLP mixto) y agregar `GastosBancarios-430003`/`Caja-111001`/`CajaUs-111003` a los fixtures `_bean_check` y `_ORCH_ACCOUNTS`.

**Acceptance Criteria:**
- Given una cartola CLP con compras, cargos bancarios y un pago (todos mapeados), when se corrige, then `Σ postings a TC:Real == −closing` y `result.unmapped == []`.
- Given una línea con `operation_type` no reconocido, when se corrige, then aparece en `result.unmapped` con `{line, op, monto}`, el asiento va a `Suspense`, y el ledger pasa bean-check (nada se descarta).
- Given la suite backend, when corre, then verde con 0 regresiones nuevas (los 2 rojos en `test_fava_edit_validator` son PRE-EXISTENTES).

## Spec Change Log

## Design Notes

**Por qué el invariante `TC:Real == −closing` vale (CLP, fx=1):** cada línea aporta `−amount` a
`TC:Real` vía (a); el `pago` aporta `+lump = +abs(amount) = −amount` vía (b); la apertura aporta
`−opening`. Total = `−(opening + Σ amounts) = −closing`. Por eso el drop de impuesto/comisión dejaba el
pasivo corto exactamente esa suma (el gap real observado en BCI = $6.795 = $781 + $6.014).

**Red de seguridad, no bloqueo:** `operation_type` es libre en `raw` (sin enum de schema), así que el
default seguro (Suspense + reportar) es obligatorio. No bloquea la corrección — el contador revisa los
`unmapped` después. Esto es lo que el comentario viejo *prometía* y no hacía.

**Out-param vs cambio de firma:** se usa `unmapped: list | None = None` (mutado por el builder) en vez
de devolver una tupla, para no romper los ~10 tests que consumen `build_tc_correction_entries(...)`
como lista de entries directa.

## Verification

**Commands:**
- `cd backend && PYTHONUTF8=1 ../venv/Scripts/python.exe -m pytest tests/test_tc_correction.py -q` -- expected: verde, todos los tests nuevos pasan.
- `PYTHONUTF8=1 ../venv/Scripts/python.exe -m pytest -q` (desde `backend/`) -- expected: 0 regresiones nuevas (2 rojos pre-existentes en `test_fava_edit_validator`).

**Manual checks (sandbox de la investigación, lo corre Ary/Valentina):**
- Re-importar la cartola BCI 2026-04 contra una copia sandbox del ledger: `TC:Real:Tc1027VisaInfinity`
  cierra en **−3.219.948** (hoy −3.213.153); impuesto $781 + comisión $6.014 en `GastosBancarios-430003`;
  `result.unmapped == []`.

## Suggested Review Order

**Clasificación y normalización (entry point)**

- Punto de entrada: normaliza el `operation_type` sucio (None→signo, sinónimos, no-reconocido→`""`); `str()` defensivo.
  [`tc_correction.py:106`](../../pipeline/importers/tc_correction.py#L106)

**Routing del asiento (a) — el núcleo**

- El dispatch que cierra el drop: toda línea toca `TC:Real`; la contrapartida varía por tipo.
  [`tc_correction.py:168`](../../pipeline/importers/tc_correction.py#L168)
- Cargo bancario → cuenta FIJA (no pasa por el 9.7).
  [`tc_correction.py:188`](../../pipeline/importers/tc_correction.py#L188)
- Avance → Caja CLP/USD por `tx.currency` (es plata, no gasto).
  [`tc_correction.py:190`](../../pipeline/importers/tc_correction.py#L190)
- Red de seguridad: no reconocido → Suspense + reporte en `unmapped` (nunca descarta).
  [`tc_correction.py:193`](../../pipeline/importers/tc_correction.py#L193)

**Orquestador — exposición y consistencia**

- Expone `result["unmapped"]` (lista compartida con el builder).
  [`tc_correction.py:362`](../../pipeline/importers/tc_correction.py#L362)
- Patch del review: el loop USD usa `_normalize_op` (evita KeyError con `pago` en mayúsculas).
  [`tc_correction.py:337`](../../pipeline/importers/tc_correction.py#L337)

**Tests (soporte)**

- Invariante `TC:Real == −closing` con todos los tipos mezclados (AC1).
  [`test_tc_correction.py:271`](../../backend/tests/test_tc_correction.py#L271)
- No reconocido → Suspense + `unmapped` (AC2).
  [`test_tc_correction.py:257`](../../backend/tests/test_tc_correction.py#L257)
- Robustez de `_normalize_op` (case/espacios/no-str, del review).
  [`test_tc_correction.py:190`](../../backend/tests/test_tc_correction.py#L190)
