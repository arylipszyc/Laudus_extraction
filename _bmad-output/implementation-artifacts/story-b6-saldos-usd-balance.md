# Story B6: Saldos USD invisibles en el balance (valorización de cierre en presentación)

Status: draft

<!-- Gated: las 2 decisiones abiertas de Valentina (§ Preguntas para Ary) + hacer ANTES de cargar el primer saldo USD-nativo. No pasar a dev-story hasta que Ary confirme Q1/Q2 o decida cargar el primer saldo real. -->

## Story

As a **dueño / contador del family office**,
I want **que las cuentas con saldo en USD-nativo (bancos e inversiones en dólares) aparezcan en el balance con su equivalente en CLP al dólar de cierre del período, mostrando además el monto USD original y el fx aplicado por línea**,
so that **cuando pregunte "¿cuánta plata tengo?" el balance sume esos activos en pesos (hoy colapsarían a cero = un activo real que desaparece del patrimonio) y, a la vez, pueda ver "¿cuánto de lo mío está en dólares?" (exposición cambiaria) sin inventar un número que rompa el espejo con Laudus**.

> **Contexto — bug LATENTE, no urgente pero grave cuando dispare.** Hoy hay **0 postings con unidades USD** en el ledger: todas las cartolas TC-USD se guardan ya convertidas a CLP con `fx:` en metadata (doctrina TC intacta, ver más abajo). El defecto se dispara cuando entren los **saldos USD-nativos de banco/inversión** de estas 5 cuentas (`valentina-tratamiento-saldos-usd-balance-2026-07-08.md` §1):
>
> | Cuenta | Tipo |
> |---|---|
> | `Assets:EAG:Bancos:BancoBci18565743Us` | cta corriente USD |
> | `Assets:EAG:Bancos:BancoBci110014172UsMiami` | cta corriente USD |
> | `Assets:EAG:Bancos:BancoCityNBank30000771265` | cta corriente USD |
> | `Assets:EAG:Inversiones:BancoJuliusBaer03133171` | inversión USD |
> | `Assets:Jocelyn:Inversiones:FmBciDlarCash` | inversión USD (hija) |
>
> Si se carga un saldo USD-nativo **sin este fix**, `_clp()` ([bql_queries.py:46-53](backend/app/services/bql_queries.py#L46)) lo colapsa a `0.0` → el activo sale en cero en el balance = **descuadre silencioso** (no un redondeo cosmético). **El fix debe estar antes del primer saldo USD.**

> **Veredicto contable autoritativo:** `_bmad-output/planning-artifacts/valentina-tratamiento-saldos-usd-balance-2026-07-08.md`. Esta story materializa su recomendación **HÍBRIDO (b)+(a)**.

## Alcance / decisiones de diseño

### La política contable (del veredicto §4) — no re-litigar

1. **El ledger guarda el saldo en unidades USD-nativas** (NO se convierte al importar). Para un activo vivo no hay pago del cual derivar un fx, y convertir al importar **congela** el valor al dólar del mes de carga y nunca lo revaloriza. Un activo de mercado debe reflejar la exposición de *cada* fecha de balance.
2. **La conversión a CLP ocurre en la capa de PRESENTACIÓN** (la query del balance), aplicando el **dólar observado BCCh de fin del mes de la fecha del balance** (`rate_clp_per_usd` de `ledger/_meta/fx-bcch-eom.jsonl`; ej. balance al 31-05-2026 → 892,89). La misma cuenta se revaloriza sola al consultar distintos cierres — que es lo que un activo de mercado debe hacer.
3. **Presentación dual:** columna **"Saldo (CLP)"** que totaliza el balance (el family office se lee en pesos) **+ detalle nativo** por línea USD: `US$ X · fx Y · = CLP Z`. El número cuadra, la exposición cambiaria queda visible, y cada CLP es auditable.

### Por qué presentación y no conversión al importar (decisión arquitectónica, veredicto §4)

El ledger debe seguir siendo **espejo fiel de Laudus**, y Laudus **no revaloriza** (0 price directives — mismo hallazgo de la auditoría de inversiones 2026-06-20). Convertir al importar y guardar CLP estamparía una revalorización que Laudus no hizo y rompería el espejo. Guardando USD-nativo y convirtiendo al leer, el ledger no inventa nada y el balance muestra el equivalente CLP de cierre como **cálculo de presentación, no como asiento.**

### Diferencia de cambio: se MUESTRA, no se BOOKEA (veredicto §5)

Un activo USD valorizado al dólar de cierre cambia su valor en CLP cada período aunque no entre ni salga un dólar (ej.: US$100.000 quietos valen CLP 93.157.000 a marzo / CLP 89.289.000 a mayo = pérdida de presentación de CLP 3.868.000 sin que se movió nada). Eso es **diferencia de cambio no realizada.**

- **NO se reconoce como asiento** (no se bookea ganancia/pérdida de cambio en el ledger). Bookearla rompería el espejo-Laudus e inflaría/desinflaría un P&L que el contador no reconoce → descuadraría la paridad.
- Con el modelo de presentación, la dif. de cambio **aparece sola** en el total CLP moviéndose período a período. Se **muestra**, no se **postea** — hasta que Laudus/el contador la reconozca y entonces la **espejamos**, no la anticipamos.

### Activo USD vivo ≠ deuda TC en USD (veredicto §2 — la distinción fina)

**NO tocar el tratamiento de la deuda TC en USD.** La deuda TC se sigue guardando en CLP al **fx del pago que la salda** ("el fx sale del pago que lo salda; sin pago no se estima") — doctrina cerrada en `valentina-story-brief-fx-revolving-tc-usd-2026-07-06.md` y en la story 6.6. El principio que separa los dos casos: *¿hay un evento de caja que fija el CLP (→ deuda TC, CLP real) o es una posición de mercado abierta (→ activo USD vivo, dólar de cierre BCCh)?* B6 es **solo** para los activos USD-nativos de banco/inversión. No hay conflicto: son los dos lados de la misma regla.

### Fuera de scope (explícito)

- **Deuda TC en USD** (`Liabilities:EAG:TC:Real:*Us`) — se queda en CLP al fx del pago. No se toca (§2).
- **Bookear un asiento de diferencia de cambio** — prohibido por §5 hasta que Laudus la reconozca.
- **Cargar los saldos USD reales** — es el trigger que destapa el bug, pero la carga en sí (de dónde salen los saldos, cómo se importan) es trabajo aparte. B6 hace el motor de presentación **correcto** para cuando lleguen.
- **`paritytomaincurrency: 1.0` en el reporte de gastos / ledger** ([bql_queries.py:164](backend/app/services/bql_queries.py#L164)) — el veredicto §6 lo lista como impacto técnico. **Fuera de scope de B6 salvo que se confirme que hay postings USD que entran al reporte de gastos.** Hoy `ledger_entries_via_beancount` y `report_rows_via_beancount` trabajan sobre montos ya en CLP; el balance-sheet es el único que colapsa un saldo USD a 0. Si Q1/Q2 no lo requieren, B6 se acota al balance. (Ver Pregunta técnica en Dev Notes.)

## Acceptance Criteria

1. **AC1 — Una cuenta USD-only ya NO sale en cero.**
   **Given** un ledger con una cuenta `Assets:EAG:Bancos:...Us` con un saldo en unidades **USD** (posting sembrado, ej. `100000 USD`) y sin pata CLP,
   **When** se consulta el balance-sheet (`balance_sheet_via_beancount`) con `date_to` en un mes que tiene EOM en `fx-bcch-eom.jsonl`,
   **Then** la fila de esa cuenta reporta un `Saldo (CLP)` = `saldo_usd × rate_clp_per_usd(EOM del mes de date_to)` (≠ 0), **no** `0.0`. (Hoy `_clp()` la colapsaría a 0.)

2. **AC2 — El balance muestra el CLP convertido al BCCh-EOM + el USD nativo.**
   **Given** la misma cuenta USD,
   **When** se lee la respuesta del balance,
   **Then** la fila trae, además del `Saldo (CLP)`, el **monto nativo USD**, el **código de moneda** (`USD`) y el **fx aplicado** (rate EOM), de modo que el frontend pueda renderizar `US$ X · fx Y · = CLP Z`. Las cuentas CLP siguen sin campo de moneda extranjera (o `currency=CLP`, `fx=1`, `native_amount=null`) — **sin regresión** en la forma de la respuesta para las filas CLP existentes.

3. **AC3 — La conversión es solo presentación: el ledger conserva USD.**
   **Given** el mismo ledger,
   **When** se inspeccionan las `entries` (`ledger.entries()`) tras servir el balance,
   **Then** el posting de la cuenta USD **sigue en unidades USD** — no se escribió ningún asiento de conversión ni de diferencia de cambio, no hay price directive nueva, el archivo del ledger no cambió. (La valorización vive en la query, no en el ledger.)

4. **AC4 — FX de cierre por el mes de `date_to`, con fallback acotado.**
   **Given** un `date_to` cuyo mes **sí** tiene EOM publicado en `fx-bcch-eom.jsonl`,
   **When** se convierte,
   **Then** se usa `rate_clp_per_usd` de **ese** mes (opción b del veredicto).
   **And** si el mes de `date_to` **no** tiene EOM aún (balance interino del mes en curso), se usa el **último EOM disponible** (`latest_bcch`, opción c = red de seguridad) y la fila expone qué rate se usó (auditable).
   **And** si **no hay ningún** EOM en el archivo, la conversión no inventa un número: la fila degrada de forma visible (ej. `currency=USD`, `fx=null`, `Saldo (CLP)` marcado como no disponible) en vez de colapsar a 0 en silencio.

5. **AC5 — Frontend: columna/anotación USD + campo de moneda en el tipo.**
   **Given** la respuesta enriquecida de AC2,
   **When** se renderiza `BalanceSheetPage`,
   **Then** el tipo `BalanceSheetRecord` ([frontend/src/types/index.ts:37](frontend/src/types/index.ts#L37)) incorpora los campos de moneda (`currency`, `native_amount`, `fx_used` — nombres a alinear con el backend), la columna **"Saldo (CLP)"** sigue totalizando el balance (los totales Activos/Pasivos/Patrimonio se calculan sobre el CLP convertido), y cada fila USD muestra el detalle nativo `US$ X @ fx Y` (anotación bajo el saldo o columna auxiliar). Las filas CLP se ven **idénticas** a hoy. `npx tsc --noEmit` verde.

6. **AC6 — Tests.**
   **Given** los cambios,
   **When** se corre la suite,
   **Then** hay: (a) test backend con una **posting USD sembrada** que verifica AC1 (saldo CLP ≠ 0 = usd×EOM) + AC2 (campos native/fx/currency presentes) + AC3 (el posting sigue en USD, ledger intacto); (b) test de AC4 (mes con EOM → ese rate; mes sin EOM → `latest_bcch`; sin EOM → degradación visible, no 0); (c) **no-regresión CLP**: una fila CLP conserva su forma y su total. Frontend: component test de una fila USD mostrando `US$ X @ Y = CLP Z` y una fila CLP sin cambios. `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` sin regresiones nuevas + `npx tsc --noEmit` verde.

## Tasks / Subtasks

- [ ] **Task 1 — `_clp()` deja de colapsar; extraer USD + moneda** (AC1, AC2)
  - [ ] En [bql_queries.py:46-53](backend/app/services/bql_queries.py#L46), reemplazar `_clp(inventory)` (o agregar un `_native(inventory)`) para que, cuando el `Inventory` traiga unidades ≠ CLP, devuelva **(número nativo, código de moneda)** en vez de forzar `0.0`. No romper el caso CLP (moneda CLP → `(número, "CLP")`).
  - [ ] Decidir el caso multi-moneda en una misma cuenta (¿posible?). Default: una cuenta USD-only. Si aparece mixta, documentar (probablemente no ocurre para estas 5 cuentas).

- [ ] **Task 2 — Convertir a CLP en la query del balance con el EOM del mes de `date_to`** (AC1, AC4)
  - [ ] En el loop de [bql_queries.py:93-108](backend/app/services/bql_queries.py#L93) (`balance_sheet_via_beancount`), para cada línea: si la moneda ≠ CLP, multiplicar el nativo por el **EOM del mes de `date_to`** (leer con `lookup_bcch(jsonl_path, year_month)` de [fx_calculator.py:34](pipeline/importers/fx_calculator.py#L34)); fallback `latest_bcch` ([fx_calculator.py:53](pipeline/importers/fx_calculator.py#L53)) si el mes de `date_to` no tiene EOM; sin EOM → degradar visible (no 0).
  - [ ] Derivar el `year_month` de `date_to` (o del `query_date` cuando `date_to` es None). Resolver la ruta del JSONL como el resto del proyecto (`LEDGER_PATH` env / `ledger/_meta/fx-bcch-eom.jsonl`).
  - [ ] Rellenar `debit_balance`/`credit_balance` con el **CLP convertido** (para que los totales del frontend sigan sumando en pesos) y agregar los campos nuevos de moneda al dict de la fila (Task 3).

- [ ] **Task 3 — Campos de moneda en la respuesta + tipo frontend** (AC2, AC5)
  - [ ] Agregar al dict de fila en [bql_queries.py:96-111](backend/app/services/bql_queries.py#L96): `currency` (código nativo), `native_amount` (número USD nativo, `null` para CLP), `fx_used` (rate aplicado, `null`/`1` para CLP). Nombres a confirmar con el modelo/response existente.
  - [ ] Extender `BalanceSheetRecord` ([frontend/src/types/index.ts:37-50](frontend/src/types/index.ts#L37)) con los mismos campos (opcionales, para no romper el path CLP/legacy Sheets).

- [ ] **Task 4 — Render dual en `BalanceSheetPage`** (AC5)
  - [ ] En [BalanceSheetPage.tsx](frontend/src/pages/BalanceSheetPage.tsx): la columna "Saldo" pasa a rotularse "Saldo (CLP)" (o mantener "Saldo" con el CLP convertido); para filas con `currency==='USD'`, mostrar el detalle nativo `US$ {native_amount} @ {fx_used}` como anotación bajo el saldo o columna auxiliar. Los totales (`totalAssets`/`totalLiabilities`/`netPatrimony`, líneas 111-113) ya suman `netPosition` sobre el CLP convertido → siguen correctos sin cambio de fórmula.
  - [ ] Filas CLP: sin cambios visibles.

- [ ] **Task 5 — Tests** (AC6)
  - [ ] Backend: test con ledger inline (`beancount.parser.parser.parse_string`) que abre una cuenta `Assets:EAG:Bancos:...Us` y postea un saldo `100000 USD`; verificar saldo CLP = `100000 × EOM`, campos native/fx/currency, y que el posting sigue en USD (AC3). Tests de fallback (`latest_bcch`) y de degradación sin EOM. Inyectar el JSONL fx por fixture (ruta temporal) — no depender del `fx-bcch-eom.jsonl` real. No-regresión: una cuenta CLP conserva forma y total.
  - [ ] Frontend: component test de una fila USD (`US$ X @ Y`) y una CLP (sin cambio). `tsc` verde.

## Dev Notes

### Estado actual de los archivos que se tocan (leídos para esta story)

- **[backend/app/services/bql_queries.py](backend/app/services/bql_queries.py) — `_clp()` (46-53) + `balance_sheet_via_beancount` (62-112).** `_clp()` hace `inventory.get_currency_units("CLP")` y devuelve `0.0` para cualquier otra moneda → **el bug**: un `Inventory` con unidades USD no tiene pata CLP → `amount is None` → `0.0`. El loop (93-108) arma la fila con `debit_balance`/`credit_balance` desde ese `_clp`. `query_date = date_to or _max_transaction_date(...)` (91) — de ahí sale el `year_month` para el EOM.
- **[pipeline/importers/fx_calculator.py](pipeline/importers/fx_calculator.py) — `lookup_bcch(jsonl_path, year_month)` (34) y `latest_bcch(jsonl_path)` (53).** Lectores YA existentes del `fx-bcch-eom.jsonl`; devuelven `Decimal | None`. **Reusar** — no reimplementar el parseo del JSONL. `lookup_bcch` = opción (b) del veredicto (EOM del mes); `latest_bcch` = opción (c) fallback.
- **[ledger/_meta/fx-bcch-eom.jsonl](ledger/_meta/fx-bcch-eom.jsonl)** — dólar observado BCCh por fin de mes: `{"year_month":"2026-03","rate_clp_per_usd":931.57,...}`. Poblado por Story 9.10 (cron + endpoint admin). Ej. reales: 2026-03 → 931,57; 2026-04 → 901,76.
- **[backend/app/api/v1/dashboard/router.py:53](backend/app/api/v1/dashboard/router.py#L53) → [service.py:19](backend/app/api/v1/dashboard/service.py#L19)** — el endpoint pasa `date_to` (ISO `YYYY-MM-DD`, inclusive) a `balance_sheet_via_beancount`. De acá sale el mes de cierre.
- **[frontend/src/types/index.ts:37-50](frontend/src/types/index.ts#L37) — `BalanceSheetRecord`** — hoy: `account_number`, `account`, `account_name`, `debit`, `credit`, `debit_balance`, `credit_balance`, `query_date`, `is_latest`. **Sin campo de moneda.** Agregar `currency`/`native_amount`/`fx_used` opcionales.
- **[frontend/src/pages/BalanceSheetPage.tsx](frontend/src/pages/BalanceSheetPage.tsx)** — tabla con columnas Cuenta/Nombre/Debe/Haber/Saldo; `netPosition = debit_balance − credit_balance`; totales sobre `netPosition`. Una sola columna "Saldo", asume CLP puro.

### `paritytomaincurrency: 1.0` (bql_queries.py:164) — pregunta técnica para Ary/dev

El veredicto §6 lista `paritytomaincurrency: 1.0` hardcodeado en `ledger_entries_via_beancount` ([bql_queries.py:164](backend/app/services/bql_queries.py#L164)) como impacto técnico. **Pero** ese campo alimenta el reporte de gastos / ledger entries, no el balance-sheet, y esos paths hoy trabajan sobre montos que ya están en CLP (la deuda TC USD se postea en CLP; no hay postings USD-nativos que entren ahí todavía). **Propuesta:** acotar B6 al balance-sheet (el único que colapsa a 0) y **dejar `paritytomaincurrency` fuera** salvo que se confirme que un saldo USD-nativo va a fluir al reporte de gastos. Confirmar con Ary/Valentina antes de ampliar el blast radius.

### Anti-patrones a evitar (del veredicto y del proyecto)

- **NO** convertir a CLP al importar / guardar CLP en el ledger para las cuentas USD-nativas (rompe el espejo-Laudus; congela el valor). Guardar **nativo**, convertir **al leer**.
- **NO** bookear un asiento de diferencia de cambio (veredicto §5). La dif. se ve sola en el total; no se postea hasta que Laudus la reconozca.
- **NO** reimplementar el parseo del `fx-bcch-eom.jsonl` — usar `lookup_bcch`/`latest_bcch`.
- **NO** tocar la deuda TC USD (`Liabilities:EAG:TC:Real:*Us`), que se queda en CLP al fx del pago (doctrina §2, story 6.6).
- **NO** inventar un fx cuando no hay EOM: degradar visible (fila marcada), nunca colapsar a 0 en silencio (ese es justo el bug original).

### Testing standards

- Backend: `pytest`, fixtures con `beancount.parser.parser.parse_string` (ledger inline). Inyectar el JSONL fx por ruta temporal (fixture), no el archivo real. Correr con `PYTHONUTF8=1` (gotcha Windows). Los 2 rojos `test_fava_edit_validator` que a veces aparecen son PRE-EXISTENTES — no atribuírselos a esta story.
- Frontend: `vitest` component test + `npx tsc --noEmit` verde.
- **Verificación de aceptación con datos reales (handoff Ary, no codeable, GATE):** cuando entre el primer saldo USD real, **spot-check obligatorio** del `Saldo (CLP)` convertido contra el estado del custodio/contador (Pregunta 1). No asumir que el dólar de cierre BCCh = el que usa el contador hasta verificarlo.

### Project Structure Notes

- Sin cuentas nuevas, sin tocar el árbol de cuentas, sin sidecar ni DB (veredicto §6). El cambio vive en: `bql_queries.py` (motor de presentación) + `BalanceSheetRecord`/`BalanceSheetPage` (display) + tests.

### References

- [Source: _bmad-output/planning-artifacts/valentina-tratamiento-saldos-usd-balance-2026-07-08.md] — **veredicto autoritativo**: §2 activo USD vivo ≠ deuda TC; §4 híbrido (b)+(a) presentación; §5 dif. de cambio se muestra no se bookea; §6 impacto técnico; §7 decisiones para Ary.
- [Source: _bmad-output/planning-artifacts/valentina-story-brief-fx-revolving-tc-usd-2026-07-06.md] — doctrina FX de la deuda TC (fx del pago que la salda) que B6 **no** toca.
- [Source: memoria project_inversiones_audit_deferred 2026-06-20] — Laudus no revaloriza (0 price directives); fundamenta "no bookear dif. de cambio / espejar, no anticipar".
- [Source: memoria project_tc_pasivo_dos_estados] — TC = pasivo, se salda con caja (CLP real); el otro lado de la regla de §2.
- [Source: pipeline/importers/fx_bcch_eom.py + fx_calculator.py:34,53 — Story 9.10] — origen y lectores del `fx-bcch-eom.jsonl` (dólar observado EOM).

## Preguntas para Ary (ABIERTAS — la story está gated hasta resolverlas)

> Valentina las dejó explícitas en el veredicto §7. **No cerrarlas en la story**; se confirman cuando entren los saldos USD reales.

1. **¿El balance del contador valoriza estas cuentas USD al dólar de cierre, o a costo histórico?**
   Es la **única** pregunta que puede cambiar la recomendación. Si el balance de referencia del contador usa **costo histórico** (o un dólar contable distinto al observado), hay que **espejarlo** para que la paridad cierre — la fidelidad a Laudus manda sobre la preferencia por el dólar de cierre. **Spot-check obligatorio** del `Saldo (CLP)` convertido contra el estado del custodio/contador **cuando llegue el primer saldo real** (mismo espíritu que la auditoría de inversiones: no asumir que Laudus está bien).

2. **¿Diferencia de cambio: mostrar y punto, o algún día reconocerla?**
   Recomendación de Valentina: **mostrarla** (se ve sola en el total, período a período) y **no** bookearla mientras Laudus no lo haga. Si el contador la reconoce, la **espejamos** (no la anticipamos). **Confirmar que estamos de acuerdo en no anticiparla.**

3. **(Menor) ¿El dólar observado EOM es el que usa el contador?**
   Es lo que tenemos (`fx-bcch-eom.jsonl`, mindicador/BCCh) y es el estándar chileno para partidas monetarias en ME. Si el contador usa otro (dólar acuerdo, dólar de cierre bancario), es un cambio de **fuente de una línea**, no de doctrina.

4. **(Técnica, para dev) ¿Se amplía a `paritytomaincurrency` (bql_queries.py:164)?**
   B6 se acota al balance-sheet por default (§ Fuera de scope + Dev Note). Ampliar al reporte de gastos solo si se confirma que un saldo USD-nativo va a fluir por ese path.

> **Prioridad (veredicto §7):** el bug es **latente** (0 USD hoy) → no urgente **hasta que se decida cargar saldos USD-nativos**. Pero cargar **sin este fix** = balance muestra esos activos en cero = descuadre silencioso grave. **Fix antes de importar el primer saldo USD.**
