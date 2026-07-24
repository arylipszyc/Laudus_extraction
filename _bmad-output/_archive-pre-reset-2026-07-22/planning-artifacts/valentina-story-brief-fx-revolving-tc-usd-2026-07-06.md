# Story Brief — FX para meses revolving en TC USD (fx heredado del estado que absorbe)

**Autora:** Valentina 💰 · 2026-07-06
**Estado:** propuesta — Ary decide
**Contexto previo:** `valentina-veredicto-desglose-tc-14cartolas-2026-06-29.md` (§ "no forzar un FX"),
regla §12.1 (el FX del estado sale del pago real que lo salda; sin pago → bloquear, nunca estimar),
modelo MONTO CANCELADO (sessions/2026-06-22).

---

## 1. El caso

**Mastercard 8996 USD, marzo 2026.** El estado cerró en US$2.234,84 y **nadie pagó ese cierre**: el
saldo rodó al estado de abril (revolving). El importer bloquea con razón: *"sin pago Laudus que salde
el estado (USD 2.234,84) en 75d tras el cierre 2026-03-24"*. No hay pago propio → no hay ancla de FX
→ §12.1 dice bloquear. **El bloqueo es correcto. Lo incompleto es que el pago SÍ existe — llegó por
otro camino.**

La cadena real (verificada contra el ledger, no teoría):

| Estado | Apertura USD | Cierre USD | Pago que lo salda | FX derivado |
|---|---|---|---|---|
| Febrero | 14.774,29 | 1.387,63 | $1.291.675 (06-03, Laudus) | **930,85** ✓ importado |
| **Marzo** | 1.387,63 | 2.234,84 | **ninguno propio — rodó** | ⛔ bloqueado |
| Abril | 2.234,84 | 57.024,47 | $51.301.494 (08-05, Laudus) | **899,64** ✓ importado |
| Mayo | 57.024,47 | 1.217,42 | $1.124.166 (08-06, Laudus) | **923,40** ✓ importado |

El cierre de abril (57.024,47) **contiene adentro el saldo de marzo**. El pago de mayo
($51.301.494) pagó abril Y marzo juntos, a 899,64. **Los dólares de marzo tienen un costo CLP real:
899,64.** No hace falta estimar nada.

**Consecuencia hoy:** C1 rojo en abril y mayo por **$718.919** (= pago-de-feb $1.291.675 que el
archivo ausente de marzo no reclasifica, menos los movimientos de marzo 2.234,84×899,64 =
$2.010.594 que no están en el pasivo). Nota de precisión: el hueco NO son "compras por US$847,21" —
847,21 es solo el neto cierre−apertura; los movimientos del mes son ~US$2.234,84 (el pago de feb
cancela la apertura dentro del período de marzo).

## 2. La aritmética que decide (telescopio)

Con marzo importado a fx `f`:

- Post-marzo: `TC:Real = −2.234,84 × f` → **C1 de marzo verde con CUALQUIER `f`** (el pago de feb
  entra como asiento (b) al CLP real $1.291.675 y cancela exacto el cierre de feb — telescopio).
- Abril es puente puro (0 pagos): aporta `−(57.024,47 − 2.234,84) × 899,64 = −49.290.943`.
- **C1 de abril verde ⟺ `2.234,84 × f + 49.290.943 = 57.024,47 × 899,64` ⟺ `f = 899,64`.**

**Un único fx deja toda la cadena en verde: el del estado que absorbió el saldo.** No es coincidencia
— es §12.1 aplicado transitivamente: "el fx sale del pago que salda; el pago que saldó marzo es el de
abril". BCCh (931,57) dejaría C1 rojo perpetuo de ~$71.359 (2.234,84 × 31,93) con un dólar que nadie
pagó.

## 3. Opciones

| | Opción | Cuadre C1 | Naturaleza del número | Veredicto |
|---|---|---|---|---|
| **A** | **FX heredado del estado que absorbe** (marzo hereda 899,64 de abril) | **Verde toda la cadena, por construcción** | Costo REAL pagado (08-05) | ✅ **Recomendada** |
| B | Ancla dólar BCCh del mes, marcada "estimada" | Rojo perpetuo ~$71k en abril+ | Estimación de mercado que nadie pagó | ❌ Rompe §12.1 y no arregla nada |
| C | Status quo: marzo afuera, C1 rojo documentado | Rojo conocido $718.919 en abril/mayo | — | Aceptable como fallback; el reporte de gastos pierde los movimientos de marzo (~US$2.234) |

**Por qué A y no B:** no es una preferencia — es la única con cuadre exacto, y además es la más
honesta contablemente: valoriza la deuda a lo que costó saldarla (misma doctrina que la apertura
USD, decisión 2026-07-04: "valorizar al CLP real del pago que la salda"). B introduce un número
estimado en el pasivo Y deja el semáforo rojo. Lo peor de los dos mundos.

**Por qué A y no C:** C ya lo tenemos gratis. A recupera: C1/C2 verdes en toda la 8996 USD, los
movimientos de marzo al reporte de gastos (hoy invisibles), y sienta la regla para cualquier tarjeta
que ruede en el futuro (con deuda en aumento, va a pasar de nuevo).

## 4. Diseño de la Opción A — regla y ACs

**Regla (extensión de §12.1, no excepción):** si un estado M no tiene pago que salde su cierre en la
ventana (75d), pero existe un estado M+1 **contiguo** (apertura de M+1 == cierre de M, misma cuenta)
con **fx propio ya derivado de un pago real**, entonces `fx(M) = fx(M+1)` — heredado, transitivo
(si M+1 también rodó, hereda de M+2, etc.), y **auditable en metadata**.

ACs propuestos:

1. `derive_statement_fx`: agotadas las vías actuales (glosa, fallback por monto), buscar el estado
   siguiente contiguo YA IMPORTADO de la misma cuenta; si tiene fx propio → heredar. Metadata nueva
   en los asientos: `fx_source: "inherited:2026-04"` (hoy los importados no la necesitan; los
   heredados la llevan SIEMPRE — trazabilidad de dónde salió el dólar).
2. **El gate BCCh ±5% aplica igual al fx heredado** (899,64 vs BCCh marzo 931,57 = −3,4% ✓ pasa).
   Si el heredado cae fuera del gate → seguir bloqueando (algo raro pasó; falla segura).
3. Si el estado siguiente NO está importado → seguir bloqueando pero con mensaje accionable:
   *"el saldo rodó al mes siguiente sin pago propio — importá primero YYYY-MM y reintentá"*.
   (Orden de import: el mes revolving se importa DESPUÉS del que lo absorbe. Hoy abril ya está →
   marzo es desbloqueable de inmediato.)
4. Herencia transitiva con tope (sugiero 3 meses — más que eso es deuda impaga de verdad y debe
   quedar bloqueada, no maquillada).
5. **No tocar:** flujo CLP, tarjetas con pago directo (anti-regresión 1027 USD y toda la suite
   actual), el asiento (b) al CLP real, el modelo MONTO CANCELADO, la apertura al fx del pago que
   la salda.
6. Tests con los números REALES de la 8996 USD (este brief §2): feb 930,85 / marzo hereda 899,64 /
   abril puente / mayo 923,40 → C1 verde en los 4 meses, `TC:Real final == −1.217,42×923,40 =
   −1.124.166`.

**Invariantes C1–C5 esperados post-import de marzo:**

| Chequeo | Antes (hoy) | Después |
|---|---|---|
| C1 feb | 🟢 | 🟢 |
| C1 marzo | — (no existe) | 🟢 por construcción |
| C1 abril / mayo | 🔴 $718.919 | 🟢 exacto |
| C2 abril | 🟡 "falta mes anterior" | 🟢 cadena contigua |
| C3 | 🟢 | 🟢 (sin cambio) |
| C4 marzo | — | 🟢 pago feb $1.291.675 == Laudus 06-03 (un pago, dos roles en estados adyacentes — doctrina MONTO CANCELADO, ya sancionada) |
| C5 marzo | — | neteo del lump 03-2026 (mecanismo existente) |

## 5. Qué NO romper (línea roja §12.1)

- El FX **nunca** se estima. Heredar ≠ estimar: el fx heredado salió de un pago real de Laudus.
- BCCh sigue siendo **solo gate de cordura**, jamás fuente del fx.
- Sin cadena de pago real (deuda que a HOY nadie pagó) → **sigue bloqueando**. La falla segura se
  mantiene; solo se le enseña al matcher un camino de pago que hoy no ve.

## 6. Relación con la 0858 Latanpass USD (retirada del ledger)

Problema DISTINTO: ahí el pago existe pero el matcher no lo atribuye (asientos consolidados
Santander, glosa inconsistente) — esa es la story del fallback por monto (veredicto 2026-06-29, ya
diseñada). Esta story (revolving) no la arregla, pero **ambas comparten el gate BCCh** y juntas
cubren los dos modos de falla de las USD Santander. Sugerencia de secuencia: esta primero (más
chica, aritmética cerrada), la 0858 después.

## 7. Decisión para Ary

- **A (recomendada):** story acotada, `derive_statement_fx` + metadata + mensaje + tests con datos
  reales. Deja la 8996 USD 100% verde y el gasto de marzo en el reporte.
- **C (fallback):** no hacer nada; C1 rojo $718.919 queda documentado como limitación conocida y
  marzo fuera del reporte de gastos.
- B queda descartada con fundamento (§3).
