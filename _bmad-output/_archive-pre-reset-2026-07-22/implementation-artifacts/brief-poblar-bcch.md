# Brief — Poblar el dólar BCCh (destraba la automatización del matcher FX)

> ✅ **EJECUTADO — NO CORRER DE NUEVO** (anotado en code-review 2026-07-06). El archivo
> `ledger/_meta/fx-bcch-eom.jsonl` **existe y está poblado** 2025-12→2026-05 (commit `0955d1e`,
> fuente mindicador dólar observado). Además la premisa quedó obsoleta: la banda [850,1000] fue
> **removida del código** — hoy sin BCCh el matcher **bloquea** (no adivina), que es exactamente la
> regla fail-safe del diseño de Valentina. Lo único aún abierto de este brief: script idempotente de
> actualización mensual + tests (alcance 2 y 4). Ojo: el ejemplo `958.34` de abajo es **ficticio**
> (el fx real de 2026-04 fue ~899) — no copiarlo como dato.

**Para correr en otra ventana.** Objetivo: poblar `ledger/_meta/fx-bcch-eom.jsonl` con el tipo de cambio
CLP/USD de cierre de mes, para que el matcher FX de tarjetas use el dólar real en vez de la banda de
plausibilidad [850,1000] que hoy es un stopgap.

## Por qué

El matcher FX (`pipeline/importers/tc_correction.py` → `derive_statement_fx`) y su validador
(`pipeline/importers/fx_calculator.py` → `lookup_bcch` / `calculate_fx`) usan el **dólar observado de
cierre de mes** para (1) validar que el FX derivado de un pago sea plausible y (2) elegir el posting
correcto en pagos consolidados. Hoy el archivo **no existe** → el validador devuelve `fx-bcch-missing`
(no bloquea) y el matcher cae a la banda. Con BCCh poblado, el matcher pasa a ser exacto y robusto.

## Contrato del archivo

`ledger/_meta/fx-bcch-eom.jsonl` — una línea JSON por mes (ver `fx_calculator.lookup_bcch`):
```json
{"year_month": "2026-04", "rate_clp_per_usd": "958.34"}
```
- `year_month`: `YYYY-MM`.
- `rate_clp_per_usd`: string decimal, el **dólar observado del último día hábil del mes** (o el cierre).
- Formato de test de referencia: `backend/tests/test_tc_correction.py` (`_make_ledger(..., bcch={...})`)
  y `backend/tests/test_admin_fx_bcch.py`.

## Fuente del tipo de cambio — hay que elegir/investigar

**El dato canónico es el "dólar observado" del Banco Central de Chile.** Opciones de fuente:

1. **mindicador.cl** (recomendado para arrancar): API pública gratis, sin auth. Serie histórica del dólar
   observado. Ej: `GET https://mindicador.cl/api/dolar/2026` → valores diarios del año; tomar el último
   de cada mes. Rápido, cero fricción. Verificar términos de uso / que la serie sea "dólar observado".
2. **API oficial BCCh** (SIETE / Base de Datos Estadísticos): autoritativa, pero requiere registrarse y
   credenciales. Serie del dólar observado (código de serie a confirmar). Más robusto a largo plazo.
3. **Descarga manual** (fallback): bajar la serie del dólar observado de la web del BCCh y cargarla una vez.

**Decisión para Ary:** ¿mindicador.cl (rápido, no-oficial) o API BCCh (oficial, con registro)? Empezar con
mindicador para desbloquear ya, y dejar la oficial como hardening es razonable — pero confirmar con Ary.

## Alcance sugerido

1. **Investigar la fuente** y confirmar que la serie es "dólar observado" (no el "dólar acuerdo" ni otro).
2. **Script de importación** (`scripts/` o un endpoint admin — ojo: ya existe infra de fx-bcch, ver
   `backend/tests/test_admin_fx_bcch.py` y buscá el endpoint/servicio de Story 9.10). Idempotente: agrega
   los meses faltantes, no duplica.
3. **Poblar los meses en juego:** al menos **2025-12 → mes actual** (cubre las cartolas 2026 feb–may).
4. **Tests:** parseo de la fuente + escritura del jsonl con el shape correcto.
5. **Verificar el efecto:** con BCCh poblado, re-correr un dry-run de una cartola Santander USD y confirmar
   que el matcher elige el posting por BCCh (no por la banda) y que el `fx_deviation_pct` sale bajo.

## Contexto (una pasada)

Story 9.10 introdujo el concepto de `fx-bcch-eom.jsonl`; puede haber ya un endpoint/servicio para
escribirlo (buscar "fx-bcch" / "admin_fx" en el repo). El matcher FX (commit `8fab632`) ya consume
`lookup_bcch` — solo falta el dato. Diseño relacionado:
`_bmad-output/planning-artifacts/valentina-fix-matcher-fx-consolidado-2026-06-29.md`.
