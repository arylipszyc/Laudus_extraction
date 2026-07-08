# Veredicto contable — B6: saldos USD invisibles en el balance

**Autora:** Valentina 💰 · 2026-07-08
**Estado:** propuesta — Ary decide (y se confirma cuando entren los saldos USD reales)
**Bug técnico:** `bql_queries.py:46-53` (`_clp()` colapsa toda unidad ≠ CLP a 0,0) + `:164`
(`paritytomaincurrency: 1.0` hardcodeado). **Bug LATENTE** — hoy 0 postings con unidades USD en el
ledger (todas las cartolas TC-USD se guardan ya convertidas a CLP con `fx:` en metadata). Se dispara
cuando entren saldos USD-nativos de banco/inversión.
**Doctrina previa relevante:** `valentina-story-brief-fx-revolving-tc-usd-2026-07-06.md` (§ FX),
MEMORY §"Apertura USD al fx del pago que la salda" (2026-07-04), §12.1.

---

## 1. La pregunta de negocio

Cuando entren los saldos USD vivos de estas 5 cuentas —

| Cuenta | Tipo |
|---|---|
| `Assets:EAG:Bancos:BancoBci18565743Us` | cta corriente USD |
| `Assets:EAG:Bancos:BancoBci110014172UsMiami` | cta corriente USD |
| `Assets:EAG:Bancos:BancoCityNBank30000771265` | cta corriente USD |
| `Assets:EAG:Inversiones:BancoJuliusBaer03133171` | inversión USD |
| `Assets:Jocelyn:Inversiones:FmBciDlarCash` | inversión USD (hija) |

— el dueño mira el balance y pregunta **"¿cuánta plata tengo?"**. Hoy la respuesta sería **cero** para
esas cuentas (colapsan a 0,0). Eso no es un redondeo feo: es un activo real que desaparece del
patrimonio. El balance mentiría por omisión. Ese es el daño a corregir.

Y una segunda pregunta que el dueño de un family office con plata afuera **sí** se hace: *"¿cuánto de
lo mío está en dólares?"* — la exposición cambiaria. El tratamiento tiene que responder las dos.

## 2. Por qué la doctrina de la deuda TC NO se traslada a un activo USD vivo

Es la parte fina, así que la dejo explícita para no re-litigarla.

**Para la DEUDA de TC en USD** rechacé el dólar BCCh de mercado y usé el **CLP real del pago que la
salda** ("el fx sale del pago que lo salda; sin pago no se estima"). El fundamento era concreto: la
deuda **se cancela con un evento de caja real**. Existe un CLP que *alguien efectivamente pagó*. Meter
un dólar de mercado ahí inventaría un número que nadie pagó y dejaría deuda fantasma (el caso de la
apertura 1027 USD: 98.736 de dif. de cambio sobre un dólar de mercado que jamás pasó por la cuenta).

**Un activo USD vivo es el caso OPUESTO:**

- **No hay pago que lo salde.** Una cuenta con US$100.000 en el Julius Baer no se "cancela" con nada —
  es un saldo que *está ahí*, vivo, en moneda extranjera. No existe ningún evento de caja CLP al cual
  anclar. La técnica de la TC (anclar al pago real) **no tiene input**: no hay pago.
- **Su valor en pesos ES una pregunta de mercado.** "¿Cuánto valen esos US$100.000 en CLP?" solo tiene
  una respuesta honesta: *lo que me darían si los convirtiera al tipo de cambio de la fecha del
  balance*. Para un activo líquido en moneda extranjera, el dólar observado **no es un número
  inventado — es el número correcto.** Es exactamente el input que para la deuda TC era veneno y que
  para el activo vivo es la verdad.

**El principio que distingue los dos casos** (y que quiero que quede en memoria): *¿hay un evento de
caja que fija el CLP, o es una posición de mercado abierta?* Si hay caja → CLP real del pago (TC). Si
es posición abierta → tipo de cambio de cierre (activo USD vivo). No es contradicción; es la misma
regla —"valorizá con el número más fiel a la realidad económica"— aplicada a dos realidades distintas.

Esto es además consistente con la norma chilena y con IAS 21: las **partidas monetarias** en moneda
extranjera (efectivo, cuentas por cobrar, fondos líquidos) se valorizan al **tipo de cambio de
cierre**. Un activo USD vivo cae de lleno en esa categoría.

## 3. Las 3 opciones, evaluadas

| | Opción | Cuadra el balance en CLP | Muestra exposición USD | Depende de FX | Veredicto |
|---|---|---|---|---|---|
| (a) | Pata USD nativa, sin convertir (columna USD aparte) | ❌ **no totaliza** — no se puede sumar US$ + CLP | ✅ | no | Necesaria como **detalle**, insuficiente como respuesta |
| (b) | Convertir a CLP al **BCCh EOM del período** (dólar observado, `fx-bcch-eom.jsonl`) | ✅ | (solo si se preserva a) | sí, EOM | ✅ **base recomendada** |
| (c) | Convertir al **último FX conocido** | ✅ aprox. | — | sí, último | Solo **fallback** cuando el mes del balance aún no tiene EOM publicado |

**(a) sola no sirve para la pregunta principal.** Un balance de family office chileno se lee **en
pesos** — el dueño quiere UN número de patrimonio. Una columna USD separada que no suma dentro del
total deja la pregunta "¿cuánto tengo?" sin responder. Pero **(a) es imprescindible como detalle**:
sin las unidades USD nativas visibles, la exposición cambiaria se pierde y el número CLP se vuelve
falsa precisión (un total que parece exacto pero que se movió solo por el dólar).

**(c) es un fallback, no la política.** Usar "el último FX que tengo" para un balance a fin de mayo
cuando existe el EOM de mayo es peor que usar el de mayo. (c) solo tiene sentido para un balance
*interino* del mes en curso, cuyo EOM todavía no se publicó.

## 4. Recomendación: **HÍBRIDO (b) + (a)** — total en CLP al dólar de cierre, con el USD nativo a la vista

**La política:**

1. **Guardar el saldo en unidades USD nativas en el ledger** (NO convertir al importar). Para un activo
   vivo no hay pago del cual derivar un fx, y —clave— convertir al importar **congela** el valor al
   dólar del mes de carga y nunca se revaloriza. Un activo vivo debe reflejar la exposición de *cada*
   fecha de balance, no la del día que se cargó.
2. **Convertir a CLP en la capa de presentación** (la query del balance), aplicando el **BCCh EOM
   (dólar observado) del mes de la fecha del balance**, leído de `ledger/_meta/fx-bcch-eom.jsonl`. La
   misma cuenta se revaloriza sola al consultar distintos cierres de período — que es justo lo que un
   activo de mercado debe hacer.
3. **Presentar dual:** una columna **"Saldo (CLP)"** que totaliza el balance (family office lee en
   pesos) **+ el detalle nativo** por línea USD: `US$ X · fx Y · = CLP Z`. Así el número cuadra, la
   exposición cambiaria queda visible, y cada CLP es auditable (de dónde salió el dólar). Nada de
   falsa precisión.

**Por qué en la capa de presentación y no convirtiendo al importar** (decisión arquitectónica, no solo
de display): el ledger debe seguir siendo **espejo fiel de Laudus**. Laudus **no revaloriza** (0 price
directives, mismo hallazgo de la auditoría de inversiones 2026-06-20). Si convertimos al importar y
guardamos CLP, estampamos una revalorización que Laudus no hizo y rompemos el espejo. Guardando USD
nativo y convirtiendo al leer, el ledger no inventa nada y el balance muestra el equivalente CLP de
cierre como **cálculo de presentación**, no como asiento.

**FX correcto para un activo USD vivo:** **dólar observado BCCh de fin del mes de la fecha del
balance** (`rate_clp_per_usd` de `fx-bcch-eom.jsonl`; ej. balance al 31-05-2026 → 892,89). **Sí es
aceptable acá aunque lo rechacé para la deuda TC** — ver §2: para la deuda había un pago real que lo
hacía fantasma; para el activo vivo no hay caja y el mercado ES la respuesta fiel. El dólar observado
es además el estándar chileno para valorizar partidas monetarias en ME.

**Nota:** esto NO toca el tratamiento de la deuda TC en USD (que se sigue guardando en CLP al fx del
pago que la salda, doctrina intacta). B6 es **solo** para los activos USD-nativos de banco/inversión.
No hay conflicto: son los dos lados de la regla de §2.

## 5. El riesgo de re-valorización (diferencia de cambio) — reconocer o no

**Sí existe y hay que nombrarlo.** Un activo USD valorizado al dólar de cierre **cambia su valor en
CLP cada período aunque no entre ni salga un solo dólar.** Ejemplo con los EOM reales:
US$100.000 quietos valen CLP 93.157.000 a marzo (931,57) y CLP 89.289.000 a mayo (892,89) — una
**pérdida de presentación de CLP 3.868.000 sin que se movió nada.** Eso es **diferencia de cambio no
realizada.**

**Mi recomendación: NO reconocerla como asiento (no bookear ganancia/pérdida de cambio en el ledger).**

- Coherente con la doctrina de la auditoría de inversiones: **Laudus no revaloriza y no fabricamos
  revalorización que él no hizo.** Bookear una dif. de cambio rompería el espejo-Laudus, igual que
  bookear la ganancia de fondos a valor cuota lo rompería.
- Con el modelo del §4, la dif. de cambio **aparece sola** en el total CLP moviéndose período a
  período — es visible sin inventar un asiento. Se **muestra**, no se **postea**.
- Reconocerla contra resultado (opción "B" del framing) inflaría/desinflaría un P&L que el contador no
  reconoce → descuadraría la paridad. No vale.

Así que: valorización de cierre en presentación **sí**; asiento de diferencia de cambio en el ledger
**no** — hasta que Laudus/el contador la reconozca y entonces la **espejamos**, no la anticipamos.

## 6. Impacto técnico (para dev, no es mi dominio pero lo acoto)

- `_clp()`: dejar de colapsar. Cuando el Inventory trae unidades USD, devolver el número USD nativo +
  el código de moneda (no forzar a 0,0).
- Balance query: para cada línea, si la moneda ≠ CLP, multiplicar por el EOM del mes de `date_to`
  (fallback: último EOM disponible → esto es la opción (c) como red de seguridad del mes en curso).
- `paritytomaincurrency: 1.0` hardcodeado (`:164`): reemplazar por el EOM real cuando la moneda es USD.
- Tipo `BalanceSheetRecord` + `BalanceSheetPage.tsx`: agregar `currency`, `native_amount`, `fx_used`.
  Columna "Saldo (CLP)" totaliza; el nativo `US$ X @ Y` va como detalle de la línea USD.
- Sin cuentas nuevas, sin tocar el árbol. La deuda TC USD (en CLP) no se toca.

## 7. Decisiones para Ary / a confirmar cuando entren los saldos reales

1. **¿El balance del contador valoriza estas cuentas USD al dólar de cierre, o a costo histórico?**
   Es la única pregunta que puede cambiar mi recomendación. Si su balance de referencia usa costo
   histórico (o un dólar contable distinto al observado), tenemos que **espejarlo** para que la
   paridad cierre — la fidelidad a Laudus manda sobre mi preferencia por el dólar de cierre. **Spot-
   check obligatorio del CLP convertido contra el estado del custodio/contador cuando llegue el primer
   saldo real.** (Mismo espíritu que la auditoría de inversiones: no asumir que Laudus está bien.)

2. **¿Diferencia de cambio: mostrar y punto, o algún día reconocerla?** Mi recomendación es mostrarla
   (se ve sola en el total) y **no** bookearla mientras Laudus no lo haga. Si el contador la reconoce,
   la espejamos. Confirmar que estamos de acuerdo en no anticiparla.

3. **Menor — ¿dólar observado EOM es el que usa el contador?** Es lo que tenemos (`fx-bcch-eom.jsonl`,
   mindicador/BCCh) y es el estándar de partidas monetarias. Si el contador usa otro (p.ej. dólar
   acuerdo o de cierre bancario), es un cambio de fuente de una línea, no de doctrina.

**Prioridad:** el bug es latente (0 USD hoy), así que esto **no es urgente** hasta que se decida cargar
saldos USD-nativos. Pero cuando se cargue **sin este fix, el balance mostrará esos activos en cero** —
es un descuadre silencioso grave, no un detalle cosmético. Fix antes de importar el primer saldo USD.
