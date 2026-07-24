# Método estándar multi-moneda (IAS 21) para patrimonio histórico que cuadre con cartola

**Autora:** Valentina 💰 · 2026-07-18
**Origen:** conversación con Ary + deep-research verificado (24/25 claims confirmados vs fuente primaria IFRS.org IAS 21 y docs Beancount).
**Estado:** método adoptado a nivel de doctrina. Falta diseño de implementación (mini-diseño Julius Baer → brief de epic).

---

## 0. La pregunta que originó esto

Ary quiere que un **reporte de patrimonio a cualquier fecha pasada** muestre el valor de cada cuenta
**cuadrando con la cartola** de origen (banco/custodio), tanto en CLP como en USD. Y poder responder
"¿cuántos dólares había en esta cuenta hace 5 meses?".

Disparador: B6 (saldos USD "invisibles"). Al investigarlo se destapó que es un síntoma de algo mayor —
**Laudus es un libro de flujos en CLP, no un estado de patrimonio a valor real** (ver §1).

---

## 1. Diagnóstico del estado actual (verificado en datos)

- **EAG y FFCC son libros CONTINUOS:** una sola apertura (2021-01-01, plug `Liabilities:*:Apertura-211005`),
  **sin asiento de cierre de ejercicio**. Ingresos/gastos acumulan desde 2021 sin resetearse. → Beancount
  nativo funciona así; NO agregar asientos de cierre (rompería el espejo y pelearía con Beancount).
- **Las 5 cuentas USD ya tienen datos, pero TODO en CLP:** los movimientos de Laudus entraron
  **ya convertidos a CLP al dólar del día de la transferencia** (ej. Julius Baer: USD 200.000 → 155.600.000
  = fx 778; el USD vive solo en la glosa como texto). **No hay ninguna unidad USD en el ledger.**
- **Consecuencia:** el saldo de esas cuentas hoy es una **pila de pesos de tasas mezcladas**, que no es ni la
  posición real en USD ni el valor CLP de hoy. Nunca se revalorizó (mismo hueco que la auditoría de
  inversiones). Ejemplo real: BCI USD 18565743 muestra hoy **−8.501.348 CLP** = saldo negativo imposible en
  una cuenta de dólares = "Error B" de la auditoría de inversiones, causado por no contabilizar la dif. de cambio.
- **La apertura es un PLUG, no patrimonio real.** Cualquier activo no cargado en la apertura (offshore,
  inversiones a mercado) simplemente no existe. Laudus responde "por dónde pasó la plata", no "cuánto tengo".

## 2. El método estándar: IAS 21 / NIC 21 (= ASC 830)

Regla central (IAS 21.23), la que hace que el patrimonio histórico cuadre con la cartola:

> Una **partida monetaria** en moneda extranjera (caja, cuentas por cobrar/pagar, deuda TC en USD) se
> retraduce a la moneda funcional (CLP) al **tipo de cambio de CIERRE de cada fecha de balance.**
> Nunca a un dólar congelado de la transacción.

- **Monetario → tipo de cambio de cierre** a cada fecha (caja USD, deuda TC USD).
- **No-monetario a costo histórico → tipo de cambio de la transacción** (no revaloriza).
- **No-monetario a valor razonable → tipo de cambio de la fecha de la valorización.**

**Tres monedas:** transacción (USD) · funcional (CLP, la nuestra) · presentación (CLP). Nuestro caso es
**REMEDICIÓN por método temporal** (entidad CLP con partidas USD), NO traducción de presentación.

**Diferencias de cambio → RESULTADO (P&L), no patrimonio.** [CORRECCIÓN de lo que dije antes en la charla:
la ruta a OCI/CTA-patrimonio es SOLO para traducir los estados de una operación extranjera con moneda
funcional propia — no aplica a nosotros.] Realizada = cuando se mueve el cash; no-realizada = revalorizar
el saldo abierto a una fecha de reporte. **Ambas van a P&L** en nuestro caso.

## 3. Implementación en Beancount (patrón de la comunidad, verificado)

Dos capas ortogonales:

| Capa | Qué hace | Herramienta |
|---|---|---|
| **1. Cantidad** | Afirmar que las unidades USD del libro = las de la cartola | `balance` assertion (por moneda) |
| **2. Valorización** | Convertir esa cantidad a CLP al dólar de la fecha | `price` directives + `CONVERT`/`VALUE` |

```beancount
; Caja/banco USD → a VALOR NOMINAL (no a costo {})
2026-02-10 * "Transferencia a Julius Baer"
  Assets:EAG:Offshore:JuliusBaer   200000 USD
  Assets:EAG:Bancos:BancoBci       -186200000 CLP
  Income:EAG:ResultadoFX                         ; el motor cuadra la dif. acá

; Tabla de precios por fecha (fx-bcch-eom.jsonl YA es esto → emitir como price)
2026-02-28 price USD 954.30 CLP
2026-05-31 price USD 892.89 CLP

; Ancla contra la cartola del custodio (afirma UNIDADES, no CLP)
2026-05-31 balance Assets:EAG:Offshore:JuliusBaer   210000 USD
```

- **Beancount no tiene moneda base privilegiada** → un libro CLP puede llevar cuentas USD directo.
- **Caja/banco USD = valor nominal.** Inversiones offshore = **costo con lotes `{}`** (para separar
  retorno de capital / ganancia de mercado / ganancia de cambio). Es una bifurcación de diseño real,
  cuenta por cuenta.
- **`price` nunca se baja solo de internet** → cada reporte histórico es determinista y reproducible offline.
- **REFUTADO (0-3):** NO hay que guardar el CLP equivalente en cada movimiento. Se guardan las unidades USD
  y el CLP se DERIVA de la tabla de precios al reportar. (El instinto de Ary de "un fx por movimiento"
  apuntaba bien pero la forma canónica es unidades + tabla de precios, no fx clavado por línea.)
- **Gotcha beanquery:** `CONVERT()` usa el precio ÚLTIMO por defecto — hay que pasar la fecha del balance
  explícita para valorizar a una fecha histórica (issue #54).

## 4. Tratamiento de TC en USD (deuda con spread del banco)

Los dos dólares NO compiten — actúan en momentos distintos:

| Momento | Qué dólar | Para qué |
|---|---|---|
| Deuda **abierta** a una fecha de balance | **BCCh de cierre** | Valorizar el pasivo |
| Cuando se **paga** | **El dólar real del banco** (con spread) | Liquidar la deuda |

La diferencia = **dif. de cambio realizada → `ResultadoFX`**. El spread del banco por sobre BCCh es un
**costo real** y por eso aparece como pérdida — correcto, no es error. La deuda queda en 0 USD (sin fantasma).

**Ojo signo:** es pasivo → dólar que sube = debés más pesos = **pérdida** (al revés que un activo USD).

**Conciliación con la doctrina TC actual** ("fx del pago que la salda"): es un **atajo válido** cuando la
tarjeta se paga completa en el mismo período (no hay fecha de balance con deuda abierta en el medio). El
BCCh de cierre solo importa para un patrimonio a una fecha con la deuda ABIERTA.

## 5. Carga fuera de orden (pago primero, cartola después)

**No complica la cuadratura** — el libro reconcilia por **FECHA**, no por orden de carga. El saldo a una
fecha = suma de todo lo ≤ esa fecha, sin importar cuándo se importó. Pagar-primero-itemizar-después es el
flujo normal de una TC y el mecanismo actual ya lo maneja.

- **Único efecto = frescura, no correctitud:** un reporte corrido antes de cargar la cartola sale
  incompleto para esa tarjeta; se auto-corrige al importar (con fechas correctas). Regla: no confiar en el
  patrimonio de un período cuyas cartolas no se cargaron.
- **Guardrail:** el `balance` assertion debe entrar JUNTO con los movimientos que afirma (atómico), o
  bean-check se queja en el transiente. El proyecto ya importa atómico con rollback → cubierto.

## 6. La decisión de arquitectura: espejo vs patrimonio real

Esto SACA al ledger del "espejo fiel de Laudus" (Laudus no revaloriza, `ResultadoFX` = 0 asientos).
Resolución limpia = **dos capas**:

- **Espejo Laudus** = queda puro CLP, sin FX (sigue cuadrando con el contador, gates 0-diffs intactos).
- **Overlay** = cuentas USD-nativas + `price` + `ResultadoFX`, que **REEMPLAZAN** (no suman) la versión
  CLP-congelada de esas cuentas. ⚠️ Riesgo de doble-conteo si se suman en vez de reemplazar — el diseño
  central a resolver.
- **Reporte** = espejo + overlay para patrimonio real; espejo solo para paridad con Laudus.

## 7. Preguntas abiertas (a resolver en el diseño)

1. **Doble-conteo espejo↔overlay:** cómo las cuentas USD-nativas reemplazan sin sumar a las CLP-congeladas
   de Laudus. (LA pregunta central.)
2. **Caja vs inversión:** banco USD a valor nominal; inversión offshore a costo `{}`. Definir por cuenta.
3. **Dónde postear `ResultadoFX`** (Income:EAG:ResultadoFX o similar) sin descuadrar la paridad Laudus.
4. **Frecuencia de anclas y precios:** ¿balance assertion mensual por cuenta vs cada cartola? ¿precio EOM
   mensual alcanza o hace falta diario para patrimonio a fecha arbitraria?
5. **Reconstrucción histórica:** el fx viejo se recupera de la glosa donde está limpia; donde no, BCCh =
   estimación. Y NINGÚN fx tapa el hueco de reconciliación (rendimiento que Laudus no registró) → para el
   saldo real hace falta la cartola del custodio como ancla, una vez.

## 8. Fuentes clave (research verificado)

- IAS 21 oficial: https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2021/issued/part-a/ias-21-the-effects-of-changes-in-foreign-exchange-rates.pdf (párrafos 21, 23, 28, 32)
- Beancount language / price directives / balance assertions (docs primarias beancount.github.io)
- hledger gain.html (realizada vs no-realizada, cost basis)
- Contexto secundario: cpdbox, gaapdynamics, datastudios (IAS 21/ASC 830)

## 9. Próximo paso recomendado

Mini-diseño **Julius Baer end-to-end** (apertura anclada a cartola, movimientos USD nominal, cómo el
overlay reemplaza el CLP-congelado sin doble-contar, saldo USD y CLP a 3 fechas) → si convence, **brief de
epic "Contabilidad de patrimonio real (IAS 21 multi-moneda)"**. Comparte bloqueo/valor con la auditoría de
inversiones diferida (ambas necesitan la posición real del custodio como ancla).
