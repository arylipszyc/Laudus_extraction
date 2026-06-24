"""Story 6.4 — listado del plan de cuentas (autocompletado de categoría) + moneda Laudus."""
from datetime import date
from decimal import Decimal

from beancount.parser import parser

from backend.app.api.v1.accounts.service import list_accounts
from pipeline.importers.matching_engine import load_laudus_entries

_ACCOUNTS = """\
2020-12-31 open Expenses:EAG:Super CLP
2020-12-31 open Expenses:EAG:Servicios:Luz CLP
2020-12-31 open Income:EAG:Intereses CLP
2020-12-31 open Assets:EAG:Bancos:Cta-100 CLP
2020-12-31 open Assets:EAG:PendingReview:Cuenta-999 CLP
"""


def _entries(tmp_path):
    p = tmp_path / "accounts.beancount"
    p.write_text(_ACCOUNTS, encoding="utf-8")
    entries, _err, _opt = parser.parse_file(str(p))
    return entries


def test_list_accounts_filtra_por_root_y_excluye_cuarentena(tmp_path):
    entries = _entries(tmp_path)
    expenses = list_accounts(entries, "Expenses")
    assert expenses == ["Expenses:EAG:Servicios:Luz", "Expenses:EAG:Super"]  # ordenadas, sin Income/Assets


def test_list_accounts_root_assets_excluye_pendingreview(tmp_path):
    entries = _entries(tmp_path)
    assets = list_accounts(entries, "Assets")
    assert assets == ["Assets:EAG:Bancos:Cta-100"]  # PendingReview excluida


def test_list_accounts_root_inexistente_da_vacio(tmp_path):
    assert list_accounts(_entries(tmp_path), "Liabilities") == []


# ── Moneda Laudus (AC7): load_laudus_entries la captura de la posting ──────────


def test_load_laudus_entries_captura_currency(tmp_path):
    laudus_dir = tmp_path / "laudus"
    laudus_dir.mkdir()
    (laudus_dir / "2026-04.beancount").write_text(
        '2026-04-10 * "COMPRA USD"\n'
        '  Assets:EAG:Bancos:Us  -42.75 USD\n'
        '  Expenses:EAG:Super  42.75 USD\n', encoding="utf-8")
    out = load_laudus_entries(laudus_dir, "Assets:EAG:Bancos:Us", date(2026, 4, 1), date(2026, 4, 30))
    assert len(out) == 1
    assert out[0].currency == "USD"
    assert out[0].amount == Decimal("-42.75")
