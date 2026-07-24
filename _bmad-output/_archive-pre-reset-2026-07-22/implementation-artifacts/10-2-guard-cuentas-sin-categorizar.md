# Story 10.2: Guard interino — cuentas sin categorizar no se pierden en silencio

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **contador**,
I want **que el reporte de gastos marque visiblemente la plata de cuentas que llegan sin categoría (cuentas nuevas creadas en Laudus, ausentes del plan de cuentas)**,
so that **no reciba totales cortos en silencio y sepa qué cuentas faltan categorizar**.

## Acceptance Criteria

1. **Detección:** tras armar todas las secciones del reporte, el builder identifica las cuentas con movimiento en el período (`have`) que NO fueron surfaced en ninguna parte — es decir, cuyo monto no quedó contado en ningún centro de costo del RESUMEN (su `Categoria2` no es ninguno de los buckets conocidos) ni renderizado como línea de detalle (código ausente de `template_order.json`).
2. **Ubicación por prefijo:** cada cuenta sin categorizar se etiqueta con el centro de costo deducido del **prefijo del número de cuenta** (mapeo 1:1 verificado contra `laudus_dump.json`): `411`/`4101`→Departamento Santiago, `413`→Casa Sur, `415`→Departamento Miami, `430`→Gastos Personales, `690`→Jocelyn, `790`→Jeannette, `890`→Johanna, `970`→Jael, `310`→Ingresos. Una cuenta cuyo prefijo no calce con ninguno conocido se etiqueta como "(prefijo desconocido)".
3. **Visibilidad + total correcto:** se renderiza una sección/fila visible **"⚠️ CUENTAS SIN CATEGORIZAR"** con una fila por cuenta (etiqueta = `accountName` de Laudus + CC deducido, valor = monto por mes), y su monto **se incluye en `TOTAL EGRESOS`** (y/o en el subtotal del CC correspondiente) de modo que el total headline del reporte deje de quedar corto. La plata nunca queda invisible.
4. **Test de regresión:** un test nuevo reproduce el caso exacto del defecto — un `get_records` fake que devuelve una cuenta con movimiento + `Categoria1/2/3` vacías + prefijo conocido (ej. `413077` = Casa Sur, $9.999.999) — y asserta que (a) el monto APARECE en el xlsx (hoy NO aparece en ninguna celda) y (b) está contado en `TOTAL EGRESOS`. Incluir además el caso de prefijo desconocido (va al balde sin etiqueta de CC).
5. **No-regresión:** los centros de costo ya validados siguen cuadrando exacto (Depto Santiago 343.642.326, Casa Sur 325.427.059, Miami 44.847.240, Gastos Personales 1.222.812.075 para 2025). El guard es **estrictamente aditivo** — no modifica las fórmulas de subtotal/total existentes salvo para sumar el nuevo bucket.

## Tasks / Subtasks

- [x] Task 1 — Helper de deducción por prefijo (AC: 2)
  - [x] Agregado `EAG_EXPENSE_PREFIX` (semilla 411/413/415/430→CC) + `_cc_prefix(code)` (normaliza 4101→411, devuelve prefijo de 3 díg). Prefijos de hijas se aprenden de la data ya categorizada en `build_report`.
- [x] Task 2 — Detección de cuentas sin categorizar (AC: 1)
  - [x] En `build_report`, tras el loop cat1/cat2, se detecta `have` con **categoría en blanco** (firma exacta del defecto: cuenta nueva ausente del plan). Se confirmó que el resumen las pierde en `cat2[""]`.
  - [x] **Refinamiento sobre el plan original:** se gatilla por categoría en blanco, NO por "categoría que no es de gasto" — si no, los activos de banco de las hijas (DISPONIBLE, prefijos 610/710/810/910) salían como falsos positivos. Verificado contra el dump real.
- [x] Task 3 — Render de la sección "⚠️ CUENTAS SIN CATEGORIZAR" (AC: 3)
  - [x] Sección al final con una fila por cuenta (`accountName · CC · código`) + subtotales.
  - [x] El bucket de CC conocido se suma a `TOTAL EGRESOS` de forma aditiva (tercer término del `cells_formula`). El bucket "prefijo desconocido" se muestra pero NO se suma.
- [x] Task 4 — Tests (AC: 4, 5)
  - [x] Creado `backend/tests/test_reportes.py` (no existía ninguno).
  - [x] Test de regresión del defecto (413077 sin categoría → aparece y suma a TOTAL EGRESOS).
  - [x] Test prefijo desconocido (888001 → visible, no sumado) + test no-regresión (cuenta categorizada → guard no dispara).
  - [x] No-regresión validada contra el dump real 2025: guard **inerte**, los 4 CC exactos (343.642.326 / 325.427.059 / 44.847.240 / 1.222.812.075).

## Dev Notes

### Por qué el bug existe (mecanismo exacto — ya reproducido)

`build_report` indexa los movimientos por `accountnumber` en `laudus[code]` y arma `have = {c for c in laudus if any(laudus[c])}`. Pero una cuenta solo se SURFACEA por dos caminos, y una cuenta sin categoría no cae en ninguno:

- **RESUMEN** (`report_builder.py` bloque "EGRESOS (resumen)"): suma por `cat2[str(r.get("Categoria2",""))]`. Una cuenta con `Categoria2` vacía cae en `cat2[""]`, bucket que el loop de los 4 CC **nunca lee** → su plata se descarta.
- **DETALLE** (`render_template`): matchea por código contra `template_order.json` (lista fija). Un código nuevo no está → no se renderiza, no entra en `used`.

Resultado verificado (cuenta `413077`, $9.999.999, sin categoría): "NO APARECE EN NINGUNA PARTE", y `TOTAL EGRESOS` queda corto sin aviso.

### Datos de soporte (verificados contra `bootstrap/_cache/laudus_dump.json`, 17.916 filas)

- Prefijo (3 díg) → `Cat1` y `Cat2` es **1:1** (0 ambiguos). Prefijo → `Cat3` NO (7 prefijos con varios valores). Por eso el guard puede deducir el CC (Cat1/Cat2) por prefijo, pero NO el rubro fino — eso queda para Story 10.3 (categorización con criterio humano).
- El mapeo de prefijos de AC2 es exactamente el observado en el dump.

### Archivos a tocar

- **UPDATE** `backend/app/api/v1/reportes/report_builder.py` — agregar `PREFIX_TO_CC` + `_cc_from_code`, la detección de cuentas perdidas, y el render del bucket. **Estado actual:** ya tiene `have`, `used`, `cat2`/`cat1`, `render_template`, y los helpers `write`/`cells_formula`/`range_formula`. Ya hay **precedente exacto de inyección**: la línea de TC se inyecta antes del subtotal `"TOTAL GASTOS PERSONALES EAG"` (buscar `if lbl == "TOTAL GASTOS PERSONALES EAG":` y `fresh = [c for c in tc_codes ...]`). Seguir ese patrón para no reinventar.
- **NEW** `backend/tests/test_reportes.py` — no existe ninguna prueba de reportes hoy.

### Recomendación de diseño (menor riesgo)

Preferir una **sección de control dedicada** al final de EGRESOS (no weavear dentro de cada subtotal de detalle, que son fórmulas Excel sobre rangos de filas validadas diff=0). La sección lista las cuentas perdidas y su subtotal se **agrega a `TOTAL EGRESOS`**. Así el guard es puramente aditivo y no toca las fórmulas existentes → satisface AC5 con riesgo mínimo. Si el dev encuentra una forma limpia de imputar cada cuenta a su CC sin tocar las fórmulas validadas, también vale, pero la prioridad es: **ninguna plata invisible + TOTAL EGRESOS completo**.

### Patrón de test (reusar el smoke ya probado)

```python
from datetime import date
from backend.app.api.v1.reportes.report_builder import build_report
from openpyxl import load_workbook
import io
rows = [{'date':'2025-03-10','accountnumber':'413077','accountName':'GASTO NUEVO',
         'debit':'9999999','credit':'0','Categoria1':'','Categoria2':'','Categoria3':''}]
out = build_report(date(2025,3,1), date(2025,3,31), lambda s: rows)
ws = load_workbook(io.BytesIO(out)).active
# assert que 9999999 aparece en alguna celda (hoy NO aparece)
```

### Restricción crítica

El guard es **aditivo**. NO cambiar el comportamiento validado diff=0 de los 4 centros de costo (ver AC5). Cualquier cambio a `cat2`, `render_template`, o las fórmulas de subtotal que altere esos totales es una regresión.

### Project Structure Notes

- El feature vive en `backend/app/api/v1/reportes/` (router + report_builder + template_order.json), gateado a rol `contador/admin`. Sin cambios de routing ni de schema. Backend-only, sin UI nueva (la UI de categorización es Story 10.3).

### References

- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-06-10.md#Sección-4.1] — Story 10.2 AC y rationale.
- [Source: _bmad-output/implementation-artifacts/sprint-status.yaml] — epic-10, 10-2-guard-cuentas-sin-categorizar.
- [Source: backend/app/api/v1/reportes/report_builder.py] — build_report, render_template, inyección TC (precedente).
- [Source: bootstrap/sources.py#L19] — Laudus no expone categorías; salen del join con el plan de cuentas.

### Review Findings (code-review 2026-06-10)

- [x] [Review][Patch] Cuenta con categoría en blanco y prefijo no parseable ("") se cae de AMBOS buckets → invisible. RESUELTO: `elif p[:1] in EXPENSE_FIRST_DIGITS or not p` rutea el código no parseable a uncat_unknown. Test nuevo `test_codigo_no_parseable_sin_categoria_sigue_visible`. [backend/app/api/v1/reportes/report_builder.py:~185]
- [x] [Review][Patch] Inconsistencia de gates resumen (`any(uncat_total)`) vs detalle (`if uncat`). RESUELTO: gate unificado a `if uncat:` → la etiqueta "(incluido en TOTAL EGRESOS)" ya no puede mentir. [backend/app/api/v1/reportes/report_builder.py:~327]
- [x] [Review][Defer] Carga de template a nivel de módulo (`with open(TEMPLATE)`) falla en import si falta/corrupto el archivo [backend/app/api/v1/reportes/report_builder.py:~31] — deferred, introducido por el cleanup previo (no por 10.2); decisión deliberada, el archivo se shippea con el código.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Amelia / dev-story)

### Debug Log References

- `pytest backend/tests/test_reportes.py` → 3 passed.
- Suite completa (venv): 476 passed, 1 xfailed, 1 pre-existing FAILED (`test_sync.py::test_run_backfill_calls_upsert_for_both_sheets` — sin relación, ya rojo antes de esta historia), 1 error de colección por dep ausente en el entorno local (`fava`). Mi cambio toca solo `report_builder.py` → cero regresiones.
- No-regresión contra `bootstrap/_cache/laudus_dump.json` (2025): guard inerte, 4 CC exactos.

### Completion Notes List

- **Defecto reproducido y tapado:** una cuenta nueva en Laudus sin categoría (ej. 413077) ya NO desaparece — aparece itemizada y, si su prefijo la ubica en un CC de gasto, suma a `TOTAL EGRESOS`.
- **Detección por categoría en blanco** (no por "no-es-gasto"): evita falsos positivos de activos categorizados (bancos DISPONIBLE de las hijas). Decisión tomada al ver 5 falsos positivos contra data real.
- **Aditivo:** con data categorizada el guard no emite filas → `TOTAL EGRESOS` y los 4 CC quedan idénticos (AC5).
- **Limitación conocida (para Story 10.3):** una cuenta de gasto con prefijo totalmente nuevo (CC nunca visto) cae en el balde "prefijo desconocido" — visible pero no sumada, porque sin categoría ni prefijo conocido no se puede imputar con seguridad. La categorización con criterio humano es justo el scope de 10.3.

### File List

- `backend/app/api/v1/reportes/report_builder.py` (modificado — constantes `EAG_EXPENSE_PREFIX`/`KNOWN_EAG_CAT2`/`EXPENSE_FIRST_DIGITS` + `_cc_prefix`, detección en `build_report`, fila en TOTAL EGRESOS, sección final)
- `backend/tests/test_reportes.py` (nuevo)

## Change Log

- 2026-06-10 — Story 10.2 implementada (Amelia). Guard "cuentas sin categorizar" en el reporte de gastos: detecta cuentas con movimiento y categoría en blanco, las ubica por prefijo, las hace visibles y suma las de CC conocido a TOTAL EGRESOS. Test nuevo `test_reportes.py` (3 casos). No-regresión validada contra dump real. Status → review.
- 2026-06-10 — Code-review (bmad-code-review, 3 capas). 2 patches aplicados (código no parseable → uncat_unknown; gate unificado `if uncat`), 1 deferred (carga template en import), 7 dismissed (incl. falso positivo del casing de "Casa Sur", verificado real). +1 test (4 total). 477 backend passed. Status → done.
