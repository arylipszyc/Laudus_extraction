"""Parity check Sheets `ledger_final` vs ledger Beancount — Story 9.11 AC1.

Compara, por (cuenta, mes), el monto neto que el reporte usaría desde cada fuente:
- Sheets: `repo.get_records("ledger_final")` (path legacy, source of truth hasta ahora).
- Beancount: `report_rows_via_beancount(ledger, ...)` (lo que el reporte leerá con el flag on).

Usa la MISMA lógica de signo/agregación que `report_builder` (reusa sus helpers), así
que un diff = 0 CLP en todos los (cuenta, mes) garantiza que flipear
`USE_BEANCOUNT_ENGINE_LEDGER` no mueve ningún número del reporte. Threshold: 0 CLP
(Q10: cuadre 1:1, no porcentaje).

Uso:
    GOOGLE_APPLICATION_CREDENTIALS=/ruta/sa.json GOOGLE_SHEET_ID=... \\
    LEDGER_PATH=ledger/main.beancount PYTHONUTF8=1 \\
    python scripts/parity_check_sheets_vs_beancount.py --from 2025-06 --to 2026-06

Exit 0 = paridad (0 diffs); 1 = hay diffs (imprime tabla); 2 = error de carga.
"""
from __future__ import annotations

import argparse
import calendar
import os
import sys
from collections import defaultdict

# Reusa EXACTAMENTE la lógica de signo/fecha del reporte para que la paridad sea fiel.
from backend.app.api.v1.reportes.report_builder import _income_accounts, _num, _row_ym


def _ym_str(ym: tuple[int, int]) -> str:
    return f"{ym[0]:04d}-{ym[1]:02d}"


def aggregate(rows: list[dict], ym_from: str | None = None, ym_to: str | None = None) -> dict:
    """{(accountnumber, 'YYYY-MM'): monto_neto} con la convención del reporte.

    monto = (credito - debito) para cuentas de INGRESOS (Categoria1 contiene "INGRESOS"),
    (debito - credito) para el resto. Filas con fecha no parseable se saltean (igual que
    el reporte). `ym_from`/`ym_to` ('YYYY-MM', inclusive) acotan los meses considerados.
    """
    income = _income_accounts(rows)
    agg: dict = defaultdict(float)
    for r in rows:
        ym = _row_ym(r)
        if ym is None:
            continue
        yms = _ym_str(ym)
        if (ym_from and yms < ym_from) or (ym_to and yms > ym_to):
            continue
        acc = str(r.get("accountnumber", ""))
        de, cr = _num(r.get("debit")), _num(r.get("credit"))
        agg[(acc, yms)] += (cr - de) if acc in income else (de - cr)
    return agg


def compare(sheets: dict, beancount: dict, tol: float = 0.5) -> list[dict]:
    """Diffs por (cuenta, mes) donde |beancount - sheets| > tol (≈ 0 CLP, redondeo).

    Devuelve lista ordenada por |diff| desc: {account, month, sheets, beancount, diff}.
    """
    out = []
    for key in set(sheets) | set(beancount):
        s, b = sheets.get(key, 0.0), beancount.get(key, 0.0)
        if abs(b - s) > tol:
            out.append({"account": key[0], "month": key[1],
                        "sheets": round(s), "beancount": round(b), "diff": round(b - s)})
    out.sort(key=lambda d: abs(d["diff"]), reverse=True)
    return out


def _print_report(diffs: list[dict], n_keys: int) -> None:
    print(f"\nParidad Sheets vs Beancount — {n_keys} (cuenta, mes) comparados")
    if not diffs:
        print("✅ 0 diferencias. Paridad 1:1 confirmada — seguro flipear el flag.")
        return
    total = sum(abs(d["diff"]) for d in diffs)
    print(f"❌ {len(diffs)} (cuenta, mes) con diferencia. |Σ diff| = {total:,} CLP\n")
    print(f"{'cuenta':<12} {'mes':<8} {'sheets':>15} {'beancount':>15} {'diff':>15}")
    print("-" * 70)
    for d in diffs[:50]:
        print(f"{d['account']:<12} {d['month']:<8} {d['sheets']:>15,} {d['beancount']:>15,} {d['diff']:>15,}")
    if len(diffs) > 50:
        print(f"... (+{len(diffs) - 50} más)")


def _load_rows(ym_from: str, ym_to: str):
    """Carga filas de ambas fuentes. Separado de la lógica pura para testear sin red."""
    from backend.app.dependencies import get_repository
    from backend.app.services.bql_queries import report_rows_via_beancount
    from backend.app.services.ledger_service import LedgerService

    sheets_rows = get_repository().get_records("ledger_final")

    ledger_path = os.getenv("LEDGER_PATH") or "ledger/main.beancount"
    date_from = f"{ym_from}-01"
    last_day = calendar.monthrange(int(ym_to[:4]), int(ym_to[5:7]))[1]
    date_to = f"{ym_to}-{last_day:02d}"
    bean_rows = report_rows_via_beancount(LedgerService(ledger_path), date_from, date_to)
    return sheets_rows, bean_rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="ym_from", required=True, help="mes desde, YYYY-MM")
    ap.add_argument("--to", dest="ym_to", required=True, help="mes hasta, YYYY-MM (inclusive)")
    args = ap.parse_args()

    try:
        sheets_rows, bean_rows = _load_rows(args.ym_from, args.ym_to)
    except Exception as exc:  # noqa: BLE001 — script CLI: reportar y salir
        print(f"Error cargando fuentes: {exc}", file=sys.stderr)
        return 2

    agg_sheets = aggregate(sheets_rows, args.ym_from, args.ym_to)
    agg_bean = aggregate(bean_rows, args.ym_from, args.ym_to)
    diffs = compare(agg_sheets, agg_bean)
    _print_report(diffs, len(set(agg_sheets) | set(agg_bean)))
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
