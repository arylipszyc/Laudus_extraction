"""Cuadre de una cartola TC contra la contabilidad (beancount) — post-confirmación.

Se calcula al postear el desglose (validate-balance status=corrected) y viaja en la respuesta
para que la pantalla de "Cartola importada" muestre si la data de la cartola cuadra con el ledger.

v1 — dos chequeos (diseño Valentina 2026-07-02, ver planning-artifacts):
- **C1** `saldo TC:Real al cierre == −cierre declarado por la cartola` (el invariante que detecta
  deuda mal materializada — este es el que habría cachado el bug de categorización).
- **Pago** el `PAGO PAC` de la cartola == el asiento de pago que Laudus registró para la tarjeta
  ese mes (Assets:Banco → Expenses:...TC:<lump>). Se muestran lado a lado.
"""
from __future__ import annotations

from decimal import Decimal

from beancount.core import data

_TOL = Decimal("1")  # CLP: sin decimales


def _month(d) -> str:
    return d.isoformat()[:7]


def compute_tc_cuadre(
    entries: list,
    *,
    tc_real_account: str,
    lump_account: str,
    year_month: str,
    closing: Decimal,
) -> dict:
    """Devuelve el cuadre de la cartola `year_month` de una tarjeta contra el ledger `entries`.

    `tc_real_account` = `Liabilities:EAG:TC:Real:<stem>`; `lump_account` = la cuenta de gasto que
    Laudus usa para el pago (`Expenses:EAG:TC:<stem>-<code>`); `closing` = cierre declarado por la
    cartola (viene del request de validate-balance).
    """
    closing = Decimal(str(closing))

    # C1 — saldo TC:Real acumulado hasta el fin del mes de la cartola.
    tc_real_balance = Decimal(0)
    for e in entries:
        if isinstance(e, data.Transaction) and _month(e.date) <= year_month:
            for p in e.postings:
                if p.account == tc_real_account and p.units:
                    tc_real_balance += p.units.number
    c1_ok = abs(tc_real_balance + closing) <= _TOL  # TC:Real == −closing

    # Pago de la cartola — la línea `pago` que toca TC:Real este mes (magnitud positiva).
    pago_cartola = Decimal(0)
    for e in entries:
        if not isinstance(e, data.Transaction):
            continue
        meta = e.meta or {}
        if meta.get("source") == "cartola-tc" and meta.get("operation_type") == "pago" \
                and _month(e.date) == year_month:
            for p in e.postings:
                if p.account == tc_real_account and p.units:
                    pago_cartola += p.units.number

    # Pago Laudus — asiento(s) NO-cartola que tocan el lump de la tarjeta este mes (magnitud +).
    laudus_payments: list[dict] = []
    for e in entries:
        if not isinstance(e, data.Transaction) or _month(e.date) != year_month:
            continue
        if (e.meta or {}).get("source") == "cartola-tc":
            continue
        lump_leg = next((p for p in e.postings if p.account == lump_account and p.units), None)
        if lump_leg is None or lump_leg.units.number <= 0:
            continue
        bank_leg = next((p for p in e.postings
                         if p.account.split(":")[0] == "Assets" and p.units), None)
        laudus_payments.append({
            "date": e.date.isoformat(),
            "narration": e.narration or "",
            "amount": float(lump_leg.units.number),
            "bank_account": bank_leg.account if bank_leg else None,
        })
    laudus_total = Decimal(str(sum(p["amount"] for p in laudus_payments)))
    pago_ok = bool(laudus_payments) and abs(pago_cartola - laudus_total) <= _TOL

    return {
        "c1_ok": c1_ok,
        "tc_real_balance": float(tc_real_balance),
        "closing": float(closing),
        "pago_cartola": float(pago_cartola),
        "laudus_payment_total": float(laudus_total),
        "laudus_payments": laudus_payments,
        "pago_ok": pago_ok,
    }
