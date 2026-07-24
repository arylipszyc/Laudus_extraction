# Veredicto contable — Cuentas "Retiros" del FFCC (115xxx): son cuenta corriente de socios, no por cobrar

**Fecha:** 2026-07-12
**Pedido por:** Ary (vía dev/Moishe), como revisión previa a construir la sección de distribuciones de la story 13.1.
**Fuente:** ledger Beancount `main.beancount` @ corte 2026-06-30, fiel a Laudus (12.5 reconcilió 0 diffs / 237 cuentas). Sondeos read-only: `_bmad-output/planning-artifacts/_forense_retiros_rut2.py`.

---

## TL;DR

Las cuentas `Assets:FFCC:Retiros<X>-115xxx` (categoria3 "CUENTAS POR COBRAR") **no son cuentas por cobrar** — funcionan como **cuentas corriente / de patrimonio de los socios** (doble vía). El saldo negativo (crédito) que le extrañó a Ary NO es un aporte de los hijos: es **utilidad del fondo asignada a cada uno** (asiento anual de cierre) que no retiraron.

> ⚠️ **CORRECCIÓN 2026-07-12 (2ª pasada, Ary tenía razón):** en la 1ª versión afirmé que esos ~13.577M "a favor" **no están respaldados**. **RETIRO esa conclusión.** El balance del FFCC está **incompleto** — igual que EAG, no carga las posiciones de inversión (Indumotora, Sade, Molco…) ni las propiedades/aviones/yates. La "caja negativa −2.941M" es **falsa**: la produce una sola cuenta, `LeoPartnershipLimited-111012` (−3.096M), un vehículo de inversión mal clasificado como disponible (111) y arrastrado a negativo (error B de la auditoría inversiones EAG). La caja bancaria real es **~+155M positiva**. **No sabemos el patrimonio real del fondo.** Ver §"Corrección — saldos no cargados" abajo.

## La pregunta de Ary

> "Suena raro una cuenta por cobrar con saldo negativo. Los hijos no tienen más ingreso que los repartos, ¿de dónde sacarían fondos para ingresar más al FFCC?"

**Respuesta: no ingresan nada.** Los créditos que dejan la cuenta en negativo vienen de:
1. **Asignación de utilidad** — el asiento `2023-01-01 "Comprobante de apertura"` (cierre anual) toma el resultado del fondo (Income Indumotora/Sade/Venta Activos − todos los gastos JAB/FFCC) y lo **acredita a la cuenta de cada hijo sin mover caja** = su participación en la utilidad.
2. **Ingresos externos atribuidos** — "Bank JB Eduardo Avayu" (USD), ventas de aeronaves: entran al banco FFCC y se acreditan a los hijos.
3. **Asientos "wash"** — reclasificaciones +X/−X en la misma cuenta (neto 0) que reparten montos entre AAG/EAG/DAG.

## Los números que importan (FFCC @ 2026-06-30, millones CLP)

| Concepto | Monto | Lectura |
|---|---|---|
| Σ cuentas 115xxx (el fondo "les debe") | **−13.577** | saldo a favor de los hijos |
| Caja + bancos FFCC (111xxx) | **−2.941** | negativa |
| Inversiones / otros activos FFCC | **0** | no hay (todo el activo es 11x) |
| Patrimonio (Equity) FFCC | **0** | no existe cuenta de patrimonio |
| Neto que FFCC financió a JAB/FGK | **+14.808** | de eso **16.502 son GASTO consumido** (casas/aviones/yates/personal); solo 24,7 quedó como activo JAB |

**Interpretación:** el FFCC gana plata (dividendos Indumotora, ventas de activos, Sade), la asigna a los hijos como su reparto, y esa misma plata se gasta en el estilo de vida de JAB/FGK. El "saldo a favor" de cada hijo es un **derecho contable sobre activos ya consumidos**, no plata retirable.

### Detalle por persona @ 2026-06-30 (millones)

| Cuenta | Saldo | |
|---|---:|---|
| RetirosAag-115021 | −4.420 | a favor |
| RetirosEag-115023 | −3.557 | a favor |
| RetirosDag-115027 | −3.344 | a favor |
| ArielBorzutzky-115037 | −535 | a favor |
| MichelleZeldis-115035 | −494 | a favor |
| RetirosAzba-115029 | −493 | a favor |
| DeniseZeldis-115033 | −486 | a favor |
| JosAlazraki-115031 | −482 | a favor |
| RetirosSag-115025 | **+261** | debe al fondo |
| Israel-115041 | +4,6 | debe al fondo |
| (operativas: FondoFijo, FondosPorRendir, Deudores Varios, Control y Liquidación) | ~0 | — |

## Corrección — saldos no cargados (2ª pasada, a pedido de Ary)

Ary apuntó: "igual que en EAG, no se están cargando los saldos de las cuentas del FFCC; no sabemos el saldo real." **Verificado — tiene razón.** La paridad 12.5 (0 diffs) solo prueba ledger = Laudus; si Laudus no cargó las posiciones, ambos están mal juntos (mismo mecanismo que la auditoría inversiones EAG).

**Evidencia (@2026-06-30):**
- **Cero cuentas de inversión en el plan FFCC.** 25 cuentas de activo son todas 11x (caja/banco/CxC); la única no-corriente es `ActivosNoCorrientes-13`, **vacía**. Pero el fondo cobra **Indumotora 6.341M en dividendos** + Sade/Molco/ventas de activos → **posee inversiones cuya tenencia no está en el balance** (solo el flujo de renta).
- **Caja negativa −2.941M = falsa.** Desglose 111xxx: BancoBci +133,7M, Banco Edwards +18,3M, Caja US$ +2,7M (real ~+155M), y **`LeoPartnershipLimited-111012` −3.096,1M** = vehículo de inversión en "disponible" arrastrado a negativo (error B EAG). La caja real es positiva.
- **Propiedades/aviones/yates** (Vía Gris, Molco, Miami, aviones, Keiki Kai): no figuran como activo; solo como **gasto JAB** al consumirse.
- **Apertura 2021-01-01 "Saldo Inicial"** cargó bancos (BancoBci 327M) y algunas CxC, pero **ninguna inversión ni patrimonio**.

**Consecuencia:** el "balance" del FFCC es en realidad **caja + cuentas corriente de socios**, no un balance completo. **No es determinable el patrimonio real del fondo desde Laudus.** Por eso NO se puede afirmar si los saldos a favor de los hijos están o no respaldados — el lado de los activos está incompleto. Mismo hueco de inversiones que EAG (auditoría ≈26.193M diferida).

## Respuestas a las preguntas de la story 13.1

**Q1 — Signo:** mecánicamente débito = debe / crédito = el fondo le debe, correcto. Pero es un **mislabel**: son cuentas corriente/patrimonio de socios, no por cobrar. Mismo patrón que TC (pasivo→gasto) e inversiones EAG (retiros mal imputados).

**Q2 — Quiebre desde 2023:** 2021-2022 cerraban a 0 (reparto=retiro); desde 2023 acumulan crédito. Como Equity FFCC = 0, estas cuentas *son* el patrimonio de facto. **Bandera roja, NO corregir sin cruzar contra el reparto real acordado.** Ítem de auditoría diferido (no bloquea el reporte).

**Q3 — Presentación:**
- Estado de **cuenta corriente por socio**: saldo inicial + retiros − asignaciones/repartos = saldo final, con etiqueta de signo ("A favor" / "Debe al fondo").
- **Netear asientos wash** (ruido; el saldo neto es lo limpio).
- **Separar** familiares (Retiros*, nombres propios) de operativas (~0).
- **Marca de limitación** al pie (estilo TC), pero **honesta, sin afirmar (des)respaldo**: *"El patrimonio real del fondo no es determinable desde Laudus — no están cargadas las inversiones (Indumotora, etc.) ni las propiedades/aviones/yates; la caja total (−2.941M) es artificial por una cuenta de inversión mal clasificada (Leo Partnership). Estas cuentas reflejan flujos de la cuenta corriente de cada socio, no la posición neta."* NO usar el total de caja como "lo que tiene el fondo".

**Q4 — Vista de mayor valor:** no "cuánto debe cada uno" a secas (engañoso: mostraría miles de millones "a favor" sin contexto). La vista que cambia una decisión = **cuenta corriente del socio** (asignado vs retirado vs saldo) **+ la advertencia de que el balance del fondo está incompleto**. La pregunta real de fondo — *"¿el fondo se está descapitalizando?"* — **no se puede responder hoy** porque las posiciones de inversión y los activos reales no están cargados. Eso es, en sí, el hallazgo de mayor valor.

## Recomendación para la story 13.1

1. **Construir sí** — los flujos de cuenta corriente son reales y fieles a Laudus.
2. Sección de distribuciones = **estado de cuenta corriente por socio** (no "por cobrar"), signos etiquetados, wash neteado, familiares vs operativas separadas.
3. **Marca de limitación obligatoria** (estilo TC), pero **honesta**: balance del fondo INCOMPLETO (inversiones/propiedades no cargadas), caja total no usable, patrimonio real no determinable. NO afirmar (des)respaldo de los saldos.
4. **Ítem de auditoría diferido** (no bloquea el reporte): (a) cargar/estimar las posiciones de inversión del FFCC (Indumotora, Sade, Molco, Leo Partnership) + propiedades/aviones/yates = el mismo hueco de EAG; (b) `LeoPartnershipLimited-111012` en −3.096M (error B: retiro contra el activo) — revisar; (c) cruzar reparto asignado 2023-25 vs reparto real acordado. → watchlist Fondo Común, junto a bancos e inversiones. **Es el mismo problema estructural que la auditoría inversiones EAG (≈26.193M) — el RUT2 lo confirma en un 2º libro.**

## Enlaces

- Sondeo retiros/repartos/saldo por año: `_forense_retiros_rut2.py`
- Story: `_bmad-output/implementation-artifacts/13-1-reporte-gastos-rut2.md`
- Contexto de negocio previo: `valentina-contexto-fondo-comun-jab-2026-07-11.md` (§4 watchlist, EAG retira del FFCC vía 115023)
- Clasificación firmada: `clasificacion-contable-rut2-firmada-2026-07-11.md`
