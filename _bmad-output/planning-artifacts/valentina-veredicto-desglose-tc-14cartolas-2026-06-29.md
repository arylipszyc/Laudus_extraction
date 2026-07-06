# Veredicto contable — Desglose TC contra 14 cartolas reales (dry-run)

- **Fecha:** 2026-06-29
- **Autora:** Valentina (asesora financiera LAUDUS)
- **Contexto:** dry-run en sandbox de las 14 cartolas reales de `samples/` (3 tarjetas × CLP/USD ×
  feb/mar/abr 2026), tras el fix "contabiliza todo operation_type" (en prod, commit `26aacf4`).
- **Insumo:** reporte del batch (11 corrected / 3 blocked, `unmapped` vacío en las 14).

## Resumen ejecutivo

El motor del desglose está **bien y es honesto**: bloquea lo que no puede cuadrar en vez de inventar.
Los 3 bloqueos USD **no son bug ni "estado impago"** — son **data sucia de Laudus** en las tarjetas
Santander. Los obstáculos para materializar son de **datos, no de código**.

## ⚠️ CORRECCIÓN (2026-06-29, tras 2 rondas de Ary insistiendo — tenía razón)

La conclusión inicial ("faltan los pagos" / "Laudus mal atribuido, hay que limpiarlo") estaba MAL.
Al ver los **asientos completos** (no solo la línea que toca la cuenta-gasto), la verdad es:

- **Los pagos ESTÁN en Laudus, bien posteados por cuenta.** Santander paga las tarjetas Santander con
  asientos **consolidados**: UN asiento "Visa Santander 0858" paga 4 cuentas TC a la vez (Master CLP+USD,
  Latanpass CLP+USD) desde la cta cte Santander. La glosa nombra UNA tarjeta y UN USD aunque paga varias.
- **El problema es el MATCHER, no la data.** `derive_statement_fx` matchea por la **glosa de texto**
  (`USD == closing`), que Santander llena inconsistente. Pero el **monto CLP que entró a la cuenta de
  cada tarjeta** sí es correcto y da un FX sano:
  - Mastercard 8996 USD feb (closing 1.387,63): 2026-03-06 → **1.291.675 CLP / 1.387,63 = FX 930,8 ✅**
  - Latanpass 0858 USD feb (closing 3.217,07): 2026-03-06 → **3.000.722 CLP / 3.217,07 = FX 932,7 ✅**
  - Mastercard 8996 USD mar (closing 2.234,84): NINGÚN posting da FX sano → **turbio de verdad**.
    OJO: 2026-05-06 postea **51.301.494 CLP a la cuenta MasterUs** (~57.000 USD) = muchísimo más que el
    closing → pago acumulado de varios meses o misposteo (¿debería ir a la cuenta CLP?). Necesita revisión humana.

- **Fix correcto (cambia respecto a lo de abajo): NO es FX-BCCh ni limpiar Laudus.** Es **augmentar el
  matcher**: cuando la glosa no cuadra, caer a `CLP posteado a la cuenta de esta tarjeta ÷ closing`, con
  el chequeo BCCh existente como red de seguridad (rechaza FX absurdos, acepta ~930). Recupera las
  consolidadas SIN romper el cuadre exacto §12.1 (usa la plata real, no tasa estimada). Marzo Mastercard
  sigue bloqueado hasta aclarar el lump de 51,3M.

## (Diagnóstico inicial — SUPERSEDED por la corrección de arriba) Pagos USD Santander

La derivación del FX (mi diseño §12.1) busca el pago Laudus cuya glosa codifica `USD == closing` del
estado. Comparé las glosas reales de las 3 tarjetas USD:

**Visa Infinity USD (BCI 1027) — LIMPIA → los 3 meses cuadraron (FX 931/902/899):**
```
2026-03-09    433.488 CLP | "USD465,59 Visa BCI 1027 Febrero 2026"
2026-04-16  7.808.845 CLP | "USD8.652,46 Visa BCI 1027 Marzo 2026"
2026-05-14 23.543.848 CLP | "USD26.188,93 Visa BCI 1027 Abril 2026"
```
Un pago por mes, USD de la glosa == closing del estado.

**Mastercard 8996 USD + Latanpass 0858 USD — CROSS-POSTEADAS:**
```
Cuenta Mastercard 8996:  "USD3.217,07 Visa Santander Febrero 2026" → 1.291.675 CLP
Cuenta Latanpass 0858:   "USD3.217,07 Visa Santander Febrero 2026" → 3.000.722 CLP   ← mismo USD, CLP distinto
Cuenta Mastercard 8996:  "Visa Santander 0858 Eduardo Avayu"        ← glosa de Latanpass en cuenta Mastercard
Cuenta Mastercard 8996:  "USD12.658,96 Mastercard Santander EAG"    (dic-2025)
```

**Evidencia dura:** la misma glosa con el mismo USD aparece en DOS cuentas con CLP distinto — imposible
si fuera un pago real único. Las glosas mezclan "Visa Santander 0858" dentro de la cuenta Mastercard.
Y **ninguna glosa trae los USD de los estados bloqueados** (1.387,63 / 2.234,84 / 1.967,62 no existen).

**Interpretación:** Santander factura/registra los pagos USD de las tarjetas Santander de forma
consolidada o mal atribuida — no por tarjeta-por-estado. El motor correctamente NO puede derivar un FX
por estado → bloquea. **El error vive DENTRO de Laudus** (mismo patrón que el error de inversiones
2026-06-20: Beancount es espejo fiel, el error es de Laudus, la paridad vs contador no lo pesca).

## Q2 — Contigüidad (no es defecto)

La apertura ancla **una sola vez** por tarjeta; cada estado mueve el saldo desde ahí. Un mes faltante
desfasa el pasivo por la actividad de ese mes. **La itemización de gastos funciona estado por estado
con o sin hueco** — solo se desfasa el cuadre del SALDO del pasivo, no el reporte de gastos.

- Mastercard CLP (feb/mar/abr) → contigua ✅
- Latanpass CLP (feb/mar) → contigua ✅
- Visa Infinity CLP (feb + abr) → **falta marzo** ⚠️ (su pasivo no cuadra hasta traerlo)

## Q3 — Packet BCI Visa Infinity 2026-04

Contablemente correcto: pasivo cuadra, impuesto+comisión 6.795 a `GastosBancarios-430003` (cuenta que
SÍ entra al reporte), 34 compras a `Suspense` esperando categorización. **Asterisco:** el −3.219.948
vale con abril como ANCLA (apertura propia). En corrida continua abril es continuación y necesita marzo
(Q2); por eso el batch dio −1.165.634 abril-tras-feb. No es error, es la contigüidad.

## Recomendación

Materializar primero **lo limpio**, dejar lo sucio bloqueado:

| Materializar ya | Esperar |
|---|---|
| CLP de las 3 tarjetas (corridas contiguas) | USD Mastercard 8996 (limpiar Laudus) |
| Visa Infinity USD (BCI, glosas limpias) | USD Latanpass 0858 (limpiar Laudus) |
| | Visa Infinity CLP: traer marzo antes de cuadrar |

**No forzar un FX** para destrabar las USD Santander — el bloqueo protege el pasivo. El fix es upstream
(Laudus atribuye los pagos USD por tarjeta) o, si no se puede, una estrategia de FX distinta para
tarjetas de pago consolidado (story aparte, no romper la regla de cuadre exacto §12.1).

## Limitación a marcar en reportes

Mientras las USD Santander estén bloqueadas, el gasto USD de Mastercard 8996 y Latanpass 0858 sigue
**lumpeado en la cuenta TC original** (no itemizado). Cualquier reporte de gasto de esas tarjetas debe
advertirlo. El lado CLP de esas tarjetas y toda la Visa Infinity ya son itemizables.
