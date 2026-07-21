# Cartola + TC — Referencia de controles para v2

**Fecha:** 2026-07-21
**Autor:** extracción de código (Moishe) previo al rewrite
**Propósito:** capturar de forma implementable TODO control, proceso, regla de negocio, contrato de
datos, invariante y edge-case del pipeline ACTUAL de ingesta y conciliación de cartolas bancarias y
tarjetas de crédito (TC), para poder reconstruirlo en v2 SIN leer el código viejo. El código descrito
está por eliminarse; este documento es el registro canónico.

> Convención de citas: los nombres de función, archivo y constante son EXACTOS al código actual.
> Rutas absolutas relativas a `c:\dev\bmad-workspace-new\family-office-eag\`.

---

## 1. Resumen y propósito

El pipeline toma un PDF de cartola/estado de cuenta chileno, lo extrae a un JSON canónico con Gemini,
lo valida y lo enriquece con warnings, y luego bifurca según el tipo de cuenta: para **cuentas
corriente/vista/ahorro** hace **conciliación sin postear** (modelo A) — compara la cartola contra los
asientos que ya trajo Laudus y registra las *diferencias* en un JSONL append-only que un dashboard
muestra para revisión/resolución; para **tarjetas de crédito** hace **materialización contable** — Laudus
solo tiene el pago lump mensual, no las compras, así que el pipeline SÍ postea al ledger Beancount el
desglose compra-por-compra (con FX derivado del pago real para cartolas USD), y computa un cuadre de
cinco chequeos (C1–C5) que verifica que la deuda materializada coincida peso-por-peso con el estado de
cuenta. Todo es idempotente, corre bajo lock de archivo + `bean-check` + commit/push a git, y Laudus
sigue siendo la fuente contable de verdad para las cuentas corriente; la cartola es la lupa (cta cte) o
el detalle que Laudus no tiene (TC).

---

## 2. Flujo end-to-end

### 2.1. Upload (POST `/api/v1/cartolas/upload`)
- **Consume:** multipart `pdf_file` + `bank_account_id` (Form). RBAC `contador|admin`.
- **Valida (síncrono, `validate_upload_inputs`):** PDF no vacío; ≤ `MAX_PDF_SIZE_BYTES` = 20 MB;
  `Content-Type == application/pdf` (si viene); magic bytes `%PDF`; `bank_account_id` existe en el índice;
  la cuenta tiene `bank_account_last4` (si no → error tipado `MISSING_LAST4`).
- **Produce:** `202 {status:"processing", batch_id}` (UUID4). Lanza la extracción como `BackgroundTask`
  (`run_job`). El frontend pollea `GET /{batch_id}`.

### 2.2. Extracción (Gemini) — `process_upload_sync` / `_extract_and_enrich`
- **Consume:** `pdf_bytes` + hint de la cuenta (id, banco, label, tipo, moneda, last4).
- **Gemini** (`GeminiClient.extract_pdf`): modelo `GEMINI_MODEL` (default `gemini-3.5-flash`),
  `response_mime_type=application/json`, `temperature=0.1`, `max_output_tokens=32768`, timeout HTTP 120 s.
  El prompt fija el shape canónico, enums cerrados, convención de signo por tipo de cuenta, reglas de
  inclusión/exclusión (cuotas pre-existentes X/N con X≥1 se incluyen; cuotas futuras X=0 y subtotales se
  excluyen), y delega los warnings al backend (Gemini solo puede emitir `LOW_CONFIDENCE`).
- **Stamps server-side (no se confía en Gemini):** `source` se sobrescribe con `resolve_source_dict`,
  `extraction.model`, `extraction.extracted_at`, `schema_version="1.0"`.
- **Valida shape:** `CartolaCanonicalV1.model_validate` (Pydantic, `extra="forbid"`).
- **Post-proceso** (`apply_post_process`): agrega warnings (ver §3).
- **Reintentos** (`MAX_EXTRACTION_ATTEMPTS = 3`): draws independientes ante `GeminiExtractionError`
  (JSON no parseable/truncado) o `BALANCE_MISMATCH`. Corta al primer resultado limpio; si persiste el
  mismatch devuelve el mejor canónico válido (mismatch legítimo se surfacea como warning). Un
  `ValidationError` (shape inválido) NO se reintenta (determinista).
- **Produce:** archivo de staging `imports/cartolas/_staging/{batch_id}.cartola.json` + job `ready`.

### 2.3. Resolución de cuenta bancaria
- Dos índices paralelos parsean `accounts.beancount` y mapean `bank_account_id` → cuenta Beancount:
  - `BankAccountIndex` (backend, cache por mtime) — usado por upload/status.
  - `BankAccountResolver` / `resolver_for` (pipeline, cache por (mtime,size)) — usado por importers.
- La entidad de la cuenta se resuelve por el 2º segmento del path (`Assets:EAG:...` → EAG); fallback
  legacy por `laudus_categoria1`; default `EAG`.

### 2.4. Confirmación (PATCH `/api/v1/cartolas/{batch_id}/validate-balance`)
- **Consume:** `{opening, closing, override_justification?}`.
- **Precheck síncrono** (`precheck_balance`, barato — solo lee staging): 404 si no hay staging; 400 si
  justificación < 20 chars; 400 si `closing ≠ opening + Σtx` y no hay override. Devuelve `202 confirming`.
- **Job pesado** (`run_confirm_job` → `validate_balance`): reconcilia/materializa + `bean-check` + git +
  reload + cuadre. Bifurca por `account_type`:
  - **`tarjeta_credito`** → `correct_tc_cartola` (postea; §2.6).
  - **resto** → `reconcile_cartola` (modelo A, no postea; §2.5).
- **Produce:** el job termina en `confirmed` (payload igual al del PATCH síncrono viejo) o `confirm_failed`
  (código tipado). El frontend lo recoge por poll de `GET /{batch_id}`.

### 2.5. Conciliación cta corriente (modelo A) — `reconcile_cartola`
1. Arma `CartolaLine[]` desde el canónico; carga `load_laudus_entries()` del período **padeado
   ±`DATE_TOLERANCE_DAYS`**.
2. `reconcile_and_build` corre el matching (`match`), construye discrepancias según estado; **las entries
   Beancount se descartan** (no se postea).
3. Acota `missing-in-cartola` al período core (descarta asientos de estados vecinos traídos por el pad).
4. Appendea discrepancias (dedup) a `_meta/cartola-discrepancies.jsonl`; escribe un run-record a
   `_meta/reconciliation-runs.jsonl`; commitea (run SIEMPRE; discrepancias solo si hubo nuevas).
5. Consume el staging. **Produce:** `{status:"reconciled", differences, blocking, matched, ...}`.

### 2.6. Materialización TC — `correct_tc_cartola`
1. Resuelve `expense_tc` (cuenta-gasto Laudus) → `tc_real` (`Liabilities:EAG:TC:Real:<stem>`).
2. **Guard de moneda:** cuenta USD (`...Us`) + cartola no-USD → bloquea (evita postear deuda USD a fx=1).
3. **FX (solo USD):** `derive_statement_fx` desde el pago Laudus que salda el estado; si falla, fallback
   revolving `inherit_statement_fx`. CLP → fx=1.
4. Pre-resuelve el lump CLP real de cada pago (`_resolve_usd_lump`).
5. Categoriza cada compra (`CategorizationService`).
6. `build_tc_correction_entries`: asientos (a) compra/cargo/avance/abono, (b) reclasificación del pago,
   (c) apertura (una vez). Rutea `operation_type` (§3).
7. **Gate de cordura FX** vs BCCh del mes del pago ±5% (solo USD con pago propio).
8. Escribe `imports/cartolas/{slug}-tc.beancount` bajo lock + `bean-check` (rollback si rojo) + commit.
9. Consume staging. **Produce:** `{status:"corrected"|"blocked", fx, fx_source, purchases, payments, ...}`.

### 2.7. Cuadre (C1–C5) — `compute_tc_cuadre`
- Corre post-confirmación (inline en `run_confirm_job` con el ledger recargado) y también on-demand
  (`GET /api/v1/tc/reconciliation`). Puro sobre las entries. Lee opening/closing/fx/currency de la
  metadata persistida. Ver §3.

### 2.8. Manejo de discrepancias (dashboard) — `/api/v1/reconciliation/*`
- Lista filtrable + summary; history (audit trail); count (chip); periods (estado por cuenta×mes);
  resolve (single) / resolve-batch (todo-o-nada). Acciones válidas por estado (§4). `confirm-cartola-only`
  sobre `missing-in-laudus` ANOTA la tx al ledger (`manual/`) antes de cerrar la discrepancia.

### 2.9. Promoción de cuentas nuevas
- No hay UI self-serve dedicada en este pipeline. Las cuentas viven en `accounts.beancount` (metadata
  `bank_account_id`, `bank_account_last4`, `bank_account_currency`, `bank_account_type`, `bank_name`);
  se editan vía Fava. El índice se invalida por mtime → una cuenta nueva aparece sin redeploy. Las
  cuentas `TC:Real:*` y su `Equity:Apertura:TarjetasSinDetalle` se crearon a mano en `accounts.beancount`
  (el flujo 10.3 no servía). Una compra sin categoría real cae a `Expenses:EAG:Suspense` y se resuelve en
  `/categorizacion`.

---

## 3. Catálogo de controles

### CONTROL — Validaciones de upload (`validate_upload_inputs`)
- **Verifica:** PDF no vacío, ≤ 20 MB (`MAX_PDF_SIZE_BYTES`), Content-Type PDF, magic bytes `%PDF`,
  cuenta registrada, `last4` presente.
- **Por qué:** defensa contra archivo mentido en MIME, PDF corrupto, cuenta desconocida, y (last4)
  contra subir a una cuenta sin identidad verificable.
- **Umbral:** 20 MB (NFR3).
- **Falla:** `CartolaValidationError` → HTTP 400 con `code` (`VALIDATION_FAILED` / `MISSING_LAST4`).

### CONTROL — Convención de signo por tipo de cuenta (prompt Gemini + `_build_postings`)
- **Verifica:** que los montos sigan la semántica Beancount. **Liabilities (TC, línea de crédito):**
  aumentar deuda = **+**, disminuir = **−**. **Assets (cta cte/vista/ahorro):** aumentar saldo = **+**,
  disminuir = **−**. La cartola presenta convención "natural de extracto" (deuda como positivo); para
  cuentas `Liabilities` el importer NIEGA el signo (`target = -amount`, `balance = -closing`).
- **Por qué:** un signo mal puesto rompe el cuadre y contabiliza al revés.
- **Falla:** el prompt exige verificar `closing - opening == Σtx` antes de devolver; el backend lo revalida
  (BALANCE_MISMATCH).

### CONTROL — Cuadre de extracción / `BALANCE_MISMATCH` (`detect_balance_mismatch`, `validate_balance`)
- **Verifica:** `closing - opening == Σ(transactions)` (equivalente: `closing == opening + Σtx`).
- **Por qué:** si Gemini omite una línea el agregado no cuadra → detecta extracción incompleta;
  reconciliar una cartola que no suma daría ruido.
- **Umbral:** tolerancia `BALANCE_MISMATCH_TOLERANCE_CLP = Decimal("100")` (redondeo). Post-proceso emite
  warning si `diff > 100`. En confirm, `diff != 0` (exacto, Decimal) sin `override_justification` → 400.
- **Falla:** warning en extracción; en confirm bloquea (`BalanceDiscrepancy` HTTP 400) salvo override con
  justificación ≥ `MIN_JUSTIFICATION = 20` chars (registrado con user+timestamp en git).

### CONTROL — Warnings de post-proceso (`apply_post_process`)
- **`DUPLICATE_LINE`** — misma (fecha, monto, descripción normalizada) que otra línea; FR26.
- **`ZERO_AMOUNT`** — `amount == 0` (probable error de parseo).
- **`PERIOD_MISMATCH`** — dispara solo si **≥80%** (`PERIOD_MISMATCH_RATIO_THRESHOLD = 0.80`) de las tx
  no-cuota caen fuera de `[period.start, period.end]` (señal de que el LLM leyó mal mes/año). Cuotas
  pre-existentes X/N (X≥1) se excluyen (su fecha es legítimamente anterior). 1-2 tx fuera por corte de
  facturación (hasta ~5 días) NO dispara.
- **`LARGE_AMOUNT`** — `|amount| > LARGE_AMOUNT_THRESHOLD_FACTOR (=3) × promedio histórico` de la cuenta;
  requiere historial (sin él, no emite). FR27.
- **Por qué:** guardarraíl empírico contra extracción incompleta/errónea; no bloquean, informan.
- **Dedup:** por (code, line_no, detail).

### CONTROL — Matching cartola↔Laudus (`match` / `_classify`, `matching_engine.py`)
- **Verifica:** empareja cada línea de cartola con el mejor asiento Laudus aceptable y clasifica en un
  estado. **Greedy, sin reusar** un asiento Laudus ya consumido.
- **Parámetros:** `DATE_TOLERANCE_DAYS = 3`; `DESC_SIMILARITY_THRESHOLD = 0.85` (SequenceMatcher);
  monto **exacto** para CLP; para USD (era FX) NO se compara monto (moneda distinta). Score =
  `(100 si monto exacto) + sim×10 − |Δdías|`. `USD_FX_EPOCH = 2026-01-01` habilita la era FX; pre-2026 es
  CLP-only (AC9). Optimización: si hay candidatos con monto exacto la similitud de los demás ni se computa
  (garantizado por `assert 100 - DATE_TOLERANCE_DAYS > 10`).
- **Estados** (`STATES`): `perfect`, `value-mismatch`, `missing-in-laudus`, `missing-in-cartola`,
  `date-mismatch`, `description-mismatch`, `category-mismatch`.
- **Falla/decisión** (`process_match_result`): `perfect` → emite `*` sin discrepancia. Soft-mismatch
  (date/description/category) → emite `!` + discrepancia. **Bloqueantes (`_BLOCKING` = {value-mismatch,
  missing-in-cartola})** → NO emiten Transaction, solo discrepancia. `missing-in-cartola` no se contabiliza
  porque la cartola es la fuente de verdad y Laudus ya lo tiene (evita doble conteo).

### CONTROL — Ventana de matching padeada + acotamiento de missing-in-cartola (`reconcile_cartola`)
- **Verifica:** la carga de asientos Laudus se hace sobre `[period.start − tol, period.end + tol]` con
  `tol = DATE_TOLERANCE_DAYS (3 días)`, para que la tolerancia de fecha del matcher alcance asientos
  fechados 1-2 días fuera del período (value-date vs fecha del estado). **Luego** las discrepancias
  `missing-in-cartola` se filtran al período core `[period.start, period.end]` (`_in_core`).
- **Por qué:** sin el pad, una línea de borde quedaba `missing-in-laudus` falso; sin el acotamiento, el
  pad traía asientos de estados adyacentes marcados como `missing-in-cartola` falso (diferencias del mes
  vecino). El pad es solo para MATCHEAR, no para flaggear.

### CONTROL — Period-awareness (`year_month`, Story 6.5b)
- **Verifica:** cada discrepancia y cada asiento TC llevan `year_month = model.period.end` (`YYYY-MM`),
  el período del ESTADO DE CUENTA, distinto de la fecha de la transacción.
- **Por qué:** una compra del 28-abr puede pertenecer al estado de mayo por el corte de facturación.
  Bucketear por fecha de tx mezclaba estados. El servicio agrupa/filtra por `year_month` persistido
  (fallback a la fecha para discrepancias/asientos viejos sin el campo).

### CONTROL — Derivación de FX del estado USD (`derive_statement_fx`, `tc_correction.py`)
- **Modelo de los DOS pagos (§12.1, diseño Valentina 2026-06-20):** cada estado USD tiene dos eventos de
  pago distintos: (1) la **liquidación** = el pago del mes siguiente que salda ESTE estado → es el
  denominador del FX (`FX = CLP_liquidación / total_USD_facturado`, fuerza `Σ(compras×FX) =
  CLP_liquidación`); (2) la línea interna **`MONTO CANCELADO`** = salda el estado M−1 → es el lump del
  asiento (b). Un mismo pago Laudus juega ambos roles pero en estados *adyacentes*. Procesar ene…dic 2026
  con este modelo cancela exactamente los 12 lumps que Laudus posteó en 2026, una vez cada uno (el modelo
  "estado propio" dejaría el pago de enero sin cancelar y cancelaría uno de 2027 → rompe la paridad
  peso-por-peso con el contador).
- **Verifica:** el FX único del estado = `CLP_del_pago / USD`. Busca en los asientos Laudus de la
  cuenta-gasto el pago fechado **tras el cierre** cuya **glosa codifica el mismo USD que el `closing`**
  (`parse_glosa_usd`, formato chileno `USD26.188,93`). Ventana `_FX_WINDOW_DAYS = 75` días;
  tolerancia de match USD `_USD_MATCH_TOLERANCE = Decimal("0.01")`.
- **Fallback consolidado** (`_select_by_amount`): si ninguna glosa codifica ese USD (pago consolidado
  Santander paga varias tarjetas y nombra UNA), elige el posting cuyo `amount / total_usd` pasa el gate
  BCCh ±tolerancia. Entre los que pasan, el de **fecha más temprana tras el cierre**.
- **Regla §12.1 (crítica):** el BCCh **NUNCA es la tasa** — solo decide qué posting es plausible; la tasa
  siempre es `CLP real / USD` del pago. El BCCh de referencia es el del **mes en que se pagó** cada
  candidato (`bcch_at`, mes exacto o `latest_bcch` si falta), no el del cierre (el estado de feb se paga en
  mar a la tasa de mar).
- **Umbral del gate** (`_fx_in_gate`): `|fx − bcch| / bcch × 100 ≤ TOLERANCE_PCT (=5)`; requiere `fx > 0`
  y `bcch` presente. **Sin BCCh de referencia → falla segura: bloquea** (decisión Ary 2026-06-30, no
  estima FX).
- **Falla:** `status:"blocked"` con reason ("sin pago Laudus que salde el estado…").

### CONTROL — Herencia de FX para meses revolving (`inherit_statement_fx`, Story 6.2 brief 2026-07-06)
- **Verifica:** un estado sin pago propio (el saldo rodó al mes siguiente, revolving) hereda el `fx` del
  estado **contiguo posterior que absorbió el saldo**. Busca en las cartolas TC ya importadas de la misma
  `TC:Real` un estado con `opening == closing` de este (contigüidad, ±0.01), período posterior, misma
  moneda; toma el más cercano.
- **Por qué:** el estado revolving SÍ tiene costo CLP real (el pago que saldó el estado que lo absorbió);
  heredar ese fx es §12.1 aplicado transitivamente, no una estimación.
- **Umbrales:** cadena `_MAX_INHERIT_CHAIN_MONTHS = 3` — si el fx vendría de un origen a > 3 meses,
  bloquea (deuda impaga demasiado larga → revisión humana). El gate BCCh ±5% aplica igual (contra el BCCh
  del mes de ESTE estado). Sin BCCh → bloquea.
- **Metadata:** `fx_source = "inherited:<YYYY-MM origen>"` (propaga el período ORIGEN cuyo pago real
  derivó el fx, para poder acotar cadenas multi-mes). Los estados con pago propio NO llevan `fx_source`.
- **Falla:** `status:"blocked"` con reason (importá primero el mes siguiente / cadena demasiado larga /
  no pasa el gate).

### CONTROL — Gate de cordura FX vs BCCh ±5% (`calculate_fx`, `correct_tc_cartola`)
- **Verifica:** solo USD **con pago propio** (`fx_source is None`). El FX derivado se compara contra el
  dólar BCCh del **mes del pago** (`fx_res["payment_date"]`). `FXResult` estados:
  `fx-out-of-tolerance` (desviación > `TOLERANCE_PCT = 5`), `fx-implausible` (`implied > FX_IMPLAUSIBLE =
  Decimal("2000")` CLP/USD, o USD == 0), `fx-bcch-missing` (sin BCCh ese mes → NO bloquea).
- **Por qué:** valida que el lump/total USD corresponden; una desviación grande = el pago o el total no
  cuadran. El BCCh valida cordura, NO se vuelve la tasa (usarlo como tasa descuadraría `Σ(compras×fx)`).
- **Falla:** `state ∈ {fx-out-of-tolerance, fx-implausible}` → `status:"blocked"`. Con fx heredado el gate
  ya se aplicó dentro de `inherit_statement_fx`.

### CONTROL — Ruteo de `operation_type` (`_normalize_op` + `build_tc_correction_entries`)
- **Verifica:** toda línea emite el asiento (a) contra `TC:Real` por `−monto×fx` (el pasivo cuadra con el
  closing SIEMPRE); la contrapartida depende del tipo canónico:
  - `_CONSUMO_OPS = {compra, cuota, abono}` → `Expenses:<cat>` vía categorizador 9.7 (abono = compra
    invertida por el signo del amount).
  - `_BANK_CHARGE_OPS = {impuesto, comision, interes, seguro, mantencion}` → `BANK_CHARGES_ACCOUNT =
    Expenses:EAG:GastosBancarios-430003` (FIJO, no pasa por el categorizador).
  - `_ADVANCE_OPS = {avance}` → `CAJA_CLP = Assets:EAG:Caja-111001` / `CAJA_USD =
    Assets:EAG:CajaUs-111003` (es plata, NO gasto).
  - `_PAYMENT_OPS = {pago}` → asiento (b) reclasificación (§siguiente).
  - **No reconocido** → `SUSPENSE_ACCOUNT = Expenses:EAG:Suspense` + se agrega a `unmapped` (línea, op,
    monto). **NUNCA se descarta** (§10.1, red de seguridad — cierra el drop silencioso).
- **Normalización** (`_normalize_op`): `None`/vacío → `compra` si monto +, `abono` si −. Sinónimos
  (`_OP_SYNONYMS`): `compras p.a.t.`/`pat`/`compra_automatica`/`cargo_automatico` → `compra`;
  `nota_credito` → `abono`. Tipo canónico conocido → pasa; otro → `""` (Suspense).

### CONTROL — Reclasificación del pago (asiento b) y valorización de la apertura
- **Verifica (asiento b):** el pago saca el "gasto" lumpeado que dejó Laudus:
  `Expenses:EAG:TC:<code>` (−lump) / `TC:Real` (+lump). El lump es el **CLP real** del pago (CLP: magnitud
  de la línea; USD: `_resolve_usd_lump` por glosa, luego por monto con el mismo gate BCCh). Si `lump == 0`
  se saltea.
- **Verifica (asiento c, apertura):** una sola vez por tarjeta (primera cartola, `emit_opening`).
  `TC:Real` (−opening) / `Equity:Apertura:TarjetasSinDetalle` (+opening). La apertura se valoriza al **CLP
  real del pago que la salda** si ese pago existe en esta cartola (MONTO CANCELADO nativo == opening
  nativo, ±0.01) — porque la deuda vieja se liquidó al fx de SU mes, no al de este estado; fallback a
  `opening × fx` si es apertura parcial. Así apertura y su pago se netean exacto y no queda diferencia de
  cambio fantasma.
- **Por qué:** telescopeo del saldo TC:Real a −closing (ver C1).

### CONTROL — Invariante C1: `TC:Real == −closing×fx` (`compute_tc_cuadre`, 🔴 crítico)
- **Verifica:** el saldo acumulado de `TC:Real` (sumando asientos con `period ≤ year_month`, **por período
  del estado, no por fecha de tx**) == `−(closing × fx)`. Tolerancia `_TOL_CLP = Decimal("1")` (CLP sin
  decimales); USD `_TOL_USD = Decimal("0.01")`.
- **Por qué:** deuda mal materializada. Cachea desde la primera cartola el bug de categorización que
  destruía la pata `TC:Real`. Acumular por período (no fecha) evita inflar la deuda cuando una compra del
  27-feb se factura en marzo.
- **Falla:** `c1_ok=False` → semáforo `red`.

### CONTROL — C2: contigüidad `apertura[M] == cierre[M−1]` (🟡)
- **Verifica:** la apertura de este estado == cierre del estado anterior (misma tarjeta, moneda nativa,
  tolerancia nativa). Lee ambos de la metadata persistida.
- **Por qué:** detecta cartola faltante entre medio.
- **Falla:** `c2_ok=False` → `yellow`. Sin cartola anterior (`prev is None`) o sin apertura persistida →
  `c2_ok=False` con `c2_reason`. La primera cartola siempre sale amarilla ("sin cartola anterior"), es
  normal.

### CONTROL — C3: integridad del asiento (🔴 crítico)
- **Verifica:** toda compra/cuota (`_CONSUMO_OPS = {compra, cuota}`) del período conserva **exactamente
  UNA** pata `Liabilities:EAG:TC:Real:` y usa **≥2 cuentas distintas**. Scope por `bank_account_id` si se
  pasa (detecta la pata destruida aunque el asiento ya no toque la cuenta), si no por cuenta.
- **Por qué:** el bug de categorización reescribía AMBAS patas a `Expenses:` → destruía la pata de deuda y
  el saldo quedaba más bajo que el real. C3 lista los corruptos (fecha/glosa/monto) para arreglarlos.
- **Falla:** `c3_ok=False` con `c3_corrupted[]` → `red`.

### CONTROL — C4: pago cartola vs pago Laudus (🟡)
- **Verifica:** `Σ pago(TC:Real, cartola-tc, period=M)` == `Σ pagos que Laudus registró para esa
  tarjeta ese mes` (lump_account con units > 0, no cartola-tc). Tolerancia `_TOL_CLP = 1`.
- **Por qué:** el pago de la cartola debe ser el que registró el banco.
- **Falla:** `pago_ok=False` → `yellow`. Típico: pago consolidado de varias tarjetas o falta el pago.

### CONTROL — C5: lump residual neteado (🟡)
- **Verifica:** el saldo de la cuenta-gasto lump `Expenses:EAG:TC:<stem>-<code>` del mes quedó ≈0 tras la
  cartola. Tolerancia `_TOL_CLP = 1`.
- **Por qué:** confirma que el "gasto en bloque" de Laudus fue reemplazado por el detalle. Informativo:
  baja a 0 a medida que se categorizan las compras.
- **Falla:** `c5_ok=False` → `yellow`.

**Semáforo agregado:** `red` si C1 o C3 fallan; `yellow` si algún 🟡 (C2/C4/C5) falla; `green` si todo pasa.

### CONTROL — Guard de moneda TC (`correct_tc_cartola`)
- **Verifica:** una cuenta `TC:Real` que termina en `Us` (convención del stem USD) NO puede recibir una
  cartola no-USD.
- **Por qué:** si Gemini etiquetó mal la moneda (caso real: 1027 USD abril leída como CLP), el desglose
  tomaría el camino CLP (fx=1) y postearía la deuda USD 1:1 = basura silenciosa.
- **Falla:** bloquea con reason (falla segura). El reverso (cuenta CLP + cartola USD) se auto-bloquea vía
  la derivación de FX (no hay pago USD que cuadre).

### CONTROL — Exclusión de apertura al re-importar (`_opening_exists`, AC4)
- **Verifica:** ¿ya hay un asiento `operation_type=apertura` para esta `TC:Real` en una cartola previa?
  Escanea los `*-tc.beancount`, **excluyendo el archivo de salida de ESTA corrida** (`exclude=out_file`).
- **Por qué:** idempotencia — la apertura se emite una sola vez por tarjeta. Sin `exclude`, re-importar la
  misma cartola (mismo slug → se sobrescribe) detectaría su propia apertura previa y la perdería.

### CONTROL — Slug por stem, anti-colisión CLP+USD (`tc_cartola_filename`)
- **Verifica:** el nombre del archivo `{slugify(bank)}-{last4}-{stem}-{YYYY-MM}-tc.beancount` incluye el
  **stem de la `TC:Real`** (`<x>` CLP vs `<x>Us` USD).
- **Por qué:** CLP y USD de la misma tarjeta/mes tendrían el mismo slug y colisionarían; con el stem cada
  moneda va a su archivo. Determinista → re-import sobrescribe (idempotencia visible, `already_imported`).

### CONTROL — Escritura atómica: lock + bean-check + rollback + git
- **Verifica:** toda escritura al ledger corre bajo `acquire_lock(.import.lock)` (timeout 60 s, max_age
  stale 300 s, heartbeat, ownership por token, adquisición atómica O_CREAT|O_EXCL). Se escribe, se corre
  `bean_check(main.beancount)` (borra el `.picklecache` antes para no validar el ledger viejo — trap con
  `include glob`), y si falla se **restaura el snapshot previo** (o unlink si era nuevo) → nunca destruye
  una cartola buena ya importada. `git_commit_push` gateado por `IMPORTER_GIT_ENABLED`; fetch+rebase antes
  del push (ledger y código comparten repo/branch `main`); auth por `BEANCOUNT_DEPLOY_KEY` (Render).
- **Por qué:** concurrencia, integridad contable, y supervivencia al `git reset --hard` del refresh del
  backend (por eso los JSONL de `_meta` se commitean).

### CONTROL — Dedup de discrepancias (`discrepancy_writer`)
- **Verifica:** clave de dedup = `(bank_account_id, year_month, cartola_line_no, laudus_je_id, state)`.
  Re-correr el matching no duplica; re-subir la misma cartola (batch_id nuevo) tampoco.
- **Por qué:** la clave vieja llevaba `batch_id` y cada re-upload duplicaba todas las discrepancias
  abiertas (review 2026-07-06 B4). `append_discrepancies` hace UNA lectura del JSONL por batch (D5).
- **Residual documentado:** entradas legacy sin `year_month` (clave con None) y líneas re-numeradas por
  una re-extracción distinta pueden dupear una vez.

### CONTROL — Run-records (`build_run`/`append_run`, Story 6.5)
- **Verifica:** cada reconciliación deja un run-record en `_meta/reconciliation-runs.jsonl` (append-only,
  sin dedup; el lector toma el más reciente por (cuenta, mes)). Se commitea **SIEMPRE** (incluso cartola
  perfecta con 0 diferencias).
- **Por qué:** distingue "cartola perfecta / todas resueltas" de "nunca subida" (las tres se ven idénticas
  en el JSONL de discrepancias) y sobrevive el `git reset` del refresh.

### CONTROL — Idempotencia "ya importada" (`tc_cartola_already_imported`)
- **Verifica:** ¿existe ya el archivo TC de esta tarjeta/moneda/mes? (mismo slug determinista).
- **Por qué:** avisar antes de sobrescribir — re-importar resetea las categorizaciones del mes.
- **Falla:** `already_imported=true` en el status → banner ámbar en la UI.

---

## 4. Contratos de datos

### 4.1. JSON canónico de cartola (`CartolaCanonicalV1`, `cartola_schema.py`, `extra="forbid"`)
```
{
  "schema_version": "1.0",                      // Literal
  "source": {                                   // stampeado server-side, NO de Gemini
    "bank_account_id": str, "bank_name": str, "account_label": str,
    "account_type": "tarjeta_credito|cta_corriente|cta_vista|cta_ahorro|linea_credito",
    "entity": str
  },
  "period": {"start": date, "end": date},       // end >= start (validado)
  "currency": "CLP|USD|EUR",
  "balances": {"opening": Decimal, "closing": Decimal},  // moneda nativa, convención estado (deuda +)
  "transactions": [{
    "line_no": int>=1,                          // único (validado)
    "date": date, "description": str,
    "amount": Decimal,                          // FIRMADO (− = outflow para el tenedor)
    "currency": "CLP|USD|EUR",                  // por-línea; puede diferir del top-level
    "raw": { "operation_type": str, "cuotas": "X/N", "merchant_country": str, ... }
  }],
  "extraction": {
    "model": str, "extracted_at": datetime,
    "warnings": [{"code": WarningCode, "line_no": int|null, "detail": str}]
  }
}
```
`WarningCode ∈ {DUPLICATE_LINE, ZERO_AMOUNT, LARGE_AMOUNT, LOW_CONFIDENCE, PARSE_AMBIGUOUS,
PERIOD_MISMATCH, BALANCE_MISMATCH}`. Se persiste en `imports/cartolas/_staging/{batch_id}.cartola.json`.

### 4.2. Discrepancia (`_meta/cartola-discrepancies.jsonl`, append-only, `build_discrepancy`)
```
{
  "schema_version": "1.0",
  "discrepancy_id": uuid4, "ts": iso8601, "batch_id": str,
  "bank_account_id": str, "year_month": "YYYY-MM"|null,   // período del ESTADO (6.5b)
  "state": str,                                            // uno de STATES / fx-*
  "source": "cartola"|"laudus"|null,                       // lado que tiene el dato cuando falta el otro
  "cartola": {"line_no", "date", "amount", "currency", "description"}|null,
  "laudus":  {"journal_entry_id", "date", "amount", "currency", "description"}|null,
  "fx": {"implied": num|null, "bcch": num|null, "deviation_pct": num|null},
  "resolution": null
}
```
**Línea de resolución** (append-only, referencia la original):
```
{"schema_version":"1.0", "ref_discrepancy_id": uuid4,
 "resolution": {"action", "resolved_by", "resolved_at", "justification", "escalated_at"?}}
```

### 4.3. Metadata de asientos TC (`_meta` en `tc_correction.py`)
Cada `data.Transaction` de `source=cartola-tc` lleva: `source:"cartola-tc"`, `bank_account_id`,
`batch_id`, `line`, `operation_type`, `period` (`YYYY-MM` del estado), `opening`, `closing`, `currency`
(nativos). `fx` solo si ≠ 1. `fx_source:"inherited:YYYY-MM"` solo si el fx se heredó. Si hubo categorización:
`match_source`, `confidence`, `color` (green/yellow/red, advisory), `category_status`
(`pending`|`suggested` — NUNCA `confirmed`: el contador confirma SIEMPRE).

### 4.4. Run-record (`_meta/reconciliation-runs.jsonl`)
```
{"schema_version":"1.0", "bank_account_id", "year_month", "reconciled_at",
 "matched": int, "differences": int, "blocking": int, "batch_id"}
```

### 4.5. FX BCCh EOM (`_meta/fx-bcch-eom.jsonl`, `fx_bcch_eom.py`)
```
{"schema_version":"1.0", "year_month":"YYYY-MM", "rate_clp_per_usd": float,
 "fetched_at": iso8601, "source":"mindicador-dolar-observado", "bcch_date":"YYYY-MM-DD"}
```
Dedup por `year_month`. `lookup_bcch(path, ym)` (mes exacto) / `latest_bcch(path)` (último cronológico).

### 4.6. Categorization history (`_meta/categorization-history.jsonl`, append-only)
```
{"ts": iso8601, "description_normalized": str, "corrected_category": str,
 "original_suggestion": str|null, "user": str}
```

### 4.7. `.beancount` generados en `imports/cartolas/`
- **cta corriente:** modelo A NO genera archivo (solo discrepancias). El `promote` legacy (Story 9.9)
  generaba `{bank}-{last4}-{YYYY-MM}.beancount` con dos postings balanceados + una `Balance` de cierre a
  `period.end + 1 día`; override convertía la `Balance` en `pad Discrepancias` + `balance`. (En modelo A
  vigente no se usa para cta cte.)
- **TC:** `{bank}-{last4}-{stem}-{YYYY-MM}-tc.beancount`. Asientos (a)/(b)/(c) en CLP; USD posteado en CLP
  con fx único (no price per-unit — la deuda se lleva materializada en CLP). Serializado con
  `render_entries` (`printer.format_entry`, determinista).

### 4.8. Endpoints
- `POST /api/v1/cartolas/upload` → 202 `{status, batch_id}`.
- `GET /api/v1/cartolas/{batch_id}` → `StatusResponse {batch_id, status ∈ (processing, ready, failed,
  confirming, confirmed, confirm_failed), canonical, error, result, already_imported}`.
- `PATCH /api/v1/cartolas/{batch_id}/validate-balance` `{opening, closing, override_justification?}` → 202
  `{status:"confirming", batch_id}`. Resultado por poll: `ValidateBalanceResponse` (cta cte) o
  `TcCorrectionResponse` (TC, con `cuadre: TcCuadre`).
- `GET /api/v1/reconciliation/discrepancies` `?state&year_month&bank_account_id&discrepancy_id` →
  `{discrepancies[], summary:{total, by_state}}`.
- `GET /api/v1/reconciliation/history/{id}`, `/count` → `{total, blocking}`, `/periods` →
  `PeriodStatus[]`.
- `POST /api/v1/reconciliation/discrepancies/{id}/resolve` `{action, justification?, category_account?}`.
- `POST /api/v1/reconciliation/discrepancies/resolve-batch` `{items:[{discrepancy_id, action,
  category_account?}], justification?}` (≤ `MAX_BATCH = 50`, todo-o-nada).
- `GET /api/v1/tc/reconciliation?card=<bank_account_id>[&year_month]` → `TcReconciliationRow[]`.
- `GET /api/v1/tc/cartolas` → `TcCartolaSummary[]` (matriz de cobertura).
- `GET /api/v1/categorization/pending` → `PendingTx[]`.

### 4.10. Plan de cuentas TC (mapping fijo, diseño Valentina 2026-06-20)
Ocho cuentas `Liabilities:EAG:TC:Real:*` (una por tarjeta-moneda con actividad 2026), derivadas por
`tc_real_account(expense_tc)` desde la cuenta-gasto Laudus. Cuenta-gasto (lump) → code → stem `TC:Real`
→ code sintético (espejo 2-prefix, verificado libre):

| Cuenta-gasto Laudus (lump) | code | `TC:Real` stem | code sintético |
|---|---|---|---|
| `Expenses:EAG:TC:Tc1027VisaInfinity` | 430005 | `Tc1027VisaInfinity` | 230005 |
| `...Tc1027VisaInfinityUs` | 430006 | `Tc1027VisaInfinityUs` | 230006 |
| `...Tc8996MastercardLanpass` | 430007 | `Tc8996MastercardLanpass` | 230007 |
| `...Tc8996MastercardLanpassUs` | 430008 | `Tc8996MastercardLanpassUs` | 230008 |
| `...Tc0858VisaLatanpass` | 430009 | `Tc0858VisaLatanpass` | 230009 |
| `...Tc0858VisaLatanpassUs` | 430010 | `Tc0858VisaLatanpassUs` | 230010 |
| `...TcVariasEag` | 430017 | `TcVariasEag` | 230017 |
| `...TcRaquelVentura` | 430019 | `TcRaquelVentura` | 230019 |

`Equity:Apertura:TarjetasSinDetalle` = code **311005**. **Amex 8083 (430011) se omite** (0 actividad 2026,
además es `CLP,USD` en UNA sola cuenta). Cargos bancarios (fijo, global) = `GastosBancarios-430003`.
**Cuenta puente Santander (pagos consolidados) = `ControlYLiquidación-115099`** (ver §8 nota 8).

**Mecanismo de exclusión de los reportes (crítico):** las `TC:Real` llevan `categoria1="PASIVO"` y las de
apertura `categoria1="PATRIMONIO"`, pero lo que REALMENTE las saca del reporte de gastos es tener
`Categoria2` **y** `Categoria3` **vacías** (caen al bucket `cat2[""]` que el reporte nunca lee, porque
agrupa TOTAL EGRESOS por `Categoria2 ∈ {DEPARTAMENTO SANTIAGO, Casa Sur, DEPARTAMENTO MIAMI, GASTOS
PERSONALES}`). Setear solo `Categoria1:"PASIVO"` es insuficiente y peligroso.

### 4.9. Acciones válidas por estado de discrepancia (`ACTIONS_BY_STATE`)
- `value-mismatch` (🔴): accept-cartola, accept-laudus, escalate.
- `missing-in-laudus`: confirm-cartola-only (ANOTA al ledger), escalate.
- `missing-in-cartola`: confirm-laudus-only, escalate.
- `date-mismatch`: accept-cartola-date, accept-laudus-date, escalate.
- `description-mismatch`: accept-cartola-description, accept-laudus-description, merge, escalate.
- `category-mismatch`: accept-cartola-category, accept-laudus-category, manual-category, escalate.
- `fx-out-of-tolerance` (🔴): accept-derived-fx, accept-bcch-fx, manual-fx, escalate.
- `escalate` siempre permitido (no cierra la discrepancia). `BLOCKING_STATES = {value-mismatch,
  fx-out-of-tolerance}` (chip rojo). Justificación ≥ 10 chars (excepto escalate).

---

## 5. Invariantes contables

1. **Balance de extracción:** `closing == opening + Σ(transactions.amount)` (±100 CLP en warning; exacto en
   confirm salvo override).
2. **TC:Real cierra a −closing×fx (C1):** el saldo acumulado de `Liabilities:EAG:TC:Real:<stem>` hasta el
   estado M == `−(closing_M × fx_M)`. Telescopeo exacto: el pago (b) de cada mes es el CLP real que canceló
   las compras del mes anterior (mismo CLP) → se anulan y sobrevive `−closing_M×fx_M`, con la apertura
   valorizada al CLP del pago que la salda.
3. **Postings balanceados:** todo asiento suma 0. El asiento (a) toca `TC:Real` por `−monto×fx` SIEMPRE
   (el pasivo cuadra con el closing sin importar el tipo de la contrapartida).
4. **Contigüidad (C2):** `apertura[M] == cierre[M−1]` por tarjeta y moneda nativa.
5. **Una pata de deuda por compra (C3):** exactamente 1 posting `TC:Real:` y ≥2 cuentas distintas por
   compra/cuota.
6. **Pago cartola == pago Laudus (C4)** y **lump residual ≈0 (C5)**.
7. **Laudus es la fuente contable para cta corriente:** el modelo A NO postea líneas de cartola encima
   (evita doble conteo). Solo `confirm-cartola-only` de `missing-in-laudus` escribe (a `manual/`).
8. **Una apertura por tarjeta.** **Ninguna línea de cartola TC se descarta** (no reconocida → Suspense).
9. **El FX nunca es el BCCh:** la tasa siempre sale del pago real (`CLP/USD`); el BCCh solo es gate de
   plausibilidad ±5%.
10. **Nada se auto-confirma:** las categorizaciones TC quedan `suggested`/`pending`; el contador confirma.
    `SUPRA_THRESHOLD = 30` ya NO es una compuerta a auto: es el termómetro del color (confianza histórica
    = `#confirmaciones / 30`).
11. **Regla de oro (diseño Valentina):** las correcciones se hacen SOLO con asientos Beancount estándar
    que el importer emite (como si un contador los tipeara a mano). NUNCA tocar el motor Beancount, el
    importer de Laudus, la metadata de cuentas existentes, ni la DB.
12. **Continuidad de los libros (IAS 21):** libro continuo, una sola apertura 2021-01-01, sin asiento de
    cierre anual. No agregar asientos de cierre.

---

## 6. Edge cases manejados

- **Gemini devuelve JSON truncado/no-parseable** → `GeminiExtractionError`, hasta 3 reintentos, luego
  `failed`.
- **BALANCE_MISMATCH persistente** → tras 3 draws se devuelve el mejor canónico válido con el warning
  (mismatch legítimo, no se oculta).
- **Shape inválido** → `ValidationError` sin reintentar; si un draw previo fue válido se devuelve ese.
- **Cuota pre-existente X/N (X≥1)** → se incluye con su fecha original; exenta de `PERIOD_MISMATCH`.
- **Cuota futura X=0** → excluida por el prompt.
- **Boundary slop de fecha (compra 1-5 días antes del período por corte)** → no dispara PERIOD_MISMATCH
  (umbral 80%); el matcher la alcanza por el pad ±3 días.
- **Pago consolidado Santander** (un asiento paga varias tarjetas, glosa nombra UNA con su USD ≠ el de
  esta) → fallback por monto con gate BCCh; elige el de fecha más temprana tras el cierre.
- **Mes revolving sin pago propio** → hereda fx del estado posterior contiguo (cadena ≤3 meses).
- **Cuenta USD (`...Us`) con cartola extraída como CLP** → guard de moneda bloquea (no postea a fx=1).
- **Sin BCCh de referencia** → falla segura, bloquea (no estima FX).
- **Re-import de la misma cartola** → mismo slug sobrescribe; `_opening_exists(exclude=out_file)` no pierde
  la apertura; `tc_cartola_already_imported` avisa (resetea categorizaciones).
- **CLP+USD de la misma tarjeta/mes** → slugs distintos por stem, no colisionan.
- **bean-check falla tras escribir** → rollback al snapshot previo (o unlink si nuevo), reason `bean-check
  failed`.
- **Job expira por TTL (1h) durante el confirm** → el ledger ya se modificó; se deja warning en logs.
  `set_confirming` revive el entry y renueva `created_at`.
- **Staging efímero (redeploy) + browser restaura sessionStorage** → 404 en el status → auto-limpia y
  vuelve al formulario.
- **Double-submit del confirm** → `set_confirming` devuelve False si ya hay uno en vuelo → 202 idempotente.
- **Discrepancia re-subida (batch_id nuevo)** → dedup por contenido, no duplica.
- **Cartola perfecta (0 diferencias)** → run-record igual (distingue de "nunca subida").
- **Crash entre push y append de resolución (batch)** → dedup por `ref_discrepancy_id` en el archivo
  `manual/`; el retry no re-appendea la tx (evita doble conteo) pero cierra la discrepancia.
- **`lump == 0` en un pago** → se saltea el asiento (b).
- **Apertura parcial (opening no saldado completo en esta cartola)** → fallback a `opening × fx` (posición
  de cambio abierta, se acepta el residuo).
- **Cartola vieja sin cierre persistido (import pre-6.6)** → la UI de cuadre no compara contra 0, pide
  re-importar.
- **`missing-in-cartola` de estado adyacente traído por el pad** → acotado al período core.

---

## 7. UX actual y sus dolores

Cuatro páginas, todas RBAC contador/admin, con marcada fricción de "muchas etapas manuales pegadas".

### 7.1. `CartolaUploadPage` (subir → extraer → confirmar → cuadre)
Flujo: elegir cuenta (select), elegir PDF, Subir → card de "Procesando" con poll → card "Cartola extraída"
con warnings + tabla de tx en `<details>` + panel de validación de balance (opening/closing editables +
justificación de override) → Confirmar → card "Confirmando" (poll) → resultado (✅ importada / ⛔ bloqueada)
+ panel de cuadre C1–C5.
**Dolores:**
- **Máquina de estados frágil expuesta al usuario:** processing / ready / failed / confirming / confirmed /
  confirm_failed, con múltiples cards de espera casi idénticas y lógica de "reintentar sin re-subir",
  "blip transitorio del poll no es terminal", "batch restaurado de sessionStorage puede apuntar a nada".
  El usuario ve `batch_id` crudos y rutas de staging (`ledger/imports/cartolas/_staging/`).
- **El contador tipea opening/closing a mano** aunque Gemini ya los extrajo — doble trabajo y fuente de
  error; el override con justificación ≥20 chars es un muro cuando la cartola genuinamente no cuadra.
- **"blocked" es un 200 con un ⛔:** confuso — parece éxito HTTP pero no se importó nada (bug real 8996 USD
  ×4). El motivo del bloqueo es un párrafo técnico ("sin pago Laudus que salde el estado…").
- **`already_imported` es un banner de advertencia**, no una barrera: se puede sobrescribir y perder
  categorizaciones sin confirmación fuerte.
- **El cuadre C1–C5 aparece recién post-confirmación**, cuando ya se posteó; si sale 🔴 "las herramientas
  para ajustarlo vienen en la próxima versión" — hoy no hay remediación, solo queda registrado.
- **Una cartola por vez**, sin cola ni batch de PDFs.

### 7.2. `ReconciliationPage` (dashboard cta cte)
Períodos reconciliados (tabla), filtros mes/cuenta, chips por estado, tabla de diferencias con checkboxes
(batch), y un DrillDown lateral (acción + justificación + autocompletado de categoría + historial).
**Dolores:**
- **Vocabulario de estados crudo** (`value-mismatch`, `missing-in-laudus`, `fx-out-of-tolerance`) expuesto
  como badges — el contador tiene que aprender la taxonomía interna.
- **El batch escala silenciosamente los estados ambiguos** (value/date/description/category) porque tienen
  2 acciones opuestas; el usuario selecciona N y solo M "se resuelven, el resto se escalan" — comportamiento
  poco obvio.
- **El DrillDown vuelca `cartola`/`laudus` como pares clave-valor genéricos** (`Section` con
  `Object.entries`), sin formato contable; los montos se muestran con `String(v)`.
- **Deep-link + selección manual + `deepLinkDismissed`** = lógica de apertura del panel confusa (bug
  histórico de reapertura al resolver).
- **Justificación ≥10 chars obligatoria** en casi toda acción — fricción para resoluciones obvias.

### 7.3. `TcReconciliationPage` (cuadre TC read-only)
Matriz de cobertura tarjeta×mes (emoji por celda), select de tarjeta, tabla mes×(C1–C5) con filas rojas
arriba, fila expandible con "Cascada de conciliación" + detalle por chequeo + movimientos, y una leyenda.
**Dolores:**
- **Read-only sin acciones:** muestra el descuadre 🔴 pero la única salida es "rechazá y volvé a importar"
  (que se hace en OTRA página) — no hay corrección inline.
- **Densidad alta:** cinco chequeos con emojis, dos representaciones del mismo cuadre (Cascada + "Detalle
  por chequeo"), `<details>` anidados; sobrecarga cognitiva.
- **La cascada re-deriva números en el cliente** (`saldoAnterior = |tc_real_balance − Σmovimientos|`),
  duplicando lógica del backend — riesgo de divergencia.
- **Refresh manual** ("Actualizar") porque los datos cambian al subir una cartola en otra página; no hay
  sincronización.
- **Terminología mixta:** "lump", "TC:Real", nombres de cuenta Beancount se filtran a la UI en partes.

### 7.4. `CategorizacionPage`
Lista de pendientes con badge de color (rojo/amarillo/verde advisory), autocompletado de cuenta por fila,
botón "Confirmar categorizadas (N)" que confirma en un commit las que salieron de Suspense.
**Dolores:**
- **Desconexión del resto del flujo:** tras importar una TC hay que ir a OTRA página a categorizar; el
  spinner "procesar una cartola recién importada tarda unos segundos" refleja el reload del ledger.
- **`Expenses:EAG:GastosVarios` y `Suspense` se tratan como "en blanco"** — el contador no ve por qué el
  picker arranca vacío.
- **El color es advisory pero el contador confirma SIEMPRE** — no hay auto-confirmación ni siquiera para
  `historical-30+`, lo que hace tedioso el alto volumen.
- **Sin agrupación por cartola/tarjeta/mes:** todas las pendientes mezcladas.

**Dolor transversal:** el trabajo de una sola cartola se reparte entre 3-4 páginas (subir → cuadre TC →
categorizar → resolver diferencias), sin un hilo que las conecte; el usuario ve internals (batch_id,
estados de matching, nombres de cuenta) y máquinas de estado de polling.

---

## 8. Notas para v2

Decisiones abiertas / mejoras que el código actual ya insinúa:

1. **Traspaso USD→CLP para el FX (diferido).** El asiento (b) y la vía-ii del traspaso USD→CLP para derivar
   el FX quedaron diferidos a story propia (`build_tc_correction_entries` comenta "vía-ii traspaso USD→CLP
   → diferida"). Hoy el USD se materializa en CLP con fx único; no hay un traspaso real que confirme dónde
   vive el USD. Ligado al **método multi-moneda IAS 21** (partida monetaria USD → dólar de cierre a cada
   fecha; dif. cambio → P&L). Ver `valentina-metodo-multimoneda-ias21-2026-07-18.md` y
   `valentina-tratamiento-saldos-usd-balance-2026-07-08.md`.
2. **Statement multi-mes.** `year_month = period.end` es un supuesto (las cartolas son mensuales); un estado
   que cruce meses cae al `period.end` (defer 6.5b documentado).
3. **Prefill de opening/closing.** Gemini ya los extrae; que el confirm los muestre pre-llenados en vez de
   pedirlos a mano.
4. **Remediación inline del cuadre 🔴.** Hoy la vista TC es read-only y el C1/C3 rojo solo se arregla
   re-importando desde otra página. v2 debería ofrecer "re-importar" / corregir desde el propio cuadre.
5. **Estados 2 de TC (con desglose real por línea) / conciliación línea-a-línea de la TC.** El matcher TC
   POSTEA (no matchea por línea; su problema es metadata, no matching); una conciliación por línea de la TC
   está diferida.
6. **Auto-confirmación de categorías de altísima confianza** (`historical-30+`, `confidence ≥ 0.85`) para
   bajar el volumen manual — hoy TODO se confirma a mano por decisión de diseño (revisar en v2).
7. **Detección server-side last4 vs PDF** (TODO 9.3 AC8): cuando los `bank_account_last4` reales estén
   poblados, re-evaluar un check de cuenta-equivocada (hoy diferido, no descartado).
8. **Wash de pago consolidado 0858 / `ControlYLiquidación-115099` (abierto, diagnóstico cerrado).** El
   Santander paga la 0858 en un asiento consolidado que reparte el pago entre `430009` (chico) y el puente
   `ControlYLiquidación-115099` (grueso); nuestra cartola revierte la apertura completa contra `430009`
   solo → el residuo (C5) es exactamente la pata del puente (feb `−4.252.472` exacto). **Reframe confirmado
   (hipótesis de Ary):** no es mecánica de pago — son **gastos de JAB/Fondo Común que EAG paga con su
   tarjeta por cuenta de ellos** (el contador los rutea a `ControlYLiquidación` porque para EAG son una
   cuenta por cobrar, no un gasto). Hoy nuestro desglose itemiza TODAS las compras 0858 como gasto EAG,
   incluidos los PAT de JAB → **sobre-declara EAG y duplica en la consolidación familiar**. Fix v2: la
   cartola debe distinguir PAT-por-cuenta-de-JAB (→ cuenta por cobrar / `ControlYLiquidación`) de gasto
   real EAG. Depende de conocimiento del contador (qué boleta es de qué propiedad — P1/P2/P3 en
   `valentina-preguntas-contadores-2026-07-21.md`). `tc_correction.py` ya tiene scaffolding de fallback por
   monto (~línea 46); guard: si no hay asiento consolidado que matchee, NO inventar el split. **Además la
   0858 USD (`430010`) es un problema DISTINTO:** nunca tuvo cartola importada (lump puro de Laudus desde
   2021); no existe `TC:Real:Tc0858VisaLatanpassUs` con data. Ver
   `valentina-fix-wash-0858-pago-consolidado-2026-07-21.md`.
9. **Extensiones del `BALANCE_MISMATCH`:** saldo corrido por línea, continuidad inter-cartola, invariantes
   no-aritméticos para cartolas de inversión (roadmap en `deferred-work.md`).
10. **Unificar el flujo en una sola superficie** que conecte subir → cuadrar → categorizar → resolver, sin
    exponer batch_id/estados internos/nombres de cuenta.
11. **Multi-moneda IAS 21 (doctrina adoptada, diseño de implementación pendiente).** Partida monetaria USD
    → dólar de cierre a cada fecha de balance; diferencia de cambio → RESULTADO (P&L), no patrimonio.
    Guardar unidades USD nativas + `price` directives (el `fx-bcch-eom.jsonl` YA es la tabla de precios);
    derivar el CLP en la capa de presentación (`CONVERT`/`VALUE` con la fecha explícita — beanquery usa el
    último precio por default, trap issue #54). **Pregunta abierta de mayor palanca (§7 del doc IAS 21):**
    cómo las cuentas USD-nativas del *overlay* REEMPLAZAN (no suman) al espejo Laudus CLP-congelado sin
    doble-conteo. Bug latente HOY: `bql_queries.py` colapsa todo no-CLP a 0 (`_clp()` + `paritytomaincurrency:
    1.0` hardcoded) → arreglar ANTES de cargar el primer saldo USD nativo. Ver
    `valentina-metodo-multimoneda-ias21-2026-07-18.md` y `valentina-tratamiento-saldos-usd-balance-2026-07-08.md`.
12. **La 8996 USD marzo / anomalía 51,3M CLP a MasterUs (2026-05-06):** dato anómalo (~57.000 USD, mucho
    más que el cierre) que Ary revisa con la cartola de abril; queda bloqueada correctamente (no se fuerza FX).

---

*Fin del documento. Fuentes de código citadas en cada sección; ver `pipeline/importers/`,
`backend/app/api/v1/{cartolas,reconciliation,tc_reconciliation,categorization}/`,
`backend/app/services/tc_cuadre.py`, `backend/app/integrations/`, y `frontend/src/pages/`.*
