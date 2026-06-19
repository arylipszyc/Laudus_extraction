# Categorización (Story 9.7)

Pipeline de categorización con feedback loop, empotrado en el import de cartolas (reemplaza al
`NoopCategoryPredictor` de 9.6a). Auto-asigna la cuenta de gasto de cada transacción y decide la
flag Beancount (`*` confirmada vs `!` pendiente de revisión) para que el contador solo revise lo
que el motor no está seguro.

## Pipeline de 5 stages (`service.py`)

| # | Stage | Condición | match_source | flag |
|---|---|---|---|---|
| 1 | **Regla supra** | ≥30 correcciones a la misma categoría para esa `description_normalized` — gana siempre | `historical-30+` | `*` |
| 2 | **smart_importer** *(seam)* | confianza ≥ 0.85 → `*`; < 0.85 → `!` | `smart_importer` | `*`/`!` |
| 3 | **historical** | 1-29 correcciones consistentes | `historical` | `!` |
| 4 | **Gemini** *(seam)* | devuelve una cuenta de la lista cerrada de Expenses | `gemini` | `!` |
| 5 | **Suspense** | nada matchea | `pending` | `!` |

**Seams (decisión Ary 2026-06-17):** `smart_importer` (stage 2) y `Gemini` (stage 4) se inyectan
como adapters opcionales (`SmartImporterAdapter` / `GeminiCategorizer`). Sin adapter, el stage se
saltea. Esto evitó: agregar la dependencia ML `smart_importer` al deploy de Render (su API estaba
sin verificar) y nuevas llamadas Gemini pagas, dentro de una corrida autónoma. La lista `allowed`
de Gemini son las cuentas `Expenses` de `accounts.beancount` (NO Supabase — deprecado en 9.11/9.14).

## Componentes

- `normalizer.py` — `normalize(description)`: key estable (uppercase + strip + quita puntuación +
  colapsa espacios + quita sufijo numérico largo + prefijo "REF "). Agrupa descripciones equivalentes.
- `history.py` — `CategorizationHistory` sobre `ledger/_meta/categorization-history.jsonl` (append-only):
  `count_for`, `dominant_category`. Alimenta los stages 1 y 3.
- `service.py` — `CategorizationService` (pipeline + cache LRU + `invalidate`). `.predict()` adapta al
  predictor de 9.6a (`(category, match_source, flag)`).

## Feedback loop (backend `transactions/` + `categorization/`)

- `GET /api/v1/categorization/pending` — tx con `category_status ∈ (suggested, pending)`.
- `PATCH /api/v1/transactions/{tx_id}/category` — corrige una tx: re-genera el archivo de cartola
  (flag `!`→`*`, status `confirmed`, nueva cuenta), bean-check, appendea a `categorization-history.jsonl`
  (alimenta la regla supra), commit. `tx_id` = `sha256(file, line, narration, monto)[:12]`.
- `POST /api/v1/transactions/bulk-confirm` — confirma las sugeridas (flag `!` + match_source ≠ pending);
  las `pending` NO se confirman (necesitan corrección manual).

## Wiring del stage 2/4 (cuando se decida)

`SmartImporterAdapter.predict(description, amount, bank_account_id) -> (categoría, confianza) | None`
y `GeminiCategorizer.suggest_category(description, amount, allowed) -> cuenta | None`. Inyectarlos en
el constructor de `CategorizationService` activa los stages sin tocar el resto del pipeline.
