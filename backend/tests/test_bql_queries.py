"""Tests for BQL dashboard queries — Story 9.2 AC3/AC4.

Validates the Sheets-compatible SHAPE and basic correctness of the Beancount
engine against a synthetic mini-ledger. Amount parity vs. real Laudus/Sheets
data is covered (xfail) by test_beancount_parity.py.
"""
from backend.app.services.bql_queries import (
    balance_sheet_via_beancount,
    ledger_entries_via_beancount,
)
from backend.app.services.ledger_service import LedgerService


MINI_LEDGER = """\
option "operating_currency" "CLP"
1900-01-01 commodity CLP

2020-01-01 open Assets:EAG:Bancos:TestBank-111005 CLP
  code: "111005"
  laudus_account_name: "Banco Test EAG"
  laudus_categoria1: "ACTIVO EAG"
  laudus_categoria2: "ACTIVOS CORRIENTES"
  laudus_categoria3: "DISPONIBLE - EAG"
2020-01-01 open Liabilities:EAG:Tarjeta-211005 CLP
  code: "211005"
  laudus_account_name: "Tarjeta EAG"
2020-01-01 open Income:EAG:Ventas-411005 CLP
  code: "411005"
2020-01-01 open Expenses:EAG:Gastos-511005 CLP
  code: "511005"
2020-01-01 open Assets:Jocelyn:Bancos:TestBankJ-610005 CLP
  code: "610005"
  laudus_account_name: "Banco Test Jocelyn"

2024-03-15 * "Pago cliente"
  Assets:EAG:Bancos:TestBank-111005   100000 CLP
  Income:EAG:Ventas-411005           -100000 CLP

2024-06-20 * "Compra insumos"
  Expenses:EAG:Gastos-511005           30000 CLP
  Assets:EAG:Bancos:TestBank-111005   -30000 CLP

2024-04-10 * "Gasto Jocelyn"
  Assets:Jocelyn:Bancos:TestBankJ-610005   50000 CLP
  Income:EAG:Ventas-411005                -50000 CLP
"""

BALANCE_SHEET_KEYS = {
    "account_id", "account_number", "account", "account_name", "debit", "credit",
    "debit_balance", "credit_balance", "query_date", "is_latest",
}
LEDGER_KEYS = {
    "journalentryid", "journalentrynumber", "date", "accountnumber", "lineid",
    "description", "debit", "credit", "currencycode", "paritytomaincurrency",
    "periodo", "accountName", "Categoria1", "Categoria2", "Categoria3",
}


def _ledger(tmp_path):
    main = tmp_path / "main.beancount"
    main.write_text(MINI_LEDGER, encoding="utf-8")
    return LedgerService(str(main))


# ── balance_sheet_via_beancount (AC3) ─────────────────────────────────────────


def test_balance_sheet_shape(tmp_path):
    """AC3: every record carries exactly the Sheets balance-sheet keys."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "EAG")
    assert set(result.keys()) == {"data", "meta"}
    assert "last_sync" in result["meta"]
    for record in result["data"]:
        assert set(record.keys()) == BALANCE_SHEET_KEYS


def test_balance_sheet_exposes_account_root(tmp_path):
    """El frontend agrupa por la raíz contable → `account` (path beancount) debe venir en cada fila."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "EAG")
    by_code = {r["account_number"]: r["account"] for r in result["data"]}
    assert by_code["111005"].startswith("Assets:")  # banco → raíz Assets (Activos)
    assert all(r["account"] for r in result["data"])  # toda fila trae el path


def test_balance_sheet_excludes_income_and_expenses(tmp_path):
    """AC3: balance sheet only includes Assets/Liabilities/Equity, not Income/Expenses."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "EAG")
    numbers = {r["account_number"] for r in result["data"]}
    assert "111005" in numbers          # Assets:EAG appears
    assert "411005" not in numbers      # Income excluded
    assert "511005" not in numbers      # Expenses excluded


def test_balance_sheet_cumulative_balance(tmp_path):
    """AC3: Assets:EAG balance = 100000 - 30000 = 70000 (debit-natured)."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "EAG")
    bank = next(r for r in result["data"] if r["account_number"] == "111005")
    assert bank["debit_balance"] == 70000.0
    assert bank["credit_balance"] == 0.0
    assert bank["account_name"] == "Banco Test EAG"


def test_balance_sheet_as_of_date(tmp_path):
    """AC3: date_to bounds the cumulative balance (AT date_range.end)."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "EAG", date_to="2024-04-01")
    bank = next(r for r in result["data"] if r["account_number"] == "111005")
    assert bank["debit_balance"] == 100000.0  # only the 2024-03-15 tx counts
    assert result["meta"]["last_sync"] == "2024-04-01"


def test_balance_sheet_eag_is_consolidated(tmp_path):
    """EAG es la entidad matriz: su balance-sheet incluye a las hijas (consolidado)."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "EAG")
    numbers = {r["account_number"] for r in result["data"]}
    assert "111005" in numbers  # cuenta propia de EAG
    assert "610005" in numbers  # cuenta de Jocelyn, consolidada bajo EAG


def test_balance_sheet_child_slice_isolated(tmp_path):
    """Seleccionar una hija devuelve SU slice — sin las cuentas propias de EAG."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "Jocelyn")
    numbers = {r["account_number"] for r in result["data"]}
    assert "610005" in numbers      # cuenta de Jocelyn
    assert "111005" not in numbers  # cuenta de EAG excluida


def test_balance_sheet_empty_entity(tmp_path):
    """AC3: an entity with no balance-sheet postings → empty data, null last_sync."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "Jeannette")
    assert result["data"] == []


# ── ledger_entries_via_beancount (AC4) ────────────────────────────────────────


def test_ledger_entries_shape(tmp_path):
    """AC4: every record carries exactly the Sheets ledger-entry alias keys."""
    result = ledger_entries_via_beancount(_ledger(tmp_path), "EAG")
    assert set(result.keys()) == {"data", "meta"}
    for record in result["data"]:
        assert set(record.keys()) == LEDGER_KEYS


def test_ledger_entries_entity_filter(tmp_path):
    """AC4: only EAG postings returned; Jocelyn's asset posting excluded."""
    result = ledger_entries_via_beancount(_ledger(tmp_path), "EAG")
    numbers = {r["accountnumber"] for r in result["data"]}
    assert "610005" not in numbers
    assert {"111005", "411005", "511005"} <= numbers


def test_ledger_entries_debit_credit_split(tmp_path):
    """AC4: positive number → debit, negative → credit; amounts are floats."""
    result = ledger_entries_via_beancount(_ledger(tmp_path), "EAG", account_number="111005")
    # account 111005 has +100000 (debit) and -30000 (credit)
    debits = sorted(r["debit"] for r in result["data"])
    credits = sorted(r["credit"] for r in result["data"])
    assert 100000.0 in debits
    assert 30000.0 in credits
    for r in result["data"]:
        assert isinstance(r["debit"], float)
        assert isinstance(r["credit"], float)
        assert r["paritytomaincurrency"] == 1.0
        assert r["currencycode"] == "CLP"


def test_ledger_entries_account_number_filter(tmp_path):
    """AC4: account_number filters to that account only."""
    result = ledger_entries_via_beancount(_ledger(tmp_path), "EAG", account_number="111005")
    assert result["data"]
    assert all(r["accountnumber"] == "111005" for r in result["data"])


def test_ledger_entries_date_range(tmp_path):
    """AC4: date_from/date_to bound the postings by date."""
    result = ledger_entries_via_beancount(
        _ledger(tmp_path), "EAG", date_from="2024-06-01", date_to="2024-06-30"
    )
    assert result["data"]
    assert all(r["date"].startswith("2024-06") for r in result["data"])


def test_ledger_entries_last_sync_is_max_date(tmp_path):
    """AC4: meta.last_sync is the most recent posting date."""
    result = ledger_entries_via_beancount(_ledger(tmp_path), "EAG")
    assert result["meta"]["last_sync"] == "2024-06-20"


def test_ledger_entries_categoria_enrichment(tmp_path):
    """AC4: records are enriched with Categoria1..3 from Open metadata."""
    result = ledger_entries_via_beancount(_ledger(tmp_path), "EAG", account_number="111005")
    record = result["data"][0]
    assert record["Categoria1"] == "ACTIVO EAG"
    assert record["accountName"] == "Banco Test EAG"
