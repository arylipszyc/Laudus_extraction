# Story 6.6: Vista de cuadre TC completa (C1–C5 + persistir apertura/cierre + `GET /tc/reconciliation`)

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **contador del family office**,
I want **una vista de cuadre por tarjeta × mes que muestre los cinco chequeos C1–C5 con semáforos y los números lado a lado (cartola vs. ledger vs. Laudus), respaldada por la apertura/cierre de cada cartola persistidos en el ledger**,
so that **pueda responder de un vistazo "¿la deuda de esta tarjeta en el ledger coincide con lo que dice la cartola?" — y cachar una corrupción (como el bug de categorización que destruyó la pata `TC:Real`) el mismo día que ocurre, en vez de descubrirla meses después cuando el saldo ya no cuadra**.

> **Contexto:** es el **paso 5** de la secuencia de materialización del desglose TC (`valentina-bug-categorizacion-destruye-tc-real-2026-07-02.md` → "Próximos pasos", ítem 5). Los pasos 1–4 ya están hechos: el fix de `_rewrite_file` (preservar patas `Assets:`/`Liabilities:`) está deployado, feb+mar se re-importaron y re-categorizaron, y el piloto BCI Visa Infinity 1027 CLP cierra en **−3.219.948 EXACTO** (C1 verificado a mano — memoria `project_epic6_reconciliacion_next` 2026-07-03). Esta story **materializa esa verificación como sistema**: la convierte en una vista que corre C1–C5 sola, sobre cualquier tarjeta y mes.

> **Continuación directa de la v1** (`88d1828`, `backend/app/services/tc_cuadre.py`). La v1 entregó **C1** (invariante de cierre) + el chequeo de pago (informal), calculados **inline** al postear (`validate-balance`, `status=corrected`) y mostrados en `CartolaUploadPage`. Esta story: (a) completa a **C1–C5**, (b) **persiste apertura/cierre** por cartola (hoy son efímeros — vienen solo en el request), (c) expone **`GET /tc/reconciliation`** para que la vista funcione fuera del momento del upload.

## Alcance / decisiones de diseño

### Por qué persistir apertura/cierre es el prerequisito #1

Hoy `compute_tc_cuadre` recibe `closing` **del request de `validate-balance`** ([router.py:213](backend/app/api/v1/cartolas/router.py#L213)). Una vez posteada la cartola, **apertura y cierre NO quedan en ninguna parte** — el `CartolaCanonicalV1` staged se borra tras el posteo ([tc_correction.py:539](pipeline/importers/tc_correction.py#L539) `staging.unlink`). Sin persistirlos, la vista **no puede cuadrar ningún mes que no se esté subiendo en ese instante**, y **C2 (contigüidad) es imposible** porque necesita el cierre del mes anterior. Es el prerequisito explícito del spec (`valentina-bug-...-2026-07-02.md` líneas 91-93, 119).

**Decisión (default de esta story): persistir como metadata en los asientos beancount al importar**, NO en un sidecar JSON ni en una DB. Razones:
- Respeta la **regla de oro** del modelo TC (`valentina-correccion-tc-cartolas-2026-06-20.md` §3): *"la corrección se hace exclusivamente con asientos contables estándar… no se toca el motor, ni el importer de Laudus, ni la base de datos"*.
- Es **idempotente por construcción**: re-importar la cartola sobrescribe el `*-tc.beancount` completo (mismo slug) → la metadata se refresca sola.
- El endpoint ya tiene que leer el ledger para los saldos → una sola fuente.
- El `_meta()` de [tc_correction.py:218](pipeline/importers/tc_correction.py#L218) ya estampa `period`, `fx`, `batch_id`, `bank_account_id` en **cada** asiento — agregar `opening`/`closing`/`currency` ahí es un cambio de una línea que cubre todas las cartolas (CLP y USD, todas las tarjetas).

**Granularidad:** estampar `opening`/`closing`/`currency` (moneda nativa de la cartola) en **todos** los asientos del batch, no solo en el asiento (c) de apertura — porque (c) se emite **una sola vez por tarjeta** ([tc_correction.py:317](pipeline/importers/tc_correction.py#L317) `emit_opening`) pero C1/C2 necesitan el opening/closing de **cada** mes.

### Moneda: USD vs. CLP (subtleza real — no ignorar)

Las cuentas `TC:Real:<stem>` y `TC:Real:<stem>Us` **ambas se postean en CLP** (los montos USD se convierten con `fx` en [tc_correction.py:284](pipeline/importers/tc_correction.py#L284) `clp = tx.amount * fx`). Pero `opening`/`closing` de la cartola están en la **moneda nativa** (USD para cartolas USD). Entonces:
- **C1** compara el saldo `TC:Real` (CLP) contra `−closing`. Para CLP `fx=1` → directo. **Para USD, C1 debe comparar contra `−(closing × fx)`** (el mismo `fx` del estado, ya persistido en la meta). La v1 comparaba contra `request.closing` crudo → **funciona solo para CLP** (el piloto era CLP). Esta story debe manejar el caso USD correctamente.
- **C2** compara `apertura[M]` vs `cierre[M−1]` — ambos en moneda nativa por tarjeta, comparación directa (no requiere fx).
- La vista debe **etiquetar la moneda** en cada fila (una `...Us` muestra USD; su `TC:Real` en CLP es informativo).

### Los 5 chequeos (autoritativos — `valentina-bug-...-2026-07-02.md` §"Chequeos de cuadre")

| Chequeo | Regla | Severidad | Fuente del dato |
|---|---|---|---|
| **C1 — Invariante de cierre** | `saldo TC:Real acumulado al cierre del mes == −closing de la cartola` (USD: `−closing × fx`) | 🔴 crítico | ledger (Σ patas `TC:Real` con `_month(date) ≤ ym`) + closing persistido |
| **C2 — Contigüidad** | `apertura de la cartola del mes == cierre de la cartola del mes anterior` (misma tarjeta) | 🟡 medio | opening/closing persistidos de M y M−1 |
| **C3 — Integridad del asiento** | toda `compra`/`cuota` (`source=cartola-tc`) tiene **una** pata `Liabilities:EAG:TC:Real:*` y **las dos patas NO son la misma cuenta** | 🔴 crítico | ledger (asientos del período) |
| **C4 — Pago vs Laudus** | el `pago` de la cartola (`operation_type=pago`) matchea por monto el/los asiento(s) de pago de Laudus del mes (banco→`Expenses:EAG:TC:<stem>-<code>`) | 🟡 medio | ledger (ya lo hace la v1) |
| **C5 — Lump residual** | el saldo del lump `Expenses:EAG:TC:<stem>-<code>` del mes quedó neteado (`≈ 0`) tras la cartola | 🟡 medio | ledger (Σ patas al lump en el mes) |

**C1 y C3 son los rojos.** C1 por sí solo habría hecho evidente el `+2.545.013` desde la primera cartola categorizada. C3 es el que detecta *directamente* el patrón del bug (categorizar reescribía **ambas** patas a `Expenses`, netéandose a 0 y borrando la deuda).

> **C5 es un indicador rezagado (aceptado):** inmediatamente post-import, antes de categorizar, el lump puede mostrar residual grande — es esperado, no un descuadre. Etiquetar "informativo: mejora a medida que se categoriza". No lo pintes rojo.

### Estado de fila (semáforo agregado)

- 🔴 **rojo** si C1 **o** C3 falla (corrupción/mal materializada — parar y revisar).
- 🟡 **amarillo** si algún 🟡 (C2/C4/C5) falla y ningún rojo.
- 🟢 **verde** si los cinco pasan.

### Fuera de scope (explícito)

- **Herramientas de corrección/ajuste** (que el contador arregle un descuadre desde la vista). La vista es **read-only** — surface el problema, no lo repara. El fix hoy es manual (rechazar + re-importar) o una story aparte. La v1 ya dejó el placeholder: *"Las herramientas para ajustarlo vienen en la próxima versión"* ([CartolaUploadPage.tsx:371](frontend/src/pages/CartolaUploadPage.tsx#L371)).
- **Enumerar meses faltantes** como filas explícitas. El endpoint lista **solo** cartolas importadas (con asientos `source=cartola-tc`). Un hueco lo delata **C2** cuando aparece el mes siguiente. Enumerar meses esperados requeriría un calendario tarjeta×mes → otra story.
- **Desbloquear las USD Santander** (Mastercard 8996 USD, Latanpass 0858 USD): bloqueadas por data sucia de Laudus (pago consolidado, misma glosa distinto CLP — `valentina-veredicto-desglose-tc-14cartolas-2026-06-29.md`). Si no hay cartola USD importada para esas, simplemente no aparecen filas. **No forzar** nada para destrabarlas (el bloqueo protege el pasivo). Si aparece una fila USD Santander, C4 la marcará 🟡 — correcto.
- **Cierre/sign-off de período TC** (equivalente a 6.5 para cuenta corriente). La TC no usa el JSONL de discrepancias modelo-A; su "cierre" es "C1–C5 verdes". Fuera de scope salvo necesidad nueva.

## Acceptance Criteria

1. **AC1 — Persistir apertura/cierre por cartola.** Al postear una cartola TC (`correct_tc_cartola` → `build_tc_correction_entries`), **cada** asiento emitido lleva en su metadata `opening`, `closing` (valores nativos de `model.balances`) y `currency` (`model.currency`), además del `period`/`fx`/`batch_id` que ya lleva. Re-importar la misma cartola (mismo slug) sobrescribe el archivo → la metadata se refresca (idempotente). No se introduce sidecar JSON ni DB.

2. **AC2 — Servicio de cuadre C1–C5 (puro).** Una función pura (extensión de `compute_tc_cuadre` o un módulo nuevo `tc_reconciliation`) recibe las `entries` del ledger + `tc_real_account` + `lump_account` + `year_month` y devuelve el resultado de **los cinco** chequeos con, por cada uno, `{ok: bool, ...números relevantes}`. Lee `opening`/`closing`/`currency`/`fx` **desde la metadata persistida** (AC1), con fallback al `closing` pasado explícito (para el path inline de `validate-balance`, que sigue teniéndolo en el request). C1 maneja USD (`closing × fx`). Sin regresión de los campos que la v1 ya devolvía (`c1_ok`, `tc_real_balance`, `closing`, `pago_cartola`, `laudus_payment_total`, `laudus_payments`, `pago_ok`).

3. **AC3 — C2 contigüidad end-to-end.** El servicio, dado un `year_month`, obtiene el `closing` del mes anterior (misma tarjeta) desde la metadata persistida y lo compara con el `opening` del mes actual. `c2_ok=true` si cuadran (tolerancia CLP 1 / USD 0.01 según moneda); si **no hay** cartola del mes anterior (primer mes o hueco), `c2_ok=false` con una razón distinguible (`"sin cartola anterior"`) — no crashea. Verificable con el piloto Visa Infinity 1027 CLP (feb→abr; mar presente ⇒ C2 pasa; si mar falta ⇒ C2 falla en abr, esperado).

4. **AC4 — C3 integridad del asiento.** Por cada asiento `source=cartola-tc` con `operation_type ∈ {compra, cuota}` del período, el chequeo verifica que exista exactamente una pata a `Liabilities:EAG:TC:Real:*` y que las dos patas del asiento **no** sean la misma cuenta. `c3_ok=false` con `corrupted_count > 0` si alguno viola. (Este es el que caza el bug de categorización directamente.)

5. **AC5 — C5 lump residual.** El chequeo suma las patas al `lump_account` (`Expenses:EAG:TC:<stem>-<code>`) fechadas en el `year_month` y reporta `residual` = ese saldo; `c5_ok = abs(residual) ≤ tolerancia`. Etiquetado informativo (🟡, no 🔴).

6. **AC6 — Endpoint `GET /tc/reconciliation`.** Nuevo endpoint (RBAC `contador`/`admin`) que, dado `?card=<stem o bank_account_id>` (y opcional `?year_month=YYYY-MM`), devuelve **una fila por cartola importada de esa tarjeta**: `{card, year_month, currency, cartola:{opening, closing, sum_compras, sum_pagos, sum_cargos, transactions[]}, ledger:{tc_real_balance_eom, tc_real_postings_sum}, laudus:{lump_account, lump_balance, payments[]}, checks:{c1..c5 con ok+números}, status}`. Enumera los períodos escaneando los asientos `source=cartola-tc` de esa `TC:Real` en el ledger (agrupados por `period`). Sin `card` → 422/400 con mensaje claro (o lista de tarjetas disponibles — ver Task 4). El endpoint **no** postea ni muta nada (read-only).

7. **AC7 — Vista frontend.** Página nueva (ruta + nav RBAC `contador`/`admin`, patrón de `ReconciliationPage`/`CuentasPendientesPage`) con una **tabla por tarjeta**: una fila por mes con los semáforos C1–C5 y los números lado a lado (cartola vs. ledger). Rojos arriba. Fila **expandible**: al abrir, la lista de movimientos de la cartola + el/los asiento(s) de Laudus del pago, para comparar a ojo. Selector de tarjeta. Moneda etiquetada. Sin toasts (estilo Cards/badges de 6.4). Consume `GET /tc/reconciliation`.

8. **AC8 — El panel inline usa el servicio completo.** `CuadrePanel` en `CartolaUploadPage` (post-import) muestra **los cinco** semáforos C1–C5 (hoy solo C1 + pago), reusando el mismo servicio de AC2 — sin duplicar lógica. El texto placeholder de "descuadre" sigue apareciendo solo si algún chequeo falla.

9. **AC9 — Tests.** Backend: la metadata `opening`/`closing`/`currency` se estampa en los asientos (AC1); el servicio da C1–C5 correctos incl. **caso USD** (C1 con `fx`), **C2 sin mes anterior**, **C3 con asiento corrupto** (dos patas a la misma cuenta → detecta), **C5 residual ≠ 0**; el endpoint agrupa por período y respeta RBAC. Frontend: component test de la tabla (al menos una fila 🟢 y una 🔴, semáforos y expandible). `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` → 0 regresiones nuevas (ojo: `test_fava_edit_validator` tiene 2 rojos PRE-EXISTENTES ajenos) + `npx tsc --noEmit` verde.

## Tasks / Subtasks

- [x] **Task 1 — Persistir apertura/cierre en la metadata** (AC1)
  - [x] En [tc_correction.py](pipeline/importers/tc_correction.py) `_meta(...)` (línea 218): agregar params `opening`, `closing`, `currency` y estamparlos (`m["opening"]=str(opening)`, etc.). Threadearlos desde `build_tc_correction_entries` (ya tiene `model.balances.opening/closing` y `model.currency`). Estampar en **todos** los asientos (a)/(b)/(c), no solo la apertura.
  - [x] Verificar que el render (`render_entries`) preserva la metadata nueva y bean-check sigue verde (los strings de metadata no rompen el parser).

- [x] **Task 2 — Servicio de cuadre C1–C5** (AC2, AC3, AC4, AC5)
  - [x] Extender [tc_cuadre.py](backend/app/services/tc_cuadre.py) `compute_tc_cuadre` (o crear `tc_reconciliation.py` que lo reuse) para computar C2, C3, C5 además de C1 + pago. Mantener las claves existentes (no romper la v1/schema/frontend).
  - [x] **C1 USD:** leer `fx` y `closing` de la metadata; comparar `TC:Real` (CLP) vs `−(closing × fx)`. Fallback: si viene `closing` explícito (path inline), usarlo.
  - [x] **C2:** función que, dado el `year_month` y la `TC:Real`, encuentra el `closing` persistido del mes anterior (scan de asientos `source=cartola-tc` con `period == mes−1` y esa cuenta) y lo compara con el `opening` del mes actual. `"sin cartola anterior"` si no hay.
  - [x] **C3:** iterar asientos `source=cartola-tc`, `operation_type ∈ {compra, cuota}`, `period == ym`; contar los que NO tienen exactamente una pata `Liabilities:EAG:TC:Real:*` o cuyas dos patas son la misma cuenta.
  - [x] **C5:** sumar patas al `lump_account` con `_month(date) == ym`; `residual` = saldo; `ok = abs ≤ _TOL`.
  - [x] Tolerancias por moneda (`_TOL=1` CLP; `0.01` USD para C2 en moneda nativa).

- [x] **Task 3 — Enumerador de períodos + endpoint `GET /tc/reconciliation`** (AC6)
  - [x] Módulo nuevo `backend/app/api/v1/tc_reconciliation/` (router `APIRouter(prefix="/tc", tags=["tc-reconciliation"])`, `GET /reconciliation`), registrado en [api/v1/router.py](backend/app/api/v1/router.py) (junto a los `include_router`). RBAC `require_role(["contador","admin"])`, `LedgerService` via `Depends(get_ledger_service)`.
  - [x] Servicio: dado `card` (stem o bank_account_id), derivar la `TC:Real` y la cuenta-lump (el `tc_real_account`/`expense_tc` — reusar `tc_correction.tc_real_account` o el `BankAccountResolver`), escanear las `entries` agrupando por `period` (los `source=cartola-tc` de esa cuenta), y por cada período llamar el servicio de Task 2 + armar los bloques `cartola`/`ledger`/`laudus`. Filtro opcional `year_month`.
  - [x] Schemas Pydantic de la respuesta (patrón de [cartolas/schemas.py](backend/app/api/v1/cartolas/schemas.py) `TcCuadre`/`TcLaudusPayment`). Reusar `TcLaudusPayment`.

- [x] **Task 4 — Vista frontend** (AC7)
  - [x] Servicio `frontend/src/services/tcReconciliation.ts` (patrón `fetch`+`credentials:'include'` de [reconciliation.ts](frontend/src/services/reconciliation.ts)) + tipos.
  - [x] Página `TcReconciliationPage.tsx`: selector de tarjeta, tabla por mes con semáforos C1–C5 (rojos arriba), números cartola vs. ledger, fila expandible (movimientos + asiento(s) Laudus). Reusar el estilo de `CuadrePanel` para el expandido. Ruta + nav RBAC (`contadorNavItems`/`RequireContador`, patrón de 9.8/9.12).
  - [x] Decidir el "listado de tarjetas": endpoint auxiliar o derivarlo de `/bank-accounts` filtrando las TC (las que resuelven a `Expenses:EAG:TC:*`). Default simple: derivar del front con `/bank-accounts`.

- [x] **Task 5 — Panel inline a C1–C5** (AC8)
  - [x] `CuadrePanel` en [CartolaUploadPage.tsx](frontend/src/pages/CartolaUploadPage.tsx#L340) + tipo `TcCuadre` en [cartolas.ts](frontend/src/services/cartolas.ts#L98) + `TcCuadre` en [schemas.py](backend/app/api/v1/cartolas/schemas.py#L37): agregar c2/c3/c5. El cómputo inline (router `validate-balance`, [router.py:211](backend/app/api/v1/cartolas/router.py#L211)) pasa por el servicio extendido (ya recarga el ledger con `ledger.load()`).

- [x] **Task 6 — Tests + verificación** (AC9)
  - [x] Backend: extender [test_tc_cuadre.py](backend/tests/test_tc_cuadre.py) (C2/C3/C5 + caso USD con fx) + test del enumerador/endpoint (agrupa por período, RBAC 401/403). Fixtures estilo `parser.parse_string` como la v1.
  - [x] Frontend: component test de `TcReconciliationPage` (fila verde + roja, semáforos, expandible).
  - [x] `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` + `npx tsc --noEmit`.

## Dev Notes

### Estado actual de los archivos que se tocan (leídos para esta story)

- **[backend/app/services/tc_cuadre.py](backend/app/services/tc_cuadre.py) — `compute_tc_cuadre` (v1, 91 líneas, puro)** — hoy computa **C1** (`tc_real_balance = Σ patas TC:Real con _month(date) ≤ ym`; `c1_ok = abs(tc_real_balance + closing) ≤ 1`) + **pago** (`pago_cartola` = patas TC:Real de asientos `source=cartola-tc, operation_type=pago` del mes; `laudus_payments` = asientos NO-cartola que tocan el `lump_account` con monto>0; `pago_ok` = |pago_cartola − Σlaudus| ≤ 1). Recibe `closing` explícito del caller. **`_TOL = Decimal("1")`**, `_month(d) = d.isoformat()[:7]`. **Extender aquí** (mismas convenciones de signo, no reinventar).
- **[pipeline/importers/tc_correction.py](pipeline/importers/tc_correction.py) — `build_tc_correction_entries` (línea 246) + `_meta` (218) + `correct_tc_cartola` (404)** — postea los asientos (a) compra/cuota/cargo/avance → `TC:Real` (−clp) / contrapartida (+clp); (b) pago → `expense_tc` (−lump) / `TC:Real` (+lump); (c) apertura (una vez) → `TC:Real` (−opening×fx) / `Equity:Apertura:TarjetasSinDetalle`. `_meta` YA estampa `source="cartola-tc"`, `bank_account_id`, `batch_id`, `line`, `operation_type`, `period` (=`model.period.end` YYYY-MM), `fx` (si ≠1), y color/confidence/match_source de categorización. **Agregar `opening`/`closing`/`currency` acá (Task 1).** `model.balances.opening/closing` y `model.currency` disponibles en `build_tc_correction_entries`.
- **[backend/app/api/v1/cartolas/router.py](backend/app/api/v1/cartolas/router.py#L197) — `validate_balance_endpoint`** — tras `status=corrected` hace `ledger.load()` y calcula el cuadre inline (líneas 205-215), popeando `tc_real_account`/`expense_tc_account`/`year_month` del `result` (el "plumbing" que agregó `correct_tc_cartola`, [tc_correction.py:437](pipeline/importers/tc_correction.py#L437)). El cuadre viaja en `TcCorrectionResponse.cuadre`. **No romper este path** (Task 5 lo enriquece).
- **[backend/app/api/v1/cartolas/schemas.py](backend/app/api/v1/cartolas/schemas.py#L37) — `TcCuadre`, `TcLaudusPayment`** — schema de respuesta actual (c1_ok, tc_real_balance, closing, pago_cartola, laudus_payment_total, laudus_payments, pago_ok). Ampliar con c2/c3/c5 (Task 5). Reusar `TcLaudusPayment` en el endpoint nuevo.
- **[frontend/src/pages/CartolaUploadPage.tsx](frontend/src/pages/CartolaUploadPage.tsx#L340) — `CuadrePanel`** — panel "Cuadre con la contabilidad" con `row()` (semáforo verde/rojo por chequeo), asientos Laudus expandibles, texto ⚠ descuadre / ✓ cuadra. Estilo a reusar en la tabla nueva.
- **[backend/app/api/v1/router.py](backend/app/api/v1/router.py) — montaje de routers** — `include_router` de cada módulo. Los que llevan `prefix` propio lo declaran en su `APIRouter` (ej. `reconciliation` = `prefix="/reconciliation"`). Agregar el `tc_reconciliation_router` acá.
- **[backend/app/api/v1/reconciliation/router.py](backend/app/api/v1/reconciliation/router.py) + [service.py](backend/app/api/v1/reconciliation/service.py)** — patrón de referencia para el módulo nuevo (router con `require_role`, `response_model`, servicio que lee del ledger/JSONL, `get_ledger_service`).

### Convenciones de cuentas (verificadas en código/tests, no en accounts.beancount)

- **Deuda real:** `Liabilities:EAG:TC:Real:<stem>` (CLP) y `<stem>Us` (USD) — **ambas se postean en CLP** (montos × fx). Ej. verificado: `Liabilities:EAG:TC:Real:TestCard`, y el piloto `Liabilities:EAG:TC:Real:Tc1027VisaInfinity`.
- **Lump Laudus (cuenta-gasto):** `Expenses:EAG:TC:<stem>-<code>` (ej. `Expenses:EAG:TC:TestCard-430005`). El `<code>` varía por tarjeta/moneda; **no hardcodear `430005`** — usar el `expense_tc_account` que resuelve el `BankAccountResolver` / `tc_correction.tc_real_account` (transforma `Expenses:EAG:TC:<stem>-<code>` → `Liabilities:EAG:TC:Real:<stem>`).
- **Apertura:** `Equity:Apertura:TarjetasSinDetalle` (una vez por tarjeta).
- Los códigos numéricos exactos y la metadata `laudus_categoria*` viven en `ledger/accounts.beancount` — leerlos de ahí si se necesitan; **no** replicar valores en código.

### Anti-patrones a evitar (aprendidos del bug 2026-07-02 y del proyecto)

- **NO** recomputar el saldo con BQL crudo si el servicio puro ya itera `entries` — reusar el patrón de `compute_tc_cuadre` (`ledger.entries()` en memoria, `_month(date)`), ya testeado.
- **NO** persistir en sidecar JSON ni DB (viola la regla de oro; introduce una segunda fuente que se desincroniza). Metadata en el asiento = idempotente vía re-import.
- **NO** forzar/estimar FX para destrabar cartolas USD Santander (memoria `project_epic6_reconciliacion_next`; el bloqueo protege el pasivo). La vista solo reporta.
- **NO** convertir opening/closing a CLP al persistir — guardar **nativo** + la moneda; el fx se aplica **al chequear** C1 (mantiene la cartola como fuente fiel y evita perder precisión).
- **NO** pintar C5 rojo (es rezagado por diseño). Solo C1 y C3 son rojos.
- **Regresión de categorización (C3 existe por esto):** categorizar debe reescribir **solo** la pata de resultado (`Expenses:`/`Income:`) y **preservar siempre** las patas `Assets:`/`Liabilities:` ([fix ya deployado](_bmad-output/planning-artifacts/valentina-bug-categorizacion-destruye-tc-real-2026-07-02.md)). C3 es la red que lo vigila; no re-introducir el patrón "reescribir por `bank_account_id`".

### Testing standards

- Backend: `pytest`, fixtures con `beancount.parser.parser.parse_string` (ledger inline), como [test_tc_cuadre.py](backend/tests/test_tc_cuadre.py). Correr con `PYTHONUTF8=1` (gotcha Windows del proyecto). Los 2 rojos `test_fava_edit_validator` son PRE-EXISTENTES — no atribuírselos a esta story.
- Frontend: `vitest` component tests, `npx tsc --noEmit` debe quedar verde.
- **Verificación de aceptación con datos reales (handoff Ary, no codeable):** correr la vista sobre el piloto Visa Infinity 1027 CLP (feb/mar/abr) y confirmar C1 verde con `TC:Real == −3.219.948` en abril; C2 verde si las tres están; C3/C5 verdes tras la re-categorización con el fix.

### Project Structure Notes

- Backend nuevo módulo: `backend/app/api/v1/tc_reconciliation/` (`router.py` + `service.py` + `schemas.py`), registrado en `api/v1/router.py`. Alinea con la organización por-recurso existente (`reconciliation/`, `cuentas_pendientes/`, `accounts/`).
- Frontend nueva página: `frontend/src/pages/TcReconciliationPage.tsx` + `frontend/src/services/tcReconciliation.ts` + ruta + nav (patrón `contadorNavItems`/`RequireContador`).
- El servicio puro de cuadre puede vivir en `backend/app/services/tc_cuadre.py` (extender) — es agnóstico del transporte, ya lo usa el router de cartolas y lo usará el endpoint nuevo.

### References

- [Source: _bmad-output/planning-artifacts/valentina-bug-categorizacion-destruye-tc-real-2026-07-02.md#Spec — Vista de revisión de cuadre TC] — **spec autoritativo**: bloques cartola/ledger/Laudus, tabla C1–C5, `GET /tc/reconciliation?card=<id>`, "persistir apertura/cierre", UI tabla-por-tarjeta con semáforos, "paso 5".
- [Source: _bmad-output/planning-artifacts/valentina-correccion-tc-cartolas-2026-06-20.md#3] — regla de oro (solo asientos estándar, no DB/motor/importer) + asientos (a)/(b)/(c) + §7 prueba de no-doble-conteo + §10.1 mapeo (nada se cae).
- [Source: _bmad-output/planning-artifacts/valentina-veredicto-desglose-tc-14cartolas-2026-06-29.md] — validación contra 14 cartolas reales, contigüidad (C2), USD Santander bloqueadas por data sucia, pagos Laudus por mes (glosa corrida un mes).
- [Source: _bmad/memory/agent-contadora/sessions/2026-07-02.md] — diseño de Ary (la vista es un paso del flujo, no página aparte, en v1; C1 el estrella; no persiste el cierre en v1) + el bug (categorizar tocaba la pata de deuda).
- [Source: git 88d1828] — v1 (`compute_tc_cuadre` C1 + pago, inline en validate-balance, `CuadrePanel`).
- [Source: memoria project_epic6_reconciliacion_next 2026-07-03] — piloto C1 verificado a mano (`−3.219.948` exacto); esta story = "COMPLETAR" la v1 (88d1828) al set C1–C5 + persistencia + endpoint.
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 6] — Epic 6 (Reconciliación Mensual, reformulado c4); esta story extiende el desglose TC de 6.2.

## Decisiones resueltas con Ary (2026-07-04)

Las cuatro cerradas antes del dev. **No re-litigar sin una necesidad nueva concreta.**

1. **Persistencia = metadata en el asiento** (NO sidecar/DB). `opening`/`closing`/`currency` en el `_meta` de cada asiento (a)/(b)/(c). Respeta la regla de oro, idempotente vía re-import, una sola fuente. → Task 1 tal cual.
2. **USD en C1 = nativo + `fx` al chequear.** Persistir opening/closing en **moneda nativa**; C1 compara `TC:Real` (CLP) vs `−closing×fx` usando el `fx` ya persistido. **No** guardar el CLP-equivalente (evita dato duplicado / recomputo en re-import). → Task 2 (C1 USD) tal cual.
3. **Listado de tarjetas = derivar en el front desde `/bank-accounts`** filtrando las que resuelven a `Expenses:EAG:TC:*`. **Sin** endpoint `GET /tc/cards`. → Task 4 default confirmado.
4. **Alcance frontend = página completa + panel inline.** La vista tabla-por-tarjeta con semáforos/expandible (AC7) **más** enriquecer el panel inline a C1–C5 (AC8) entran ambos en 6.6. No se difiere a 6.7. → AC7 + AC8 en scope.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Amelia, dev-story)

### Debug Log References

- `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` → **641 passed, 1 xfailed, 0 failed** (los 2 rojos `test_fava_edit_validator` que el storyfile anticipaba NO aparecieron — la suite quedó totalmente verde). Sin regresiones.
- `npx tsc --noEmit` (frontend) → verde.
- `npx vitest run` (frontend) → **66 passed** (6 archivos, incl. los 2 tests nuevos de `TcReconciliationPage`).
- `npx eslint` sobre los archivos nuevos/tocados → limpio.

### Completion Notes List

- **Task 1 — persistencia.** `opening`/`closing`/`currency` (moneda nativa) se estampan en `_meta()` de [tc_correction.py](pipeline/importers/tc_correction.py) → viajan en **cada** asiento (a)/(b)/(c) del batch. Idempotente vía re-import (mismo slug sobrescribe el archivo). Se persisten como strings (como el `fx` existente); `render_entries`/`printer.format_entry` los serializa y bean-check los re-parsea sin ruido (641 verde lo confirma).
- **Task 2 — servicio C1–C5.** [tc_cuadre.py](backend/app/services/tc_cuadre.py) `compute_tc_cuadre` reescrito para los 5 chequeos, **conservando las claves de la v1** (backward-compat: el test v1 y el schema siguen verdes). `closing` ahora es opcional: si no viene, se lee de la metadata persistida (`_statement_meta`); el path inline lo sigue pasando desde el request. **C1 USD**: compara `TC:Real` (CLP) vs `−(closing×fx)` con el `fx` de la meta. **C2**: `apertura[M]` vs `cierre[M−1]` (moneda nativa, tolerancia por moneda); `"sin cartola anterior"` si no hay previa. **C3**: scope por `bank_account_id` (detecta la pata TC:Real destruida aunque el asiento ya no toque la cuenta) con fallback por cuenta. **C5**: Σ patas al lump del mes ≈ 0. Semáforo agregado `status` (red si C1/C3, yellow si C2/C4/C5, green si todo).
- **Task 3 — endpoint.** Módulo nuevo `backend/app/api/v1/tc_reconciliation/` (`GET /api/v1/tc/reconciliation?card=<bank_account_id>[&year_month=]`, RBAC contador/admin, read-only). `build_rows` (puro) enumera períodos por `bank_account_id` y computa C1–C5 por mes + movimientos/Σs. El router resuelve la cuenta vía `BankAccountResolver` + `tc_real_account`; `UnknownBankAccount`→404, cuenta no-TC→400.
- **Task 4 — vista.** [TcReconciliationPage.tsx](frontend/src/pages/TcReconciliationPage.tsx) (tabla por tarjeta×mes, semáforos C1–C5, rojos arriba, filas expandibles con movimientos + pagos de Laudus + razones), [tcReconciliation.ts](frontend/src/services/tcReconciliation.ts), ruta `/cuadre-tc` (RequireContador) y nav "Cuadre TC". Selector de tarjetas derivado de `/bank-accounts` filtrando `account_type==="tarjeta_credito"`.
- **Task 5 — panel inline.** `TcCuadre` (schema backend + tipo frontend) ampliado a C1–C5; `CuadrePanel` en [CartolaUploadPage.tsx](frontend/src/pages/CartolaUploadPage.tsx) muestra los 5 semáforos + texto por `status`. Plumbing: `correct_tc_cartola` expone `cuadre_bank_account_id` y el router lo pasa a `compute_tc_cuadre` (scope de C3).
- **Nota de comportamiento (intencional):** la **primera** cartola de una tarjeta muestra C2 🟡 `"sin cartola anterior"` (no hay previa contra la cual verificar contigüidad) → el agregado sale amarillo aunque la deuda cuadre. Es honesto y coincide con el spec (C2 🟡 = falta un mes / salto). No es un descuadre.
- **Handoff Ary (no codeable, verificación con datos reales):** correr la vista sobre el piloto Visa Infinity 1027 CLP (feb/mar/abr) y confirmar C1 verde con `TC:Real == −3.219.948` en abril + C2 verde con las tres cartolas presentes.

### Change Log

- 2026-07-04 — Story 6.6 implementada (C1–C5 + persistir apertura/cierre + `GET /tc/reconciliation` + vista + panel inline). 6 tasks, 641 backend passed / 66 frontend passed, tsc+eslint verdes, 0 regresiones.

### File List

**Backend (modificados):**
- `pipeline/importers/tc_correction.py` — `_meta` estampa `opening`/`closing`/`currency`; plumbing `cuadre_bank_account_id`.
- `backend/app/services/tc_cuadre.py` — reescrito a C1–C5 (C2/C3/C5 + C1 USD), lee metadata persistida.
- `backend/app/api/v1/cartolas/schemas.py` — `TcCuadre` ampliado a C1–C5.
- `backend/app/api/v1/cartolas/router.py` — pasa `bank_account_id` al cuadre inline.
- `backend/app/api/v1/router.py` — registra `tc_reconciliation_router`.

**Backend (nuevos):**
- `backend/app/api/v1/tc_reconciliation/__init__.py`
- `backend/app/api/v1/tc_reconciliation/schemas.py`
- `backend/app/api/v1/tc_reconciliation/service.py`
- `backend/app/api/v1/tc_reconciliation/router.py`

**Frontend (modificados):**
- `frontend/src/services/cartolas.ts` — `TcCuadre` ampliado a C1–C5.
- `frontend/src/pages/CartolaUploadPage.tsx` — `CuadrePanel` a C1–C5.
- `frontend/src/App.tsx` — ruta `/cuadre-tc`.
- `frontend/src/components/layout/Sidebar.tsx` — nav "Cuadre TC".

**Frontend (nuevos):**
- `frontend/src/services/tcReconciliation.ts`
- `frontend/src/pages/TcReconciliationPage.tsx`
- `frontend/src/pages/TcReconciliationPage.test.tsx`

**Tests (modificados/nuevos):**
- `backend/tests/test_tc_cuadre.py` — +6 tests (C1 CLP/USD, C2, C3, C5).
- `backend/tests/test_tc_reconciliation.py` — nuevo (build_rows + RBAC + endpoint OK/404).

### Review Findings

Code review 3 capas adversariales (Blind Hunter + Edge Case Hunter + Acceptance Auditor) — 2026-07-04. Auditor: 9/9 ACs funcionalmente MET. 2 decision-needed, 1 patch, 7 defer, 10 dismiss.

- [ ] [Review][Decision→Valentina] **C1 USD: exacto en un mes, DRIFT multi-mes (consecuencia de la Decisión #2)** — Con montos sin redondear y fx constante, C1 USD de UN mes es exacto (Σcompras×fx = closing×fx). PERO el saldo `TC:Real` es acumulativo (`_month(date) ≤ ym`) y cada estado persiste su propio `fx`; la Decisión #2 fijó C1 = comparar `TC:Real` (CLP) vs `−closing×fx_actual`. En multi-mes eso da `residual ≈ closing_{M−1} × (fx_M − fx_{M−1})` (p.ej. BCI 1027 USD mar ≈ 465,59×(902−931) ≈ −13.502 CLP) → **falso rojo**, porque `TC:Real` quedó al fx histórico de cada mes y C1 lo compara contra el fx del mes actual. NO es corrupción. Resolverlo = **revisar la Decisión #2** (opciones: C1 en unidades USD nativas reconstruyendo por `fx` de cada asiento — exacto pero cambia la semántica del AC2/Decisión #2; o tolerancia escalada por fx — tapa el síntoma). Requiere a Valentina (dueña del spec). Edge menor adjunto: `fx=="0"` en la meta daría `closing_clp=0`. [tc_cuadre.py:63,104-105]
- [ ] [Review][Decision→Valentina] **AC6 — respuesta plana vs. forma documentada + `card` solo acepta bank_account_id** — El endpoint devuelve un `TcReconciliationRow` PLANO (c1_ok, tc_real_balance, opening, closing, closing_clp, movements, laudus_payments, status…); AC6 documenta una forma anidada `{cartola:{…}, ledger:{…}, laudus:{…}, checks:{c1..c5}}`. Todos los datos están, solo aplanados. Además AC6 dice `?card=<stem o bank_account_id>` pero `resolver.resolve(card)` solo acepta bank_account_id (un stem daría 404). Frontend pasa bank_account_id → sin daño hoy. **Pendiente-Valentina** (Ary 2026-07-04): confirmar si la forma plana le sirve o necesita los bloques separados. [tc_reconciliation/router.py:36-48]
- [x] [Review][Patch] **APLICADO 2026-07-04 — Sort `STATUS_WEIGHT` con fallback** [frontend/src/pages/TcReconciliationPage.tsx:40] — `(STATUS_WEIGHT[a.status] ?? 99) - (STATUS_WEIGHT[b.status] ?? 99)`: un status inesperado ya no produce `NaN` en el comparador (se hunde al fondo, no rompe "rojos arriba"). tsc verde, 13/13 tests TC verdes.
- [x] [Review][Defer] **C3 depende de que la meta del asiento sobreviva la corrupción** [tc_cuadre.py:125-137] — deferred, hardening. C3 solo evalúa asientos con `source=cartola-tc` + `period` + `operation_type∈{compra,cuota}` en la meta. El bug conocido (categorizar reescribía las patas, no la meta del asiento) SÍ lo caza (la meta sobrevive → `real_legs=0`). Un rewrite futuro que además borre esa meta evadiría C3. La red vale solo mientras la meta del asiento sea inmutable.
- [x] [Review][Defer] **C5 bucketea por fecha de tx; el resto enumera por `period` de metadata** [tc_cuadre.py:172-178] — deferred, matiz de diseño. C5 suma el lump por `_month(e.date)==ym` (como C1/C4), pero los períodos se enumeran por `meta["period"]`. Una compra de borde (28-abr en el estado de mayo) puede caer en un bucket distinto → residual fantasma o enmascarado. Matchea la definición date-based del spec; latente en bordes.
- [x] [Review][Defer] **`_statement_meta` devuelve el primer batch que matchea** [tc_cuadre.py:50-66] — deferred. Si coexisten dos batches del mismo período+tarjeta (stale + re-import parcial), lee uno arbitrario y C1/C2 comparan contra el estado equivocado. La idempotencia por slug (re-import sobrescribe el archivo) lo previene hoy; sin de-dup ni "último gana".
- [x] [Review][Defer] **`GET /tc/reconciliation` sin error boundary (asimétrico con el path inline)** [tc_reconciliation/router.py:46] — deferred. El path inline envuelve el cuadre en `try/except`; el endpoint corre `build_rows` (que hace `_prev_month`, `Decimal(str(meta[…]))`) sin protección → una metadata malformada en el ledger daría 500 y blanquearía la vista, en vez de degradar a fila roja/desconocida. Inputs hoy controlados por el importer (`strftime`, `str(Decimal)`).
- [x] [Review][Defer] **La apertura postea pata `TC:Real` (cuenta para C1) pero C3 no la inspecciona** [tc_cuadre.py:127] — deferred. `operation_type="apertura"` no está en `_CONSUMO_OPS` → una apertura corrupta daría C1 rojo / C3 verde, sin señalar el asiento culpable.
- [x] [Review][Defer] **`BankAccountResolver` se instancia y lee `accounts.beancount` sin caché ni manejo de archivo ausente** [tc_reconciliation/router.py:34] — deferred. Ledger fresco/sin el archivo → 500 en vez de error limpio.
- [x] [Review][Defer] **Sin test de tarjeta TC válida con cero cartolas** [test_tc_reconciliation.py] — deferred, gap de test. `build_rows` devolvería `[]`, pero el path resolver/`tc_real_account` se ejercita solo con el ledger de 2 cartolas. Tampoco hay assert directo de que `build_tc_correction_entries` estampe `opening`/`closing`/`currency` (AC1 se cubre indirecto vía fixtures del cuadre).

**Dismiss (10):** panel inline hardcodea `'CLP'` en C1/C4/C5 = correcto (`pago_cartola`/`laudus_payment_total`/`closing_clp`/`c5_residual` SON CLP: TC:Real y lump postean en CLP) · React key por `year_month` = `build_rows` dedup garantiza unicidad por período · `year_month` malformado en el query NO crashea (`periods &= {year_month}` filtra; `_prev_month` solo recibe períodos de metadata) · C2 compara closing declarado vs. real = por diseño (C1 cubre el ledger) · C2 cross-currency = CLP/USD son `tc_real_account` distintos, ya filtrados · C4 `Decimal(str(sum(floats)))` = tolerancia 1, inocuo · `fmt` moneda minúscula = ya cae a CLP con regex · movimiento corrupto muestra amount 0 = UX menor · selectedCard stale → 404 = UX menor · C3 pata a tarjeta equivocada = con scope por bank_account_id los asientos son de esta tarjeta.
