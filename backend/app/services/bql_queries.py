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

import re
from datetime import date

from beancount.core.data import Open, Transaction

from backend.app.services.ledger_service import LedgerService, tx_id_of

# Roots that make up the balance sheet (AC3).
_BALANCE_SHEET_ROOTS = "Assets|Liabilities|Equity"

# Entidad matriz cuyo balance-sheet es CONSOLIDADO (EAG + las 4 hijas),
# espejando el tab legacy `balance_sheet_eag` de Sheets. Las hijas son egresos
# de EAG (971/1077 tx con contraparte en EAG). Seleccionar una hija en el filtro
# sigue devolviendo SU slice — la separación por entidad no se pierde.
_CONSOLIDATED_ENTITY = "EAG"


def _account_meta(entries: list) -> dict[str, dict]:
    """Map full account name → its Open directive metadata."""
    return {e.account: (e.meta or {}) for e in entries if isinstance(e, Open)}


import functools


def _entity_pattern(roots: str, entity: str) -> str:
    """Regex matching `<root>:<entity>:...` for the given roots."""
    return f"^({roots}):{entity}:"


@functools.lru_cache(maxsize=16)
def _compiled_entity_pattern(roots: str, entity: str) -> re.Pattern:
    return re.compile(_entity_pattern(roots, entity))


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

    if entity == _CONSOLIDATED_ENTITY:
        # Consolidado: roots-only, sin segmento de entidad → todas las entidades.
        pattern = f"^({_BALANCE_SHEET_ROOTS}):"
    else:
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
            # Path beancount completo (ej. "Assets:Jocelyn:Bancos:..."). El frontend agrupa por la
            # raíz contable (Assets/Liabilities/Equity) en vez del primer dígito del código — así las
            # cuentas de las hijas (consolidadas en EAG, códigos 6/7/8/9) caen en Activos/Pasivos y no
            # en "Otros". El path legacy de Sheets no trae este campo → el frontend cae al código.
            "account": account,
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

    Itera `ledger.entries()` directamente en vez de BQL (Story 7.1b AC1): el BQL entrega
    filas por posting sin acceso a la transacción padre, y cada fila necesita el `tx_id`
    de la TX (el ancla de owner-comments es por transacción, no por pata). Mismo patrón
    que `list_pending` en `transactions/service.py`. Una sola pasada (lección D7).
    """
    entries = ledger.entries()
    meta = _account_meta(entries)

    pattern = _compiled_entity_pattern("Assets|Liabilities|Equity|Income|Expenses", entity)
    try:
        d_from = date.fromisoformat(date_from) if date_from else None
        d_to = date.fromisoformat(date_to) if date_to else None
    except ValueError as e:
        raise ValueError(f"Invalid date format: {e}")

    data = []
    last_sync: str | None = None
    for entry in entries:
        if not isinstance(entry, Transaction):
            continue
        if d_from is not None and entry.date < d_from:
            continue
        if d_to is not None and entry.date > d_to:
            break
        tx_id: str | None = None  # una sola vez por tx, compartido entre sus patas
        for posting in entry.postings:
            if not pattern.match(posting.account):
                continue
            m = meta.get(posting.account, {})
            code = str(m.get("code", ""))
            if account_number is not None and code != account_number:
                continue
            number = posting.units.number if posting.units else None
            currency = posting.units.currency if posting.units else None
            amount = float(number) if number is not None else 0.0
            iso_date = entry.date.isoformat()
            if last_sync is None or iso_date > last_sync:
                last_sync = iso_date
            if tx_id is None:
                tx_id = tx_id_of(entry)
            data.append({
                "journalentryid": None,
                "journalentrynumber": None,
                "date": iso_date,
                "accountnumber": code,
                "lineid": None,
                "description": entry.narration or "",
                "debit": amount if amount >= 0 else 0.0,
                "credit": -amount if amount < 0 else 0.0,
                "currencycode": currency or "CLP",
                "paritytomaincurrency": 1.0,
                "periodo": "",
                "accountName": str(m.get("laudus_account_name", posting.account)),
                "Categoria1": str(m.get("laudus_categoria1", "")),
                "Categoria2": str(m.get("laudus_categoria2", "")),
                "Categoria3": str(m.get("laudus_categoria3", "")),
                "tx_id": tx_id,
            })
    # `ORDER BY date DESC` del BQL saliente; sort estable → orden de archivo intra-día.
    data.sort(key=lambda r: r["date"], reverse=True)
    return {"data": data, "meta": {"last_sync": last_sync}}


def report_rows_via_beancount(
    ledger: LedgerService,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Filas estilo `ledger_final` desde Beancount — TODAS las entidades (#4 migración reporte).

    El reporte de gastos (`report_builder`) agrega por código de cuenta y categoría
    sobre EAG + las 4 hijas a la vez, así que a diferencia de
    `ledger_entries_via_beancount` NO se filtra por entity. Cada posting del rango
    se mapea a una fila con exactamente las claves que `report_builder` consume desde
    `ledger_final` (date, accountnumber, accountName, Categoria1..3, debit, credit).
    El split debit/credit por signo del número es el mismo que el resto del módulo.
    """
    entries = ledger.entries()
    meta = _account_meta(entries)
    conn = ledger.connection()

    conds = []
    if date_from:
        conds.append(f"date >= {date_from}")
    if date_to:
        conds.append(f"date <= {date_to}")
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    bql = f"SELECT date, account, number, currency{where} ORDER BY date"
    cursor = conn.execute(bql)

    rows = []
    for row_date, account, number, currency in cursor.fetchall():
        m = meta.get(account, {})
        amount = float(number) if number is not None else 0.0
        iso_date = row_date.isoformat() if isinstance(row_date, date) else str(row_date)
        rows.append({
            "date": iso_date,
            "accountnumber": str(m.get("code", "")),
            "accountName": str(m.get("laudus_account_name", account)),
            "Categoria1": str(m.get("laudus_categoria1", "")),
            "Categoria2": str(m.get("laudus_categoria2", "")),
            "Categoria3": str(m.get("laudus_categoria3", "")),
            "debit": amount if amount >= 0 else 0.0,
            "credit": -amount if amount < 0 else 0.0,
        })
    return rows
