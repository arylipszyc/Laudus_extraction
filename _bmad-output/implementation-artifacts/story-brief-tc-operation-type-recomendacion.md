# Brief quick-dev — Desglose TC: operation_type completo + recomendación con colores

- **Fecha:** 2026-06-27
- **Origen:** consulta a Valentina (agente-contadora) tras verificación end-to-end del desglose TC.
- **Spec contable (fuente única):** `_bmad-output/planning-artifacts/valentina-correccion-tc-cartolas-2026-06-20.md` §10.1, §10.2, §11, §12.4, §12.5.
- **Caso de investigación:** `_bmad-output/implementation-artifacts/investigations/tc-desglose-e2e-investigation.md`.
- **Tipo:** quick-dev (cambio acotado sobre core existente; el camino feliz ya funciona).

## Problema (verificado en sandbox, datos reales)

El builder de corrección TC solo contabiliza `operation_type ∈ {compra, cuota, abono, pago}` y
**descarta el resto en silencio** (`else: continue` en `pipeline/importers/tc_correction.py:151`). El
comentario "queda para revisión/discrepancia" es aspiracional — nada lo reporta.

Barrido de 304 cartola.json ya extraídas → lo que se dropea hoy:

| op crudo (Gemini) | #tx | qué es | debe ir a |
|---|---|---|---|
| `None` (sin etiqueta) | **630** | compras sin taggear (Uber Eats, Warner…) | compra (monto +) / abono (monto −) |
| `COMPRAS P.A.T.` / `pat` / `compra_automatica` | 69 | pago automático servicios (Aguas, Enel, Claro) | compra |
| `cargo_automatico` | 7 | suscripciones (Netflix, Colmena) | compra |
| `impuesto` | 21 | timbres DL 3475 | `Expenses:EAG:GastosBancarios-430003` |
| `comision` | 53 | "COBRO ADM MENSUAL" | `Expenses:EAG:GastosBancarios-430003` |
| `nota_credito` | 1 | nota de crédito | abono |

Impacto **doble** por cada línea dropeada (el asiento (a) tiene dos lados): el pasivo `TC:Real` queda
corto Y ese gasto desaparece de los libros. Los 630 `None` son la fuga grande, no los $6.795 de BCI.

## Alcance

### 1. Builder TC — `pipeline/importers/tc_correction.py` (núcleo, mayor valor)
- **Normalizar `operation_type`** antes de despachar (tabla §10.1): sinónimos PAT/automática → `compra`;
  `None` → `compra` si `amount > 0` / `abono` si `< 0`; `nota_credito` → `abono`.
- **Rutear la contrapartida del asiento (a) por tipo:**
  - consumo (`compra`/`cuota`) → `Expenses:<cat>` vía categorizador 9.7 (como hoy).
  - cargo bancario (`impuesto`/`comision`/`interes`/`seguro`/`mantencion`) → **FIJO**
    `Expenses:EAG:GastosBancarios-430003` (global; NO pasa por el 9.7).
  - `avance` → `Assets:EAG:Caja-111001` (CLP) / `Assets:EAG:CajaUs-111003` (USD). NO es gasto.
  - `abono` → compra invertida por signo (§12.2, ya existe).
- **Nunca descartar:** op no reconocida → asiento (a) contra `Expenses:EAG:Suspense` **+ reportar** en el
  `result` (campo nuevo `unmapped: [{line, op, monto}]`). Así `TC:Real = closing` se sostiene SIEMPRE.

### 2. Exponer confianza (para los colores) — `pipeline/importers/categorization/service.py` + builder
- Hoy `predict()` devuelve `(category, match_source, flag)` (línea ~106) y el builder hace
  `category_for(...)[0]` (línea ~308-309), **descartando `match_source` y `flag`/confianza**.
- Cambiar para que el asiento (a) preserve `match_source` + `confidence` en su metadata (para pintar).
- Mapear (confianza, fuente) → color (§10.2): 🟢 `historical-30+`/confianza alta · 🟡 `smart_importer`/
  `historical` pocas/keyword bancario-avance · 🔴 Suspense/Gemini/no reconocido.

### 3. Frontend — página `/categorizacion` (cosmético, puede ir en 2ª pasada)
- Pintar badge de color por ítem; **ordenar rojos arriba**.
- 3 colores (sin naranja). El contador confirma SIEMPRE; nada se auto-confirma.

## Criterio de éxito (verificable — mismo sandbox de la investigación)

Re-correr el import de la cartola BCI 2026-04 (`58431cba-…`, bank_account_id apuntado a
`e919b1db-be7d-430c-9f40-60fc58ae2bcb`) contra una copia sandbox del ledger, sin `IMPORTER_GIT_ENABLED`:

1. `Liabilities:EAG:TC:Real:Tc1027VisaInfinity` cierra en **−3.219.948** (= −closing; HOY da −3.213.153). ✓
2. impuesto ($781) + comisión ($6.014) caen en `Expenses:EAG:GastosBancarios-430003`. ✓
3. Una línea `None` con comercio y monto positivo se contabiliza como `compra`. ✓
4. `result.unmapped == []` para BCI (todo mapeó); cero líneas descartadas en silencio. ✓
5. Suite backend verde, 0 regresiones nuevas (ojo: 2 rojos PRE-EXISTENTES en `test_fava_edit_validator`).

### Setup sandbox (de la investigación, reproducible)
```
cp -r ledger <sandbox>
# parchar <sandbox>/imports/cartolas/_staging/58431cba-….cartola.json:
#   source.bank_account_id = "e919b1db-be7d-430c-9f40-60fc58ae2bcb"
PYTHONUTF8=1 venv/Scripts/python.exe  # (Windows: PYTHONUTF8=1 obligatorio)
#   _build_importer(<sandbox>) → correct_tc_cartola("58431cba-…", importer, <sandbox>)
```

## Decisiones ya tomadas (no re-litigar)
- **Cero cuentas nuevas.** `GastosBancarios-430003`, `Caja-111001`, `CajaUs-111003`, `Suspense` ya
  existen en `ledger/accounts.beancount` (verificado 2026-06-27).
- **GastosBancarios global** (no per-tarjeta; la metadata `bank_account_id` del asiento conserva el detalle).
- **Nada va a automático. El contador confirma siempre.** NO bajar `SUPRA_THRESHOLD` (queda como
  termómetro del color, no como compuerta). NO regla permanente.
- **No tocar el prompt de extracción 9.5** (la normalización es band-aid en el builder; upstream queda
  como limitación conocida §11).
- **3 colores** (verde/amarillo/rojo).

## Notas
- `operation_type` es **libre** en `raw` (sin constraint de schema) → el default seguro (Suspense +
  reportar) es obligatorio, no opcional.
- Validación post-fix recomendada (Valentina o Ary): revisar una corrida real con `None`/PAT para
  confirmar que la normalización por signo no se come ningún caso raro.
