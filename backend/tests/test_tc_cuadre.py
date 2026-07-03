"""Tests de compute_tc_cuadre — cuadre de la cartola TC contra el ledger (C1 + pago vs Laudus)."""
from decimal import Decimal

from beancount.parser import parser

from backend.app.services.tc_cuadre import compute_tc_cuadre

REAL = "Liabilities:EAG:TC:Real:TestCard"
LUMP = "Expenses:EAG:TC:TestCard-430005"

# Deuda: apertura −1000, compra −300, pago +1000 → TC:Real = −300 = −closing(300). Pago cartola 1000
# == pago Laudus 1000 (Assets:Banco → lump).
LEDGER = """
2026-04-01 * "APERTURA"
  operation_type: "apertura"
  source: "cartola-tc"
  Liabilities:EAG:TC:Real:TestCard   -1000.00 CLP
  Equity:Apertura:TarjetasSinDetalle  1000.00 CLP

2026-04-05 * "COMPRA X"
  operation_type: "compra"
  source: "cartola-tc"
  Liabilities:EAG:TC:Real:TestCard   -300.00 CLP
  Expenses:EAG:Suspense               300.00 CLP

2026-04-14 * "PAGO PAC"
  operation_type: "pago"
  source: "cartola-tc"
  Expenses:EAG:TC:TestCard-430005    -1000.00 CLP
  Liabilities:EAG:TC:Real:TestCard    1000.00 CLP

2026-04-14 * "Visa Test EAG Marzo 2026"
  id: "999"
  Assets:EAG:Bancos:Test             -1000.00 CLP
  Expenses:EAG:TC:TestCard-430005     1000.00 CLP
"""


def _entries():
    entries, errors, _ = parser.parse_string(LEDGER)
    assert not errors, errors
    return entries


def test_cuadre_ok():
    r = compute_tc_cuadre(_entries(), tc_real_account=REAL, lump_account=LUMP,
                          year_month="2026-04", closing=Decimal("300"))
    assert r["c1_ok"] is True
    assert r["tc_real_balance"] == -300.0
    assert r["pago_cartola"] == 1000.0
    assert r["laudus_payment_total"] == 1000.0
    assert r["pago_ok"] is True
    assert len(r["laudus_payments"]) == 1
    assert r["laudus_payments"][0]["bank_account"] == "Assets:EAG:Bancos:Test"
    assert "Marzo 2026" in r["laudus_payments"][0]["narration"]


def test_c1_falla_si_deuda_no_matchea_cierre():
    r = compute_tc_cuadre(_entries(), tc_real_account=REAL, lump_account=LUMP,
                          year_month="2026-04", closing=Decimal("999"))  # cierre equivocado
    assert r["c1_ok"] is False
    assert r["tc_real_balance"] == -300.0


def test_pago_no_cuadra_sin_asiento_laudus():
    # Sin el asiento de Laudus (solo cartola) → pago_ok False, laudus vacío.
    only_cartola = "\n".join(LEDGER.split("\n")[:18])  # corta antes del asiento Laudus
    entries, errors, _ = parser.parse_string(only_cartola)
    assert not errors, errors
    r = compute_tc_cuadre(entries, tc_real_account=REAL, lump_account=LUMP,
                          year_month="2026-04", closing=Decimal("300"))
    assert r["laudus_payments"] == []
    assert r["pago_ok"] is False
