# Mini-diseño end-to-end: Julius Baer en USD nativo (prueba del método IAS 21)

**Autora:** Valentina 💰 · 2026-07-18
**Propósito:** validar en números reales el método multi-moneda (ver `valentina-metodo-multimoneda-ias21-2026-07-18.md`) sobre una cuenta concreta antes de comprometer un epic.
**Cuenta:** `Assets:EAG:Inversiones:BancoJuliusBaer03133171-111017` (fondo dólar / cta inversión USD).

---

## 1. Los datos reales (8 movimientos de Laudus, todo en CLP hoy)

| fecha | CLP (Laudus) | USD (glosa) | fx implícito | nota |
|---|---:|---:|---:|---|
| 2021-08-04 | 155.600.000 | 200.000 | 778,00 | limpio |
| 2021-09-27 | 79.590.000 | 100.000 | 795,90 | limpio |
| 2021-12-07 | 87.470.107 | 103.699 | 843,50 | limpio |
| 2021-12-07 | 10.023 | — | — | cargo menor, sin USD claro → estimar/ignorar |
| 2021-12-14 | 103.296.411 | 121.654 | 849,10 | limpio |
| 2021-12-16 | 6.519.790 | — | — | "CC-931 Saldo empresa Turski" SIN USD → **requiere criterio** |
| 2022-05-30 | 788.405.000 | 950.000 | 829,90 | limpio |
| 2024-10-09 | −784.766.379 | −840.000 | 934,25 | limpio (rescate FM Dólar Cash) |

**6 de 8 movimientos tienen USD limpio en la glosa** → fx exacto recuperable. 2 son fuzzy (un cargo
menor de 10.023 y un "saldo empresa" de 6.519.790 sin USD). → ejemplo perfecto de dónde la reconstrucción
histórica es exacta vs dónde hay que estimar con BCCh o pedir criterio.

## 2. El punchline: la ganancia de cambio invisible

- **USD reconstruido (limpio):** 635.353 USD
- **CLP-congelado que muestra el libro HOY:** 436.124.952 CLP
- **Valor real de 635.353 USD @ dólar de cierre 2026-05 (892,89):** 567.300.340 CLP
- **Ganancia de cambio INVISIBLE hoy: ≈ 131.175.388 CLP**

El libro subvalúa esta cuenta en ~131 millones, solo porque nunca se reconoció la diferencia de cambio
(los dólares se compraron a ~800 y hoy valen ~893). El patrimonio miente por omisión.

⚠️ **Y todavía falta el hueco de reconciliación:** el Julius Baer es un **fondo dólar** (rinde). El
2024-10-09 dice literal "Rescate FM Dólar Cash". Los 635.353 USD son "USD principal transferido", NO el
saldo real — el fondo puede haber rendido más. **Solo la cartola del custodio da el número verdadero.**
Por eso el ancla es la cartola.

## 3. Cómo se ve en Beancount (overlay que REEMPLAZA, sin doble-contar)

El espejo Laudus queda intacto (CLP, mantiene paridad). El overlay pone un **asiento de corte** que (a)
neutraliza el CLP-congelado y (b) establece la posición real en USD anclada a la cartola:

```beancount
; --- OVERLAY (imports/cartolas/ o manual/, NO imports/laudus/) ---

; Corte: saca el CLP-congelado del espejo y pone la posición USD real (de la cartola del custodio)
2026-05-31 * "Cutover USD nativo — Julius Baer (ancla cartola custodio)"
  Assets:EAG:Inversiones:BancoJuliusBaer03133171-111017   -436124952 CLP   ; anula el congelado
  Assets:EAG:Offshore:JuliusBaerUsd                            635353 USD @ 892.89 CLP  ; posición real
  Income:EAG:ResultadoFX                                                      ; la dif. (~131M) = FX + retorno

; Tabla de precios por fecha (fx-bcch-eom.jsonl → emitir como price directives)
2026-05-31 price USD 892.89 CLP

; Ancla contra la cartola (afirma UNIDADES USD, no CLP)
2026-05-31 balance Assets:EAG:Offshore:JuliusBaerUsd   635353 USD
```

- **Espejo Laudus** = ve 436.124.952 CLP (matchea Laudus, paridad 0-diffs intacta si el gate lee solo `imports/laudus/`).
- **Patrimonio real** (espejo + overlay) = cuenta CLP-congelada neteada a 0 + `JuliusBaerUsd` a valor real.
- **De 2026-05 en adelante**, los movimientos nuevos entran a `JuliusBaerUsd` en USD nativo.
- **Sin doble-conteo:** el overlay ANULA el congelado, no lo suma.

## 4. El saldo a distintas fechas (misma cantidad USD, distinto valor CLP)

Con la posición quieta en **635.353 USD** desde el rescate de 2024, revalorizada al dólar de cierre de cada mes:

| Fecha reporte | USD (cantidad) | Dólar cierre (BCCh) | Valor patrimonio (CLP) |
|---|---:|---:|---:|
| 2026-01-31 | 635.353 | 858,45 | 545.418.783 |
| 2026-02-28 | 635.353 | 861,19 | 547.159.650 |
| 2026-03-31 | 635.353 | 931,57 | 591.875.794 |
| 2026-05-31 | 635.353 | 892,89 | 567.300.340 |

La cantidad de dólares no se movió, pero el valor CLP oscila ~46M entre meses — eso es la exposición
cambiaria, hoy 100% invisible en el libro (que muestra 436M plano). **Responde las dos preguntas de Ary:**
cuántos dólares había (635.353, de las unidades) y cuánto valían en CLP a cada fecha (× dólar de cierre).

## 5. Decisiones que valida este ejemplo

- **Cutover vs re-expresión histórica completa.** Julius Baer está prácticamente estático (635k USD
  parados desde 2024) → **cutover** es lo correcto: anclar a una cartola reciente, USD nativo hacia
  adelante. Responde "cuántos USD hace 5 meses" exacto (post-corte). Re-expresar los 8 movimientos en USD
  (para historia perfecta 2021-24) es la versión ambiciosa — necesita resolver los 2 fuzzy + poblar BCCh
  histórico. Para esta cuenta no vale la pena; para otras con más movimiento, evaluar.
- **fx-bcch-eom hoy solo tiene 2025-12→2026-05** → hay que **poblar el histórico** (2021→) para valorizar
  fechas viejas. Es una tarea acotada (misma fuente mindicador/BCCh).
- **La ganancia (~131M) va a `Income:EAG:ResultadoFX`** — rompe paridad con Laudus (que no la tiene) →
  por eso vive en el overlay, y el reporte la puede apagar para reconciliar con el contador.

## 6. Próximo paso

Este mini-diseño confirma que el método funciona y cuánto valor destapa (~131M en UNA cuenta). Si Ary lo
aprueba → **brief de epic "Contabilidad de patrimonio real (IAS 21 multi-moneda)"**: overlay + price
directives (poblar BCCh histórico) + `ResultadoFX` + reporte de patrimonio dual CLP/USD + anclas de
cartola. Insumo de Ary = conseguir las cartolas del custodio (mismo desbloqueo que la auditoría de
inversiones diferida).

---

## 7. DATOS REALES del custodio (2026-07-18) — reemplazan la reconstrucción de §1-§2

Ary aportó las cartolas reales de Julius Baer (carpeta `H:\...\Inversiones Edu\`). **Scope acotado por
Ary: solo la(s) cuenta(s) Julius Baer que están en el plan de Laudus** = una sola, `Assets:EAG:
Inversiones:BancoJuliusBaer03133171-111017` (relación **1313.3171 = MR. EDUARDO AVAYU GUILOFF = EAG**).
La otra mención en el plan (`Income:Jael:RetirosBankJuliusBaerCoLtdJael`) es un flujo, no una tenencia → fuera.

**Saldo real al 30.06.2025** (Portfolio Valuations):
- Portafolio 02.01 = USD 12.432.904 (bonos 5,41M / acciones 5,68M / cash+T-bills 1,07M / oro 0,26M; USD/EUR/CHF)
- Portafolio 02.02 = USD 2.953.201 (estructurados/barrier reverse conv 1,91M / private equity GCP14 0,45M / otro 0,50M / cash 0,09M)
- **TOTAL cuenta = USD 15.386.105** vs ledger 436.124.952 CLP congelado (≈USD 465k) → el libro muestra ~3%.

**Anclaje (asiento de reconocimiento):** retira el CLP-congelado + pone 15.386.105 USD @ dólar BCCh
30.06.2025 [POBLAR, ~940] contra `Equity:EAG:ReconocimientoPatrimonioReal` (~14.500M CLP — NO a resultado,
es patrimonio preexistente). Luego `price` + `balance` assertion. Vive en overlay `manual/`, NO toca Laudus.

**Modelo operativo elegido = A1** (marca + renta itemizada):
- Valorización = ancla (balance assertion). Cartola de movimientos = eventos.
- Renta (cupones/dividendos/distrib.) → `Income:EAG:RentaInversiones`; comisiones → `Expenses:EAG:ComisionesInversion`;
  ganancia realizada → `Income:EAG:GananciaRealizada`; revalorización de mercado (plug que cuadra vs valorización)
  → `Income:EAG:RevalorizacionNoRealizada`. Depósitos/retiros/compras de valores = transferencias, NO resultado.
- Cadencia: se re-ancla cuando llega cada valorización (trimestral/semestral); cartolas mensuales entremedio.

**Resultado REALIZADO junio 2025** (de las 5 hojas de efectivo, completo): renta 23.890,98 + ganancia
realizada 3.233,33 − comisiones 10.641,93 = **+16.482,38 USD** (≈+15,5M CLP). Falta la revalorización no
realizada de junio (necesita la valorización al 31.05.2025, no disponible).

## 8. PENDIENTES (Ary consigue las cartolas completas → retomamos)

1. **Crédito Lombard / pignoración** ("assets pledged as collateral 27.06.2025"). Ary NO tiene conocimiento
   de él. Casi seguro hay deuda contra el portafolio → reconocer 15,4M sin ella **sobreestima el neto**.
   Conseguir el estado del préstamo antes de dar el patrimonio neto por bueno.
2. **Frecuencia del "all-inclusive fee"** (junio: 9.057,35 en .01 pág.2 + 1.584,58 en .02 pág.2 = 10.641,93).
   NO sabemos si es mensual o trimestral. Ary sospecha que es alta. Mensual→0,83%/año, trimestral→0,28%/año.
   Verificar contra OTRO mes: si aparece con monto similar = mensual; si no = trimestral. NO anualizar ×12 sin confirmar.
3. **Valorización al 31.05.2025** (y demás fechas) para cerrar el resultado TOTAL mensual (realizado + revalorización).
4. **Dólar BCCh 30.06.2025** (y el histórico) para el `@ price` exacto del anclaje.
5. Compromiso no fondeado del private equity GCP 14 LP = USD 40.000 (memo, contingente).
