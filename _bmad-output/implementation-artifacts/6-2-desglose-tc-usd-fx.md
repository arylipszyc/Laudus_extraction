# Story 6.2: Corrección contable de Tarjetas de Crédito vía cartola (nacional CLP + internacional USD)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **contador del family office**,
I want que **al importar el estado de cuenta de una tarjeta de crédito (nacional en CLP o internacional en USD), el sistema itemice las compras como gasto real, reclasifique el pago como movimiento entre cuentas, y modele la deuda en una cuenta de pasivo real** — todo con asientos contables nuevos, sin tocar Laudus,
so that **el gasto de tarjeta quede desglosado compra-por-compra y la deuda quede bien contabilizada, cuadrando exacto con lo que Laudus ya registró (el pago lump)**.

> **Diseño base: Valentina (asesora financiera), `valentina-correccion-tc-cartolas-2026-06-20.md`.** Esta story implementa ese flujo. Regla de oro: **NO se toca Laudus ni el importer ni la metadata de cuentas existentes** — la corrección es 100% asientos contables estándar que emite el import de la cartola, como si un contador los ingresara a mano.

## Contexto — por qué las TC necesitan POSTEAR (≠ cuenta corriente)

**Diagnóstico de Valentina (verificado histórico 2021-2022):** Laudus **no registra las compras** de tarjeta — solo el **pago mensual** (`Banco → Expenses:EAG:TC:...`). De 568 movimientos TC, 566 son pagos y 2 compras. El reporte lee el pago lump como "el gasto", sin detalle.

**Por eso TC es distinto de cuenta corriente:**
- **Cuenta corriente** → Laudus tiene cada movimiento → cartola **reconcilia SIN postear** (modelo A, Story 6.1; postear duplicaría).
- **Tarjeta de crédito** → Laudus solo tiene el lump → cartola **SÍ postea** la corrección (itemiza lo que Laudus no tiene). **No hay doble conteo** porque las compras itemizadas no están en Laudus, y el asiento (b) saca el lump-como-gasto.

**~50% de las cartolas reales son internacionales en USD** (revisión de `samples/`: el companion del nacional CLP; compras en el exterior). Hoy ninguna TC se desglosa. Esta story cierra ambos casos.

## El flujo de corrección (3 asientos por tarjeta, al importar su cartola)

Convención de signo Beancount: pasivo = deuda-negativa. [Source: valentina §5-§6]

**(a) Compras itemizadas** — una transacción por línea `raw.operation_type ∈ {compra, cuota}`:
```beancount
Liabilities:EAG:TC:Real:<tarjeta>   -<monto> CLP   ; ↑ deuda real
Expenses:EAG:<categoría>             +<monto> CLP   ; gasto itemizado (categorizador 9.7)
```

**(b) Reclasificación del pago** — por cada línea `raw.operation_type == pago` (la `MONTO CANCELADO`), fechada el mismo mes:
```beancount
Expenses:EAG:TC:<tarjeta>-<code>    -<lump> CLP   ; saca el "gasto" lumpeado que dejó Laudus
Liabilities:EAG:TC:Real:<tarjeta>   +<lump> CLP   ; ↓ deuda real
```
> El pago **ya existe en Laudus** (`Banco → Expenses:EAG:TC:...`). NO se vuelve a tocar el banco; (b) solo reclasifica el gasto falso. El matching (9.6b) debe garantizar que el pago se cuente **una sola vez**.

**(c) Apertura — una sola vez por tarjeta, en su primera cartola:**
```beancount
Liabilities:EAG:TC:Real:<tarjeta>     -<opening> CLP   ; deuda arrastrada de 2025
Equity:Apertura:TarjetasSinDetalle    +<opening> CLP   ; posición inicial — NO gasto
```

**Prueba de no-doble-conteo (suma anual, por tarjeta)** [Source: valentina §7]:
`Σpagos (Laudus lump) − Σpagos (asiento b) + Σcompras (asiento a) + opening→Equity = Σcompras 2026` ✓

## El FX para cartolas USD (regla Ary + Valentina, resuelto 2026-06-22)

Las cartolas internacionales vienen 100% en USD; los asientos (a)/(b)/(c) son en CLP. La conversión:

> **`FX = CLP que SALDA el estado USD ÷ total USD facturado del estado`.** Mismo FX para todas las líneas; estampado en cada transacción.

**El CLP que salda el estado puede venir de dos lados** (corrección Ary 2026-06-22):

- **(i) Pago directo de la TC USD** (caso normal): el lump de Laudus `Banco → Expenses:EAG:TC:...Us` que paga el estado (normalmente el mes siguiente al cierre). `FX = lump_CLP / total_USD`.
- **(ii) Traspaso USD→CLP:** si el contador **no pagó la TC USD directamente** y el monto facturado se pasó a la TC en pesos, en Laudus hay un **movimiento entre la TC USD y la TC CLP**. `FX = CLP que entra a la TC CLP / USD que sale de la TC USD`.

**El `MONTO CANCELADO` interno de la cartola NO se usa para el FX** (ese paga el período anterior). El estado cierra (ej.) 28/04 y se salda ~14/05; esa liquidación de mayo es la del FX. [Valentina §12.1]

**Por qué así y no BCCh:** fuerza `Σ(compras USD × FX) = CLP que salda` → los asientos cuadran exacto contra lo que el banco/contador realmente movió. No es estimación. (Contrasta con `fx_calculator.calculate_fx` de 9.6b = per-línea + BCCh ±5%, que NO sirve acá.)

**Una liquidación, dos roles (sin doble conteo):** la liquidación (pago o traspaso) es el denominador del FX **Y** el evento que reclasifica el asiento (b).

**Timing:** proceso continuo/retrospectivo (2026+) → la liquidación suele estar en Laudus al itemizar. **Si aún no existe** (estado más reciente, antes del vencimiento) → **bloqueante, NO estimar**; esperar al próximo import.

**CLP nacional:** sin FX — montos ya en CLP, asientos (a)/(b)/(c) directos.

## Acceptance Criteria

**AC1 — Ramificar TC vs cuenta corriente.**
Given una cartola con `source.account_type == "tarjeta_credito"`,
Then el flujo de import entra al **modo corrección TC** (postea los asientos a/b/c), NO al modo A de reconciliación-sin-postear (que sigue para `cta_corriente`).

**AC2 — Compras itemizadas (asiento a).**
Given líneas `raw.operation_type ∈ {compra, cuota}`,
Then una transacción por compra: `Liabilities:EAG:TC:Real:<tarjeta>` (−monto) / `Expenses:<categoría>` (+monto). Categoría vía el categorizador real (9.7); sin recomendación → Suspense. Monto en CLP (USD × FX si la cartola es USD).

**AC3 — Reclasificación del pago (asiento b), sin tocar el banco.**
Given líneas `raw.operation_type == pago`,
Then `Expenses:EAG:TC:<tarjeta>-<code>` (−lump) / `Liabilities:EAG:TC:Real:<tarjeta>` (+lump), fechado el mes del pago. NO se postea contra el banco (el pago ya está en Laudus). El pago se cuenta una sola vez (matching).

**AC4 — Apertura una vez (asiento c).**
Given la primera cartola de la tarjeta (sin apertura previa registrada),
Then `Liabilities:EAG:TC:Real:<tarjeta>` (−opening) / `Equity:Apertura:TarjetasSinDetalle` (+opening). Idempotente: no se repite en cartolas siguientes de la misma tarjeta.

**AC5 — FX correcto para USD (regla Ary + Valentina §12.1, dos vías).**
Given una cartola USD,
Then `FX = CLP_que_salda_el_estado / total_USD_facturado` (excl. pago/abono del total USD); cada línea CLP = USD × FX; el FX en la metadata de cada transacción. El CLP que salda viene de **(i)** el pago directo de la TC USD (lump Banco→`...Us`), **o (ii)** el traspaso USD→CLP (movimiento entre la TC USD y la TC CLP: `FX = CLP que entra a TC CLP / USD que sale de TC USD`). `Σ compras CLP == CLP que salda` (con ajuste de redondeo, AC7). **No** se usa el MONTO CANCELADO interno. Sin liquidación aún en Laudus → bloqueante (no inventa FX, no usa BCCh).

**AC8 — Líneas `abono` (Valentina §12.2).**
Given líneas `raw.operation_type == abono` (devoluciones / notas de crédito),
Then asiento espejo invertido de la compra: `Liabilities:EAG:TC:Real:<línea-crédito>` (+monto) / `Expenses:<categoría>` (−monto). USD: mismo FX. Categoría del comercio si el categorizador la pesca, si no Suspense. No se distingue devolución-de-comercio vs nota-de-crédito-de-impuesto.

**AC6 — Cuentas nuevas vía el flujo sancionado.**
Given que faltan las cuentas de pasivo real (metadata `laudus_categoria1: "PASIVO"`) y `Equity:Apertura:TarjetasSinDetalle`,
Then se crean por el flujo de cuentas pendientes (Story 10.3, `_new-accounts-pending` → promover), NO editando metadata existente. **Una `TC:Real` por tarjeta-moneda** (CLP y USD son TC distintas, corrección Ary): `TC:Real:VisaInfinity1027` (CLP) + `TC:Real:VisaInfinity1027Us` (USD), cada una con su pago. Cada cuenta-gasto Laudus reclasifica (asiento b) contra **su** `TC:Real`: `-430005`→`...1027`, `-430006`(Us)→`...1027Us`. Adicionales (card_suffix) dentro de una tarjeta-moneda ruedan a su misma `TC:Real`.

**AC7 — Cuadre + bean-check + sin regresiones.**
Given los asientos,
Then se escriben vía el proceso de import existente (lock + render + `bean-check` + git, patrón `promote`/`commit_reconciliation`); bean-check pasa; el gasto neto de la tarjeta = Σ compras del período (prueba de §7); residuo de redondeo FX **siempre** absorbido en una línea de ajuste, y si `> $1.000 CLP` → bloqueante (ver Decisión 5). Suite completa sin regresiones nuevas. Tarjeta/período sin cartola → intacto (gasto en cuenta TC original).

### Fuera de scope

- Cuenta corriente (modelo A de 6.1, ya hecho).
- Anotar diferencias CLP de cuenta corriente → **Story 6.3**.
- Dashboard polish → **6.4**. Cierre de período → **6.5**.
- Pre-2026 (intacto, espejo Laudus).
- Auditoría de inversiones (otro hilo, `project_inversiones_audit_deferred`).

## Tasks / Subtasks

- [ ] **Task 1 — Cuentas + ramificación TC** (AC1, AC6)
  - [ ] Crear `Liabilities:EAG:TC:Real:<tarjeta>` por tarjeta (metadata `PASIVO`) + `Equity:Apertura:TarjetasSinDetalle` vía el flujo de cuentas pendientes (10.3). Convención de nombre a confirmar (Q).
  - [ ] En `cartolas/service.py`/`reconcile.py`: ramificar por `account_type == "tarjeta_credito"` → modo corrección TC.

- [ ] **Task 2 — FX del statement (solo USD)** (AC5)
  - [ ] Ubicar el lump Laudus del pago de esa tarjeta/período (`load_laudus_entries` sobre `imports/laudus`, cuenta `Expenses:EAG:TC:...Us-43000X`). **Q1 (timing):** definir qué pago Laudus corresponde a qué cartola (el pago que salda el statement aparece ~1 mes después del cierre; la `MONTO CANCELADO` de la cartola es el pago del período ANTERIOR — ver Dev Notes).
  - [ ] `FX = lump_CLP / total_USD_facturado`. Sin lump → bloqueante.
  - [ ] CLP nacional: saltear FX.

- [ ] **Task 3 — Emitir asientos (a)/(b)/(c)** (AC2, AC3, AC4)
  - [ ] (a) compra/cuota → tx por línea (CLP o USD×FX). Categoría vía categorizador 9.7.
  - [ ] (b) pago → reclasificación; matchear con el lump Laudus para no doble-contar.
  - [ ] (c) opening → Equity, una vez por tarjeta (idempotente; chequear si ya hay apertura).
  - [ ] **abono** (`raw.operation_type == abono`, devoluciones): definir (reduce deuda + revierte gasto). Ver gap en Dev Notes.

- [ ] **Task 4 — Escritura + cuadre** (AC7)
  - [ ] Proceso de import existente (lock + render + bean-check + git). Sin `Balance` directive.
  - [ ] Ajuste de redondeo FX si `Σ compras CLP ≠ lump` (umbral a definir, ≤ unos pesos).

- [ ] **Task 5 — Tests** (AC7)
  - [ ] Fixture: cuenta TC original (Expenses) + lump Laudus + cuenta TC:Real + cartola TC (CLP y USD). Verificar: asientos a/b/c, FX, suma anual (§7), opening idempotente, bean-check verde, sin-lump→bloqueante, abono. Shape de cartola USD basado en `_bmad-output/validation-runs/` (fixture sintético, no datos reales — `samples/README.md`).

## Dev Notes

### Datos verificados (2026-06-22)

- **Cartola USD shape:** canónico V1, `currency:"USD"`, balances USD; `raw.operation_type ∈ {compra(90), abono(2), pago(1)}`; `raw` tiene `operation_type`, `merchant_country`, `merchant_state`. `MONTO CANCELADO` → `operation_type:"pago"`, monto negativo (= −opening).
- **Laudus TC int'l = lump CLP:** `Assets:Bancos −X` / `Expenses:EAG:TC:...Us-43000X +X`, un asiento por pago. Verificado `ledger/imports/laudus/2026-*.beancount`.
- **Cuentas TC:** `Expenses:EAG:TC:Tc{last4}{Nombre}-43000X` (nacional) + `...Us-43000X` (internacional), declaradas CLP (Amex 430011 = `CLP, USD`). Son `Expenses` (reclasif 2026-06-20, `docs/handoff-tc-gasto-2026-06-20.md`).

### ✅ `card_suffix` — resuelto (Valentina §12.3): no bloquea

Valentina §10 asumía separar por tarjeta física vía `card_suffix`. **Decisión:** la deuda es **una por línea de crédito** (unifica nacional+USD+adicionales), así que las tarjetas adicionales (6669/6047/9149) **ruedan a la misma `TC:Real`** — NO se necesita cuenta por suffix. `card_suffix` queda como **metadata opcional** en la tx para drill-down en Fava; su ausencia hoy **no bloquea** la story y NO obliga a tocar el prompt/schema de 9.5.

### ✅ `abono` — resuelto (Valentina §12.2): espejo invertido

`operation_type == abono` (devoluciones / notas de crédito) → asiento espejo de la compra con signo invertido (`TC:Real +` / `Expenses −`). No distinguir devolución-de-comercio vs nota-de-crédito-de-impuesto (finanzas personales). Ver AC8.

### ✅ Timing del FX / matching pago↔statement — resuelto (Valentina §12.1)

El FX sale del **lump de Laudus que PAGA el estado** (el pago del mes siguiente que salda el cierre), no del `MONTO CANCELADO` interno (que paga el período anterior). Unidad de matching = (estado) ↔ (lump que lo paga); ese lump es FX-denominador **y** asiento (b), un solo evento. Si el lump aún no está en Laudus → bloqueante, no estimar. Ver la sección "El FX para cartolas USD".

### Piezas a reusar (NO reescribir)

| Pieza | Ubicación | Uso |
|---|---|---|
| `load_laudus_entries` | [matching_engine.py:59](pipeline/importers/matching_engine.py#L59) | ubicar el lump Laudus |
| `commit_reconciliation` / patrón `promote` | [reconcile.py:179](pipeline/importers/reconcile.py#L179) / [cartola_pdf_importer.py:216](pipeline/importers/cartola_pdf_importer.py#L216) | lock+render+bean-check+rollback+git |
| `_build_postings` / `build_usd_postings` | [cartola_pdf_importer.py:45](pipeline/importers/cartola_pdf_importer.py#L45) | postings (ojo signo) |
| categorizador real | [categorization/service.py](pipeline/importers/categorization/service.py) | categoría de cada compra (asiento a) |
| flujo cuentas pendientes | Story 10.3, `_new-accounts-pending.beancount` | crear `TC:Real` + `Equity:Apertura` |
| `reconcile_cartola` (6.1) | [reconcile.py](pipeline/importers/reconcile.py) | punto de ramificación (cta corriente vs TC) |

### Convención de signo

TC ahora `Expenses` → el asiento (b) saca de `Expenses:EAG:TC:<code>` (no de Liabilities). La deuda real va a `Liabilities:EAG:TC:Real:*` (deuda-negativa). Verificar con bean-check real.

### Testing standards

- pytest `backend/tests/`, `PYTHONUTF8=1`, venv `./venv/Scripts/python.exe`. bean-check real (beancount.loader) = gate. Fixture USD basado en shape de validation-runs (sintético, sin datos personales).

### References

- [Source: _bmad-output/planning-artifacts/valentina-correccion-tc-cartolas-2026-06-20.md] — **el diseño base** (flujo a/b/c, prueba §7, cuentas §9, mapeo §10, pendientes §11).
- [Source: _bmad/memory/agent-contadora/MEMORY.md] — diagnóstico TC, decisión de diseño.
- [Source: ledger/imports/laudus/2026-*.beancount, ledger/accounts.beancount] — lump CLP, cuentas `...Us`.
- [Source: samples/ + _bmad-output/validation-runs/] — cartolas reales (CLP nacional + USD internacional).
- [Source: pipeline/importers/fx_calculator.py] — el FX per-línea (contraste; NO sirve acá).
- [Source: 6-1-wiring-promote-reconcile.md] — modelo A (cta corriente), el SEAM, `reconcile_cartola`.
- [Source: memoria project_tc_pasivo_dos_estados] — modelo de dos estados.

## Decisiones de diseño (resueltas 2026-06-22 — Valentina + Ary)

Las 5 preguntas abiertas quedaron cerradas. Detalle contable en `valentina-correccion-tc-cartolas-2026-06-20.md §12`.

1. ✅ **Timing del FX / matching** — FX de la **liquidación que SALDA el estado** (mes siguiente), no del MONTO CANCELADO. Dos vías: pago directo de la TC USD, o traspaso USD→CLP (FX = CLP que entra a TC CLP / USD que sale de TC USD). La liquidación es FX-denominador + asiento(b). Sin liquidación aún → bloqueante. [Valentina §12.1, corrección Ary]
2. ✅ **`card_suffix`** — NO se necesita; las adicionales (dentro de una tarjeta-moneda) ruedan a su `TC:Real`. Suffix = metadata opcional, no toca el prompt 9.5. [Valentina §12.3]
3. ✅ **`abono`** — espejo invertido de la compra (`TC:Real +` / `Expenses −`), mismo FX, sin distinguir impuesto vs devolución. [Valentina §12.2 / AC8]
4. ✅ **Nombre `TC:Real` (corrección Ary 2026-06-22)** — **CLP y USD son TC distintas, cada una con su pago**: `TC:Real:<Producto>` (CLP) + `TC:Real:<Producto>Us` (USD). Cada cuenta-gasto Laudus reclasifica contra su propia `TC:Real` (`-430005`→`...1027`, `-430006`Us→`...1027Us`). NO unificar. [supersede la propuesta de Valentina §12.3]
5. ✅ **Redondeo del FX** (decisión técnica) — `Σ(compras redondeadas a peso × FX)` puede diferir del lump por unos pesos (ruido de redondeo per-línea, ~$0.5 × N líneas ≈ máx ~$50 en 90 líneas). **Siempre** absorber el residuo en una línea de ajuste (`Expenses:EAG:TC:AjusteRedondeoFX` o similar) para que cuadre exacto. Si el residuo **> $1.000 CLP** (más de lo que el redondeo explica) → **bloqueante** (señal de que el lump o el total USD no corresponden, no es redondeo).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m]

### Debug Log References

- 2026-06-22: backbone de asientos implementado (`tc_correction.build_tc_correction_entries`) + 6 tests verde (bean-check real). HALT en la derivación del FX USD (Task 2) — ver Completion Notes.

### Completion Notes List

- **Backbone (Task 3 núcleo) DONE:** `pipeline/importers/tc_correction.py` — builder PURO que emite
  los asientos (a) compra/cuota, abono (espejo vía amount firmado), (b) pago (reclasifica el lump
  fuera de `Expenses:EAG:TC:<code>` sin tocar el banco), (c) apertura → `Equity:Apertura:TarjetasSinDetalle`
  una vez. `fx` + `lump_for` + `category_for` inyectables (FX=1 para CLP). 6 tests
  (`backend/tests/test_tc_correction.py`) verdes con bean-check real, incl. prueba de no-doble-conteo
  §7 (Expenses:TC neteado a 0, gasto = compras − abonos).
- **⏸️ HALT en Task 2 (derivación del FX USD) — requiere confirmar el algoritmo de matching con Ary.**
  El backbone toma `fx` y `lump_for` ya resueltos. Falta la pieza que, para una cartola USD,
  identifica en Laudus la **liquidación que salda ese estado** (pago directo a `...Us` o traspaso
  USD→CLP) para calcular `FX = CLP_que_salda / total_USD` y los lumps de (b). Es lo que la story
  marca como "lo más delicado": el desfase de ~1 mes + el caso traspaso tienen ambigüedad de
  algoritmo que, mal resuelta, corrompe el cuadre validado vs el contador. Pendiente de decisión.

### File List

- `pipeline/importers/tc_correction.py` (NUEVO — builder de asientos de corrección TC)
- `backend/tests/test_tc_correction.py` (NUEVO — 6 tests, bean-check real)
