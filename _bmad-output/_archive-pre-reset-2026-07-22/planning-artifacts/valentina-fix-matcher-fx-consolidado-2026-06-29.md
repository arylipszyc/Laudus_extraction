# Diseño contable — FX matcher para pagos consolidados (tarjetas Santander)

- **Fecha:** 2026-06-29
- **Autora:** Valentina (asesora financiera LAUDUS)
- **Tipo:** diseño contable → input para story de dev (quick-dev). Cierra el bloqueo de las TC USD Santander.
- **Origen:** validación del desglose vs 14 cartolas reales (`valentina-veredicto-desglose-tc-14cartolas-2026-06-29.md`).
- **Fuente de verdad del FX:** §12.1 del doc `valentina-correccion-tc-cartolas-2026-06-20.md` (NO cambia la regla; la extiende).

## Problema (verificado con datos reales)

La derivación del FX de un estado USD (`derive_statement_fx`, `pipeline/importers/tc_correction.py`)
matchea el pago que salda el estado **parseando la glosa** del asiento Laudus en busca de `USD == closing`
(`parse_glosa_usd`). Funciona para BCI (Visa Infinity 1027): paga **un asiento por tarjeta-moneda-estado**
con el USD en la glosa → los 3 meses cuadraron (FX 931/902/899).

**Falla para las tarjetas Santander (Mastercard 8996, Latanpass 0858).** Santander paga con asientos
**consolidados**: UN asiento "Visa Santander 0858" paga 4 cuentas TC a la vez (Master CLP+USD, Latanpass
CLP+USD) desde la cta cte Santander. La glosa nombra UNA tarjeta y UN USD aunque paga varias → el parseo
de glosa no encuentra el `USD == closing` y **bloquea** (3 de 14 estados en el dry-run).

**Clave:** el monto CLP que entró a la cuenta de **cada** tarjeta SÍ está bien posteado, y da un FX sano:

| Estado bloqueado | Posting Laudus a su cuenta TC | FX = CLP / closing |
|---|---|---|
| Mastercard 8996 USD feb (1.387,63 USD) | 2026-03-06 → 1.291.675 CLP | **930,8 ✅** |
| Latanpass 0858 USD feb (3.217,07 USD) | 2026-03-06 → 3.000.722 CLP | **932,7 ✅** |
| Mastercard 8996 USD mar (2.234,84 USD) | ningún posting da FX sano | 578 / 664 / 22.955 ✗ → sigue bloqueado (correcto) |

El dato YA está cargado: `load_laudus_entries(laudus_dir, expense_tc, …)` devuelve `LaudusEntry.amount` =
el CLP del posting a esa cuenta-gasto. Hoy solo se usa `.description` (glosa); el `.amount` es lo que falta.

## Fix (diseño)

**Augmentar `derive_statement_fx` con un fallback por monto**, gateado por BCCh:

1. **Path actual primero (NO tocar el de BCI):** buscar el pago cuya glosa codifica `USD == closing`.
   Si matchea → FX exacto como hoy. Es el camino limpio y preferido.
2. **Fallback (glosa no matchea):** entre los `LaudusEntry` a la cuenta-gasto fechados tras el cierre y
   dentro de la ventana (`_FX_WINDOW_DAYS`), calcular `fx_candidato = le.amount / total_usd` para cada uno,
   y **elegir el que cae dentro de la tolerancia BCCh** del mes (reusar `fx_calculator.calculate_fx` /
   `lookup_bcch`, Story 9.10). Si hay más de uno en tolerancia, preferir el de **fecha más cercana** al
   cierre+ciclo. Si **ninguno** cae en tolerancia → **bloqueante** (como hoy, correcto: ej. Master USD mar).
3. El chequeo BCCh post-hoc que ya existe en `correct_tc_cartola` valida el resultado (queda redundante con
   la selección, pero es la red de seguridad).

**Mismo tratamiento para el asiento (b)** (`_resolve_usd_lump`, el `MONTO CANCELADO` que salda el estado
ANTERIOR): hoy también matchea por glosa USD. Para consolidados, caer al posting a la cuenta-gasto del
mes correspondiente, mismo gate BCCh. (Latanpass feb bloqueó por ESTO, no por el FX.) **Decisión Ary:**
¿en la misma story o fase 2? Recomiendo misma story — el bloqueo se levanta solo si ambos lados matchean.

## Decisiones / reglas de oro (mías)

- **NO romper el cuadre exacto §12.1.** El fallback usa el **CLP real** posteado (no una tasa BCCh
  estimada) → `Σ(compras × FX) = lump` sigue valiendo. BCCh es solo el **filtro** que elige/valida el
  posting correcto, NUNCA la tasa. (Esto es distinto de "FX por BCCh", que SÍ rompería el cuadre — descartado.)
- **Sin BCCh ese mes → no se puede filtrar → bloquear** (no adivinar cuál posting). Falla segura.
- **Ambigüedad residual:** si dos postings a la misma cuenta caen en tolerancia BCCh dentro de la ventana,
  se elige por fecha; documentar como limitación (baja prob: requiere 2 pagos del mismo monto-orden).
- **Tolerancia BCCh:** la misma que usa hoy el sanity check (±, ver `calculate_fx`). No inventar otra.

## Criterio de éxito (verificable — mismo sandbox del dry-run)

Re-correr las 14 cartolas reales:
1. **Mastercard 8996 USD feb** → `corrected`, FX ≈ **931** (antes: blocked).
2. **Latanpass 0858 USD feb** → `corrected`, FX ≈ **933** (antes: blocked, por el MONTO CANCELADO).
3. **Mastercard 8996 USD mar** → sigue `blocked` (ningún posting en tolerancia BCCh — correcto hasta
   aclarar el lump de 51,3M).
4. **BCI 1027 USD (feb/mar/abr)** → sin cambios (FX 931/902/899; el path de glosa sigue ganando).
5. Suite backend verde, 0 regresiones (los tests USD de `test_tc_correction.py` cubren el path de glosa;
   agregar casos del fallback por monto + BCCh).

## Fuera de scope

- El lump de **51,3M CLP a la cuenta MasterUs (2026-05-06)** = anomalía de dato, la revisa Ary con la
  cartola Mastercard USD de abril. NO es de esta story.
- Limpiar/cambiar cómo Santander postea (no se puede; el fix vive en el matcher, no en Laudus).
- Goal B (colores) sigue diferido.

## Handoff a dev

- Núcleo: `pipeline/importers/tc_correction.py` → `derive_statement_fx` (fallback por monto + gate BCCh)
  y `_resolve_usd_lump` (mismo patrón para el asiento b). El dato (`LaudusEntry.amount`) ya viene cargado.
- Reusar: `fx_calculator.calculate_fx` / `lookup_bcch` (ya importados en `correct_tc_cartola`).
- Tests: `backend/tests/test_tc_correction.py` (fixtures USD + BCCh ya existen; agregar un asiento Laudus
  consolidado multi-cuenta y verificar la selección por tolerancia BCCh).
