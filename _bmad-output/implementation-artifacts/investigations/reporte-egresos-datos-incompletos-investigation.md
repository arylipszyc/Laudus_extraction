# Investigation: Reporte de gastos EAG no cuadra con Laudus (faltan meses recientes)

## Hand-off Brief

1. **What happened.** El reporte de la app (`GET /reportes/gastos`, 2026-01-01→2026-05-31) muestra los egresos/ingresos **completos en ene/feb, parciales en marzo, casi vacíos en abril y en cero en mayo** — Confirmado por comparación celda a celda contra la planilla Laudus del contador.
2. **Where the case stands.** Root cause aislado a la **fuente de datos** (`ledger_final` en Google Sheets), NO al generador del reporte: donde hay data, el reporte reproduce a Laudus al peso (Casa Sur ene/feb = 100% exacto). La completitud decae por recencia → firma de un **sync incremental detenido ~principios de marzo**. Falta evidencia en vivo del *por qué* del corte.
3. **What's needed next.** Disparar `POST /sync/trigger` y regenerar el reporte: si mar–may se llenan, era freshness/sync stale; si no, el sync incremental tiene un bug de catch-up (revisar pestaña `date_range` y logs).

## Case Info

| Field            | Value                                                                      |
| ---------------- | -------------------------------------------------------------------------- |
| Ticket           | N/A                                                                        |
| Date opened      | 2026-06-15                                                                 |
| Status           | Active — root cause WHERE confirmado (High); mecanismo del corte por confirmar |
| System           | Epic 10 reportes · backend/app/api/v1/reportes · fuente Google Sheets `ledger_final` |
| Evidence sources | 2 xlsx (Laudus contador + reporte app), report_builder.py, router.py, pipeline/sync.py, pipeline/utils/dates.py |

## Problem Statement

(Ary) "El reporte al 31 de mayo no coincide con los valores de Laudus. Faltan muchos números y hay algunos diferentes."
Evidencia: Laudus = `C:\Users\AL-PC\Downloads\Gastos EAG 05-2026.xlsx`; app = `C:\Users\AL-PC\Downloads\Reporte gastos EAG 2026-01-01_2026-05-31 Euge.xlsx`.

## Evidence Inventory

| Source | Status | Notes |
| ------ | ------ | ----- |
| Reporte app (xlsx) | Available | 1 hoja `Reporte`, 281 filas. May (col 05/2026) **0 filas con valor**; abril 8 filas |
| Planilla Laudus (xlsx) | Available | Hoja `Resúmen` con columnas mensuales ene..may — fuente de verdad del contador |
| report_builder.py | Available | Lógica de agregación correcta; rango de meses incluye mayo |
| router.py | Available | Solo LEE `ledger_final`; no calcula contra Laudus en vivo |
| pipeline/sync.py + dates.py | Available | Sync incremental: `get_date_range` va de last `dateTo`+1 a **hoy** (no a fin de mes) |
| Pestaña `date_range` (último `dateTo` sincronizado) | **Missing** | Confirmaría dónde se detuvo el sync — requiere acceso al Google Sheet en vivo |
| Logs del último `POST /sync/trigger` | **Missing** | Confirmarían si el sync corrió, falló a medias, o no se disparó |

## Confirmed Findings

### Finding 1: La completitud del reporte decae por recencia (ene/feb full → mayo vacío)

**Evidence:** Comparación por centro de costo, mes a mes (LAUDUS vs APP, % capturado):

```
Casa Sur          ene 100% · feb 100% · mar 33% · abr 0% · may 0%
Depto Santiago    ene  88% · feb  69% · mar 73% · abr 1% · may 0%
Gastos Personales ene 102% · feb 104% · mar 40% · abr 1% · may 0%
Depto Miami       ene 100% (resto 0 en ambos)
```

**Detail:** Casa Sur ene/feb calza **exacto** (30.255.784 y 9.394.649 idénticos). A partir de marzo el monto capturado cae monótonamente con la recencia. Mayo: 0 filas con valor en todo el reporte (verificado: ene 46 filas, feb 33, mar 33, abr 8, may 0).

### Finding 2: El generador del reporte es correcto — está exonerado

**Evidence:** `report_builder.py:92-97` (`_months_in_range`) genera correctamente `[2026-01..2026-05]`; `:149-161` mapea cada fila al mes por fecha. Donde la fuente tiene data, el output iguala a Laudus al peso (Casa Sur ene/feb, Depto Miami ene = 100%).

**Detail:** Mayo no sale en cero por un filtro de fecha ni un tope: el rango lo incluye. Sale en cero porque `ledger_final` no tiene (casi) filas de marzo en adelante.

### Finding 3: La fuente es `ledger_final` (Sheets), solo-lectura, poblada por un sync aparte

**Evidence:** `router.py:33` → `build_report(start, end, repo.get_records)`; `report_builder.py:139` → `get_records("ledger_final")`. Comentario `router.py:3-6`: "este endpoint solo LEE lo que ya está en Sheets".

**Detail:** El reporte es una proyección pura de `ledger_final`. Su completitud = la del último sync exitoso. `dates.py:5-13`: el sync del ledger va hasta `datetime.now()` (hoy), así que el corte NO es un límite de fecha hardcodeado — apunta a un sync detenido/incompleto.

## Deduced Conclusions

### Deduction 1: Sync incremental detenido ~principios de marzo

**Based on:** Findings 1, 2, 3.

**Reasoning:** El reporte es proyección pura de `ledger_final` (F3) y su lógica es correcta (F2), entonces el patrón full→parcial→vacío por recencia (F1) refleja exactamente el estado de `ledger_final`. Un sync incremental que se detuvo capturó ene/feb completos, un slice de marzo, y nada después.

**Conclusion:** El defecto está en el pipeline de sync hacia `ledger_final`, no en Epic 10. Las "diferencias" que vio Ary son, en su gran mayoría, **datos faltantes**, no montos mal calculados.

## Hypothesized Paths

### Hypothesis 1: Causa del corte = sync no disparado / freshness (operacional)

**Status:** Open
**Theory:** El reporte se generó con un `ledger_final` viejo; nadie disparó `POST /sync/trigger` después de que Laudus posteara mar–may.
**Would confirm:** Re-disparar el sync → `ledger_final` se llena mar–may → regenerar reporte cuadra.
**Would refute:** Tras el sync, mar–may siguen vacíos.

### Hypothesis 2: Causa del corte = bug de catch-up en el sync incremental

**Status:** Open
**Theory:** El sync corre pero no avanza (pestaña `date_range` con `dateTo` pegado, dedup que descarta filas, o un run que falló a medias dejando marzo parcial).
**Would confirm:** Tras `POST /sync/trigger`, `ledger_final` sigue incompleto Y la pestaña `date_range` muestra un `dateTo` anterior a marzo / logs con error parcial.
**Would refute:** El sync llena todo limpio.

### Hypothesis 3 (secundaria): Diferencias residuales en meses "completos" = reclasificación del contador / TC

**Status:** Open
**Theory:** Depto Santiago (88-73%) y Gastos Personales (102-104%) difieren de Laudus incluso en ene/feb porque la planilla Laudus es la vista **manual recategorizada** del contador (reclasificaciones, desglose de tarjetas de crédito), mientras la app deriva categorías del join `ledger_final`.
**Would confirm:** Cruzar al detalle de cuenta los deltas de ene/feb y ver que son re-mapeos de categoría, no filas ausentes.
**Would refute:** Hay filas de ledger de ene/feb que faltan en `ledger_final`.

## Missing Evidence

| Gap | Impact | How to Obtain |
| --- | ------ | ------------- |
| Último `dateTo` en pestaña `date_range` | Discrimina H1 vs H2 | Abrir el Google Sheet o `repo.get_records("date_range")` |
| Logs del último sync | Confirma si corrió/falló | Render logs / consola del job |
| ¿Laudus ERP tiene mar–may posteado? | Si Laudus tampoco tiene, no es bug del sync sino lag de cierre contable | Consultar Laudus directamente |

## Source Code Trace

| Element | Detail |
| ------- | ------ |
| Síntoma | `report_builder.py:264` rinde celdas vacías cuando el código de cuenta no está en `have` (fuente sin esa fila/mes) |
| Origen real | Fuente `ledger_final` incompleta de marzo en adelante — fuera de Epic 10 |
| Trigger | `pipeline/sync.py:160-169` sync incremental Laudus→Sheets; estado guardado en pestaña `date_range` |
| Condición | Sync detenido/incompleto: `ledger_final` sin filas mar–may |
| Related files | pipeline/sync.py, pipeline/utils/dates.py, backend/app/repositories/sheets_repository.py |

## Conclusion

**Confidence:** High (para el WHERE) · Medium (para el mecanismo exacto del corte)

Confirmado: el reporte de Epic 10 está **correcto**; reproduce a Laudus al peso donde hay datos (Casa Sur ene/feb = 100% exacto). Lo que Ary ve como "faltan números y otros difieren" es, en su mayoría, **datos ausentes en la fuente `ledger_final`**, con completitud que decae por recencia (ene/feb full → marzo parcial → abril sliver → mayo vacío) — la firma de un **sync incremental Laudus→Sheets detenido a principios de marzo**. Queda por confirmar si la causa es operacional (sync no disparado, H1) o un bug de catch-up (H2); un residual menor de reclasificación del contador explica los deltas de ene/feb (H3, baja severidad).

## Recommended Next Steps

### Diagnóstico (decisivo, barato)
1. `POST /sync/trigger` (rol contador/admin) y regenerar el reporte mismo rango.
   - mar–may se llenan → **H1 confirmada** (freshness). Cerrar con runbook: disparar sync antes de exportar.
   - siguen vacíos → **H2**: leer pestaña `date_range` (último `dateTo`) + logs del sync; revisar dedup/avance del incremental en `pipeline/sync.py`.
2. En paralelo, confirmar que Laudus ERP tenga mar–may posteado (descarta lag de cierre contable, no es bug nuestro).

### Fix direction (según resulte)
- H1 → cero código; nota operacional + (opcional) que `/reportes/gastos` gatille/valide frescura antes de exportar.
- H2 → fix en el sync incremental (estado `date_range` / dedup / manejo de runs parciales).

## Reproduction Plan

1. Estado actual: exportar `/reportes/gastos?start=2026-01-01&end=2026-05-31` → mayo en cero, abril sliver (reproducido vía el xlsx entregado).
2. Disparar `POST /sync/trigger`.
3. Re-exportar mismo rango → comparar columnas mar–may contra `Gastos EAG 05-2026.xlsx`.

## Side Findings

- `pipeline/utils/dates.py:33` `get_last_day_of_previous_month` se usa solo para el balance sheet (`sync.py:95`), NO para el ledger — el ledger va hasta hoy. Descarta la teoría "el código corta en fin de mes anterior".
- Deltas ene/feb de Gastos Personales (app 102-104% > Laudus) sugieren que la app suma algo que el contador reclasifica/desglosa (probable TC); revisar si se persigue paridad fina (H3).

## Follow-up: 2026-06-15

### New Evidence (snapshot en vivo de Google Sheets + API Laudus)

- Pestaña `date_range`: último `dateTo = 2026-06-15` (hoy). El sync SÍ corre y avanza al día.
- `ledger` (crudo): 18.036 filas, max date 2026-06-12. Tiene mayo (29) y junio (14) filas, pero pocas.
- `ledger_final` (lo que lee el reporte): **17.916 filas, max date 2026-04-13** — congelado. Grilla = 17.917 (exacta).
- `plan_lookup` carga 293 cuentas OK; `enrich_ledger_row` no rompe en ninguna de las 18.036 filas.
- gspread 6.2.1 `ws.update` **auto-expande** la grilla (repro temp 100→151) → teoría "grid limit" **refutada**.
- `python -m pipeline.sync` local: rebuild OK, `Reemplazando 18036 filas en ledger_final`. Reparó el freeze.
- **API Laudus directo** (con `accountNumberFrom`), gasto (cuentas 4/6/7/8/9xx) por mes vs nuestro `ledger`:
  ene 100.542.838/100.542.838 (100%) · feb 80.327.134/80.247.134 (~100%) · mar 85.998.520/35.581.225 (41%) ·
  abr 338.177.905/37.273.164 (11%) · may 275.021.496/23.922.044 (9%). Ej cta 413900 Casa Sur mayo: API $120.871.410 vs ledger $0.

### Additional Findings — DOS bugs confirmados

**Bug #1 (Confirmed, data reparada): rebuild de `ledger_final` fallaba en silencio en Render.**
El `ledger` crudo se actualiza ANTES del guard `if plan_lookup:` (sync.py:213); el rebuild de `ledger_final` queda detrás.
En Render venía fallando/abortando desde ~13-abr (timeout/OOM/rate-limit — falta log de Render para fijar cuál) y el
`except` global de `sync_api` (sync.py:250) **se traga el error**: `date_range` avanza (sync.py:202), `ledger` crece,
`ledger_final` queda congelado. Correr el sync local lo reescribió a 18.036 filas / 12-jun. **Reparado.**

**Bug #2 (Confirmed, NO reparado): el sync incremental sub-extrae los meses recientes.**
Watermark forward-only (`date_range.dateTo`→hoy; `get_date_range` = dateTo+1..hoy) **nunca re-busca asientos posteados
tarde/retroactivos**. El contador postea/ajusta gastos de un mes durante semanas; una vez que la ventana pasó y
`date_range` avanzó, esos asientos no se re-piden jamás → ene/feb completos, mar 41%, abr 11%, may 9% (decaimiento por
recencia). Por esto, aun con Bug #1 reparado, el reporte regenerado sigue sin cuadrar.

### Updated Hypotheses
- H1 (freshness): **Refutada** — el sync corre, `date_range`=hoy.
- H2 (catch-up bug): **Confirmada en DOS capas** — (a) rebuild `ledger_final` (Bug #1), (b) under-fetch incremental por late-posting (Bug #2).
- H3 (reclasificación ene/feb): residual menor, baja prioridad.

### Side Findings (nuevos)
- Anomalía junio: ledger gasto jun $179.605.570 (6 filas) vs API $359.667 — monto grande en junio que la API no devuelve (¿fecha mal asignada del asiento Jael ~179M?). Revisar; no bloquea el diagnóstico.
- `accountNumberFrom = min(account_numbers)` como **string** (sync.py:179): frágil con códigos de distinto largo.
- `replace_sheet` hace `clear()` antes de `update()`: un SIGKILL/timeout entre ambos deja la hoja vacía (el restore solo corre en excepción Python atrapada).

### Backlog Changes
- Bug #1: sacar el rebuild del swallow silencioso; alertar si `len(ledger_final) != len(ledger)`; no avanzar `date_range` hasta confirmar rebuild. Buscar log Render para la causa puntual.
- Bug #2: incremental con **ventana solapada** (re-sincronizar últimos N meses cada corrida). Backfill inmediato 2026 vía upsert idempotente (clave journalentryid_lineid) para recuperar lo faltante.

### Updated Conclusion
**Confidence: High.** El reporte de Epic 10 es correcto. Causa 100% upstream en `pipeline/sync.py`, dos bugs:
(1) rebuild de `ledger_final` fallaba en silencio en Render → reporte pegado en 13-abr — **reparado** al correr el sync;
(2) sync incremental forward-only sub-extrae meses recientes porque no re-pide asientos posteados tarde — **pendiente**,
requiere backfill + ventana solapada. La "diferencia con Laudus" = datos faltantes en la fuente, no cálculo errado.

**Status:** Active — Bug #1 data reparada; Bug #2 pendiente de backfill + fix de código.

## Follow-up: 2026-06-15 #2 (backfill ejecutado — causa raíz REAL de Bug #1 confirmada)

### Causa raíz REAL de Bug #1 (CONFIRMED, supera las hipótesis previas)
No era timeout/OOM/rate-limit de Render (esas eran Hipótesis no confirmadas). Al correr el backfill, el rebuild de
`ledger_final` crasheó: `ValueError: invalid literal for int() with base 10: '02T00:00:00'` en
`models.py:_eomonth` (`pipeline/models.py:120`). La API de Laudus devuelve fechas ISO con separador **"T"**
(`2026-06-02T00:00:00`); `_eomonth` solo partía por **espacio** (`split(" ")[0]`), formato que Sheets reescribe al
releer. Por eso `ledger_final` se rebuildeaba bien cuando NO había data nueva (re-lee Sheets → formato con espacio)
y **crasheaba en cuanto llegaba data nueva** (formato "T" desde la API en `merged_ledger`) → el `except` global de
`sync_api` lo tragaba → `ledger_final` congelado. Eso explica el corte exacto en 13-abr.

**Fix aplicado:** `pipeline/models.py:122` → `d = str(date_str).split(" ")[0].split("T")[0]` (acepta ambos
separadores). Surgical, una línea. **Pendiente de deploy a Render** — sin deploy, `ledger_final` se re-congelará en
la próxima sync de Render que traiga data nueva.

### Backfill ejecutado (data reparada)
Re-fetch Laudus 2026-01-01..hoy (1.503 filas) → upsert idempotente a `ledger` (18.036 → **18.581**, +545 asientos
mar–may recuperados) → rebuild `ledger_final` (18.581, max date 12-jun) → copia a `ledger_eag`. Verificación reporte
vs planilla Laudus: **Casa Sur 100% exacto ene–may** (mayo $136.203.633, antes $0).

### Residual (esperado, NO es bug)
Deltas restantes vs la planilla del contador = el app lee el **ERP crudo** mientras la planilla es la vista
**manual reclasificada** del contador. Ej. Gastos Personales mayo: app $131.9M (= 430xxx reales en Laudus ERP) vs
planilla $48.9M (el contador aún no terminó de procesar/reclasificar mayo). Depto Santiago queda 70–88% en meses
viejos por la misma razón (reclasificación). El app ahora **refleja fielmente Laudus ERP**, que es su trabajo.

### Pendientes para durabilidad
1. **Deploy del fix `_eomonth`** a Render (si no, Bug #1 recurre).
2. **Story de fix de sync** (Bug #2): ventana solapada (re-fetch últimos N meses) + sacar el rebuild del swallow
   silencioso (alertar si `len(ledger_final) != len(ledger)`; no avanzar `date_range` hasta confirmar rebuild).
   Hasta que esto exista, los asientos posteados-tarde se seguirán perdiendo → habría que re-correr el backfill
   periódicamente como parche.

**Status:** Bug #1 — causa raíz confirmada + fix en código (falta deploy). Bug #2 — data reparada vía backfill;
fix durable pendiente como story. Reporte de Epic 10 verificado correcto contra la fuente.

## Follow-up: 2026-06-15 #3 (comparación reporte nuevo post-fix → Bug #3 mapeo template)

Ary generó reporte nuevo (post deploy `_eomonth` + backfill) y detectó RETIROS FONDO COMUN $100M en Laudus pero en
blanco en el app. Comparación completa app-nuevo vs Laudus:
- **EGRESOS: cuadra** (los fixes de sync + backfill lo resolvieron; Casa Sur 100%). Líneas de ingreso con código
  correcto ahora traen todo (IP Chile, Indumotora, Otros, Isapre mar–may completos).
- **Bug #3 (CONFIRMED, FIXED+DEPLOYED): códigos de cuenta mal mapeados en `template_order.json` (lado INGRESOS).**
  El Excel del contador rotula cuentas con códigos que NO son el número real de Laudus. Auditado todo INGRESOS:
  3 cuentas con plata real 2026 que el template no capturaba (verificado contra ledger_final):
  - RETIROS FONDO COMUN: template `310-004` → real **310006** ($100M feb)
  - RETIROS TECNION (Johanna): template `""` → real **870011** ($3M/mes = $15M)
  - OTROS INGRESOS JAEL: template `9301-099` → real **970099** ($2M may)
  Fix: 3 códigos corregidos en `template_order.json`, commit `519d951` → cherry-pick `55b71e6` a `main` → Render.
  Regenerado: las 3 líneas resuelven con el monto exacto. Egresos no afectados (sus códigos sí coincidían).

**Status final:** Bug #1 (`_eomonth`) fixed+deployed. Bug #2 (under-fetch) data parchada (backfill); fix durable
= story pendiente. Bug #3 (template INGRESOS) fixed+deployed. Reporte ahora cuadra con Laudus salvo reclasificación
manual del contador (esperado). Caso CONCLUIDO salvo la story de Bug #2.
