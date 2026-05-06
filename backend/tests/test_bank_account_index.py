"""Tests for BankAccountIndex — Story 9.5 Task 4."""
from pathlib import Path

import pytest

from backend.app.integrations.bank_account_index import (
    BankAccountIndex,
    _resolve_entity,
)


# ── _resolve_entity (architecture-c4 §2.3 mapping table) ─────────────────


@pytest.mark.parametrize(
    "categoria1, expected_entity",
    [
        ("ACTIVO EAG", "EAG"),
        ("PASIVO", "EAG"),
        ("INGRESOS", "EAG"),
        ("GASTOS - EGRESOS", "EAG"),
        ("DISPONIBLE Jocelyn", "Jocelyn"),
        ("EGRESOS Jeannette", "Jeannette"),
        ("INGRESOS Johanna", "Johanna"),
        ("DISPONIBLE Jael", "Jael"),
    ],
)
def test_resolve_entity_known_categorias(categoria1, expected_entity):
    assert _resolve_entity(categoria1) == expected_entity


def test_resolve_entity_returns_none_for_unknown():
    assert _resolve_entity("UNKNOWN_CATEGORIA") is None


def test_resolve_entity_returns_none_for_empty():
    assert _resolve_entity(None) is None
    assert _resolve_entity("") is None


# ── Index against minimal fixture file ────────────────────────────────────


_FIXTURE = """
2020-12-31 open Assets:EAG:Bancos:Bci-111005 CLP
  code: "111005"
  laudus_account_name: "Banco BCI - 10160175"
  laudus_categoria1: "ACTIVO EAG"
  bank_account_id: "uuid-bci-clp"
  bank_name: "BCI"
  bank_account_type: "cta_corriente"
  bank_account_currency: "CLP"
  bank_account_last4: "0175"

2020-12-31 open Assets:Jocelyn:Bancos:Santander-211005 CLP
  laudus_account_name: "Santander - Jocelyn"
  laudus_categoria1: "DISPONIBLE Jocelyn"
  bank_account_id: "uuid-santander-jocelyn"
  bank_name: "Santander"
  bank_account_type: "cta_corriente"
  bank_account_currency: "CLP"

2020-12-31 open Liabilities:EAG:TC:Visa-VisaInfinityEduardo CLP
  laudus_account_name: "Visa Infinity Eduardo"
  laudus_categoria1: "PASIVO"
  bank_account_id: "uuid-visa-eduardo"
  bank_name: "BCI"
  bank_account_type: "tarjeta_credito"
  bank_account_currency: "CLP"
  bank_account_last4: "1234"

2020-12-31 open Assets:EAG:Caja-111001 CLP
  code: "111001"
  laudus_account_name: "Caja $"
  laudus_categoria1: "ACTIVO EAG"
"""


def _write_fixture(tmp_path: Path) -> Path:
    f = tmp_path / "accounts.beancount"
    f.write_text(_FIXTURE.strip() + "\n", encoding="utf-8")
    return f


def test_index_loads_only_entries_with_bank_account_id(tmp_path):
    idx = BankAccountIndex(_write_fixture(tmp_path))
    accounts = idx.list_active()
    # Caja (no bank_account_id) is excluded.
    assert {a.bank_account_id for a in accounts} == {
        "uuid-bci-clp", "uuid-santander-jocelyn", "uuid-visa-eduardo"
    }


def test_index_resolves_entity_per_mapping_table(tmp_path):
    idx = BankAccountIndex(_write_fixture(tmp_path))
    assert idx.get("uuid-bci-clp").entity == "EAG"
    assert idx.get("uuid-santander-jocelyn").entity == "Jocelyn"
    assert idx.get("uuid-visa-eduardo").entity == "EAG"


def test_index_exposes_full_metadata(tmp_path):
    idx = BankAccountIndex(_write_fixture(tmp_path))
    e = idx.get("uuid-bci-clp")
    assert e is not None
    assert e.bank_name == "BCI"
    assert e.account_label == "Banco BCI - 10160175"
    assert e.account_type == "cta_corriente"
    assert e.currency == "CLP"
    assert e.last4 == "0175"
    assert e.beancount_account == "Assets:EAG:Bancos:Bci-111005"


def test_index_last4_is_none_when_missing(tmp_path):
    idx = BankAccountIndex(_write_fixture(tmp_path))
    assert idx.get("uuid-santander-jocelyn").last4 is None


def test_get_unknown_id_returns_none(tmp_path):
    idx = BankAccountIndex(_write_fixture(tmp_path))
    assert idx.get("does-not-exist") is None


def test_index_reloads_on_mtime_change(tmp_path):
    f = _write_fixture(tmp_path)
    idx = BankAccountIndex(f)
    assert len(idx.list_active()) == 3

    # Append a new bank account and force mtime forward.
    new_entry = """

2020-12-31 open Assets:EAG:Bancos:Chile-NEW CLP
  laudus_categoria1: "ACTIVO EAG"
  laudus_account_name: "Banco Chile NEW"
  bank_account_id: "uuid-new"
  bank_name: "Banco Chile"
  bank_account_type: "cta_corriente"
  bank_account_currency: "CLP"
"""
    import os
    f.write_text(f.read_text() + new_entry, encoding="utf-8")
    # Bump mtime explicitly (Windows file systems can repeat mtime within same second).
    new_mtime = f.stat().st_mtime + 1
    os.utime(f, (new_mtime, new_mtime))

    assert len(idx.list_active()) == 4
    assert idx.get("uuid-new").bank_name == "Banco Chile"


def test_reload_force_returns_count(tmp_path):
    idx = BankAccountIndex(_write_fixture(tmp_path))
    assert idx.reload() == 3


def test_missing_file_raises(tmp_path):
    idx = BankAccountIndex(tmp_path / "does-not-exist.beancount")
    with pytest.raises(RuntimeError, match="not found"):
        idx.list_active()


def test_real_accounts_beancount_loads():
    """Smoke test against the real ledger — verifies the loader mechanics, not
    data completeness. Story 9.3 AC8 has Ary populating bank_name + last4 via
    Fava as an operational pre-condition; this index must work even when those
    are empty (the upload endpoint short-circuits with MISSING_LAST4)."""
    real = Path(__file__).resolve().parents[2] / "ledger" / "accounts.beancount"
    if not real.exists():
        pytest.skip("ledger/accounts.beancount not present in this checkout")
    idx = BankAccountIndex(real)
    accounts = idx.list_active()
    # Story 9.1 bootstrapped 47 bank accounts; we tolerate +/- 5 to absorb
    # later admin-inserted entries without the test going stale.
    assert 40 <= len(accounts) <= 60
    # Every entry must at least have an account_label and beancount_account.
    for a in accounts:
        assert a.account_label, f"missing label for {a.bank_account_id}"
        assert a.beancount_account, f"missing beancount account for {a.bank_account_id}"
