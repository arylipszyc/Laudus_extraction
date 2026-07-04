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


# ── Story 6.6: C1–C5 con metadata persistida (opening/closing/currency/fx) ──

# Dos meses contiguos de la misma tarjeta CLP: mar (0→1000) y abr (1000→1300). La deuda TC:Real
# acumulada a fin de abr = −1300 = −closing_abr (C1); apertura abr 1000 == cierre mar 1000 (C2).
LEDGER_2M = """
2026-03-10 * "COMPRA MARZO"
  operation_type: "compra"
  source: "cartola-tc"
  period: "2026-03"
  bank_account_id: "BCI_1027"
  opening: "0"
  closing: "1000"
  currency: "CLP"
  Liabilities:EAG:TC:Real:TestCard   -1000.00 CLP
  Expenses:EAG:Suspense               1000.00 CLP

2026-04-05 * "COMPRA ABRIL"
  operation_type: "compra"
  source: "cartola-tc"
  period: "2026-04"
  bank_account_id: "BCI_1027"
  opening: "1000"
  closing: "1300"
  currency: "CLP"
  Liabilities:EAG:TC:Real:TestCard   -300.00 CLP
  Expenses:EAG:Suspense               300.00 CLP
"""


def _parse(text):
    entries, errors, _ = parser.parse_string(text)
    assert not errors, errors
    return entries


def test_c1_c2_ok_contiguo():
    r = compute_tc_cuadre(_parse(LEDGER_2M), tc_real_account=REAL, lump_account=LUMP,
                          year_month="2026-04")  # closing se lee de la metadata
    assert r["c1_ok"] is True          # −1300 == −(1300 × 1)
    assert r["tc_real_balance"] == -1300.0
    assert r["closing"] == 1300.0
    assert r["c2_ok"] is True           # apertura abr 1000 == cierre mar 1000
    assert r["c2_prior_closing"] == 1000.0
    assert r["c3_ok"] is True


LEDGER_SOLO_ABRIL = """
2026-04-05 * "COMPRA ABRIL"
  operation_type: "compra"
  source: "cartola-tc"
  period: "2026-04"
  bank_account_id: "BCI_1027"
  opening: "1000"
  closing: "1300"
  currency: "CLP"
  Liabilities:EAG:TC:Real:TestCard   -300.00 CLP
  Expenses:EAG:Suspense               300.00 CLP
"""


def test_c2_falla_sin_mes_anterior():
    # Solo abril → no hay cartola de marzo → C2 no puede cuadrar.
    r = compute_tc_cuadre(_parse(LEDGER_SOLO_ABRIL), tc_real_account=REAL, lump_account=LUMP,
                          year_month="2026-04")
    assert r["c2_ok"] is False
    assert r["c2_reason"] == "sin cartola anterior"


# USD: closing en USD (10), fx 900 → TC:Real (CLP) debe ser −9000. C1 aplica el fx.
LEDGER_USD = """
2026-05-08 * "COMPRA USD"
  operation_type: "compra"
  source: "cartola-tc"
  period: "2026-05"
  bank_account_id: "BCI_1027_USD"
  opening: "0"
  closing: "10"
  currency: "USD"
  fx: "900"
  Liabilities:EAG:TC:Real:TestCardUs   -9000.00 CLP
  Expenses:EAG:Suspense                 9000.00 CLP
"""


def test_c1_usd_aplica_fx():
    r = compute_tc_cuadre(_parse(LEDGER_USD), tc_real_account="Liabilities:EAG:TC:Real:TestCardUs",
                          lump_account="Expenses:EAG:TC:TestCardUs-430006", year_month="2026-05")
    assert r["c1_ok"] is True           # nativo: −9000/900 = −10 == −closing(10)
    assert r["currency"] == "USD"
    assert r["fx"] == 900.0
    assert r["tc_real_native"] == -10.0
    assert r["closing_clp"] == 9000.0


# USD multi-mes con fx DISTINTO por estado (el caso que el drift rompía). Mayo fx 900 (compra 10 USD →
# TC:Real −9000 CLP, native −10). Junio fx 950 (compra 5 USD → TC:Real −4750 CLP, native −5). Saldo CLP
# acumulado junio = −13750, pero closing_jun×fx_jun = 15×950 = 14250 → la fórmula CLP daría |−13750+14250|
# = 500 > tol → FALSO ROJO. En nativo: −10 + −5 = −15 == −closing(15) → verde. Decisión Valentina.
LEDGER_USD_MULTIMES = """
2026-05-08 * "COMPRA MAYO USD"
  operation_type: "compra"
  source: "cartola-tc"
  period: "2026-05"
  bank_account_id: "BCI_1027_USD"
  opening: "0"
  closing: "10"
  currency: "USD"
  fx: "900"
  Liabilities:EAG:TC:Real:TestCardUs   -9000.00 CLP
  Expenses:EAG:Suspense                 9000.00 CLP

2026-06-08 * "COMPRA JUNIO USD"
  operation_type: "compra"
  source: "cartola-tc"
  period: "2026-06"
  bank_account_id: "BCI_1027_USD"
  opening: "10"
  closing: "15"
  currency: "USD"
  fx: "950"
  Liabilities:EAG:TC:Real:TestCardUs   -4750.00 CLP
  Expenses:EAG:Suspense                 4750.00 CLP
"""


def test_c1_usd_multimes_nativo_no_falso_rojo():
    """Junio: la deuda cuadra en nativo aunque el saldo CLP mezcle fx históricos (diferencia de cambio)."""
    real = "Liabilities:EAG:TC:Real:TestCardUs"
    r = compute_tc_cuadre(_parse(LEDGER_USD_MULTIMES), tc_real_account=real,
                          lump_account="Expenses:EAG:TC:TestCardUs-430006", year_month="2026-06")
    assert r["c1_ok"] is True                       # nativo −15 == −closing(15), NO falso rojo
    assert r["tc_real_native"] == -15.0             # −9000/900 + −4750/950
    assert r["tc_real_balance"] == -13750.0         # saldo CLP (mezcla fx) para el display
    # con la fórmula CLP vieja habría sido |−13750 + 15×950| = 500 → rojo


# Asiento corrupto: ambas patas a Expenses (pata TC:Real destruida — el bug de categorización).
LEDGER_CORRUPTO = """
2026-04-05 * "COMPRA CORRUPTA"
  operation_type: "compra"
  source: "cartola-tc"
  period: "2026-04"
  bank_account_id: "BCI_1027"
  opening: "1000"
  closing: "1300"
  currency: "CLP"
  Expenses:EAG:Suspense    300.00 CLP
  Expenses:EAG:Otros      -300.00 CLP
"""


def test_c3_detecta_asiento_corrupto():
    r = compute_tc_cuadre(_parse(LEDGER_CORRUPTO), tc_real_account=REAL, lump_account=LUMP,
                          year_month="2026-04", bank_account_id="BCI_1027")
    assert r["c3_ok"] is False          # sin pata TC:Real → corrupto
    assert r["c3_corrupted_count"] == 1
    assert r["status"] == "red"


# Lump con residual: un pago de Laudus al lump SIN el asiento (b) que lo reclasifica → no netea.
LEDGER_LUMP_RESIDUAL = """
2026-04-14 * "Pago Laudus sin reclasificar"
  id: "999"
  Assets:EAG:Bancos:Test            -1000.00 CLP
  Expenses:EAG:TC:TestCard-430005    1000.00 CLP
"""


def test_c5_residual_no_cero():
    r = compute_tc_cuadre(_parse(LEDGER_LUMP_RESIDUAL), tc_real_account=REAL, lump_account=LUMP,
                          year_month="2026-04", closing=Decimal("0"))
    assert r["c5_ok"] is False
    assert r["c5_residual"] == 1000.0
