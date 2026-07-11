"""Tests para bootstrap.reconcile_rut2 — Story 12.5.

El fetch live (login RUT2 + balanceSheet/totals) NO se testea — se opera. Acá
se cubre la lógica pura: comparación cuenta-por-cuenta, scoping por entidad del
índice (ninguna cuenta EAG entra), y el aislamiento de codes colisionados.
"""
from textwrap import dedent

from bootstrap.reconcile_rut2 import (
    compare,
    fetch_beancount_rut2_balances,
    load_rut2_account_index,
)


# ── Fixtures ────────────────────────────────────────────────────────────

# Laudus RUT2 rows (signed = debitBalance - creditBalance).
LAUDUS_RUT2 = [
    {"accountNumber": "111005", "debitBalance": 1000.0, "creditBalance": 0.0},   # Assets FFCC
    {"accountNumber": "211005", "debitBalance": 0.0, "creditBalance": 700.0},    # Liab FFCC
    {"accountNumber": "111001", "debitBalance": 500.0, "creditBalance": 0.0},    # Assets JAB (via index)
]

# Índice scopeado a RUT2 (code normalizado → path).
RUT2_INDEX = {
    "111005": "Assets:FFCC:BancoBci28981162-111005",
    "211005": "Liabilities:FFCC:Apertura-211005",
    "111001": "Assets:JAB:Caja-111001",
}


# ── compare ─────────────────────────────────────────────────────────────

class TestCompare:
    def test_exact_match_zero_diffs(self):
        bc = {
            "Assets:FFCC:BancoBci28981162-111005": 1000.0,
            "Liabilities:FFCC:Apertura-211005": -700.0,
            "Assets:JAB:Caja-111001": 500.0,
        }
        assert compare(LAUDUS_RUT2, bc, RUT2_INDEX) == []

    def test_amount_mismatch_emits_one_diff(self):
        bc = {
            "Assets:FFCC:BancoBci28981162-111005": 999.0,  # off by 1
            "Liabilities:FFCC:Apertura-211005": -700.0,
            "Assets:JAB:Caja-111001": 500.0,
        }
        diffs = compare(LAUDUS_RUT2, bc, RUT2_INDEX)
        assert len(diffs) == 1
        assert diffs[0]["account_number"] == "111005"
        assert diffs[0]["diff"] == 1.0
        assert diffs[0]["reason"] == "amount_mismatch"

    def test_laudus_code_not_in_rut2_tree_is_routing_signal(self):
        # Laudus reporta un code con saldo que NO está en el árbol RUT2 → ruteo roto.
        laudus = LAUDUS_RUT2 + [
            {"accountNumber": "999999", "debitBalance": 42.0, "creditBalance": 0.0}]
        bc = {
            "Assets:FFCC:BancoBci28981162-111005": 1000.0,
            "Liabilities:FFCC:Apertura-211005": -700.0,
            "Assets:JAB:Caja-111001": 500.0,
        }
        diffs = compare(laudus, bc, RUT2_INDEX)
        assert [d for d in diffs if d["reason"] == "account_not_in_rut2_tree"] == [{
            "account_number": "999999", "path": "(not in RUT2 tree)",
            "laudus_clp": 42.0, "beancount_clp": 0.0, "diff": 42.0,
            "reason": "account_not_in_rut2_tree",
        }]

    def test_zero_balance_unmapped_row_is_ignored(self):
        # Fila rollup/inactiva con saldo 0 y sin path → no es discrepancia.
        laudus = LAUDUS_RUT2 + [
            {"accountNumber": "1", "debitBalance": 0.0, "creditBalance": 0.0}]
        bc = {
            "Assets:FFCC:BancoBci28981162-111005": 1000.0,
            "Liabilities:FFCC:Apertura-211005": -700.0,
            "Assets:JAB:Caja-111001": 500.0,
        }
        assert compare(laudus, bc, RUT2_INDEX) == []

    def test_trap3_code_13_matches_symmetrically_end_to_end(self):
        # TRAP #3: una fila Laudus con accountNumber "13" (no-padded) debe matchear
        # la cuenta "130000" del índice — la normalización es simétrica en compare().
        laudus = [{"accountNumber": "13", "debitBalance": 500.0, "creditBalance": 0.0}]
        index = {"130000": "Assets:FFCC:ActivosNoCorrientes-13"}
        bc = {"Assets:FFCC:ActivosNoCorrientes-13": 500.0}
        assert compare(laudus, bc, index) == []  # cuadra, no cae a account_not_in_rut2_tree

    def test_beancount_only_account_emitted(self):
        # Cuenta RUT2 con saldo en el ledger que Laudus no reporta (p.ej. plug Equity).
        bc = {
            "Assets:FFCC:BancoBci28981162-111005": 1000.0,
            "Liabilities:FFCC:Apertura-211005": -700.0,
            "Assets:JAB:Caja-111001": 500.0,
            "Equity:FFCC:Apertura": -123.0,
        }
        index = {**RUT2_INDEX, "900001": "Equity:FFCC:Apertura"}
        diffs = compare(LAUDUS_RUT2, bc, index)
        assert len(diffs) == 1
        assert diffs[0]["reason"] == "beancount_only"
        assert diffs[0]["path"] == "Equity:FFCC:Apertura"
        assert diffs[0]["account_number"] == "900001"
        assert diffs[0]["diff"] == 123.0


# ── load_rut2_account_index — scoping por entidad ────────────────────────

def _accounts_file(tmp_path):
    """accounts.beancount mixto EAG + RUT2 con un code colisionado (111005)."""
    accounts = tmp_path / "accounts.beancount"
    accounts.write_text(dedent('''\
        2020-12-31 open Assets:EAG:Bancos:BancoBci-111005 CLP
          code: "111005"
        2020-12-31 open Assets:FFCC:BancoBci28981162-111005 CLP
          code: "111005"
        2020-12-31 open Assets:JAB:Caja-111001 CLP
          code: "111001"
        2020-12-31 open Assets:EAG:Bancos:BancoSolo-222222 CLP
          code: "222222"
        2020-12-31 open Assets:FFCC:ActivosNoCorrientes-13 CLP
          code: "13"
    '''), encoding="utf-8")
    return accounts


class TestLoadRut2AccountIndex:
    def test_only_rut2_entities_indexed(self, tmp_path):
        index = load_rut2_account_index(_accounts_file(tmp_path))
        # code colisionado 111005 resuelve a la cuenta RUT2 (FFCC), NO a la de EAG.
        assert index["111005"] == "Assets:FFCC:BancoBci28981162-111005"
        assert index["111001"] == "Assets:JAB:Caja-111001"

    def test_eag_only_code_absent(self, tmp_path):
        index = load_rut2_account_index(_accounts_file(tmp_path))
        # 222222 solo existe en EAG → NO se mapea a RUT2 (scoping por entidad).
        assert "222222" not in index

    def test_code_13_normalized_symmetrically(self, tmp_path):
        index = load_rut2_account_index(_accounts_file(tmp_path))
        # "13" se normaliza a "130000" (TRAP #3) — el lado Laudus se normaliza igual.
        assert index["130000"] == "Assets:FFCC:ActivosNoCorrientes-13"


# ── fetch_beancount_rut2_balances — scoping en el BQL ────────────────────

class TestFetchBeancountRut2Balances:
    def test_excludes_eag_accounts(self, tmp_path):
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        (ledger / "main.beancount").write_text(dedent('''\
            option "operating_currency" "CLP"
            1900-01-01 commodity CLP
            include "accounts.beancount"
            include "opening.beancount"
        '''), encoding="utf-8")
        (ledger / "accounts.beancount").write_text(dedent('''\
            2020-12-31 open Assets:EAG:Bancos:BancoBci-111005 CLP
            2020-12-31 open Assets:FFCC:BancoBci28981162-111005 CLP
            2020-12-31 open Equity:EAG:OpeningBalances CLP
            2020-12-31 open Equity:FFCC:Apertura CLP
        '''), encoding="utf-8")
        (ledger / "opening.beancount").write_text(dedent('''\
            2021-01-01 * "seed"
              Assets:EAG:Bancos:BancoBci-111005   9000 CLP
              Equity:EAG:OpeningBalances

            2021-01-02 * "seed rut2"
              Assets:FFCC:BancoBci28981162-111005  1000 CLP
              Equity:FFCC:Apertura
        '''), encoding="utf-8")
        balances = fetch_beancount_rut2_balances(ledger, "2026-06-30")
        assert balances["Assets:FFCC:BancoBci28981162-111005"] == 1000.0
        assert balances["Equity:FFCC:Apertura"] == -1000.0
        # Ninguna cuenta EAG entra en el scope RUT2.
        assert not any(":EAG:" in a for a in balances)
