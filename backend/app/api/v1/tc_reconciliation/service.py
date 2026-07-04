"""Servicio de la vista de cuadre TC — Story 6.6.

Enumera las cartolas TC importadas de una tarjeta (por `bank_account_id`, escaneando los asientos
`source=cartola-tc` del ledger) y computa C1–C5 por período reusando `compute_tc_cuadre`. Puro sobre
las `entries` — el router resuelve la cuenta (`BankAccountResolver` + `tc_real_account`) y llama acá.
"""
from __future__ import annotations

from beancount.core import data

from backend.app.services.tc_cuadre import compute_tc_cuadre

_CONSUMO_OPS = {"compra", "cuota"}
_PAYMENT_OPS = {"pago"}
_SKIP_MOVEMENT_OPS = {"apertura"}  # la apertura es saldo inicial, no un movimiento del mes


def _movements(entries: list, bank_account_id: str, year_month: str, tc_real_account: str):
    """Movimientos de la cartola `year_month` (para el detalle expandible) + Σs por tipo.

    El monto de cada movimiento = la pata a `tc_real_account` (CLP posteado); la apertura se excluye.
    """
    movements: list[dict] = []
    sum_compras = sum_pagos = sum_cargos = 0.0
    for e in entries:
        if not isinstance(e, data.Transaction):
            continue
        meta = e.meta or {}
        if (meta.get("source") != "cartola-tc"
                or meta.get("bank_account_id") != bank_account_id
                or meta.get("period") != year_month):
            continue
        op = str(meta.get("operation_type") or "")
        if op in _SKIP_MOVEMENT_OPS:
            continue
        leg = next((p.units.number for p in e.postings
                    if p.account == tc_real_account and p.units), None)
        amount = float(leg) if leg is not None else 0.0
        movements.append({
            "date": e.date.isoformat(),
            "narration": e.narration or "",
            "amount": amount,
            "operation_type": op,
        })
        magnitude = abs(amount)
        if op in _CONSUMO_OPS:
            sum_compras += magnitude
        elif op in _PAYMENT_OPS:
            sum_pagos += magnitude
        else:
            sum_cargos += magnitude
    return movements, {"sum_compras": sum_compras, "sum_pagos": sum_pagos, "sum_cargos": sum_cargos}


def build_rows(
    entries: list,
    *,
    tc_real_account: str,
    lump_account: str,
    bank_account_id: str,
    year_month: str | None = None,
) -> list[dict]:
    """Filas de cuadre (una por cartola importada de la tarjeta), mes descendente.

    `lump_account` = la cuenta-gasto de Laudus (`Expenses:EAG:TC:<stem>-<code>`, = `resolver.resolve`).
    `year_month` opcional filtra a un solo mes.
    """
    periods: set[str] = set()
    for e in entries:
        if not isinstance(e, data.Transaction):
            continue
        meta = e.meta or {}
        if (meta.get("source") == "cartola-tc"
                and meta.get("bank_account_id") == bank_account_id
                and meta.get("period")):
            periods.add(str(meta["period"]))
    if year_month is not None:
        periods &= {year_month}

    rows: list[dict] = []
    for ym in sorted(periods, reverse=True):
        cuadre = compute_tc_cuadre(
            entries, tc_real_account=tc_real_account, lump_account=lump_account,
            year_month=ym, bank_account_id=bank_account_id)
        movements, sums = _movements(entries, bank_account_id, ym, tc_real_account)
        rows.append({
            **cuadre,
            "card": bank_account_id,
            "year_month": ym,
            "tc_real_account": tc_real_account,
            "lump_account": lump_account,
            "movements": movements,
            **sums,
        })
    return rows
