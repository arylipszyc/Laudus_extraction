"""Integración 9.6b — postings USD (AC8) + orquestador reconcile_and_build (AC1-AC9).

Renderiza las entries producidas y las carga con el loader de beancount (= bean-check) para
probar que balancean y que implicit_prices deriva la price USD.
"""
import json
from datetime import date
from decimal import Decimal

from beancount import loader
from beancount.core import data
from beancount.parser import printer

from pipeline.importers.cartola_pdf_importer import build_usd_postings
from pipeline.importers.matching_engine import CartolaLine, LaudusEntry
from pipeline.importers.reconcile import commit_reconciliation, reconcile_and_build

_LEDGER_HEADER = """\
option "operating_currency" "CLP"
plugin "beancount.plugins.implicit_prices"
1900-01-01 commodity CLP
1900-01-01 commodity USD
2020-01-01 open Liabilities:EAG:TC:Citi
2020-01-01 open Assets:EAG:Bancos:Banco
2020-01-01 open Expenses:EAG:Online
2020-01-01 open Equity:Reconciliation:Discrepancias
"""


def _load(entries) -> list:
    text = _LEDGER_HEADER + "\n" + "".join(printer.format_entry(e) for e in entries)
    _entries, errors, _opts = loader.load_string(text)
    return errors


# ── AC8: postings USD balancean + implicit_prices deriva price ───────────────


def test_usd_postings_balancean_y_derivan_price():
    postings = build_usd_postings(
        "Liabilities:EAG:TC:Citi", "Expenses:EAG:Online",
        usd_amount=Decimal("-100.00"), fx_implied=Decimal("950.45"), is_liability=True,
    )
    txn = data.Transaction(
        meta=data.new_metadata("<t>", 0), date=date(2026, 4, 15), flag="*", payee=None,
        narration="Amazon", tags=frozenset(), links=frozenset(), postings=postings,
    )
    text = _LEDGER_HEADER + "\n" + printer.format_entry(txn)
    entries, errors, _ = loader.load_string(text)
    assert errors == [], errors
    # implicit_prices deriva la price directive USD→CLP.
    assert any(isinstance(e, data.Price) and e.currency == "USD" for e in entries)


# ── AC1-AC9: orquestador end-to-end ──────────────────────────────────────────


def _fx_file(tmp_path):
    p = tmp_path / "fx-bcch-eom.jsonl"
    p.write_text(json.dumps({"year_month": "2026-04", "rate_clp_per_usd": 948.20}) + "\n", encoding="utf-8")
    return p


def test_reconcile_and_build_multi_estado(tmp_path):
    cartola = [
        CartolaLine(1, date(2026, 4, 10), Decimal("-45000"), "CLP", "JUMBO"),       # perfect
        CartolaLine(2, date(2026, 4, 12), Decimal("-30000"), "CLP", "FALABELLA"),   # value-mismatch (no emite)
        CartolaLine(3, date(2026, 4, 15), Decimal("-100.00"), "USD", "AMAZON"),     # USD perfect + FX
        CartolaLine(4, date(2026, 4, 20), Decimal("-9999"), "CLP", "DESCONOCIDO"),  # missing-in-laudus
    ]
    laudus = [
        LaudusEntry("J1", date(2026, 4, 10), Decimal("-45000"), "JUMBO", "Expenses:EAG:Online"),
        LaudusEntry("J2", date(2026, 4, 12), Decimal("-32000"), "FALABELLA", "Expenses:EAG:Online"),  # monto distinto
        LaudusEntry("J3", date(2026, 4, 15), Decimal("-95045"), "AMAZON", "Expenses:EAG:Online"),
    ]
    entries, discrepancies = reconcile_and_build(
        cartola_lines=cartola, laudus_entries=laudus, period_start=date(2026, 4, 1),
        account_target="Liabilities:EAG:TC:Citi", is_liability=True,
        category_for=lambda cl: "Expenses:EAG:Online",
        fx_jsonl_path=_fx_file(tmp_path), bank_slug="citi", year_month="2026-04",
        batch_id="b1", bank_account_id="acc1", ts="2026-05-05T00:00:00Z",
    )
    # value-mismatch NO se emite → 3 transactions (perfect, usd, missing-in-laudus).
    assert len([e for e in entries if isinstance(e, data.Transaction)]) == 3
    # discrepancias: value-mismatch + missing-in-laudus (perfect/usd-perfect no generan).
    states = sorted(d["state"] for d in discrepancies)
    assert states == ["missing-in-laudus", "value-mismatch"]
    # las entries renderizadas balancean (bean-check verde).
    assert _load(entries) == []


def test_pre_2026_clp_only_sin_fx(tmp_path):
    cartola = [CartolaLine(1, date(2024, 4, 15), Decimal("-100.00"), "USD", "AMAZON")]
    laudus = [LaudusEntry("J1", date(2024, 4, 15), Decimal("-95045"), "AMAZON", "Expenses:EAG:Online")]
    entries, discrepancies = reconcile_and_build(
        cartola_lines=cartola, laudus_entries=laudus, period_start=date(2024, 4, 1),
        account_target="Liabilities:EAG:TC:Citi", is_liability=True,
        category_for=lambda cl: "Expenses:EAG:Online",
        fx_jsonl_path=_fx_file(tmp_path), bank_slug="citi", year_month="2024-04",
        batch_id="b0", bank_account_id="acc1", ts="2026-05-05T00:00:00Z",
    )
    # Pre-2026: el "USD" se compara como monto CLP (100 vs 95045) → value-mismatch, no emite, sin FX.
    assert [d["state"] for d in discrepancies] == ["value-mismatch"]
    assert not any("fx_implied" in (getattr(e, "meta", {}) or {}) for e in entries)


# ── AC6: re-emit post-resolución (commit_reconciliation) ─────────────────────


def _ledger_root(tmp_path):
    """Ledger root mínimo: main incluye imports/cartolas/*.beancount + opens."""
    (tmp_path / "imports" / "cartolas").mkdir(parents=True)
    (tmp_path / "accounts.beancount").write_text(
        "2020-01-01 open Assets:EAG:Bancos:Banco CLP\n"
        "2020-01-01 open Expenses:EAG:Online CLP\n", encoding="utf-8")
    (tmp_path / "main.beancount").write_text(
        'option "operating_currency" "CLP"\n1900-01-01 commodity CLP\n'
        'include "accounts.beancount"\ninclude "imports/cartolas/*.beancount"\n', encoding="utf-8")
    return tmp_path


def test_commit_reconciliation_verde(tmp_path, monkeypatch):
    monkeypatch.delenv("IMPORTER_GIT_ENABLED", raising=False)
    root = _ledger_root(tmp_path)
    target = root / "imports" / "cartolas" / "citi-2026-04.beancount"
    content = ('2026-04-15 * "ajuste"\n'
               "  Assets:EAG:Bancos:Banco   1000 CLP\n"
               "  Expenses:EAG:Online      -1000 CLP\n")
    res = commit_reconciliation(target, content, "disc-1", "accept-cartola", root)
    assert res["success"] is True
    assert target.read_text(encoding="utf-8") == content


def test_commit_reconciliation_rojo_hace_rollback(tmp_path, monkeypatch):
    monkeypatch.delenv("IMPORTER_GIT_ENABLED", raising=False)
    root = _ledger_root(tmp_path)
    target = root / "imports" / "cartolas" / "citi-2026-04.beancount"
    # transacción desbalanceada → bean-check rojo → rollback (archivo no debe quedar)
    bad = '2026-04-15 * "rota"\n  Assets:EAG:Bancos:Banco   1000 CLP\n  Expenses:EAG:Online   -500 CLP\n'
    res = commit_reconciliation(target, bad, "disc-2", "x", root)
    assert res["success"] is False and "bean-check" in res["error_msg"]
    assert not target.exists()  # era nuevo → se borró en el rollback
