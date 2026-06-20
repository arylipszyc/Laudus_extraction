# scripts/

Utilidades operativas / QA (corren con el venv del repo, `PYTHONUTF8=1` en Windows).

## `draft_balance_sheet.py` — borrador de balance consolidado para el contador

Genera un BORRADOR de balance consolidado (EAG + hijas) desde Beancount para que el contador
lo revise. Consolidado = todas las entidades (las hijas son egresos de EAG). El saldo se presenta
en su signo natural (Activo deudor +, Pasivo/Patrimonio acreedor +).

```bash
PYTHONUTF8=1 python scripts/draft_balance_sheet.py [YYYY-MM-DD]
```

Fecha de corte por defecto: `2026-05-31`. Salida: `_handoff/Borrador-Balance-EAG-Consolidado-<fecha>.xlsx`.

---

> **Nota (cleanup c4, 2026-06-20 — Story 9.16):** los scripts de paridad
> `parity_check_sheets_vs_beancount.py` y `parity_check_balance_sheet.py` (+ sus tests) fueron
> **removidos**. Eran andamiaje de la transición Sheets→Beancount: validaban que el reporte y el
> balance-sheet cuadraran contra Sheets antes de flipear los flags `USE_BEANCOUNT_ENGINE_*`. Con el
> cutover cerrado y Sheets retirado, ya no se corren. Quedan en el historial de git.
