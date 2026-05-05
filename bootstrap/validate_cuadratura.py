"""Cuadratura CLP↔CLP: Beancount vs Laudus balance sheet — Story 9.1 Task 6.

Compara el saldo de cada cuenta en Beancount (vía `beanquery`) contra el
saldo Laudus en una fecha de corte. Diferencia esperada = exacto 0 CLP por
construcción (pre-2026 todo CLP, sin lógica multi-currency).

Estado actual (2026-05-05):
    - Sólo el corte **2021-01-01 post-opening** se valida en este momento.
      Los demás cortes (cierres anuales 2021-2025, 2026-04-30) requieren
      que Story 9.4 (importer Laudus producción) esté done y el bootstrap
      haya cargado las JEs históricas a `imports/laudus/YYYY-MM.beancount`.
    - Los cortes adicionales se agregan a `CUTOFF_DATES` cuando 9.4 cierre.

Uso:
    python -m bootstrap.validate_cuadratura [--ledger-path PATH] [--reports-path PATH]
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path
from typing import Any, Optional

from beancount import loader
from beanquery.query import run_query

from bootstrap.account_mapping import normalize_account_number
from bootstrap.generate_opening_balances import (
    fetch_opening_balances,
    signed_balance,
)

logger = logging.getLogger(__name__)

# Cortes a validar. Pre-9.4: solo 2021-01-01. Post-9.4: agregar cierres anuales.
CUTOFF_DATES = ["2021-01-01"]


def fetch_laudus_balance_sheet(date_to: str) -> list[dict[str, Any]]:
    """Wrapper genérico — `fetch_opening_balances` ya hace lo mismo pero el
    nombre no comunica que sirve para cualquier fecha. Alias semántico."""
    return fetch_opening_balances(opening_date=date_to)


def fetch_beancount_balances(ledger_path: Path, date_to: str) -> dict[str, float]:
    """Saldos por cuenta en Beancount al inicio de `date_to`.

    Returns:
        Dict account_path → saldo signed CLP (positivo Assets, negativo
        Liabilities — convención Beancount nativa).
    """
    main_path = ledger_path / "main.beancount"
    entries, errors, options_map = loader.load_file(str(main_path))
    if errors:
        raise RuntimeError(f"Errores cargando {main_path}: {errors}")
    bql = (
        f"SELECT account, sum(position) AS total "
        f"WHERE date <= {date_to} "
        f"GROUP BY account ORDER BY account"
    )
    _, rows = run_query(entries, options_map, bql)
    # beanquery retorna tuples (account, inventory). Indexamos posicional.
    balances: dict[str, float] = {}
    for account, inventory in rows:
        amount = _extract_clp_amount(inventory)
        if amount != 0:
            balances[account] = amount
    return balances


def _extract_clp_amount(inventory: Any) -> float:
    """Extrae el monto CLP de un Inventory de beanquery. 0 si no hay CLP."""
    if inventory is None:
        return 0.0
    for pos in inventory:
        if pos.units.currency == "CLP":
            return float(pos.units.number)
    return 0.0


def load_account_index_with_padded_codes(ledger_path: Path) -> dict[str, str]:
    """account_number padded → full Beancount path."""
    from bootstrap.generate_opening_balances import load_account_index
    return load_account_index(ledger_path / "accounts.beancount")


def compare(
    laudus_rows: list[dict[str, Any]],
    beancount_balances: dict[str, float],
    account_index: dict[str, str],
) -> list[dict[str, Any]]:
    """Compara saldos Laudus vs Beancount cuenta-por-cuenta.

    Returns:
        Lista de discrepancias con diff != 0. Cada entrada incluye
        account_number, path, laudus_clp, beancount_clp, diff.
    """
    diffs: list[dict[str, Any]] = []
    for row in laudus_rows:
        padded = normalize_account_number(row["accountNumber"])
        path = account_index.get(padded)
        laudus_amount = signed_balance(row)
        if path is None:
            diffs.append({
                "account_number": padded,
                "path": "(not opened)",
                "laudus_clp": laudus_amount,
                "beancount_clp": 0.0,
                "diff": laudus_amount,
                "reason": "account_not_in_beancount",
            })
            continue
        beancount_amount = beancount_balances.get(path, 0.0)
        diff = laudus_amount - beancount_amount
        if diff != 0:
            diffs.append({
                "account_number": padded,
                "path": path,
                "laudus_clp": laudus_amount,
                "beancount_clp": beancount_amount,
                "diff": diff,
                "reason": "amount_mismatch",
            })
    return diffs


def write_cuadratura_report(
    cutoff: str, diffs: list[dict[str, Any]], reports_path: Path,
) -> Path:
    out = reports_path / f"report-cuadratura-{cutoff}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(
            fp, fieldnames=["account_number", "path", "laudus_clp",
                            "beancount_clp", "diff", "reason"],
        )
        writer.writeheader()
        for d in diffs:
            writer.writerow(d)
    return out


def validate_cutoff(
    *,
    ledger_path: Path,
    reports_path: Path,
    cutoff: str,
    laudus_rows: Optional[list[dict[str, Any]]] = None,
) -> tuple[int, Path]:
    """Valida cuadratura para un corte. Retorna (n_diffs, report_path)."""
    rows = laudus_rows if laudus_rows is not None else fetch_laudus_balance_sheet(cutoff)
    account_index = load_account_index_with_padded_codes(ledger_path)
    bc_balances = fetch_beancount_balances(ledger_path, cutoff)
    diffs = compare(rows, bc_balances, account_index)
    report = write_cuadratura_report(cutoff, diffs, reports_path)
    return len(diffs), report


def run_validation(
    *,
    ledger_path: Path,
    reports_path: Path,
    cutoffs: list[str] = CUTOFF_DATES,
) -> int:
    """Orquesta validación de todos los cortes. Returns 0 OK, 2 si hay diffs."""
    total_diffs = 0
    for cutoff in cutoffs:
        n, report = validate_cutoff(
            ledger_path=ledger_path, reports_path=reports_path, cutoff=cutoff,
        )
        marker = "OK" if n == 0 else "FAIL"
        print(f"[{marker}] Cuadratura {cutoff}: {n} diferencias  ->  {report}")
        total_diffs += n
    if total_diffs == 0:
        print(f"\n[OK] Todos los cortes cuadran exacto en CLP.")
        return 0
    print(f"\n[FAIL] {total_diffs} diferencias totales — revisar reportes en {reports_path}/")
    return 2


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-path", type=Path, default=Path("ledger"))
    parser.add_argument("--reports-path", type=Path, default=Path("bootstrap"))
    parser.add_argument(
        "--cutoff", action="append", help="Override: corte específico a validar (repetible)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cutoffs = args.cutoff or CUTOFF_DATES
    return run_validation(
        ledger_path=args.ledger_path, reports_path=args.reports_path, cutoffs=cutoffs,
    )


if __name__ == "__main__":
    sys.exit(_cli())
