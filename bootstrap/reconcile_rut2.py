"""Reconciliación peso-por-peso del libro RUT2 (Fondo Común FFCC/JAB) vs Laudus.

Story 12.5 — DoD del Epic 12. Hermano de `validate_cuadratura.py`, pero:
  - Fetch con `login(get_book("RUT2"))` + `verify_book_identity` (libro RUT2,
    NO EAG) → `balanceSheet/totals?dateTo=<corte>`.
  - Scoping por ENTIDAD (2º segmento del path ∈ {FFCC, JAB}), NO por code:
    los `load_account_index` globales indexan el archivo completo por code
    desnudo last-wins (defer 12-2) → contaminarían con cuentas EAG. La fuente
    de verdad para aislar el libro es el 2º segmento del path.

Es una verificación read-only: NO escribe asientos al ledger; produce un CSV
de discrepancias por corte y un exit code (0 = cuadra al peso, 2 = hay diffs).

Uso:
    python -m bootstrap.reconcile_rut2 --cutoff 2026-06-30
"""
from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from beancount import loader
from beancount.core.data import Open
from beanquery.query import run_query

from bootstrap.account_mapping import normalize_account_number
from bootstrap.generate_opening_balances import signed_balance
from pipeline.config.laudus_config import BALANCE_SHEET_URL, get_book
from pipeline.services.laudus_service import get_info_API, verify_book_identity

logger = logging.getLogger(__name__)

RUT2_BOOK_ID = "RUT2"

# Corte primario = último fin de mes COMPLETO (el libro está vivo hasta 2026-07-10,
# así que julio está a medias y no sirve de ancla). Los cierres anuales YYYY-12-31
# se evitan por el asiento de cierre/apertura de Laudus (TRAP #2, ver Dev Notes 12.5).
DEFAULT_CUTOFF = "2026-06-30"


def _rut2_account_pattern() -> str:
    """Regex case-sensitive de las cuentas del libro RUT2: 2º segmento ∈ entidades.

    `(?-i:)` es obligatorio (beanquery `~` es IGNORECASE): sin él una cuenta
    case-variante de EAG podría filtrarse (misma razón que 11.1)."""
    members = "|".join(sorted(get_book(RUT2_BOOK_ID).entities))
    return f"(?-i:^(Assets|Liabilities|Equity|Income|Expenses):({members}):)"


def fetch_laudus_rut2_balance_sheet(date_to: str) -> list[dict[str, Any]]:
    """Balance sheet de Laudus del LIBRO RUT2 al `date_to`.

    `verify_book_identity` assert-a "ACTIVO FFCC" ANTES de leer (no vaya a ser
    que el companyVATId apunte a otro libro). El fetch usa `book=get_book(RUT2)`
    → token y companyVATId del libro RUT2, NO EAG.
    """
    book = get_book(RUT2_BOOK_ID)
    verify_book_identity(book)
    rows = get_info_API(BALANCE_SHEET_URL, {"dateTo": date_to}, book=book)
    if rows is None:
        raise RuntimeError(
            f"Laudus balanceSheet/totals (libro {RUT2_BOOK_ID}, {date_to}) devolvió None"
        )
    if not isinstance(rows, list):
        raise RuntimeError(
            f"Laudus balanceSheet/totals devolvió {type(rows).__name__}, esperaba lista"
        )
    logger.info("Laudus balanceSheet/totals RUT2 %s: %d cuentas", date_to, len(rows))
    return rows


def load_rut2_account_index(accounts_beancount: Path) -> dict[str, str]:
    """Índice `code_normalizado → path`, SCOPEADO al libro RUT2 (entidad FFCC/JAB).

    NO reusa `generate_opening_balances.load_account_index` ni
    `validate_cuadratura.load_account_index_with_padded_codes`: esos indexan el
    archivo COMPLETO por code last-wins (defer 12-2) — para RUT2 aciertan por
    casualidad, pero el índice sigue conteniendo cuentas EAG. El scoping por
    entidad es la fuente de verdad (TRAP #1).

    El code se normaliza a 6 dígitos en AMBOS lados (acá y en el fetch Laudus)
    para que la hoja "13" (verbatim, no-padded — TRAP #3) matchee simétrica si
    llegara a aparecer con saldo (hoy 0 movimientos).
    """
    entries, errors, _ = loader.load_file(str(accounts_beancount))
    if errors:
        raise RuntimeError(f"Errores al cargar {accounts_beancount}: {errors}")
    rx = re.compile(_rut2_account_pattern())
    index: dict[str, str] = {}
    for entry in entries:
        if isinstance(entry, Open) and rx.search(entry.account):
            code = entry.meta.get("code")
            if code:
                key = normalize_account_number(str(code))
                if key in index:
                    # Last-wins silencioso mentiría el gate (una cuenta RUT2
                    # quedaría sin matchear → beancount_only fantasma). Falla
                    # ruidoso: hoy 0 colisiones sobre 311 opens FFCC/JAB.
                    raise RuntimeError(
                        f"Code normalizado duplicado en el árbol RUT2: {key!r} "
                        f"→ {index[key]!r} y {entry.account!r}"
                    )
                index[key] = entry.account
    return index


def _extract_clp_amount(inventory: Any) -> float:
    """Extrae el monto CLP de un Inventory de beanquery. 0 si no hay CLP."""
    if inventory is None:
        return 0.0
    for pos in inventory:
        if pos.units.currency == "CLP":
            return float(pos.units.number)
    return 0.0


def fetch_beancount_rut2_balances(ledger_path: Path, date_to: str) -> dict[str, float]:
    """Saldos por cuenta en Beancount al `date_to`, SCOPEADOS al libro RUT2.

    Returns: dict path → saldo signed CLP (positivo Assets/Expenses, negativo
    Liabilities/Income/Equity — convención Beancount nativa).
    """
    main_path = ledger_path / "main.beancount"
    entries, errors, options_map = loader.load_file(str(main_path))
    if errors:
        raise RuntimeError(f"Errores cargando {main_path}: {errors}")
    bql = (
        f'SELECT account, sum(position) AS total '
        f'WHERE account ~ "{_rut2_account_pattern()}" AND date <= {date_to} '
        f'GROUP BY account ORDER BY account'
    )
    _, rows = run_query(entries, options_map, bql)
    balances: dict[str, float] = {}
    for account, inventory in rows:
        amount = _extract_clp_amount(inventory)
        if amount != 0:
            balances[account] = amount
    return balances


def compare(
    laudus_rows: list[dict[str, Any]],
    beancount_balances: dict[str, float],
    account_index: dict[str, str],
) -> list[dict[str, Any]]:
    """Compara Laudus RUT2 vs Beancount RUT2 cuenta-por-cuenta.

    Emite tres clases de discrepancia:
      - `amount_mismatch`: la cuenta existe en ambos pero el saldo difiere.
      - `account_not_in_rut2_tree`: Laudus reporta un saldo ≠ 0 para un code que
        no está en el árbol RUT2 → señal de ruteo/plan roto (NO "explicación
        aceptada"). Se ignora si el saldo es 0 (filas rollup/inactivas).
      - `beancount_only`: una cuenta RUT2 tiene saldo en el ledger que Laudus no
        reporta (p.ej. un plug de Equity que no existe en Laudus).
    """
    diffs: list[dict[str, Any]] = []
    matched_paths: set[str] = set()
    for row in laudus_rows:
        padded = normalize_account_number(str(row["accountNumber"]))
        laudus_amount = signed_balance(row)
        path = account_index.get(padded)
        if path is None:
            if laudus_amount != 0:
                diffs.append({
                    "account_number": padded,
                    "path": "(not in RUT2 tree)",
                    "laudus_clp": laudus_amount,
                    "beancount_clp": 0.0,
                    "diff": laudus_amount,
                    "reason": "account_not_in_rut2_tree",
                })
            continue
        matched_paths.add(path)
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
    # Cuentas RUT2 con saldo en Beancount que Laudus no reportó.
    path_to_code = {v: k for k, v in account_index.items()}
    for path, amount in sorted(beancount_balances.items()):
        if path not in matched_paths and amount != 0:
            diffs.append({
                "account_number": path_to_code.get(path, ""),
                "path": path,
                "laudus_clp": 0.0,
                "beancount_clp": amount,
                "diff": -amount,
                "reason": "beancount_only",
            })
    return diffs


def write_reconciliation_report(
    cutoff: str, diffs: list[dict[str, Any]], reports_path: Path,
) -> Path:
    out = reports_path / f"report-reconciliacion-rut2-{cutoff}.csv"
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


def reconcile_cutoff(
    *,
    ledger_path: Path,
    reports_path: Path,
    cutoff: str,
    laudus_rows: Optional[list[dict[str, Any]]] = None,
) -> tuple[int, int, Path]:
    """Reconcilia un corte. Retorna (n_diffs, n_cuentas_reconciliadas, report_path)."""
    rows = laudus_rows if laudus_rows is not None else fetch_laudus_rut2_balance_sheet(cutoff)
    account_index = load_rut2_account_index(ledger_path / "accounts.beancount")
    bc_balances = fetch_beancount_rut2_balances(ledger_path, cutoff)
    diffs = compare(rows, bc_balances, account_index)
    report = write_reconciliation_report(cutoff, diffs, reports_path)
    n_accounts = len(bc_balances)  # cuentas RUT2 con saldo ≠ 0 en el ledger
    return len(diffs), n_accounts, report


def run_reconciliation(
    *,
    ledger_path: Path,
    reports_path: Path,
    cutoffs: list[str],
) -> int:
    """Orquesta la reconciliación de todos los cortes. 0 OK, 2 si hay diffs."""
    total_diffs = 0
    for cutoff in cutoffs:
        n, n_accounts, report = reconcile_cutoff(
            ledger_path=ledger_path, reports_path=reports_path, cutoff=cutoff,
        )
        marker = "OK" if n == 0 else "FAIL"
        print(f"[{marker}] Reconciliación RUT2 {cutoff}: {n} diferencias "
              f"sobre {n_accounts} cuentas con saldo  ->  {report}")
        total_diffs += n
    if total_diffs == 0:
        print("\n[OK] RUT2 cuadra peso-por-peso con Laudus en todos los cortes.")
        return 0
    print(f"\n[FAIL] {total_diffs} diferencias totales — revisar reportes en {reports_path}/")
    return 2


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-path", type=Path, default=Path("ledger"))
    parser.add_argument("--reports-path", type=Path, default=Path("bootstrap"))
    parser.add_argument(
        "--cutoff", action="append", help="Corte a reconciliar (repetible)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cutoffs = args.cutoff or [DEFAULT_CUTOFF]
    for c in cutoffs:
        # Un corte mal formado (`2026-6-30`) se interpola crudo en el BQL como
        # aritmética (`date <= 1990`) → hoja de mismatches falsos. beanquery exige
        # `\d{4}-\d{2}-\d{2}` exacto: el regex descarta el 1-dígito (strptime lo
        # aceptaría) y strptime valida que sea una fecha real.
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", c):
            parser.error(f"--cutoff invalido: {c!r} (formato esperado YYYY-MM-DD)")
        try:
            datetime.strptime(c, "%Y-%m-%d")
        except ValueError:
            parser.error(f"--cutoff invalido: {c!r} (no es una fecha valida)")
    return run_reconciliation(
        ledger_path=args.ledger_path, reports_path=args.reports_path, cutoffs=cutoffs,
    )


if __name__ == "__main__":
    sys.exit(_cli())
