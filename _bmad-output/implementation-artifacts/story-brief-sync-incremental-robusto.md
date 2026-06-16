# Story brief — Sync incremental robusto (ventana solapada + falla visible)

> Input para `bmad-create-story`. Origen: investigación 2026-06-15 (Bug #2),
> case file `investigations/reporte-egresos-datos-incompletos-investigation.md`.

## Ubicación sugerida
**Epic 10 (Reportes) como 10.4** — es el epic activo y el reporte es el consumidor/valor.
Linaje técnico: es una regresión de **Epic 2 / Story 2.2 "incremental-sync-deduplicación-y-confiabilidad"**
(el sync `pipeline/sync.py`). Ary decide si va como 10.4 o como reapertura de Epic 2.

## Título
Sync incremental Laudus→Sheets: ventana solapada para asientos posteados-tarde + rebuild que no falla en silencio.

## Contexto / problema (verificado con datos)
El sync incremental (`pipeline/sync.py`) usa un watermark forward-only: lee `date_range.dateTo`, pide a Laudus solo
`[dateTo+1 .. hoy]` filtrando por **fecha contable**, y avanza `dateTo` a hoy. La contabilidad se postea/ajusta
semanas después y con fechas backdateadas → todo asiento cuya fecha contable quede **detrás** del watermark cuando
aparece en Laudus **no se re-pide nunca** = pérdida permanente de datos. Medido (gasto capturado vs Laudus API):
ene/feb 100%, mar 41%, abr 11%, may 9%. Ej: Casa Sur mayo cta 413900 = $120M en Laudus, $0 en el reporte.

Agravante: `sync_api` envuelve todo en un `try/except` global (`sync.py:250`) que se traga el error. El rebuild de
`ledger_final` (después del watermark) puede fallar mientras `date_range` ya avanzó y `ledger` ya se actualizó →
estado parcial silencioso. (El crash puntual `_eomonth` ya se arregló por separado; el patrón silencioso queda.)

Nota API: `/accounting/ledger` NO expone timestamp de creación (solo `date`, editable, filtrable por fecha). Un
cursor por `modifiedAt` no es viable en ese endpoint (se probó, `/journalEntries` etc. → 404). Por eso la solución
es ventana solapada, no cambio de cursor.

## Acceptance Criteria
1. El sync re-pide en cada corrida una **ventana solapada hacia atrás** (no solo forward): por defecto el año fiscal
   en curso + margen para backdating de fin de año anterior (≈ últimos 13 meses), configurable por env. Asientos
   posteados-tarde/backdateados dentro de la ventana se recuperan en la corrida siguiente.
2. El upsert sigue siendo idempotente (clave `journalentryid_lineid`) — re-pedir no duplica ni pierde filas ya
   presentes. Test: dos corridas seguidas dejan `ledger` bit-idéntico.
3. Test de regresión del bug: un asiento con fecha contable en un mes pasado-pero-dentro-de-ventana, ingresado
   después de que el watermark pasó ese mes, **aparece** en `ledger` tras el sync (hoy no aparece).
4. El fallo del rebuild de `ledger_final` deja de ser silencioso: si el rebuild lanza, o si tras la corrida
   `len(ledger_final) != len(ledger)` (módulo colapso conocido de "Saldo anterior" journalEntryId=0), se loguea
   error/alerta y se refleja en `/sync/status`.
5. `date_range` no avanza a un watermark nuevo salvo que la corrida completa (incluido el rebuild de `ledger_final`)
   haya tenido éxito. Una corrida que falla a medias es re-intentable.
6. Documentar el tamaño de ventana elegido y que el backfill manual deja de ser necesario como parche recurrente.

## Notas técnicas (puntos de cambio)
- `pipeline/utils/dates.py:get_date_range` (líneas 5-13): hoy `date_from = dateTo+1`. Cambiar a
  `date_from = min(dateTo+1, inicio_de_ventana_solapada)`; `date_to = hoy`.
- `pipeline/sync.py` ledger incremental (145-208), rebuild `ledger_final` (210-226), `except` global (250):
  separar el éxito del rebuild del avance de `date_range`; no tragar el error del rebuild.
- Conteo de control `ledger` vs `ledger_final` post-rebuild; superficie en `/sync/status` (ya existe el endpoint).
- Idempotencia ya garantizada por `upsert_to_sheet` (clave journalentryid_lineid).

## Fuera de alcance
- Migración al motor Beancount (Epic 9) — esto es el pipeline legacy de Sheets.
- Deltas por reclasificación manual del contador (divergencia esperada app-ERP vs planilla).
- El fix `_eomonth` (ya deployado) y los 3 códigos de template INGRESOS (ya deployados).

## Referencias
- Case file: `_bmad-output/implementation-artifacts/investigations/reporte-egresos-datos-incompletos-investigation.md`
- Memoria: `project_reporte_gastos_auto.md` (sección Investigación 2026-06-15).
