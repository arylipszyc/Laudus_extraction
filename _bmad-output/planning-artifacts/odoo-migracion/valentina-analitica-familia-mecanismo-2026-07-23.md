# Mecanismo de activos compartidos (yate/avión) + retiros por socio — verificación Laudus vs contadoras vs Excel, y diseño analítico Odoo

**Autora:** Valentina · **Fecha:** 2026-07-23 · **Contexto:** spike Odoo (analítica). Ary trajo el relato de las contadoras (reunión 2026-07-22). Este doc verifica ese relato contra Laudus/Beancount, contra los Excel del family office, y propone cómo ordenarlo con contabilidad analítica en Odoo.

## 1. Relato de las contadoras (2026-07-22)

1. **TC 0858 de EAG paga gastos de FGK** (viuda de JAB). Parte va a `ControlYLiquidación`. NO llevan el saldo de esa cuenta: a fin de mes revisan lo que pagó la 0858 a FGK y transfieren desde una cuenta del FFCC a una de EAG ese monto.
2. **FFCC tiene bancos en Chile + cuentas afuera** desde las que se envían fondos a las locales (sociedades offshore tipo "Leo", "Tauro").
3. **Yate:** antes se enviaban fondos al capitán desde cuentas locales y él rendía; hoy se envían directo desde el exterior, pero las contadoras registran algo para controlar rendiciones (no está claro si en Laudus).
4. **AZBA salió de la propiedad del yate y el avión** → costos FIJOS se reparten entre los 3 hermanos (AAG, DAG, EAG); costos de USO se asignan a quien incurrió (viaje de un hermano o de alguien que él financie). Quedan como **retiros = CxC**.
5. Cada uso del yate/avión = retiro (deuda con FFCC). Cada cierto tiempo se **inyectan fondos desde sociedades offshore** (partes iguales EAG/AAG/DAG/AZBA) que **netean** los retiros.

## 2. Verificación contra Laudus — ✅ CALZA (con asiento real)

**Asiento Fraser Julio 2026 (JE 10551, USD 115.896 = 104.698.463 CLP):**
```
FFCC:LeoPartnershipLimited-111012      −104.698.463   ← Leo (offshore) PAGA a Fraser (gestora del yate)
FFCC:RetirosAag-115021   +34,9M / −34,9M              ┐ split 1/3 c/u entre 3 hermanos,
FFCC:RetirosEag-115023   +34,9M / −34,9M              ├ PERO se lava a 0 (fijo compartido)
FFCC:RetirosDag-115027   +34,9M / −34,9M              ┘ AZBA NO aparece → confirma que salió
JAB:KeikiKaiMantencinReparacin-855024  +104.698.463   ← queda como GASTO del yate
```

Confirmado:
- **Leo (`Assets:FFCC:...-111012`)** = vehículo offshore que paga el yate (Fraser) ~USD 90-115k/mes. Saldo **−3.286M** (negativo imposible).
- **Tauro (`Assets:EAG:...-113021`)** = sociedad offshore con **aportes de capital** reales (USD 375k+ en 2023, contra banco de Jocelyn). Saldo **+6.208M** (congelado al costo del aporte).
- **Retiros por socio:** AAG·EAG·SAG·DAG·AZBA (`115021/023/025/027/029`) + `OtrosRetirosHijos-115039`. SAG (hija fallecida) tiene la suya.
- **AZBA salió del yate:** `Venta participación Fraser` −859M (2025-01-31, USD 875k, contra RetirosAag/Eag).
- **Netting desde offshore:** en 2026 los hermanos inyectan a Leo ("Leo Limited Partnership EAG" −61M, "Leo Limited Pictet EAG" −30M). Antes (2021-23) entraban aportes al banco local (Zeldis, Alazraki, Borzutzky → cuentas 115031-037).

## 3. Limitaciones / desorden encontrado (honestidad de datos)

| # | Hallazgo | Implicancia para reportería |
|---|---|---|
| 1 | El costo **fijo** del yate **se lava a 0 en los retiros** y cae como gasto | El split 3-hermanos está documentado en cada asiento pero NO queda como saldo por hermano → "costo por hermano" hay que reconstruirlo |
| 2 | **Leo −3.286M** (negativo), **Tauro** congelado al aporte | Offshore en Laudus pero **sin valor real** (error B inversiones, confirmado en 2º libro) |
| 3 | **Rendiciones del capitán NO están en Laudus**: `KeikiKaiGastosDeOperacinTripulacin-855003` = VACÍA (0 movs) | Fraser gestiona cobrando desde Leo; Laudus solo ve el lump "Fraser". Control de rendiciones = fuera de Laudus |
| 4 | Cuentas `ControlYLiquidación` **no se cuadran** (C&L FFCC −43M) | Confirmado por contadoras: no llevan saldo, solo transfieren mensual lo que pagó la TC |

## 4. Verificación contra los Excel — SON TRANSFORMACIÓN, no dump directo

Carpeta `H:\My Drive\Emprendimientos\Analisis gastos Edu\Familia`. Últimos = período 06-2026 (`Resúmen Retiros al 30-06-2026`, `Retiros AAG/AZBA/DAG/EAG 2026`, `FFCC 06-2026`, `Deuda 30-06-2026`).

**`Resúmen Retiros al 30-06-2026.xlsx`** = pivote manual de los retiros de Laudus: **por socio × año × mes**, + columna **"Abono Julius / Leo"** (el netting offshore) + **"Acumulado"**. Ej. AAG 2026: Ene 58,7M…Jun 28,6M = TOTAL ANUAL 219.065.689, Abono Julius/Leo −276M.

**Conclusión:** las contadoras **ya hacen contabilidad analítica a mano en Excel** — pivote por socio + netting Leo/Julius + acumulado. Es trabajo manual, repetido cada período, propenso a error. Es EXACTAMENTE lo que la analítica de Odoo hace nativo.

## 5. Diseño analítico en Odoo (propuesta)

Dimensiones (con la regla partición/disperso para que NO se descuadre):

| Dimensión | Cuentas analíticas | Partición/Disperso | Fuente (escalón) |
|---|---|---|---|
| **Socio** | AAG·EAG·DAG·AZBA·SAG (+ Zeldis/Alazraki/Borzutzky) | Partición (reconcilia) | Cuentas Retiros 115021-039 (escalón 1) |
| **Propiedad/activo** | Keiki Kai (yate), aviones, casas (Vía Gris/Molco/Miami) | Disperso | categoria2 "85 Yates"/"83 Aviones" + glosas (escalón 1-2) |
| **Sociedad offshore** | Leo, Tauro, Julius Baer, Pictet | Disperso | cuentas 111012/113021 + glosas (escalón 1-2) |
| **Por cuenta de** | FGK, JAB (gastos que EAG paga por ellos) | Disperso | ControlYLiquidación + PAT 0858 (escalón 2) |

**Lo que Odoo automatiza (reemplaza el Excel):** taggear una vez por regla (desde la cuenta retiro + glosa) → el "Resúmen Retiros", "Retiros por hermano" y "costo por yate/avión" se generan solos y reconcilian.

**Lo que Odoo NO arregla solo (data, no herramienta):** valuación offshore (Leo/Tauro), capitalización del yate/avión, rendiciones del capitán (fuera de Laudus). La analítica hace la reportería reproducible y más rica, pero **hereda los huecos de Laudus**. Fix de datos = separado (ancla = posición real del custodio, misma que la auditoría de inversiones diferida).

## 7. Sinceramiento de ingresos — traspasos/retiros catalogados como ingreso (2026-07-23)

Revisión a pedido de Ary (que Odoo refleje la realidad de Laudus, sin arrastrar el P&L inflado).

**Hallazgo (todos los años):** de **78.253M** de "ingresos", **~46.000M son movimientos de capital / traspasos entre bolsillos propios**, no ingreso operativo. Sumando Indumotora (25,3B, dividendo real), el **ingreso operativo verdadero ≈ 7B (<10%)**. El P&L de Laudus tal cual es ficción para quien lo lea como "cuánto ganó la familia".

**Catálogo de errores:**
| Tipo | Ejemplo (glosa real) | Realidad | Magnitud |
|---|---|---|---|
| Transfer entre cuentas propias→ingreso | Jb-310029 "USD 1.500.000 a BCI USD EAG" | traspaso de caja | ~3,3B |
| Rescate de fondo→ingreso | Mbi "Rescate FM Security Plus" | redención capital+ganancia | ~4,8B |
| Devolución préstamo→ingreso | NuevoCiclo "Devolución de préstamos" | retorno de capital | ~5,9B |
| Retiro inmobiliaria→ingreso | InmobiliariaEspaña "Retiro" | retiro de capital | ~9,0B |
| Retiro inversión→ingreso | Tecnin + 4 hijas "abono mandato" | retiro de capital | ~12,2B + ~9,4B |
| Retiro Julius Baer→ingreso | RetirosJuliusBaerJael | retiro de capital | ~0,4B |
| Pérdida operativa→ingreso NEGATIVO | Molco −2,9B | pérdida operativa (campo) mal ubicada | −2,9B |
| **Aporte de capital→ingreso NEGATIVO** | **Sade +4,9B** (ver §8) | inversión ENTRANDO, mal puesta como ingreso neg. | −4,9B |

**Lógica adjudicada (Ary, correcta):** la ganancia/pérdida se genera en la **revaluación de la cuenta de ORIGEN** (el activo), no en la que recibe. La que recibe solo ve un traspaso de caja. En Fase 1 (origen sin trackear) lo que se ve es real = puros traspasos; la utilidad aparece en Fase 2 al revaluar el origen.

**Excepción a la lógica (Valentina):** **dividendo/interés ≠ retiro.** Un retiro achica el activo (ganancia vive en el origen); un dividendo NO achica el activo (la empresa repartió su utilidad) → es **ingreso real al recibir**, se queda. La regla debe distinguir por **naturaleza, no por nombre**:
- "rescate / retiro / devolución / traspaso / a cuenta X" → sale de ingreso (a cuenta de balance origen)
- "dividendo / interés / directorio / arriendo / distribución" → se queda como ingreso

**Estrategia de 2 fases (plan de Ary, ratificado):**
```
FASE 1 (al pasar a Odoo): regla determinística en el import
  · transfer/retiro-como-ingreso → cuenta de balance origen (crear si no existe, marcar "provisional")
  · traspaso puro (JB→BCI) → limpio; retiro de inversión → saldo origen negativo/provisional (aceptado)
  · pérdidas OPERATIVAS (Molco) → gasto ahora; aportes de capital (Sade) → Activo ahora (§8)
  · RESULTADO: P&L local sincerado (ingreso operativo real ~7B; CONSERVADOR — subestima la ganancia hasta Fase 2)
FASE 2 (módulo de inversiones): con custodio, separar capital vs ganancia, reconocer utilidad, valuar orígenes
```

**Decisiones de Ary (2026-07-23):**
- **Indumotora (25,3B) se DEJA como ingreso** — asunción documentada: no se consolida la contabilidad de Indumotora (empresa completa) solo para separar capital/ganancia. Puede contener retiro de capital; aceptado; revisable si algún día se consolida Indumotora. → allowlist explícito de la regla.
- **Cuentas de origen (Leo/Tauro/etc.): dejar los saldos como están** por ahora ("van a decir cualquier cosa"); se arreglan en Fase 2 con el custodio.
- Módulo de inversiones = proyecto propio, después.

## 6. Preguntas abiertas / próximos pasos

- [ ] Reconciliar al peso los saldos de retiro Laudus vs el "Acumulado" del Excel (paridad — misma disciplina del proyecto).
- [ ] Confirmar con contadoras: ¿el control de rendiciones del capitán vive en un sistema aparte (Fraser)? ¿Se quiere traer a Odoo?
- [ ] Decisión Ary: la dimensión "propiedad" — ¿solo mantención (lo que hay) o excusa para capitalizar el activo (cruza con auditoría inversiones diferida)?
- [ ] Mapear el mecanismo TC 0858→FGG→transfer FFCC→EAG en ambos libros (cómo se registra el reembolso).
- [ ] Barrer el resto de ingresos negativos buscando el patrón "aporte de capital mal puesto" (Sade es uno; ¿hay más?).

## 8. Sade — CERRADO (2026-07-23): aporte de capital disfrazado de ingreso negativo

- **Qué es:** `Inversiones Sade SpA` — empresa de inversión **chilena local** (SpA, se fondea en CLP desde el banco local; NO offshore).
- **Libro:** solo **FFCC** (`Income:FFCC:Sade-310011`).
- **Movimientos (30):** aporte inicial 2022-10-04 **+3.660M** "Inv. Sade Ltda - Aporte capital" + inversiones mensuales continuas 2023-2026 (+21M a +343M "Inversiones Sade SPA"). Cumulativo **+4.876M**. **30/30 contra el banco local FFCC** (`BancoBci28981162-111005`).
- **Error:** es plata **ENTRANDO** a una inversión (aporte de capital), contabilizada como **ingreso NEGATIVO**. Espejo del error de retiros (retiro sale→ingreso+; aporte entra→ingreso−). Los asientos están bien (banco→Sade); lo único mal es el **TIPO de cuenta**: es INGRESO cuando debería ser ACTIVO.
- **Fix (Fase 1, limpio, NO diferido):** crear `Assets:FFCC:InversionesSade`, mapear todo ahí. El −4.876M sale del P&L y queda +4.876M de activo (costo). La ganancia/pérdida (valor actual vs 4.876M) = Fase 2.
- **Corrige mi lump previo** que decía "Sade = pérdida financiera → diferir": MAL. No es pérdida, es aporte; no se difiere, se arregla ahora.
