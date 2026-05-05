"""Tests para bootstrap.validate_cuadratura — Story 9.1 Task 6."""
from textwrap import dedent

from bootstrap.validate_cuadratura import (
    compare,
    fetch_beancount_balances,
    run_validation,
)


# ── Fixtures ────────────────────────────────────────────────────────────

LAUDUS_FIXTURE = [
    {"accountId": 273, "accountNumber": "111005", "accountName": "Banco BCI",
     "debit": 1000.0, "credit": 0.0, "debitBalance": 1000.0, "creditBalance": 0.0},
    {"accountId": 500, "accountNumber": "215001", "accountName": "VISA",
     "debit": 0.0, "credit": 500.0, "debitBalance": 0.0, "creditBalance": 500.0},
]

ACCOUNT_INDEX = {
    "111005": "Assets:EAG:Bancos:BancoBci-111005",
    "215001": "Liabilities:EAG:TC:Visa-215001",
}


def _bootstrap_ledger(tmp_path, opening_amounts: dict[str, float]):
    """Genera un main + accounts + opening mínimo. opening_amounts={path: signed_clp}."""
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / "main.beancount").write_text(dedent('''\
        option "operating_currency" "CLP"
        plugin "beancount.plugins.implicit_prices"
        1900-01-01 commodity CLP
        include "accounts.beancount"
        include "opening-2021.beancount"
    '''), encoding="utf-8")
    (ledger / "accounts.beancount").write_text(dedent('''\
        2020-12-31 open Assets:EAG:Bancos:BancoBci-111005 CLP
          code: "111005"
        2020-12-31 open Liabilities:EAG:TC:Visa-215001 CLP
          code: "215001"
    '''), encoding="utf-8")
    open_lines = ['2020-12-31 open Equity:EAG:OpeningBalances CLP, USD']
    for path, amt in opening_amounts.items():
        open_lines.append(
            f"2020-12-31 pad {path} Equity:EAG:OpeningBalances\n"
            f"2021-01-01 balance {path} {amt:.2f} CLP"
        )
    (ledger / "opening-2021.beancount").write_text("\n\n".join(open_lines) + "\n",
                                                    encoding="utf-8")
    return ledger


# ── compare ────────────────────────────────────────────────────────────

class TestCompare:
    def test_exact_match_returns_no_diffs(self):
        bc = {"Assets:EAG:Bancos:BancoBci-111005": 1000.0,
              "Liabilities:EAG:TC:Visa-215001": -500.0}
        assert compare(LAUDUS_FIXTURE, bc, ACCOUNT_INDEX) == []

    def test_amount_mismatch_emits_diff(self):
        bc = {"Assets:EAG:Bancos:BancoBci-111005": 999.0,  # off by 1
              "Liabilities:EAG:TC:Visa-215001": -500.0}
        diffs = compare(LAUDUS_FIXTURE, bc, ACCOUNT_INDEX)
        assert len(diffs) == 1
        assert diffs[0]["account_number"] == "111005"
        assert diffs[0]["diff"] == 1.0
        assert diffs[0]["reason"] == "amount_mismatch"

    def test_account_not_in_index(self):
        bc = {"Liabilities:EAG:TC:Visa-215001": -500.0}
        diffs = compare(LAUDUS_FIXTURE, bc, {"215001": "Liabilities:EAG:TC:Visa-215001"})
        assert any(d["reason"] == "account_not_in_beancount"
                   and d["account_number"] == "111005" for d in diffs)


# ── fetch_beancount_balances + run_validation end-to-end ─────────────

class TestFetchBeancountBalances:
    def test_reads_post_opening_balances(self, tmp_path):
        ledger = _bootstrap_ledger(tmp_path, {
            "Assets:EAG:Bancos:BancoBci-111005": 1000.0,
            "Liabilities:EAG:TC:Visa-215001": -500.0,
        })
        balances = fetch_beancount_balances(ledger, "2021-01-01")
        assert balances["Assets:EAG:Bancos:BancoBci-111005"] == 1000.0
        assert balances["Liabilities:EAG:TC:Visa-215001"] == -500.0


class TestRunValidation:
    def test_happy_path_zero_diffs(self, tmp_path, monkeypatch):
        ledger = _bootstrap_ledger(tmp_path, {
            "Assets:EAG:Bancos:BancoBci-111005": 1000.0,
            "Liabilities:EAG:TC:Visa-215001": -500.0,
        })
        reports = tmp_path / "bootstrap"
        monkeypatch.setattr(
            "bootstrap.validate_cuadratura.fetch_laudus_balance_sheet",
            lambda d: LAUDUS_FIXTURE,
        )
        rc = run_validation(ledger_path=ledger, reports_path=reports,
                            cutoffs=["2021-01-01"])
        assert rc == 0

    def test_mismatch_returns_2(self, tmp_path, monkeypatch):
        # Beancount tiene un saldo distinto del que dice Laudus
        ledger = _bootstrap_ledger(tmp_path, {
            "Assets:EAG:Bancos:BancoBci-111005": 999.0,  # off by 1
            "Liabilities:EAG:TC:Visa-215001": -500.0,
        })
        reports = tmp_path / "bootstrap"
        monkeypatch.setattr(
            "bootstrap.validate_cuadratura.fetch_laudus_balance_sheet",
            lambda d: LAUDUS_FIXTURE,
        )
        rc = run_validation(ledger_path=ledger, reports_path=reports,
                            cutoffs=["2021-01-01"])
        assert rc == 2
        # Reporte CSV escrito
        report = reports / "report-cuadratura-2021-01-01.csv"
        assert report.exists()
        assert "111005" in report.read_text(encoding="utf-8")
