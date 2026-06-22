"""Story 6.1 (modelo A) — conciliación cartola↔Laudus en el promote.

La cartola se concilia contra `imports/laudus/*` y se reportan las DIFERENCIAS al JSONL que el
dashboard 9.12 consume. NO se postea nada al ledger (Laudus sigue siendo lo contabilizado/validado).
`perfect` no genera diferencia; `value-mismatch`/`missing-in-cartola` son bloqueantes.
"""
import json

import pytest

from backend.app.api.v1.cartolas.service import validate_balance
from pipeline.importers.bank_account_resolver import BankAccountResolver
from pipeline.importers.cartola_pdf_importer import CartolaPdfImporter
from pipeline.importers.reconcile import reconcile_cartola

CC_ID = "11111111-1111-1111-1111-111111111111"
ACCOUNT = "Assets:EAG:Bancos:CtaCorriente-100200"

ACCOUNTS = """\
2020-12-31 open Assets:EAG:Bancos:CtaCorriente-100200 CLP
  bank_account_id: "11111111-1111-1111-1111-111111111111"
  bank_account_type: "cta_corriente"
  bank_account_currency: "CLP"
  bank_account_last4: "0200"
  bank_name: "Banco BCI"
2020-12-31 open Expenses:EAG:Suspense CLP, USD
2020-12-31 open Expenses:EAG:Super CLP
2020-12-31 open Equity:Reconciliation:Discrepancias CLP, USD
"""


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("IMPORTER_GIT_ENABLED", raising=False)
    monkeypatch.delenv("LEDGER_DISCREPANCIES", raising=False)


def _root(tmp_path):
    (tmp_path / "imports" / "cartolas" / "_staging").mkdir(parents=True, exist_ok=True)
    (tmp_path / "imports" / "laudus").mkdir(parents=True, exist_ok=True)
    (tmp_path / "accounts.beancount").write_text(ACCOUNTS, encoding="utf-8")
    return tmp_path


def _laudus(root, entries_text):
    (root / "imports" / "laudus" / "2026-03.beancount").write_text(entries_text, encoding="utf-8")


def _staging(root, txs, batch_id="b1", opening="0", closing=None):
    """txs = list of (date_iso, description, amount_int). closing default = opening + Σ."""
    if closing is None:
        closing = str(int(opening) + sum(a for _, _, a in txs))
    payload = {
        "schema_version": "1.0",
        "source": {"bank_account_id": CC_ID, "bank_name": "Banco BCI", "account_label": "CC",
                   "account_type": "cta_corriente", "entity": "EAG"},
        "period": {"start": "2026-03-01", "end": "2026-03-31"},
        "currency": "CLP",
        "balances": {"opening": opening, "closing": closing},
        "transactions": [{"line_no": i + 1, "date": d, "description": desc, "amount": str(a),
                          "currency": "CLP", "raw": {}} for i, (d, desc, a) in enumerate(txs)],
        "extraction": {"model": "gemini-3.5-flash", "extracted_at": "2026-04-01T10:00:00Z", "warnings": []},
    }
    (root / "imports" / "cartolas" / "_staging" / f"{batch_id}.cartola.json").write_text(
        json.dumps(payload), encoding="utf-8")


def _importer(root):
    return CartolaPdfImporter(BankAccountResolver(root / "accounts.beancount"))


def _disc_lines(root):
    p = root / "_meta" / "cartola-discrepancies.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _laudus_jumbo():
    return (f'2026-03-15 * "JUMBO"\n  {ACCOUNT}  -45000 CLP\n  Expenses:EAG:Super  45000 CLP\n')


# ── perfect → 0 diferencias, no postea, staging consumido ─────────────────────


def test_perfect_match_sin_diferencia(tmp_path):
    root = _root(tmp_path)
    _laudus(root, _laudus_jumbo())
    _staging(root, [("2026-03-15", "JUMBO", -45000)])
    res = reconcile_cartola("b1", _importer(root), root, ts="2026-04-01T00:00:00Z")
    assert res["status"] == "reconciled"
    assert res["differences"] == 0 and res["blocking"] == 0 and res["matched"] == 1
    assert _disc_lines(root) == []
    # modelo A: nada posteado al ledger, staging consumido.
    assert not list((root / "imports" / "cartolas").glob("*.beancount"))
    assert not (root / "imports" / "cartolas" / "_staging" / "b1.cartola.json").exists()


# ── value-mismatch → bloqueante ───────────────────────────────────────────────


def test_value_mismatch_es_bloqueante(tmp_path):
    root = _root(tmp_path)
    _laudus(root, f'2026-03-15 * "JUMBO"\n  {ACCOUNT}  -50000 CLP\n  Expenses:EAG:Super  50000 CLP\n')
    _staging(root, [("2026-03-15", "JUMBO", -45000)])
    res = reconcile_cartola("b1", _importer(root), root, ts="t")
    assert res["differences"] == 1 and res["blocking"] == 1
    assert [d["state"] for d in _disc_lines(root)] == ["value-mismatch"]


# ── missing-in-cartola (asiento Laudus sin línea de cartola) → bloqueante ──────


def test_missing_in_cartola_es_bloqueante(tmp_path):
    root = _root(tmp_path)
    _laudus(root, _laudus_jumbo()
            + f'2026-03-20 * "SOLO-LAUDUS"\n  {ACCOUNT}  -12000 CLP\n  Expenses:EAG:Super  12000 CLP\n')
    _staging(root, [("2026-03-15", "JUMBO", -45000)])
    res = reconcile_cartola("b1", _importer(root), root, ts="t")
    assert [d["state"] for d in _disc_lines(root)] == ["missing-in-cartola"]
    assert res["blocking"] == 1 and res["matched"] == 1


# ── missing-in-laudus (línea de cartola sin asiento) → NO bloqueante ──────────


def test_missing_in_laudus_no_bloqueante(tmp_path):
    root = _root(tmp_path)  # imports/laudus vacío
    _staging(root, [("2026-03-15", "TRANSFER DESCONOCIDA", -9999)])
    res = reconcile_cartola("b1", _importer(root), root, ts="t")
    assert res["differences"] == 1 and res["blocking"] == 0 and res["matched"] == 0
    assert [d["state"] for d in _disc_lines(root)] == ["missing-in-laudus"]


# ── dedup: re-reconciliar el mismo batch no duplica el JSONL (AC idempotencia) ─


def test_dedup_no_duplica_al_reconciliar_dos_veces(tmp_path):
    root = _root(tmp_path)
    _staging(root, [("2026-03-15", "X", -9999)])
    reconcile_cartola("b1", _importer(root), root, ts="t")
    _staging(root, [("2026-03-15", "X", -9999)])  # re-stage mismo batch (reconcile consumió el anterior)
    reconcile_cartola("b1", _importer(root), root, ts="t")
    assert len(_disc_lines(root)) == 1


# ── trampa: suggested_category="" evita category-mismatch espurio vs Laudus ───


def test_match_con_categoria_laudus_distinta_no_genera_category_mismatch(tmp_path):
    # Línea que matchea perfecto un asiento Laudus cuya categoría (Expenses:EAG:Super) difiere de
    # la que devolvería el predictor Noop (Suspense). Con suggested_category="" el matcher NO debe
    # disparar category-mismatch (si se poblara suggested_category, TODA línea matcheada lo haría).
    root = _root(tmp_path)
    _laudus(root, _laudus_jumbo())  # categoría Laudus = Expenses:EAG:Super
    _staging(root, [("2026-03-15", "JUMBO", -45000)])
    res = reconcile_cartola("b1", _importer(root), root, ts="t")
    assert res["differences"] == 0 and res["matched"] == 1
    assert _disc_lines(root) == []


# ── integración por validate_balance (cuadre de extracción OK → concilia) ─────


def test_via_validate_balance_concilia_perfect(tmp_path):
    root = _root(tmp_path)
    _laudus(root, _laudus_jumbo())
    _staging(root, [("2026-03-15", "JUMBO", -45000)])
    res = validate_balance("b1", "0", "-45000", None, user_email="c@test.com",
                           ledger_root=root, importer=_importer(root))
    assert res["status"] == "reconciled" and res["differences"] == 0 and res["matched"] == 1
