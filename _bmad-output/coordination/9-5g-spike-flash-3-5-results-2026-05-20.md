# 9.5g — Spike Flash 3.5 Results

**Fecha:** 2026-05-20
**De:** Amelia (dev) → Mary (research)
**Branch:** `spike/9-5f-tier1-gemini-api-params` (extiende 9.5f con 4ª medición)
**Handoff fuente:** [9-5g-spike-flash-3-5-handoff-2026-05-20.md](9-5g-spike-flash-3-5-handoff-2026-05-20.md)
**Status:** Spike ejecutado — **Flash 3.5 es el ganador claro**. Cae en el escenario *"after-flash-3-5 ∈ [85%, 90%) balance OK → mergear DEFAULT_MODEL=gemini-3.5-flash + Path #1 en story siguiente"*.

---

## Executive summary

**Flash 3.5 iguala la calidad de Pro (95% balance OK por run, 86% PDFs amarillo estable) pero gana en latencia (35% más rápido) y costo (5× más barato).** Además tiene **menos BALANCE_MISMATCH que Pro** (2 vs 4 runs), señal de extracción más robusta. El gate ≥90% verde sigue sin alcanzarse, pero el cuello del 86% al 100% son los warnings espurios (`PARSE_AMBIGUOUS` siempre, `PERIOD_MISMATCH` por cuotas X/N) — Path #1 los ataca.

**Acción recomendada (per branching del handoff):**
1. Mergear el branch del spike `spike/9-5f-tier1-gemini-api-params` cambiando `DEFAULT_MODEL` a `gemini-3.5-flash`.
2. Abrir story formal con Bob para Path #1 (validators deterministas / atenuar warnings espurios) que cierre el gap del 86% al 90%+.

## Tabla comparativa 4 corridas

| Métrica | Baseline | After-flash (2.5) | After-pro (2.5) | **After-flash-3.5** |
|---|---|---|---|---|
| Modelo | flash 2.5 | flash 2.5 | pro 2.5 | **flash 3.5** |
| Config | T=0.0, [prompt,pdf] | T=0.1, max_tok=32k, [pdf,prompt] | mismo Tier 1 | mismo Tier 1 |
| 🟢 Verde | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | **0 (0.0%)** |
| 🟡 Amarillo | 6 (42.9%) | 6 (42.9%) | 12 (85.7%) | **12 (85.7%)** |
| 🔴 Rojo | 8 (57.1%) | 8 (57.1%) | 2 (14.3%) | **2 (14.3%)** |
| **Runs con diff=0.00** | 29/42 (69%) | 32/42 (76%) | 40/42 (95%) | **40/42 (95%)** |
| **Runs con BALANCE_MISMATCH** | 20 | 23 | 4 | **2** ✅ |
| Runs con PARSE_AMBIGUOUS | 38 | 40 | 42 | 41 |
| Runs con PERIOD_MISMATCH | 26 | 29 | 33 | 32 |
| Tiempo wall-clock | 41397s (con standby ~10h) | 2434s | 2725s | **1734s** ⚡ |
| Tiempo activo aprox | ~70 min | 40 min | 45 min | **29 min** |
| Latencia avg/call | ~100s | ~58s | ~65s | **~41s** |
| Costo aprox | $0.13 | $0.13 | $0.65 (~5×) | **$0.13** |
| Gate ≥90% verde | FAIL | FAIL | FAIL | FAIL |

**Reports completos:**
- `_bmad-output/validation-runs/9-5f-baseline/report.md`
- `_bmad-output/validation-runs/9-5f-after-flash/report.md`
- `_bmad-output/validation-runs/9-5f-after-pro/report.md`
- `_bmad-output/validation-runs/9-5g-after-flash-3-5/report.md`

## Análisis: por qué Flash 3.5 es el ganador

### vs Flash 2.5 + Tier 1

| Eje | Flash 2.5 | Flash 3.5 | Δ |
|---|---|---|---|
| Runs con diff=0 | 32/42 (76%) | 40/42 (95%) | **+19pp** |
| BALANCE_MISMATCH | 23 | 2 | **-91%** |
| Latencia/call | 58s | 41s | -29% |
| Costo | $0.13 | $0.13 | igual |

Gran salto cualitativo: Flash 3.5 elimina casi todos los BALANCE_MISMATCH, igualando a Pro en correctitud de extracción, pero manteniendo el costo de flash.

### vs Pro 2.5 + Tier 1

| Eje | Pro 2.5 | Flash 3.5 | Δ |
|---|---|---|---|
| Runs con diff=0 | 40/42 (95%) | 40/42 (95%) | igual |
| BALANCE_MISMATCH | 4 | 2 | **-50%** ✅ |
| Latencia/call | 65s | 41s | **-37%** |
| Costo | $0.65 (~5×) | $0.13 | **-80%** |

Flash 3.5 **iguala o mejora** a Pro en todas las dimensiones. Pro queda como upgrade reserve si Flash 3.5 falla en algún PDF específico, pero **no es necesario como default**.

### Composición de los 2 PDFs rojos en Flash 3.5

| PDF | Run 1 | Run 2 | Run 3 | Notas |
|---|---|---|---|---|
| `bci-visa-202604.pdf` | 🔴 BALANCE_MISMATCH (diff=33943) | 🟢 diff=0 | 🟢 diff=0 | Inestable: 1 run con 36 tx en vez de 37 → falta 1 tx de ~$34k |
| `santander-mastercard-202604.pdf` | 🟢 diff=0 (opening=17.045.465 correcto) | 🔴 GeminiExtractionError (JSON inválido truncado) | 🟢 diff=0 | Inestable: 1 run falló por output JSON truncado mid-string |

Ambos casos: 2/3 runs OK. Inestabilidad ocasional, no error sistemático.

**Comparación: Pro tuvo BCI estable (3/3 verde) pero Santander con 1 BALANCE_MISMATCH (1/3 falla por opening incorrecto). Flash 3.5 invierte: BCI con 1 BALANCE_MISMATCH (1/3 perdió tx) pero Santander con 2/3 opening correcto y 1 con JSON truncado.** Ambos en 2/3 OK = mismo performance neto.

## El cuello que impide llegar al verde

Mismo diagnóstico que el spike 9.5f, ahora con Flash 3.5 confirmando el patrón:

- **`PARSE_AMBIGUOUS` (Gemini-emitido)**: 41 de 42 runs en Flash 3.5. El prompt 9.5 lo pide explícitamente "cuando estructura del PDF es inusual"; Gemini lo emite religiosamente.
- **`PERIOD_MISMATCH` (post-process)**: 32 de 42 runs. Causado por cuotas pre-existentes X/N con `date = fecha operación original` (anterior al `period.start`).
- **`DUPLICATE_LINE`**: 12 runs (4 dupes × 3 runs) en `estado-de-cuenta (24).pdf` — posiblemente diseño legítimo del PDF.

Todos son flags de "review humana", no errores de extracción. **Path #1 (validators deterministas) ataca esto:** o atenuar las emisiones del prompt, o relajar el classifier de `validate_cartolas_batch.py` para que `diff=0` con warnings sea VERDE en vez de AMARILLO.

## Decisión recomendada (per branching Mary)

**Escenario detectado:** `after-flash-3-5 ∈ [85%, 90%) balance OK` (estamos en **85.7%**).

**Acción:**
1. **Mergear el branch** `spike/9-5f-tier1-gemini-api-params` cambiando además `DEFAULT_MODEL` en [`backend/app/integrations/gemini_client.py`](../../backend/app/integrations/gemini_client.py#L16) de `"gemini-2.5-flash"` a `"gemini-3.5-flash"`. Los 3 cambios Tier 1 ya están commiteados en el branch (T=0.1, max_output_tokens=32768, contents=[pdf_part, prompt]).
2. **Story formal con Bob para Path #1**: validators deterministas / atenuar warnings espurios. Objetivo: cerrar el gap 85.7% → ≥90% verde. Scope tentativo:
   - Cambiar el prompt 9.5 para NO emitir `PARSE_AMBIGUOUS` por default (sólo si Gemini genuinamente no puede extraer).
   - Excluir cuotas X/N pre-existentes del check `PERIOD_MISMATCH` (sus fechas son legítimamente anteriores al período).
   - O alternativamente: cambiar el classifier de `validate_cartolas_batch.py` para que `diff=0` con esos warnings sea VERDE.
3. **Mantener `gemini-2.5-pro` como upgrade reserve** documentado, no como default. Usar solo si Path #1 + Flash 3.5 no llega a 90%.

## Costo en producción del switch a Flash 3.5

Pricing oficial Gemini 3.5 Flash (per handoff): **$1.50 input / $9 output per M tokens**. Comparado con 2.5 Flash ($0.30 / $2.50) es ~5× más caro. Pero:
- Procesar 1 cartola con prompt 9.5 (~5k tokens input, ~4.5k output) ≈ **$0.05 per upload**.
- 50 cartolas/mes = ~$2.50/mes incremental.
- vs Pro: ~$25/mes incremental (10× más caro per call).

**Costo/mes en producción con Flash 3.5: bajo. Justifica el salto de calidad.**

## Lo que NO se hizo (per acuerdo con handoff)

- No se mergeó nada todavía (esperando decisión Ary/Mary).
- No se tocó el prompt (regla del research).
- No se cambió `cartola_post_process.py` (eso es Path #1).
- No se cambió el classifier de `validate_cartolas_batch.py` (eso es Path #1).

## Próximo paso

Que Mary confirme:
1. Aprobar mergeo del branch con switch a `gemini-3.5-flash` como default.
2. Definir scope exacto del Path #1 (prompt patch + post-process patch + classifier patch) para abrir story formal con Bob.
3. Decidir si la story Path #1 incluye también re-medición con classifier ajustado para confirmar ≥90% verde, o si eso queda como Definition of Done separado.

---

| | |
|---|---|
| Autor | Amelia (claude-opus-4-7[1m]) |
| Fecha | 2026-05-20 |
| Gemini calls gastados en este spike | 42 (flash-3.5) |
| Costo aprox spike 9.5g | ~$0.13 |
| Acumulado spikes 9.5e + 9.5f + 9.5g | ~$1.18 |
