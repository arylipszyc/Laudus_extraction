"""Tests for CartolaPdfImporter — Story 9.6a AC1-AC9."""
import json
from decimal import Decimal

import pytest
from beancount import loader
from beancount.core import data

from pipeline.importers.bank_account_resolver import BankAccountResolver, UnknownBankAccount
from pipeline.importers.cartola_pdf_importer import (
    CartolaPdfImporter,
    _build_postings,
    convert_balance_to_pad,
    promote,
    render_entries,
)
from pipeline.importers.category_predictor import NoopCategoryPredictor

TC_ID = "e919b1db-be7d-430c-9f40-60fc58ae2bcb"
ASSET_ID = "d844c24e-e5da-41c6-8734-039424f13613"

# Mini accounts: one TC (Liability) + one checking (Asset) + system accounts.
MINI_ACCOUNTS = """\
2020-12-31 open Liabilities:EAG:TC:VisaInfinity-430005 CLP
  bank_account_id: "e919b1db-be7d-430c-9f40-60fc58ae2bcb"
  bank_account_type: "tarjeta_credito"
  bank_account_currency: "CLP"
  bank_account_last4: "1027"
  bank_name: "Banco BCI"
2020-12-31 open Assets:EAG:Bancos:BancoBci-111005 CLP
  bank_account_id: "d844c24e-e5da-41c6-8734-039424f13613"
  bank_account_type: "cta_corriente"
  bank_account_currency: "CLP"
  bank_account_last4: "0175"
  bank_name: "Banco BCI"
2020-12-31 open Expenses:EAG:Suspense CLP, USD
2020-12-31 open Equity:Reconciliation:Discrepancias CLP, USD
"""


def _accounts(tmp_path):
    p = tmp_path / "accounts.beancount"
    p.write_text(MINI_ACCOUNTS, encoding="utf-8")
    return p


def _importer(tmp_path):
    return CartolaPdfImporter(BankAccountResolver(_accounts(tmp_path)), NoopCategoryPredictor())


def _cartola(bank_account_id, account_type, transactions, opening="0", closing=None,
             bank_name="Banco BCI", entity="EAG"):
    if closing is None:
        closing = str(sum(Decimal(str(t[1])) for t in transactions) + Decimal(opening))
    return {
        "schema_version": "1.0",
        "source": {"bank_account_id": bank_account_id, "bank_name": bank_name,
                   "account_label": "x", "account_type": account_type, "entity": entity},
        "period": {"start": "2026-03-01", "end": "2026-03-31"},
        "currency": "CLP",
        "balances": {"opening": opening, "closing": closing},
        "transactions": [
            {"line_no": i + 1, "date": "2026-03-15", "description": d, "amount": str(a), "currency": "CLP", "raw": {}}
            for i, (d, a) in enumerate(transactions)
        ],
        "extraction": {"model": "gemini-3.5-flash", "extracted_at": "2026-04-01T10:00:00Z", "warnings": []},
    }


def _write_cartola(tmp_path, payload, batch_id="batch1"):
    staging = tmp_path / "imports" / "cartolas" / "_staging"
    staging.mkdir(parents=True, exist_ok=True)
    f = staging / f"{batch_id}.cartola.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    return f


# ── AC4: _build_postings sign convention ─────────────────────────────────────


def test_postings_asset_outflow():
    p = _build_postings("Assets:EAG:Bancos:X-1", "Expenses:EAG:C", Decimal("-45000"), "CLP", is_liability=False)
    assert p[0].units == data.Amount(Decimal("-45000"), "CLP")   # asset down
    assert p[1].units == data.Amount(Decimal("45000"), "CLP")    # expense up


def test_postings_asset_inflow():
    p = _build_postings("Assets:EAG:Bancos:X-1", "Income:EAG:C", Decimal("1000"), "CLP", is_liability=False)
    assert p[0].units == data.Amount(Decimal("1000"), "CLP")     # asset up
    assert p[1].units == data.Amount(Decimal("-1000"), "CLP")    # income (negative)


def test_postings_liability_charge():
    # statement-natural: a charge is POSITIVE; beancount debt grows = more negative.
    p = _build_postings("Liabilities:EAG:TC:X-1", "Expenses:EAG:C", Decimal("382282"), "CLP", is_liability=True)
    assert p[0].units == data.Amount(Decimal("-382282"), "CLP")  # debt grows (more negative)
    assert p[1].units == data.Amount(Decimal("382282"), "CLP")   # expense up


def test_postings_liability_payment():
    p = _build_postings("Liabilities:EAG:TC:X-1", "Expenses:EAG:Suspense", Decimal("-2054314"), "CLP", is_liability=True)
    assert p[0].units == data.Amount(Decimal("2054314"), "CLP")   # debt shrinks
    assert p[1].units == data.Amount(Decimal("-2054314"), "CLP")


def test_postings_always_balance():
    for amt, liab in [("-45000", False), ("1000", False), ("382282", True), ("-2054314", True)]:
        p = _build_postings("X:A", "Y:B", Decimal(amt), "CLP", liab)
        assert p[0].units.number + p[1].units.number == 0


# ── AC1: identify ────────────────────────────────────────────────────────────


def test_identify_accepts_valid(tmp_path):
    imp = _importer(tmp_path)
    f = _write_cartola(tmp_path, _cartola(ASSET_ID, "cta_corriente", [("Compra", -45000)]))
    assert imp.identify(str(f)) is True


def test_identify_rejects_wrong_extension(tmp_path):
    imp = _importer(tmp_path)
    f = tmp_path / "x.json"
    f.write_text('{"schema_version": "1.0"}', encoding="utf-8")
    assert imp.identify(str(f)) is False


def test_identify_rejects_bad_schema_version(tmp_path):
    imp = _importer(tmp_path)
    f = tmp_path / "x.cartola.json"
    f.write_text('{"schema_version": "2.0"}', encoding="utf-8")
    assert imp.identify(str(f)) is False


# ── AC2: account resolution ──────────────────────────────────────────────────


def test_account_resolves_via_accounts_beancount(tmp_path):
    imp = _importer(tmp_path)
    f = _write_cartola(tmp_path, _cartola(TC_ID, "tarjeta_credito", [("Compra", 5000)]))
    assert imp.account(str(f)) == "Liabilities:EAG:TC:VisaInfinity-430005"


def test_resolver_unknown_id_raises(tmp_path):
    resolver = BankAccountResolver(_accounts(tmp_path))
    with pytest.raises(UnknownBankAccount):
        resolver.resolve("does-not-exist")


# ── AC3: extract emits N transactions + 1 Balance ────────────────────────────


def test_extract_emits_transactions_and_balance(tmp_path):
    imp = _importer(tmp_path)
    f = _write_cartola(tmp_path, _cartola(ASSET_ID, "cta_corriente",
                                          [("Compra A", -45000), ("Pago B", 1000)]))
    entries = imp.extract(str(f))
    txns = [e for e in entries if isinstance(e, data.Transaction)]
    balances = [e for e in entries if isinstance(e, data.Balance)]
    assert len(txns) == 2
    assert len(balances) == 1
    t = txns[0]
    assert t.flag == "!"                       # noop predictor → pending
    assert t.narration == "Compra A"
    assert t.meta["source"] == "cartola-pdf"
    assert t.meta["bank_account_id"] == ASSET_ID
    assert t.meta["match_source"] == "pending"
    assert t.meta["extraction_model"] == "gemini-3.5-flash"
    assert t.meta["line"] == "1"


def test_extract_balance_date_and_sign_liability(tmp_path):
    imp = _importer(tmp_path)
    # TC: opening 0, charges 382282 + 852689, closing = 1234971 (statement positive).
    f = _write_cartola(tmp_path, _cartola(TC_ID, "tarjeta_credito",
                                          [("ENEL", 852689), ("COLMENA", 382282)], opening="0"))
    entries = imp.extract(str(f))
    bal = next(e for e in entries if isinstance(e, data.Balance))
    assert str(bal.date) == "2026-04-01"                    # period.end + 1
    assert bal.account == "Liabilities:EAG:TC:VisaInfinity-430005"
    assert bal.amount == data.Amount(Decimal("-1234971"), "CLP")  # -closing


# ── AC5: bean-check passes on a real-shaped cartola ──────────────────────────


def test_extracted_entries_pass_bean_check(tmp_path):
    imp = _importer(tmp_path)
    # Real BCI TC math: opening 0, charges summing to closing.
    txs = [("ENEL", 852689), ("COLMENA", 382282), ("PAGO PAC", -100000)]
    f = _write_cartola(tmp_path, _cartola(TC_ID, "tarjeta_credito", txs, opening="0"))
    entries = imp.extract(str(f))

    out = tmp_path / "imports" / "cartolas" / "out.beancount"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_entries(entries), encoding="utf-8")
    main = tmp_path / "main.beancount"
    main.write_text(
        'option "operating_currency" "CLP"\n1900-01-01 commodity CLP\n'
        'include "accounts.beancount"\ninclude "imports/cartolas/out.beancount"\n',
        encoding="utf-8",
    )
    _e, errors, _o = loader.load_file(str(main))
    assert errors == []


# ── AC7: idempotency ─────────────────────────────────────────────────────────


def test_render_is_idempotent(tmp_path):
    imp = _importer(tmp_path)
    f = _write_cartola(tmp_path, _cartola(ASSET_ID, "cta_corriente", [("Compra", -45000)]))
    assert render_entries(imp.extract(str(f))) == render_entries(imp.extract(str(f)))


# ── AC6: override Balance → pad + balance ────────────────────────────────────


def test_convert_balance_to_pad(tmp_path):
    imp = _importer(tmp_path)
    f = _write_cartola(tmp_path, _cartola(TC_ID, "tarjeta_credito", [("X", 5000)], opening="0"))
    entries = imp.extract(str(f))
    converted = convert_balance_to_pad(entries, "Cartola cortada", "contador@ammy.cl", "2026-05-01T10:30:00Z")
    pads = [e for e in converted if isinstance(e, data.Pad)]
    assert len(pads) == 1
    assert pads[0].source_account == "Equity:Reconciliation:Discrepancias"
    assert pads[0].meta["override_justification"] == "Cartola cortada"
    assert pads[0].meta["override_user"] == "contador@ammy.cl"
    # pad precedes balance
    assert isinstance(converted[-1], data.Balance)
    assert isinstance(converted[-2], data.Pad)


# ── AC8: promotion ───────────────────────────────────────────────────────────


def test_promote_writes_file_and_removes_staging(tmp_path):
    # Build a self-contained ledger root.
    root = tmp_path
    (root / "imports" / "cartolas").mkdir(parents=True, exist_ok=True)
    _accounts(root)
    (root / "main.beancount").write_text(
        'option "operating_currency" "CLP"\n1900-01-01 commodity CLP\n'
        'include "accounts.beancount"\ninclude "imports/cartolas/*.beancount"\n',
        encoding="utf-8",
    )
    # placeholder so the glob is non-empty before promotion
    (root / "imports" / "cartolas" / "_init.beancount").write_text(";; init\n", encoding="utf-8")

    imp = CartolaPdfImporter(BankAccountResolver(root / "accounts.beancount"), NoopCategoryPredictor())
    staging = _write_cartola(root, _cartola(TC_ID, "tarjeta_credito",
                                            [("ENEL", 852689), ("PAGO", -100000)], opening="0"), batch_id="b9")

    result = promote("b9", imp, root)
    assert result["success"] is True
    assert result["tx"] == 2
    assert not staging.exists()                       # staging removed
    out_files = list((root / "imports" / "cartolas").glob("BancoBci-1027-2026-03.beancount"))
    assert len(out_files) == 1


def test_promote_re_import_bean_check_rojo_restaura_archivo_previo(tmp_path):
    """Fix review 2026-07-06 (B3): re-import con mismo slug sobrescribe el archivo; si
    bean-check falla (ej. un sibling roto), el contenido BUENO previo debe restaurarse —
    antes se hacía unlink y desaparecía la cartola ya importada."""
    root = tmp_path
    (root / "imports" / "cartolas").mkdir(parents=True, exist_ok=True)
    _accounts(root)
    (root / "main.beancount").write_text(
        'option "operating_currency" "CLP"\n1900-01-01 commodity CLP\n'
        'include "accounts.beancount"\ninclude "imports/cartolas/*.beancount"\n',
        encoding="utf-8",
    )
    (root / "imports" / "cartolas" / "_init.beancount").write_text(";; init\n", encoding="utf-8")

    imp = CartolaPdfImporter(BankAccountResolver(root / "accounts.beancount"), NoopCategoryPredictor())
    _write_cartola(root, _cartola(TC_ID, "tarjeta_credito",
                                  [("ENEL", 852689), ("PAGO", -100000)], opening="0"), batch_id="b9")
    r1 = promote("b9", imp, root)
    assert r1["success"] is True
    out_file = next((root / "imports" / "cartolas").glob("BancoBci-1027-2026-03.beancount"))
    good_content = out_file.read_text(encoding="utf-8")

    # Sibling ROTO → el próximo bean-check del ledger completo falla. El re-import trae
    # una tx DISTINTA (FARMACIA) para que el assert de restore no sea vacuo: si el restore
    # no corriera, el archivo quedaría con el contenido nuevo, no con el bueno.
    (root / "imports" / "cartolas" / "zz-roto.beancount").write_text(
        '2026-01-01 * "desbalanceada"\n  Assets:Nope  1 CLP\n', encoding="utf-8")
    _write_cartola(root, _cartola(TC_ID, "tarjeta_credito",
                                  [("FARMACIA", 999999), ("PAGO", -100000)], opening="0"),
                   batch_id="b10")
    r2 = promote("b10", imp, root)

    assert r2["success"] is False
    assert "bean-check failed" in r2["error_msg"]
    assert out_file.exists(), "el archivo previo NO debe borrarse en un re-import fallido"
    restored = out_file.read_text(encoding="utf-8")
    assert restored == good_content
    assert "FARMACIA" not in restored  # el contenido nuevo NO quedó


def test_promote_import_nuevo_bean_check_rojo_hace_unlink(tmp_path):
    """Contrapartida del restore: si el archivo NO existía antes (import nuevo fallido),
    el rollback sigue siendo unlink (no debe quedar un archivo huérfano roto)."""
    root = tmp_path
    (root / "imports" / "cartolas").mkdir(parents=True, exist_ok=True)
    _accounts(root)
    (root / "main.beancount").write_text(
        'option "operating_currency" "CLP"\n1900-01-01 commodity CLP\n'
        'include "accounts.beancount"\ninclude "imports/cartolas/*.beancount"\n',
        encoding="utf-8",
    )
    (root / "imports" / "cartolas" / "_init.beancount").write_text(";; init\n", encoding="utf-8")
    # Sibling roto DESDE el principio → el primer promote ya falla bean-check.
    (root / "imports" / "cartolas" / "zz-roto.beancount").write_text(
        '2026-01-01 * "desbalanceada"\n  Assets:Nope  1 CLP\n', encoding="utf-8")

    imp = CartolaPdfImporter(BankAccountResolver(root / "accounts.beancount"), NoopCategoryPredictor())
    _write_cartola(root, _cartola(TC_ID, "tarjeta_credito",
                                  [("ENEL", 852689)], opening="0"), batch_id="b11")
    r = promote("b11", imp, root)

    assert r["success"] is False
    assert not list((root / "imports" / "cartolas").glob("BancoBci-1027-2026-03.beancount"))
