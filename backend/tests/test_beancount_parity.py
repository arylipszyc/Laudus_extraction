"""Sheets ↔ Beancount parity suite — Story 9.2 AC9.

Two layers:
  1. STRUCTURAL parity (runs now): the Beancount engine emits exactly the keys
     the Sheets path / Pydantic models expect — the frontend cannot tell engines
     apart. This is enforceable today against the synthetic mini-ledger.
  2. VALUE parity (xfail): amount-for-amount comparison vs. the real Laudus-derived
     Sheets data. Cannot run until the ledger is fully bootstrapped by the Laudus
     importer (Story 9.4). See tests/README-beancount-parity.md.

Marked `beancount_parity` so CI can run/skip this suite independently.
"""
import pytest

from backend.app.api.v1.dashboard.schemas import BalanceSheetRecord, LedgerEntryRecord
from backend.app.services.bql_queries import (
    balance_sheet_via_beancount,
    ledger_entries_via_beancount,
)
from backend.app.services.ledger_service import LedgerService
from backend.tests.test_bql_queries import MINI_LEDGER

pytestmark = pytest.mark.beancount_parity


def _ledger(tmp_path):
    main = tmp_path / "main.beancount"
    main.write_text(MINI_LEDGER, encoding="utf-8")
    return LedgerService(str(main))


# ── Layer 1: structural parity (enforceable now) ──────────────────────────────


def test_balance_sheet_keys_match_model(tmp_path):
    """Beancount balance-sheet keys == BalanceSheetRecord field names."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "EAG")
    model_fields = set(BalanceSheetRecord.model_fields.keys())
    for record in result["data"]:
        assert set(record.keys()) == model_fields
        # And the record must actually validate against the API model.
        BalanceSheetRecord(**record)


def test_ledger_entry_keys_validate_against_model(tmp_path):
    """Beancount ledger records validate against LedgerEntryRecord (alias-keyed)."""
    result = ledger_entries_via_beancount(_ledger(tmp_path), "EAG")
    assert result["data"]
    for record in result["data"]:
        # populate_by_name + alias keys → must construct without error.
        LedgerEntryRecord(**record)


# ── Layer 2: value parity vs. real Sheets data (deferred) ─────────────────────


@pytest.mark.xfail(
    reason="Requires full ledger bootstrap via the Laudus importer (Story 9.4). "
           "See tests/README-beancount-parity.md.",
    strict=False,
)
def test_value_parity_balance_sheet_vs_sheets():
    """Amount-for-amount parity vs. the Laudus-derived Sheets balance sheet.

    Intentionally fails until a bootstrapped ledger + a Sheets snapshot exist to
    compare. The structural contract above is what guards the frontend today.
    """
    raise AssertionError("No bootstrapped ledger available to compare yet.")
