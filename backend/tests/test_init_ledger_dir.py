"""Tests para bootstrap.init_ledger_dir — Story 9.1 Task 1."""
from pathlib import Path

from bootstrap.init_ledger_dir import (
    DIRS_TO_ENSURE,
    MAIN_TEMPLATE,
    PLACEHOLDERS,
    init_ledger,
)


class TestInitLedger:
    def test_creates_full_structure_from_empty(self, tmp_path):
        ledger = tmp_path / "ledger"
        summary = init_ledger(ledger)
        assert summary["rewrote_main"] is True
        for rel in DIRS_TO_ENSURE:
            assert (ledger / rel).is_dir(), f"missing dir: {rel}"
        for rel in PLACEHOLDERS:
            assert (ledger / rel).is_file(), f"missing placeholder: {rel}"
        assert (ledger / "main.beancount").is_file()
        assert (ledger / "accounts.beancount").is_file()

    def test_main_beancount_matches_template(self, tmp_path):
        ledger = tmp_path / "ledger"
        init_ledger(ledger)
        actual = (ledger / "main.beancount").read_text(encoding="utf-8")
        assert actual == MAIN_TEMPLATE
        # contenido clave esperado
        assert 'option "title" "LAUDUS — EAG Family Office"' in actual
        assert 'option "operating_currency" "CLP"' in actual
        assert 'plugin "beancount.plugins.implicit_prices"' in actual
        assert 'plugin "beancount.plugins.check_commodity"' in actual
        assert "1900-01-01 commodity CLP" in actual
        assert "1900-01-01 commodity USD" in actual
        assert 'custom "fava-extension" "fava_edit_validator"' in actual
        for inc in [
            'include "accounts.beancount"',
            'include "opening-2021.beancount"',
            'include "prices.beancount"',
            'include "imports/laudus/*.beancount"',
            'include "imports/cartolas/*.beancount"',
            'include "imports/_new-accounts-pending.beancount"',
            'include "manual/*.beancount"',
        ]:
            assert inc in actual, f"missing include: {inc}"

    def test_idempotent_does_not_overwrite_placeholders(self, tmp_path):
        ledger = tmp_path / "ledger"
        init_ledger(ledger)
        # Modifica un placeholder simulando trabajo del usuario
        opening = ledger / "opening-2021.beancount"
        opening.write_text(";; modified by user\n2021-01-01 open Equity:Test CLP\n",
                           encoding="utf-8")
        # Re-corre
        summary = init_ledger(ledger)
        assert summary["created_files"] == [], "idempotent run created files"
        assert summary["created_dirs"] == [], "idempotent run created dirs"
        # Placeholder modificado se conserva
        assert "modified by user" in opening.read_text(encoding="utf-8")

    def test_main_beancount_always_rewritten(self, tmp_path):
        ledger = tmp_path / "ledger"
        init_ledger(ledger)
        main_path = ledger / "main.beancount"
        main_path.write_text(";; tampered\n", encoding="utf-8")
        init_ledger(ledger)
        assert main_path.read_text(encoding="utf-8") == MAIN_TEMPLATE

    def test_creates_gitkeep_in_each_dir(self, tmp_path):
        ledger = tmp_path / "ledger"
        init_ledger(ledger)
        for rel in DIRS_TO_ENSURE:
            assert (ledger / rel / ".gitkeep").is_file(), f".gitkeep missing in {rel}"
