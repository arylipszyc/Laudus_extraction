"""Tests para bootstrap.generate_opening_balances — Story 9.1 Task 3."""
from textwrap import dedent

import pytest

from bootstrap.generate_opening_balances import (
    OpeningBalanceError,
    load_account_index,
    render_opening_beancount,
    run_opening_bootstrap,
    signed_balance,
)


# ── Fixtures ────────────────────────────────────────────────────────────

LAUDUS_BALANCE_FIXTURE = [
    # Asset con saldo deudor
    {"accountId": 273, "accountNumber": "111005", "accountName": "Banco BCI",
     "debit": 20309785.0, "credit": 0.0,
     "debitBalance": 20309785.0, "creditBalance": 0.0},
    # Liability con saldo acreedor (TC)
    {"accountId": 500, "accountNumber": "215001", "accountName": "VISA Infinity",
     "debit": 0.0, "credit": 1500000.0,
     "debitBalance": 0.0, "creditBalance": 1500000.0},
    # Cuenta con saldo cero — debe filtrarse
    {"accountId": 999, "accountNumber": "413044", "accountName": "Combustible",
     "debit": 0.0, "credit": 0.0,
     "debitBalance": 0.0, "creditBalance": 0.0},
]

ACCOUNTS_BEANCOUNT_FIXTURE = dedent('''\
    1900-01-01 commodity CLP
    1900-01-01 commodity USD

    2021-01-01 open Assets:EAG:Bancos:BancoBci-111005 CLP
      code: "111005"
    2021-01-01 open Liabilities:EAG:TC:VisaInfinity-215001 CLP, USD
      code: "215001"
    2021-01-01 open Expenses:EAG:Combustible-413044 CLP
      code: "413044"
''')


# ── signed_balance ──────────────────────────────────────────────────────

class TestSignedBalance:
    def test_asset_positive(self):
        assert signed_balance(LAUDUS_BALANCE_FIXTURE[0]) == 20309785.0

    def test_liability_negative(self):
        assert signed_balance(LAUDUS_BALANCE_FIXTURE[1]) == -1500000.0

    def test_zero_when_both_sides_match(self):
        assert signed_balance({"debitBalance": 100.0, "creditBalance": 100.0}) == 0.0


# ── load_account_index ─────────────────────────────────────────────────

class TestLoadAccountIndex:
    def test_extracts_code_metadata(self, tmp_path):
        accounts = tmp_path / "accounts.beancount"
        accounts.write_text(ACCOUNTS_BEANCOUNT_FIXTURE, encoding="utf-8")
        idx = load_account_index(accounts)
        assert idx["111005"] == "Assets:EAG:Bancos:BancoBci-111005"
        assert idx["215001"] == "Liabilities:EAG:TC:VisaInfinity-215001"
        assert idx["413044"] == "Expenses:EAG:Combustible-413044"
        assert len(idx) == 3


# ── render_opening_beancount ───────────────────────────────────────────

class TestRenderOpening:
    def _index(self):
        return {
            "111005": "Assets:EAG:Bancos:BancoBci-111005",
            "215001": "Liabilities:EAG:TC:VisaInfinity-215001",
            "413044": "Expenses:EAG:Combustible-413044",
        }

    def test_emits_equity_open_first(self):
        text = render_opening_beancount(LAUDUS_BALANCE_FIXTURE, self._index())
        # Equity y pads van al día previo (2020-12-31) — Beancount exige
        # pad-date < balance-date para emparejarlos.
        assert "2020-12-31 open Equity:EAG:OpeningBalances CLP, USD" in text

    def test_skips_zero_balances(self):
        text = render_opening_beancount(LAUDUS_BALANCE_FIXTURE, self._index())
        # 413044 tiene saldo 0 — no debe aparecer en pad/balance
        lines = [ln for ln in text.splitlines() if "413044" in ln]
        assert lines == [], f"saldo cero leakeó: {lines}"

    def test_emits_pad_and_balance_for_nonzero(self):
        text = render_opening_beancount(LAUDUS_BALANCE_FIXTURE, self._index())
        assert "2020-12-31 pad Assets:EAG:Bancos:BancoBci-111005 Equity:EAG:OpeningBalances" in text
        assert "2021-01-01 balance Assets:EAG:Bancos:BancoBci-111005 20309785.00 CLP" in text
        assert "2020-12-31 pad Liabilities:EAG:TC:VisaInfinity-215001 Equity:EAG:OpeningBalances" in text
        assert "2021-01-01 balance Liabilities:EAG:TC:VisaInfinity-215001 -1500000.00 CLP" in text

    def test_includes_source_je_metadata(self):
        text = render_opening_beancount(LAUDUS_BALANCE_FIXTURE, self._index())
        assert 'source_je: "140"' in text

    def test_raises_when_account_not_in_index(self):
        bad_index = {"413044": "Expenses:EAG:Combustible-413044"}  # falta 111005, 215001
        with pytest.raises(OpeningBalanceError, match="cuentas con saldo"):
            render_opening_beancount(LAUDUS_BALANCE_FIXTURE, bad_index)

    def test_sorts_balances_by_account_number(self):
        text = render_opening_beancount(LAUDUS_BALANCE_FIXTURE, self._index())
        i111 = text.index("111005")
        i215 = text.index("215001")
        assert i111 < i215


# ── run_opening_bootstrap end-to-end ──────────────────────────────────

class TestRunOpeningBootstrap:
    def test_happy_path(self, tmp_path):
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        (ledger / "accounts.beancount").write_text(
            ACCOUNTS_BEANCOUNT_FIXTURE, encoding="utf-8"
        )
        rc = run_opening_bootstrap(
            ledger_path=ledger,
            laudus_balances=LAUDUS_BALANCE_FIXTURE,
        )
        assert rc == 0
        out = (ledger / "opening-2021.beancount").read_text(encoding="utf-8")
        assert "Equity:EAG:OpeningBalances CLP, USD" in out
        assert "20309785.00 CLP" in out
        assert "-1500000.00 CLP" in out

    def test_missing_accounts_beancount_returns_3(self, tmp_path):
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        rc = run_opening_bootstrap(
            ledger_path=ledger, laudus_balances=LAUDUS_BALANCE_FIXTURE,
        )
        assert rc == 3

    def test_account_with_balance_not_opened_returns_2(self, tmp_path):
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        # accounts.beancount existe pero no tiene 111005 (la cuenta con saldo)
        (ledger / "accounts.beancount").write_text(
            dedent('''\
                1900-01-01 commodity CLP
                2021-01-01 open Expenses:EAG:Other-999999 CLP
                  code: "999999"
            '''),
            encoding="utf-8",
        )
        rc = run_opening_bootstrap(
            ledger_path=ledger, laudus_balances=LAUDUS_BALANCE_FIXTURE,
        )
        assert rc == 2
        # opening-2021.beancount NO se escribe
        assert not (ledger / "opening-2021.beancount").exists()
