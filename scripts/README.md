# scripts/

Utilidades operativas / QA (corren con el venv del repo, `PYTHONUTF8=1` en Windows).

## `parity_check_sheets_vs_beancount.py` — paridad del reporte (Story 9.11)

Compara, por (cuenta, mes), el monto neto del reporte de gastos desde Sheets (`ledger_final`)
vs Beancount (`report_rows_via_beancount`). Diff 0 CLP = seguro flipear `USE_BEANCOUNT_ENGINE_LEDGER`.

```bash
GOOGLE_APPLICATION_CREDENTIALS=/ruta/sa.json GOOGLE_SHEET_ID=... \
LEDGER_PATH=ledger/main.beancount PYTHONUTF8=1 \
python scripts/parity_check_sheets_vs_beancount.py --from 2025-06 --to 2026-06
```

Exit 0 = paridad; 1 = diffs (imprime tabla); 2 = error de carga.

## `parity_check_balance_sheet.py` — paridad del balance-sheet (Story 9.15)

Compara, por (entity, cuenta) **AT un cierre de mes** (point-in-time), la posición neta del
dashboard Activos/Pasivos desde Sheets (`balance_sheet_{entity}`) vs Beancount
(`balance_sheet_via_beancount`). Clasifica los diffs: **TC/pasivo reclasificado a `Liabilities`**
es ESPERADO (modelado correcto, architecture-c4 §2.5); cualquier otro diff → investigar antes de
flipear `USE_BEANCOUNT_ENGINE_BALANCE_SHEET`.

```bash
GOOGLE_APPLICATION_CREDENTIALS=/ruta/sa.json GOOGLE_SHEET_ID=... \
LEDGER_PATH=ledger/main.beancount PYTHONUTF8=1 \
python scripts/parity_check_balance_sheet.py [--as-of 2026-05-31] [--entities EAG,Jocelyn,Jeannette,Johanna,Jael]
```

`--as-of` default = el `query_date` más reciente de la hoja de cada entity (el snapshot vigente).
Se compara AT fin-de-mes, NUNCA sobre un rango multi-snapshot (daría falso diff — ver Dev Notes
de la Story 9.15).

Exit 0 = sólo diffs esperados (seguro flipear); 1 = diffs inesperados (NO flipear); 2 = error de carga.

> El núcleo puro de ambos scripts (agregación/comparación/clasificación) está cubierto por tests
> sin red (`backend/tests/test_parity_check*.py`). La corrida real contra Sheets+Beancount es QA
> con data de producción (creds Sheets + `LEDGER_PATH`).
