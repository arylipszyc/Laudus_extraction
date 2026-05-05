"""Genera ledger/opening-2021.beancount con saldos iniciales — Story 9.1 Task 3.

Pipeline:
    1. Lee balance sheet de Laudus al 2021-01-01 (endpoint
       `GET /accounting/balanceSheet/totals?dateTo=2021-01-01`).
    2. Filtra cuentas con saldo ≠ 0 (signed = debitBalance - creditBalance).
    3. Resuelve account_number → Beancount path leyendo accounts.beancount
       (output de Task 2 — la metadata `code:` de cada `open` directive
       lleva el account_number padded a 6).
    4. Cuentas con saldo en Laudus que NO están abiertas en accounts.beancount
       fallan con exit ≠ 0 (mismatch que requiere intervención).
    5. Renderiza:
         2021-01-01 open Equity:EAG:OpeningBalances CLP, USD
         2021-01-01 pad {path} Equity:EAG:OpeningBalances
           source_je: "140"
         2021-01-01 balance {path} {signed_balance} CLP

Pre-2026 todo CLP por decisión Q4 (2026-05-05).

Uso:
    python -m bootstrap.generate_opening_balances [--ledger-path PATH]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Optional

import requests
from beancount import loader
from beancount.core import data as bcdata

from bootstrap.account_mapping import normalize_account_number
from pipeline.services.laudus_service import login

logger = logging.getLogger(__name__)

OPENING_DATE = "2021-01-01"          # fecha del balance check
PAD_DATE = "2020-12-31"              # día anterior — Beancount exige pad < balance
EQUITY_OPENING = "Equity:EAG:OpeningBalances"
SOURCE_JE = "140"
LAUDUS_BALANCE_SHEET_URL = "https://api.laudus.cl/accounting/balanceSheet/totals"


class OpeningBalanceError(RuntimeError):
    """Cuenta con saldo en Laudus que no existe en accounts.beancount."""


def fetch_opening_balances(opening_date: str = OPENING_DATE) -> list[dict[str, Any]]:
    """Trae las cuentas con saldo al `opening_date` desde Laudus.

    Returns:
        Lista de dicts con `accountNumber`, `accountName`, `debit`,
        `credit`, `debitBalance`, `creditBalance`. Vacío si no hay saldos.
    """
    token = login()
    if not token:
        raise RuntimeError("Laudus login devolvió token vacío.")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    response = requests.get(
        LAUDUS_BALANCE_SHEET_URL,
        headers=headers,
        params={"dateTo": opening_date},
        timeout=60,
    )
    if response.status_code == 204:
        return []
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        raise RuntimeError(
            f"Laudus balanceSheet/totals devolvió tipo inesperado: {type(rows).__name__}"
        )
    logger.info("Laudus balanceSheet/totals %s: %d cuentas", opening_date, len(rows))
    return rows


def signed_balance(row: dict[str, Any]) -> float:
    """Saldo neto en convención Beancount (positivo Assets, negativo Liabilities)."""
    return float(row["debitBalance"]) - float(row["creditBalance"])


def load_account_index(accounts_beancount: Path) -> dict[str, str]:
    """Parsea accounts.beancount y devuelve mapping account_number → full path.

    Usa la metadata `code:` de cada directiva `open` (que el Task 2 emite
    siempre con el account_number padded a 6 dígitos).
    """
    entries, errors, _ = loader.load_file(str(accounts_beancount))
    if errors:
        raise OpeningBalanceError(
            f"Errores al cargar {accounts_beancount}: {errors}"
        )
    index: dict[str, str] = {}
    for entry in entries:
        if isinstance(entry, bcdata.Open):
            code = entry.meta.get("code")
            if code:
                index[code] = entry.account
    return index


def render_opening_beancount(
    balances: list[dict[str, Any]],
    account_index: dict[str, str],
) -> str:
    """Renderiza el archivo opening-2021.beancount completo."""
    header = (
        ";; ledger/opening-2021.beancount — generado por bootstrap/generate_opening_balances.py\n"
        ";; Story 9.1 (Bootstrap histórico Beancount).\n"
        ";; Saldos iniciales al 2021-01-01 derivados del balance sheet de Laudus\n"
        ";; (JE 140 — Saldo anterior). Pre-2026 todo CLP por decisión Q4.\n"
    )
    parts = [header]
    # Equity y pads van al día anterior — Beancount exige pad-date < balance-date
    # para que el pad sea aplicado y el balance check pase.
    parts.append(f"{PAD_DATE} open {EQUITY_OPENING} CLP, USD")

    nonzero = [r for r in balances if signed_balance(r) != 0]
    nonzero_sorted = sorted(nonzero, key=lambda r: r["accountNumber"])

    missing: list[str] = []
    for row in nonzero_sorted:
        padded = normalize_account_number(row["accountNumber"])
        path = account_index.get(padded)
        if path is None:
            missing.append(f"{padded} ({row['accountName']!r})")
            continue
        amount = signed_balance(row)
        # Beancount accepta hasta 2 decimales para CLP (saldos enteros en práctica).
        amount_str = f"{amount:.2f}"
        parts.append(
            f"{PAD_DATE} pad {path} {EQUITY_OPENING}\n"
            f'  source_je: "{SOURCE_JE}"'
        )
        parts.append(f"{OPENING_DATE} balance {path} {amount_str} CLP")

    if missing:
        raise OpeningBalanceError(
            f"{len(missing)} cuentas con saldo en Laudus pero no abiertas en "
            f"accounts.beancount: {missing}. Re-correr generate_accounts.py o "
            f"reclasificar la cuenta en Supabase."
        )

    return "\n\n".join(parts) + "\n"


def run_opening_bootstrap(
    *,
    ledger_path: Path,
    opening_date: str = OPENING_DATE,
    laudus_balances: Optional[list[dict[str, Any]]] = None,
) -> int:
    """Orquesta el bootstrap de opening balances.

    Returns: 0 OK, 2 mismatch (saldo en Laudus sin cuenta abierta), 3 inviable.
    """
    accounts_path = ledger_path / "accounts.beancount"
    if not accounts_path.exists():
        print(f"[FAIL] {accounts_path} no existe — correr generate_accounts.py primero")
        return 3

    balances = laudus_balances if laudus_balances is not None else fetch_opening_balances(opening_date)
    account_index = load_account_index(accounts_path)

    nonzero_count = sum(1 for r in balances if signed_balance(r) != 0)
    print(f"Laudus balance sheet @ {opening_date}: {len(balances)} cuentas "
          f"({nonzero_count} con saldo != 0)")
    print(f"accounts.beancount: {len(account_index)} cuentas abiertas")

    try:
        text = render_opening_beancount(balances, account_index)
    except OpeningBalanceError as exc:
        print(f"\n[FAIL] {exc}")
        return 2

    out_path = ledger_path / "opening-2021.beancount"
    out_path.write_text(text, encoding="utf-8")
    print(f"\n[OK] Renderizado {out_path} ({nonzero_count} balances + 1 equity open)")
    return 0


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-path", type=Path, default=Path("ledger"))
    parser.add_argument("--opening-date", type=str, default=OPENING_DATE)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return run_opening_bootstrap(
        ledger_path=args.ledger_path, opening_date=args.opening_date,
    )


if __name__ == "__main__":
    sys.exit(_cli())
