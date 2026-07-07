# Bug crítico — categorizar una compra TC destruye la pata `TC:Real` + spec de vista de cuadre

**Fecha:** 2026-07-02
**Autora:** Valentina (asesora financiera LAUDUS)
**Para:** Ary + Moishe/dev
**Severidad:** ALTA — corrupción silenciosa de datos del pasivo TC

> ✅ **RESUELTO el mismo día** (anotado en code-review 2026-07-06): fix en commit `9f0c2f3` — categorizar
> reescribe solo la pata de resultado y preserva las patas `Assets:`/`Liabilities:`, exactamente el fix
> recomendado abajo (`_resolve_bank_target` fue eliminado del código en el proceso). Feb+mar
> re-importados y re-categorizados; C1 verificado: `TC:Real:Tc1027VisaInfinity == −3.219.948` exacto.
> La vista de cuadre (spec de la 2ª mitad) se implementó como story **6.6** (commit `2e17b45`, deployada).
> El análisis de abajo queda como registro histórico — los "Próximos pasos" ya se ejecutaron todos.

---

## TL;DR

El piloto BCI Visa Infinity 1027 CLP (feb/mar/abr) NO cerró en −3.219.948 sino en **+2.545.013**.
No es un problema del modelo contable ni de la extracción. Es un **bug en la categorización**:
confirmar/categorizar una compra TC **reescribe las DOS patas del asiento a la misma cuenta de gasto**,
anulándose entre sí y **borrando la pata `Liabilities:EAG:TC:Real:*`** (la deuda).

- **abril** (aún sin categorizar) conserva sus 29 patas `TC:Real` ✓
- **feb** (12 compras) y **mar** (25 compras) ya categorizadas → pata `TC:Real` destruida ❌
- Los **pagos** no se categorizan, así que su pata `TC:Real` sobrevive → por eso el saldo quedó positivo
  (entraron los 3 pagos pero solo las compras de abril).

---

## Evidencia

Una compra de febrero ya categorizada, postings completos:

```
2026-02-02 * "PAYU *UBER TRIP SANTIAGO"
  operation_type: "compra"
  category_status: "confirmed"
  Expenses:EAG:TC:TcVariasEag-430017  -22042.0 CLP
  Expenses:EAG:TC:TcVariasEag-430017   22042.0 CLP    ← las 2 patas a la MISMA cuenta → neto 0
```

Debería ser:
```
  Liabilities:EAG:TC:Real:Tc1027VisaInfinity  -22042.0 CLP   (la deuda — SE PRESERVA)
  Expenses:EAG:TC:TcVariasEag-430017           22042.0 CLP   (el gasto — SE RECATEGORIZA)
```

Postings a `TC:Real` por archivo (verificado con beancount, 0 errores de carga):

| Cartola | Compras → TC:Real | Compras destruidas | Σ deuda perdida |
|---|---|---|---|
| febrero | 0 de 12 | **12** | ≈ 2.724.712 |
| marzo | 0 de 25 | **25** | ≈ 2.014.151 |
| abril | 29 de 29 ✓ | 0 | 0 |

Saldo `Liabilities:EAG:TC:Real:Tc1027VisaInfinity` = **+2.545.013** (esperado −3.219.948).
Gap ≈ 5,76M = compras feb+mar borradas (+ cuotas).

---

## Causa técnica (para Moishe/dev)

En `backend/app/api/v1/transactions/service.py`, `_rewrite_file` decide qué pata reescribir con
`p.account != bank_target`, donde `bank_target = _resolve_bank_target(entry)`.

`_resolve_bank_target` resuelve el `bank_account_id` de la tarjeta → **la cuenta de gasto lump
`Expenses:EAG:TC:Tc1027VisaInfinity-430005`** (esa cuenta tiene `bank_account_last4: "1027"`), NO
`Liabilities:EAG:TC:Real:*`. Como NINGUNA de las dos patas del asiento TC es `430005`, la condición
`!= bank_target` es verdadera para AMBAS → se reescriben las dos → la pata de deuda se destruye.

En una cartola de banco normal (cta cte) esto funciona porque `bank_account_id` sí resuelve a la pata
`Assets:Bank` real. La TC lo rompe porque su pata de deuda (`TC:Real`) es una cuenta DERIVADA por
nombre, no la que resuelve el `bank_account_id`.

**Fix recomendado:** categorizar debe reescribir **solo la pata de resultado** (`Expenses:`/`Income:`
— la Suspense/categoría) y **preservar siempre** las patas `Assets:`/`Liabilities:`. O sea, la regla de
qué pata cambiar no debe depender de `bank_account_id`, sino de que la pata sea la cuenta de gasto/ingreso.
Esto arregla TC y sigue siendo correcto para cartolas de banco.

**Impacto en datos:** feb y mar están corruptos (patas `TC:Real` borradas). Tras el fix, hay que
**re-importar feb y mar** (idempotente por slug) y **re-categorizar** con el categorizador arreglado.
abril está sano pero aún sin categorizar — NO categorizar más hasta que el fix esté deployado, o se
seguirá destruyendo deuda.

---

## Spec — Vista de revisión de cuadre TC (para que esto no vuelva a pasar en silencio)

**Pregunta que responde:** "¿la deuda de esta tarjeta en el ledger coincide con lo que dice la cartola?"
Un contador tiene que poder verlo de un vistazo, sin abrir Beancount.

### Alcance: por **tarjeta × mes** (una fila por cartola importada)

Columnas / bloques a mostrar:

1. **Cartola (estado de cuenta)** — lo que dice el banco:
   - Apertura, Cierre, Σ compras, Σ pagos, Σ cargos. **⚠ Hoy apertura/cierre NO se persisten** — hay
     que guardarlos en el asiento al importar (metadata del archivo de la cartola) para poder mostrarlos.
     Sin esto, la vista no puede cuadrar. Es el prerequisito #1.
   - Lista de movimientos (compra/pago/cuota/comisión) con monto.

2. **Ledger (lo posteado)** — lo que quedó en Beancount:
   - Saldo `Liabilities:EAG:TC:Real:<tarjeta>` **al cierre del mes** (point-in-time).
   - Σ de las patas `TC:Real` de ese período (compras, pagos, cargos).

3. **Laudus (el lump)** — el pago que registró Laudus:
   - El/los asiento(s) `Expenses:EAG:TC:<tarjeta>-4300xx` del mes (el pago lumpeado banco→TC).
   - Saldo residual del lump (debería tender a 0 a medida que las cartolas lo supersedan).

### Chequeos de cuadre (los semáforos que importan)

| Chequeo | Regla | Si falla |
|---|---|---|
| **C1 — Invariante de cierre** | `saldo TC:Real al cierre == −closing de la cartola` | 🔴 la cartola no está bien materializada (ESTE bug lo habría cacheado) |
| **C2 — Contigüidad** | `apertura de la cartola == cierre de la cartola anterior` | 🟡 falta un mes / hay un salto → el saldo del pasivo se desfasa |
| **C3 — Integridad del asiento** | toda compra/cuota tiene una pata `Liabilities:TC:Real` (ninguna con las 2 patas iguales) | 🔴 categorización corrompió el asiento |
| **C4 — Pago vs Laudus** | el `pago` de la cartola matchea (glosa+monto) un asiento de pago de Laudus del mes | 🟡 el pago no concilia con el banco |
| **C5 — Lump residual** | el lump `430005` del mes quedó neteado (≈0) tras la cartola | 🟡 quedó gasto lumpeado sin desglosar |

C1 y C3 son los críticos (rojos). C1 por sí solo habría hecho evidente el +2.545.013 desde la primera
cartola categorizada.

### Datos / endpoints necesarios

- **Persistir apertura/cierre** por cartola (prerequisito, hoy no existe).
- Endpoint `GET /tc/reconciliation?card=<id>` que por tarjeta×mes devuelva: {apertura, cierre, Σs de la
  cartola, saldo TC:Real al cierre, Σ patas TC:Real del período, lump del mes, resultado de C1–C5}.
- Fuente: los archivos `ledger/imports/cartolas/*-tc.beancount` (movimientos) + BQL sobre `TC:Real` y
  `430005` (saldos) + `imports/laudus/*` (pago Laudus para C4).

### UI (mínimo útil)

Tabla por tarjeta: una fila por mes con los semáforos C1–C5 y los números lado a lado (cartola vs ledger).
Expandible: al abrir una fila, la lista de movimientos de la cartola y el/los asiento(s) de Laudus del pago,
para comparar a ojo. Rojos arriba.

---

## Próximos pasos (orden)

1. **Dev/Moishe:** arreglar `_rewrite_file` (preservar patas Assets/Liabilities). Deployar.
2. **NO categorizar más TC** hasta que el fix esté en prod (o se sigue destruyendo deuda de abril).
3. Re-importar feb + mar (idempotente) → re-categorizar con el fix.
4. Verificar C1: `TC:Real == −closing` en las 3. Recién ahí el piloto cierra en −3.219.948.
5. Persistir apertura/cierre por cartola → construir la vista de cuadre (C1–C5).
