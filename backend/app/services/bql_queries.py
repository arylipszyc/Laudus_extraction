"""BQL query functions for the dashboard endpoints (Story 9.2 AC3/AC4).

Each function takes a `LedgerService` plus the same params the Sheets path
receives and returns a dict shaped identically to the Sheets response
(`{"data": [...], "meta": {"last_sync": ...}}`) so the frontend cannot tell
which engine produced the response (AC2).

Amount semantics here are best-effort double-entry mappings (debit/credit split
by sign); true parity vs. the Laudus-derived Sheets values is validated by the
parity suite once the ledger is fully bootstrapped — see
`tests/README-beancount-parity.md` (AC9).

Account-name convention (from `accounts.beancount`):
    Assets:EAG:Bancos:BancoBci10160175-111005
      → entity   = 2nd path component ("EAG")
      → metadata = Open directive meta: code, laudus_account_name, laudus_categoria1..3
"""
from __future__ import annotations

from datetime import date

from beancount.core.data import Open, Transaction

from backend.app.services.ledger_service import LedgerService

# Roots that make up the balance sheet (AC3).
_BALANCE_SHEET_ROOTS = "Assets|Liabilities|Equity"


def _account_meta(entries: list) -> dict[str, dict]:
    """Map full account name → its Open directive metadata."""
    return {e.account: (e.meta or {}) for e in entries if isinstance(e, Open)}


def _entity_pattern(roots: str, entity: str) -> str:
    """Regex matching `<root>:<entity>:...` for the given roots."""
    return f"^({roots}):{entity}:"


def _clp(inventory) -> float:
    """Extract the CLP number from a beanquery `sum(position)` Inventory."""
    if inventory is None:
        return 0.0
    amount = inventory.get_currency_units("CLP")
    if amount is None or amount.number is None:
        return 0.0
    return float(amount.number)


def _max_transaction_date(entries: list) -> str | None:
    """Latest transaction date in the ledger as ISO string, or None."""
    dates = [e.date for e in entries if isinstance(e, Transaction)]
    return max(dates).isoformat() if dates else None


def balance_sheet_via_beancount(
    ledger: LedgerService,
    entity: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Balance sheet for `entity` as of `date_to` (cumulative), Sheets-shaped.

    `date_from` is accepted for signature parity but does not bound a
    point-in-time balance sheet (AC3 queries `AT date_range.end`).
    """
    entries = ledger.entries()
    meta = _account_meta(entries)
    conn = ledger.connection()

    pattern = _entity_pattern(_BALANCE_SHEET_ROOTS, entity)
    where = f'account ~ "{pattern}"'
    if date_to:
        where += f" AND date <= {date_to}"
    bql = (
        f"SELECT account, sum(position) AS balance "
        f"WHERE {where} GROUP BY account ORDER BY account"
    )
    cursor = conn.execute(bql)

    query_date = date_to or _max_transaction_date(entries) or ""
    data = []
    for account, balance in cursor.fetchall():
        amount = _clp(balance)
        m = meta.get(account, {})
        data.append({
            "account_id": None,
            "account_number": str(m.get("code", "")),
            "account_name": str(m.get("laudus_account_name", account)),
            "debit": 0.0,
            "credit": 0.0,
            "debit_balance": amount if amount >= 0 else 0.0,
            "credit_balance": -amount if amount < 0 else 0.0,
            "query_date": query_date,
            "is_latest": "TRUE",
        })
    return {"data": data, "meta": {"last_sync": query_date or None}}


def ledger_entries_via_beancount(
    ledger: LedgerService,
    entity: str,
    date_from: str | None = None,
    date_to: str | None = None,
    account_number: str | None = None,
) -> dict:
    """Ledger postings for `entity`, optionally filtered by date range/account.

    Returns records keyed by the Sheets column aliases the `LedgerEntryRecord`
    model expects (accountnumber, accountName, Categoria1..3, ...).
    """
    entries = ledger.entries()
    meta = _account_meta(entries)
    conn = ledger.connection()

    pattern = _entity_pattern("Assets|Liabilities|Equity|Income|Expenses", entity)
    where = f'account ~ "{pattern}"'
    if date_from:
        where += f" AND date >= {date_from}"
    if date_to:
        where += f" AND date <= {date_to}"
    bql = (
        f"SELECT date, account, narration, number, currency "
        f"WHERE {where} ORDER BY date DESC"
    )
    cursor = conn.execute(bql)

    data = []
    last_sync: str | None = None
    for row_date, account, narration, number, currency in cursor.fetchall():
        m = meta.get(account, {})
        code = str(m.get("code", ""))
        if account_number is not None and code != account_number:
            continue
        amount = float(number) if number is not None else 0.0
        iso_date = row_date.isoformat() if isinstance(row_date, date) else str(row_date)
        if last_sync is None or iso_date > last_sync:
            last_sync = iso_date
        data.append({
            "journalentryid": None,
            "journalentrynumber": None,
            "date": iso_date,
            "accountnumber": code,
            "lineid": None,
            "description": narration or "",
            "debit": amount if amount >= 0 else 0.0,
            "credit": -amount if amount < 0 else 0.0,
            "currencycode": currency or "CLP",
            "paritytomaincurrency": 1.0,
            "periodo": "",
            "accountName": str(m.get("laudus_account_name", account)),
            "Categoria1": str(m.get("laudus_categoria1", "")),
            "Categoria2": str(m.get("laudus_categoria2", "")),
            "Categoria3": str(m.get("laudus_categoria3", "")),
        })
    return {"data": data, "meta": {"last_sync": last_sync}}
