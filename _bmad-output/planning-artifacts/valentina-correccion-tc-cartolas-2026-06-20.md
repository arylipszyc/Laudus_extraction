# Corrección contable de Tarjetas de Crédito vía import de cartolas

**Autor:** Valentina (asesora financiera) · **Fecha:** 2026-06-20 · **Owner:** Ary
**Estado:** Diseño acordado. **BASE implementada 2026-06-20** (ver nota); la corrección con cartolas sigue pendiente del flujo de import.

---

> **NOTA 2026-06-20 — base implementada (cambia los paths de este diseño):**
> Las cuentas TC originales ya **NO** son `Liabilities:EAG:TC:*` — pasaron a **`Expenses:EAG:TC:*`**
> (gasto, tal cual Laudus) en el ledger vivo (PR #19, ver `docs/handoff-tc-gasto-2026-06-20.md`). El
> override viejo que las forzaba a Pasivo se sacó. Esto **no cambia la contabilidad** de este diseño,
> pero sí los **paths**:
> - El **asiento (b)** del §6 ahora **saca el gasto falso de `Expenses:EAG:TC:<code>`** (la cuenta
>   original, ahora gasto), no de `Liabilities:EAG:TC:<code>`.
> - El destino de la **deuda real** sigue siendo una cuenta nueva `Liabilities:EAG:TC:Real:*` (§9).
> - **Estado interino** (tarjeta/período sin cartola): la TC queda como **gasto** en su cuenta
>   `Expenses:EAG:TC` original — antes el §1 decía que era pasivo-con-metadata-gasto; ahora es
>   directamente gasto, más simple y fiel a Laudus.

---

## 1. Problema

En Laudus (y por lo tanto en el espejo Beancount, una vez que el importer quede bien armado) las
tarjetas de crédito están mal contabilizadas:

- Las **compras individuales no se registran**. Solo se registra el **pago mensual** de la tarjeta
  (`Assets:Bancos -X` / `Liabilities:EAG:TC:...  +X`).
- Las cuentas `Liabilities:EAG:TC:*` existen como pasivo en el árbol Beancount, **pero su metadata
  dice `laudus_categoria1: "GASTOS - EGRESOS"`**. Como el reporte agrupa por esa categoría, el
  **pago mensual se lee como el gasto** de la tarjeta (lumpeado, sin detalle).

Diagnóstico verificado contra el histórico Laudus 2021-2022: de 568 movimientos que tocan cuentas
TC, **566 son pagos y solo 2 son compras**. El saldo de las cuentas TC queda absurdamente positivo
(deuda debería ser negativa en Beancount). Confirma: se registran pagos, no compras.

## 2. Objetivo

Cuando se importe la cartola (estado de cuenta) de una tarjeta, corregir la contabilidad de esa
tarjeta para ese período:

- Las **compras** del detalle de la cartola pasan a ser el **gasto real itemizado**.
- El **pago** de la tarjeta pasa a ser un **movimiento entre cuentas** (banco → tarjeta), no un gasto.

## 3. Restricción de diseño (regla de oro)

> La corrección se hace **exclusivamente con asientos contables estándar** (transacciones Beancount
> normales que emite la funcionalidad de import), **como si un contador ingresara asientos a mano**.
> **No se toca** el motor de Beancount, ni el importer de Laudus, ni la metadata de las cuentas
> existentes, ni la base de datos. Esto evita introducir bugs.

Corolarios:

- El importer de Laudus deja Beancount = Laudus, fielmente. Eso se queda así.
- **Mientras una tarjeta/período no tenga cartola importada, su asiento queda tal cual** (gasto en la
  cuenta TC original de Laudus). Es el estado interino aceptado.
- La corrección es **por tarjeta y por período** — solo donde efectivamente hay cartola.

## 4. Alcance

- Se importan **solo cartolas de 2026 en adelante** (2026 es el arranque de un proceso continuo).
- Pre-2026: intacto, espejo Laudus, gasto en las cuentas TC originales.

## 5. Modelo objetivo (convención de signo Beancount: pasivo deuda-negativa)

**Compra** (fuente de verdad = cartola; ya implementado por `_build_postings` en `cartola_pdf_importer.py`):
```beancount
2026-03-24 * "PAYU *UBER EATS"
  Liabilities:EAG:TC:Real:Tc8996MastercardLanpass   -5069 CLP    ; ↑ deuda real
  Expenses:EAG:<categoría>                            5069 CLP    ; gasto itemizado
```

**Pago** (movimiento entre cuentas, NO gasto):
```beancount
2026-04-09 * "Pago TC 8996"
  Liabilities:EAG:TC:Real:Tc8996MastercardLanpass   17045465 CLP  ; ↓ deuda real
  Assets:EAG:Bancos:BancoSantander63188824-111009  -17045465 CLP  ; sale del banco
```
Nota: el pago **ya existe en Laudus** como `Banco → TC original`. No se vuelve a tocar el banco
(ver asiento (b), que solo reclasifica).

## 6. Los asientos de corrección (lo que emite la funcionalidad de import)

Por cada tarjeta, al importar su cartola de 2026:

### (a) Compras itemizadas
Una transacción por línea `raw.operation_type ∈ {compra, cuota}` de la cartola:
```beancount
Liabilities:EAG:TC:Real:<tarjeta>   -<monto> CLP
Expenses:EAG:<categoría>             <monto> CLP
```
Granularidad: **una transacción por compra** (para drill-down en Fava).

### (b) Reclasificación del pago — saca el gasto falso, no toca el banco
Por cada línea `raw.operation_type == pago` (la "MONTO CANCELADO", monto negativo en la cartola).
Fechada **el mismo mes del pago** (calza con el pago de Laudus del mismo mes):
```beancount
Liabilities:EAG:TC:<tarjeta>-<code>        -<Q> CLP   ; saca el +Q que dejó el pago de Laudus (cuenta-gasto)
Liabilities:EAG:TC:Real:<tarjeta>           <Q> CLP   ; ↓ deuda real
```
La línea `pago` de la cartola **no genera una compra**; es el mismo evento que el pago de Laudus.
(El matching engine 9.6b debe asegurar que el pago se reconcilie y no se emita dos veces.)

### (c) Apertura — una sola vez por tarjeta, en su primera cartola
Toma `balances.opening` de la primera cartola 2026 (deuda arrastrada de 2025):
```beancount
Liabilities:EAG:TC:Real:<tarjeta>   -<opening> CLP   ; deuda real inicial
Equity:Apertura:TarjetasSinDetalle   <opening> CLP   ; posición inicial (NO gasto)
```
**La contrapartida va a `Equity`, no a `Expenses`.** El `opening` es consumo de 2025 (deuda previa),
o sea posición inicial, no gasto de 2026. Mandarlo a un gasto inflaría el gasto 2026.

## 7. Por qué no hay doble conteo ni fuga (prueba de la suma anual)

Gasto 2026 después de la corrección, por tarjeta:
```
  Σ pagos 2026        ← lo que puso Laudus (lump, como gasto)
− Σ pagos 2026        ← asiento (b): los saco de la cuenta-gasto
+ Σ compras 2026      ← asiento (a): las itemizo
+ opening → Equity    ← asiento (c): aporta 0 al gasto
─────────────────────
= Σ compras 2026      ✓ exactamente el consumo real de 2026
```
Como se importa **todo** 2026, cada pago cancelado por (b) tiene sus compras itemizadas en alguna
cartola del set. Sin diferido (todo se fecha en el mes del evento). Sin descuadre (cada asiento
balancea por construcción).

## 8. Bordes

- **Entrada (1-ene-2026):** resuelto por el asiento (c) → `Equity`. El consumo 2025 arrastrado es
  posición inicial, no gasto 2026.
- **Salida (dic-2026 pagado en ene-2027):** se arregla solo. Como el proceso es **continuo**, al
  importar la cartola de ene-2027 el asiento (b) cancela ese pago. No requiere asiento de cierre.
  (Solo haría falta un asiento de cierre si 2026 fuera un piloto que se detiene — no es el caso.)
- **Tarjetas sin cartola / períodos sin cartola:** intactos, gasto en la cuenta TC original.

## 9. Estructura de cuentas requerida

Cuenta de pasivo "real" bien categorizada, **por tarjeta**:
- Nombre: `Liabilities:EAG:TC:Real:<tarjeta>` (convención a confirmar).
- Metadata: `laudus_categoria1: "PASIVO"` (NO "GASTOS - EGRESOS"), para que el reporte no la cuente
  como gasto.
- Se crea por el **flujo sancionado** de cuentas (`_new-accounts-pending.beancount` →
  `POST /cuentas-pendientes/{code}/promover`, Story 10.3). No se edita metadata de cuentas existentes.

`Equity:Apertura:TarjetasSinDetalle` también debe abrirse (open directive).

## 10. Mapeo cartola → asientos

| Campo cartola | Uso |
|---|---|
| `transactions[].raw.operation_type == compra/cuota` | asiento (a) compra |
| `transactions[].raw.operation_type == pago` (monto negativo) | asiento (b) reclasif. pago |
| `balances.opening` (primera cartola del card) | asiento (c) apertura |
| `transactions[].raw.card_suffix` | identifica la tarjeta física; **una cartola JSON puede traer varios suffixes** → separar por tarjeta |
| `source.bank_account_id` → `bank_account_resolver` | resuelve la cuenta Beancount destino |

## 11. Pendientes a confirmar / fuera de este diseño

- **Categorización real de las compras** (asiento a): hoy `NoopCategoryPredictor` manda todo a
  `Expenses:EAG:Suspense`. Story 9.7 lo reemplaza. La calidad del reporte de gastos depende de esto.
- **Convención de nombre** de las cuentas `TC:Real` (confirmar con Ary).
- **USD / FX**: cartolas en USD usan la FX implícita derivada (Story 9.6b). Aplica igual al modelo,
  con `build_usd_postings`.
- **Reconciliación pago cartola ↔ pago Laudus**: el matching engine (9.6b) debe garantizar que el
  pago se cuente una sola vez (estado `perfect`/`missing-in-cartola`), no emitir el pago dos veces.
- Verificar el diagnóstico contra el estado **corregido** del importer de Laudus (no contra el
  estado actual, que aún no es confiable).
