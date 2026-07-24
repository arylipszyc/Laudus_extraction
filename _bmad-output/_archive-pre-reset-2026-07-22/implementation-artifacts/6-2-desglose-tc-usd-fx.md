# Story 6.2: Corrección contable de Tarjetas de Crédito vía cartola (nacional CLP + internacional USD)

Status: done

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

**⚠️ CORRECCIÓN post-revisión Valentina (2026-06-22) — supersede el framing "una liquidación, dos roles del mismo estado":** cada estado USD tiene DOS pagos distintos, y son DOS pagos Laudus diferentes:
- **Liquidación del estado** (pago del mes siguiente, glosa USD == `closing`) → **denominador del FX** de ESTE estado.
- **`MONTO CANCELADO`** (línea interna, salda el período ANTERIOR) → **asiento (b)** de ESTE estado.

Un mismo pago `Pay_M` juega los dos roles pero en estados **ADYACENTES**: denominador del FX del estado M−1 (lo salda) y asiento (b) del estado M (es su `MONTO CANCELADO`). El modelo MONTO-CANCELADO es el que mantiene el cuadre anual §7 (cancela exactamente los lumps Laudus de 2026, uno cada uno); el modelo "liquidación del propio estado" dejaría el pago de enero sin cancelar y cancelaría uno de 2027 → rompe la paridad vs el contador. Detalle en `valentina-correccion-tc-cartolas-2026-06-20.md §12.1`.

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
Given líneas `raw.operation_type == pago` (la línea `MONTO CANCELADO`, que salda el período ANTERIOR),
Then `Expenses:EAG:TC:<tarjeta>-<code>` (−lump) / `Liabilities:EAG:TC:Real:<tarjeta>` (+lump), fechado el mes del pago. NO se postea contra el banco (el pago ya está en Laudus). El pago se cuenta una sola vez (matching). **El `lump` es el CLP REAL del pago Laudus que matchea (por glosa USD) el USD de ESA línea `MONTO CANCELADO` — NUNCA `MONTO_CANCELADO_USD × FX_del_estado`** (se liquidó al FX del estado anterior; usar el FX actual dejaría `Expenses:EAG:TC:<code>` sin netear a 0 → residual de gasto falso). Mismo glosa-matching que el FX, pero sobre el USD de la línea.

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
Given que faltan las cuentas de pasivo real y `Equity:Apertura:TarjetasSinDetalle`,
Then se crean por el flujo de cuentas pendientes (Story 10.3, `_new-accounts-pending` → promover), NO editando metadata existente. **Una `TC:Real` por tarjeta-moneda** (CLP y USD son TC distintas, corrección Ary). El nombre copia el **stem EXACTO** de la cuenta-gasto Laudus (decisión Ary 2026-06-22, supersede `VisaInfinity1027`): `Tc1027VisaInfinity` (CLP) + `Tc1027VisaInfinityUs` (USD). Cada cuenta-gasto Laudus reclasifica (asiento b) contra **su** `TC:Real` vía transformación de string pura `Expenses:EAG:TC:<X>-<code>` → `Liabilities:EAG:TC:Real:<X>`. Adicionales (card_suffix) dentro de una tarjeta-moneda ruedan a su misma `TC:Real`.

**Lista exacta (confirmada Valentina 2026-06-22 contra `accounts.beancount` + actividad 2026) — 8 `TC:Real` + Equity:** `Tc1027VisaInfinity`/`…Us` (430005/06), `Tc8996MastercardLanpass`/`…Us` (430007/08), `Tc0858VisaLatanpass`/`…Us` (430009/10), `TcVariasEag` (430017, CLP), `TcRaquelVentura` (430019, CLP) + `Equity:Apertura:TarjetasSinDetalle`. **Skip Amex 8083 (430011): cero actividad 2026.** `TcVariasEag` se crea pero queda en lump (cajón de varias físicas, sin cartola única).

**⚠️ Metadata — el label PASIVO NO basta (hallazgo Valentina):** el reporte agrupa el gasto por **`Categoria2`**, no por `Categoria1`. Lo que saca una cuenta del gasto es tener **`laudus_categoria2` y `laudus_categoria3` VACÍOS**. TRAP: las TC originales son `categoria2:"GASTOS PERSONALES"`/`categoria3:"Tarjetas Credito"`; si se copia ese metadata y solo se cambia `Categoria1`, la `TC:Real` IGUAL suma al gasto. Cada cuenta nueva: `Categoria1` no-vacío (`PASIVO` para TC:Real, `PATRIMONIO` para Equity — evita el guard "sin categorizar" 10.2) + `Categoria2`/`Categoria3` **vacíos** + un `code` sintético en rango no-gasto (2xxxxx pasivo / 3xxxxx patrimonio; sin `code` los postings colisionan en `accountnumber=""` y afloran como línea fantasma en el reporte). Ver `valentina-correccion-tc-cartolas-2026-06-20.md §9`.

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

- [x] **Task 1 — Cuentas + ramificación TC** (AC1, AC6)
  - [x] ~~Crear cuentas vía 10.3~~ → **HANDOFF Ary (no codeable):** sembrar las 8 `TC:Real` + `Equity:Apertura:TarjetasSinDetalle` (metadata §9: `Categoria1` no-vacío, `Categoria2/3` vacíos, `code` sintético) vía el flujo de cuentas pendientes (10.3), y poblar `bank_account_id` en las cuentas-gasto `...Us`. El código deriva `TC:Real` del stem (`tc_real_account`), no edita metadata existente.
  - [x] `cartolas/service.py::validate_balance`: ramifica por `account_type == "tarjeta_credito"` → `correct_tc_cartola` (postea); `cta_corriente` sigue en modelo A (reconcilia sin postear).

- [x] **Task 2 — FX del statement (solo USD)** (AC5) — ya hecho en el checkpoint previo.
  - [x] `derive_statement_fx` ubica el pago Laudus que salda el estado (glosa USD == closing) sobre la cuenta-gasto `...Us` (`load_laudus_entries`, ventana 75d tras el cierre). `FX = lump_CLP / USD_glosa`. Sin pago que cuadre → bloqueante.
  - [x] CLP nacional: `fx = 1` (saltea FX).

- [x] **Task 3 — Emitir asientos (a)/(b)/(c)** (AC2, AC3, AC4, AC8)
  - [x] (a) compra/cuota + abono (espejo vía amount firmado) → tx por línea (CLP o USD×FX). Categoría vía `importer.category_predictor` (seam 9.7; Noop→Suspense).
  - [x] (b) pago → reclasificación; lump USD resuelto por glosa del `MONTO CANCELADO` (`_resolve_usd_lump`), CLP = magnitud de la línea. No doble-conteo probado (§7).
  - [x] (c) opening → Equity, idempotente (`_opening_exists` escanea `*-tc.beancount` previos).

- [x] **Task 4 — Escritura + cuadre** (AC7)
  - [x] `correct_tc_cartola` escribe a `imports/cartolas/{slug}-tc.beancount` (lock + render + bean-check + rollback + git, patrón `promote`). Sin `Balance` directive.
  - [x] Cuadre USD: residuo `> $1.000` → bloqueante. **Decisión Ary 2026-06-23: NO se redondea** — los montos por línea se guardan con precisión completa (2+ decimales, aunque el UI muestre CLP:1), así `Σ(compras × fx) = closing × fx = lump` EXACTO. Esto **elimina** el residuo de redondeo y por lo tanto la línea de ajuste `Expenses:AjusteRedondeoFX` de AC7/Decisión 5 (no hace falta crear esa cuenta). El check `> $1.000` sobrevive solo como detector de descuadre REAL (lump/total no corresponden).

- [x] **Task 5 — Tests** (AC7) — `backend/tests/test_tc_correction.py` (17 tests, bean-check real).
  - [x] `tc_real_account`, CLP e2e, USD e2e, opening idempotente, FX sin-pago→bloqueante, descuadre>umbral→bloqueante, ruteo `validate_balance`→corrección. (builder + FX ya cubiertos en el checkpoint).

### Review Findings (code review 2026-06-23 — 3 capas adversariales)

**Patches (fix no ambiguo):**

- [x] [Review][Patch] Cuadre `residuo` falla-positivo y no valida el lump — `residuo = settling_lump − purchased_clp = fx×(opening − |Σpagos|)`, solo ~0 si la tarjeta se paga al contado; arrastrar saldo bloquea un estado correcto, y como `settling_lump` se deriva del mismo fx, el check nunca detecta un lump errado. **Resolución (Ary 2026-06-23): asumir pago al contado + reemplazar el check por cross-check del FX derivado vs BCCh del mes (±5%, reutiliza `fx_calculator.lookup_bcch`/`calculate_fx`).** El FX SIGUE saliendo del pago (`lump/closing`, regla §12.1 "NO usar BCCh como tasa"); BCCh es solo gate de cordura. Sin BCCh ese mes → no bloquea (igual que 9.6b). [tc_correction.py:307-317]
- [x] [Review][Patch] `_opening_exists` escanea el archivo que está por sobrescribir → re-importar la PRIMERA cartola de la tarjeta pierde su propia apertura (silencioso, bean-check verde). Excluir el `out_file` destino del glob. [tc_correction.py:198,297,328]
- [x] [Review][Patch] Colisión de slug: dos tarjetas distintas (sobre todo CLP `<Producto>` + USD `<Producto>Us` que comparten last4, o `last4=None→'xxxx'`) del mismo banco/mes → mismo `{slug}-tc.beancount` → sobrescritura silenciosa. Desambiguar el slug por stem de cuenta / moneda. [tc_correction.py:327]

**Deferidos (reales, no críticos ahora):**

- [x] [Review][Defer] Vía (ii) traspaso USD→CLP NO implementada — `derive_statement_fx` solo busca pago directo `Banco→...Us` (spec §12.1 lista DOS vías). Un estado saldado por traspaso queda bloqueado (seguro: avisa, no corrompe). **Decisión Ary 2026-06-23: story propia** — falta un traspaso real para confirmar dónde vive el USD (glosa vs posting USD); implementar sin caso real arriesga FX silenciosamente errado. [tc_correction.py:232,266] — deferred
- [x] [Review][Defer] Regex de glosa frágil: `USD\s*([\d.]*\d,\d{2})` exige coma+2 decimales y `.search` toma el primer token → glosas sin centavos o con múltiples USD no matchean → bloqueo falso (falla segura). [tc_correction.py:52] — deferred
- [x] [Review][Defer] `_resolve_usd_lump`/`derive_statement_fx` eligen el primer match por orden de archivo, sin desempate por fecha más cercana → dos pagos con el mismo USD en la ventana atan el lump CLP equivocado. [tc_correction.py:219,84] — deferred
- [x] [Review][Defer] Camino CLP: asiento (b) usa `lump = abs(línea)` SIN verificar contra el pago CLP real de Laudus → si difieren (comisiones/parcial) queda un residual falso-gasto silencioso en `Expenses:EAG:TC:<code>` (rompe §7). Supuesto documentado del dev. [tc_correction.py:291] — deferred
- [x] [Review][Defer] `validate_balance` devuelve dos esquemas de respuesta incompatibles discriminados solo por `account_type` (TC: purchases/residuo… vs reconcile: differences/matched) — verificar que el frontend maneje la forma TC. [service.py:472] — deferred
- [x] [Review][Defer] EUR (enum válido) se rutea al branch USD vía `is_usd = currency != 'CLP'` → siempre bloqueado con mensaje USD engañoso; agregar guard explícito de moneda no soportada. [tc_correction.py:259] — deferred

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

1. ✅ **Timing del FX / matching** — FX de la **liquidación que SALDA el estado** (mes siguiente, glosa USD == closing), no del MONTO CANCELADO. Dos vías: pago directo de la TC USD, o traspaso USD→CLP (FX = CLP que entra a TC CLP / USD que sale de TC USD). **El asiento (b) NO sale de esa liquidación: sale del `MONTO CANCELADO` del propio estado, matcheado por glosa a SU pago Laudus (lump = CLP real, no USD×FX).** Son dos pagos Laudus distintos en estados adyacentes (ver corrección post-revisión arriba). Sin liquidación aún → bloqueante. [Valentina §12.1, corrección Ary + revisión 2026-06-22]
2. ✅ **`card_suffix`** — NO se necesita; las adicionales (dentro de una tarjeta-moneda) ruedan a su `TC:Real`. Suffix = metadata opcional, no toca el prompt 9.5. [Valentina §12.3]
3. ✅ **`abono`** — espejo invertido de la compra (`TC:Real +` / `Expenses −`), mismo FX, sin distinguir impuesto vs devolución. [Valentina §12.2 / AC8]
4. ✅ **Nombre `TC:Real` (corrección Ary 2026-06-22)** — **CLP y USD son TC distintas, cada una con su pago**: `TC:Real:<Producto>` (CLP) + `TC:Real:<Producto>Us` (USD). Cada cuenta-gasto Laudus reclasifica contra su propia `TC:Real` (`-430005`→`...1027`, `-430006`Us→`...1027Us`). NO unificar. [supersede la propuesta de Valentina §12.3]
5. ✅ **Redondeo del FX** (decisión técnica) — `Σ(compras redondeadas a peso × FX)` puede diferir del lump por unos pesos (ruido de redondeo per-línea, ~$0.5 × N líneas ≈ máx ~$50 en 90 líneas). **Siempre** absorber el residuo en una línea de ajuste (`Expenses:EAG:TC:AjusteRedondeoFX` o similar) para que cuadre exacto. Si el residuo **> $1.000 CLP** (más de lo que el redondeo explica) → **bloqueante** (señal de que el lump o el total USD no corresponden, no es redondeo).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m]

### Debug Log References

- 2026-06-22: backbone de asientos implementado (`tc_correction.build_tc_correction_entries`) + 6 tests verde (bean-check real).
- 2026-06-22: HALT del FX resuelto consultando datos reales — la glosa del pago Laudus trae el USD + período (ej. "USD26.188,93 Visa BCI 1027 Abril" = 23.543.848 CLP, y ese USD == closing de la cartola). Ary confirmó: FX de la glosa + validar cuadre, si no cuadra → bloqueante (falta movimiento/error). `derive_statement_fx` + `parse_glosa_usd` implementados + 4 tests (10 total verde).
- 2026-06-23: orquestador `correct_tc_cartola` + ramificación `validate_balance` + idempotencia apertura + cuadre. 17 tests verde (bean-check real). Suite 555 passed/1 xfailed; 2 rojos PRE-EXISTENTES (test_fava_edit_validator, confirmados en HEAD limpio vía stash), 0 regresiones nuevas. Story → review.

### Change Log

- 2026-06-23: cierre del dev de 6.2 — orquestador TC (postea a/b/c), ramificación TC vs cuenta corriente, idempotencia de apertura, cuadre con bloqueo >$1.000. Migrado `test_validate_balance` a `cta_corriente` (modelo A = cuenta corriente tras AC1).
- 2026-06-23 (decisión Ary): se elimina el redondeo per-línea (precisión completa) → `Σ(compras × fx) = lump` exacto, sin residuo ni línea de ajuste `AjusteRedondeoFX`. Supersede Decisión 5 / AC7-redondeo. Suite 555 passed, 0 regresiones nuevas.

### Completion Notes List

- **Backbone (Task 3 núcleo) DONE:** `pipeline/importers/tc_correction.py` — builder PURO que emite
  los asientos (a) compra/cuota, abono (espejo vía amount firmado), (b) pago (reclasifica el lump
  fuera de `Expenses:EAG:TC:<code>` sin tocar el banco), (c) apertura → `Equity:Apertura:TarjetasSinDetalle`
  una vez. `fx` + `lump_for` + `category_for` inyectables (FX=1 para CLP). 6 tests
  (`backend/tests/test_tc_correction.py`) verdes con bean-check real, incl. prueba de no-doble-conteo
  §7 (Expenses:TC neteado a 0, gasto = compras − abonos).
- **FX USD (Task 2) DONE:** `derive_statement_fx` busca en Laudus el pago de la cuenta `...Us`
  (ventana 75d tras el cierre) cuya **glosa codifica el mismo USD que el `closing`** del estado;
  `FX = CLP_pago / USD_glosa`. Si ningún pago cuadra → bloqueante (falta movimiento/error, NO estima
  FX — decisión Ary). `parse_glosa_usd` parsea el formato chileno "USD26.188,93". 4 tests.
- **HALLAZGO durante el FX (subtleza cross-período):** la línea `MONTO CANCELADO` de un estado paga el
  período ANTERIOR; su lump (para el asiento b) es el pago Laudus que matchea **el USD de esa línea**,
  no el del closing. Es la misma regla de glosa aplicada al pago. A wirear en el orquestador.
- **✅ Orquestador + wiring DONE (sesión 2026-06-23) — Tasks 1, 3-final, 4:**
  - `correct_tc_cartola(batch_id, importer, root, *, ts)` en `tc_correction.py`: resuelve `expense_tc`
    (resolver) → `tc_real_account()` deriva `TC:Real:<stem>` (string puro, AC6), calcula FX (USD vía
    `derive_statement_fx`) o 1 (CLP), pre-resuelve el lump de cada `MONTO CANCELADO` por glosa
    (`_resolve_usd_lump`; sin match → bloqueante), llama al builder, valida cuadre, escribe a
    `imports/cartolas/{slug}-tc.beancount` (lock + bean-check + rollback + git, patrón `promote`).
  - **Idempotencia de la apertura:** `_opening_exists()` escanea los `*-tc.beancount` ya escritos por
    una Transaction con `operation_type=apertura` que toque la `TC:Real` → no repite (AC4).
  - **Ramificación:** `validate_balance` (service.py) bifurca por `account_type` —
    `tarjeta_credito`→`correct_tc_cartola` (postea); `cta_corriente`→`reconcile_cartola` (modelo A 6.1).
  - **Cuadre (USD):** `residuo = CLP_que_salda − Σ(compras×fx)`. `>$1.000` → bloqueante (lump/total no
    corresponden). Sub-umbral = ruido de redondeo per-línea (~$50 en 90 líneas).
- **✅ AC7 — redondeo RESUELTO (decisión Ary 2026-06-23): no se redondea.** En vez de absorber un residuo
  de redondeo en una línea `Expenses:AjusteRedondeoFX`, los montos por línea se guardan con **precisión
  completa** (se quitó todo `.quantize()` del builder y del cuadre). Como `fx = lump / closing`, entonces
  `Σ(compras × fx) = closing × fx = lump` exacto → **no hay residuo de redondeo** (verificado: `residuo`
  ≈ 0 en el test USD e2e). Beneficios: gasto reportado = Σ compras exacto, no se crea la cuenta
  `AjusteRedondeoFX`, y respeta la regla de oro (precisión en el valor; el redondeo de Fava es solo
  display, `CLP:1`). El check `> $1.000` queda como detector de descuadre real (lump/total no
  corresponden), no de redondeo. **Decisión 5 del storyfile queda superseded por esto.**
- **Handoff de prod (no codeable):** (1) `bank_account_id` en las cuentas-gasto `...Us` (sin esto el
  resolver no mapea la cartola USD); (2) sembrar las 8 `TC:Real` + `Equity:Apertura:TarjetasSinDetalle`
  vía 10.3 con la metadata del §9; (3) **wirear el categorizador real (9.7)** en `_build_importer` —
  hoy crea el importer con `NoopCategoryPredictor`, así que en prod las compras caen a `Suspense` (safe
  default; el contador las revisa) hasta que se inyecte `CategorizationService`.
- **CLP — supuesto:** el lump del asiento (b) = magnitud de la línea `MONTO CANCELADO` (asume
  cartola==Laudus para el pago CLP, mismo evento/moneda). No matchea contra Laudus (sí lo hace USD).

### File List

- `pipeline/importers/tc_correction.py` (builder de asientos + FX desde glosa + **orquestador
  `correct_tc_cartola`, `tc_real_account`, `_opening_exists`, `_resolve_usd_lump`**)
- `backend/app/api/v1/cartolas/service.py` (`validate_balance`: ramifica `tarjeta_credito`→corrección TC)
- `backend/tests/test_tc_correction.py` (17 tests, bean-check real — builder/FX + orquestador e2e)
- `backend/tests/test_validate_balance.py` (fixture migrado a `cta_corriente`: modelo A = cuenta
  corriente tras la ramificación AC1; la TC tiene su propio flujo)
