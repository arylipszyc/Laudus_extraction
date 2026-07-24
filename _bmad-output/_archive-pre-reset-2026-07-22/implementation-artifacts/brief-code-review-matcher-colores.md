# Brief — Code review adversarial: matcher FX consolidado + Goal B colores

> ✅ **EL REVIEW YA CORRIÓ** — patches aplicados en `8bf60a4` (anotado en code-review 2026-07-06).
> Si se re-corre, hacerlo **contra HEAD** (no `8fab632` aislado, o vas a re-reportar cosas ya
> arregladas). Dos hipótesis de abajo quedaron OBSOLETAS en main: la **#1** (BCCh SÍ está poblado
> desde `0955d1e` y la banda [850,1000] fue removida — sin BCCh el matcher bloquea) y la **#7**
> (el corte verde es **0.85**, commit `b8ed549`, no 0.5).

**Para correr en otra ventana** (sesión limpia). Pegá este brief y pedí un code-review adversarial.
Sugerido: skill `bmad-code-review` o `/code-review high` sobre el commit indicado.

## Qué revisar

**Commit:** `8fab632` (feat(tc): matcher FX para pagos consolidados + recomendación con colores).
Diff: `git show 8fab632` — o el rango `git diff 26aacf4..8fab632`.

**Archivos:**
- `pipeline/importers/tc_correction.py` — núcleo (matcher FX + colores, dos features en un archivo)
- `backend/tests/test_tc_correction.py`, `backend/tests/test_tc_color.py`
- `backend/app/api/v1/transactions/{schemas,service}.py`
- `frontend/src/pages/CategorizacionPage.tsx` (+ `.test.tsx`), `frontend/src/services/categorizacion.ts`

**Diseño (leer para juzgar contra la intención):**
- Matcher: `_bmad-output/planning-artifacts/valentina-fix-matcher-fx-consolidado-2026-06-29.md`
- Reglas FX §12.1 + colores §10.2: `_bmad-output/planning-artifacts/valentina-correccion-tc-cartolas-2026-06-20.md`
- Contexto y evidencia: `_bmad-output/planning-artifacts/valentina-veredicto-desglose-tc-14cartolas-2026-06-29.md`

## Contexto (una pasada)

Los pagos de tarjetas Santander en Laudus son **consolidados**: un asiento paga varias tarjetas y
monedas juntas, y la glosa nombra solo una. El matcher (`derive_statement_fx` / `_resolve_usd_lump`)
antes matcheaba por glosa-USD y bloqueaba las consolidadas. El fix: si la glosa falla, cae a **match por
monto** `CLP-a-la-cuenta / closing`, gateado por **BCCh-si-existe** (tolerancia 5%) **o banda de
plausibilidad [850,1000]** si no hay BCCh. Regla de oro §12.1: el FX siempre es CLP-real/USD (nunca una
tasa estimada); BCCh/banda solo SELECCIONAN el posting. Goal B expone confianza+fuente del categorizador
como color advisory (verde/amarillo/rojo), el contador confirma SIEMPRE.

Validado en un dry-run de 16 cartolas reales: 15/16 corrected, bean-check OK, FX cross-card consistente
(feb~931, mar~902, abr~899). 616 backend tests + frontend tsc/64 verdes.

## Hipótesis de fallo a cazar (adversarial)

**Matcher FX:**
1. **Banda hardcoded [850,1000] en prod.** BCCh NO está poblado (`ledger/_meta/fx-bcch-eom.jsonl` no
   existe) → en prod SIEMPRE se usa la banda. ¿Es seguro? ¿Qué pasa el día que el dólar salga de 850-1000?
2. **Ambigüedad de `_select_by_amount`.** Si dos postings a la misma cuenta caen en la banda/tolerancia
   dentro de la ventana, ¿cuál elige? ¿Puede atar el pago del mes equivocado? ¿El desempate por fecha es
   correcto?
3. **Rompe el path de BCI limpio.** Verificá que la glosa-first sigue ganando y el FX exacto de BCI no
   cambió (test (e)). ¿El nuevo kwarg `bcch` se pasa bien en todos los llamados?
4. **§12.1 cuadre exacto.** ¿El FseleccionadoX = le.amount/USD preserva `Σ(compras×fx)=lump`? ¿Hay algún
   camino donde BCCh/banda se filtre como la tasa en vez de solo seleccionar?
5. **`_resolve_usd_lump` (asiento b).** Mismo fallback — ¿matchea el lump correcto para el MONTO
   CANCELADO cross-período? ¿Signos, `abs()`, candidatos negativos?
6. **Sin candidato → blocked.** ¿Bloquea limpio (Master USD marzo revolving) sin falso-positivo?

**Goal B colores:**
7. **`color_for` mapping.** ¿El corte de confianza (≥0.5 verde, >0 amarillo, 0 rojo) y las fuentes
   (`historical-30+`→verde, `pending`/`gemini`→rojo) matchean §10.2? ¿Algún caso cae en el color equivocado?
8. **`category_status` nunca `confirmed`.** Verificá que NADA se auto-confirma (solo suggested/pending).
9. **Compat `str` vs `CategorizationResult`.** El builder acepta ambos; ¿el path legacy (str) sigue
   andando sin meta de color? ¿El Noop→confidence=0→rojo es correcto?
10. **Cambio en `transactions/service.py` + `schemas.py`.** Se expuso `current_color`/`current_confidence`
    en `PendingTx`. ¿Rompe algún consumidor? ¿El response_model los filtra?
11. **Frontend.** ¿El sort "rojos arriba" es estable? ¿El fallback a rojo cuando falta color? ¿a11y del badge?

**Integración:**
12. Los dos features tocan `tc_correction.py` y se mergearon a mano. ¿Quedó algo inconsistente entre el
    asiento (a) de colores y la sección FX del matcher?

## Entregable

Findings clasificados (bug real / mejora / nit / falso-positivo), con severidad y ubicación. Foco en
correctitud contable (el FX y el cuadre) por sobre estilo. Si algo amerita patch, proponelo.
