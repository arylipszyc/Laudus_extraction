# INVENTARIO DE NATURALEZAS DEL SINCERAMIENTO — población cerrada

**Autora:** Valentina · **Fecha:** 2026-07-23 · **Destino:** input directo de los ACs de la story **E1.3** (transformador de sinceramiento)
**Estado:** CERRADO. Población enumerada y verificada contra la data real del ledger (`bean-query` sobre `ledger/main.beancount`, acumulado 2021→hoy).
**Precondición que cierra:** la tabla §2 del SPEC (`valentina-spec-estructura-odoo-2026-07-23.md`) queda con la afirmación fuerte verificada abajo. Sin esto, un "aporte disfrazado" tipo Sade se cuela e infla el ingreso sin que el gate de paridad se entere.

> **Método.** Beancount = espejo de Laudus; el ingreso es crédito (signo **negativo**). Un número **positivo** dentro de una cuenta `Income:` = plata **saliendo** por una cuenta de ingreso — el patrón del aporte-disfrazado (Sade +4.876M). Barrí **dos niveles**: (1) el **neto** de cada cuenta de ingreso; (2) **cada pata individual de signo positivo** dentro de cuentas que netean negativo o cero (donde un aporte se puede esconder detrás de retiros legítimos).

---

## PARTE 1 — Barrido de aportes-disfrazados (el "barrido pendiente" tipo Sade)

### 1.1 Afirmación fuerte (verificada)

> **Exactamente DOS cuentas de ingreso netean de signo positivo en todo el libro** (2021→hoy):
> - `Income:FFCC:Sade-310011` = **+4.876.249.792** (aporte de capital — SPEC §2.C)
> - `Income:FFCC:Molco-310005` = **+2.895.757.384** (financiamiento de pérdida — SPEC §2.E)
>
> **Ambas ya están enumeradas y con naturaleza asignada en el SPEC §2.** No hay una tercera cuenta que netee positivo. → *No apareció ningún aporte-disfrazado NUEVO a nivel de cuenta.*

Query de respaldo (`... GROUP BY account HAVING sum(number) > 0`): devuelve solo esas dos filas.

### 1.2 Barrido a nivel de PATA (positivos dentro de cuentas que netean ≤ 0)

Toda cuenta de ingreso tiene al menos una pata de signo positivo por los **washes de cierre/apertura** de Laudus (JE "Comprobante de cierre"/"Comprobante de apertura", que netean a 0 dentro del ejercicio). Filtrando esos washes, quedan estas patas positivas **reales** — cada una clasificada:

| Cuenta | Pata + (mayor) | Glosa dominante | ¿Explicada por §2? | Naturaleza |
|---|---|---|---|---|
| `Income:FFCC:Sade-310011` | +3.660M (JE3980) + ~30 mensuales 25–62M | "Inv. Sade Ltda – Aporte capital" / "Inversiones Sade SPA" | **Sí — §2.C** | Aporte de capital (→ `Assets:FFCC:InversionesSade`) |
| `Income:FFCC:Molco-310005` | 80 patas de "Traspaso de cuenta BCI FC 28981162" (30–100M) | Traspaso a Molco (financiamiento) | **Sí — §2.E** | Gasto `Expenses:…:MolcoFinanciamiento` |
| `Income:EAG:VentaDeActivos-310091` | +50M (JE4363) | "Venta lancha Cobalt de EAG a hijas" | **Sí — §2.D** | Disposición (venta intra-familia; baja de activo) |
| `Income:EAG:OtrosIngresos-310099` | +68,4M (JE3311) | "USD70.101 BCI Miami EAG – BUPA FGK" | **Sí — §2.G (por-glosa)** | "por cuenta de" FGK (por-cobrar / contra-gasto) |
| `Income:EAG:RetirosInvNuevoCiclo-310016` | +32,16M (JE4139) | "Inversiones Nuevo Ciclo SPA – **Dividendo**" | Parcial — cuenta es §2.B | Ver ⚠️ **N-2** abajo |
| `Income:FFCC:OtrosIngresos-310099` / `Income:JAB:OtrosIngresos-710099` | patas chicas + washes | mixto | **Sí — §2.G** | Regla por-glosa |
| `Income:EAG:SueldoFcComplemento-310005` | +17,17M (1 pata) | ajuste de sueldo | **Sí — §2.A (allowlist)** | Ingreso real (ajuste/reverso interno) |

**Conclusión del barrido:** ninguna pata positiva material corresponde a un aporte de capital **nuevo** oculto. Las positivas son: (a) washes de cierre que netean 0; (b) el propio Sade y Molco ya enumerados; (c) una venta intra-familia (D); (d) un pago "por cuenta de FGK" (G); (e) reversos/ajustes internos. **Cero candidatos nuevos tipo-Sade.**

### 1.3 Candidatos NUEVOS = GAPS de enumeración del SPEC (no inflan ingreso, pero faltan en §2)

El barrido sí destapó **cuentas que el SPEC §2 no lista** (no son aporte-disfrazado, pero deben quedar enumeradas para que la población esté cerrada):

| # | Cuenta | Neto | Contenido (glosa) | Naturaleza real | Destino recomendado |
|---|---|---|---|---|---|
| **N-1** | `Income:EAG:LatinoamericanaSa-310010` **+** `Income:FFCC:LatinoamericanaSa-310009` | **0 / 0** (netean exacto) | "EAG devolución préstamo Latinoamericana" — patas −98,2M/−10M/−33M contra sus reversos +igual monto (JE552↔JE634, etc.) + wash de cierre 423,6M | **Movimiento de capital** (devolución de préstamo), ya **neteado por Laudus** dentro del ingreso | **Excluir** (netea 0). Marcar `sinceramiento:"capital"` por trazabilidad; NO crea activo (Laudus ya lo revirtió). **AGREGAR a §2** como fila explícita para cerrar población. |
| **N-2** | Pata +32,16M en `Income:EAG:RetirosInvNuevoCiclo-310016` (JE4139) | cuenta neta −5.931M | "Inversiones Nuevo Ciclo SPA – **Dividendo**" | Dividendo (ingreso real) **mal firmado dentro de una cuenta de retiro** | ⚠️ **Revisar con contadoras:** es un +positivo con glosa "Dividendo". O es (a) un dividendo real que debería quedar en Income, o (b) un reverso de retiro. Materialidad baja (0,5% de la cuenta). La cuenta entera igual va a `Assets:EAG:InvNuevoCiclo` (§2.B); esta pata **sigue el destino de la cuenta** salvo que las contadoras la separen. |
| **N-3** | `Income:EAG:JhonnyGuerraHijo-310047` | −400.000 | "Abono préstamo Jhonny – Auto" (2 patas −200K) | Devolución de préstamo (cuenta por cobrar), gemela de `JhonnyGuerra-310045` (§1.2) | `Assets:EAG:PrestamoJhonnyGuerra` (mismo destino que la cuenta madre). **AGREGAR a §2.** Chico. |
| **N-4** | `Income:{Jael,Jeannette,Jocelyn,Johanna}:OtrosIngresos-*70099` | −4M a −8M c/u | "Otros Ingresos" de hijas | Cajón mixto (análogo a §2.G) | **Regla por-glosa** (§2.G extendida a hijas). **AGREGAR a §2.G** la familia `*70099`. Chicos. |

> **Nota clave para E1.3:** N-1 (Latinoamericana) es el hallazgo más importante del barrido porque **no aparecía en el SPEC y mueve 423,6M en patas individuales** — pero **netea exacto a cero**, así que NO infla el ingreso. Es un préstamo devuelto que Laudus registró y revirtió dentro de la cuenta de ingreso. El riesgo era no verlo; ahora está enumerado. El gate de paridad debe tratarlo como wash (paso 1 de la regla §3.2).

### 1.4 Afirmación de cierre (para el AC de paridad de E1.3)

> **Toda pata de signo positivo dentro de cuentas `Income:*` está enumerada y tiene una naturaleza asignada.** Se compone de: (i) 2 cuentas de neto positivo — Sade y Molco, ambas en §2; (ii) washes de cierre/apertura que netean a 0; (iii) 4 gaps de enumeración (N-1 a N-4), todos de neto ≤ 0 y sin inflar ingreso, ya clasificados arriba y a agregar al SPEC §2. **No queda ninguna pata positiva sin explicar. Cero aportes-disfrazados nuevos tipo-Sade.**

---

## PARTE 2 — P-7 rendiciones + tabla-madre de naturalezas

### 2.1 P-7 — Rendiciones del capitán del yate (Fraser / Keiki Kai)

**Verdicto: NO hay señal de rendiciones del capitán del yate en Laudus → FUERA DE SCOPE de E1.**

Verificado con `grep` sobre todo `ledger/`:
- **"Fraser" → 0 resultados.** No existe el capitán en ninguna glosa ni cuenta.
- **"Keiki Kai" → solo cuentas de GASTO** (`Expenses:JAB:KeikiKaiSueldosTripulacin-855001`, `KeikiKaiGastosDeOperacinTripulacin-855003`, `KeikiKaiTelfono-855007`, etc.), categoría Laudus `YATES / MANTENCION YATE KEIKI KAI`. Total de gasto del yate en el libro ≈ **6.674.679.720 CLP** (incluye Destiny, Alfín II y Keiki Kai bajo JAB).
- **"Rendición" → sí existe, pero es OTRA cosa:** todas las rendiciones en Laudus son de **gasto de propiedades/casas** — "Rendición casa sur EAG" (Oscar Bustamante, Noelia Farfal), "Rendición Daniel Cadenas – materiales/Sodimac/Unimarc", "Eluchans – Rendición Tauro EAG". Son rendiciones de mayordomo/administrador de casa, **no del yate**.

**Interpretación (consistente con SPEC §5.3):** el yate vive en Laudus **solo como gasto de mantención/tripulación** (JAB). La gestión del capitán (Fraser cobrando desde Leo offshore) **no toca Laudus** → no hay asiento que sincerar. → **P-7 = fuera de scope E1.** Las rendiciones que **sí** están en Laudus (casas/administradores) son **gasto ordinario con workflow de rendición**: rutean como **GASTO**, no como traspaso. No hay que inventar nada; la señal es clara y negativa para el yate, positiva para las casas.

### 2.2 TABLA-MADRE de naturalezas — la población que E1.3 debe cubrir

Lista completa y enumerada. Cada naturaleza: **patrón de detección** (código y/o glosa) · **destino** · **precondición abierta**. Esto es el input directo de los ACs de E1.3.

| # | Naturaleza | Patrón de detección (código / glosa) | Destino | Precondición abierta |
|---|---|---|---|---|
| **0** | **Wash de cierre/apertura** | glosa = "Comprobante de cierre" / "Comprobante de apertura" con par igual-y-opuesto en el ejercicio | **Excluir** ambos (netea 0). No re-clasificar. | — |
| **A** | **Ingreso real** | Allowlist de código: `RetirosIndumotora-310011`, `Indumotora-310001`, `Directorio*`, `Sueldo*`, `KiaChileSpa-310023`, `HyundaiChileSpa-310024`, `DevolucinOficinaTecnin-310035`, `IngresosPorInversiones-310095`, `DividendosRetiros-310009`. Glosa: dividendo/interés/directorio/arriendo/sueldo | **Queda en Income** | P-3 resuelta (Kia/Hyundai = sueldo director). Indumotora = allowlist explícito (no se consolida) |
| **B** | **Retiro de inversión** | Código `Retiros*` de vehículos: `-310013` (Tecnión), `-310018` (Inmob. España), `-310016` (Nuevo Ciclo), `-310027` (MBI), `-310029` (JB), `-310019` (Inmob. Metrop.), `-310015` (Pléyades), `-310006` (Fondo Común); hijas `*70011`, `*70010`, `*70023`, `*70013`. Glosa: rescate/retiro/traspaso | **Activo de ORIGEN** (§1.2), provisional | Saldos negativos esperados → **valuación Fase 2** (custodio). Retiros de hijas = auditoría diferida (¿fondos propios o pozo común?) |
| **C** | **Aporte de capital** (signo +) | Código `Sade-310011`; glosa "aporte capital" / "Inversiones Sade SPA" + **signo positivo** | **Activo** `Assets:FFCC:InversionesSade` | Cerrado. Costo, no valor. Valuación Fase 2 |
| **D** | **Disposición de activo** | Código `VentaDeActivos-310091` (EAG/FFCC), `*70091` (hijas), `VentaAccionesPerla-310059`; glosa "venta <bien>" (Kia/Bentley/Rolls/lancha/acciones) | **Baja del activo** (no ingreso) | **P-2:** confirmar si algún bloque es reventa comercial (giro) vs bien propio. Verificar cuenta-por-pagar transitoria del trade-in Indumotora |
| **E** | **Financiamiento de pérdida (Molco)** | Código `Molco-310005` (FFCC, +2.896M) y `Molco-710005` (JAB, −1.200M); glosa "Traspaso de cuenta BCI FC 28981162" / "Traspaso de Agrícola Molco" | **GASTO** `Expenses:…:MolcoFinanciamiento`, tag `propiedad:Molco`; JAB netea contra el gasto | P-1 resuelta (gasto, no activo). Molco entra como 3ª entidad más adelante |
| **F** | **Reembolso / contra-gasto** | Código `Devolucin*` (`-310037/39/41/43/49`, `ClubDeGolf-310019`, `DevolucinIsapreJael-970051`); glosa "devol"/"reemb" | **Queda como ingreso menor** (Fase 1); opción purista = netear contra el gasto | Baja materialidad. Refinar después |
| **G** | **MIXTO — regla por-glosa** | Código `OtrosIngresos-310099` (EAG/FFCC), `-710099` (JAB), **+ hijas `*70099` (N-4)**; se clasifica **pata por pata** por la glosa (traspaso / donación / préstamo / venta / reembolso / "por cuenta de") | **Según glosa de cada pata** (mixto) | El cajón de sastre. La regla por-naturaleza corre línea a línea sobre `desc` |
| **H** | **Devolución de préstamo (por-cobrar)** | Código `JhonnyGuerra-310045`, **`JhonnyGuerraHijo-310047` (N-3)**, **`LatinoamericanaSa-310009/310010` (N-1)**; glosa "abono préstamo" / "devolución préstamo" | Latinoamericana: **excluir** (netea 0, ya revertido). Jhonny: **cuenta por cobrar** `Assets:EAG:PrestamoJhonnyGuerra` | **GAPS del SPEC §2 — agregar.** Latinoamericana neta 0; Jhonny chico |
| **—** | **Vacías (Fase 2)** | Cuentas `5xxx Resultado*`, `Dividendos Art.107`, `FIP`, `LatinoamericanaSa` sin movimiento neto | Se crean en el plan, no mueven nada; reservadas Fase 2 | Se llenan al reconocer resultado acumulado (§4.2) |

**Diferencia vs SPEC §2:** la tabla-madre agrega la fila **0** (wash, ya implícita en §3.2 paso 1, ahora explícita como naturaleza) y la fila **H** (devolución de préstamo/por-cobrar) que consolida los gaps N-1/N-3 y a `JhonnyGuerra` que en el SPEC estaba solo en §1.2 sin fila en §2. Con H, la población queda **cerrada**: cada cuenta de ingreso del libro cae en 0/A/B/C/D/E/F/G/H.

### 2.3 Precondiciones abiertas que E1.3 hereda (no bloquean la enumeración)

- **P-1 Molco** → resuelta (gasto).
- **P-2 Venta de Activos** → abierta (¿reventa comercial? ¿cuenta-por-pagar trade-in en la data?). Afecta D.
- **P-3 Kia/Hyundai** → resuelta (sueldo director).
- **P-5 Misc JB, P-6 AZBA** → Fase 2 / auditoría, no afectan la regla de import.
- **N-2 (dividendo +32M en Nuevo Ciclo)** → revisar con contadoras el signo; materialidad baja; por defecto sigue el destino de la cuenta (B).

---

## Resumen de una línea

> **57 cuentas de ingreso barridas; exactamente 2 netean positivo (Sade +4.876M aporte, Molco +2.896M financiamiento) y ambas ya están en §2 → 0 aportes-disfrazados nuevos tipo-Sade.** El barrido a nivel de pata destapó 4 gaps de enumeración (Latinoamericana, JhonnyGuerraHijo, OtrosIngresos de hijas, y una pata "dividendo" a revisar), todos de neto ≤ 0 y sin inflar ingreso, ahora clasificados (naturaleza **H** nueva). **P-7 rendiciones del capitán del yate = fuera de scope E1** (Fraser/Keiki Kai no están en Laudus como flujo; el yate vive solo como gasto JAB ~6,67B; las rendiciones que sí existen son de casas → gasto). La población de naturalezas para E1.3 queda **cerrada** en la tabla-madre (0/A–H).
