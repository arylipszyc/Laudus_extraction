"""Tests de corrección de categorías — Story 9.7 AC7/AC8/AC9 + tx_id."""
import json
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.transactions.service import (
    TxNotFound,
    bulk_categorize,
    bulk_confirm,
    list_pending,
    update_category,
)
from backend.app.auth.service import create_jwt
from backend.app.dependencies import get_ledger_service
from backend.app.middleware import add_middleware
from backend.app.services.ledger_service import LedgerService
from pipeline.importers.bank_account_resolver import BankAccountResolver
from pipeline.importers.cartola_pdf_importer import CartolaPdfImporter, promote

TC_ID = "e919b1db-be7d-430c-9f40-60fc58ae2bcb"

ACCOUNTS = """\
2020-12-31 open Liabilities:EAG:TC:VisaInfinity-430005 CLP
  bank_account_id: "e919b1db-be7d-430c-9f40-60fc58ae2bcb"
  bank_account_type: "tarjeta_credito"
  bank_account_currency: "CLP"
  bank_account_last4: "1027"
  bank_name: "Banco BCI"
2020-12-31 open Expenses:EAG:Super CLP, USD
2020-12-31 open Expenses:EAG:Farmacia CLP, USD
2020-12-31 open Expenses:EAG:Suspense CLP, USD
2020-12-31 open Equity:Reconciliation:Discrepancias CLP, USD
"""


class _FakeSuggested:
    """Predictor que sugiere (flag '!', match_source smart_importer → category_status 'suggested')."""
    def predict(self, description, amount, bank_account_id):
        return "Expenses:EAG:Super", "smart_importer", "!"


def _ledger(tmp_path):
    (tmp_path / "imports" / "cartolas" / "_staging").mkdir(parents=True, exist_ok=True)
    (tmp_path / "_meta").mkdir(parents=True, exist_ok=True)
    (tmp_path / "accounts.beancount").write_text(ACCOUNTS, encoding="utf-8")
    (tmp_path / "main.beancount").write_text(
        'option "operating_currency" "CLP"\n1900-01-01 commodity CLP\n'
        'include "accounts.beancount"\ninclude "imports/cartolas/*.beancount"\n', encoding="utf-8")
    (tmp_path / "imports" / "cartolas" / "_init.beancount").write_text(";; init\n", encoding="utf-8")
    return tmp_path


def _staging(root, txs, batch_id="b1", period=("2026-03-01", "2026-03-31"), tx_date="2026-03-15",
             closing=None):
    closing = str(closing if closing is not None else sum(Decimal(str(a)) for _, a in txs))
    payload = {
        "schema_version": "1.0",
        "source": {"bank_account_id": TC_ID, "bank_name": "Banco BCI", "account_label": "x",
                   "account_type": "tarjeta_credito", "entity": "EAG"},
        "period": {"start": period[0], "end": period[1]},
        "currency": "CLP",
        "balances": {"opening": "0", "closing": closing},
        "transactions": [{"line_no": i + 1, "date": tx_date, "description": d,
                          "amount": str(a), "currency": "CLP", "raw": {}} for i, (d, a) in enumerate(txs)],
        "extraction": {"model": "g", "extracted_at": "2026-04-01T10:00:00Z", "warnings": []},
    }
    (root / "imports" / "cartolas" / "_staging" / f"{batch_id}.cartola.json").write_text(
        json.dumps(payload), encoding="utf-8")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("IMPORTER_GIT_ENABLED", raising=False)


def _promote(root):
    imp = CartolaPdfImporter(BankAccountResolver(root / "accounts.beancount"), _FakeSuggested())
    _staging(root, [("JUMBO", 45000), ("FARMACIA", 12000)])
    res = promote("b1", imp, root)
    assert res["success"], res
    return LedgerService(str(root / "main.beancount"))


# ── AC9: list_pending ─────────────────────────────────────────────────────────


def test_list_pending(tmp_path):
    svc = _promote(_ledger(tmp_path))
    pend = list_pending(svc.entries())
    assert len(pend) == 2
    assert all(p["current_category_status"] == "suggested" for p in pend)
    assert all(p["current_flag"] == "!" for p in pend)
    assert {p["current_category"] for p in pend} == {"Expenses:EAG:Super"}


# ── AC7: PATCH category ───────────────────────────────────────────────────────


def test_update_category_corrige_y_appendea_history(tmp_path):
    root = _ledger(tmp_path)
    svc = _promote(root)
    pend = list_pending(svc.entries())
    tx_id = pend[0]["tx_id"]
    res = update_category(tx_id, "Expenses:EAG:Farmacia", entries=svc.entries(),
                          ledger_root=root, user_email="c@test.com", now_iso="2026-05-01T00:00:00Z")
    assert res["flag"] == "*"
    # el archivo refleja el cambio: flag * + nueva categoría + status confirmed
    f = next((root / "imports" / "cartolas").glob("*2026-03.beancount")).read_text(encoding="utf-8")
    assert "Expenses:EAG:Farmacia" in f
    assert 'category_status: "confirmed"' in f
    # history appendeada (alimenta la regla supra)
    hist = (root / "_meta" / "categorization-history.jsonl").read_text(encoding="utf-8")
    assert "Expenses:EAG:Farmacia" in hist
    # tras recargar, esa tx ya no está pendiente
    svc.load()
    assert all(p["tx_id"] != tx_id for p in list_pending(svc.entries()))


def test_update_category_tx_inexistente(tmp_path):
    svc = _promote(_ledger(tmp_path))
    with pytest.raises(TxNotFound):
        update_category("deadbeef0000", "Expenses:EAG:Super", entries=svc.entries(),
                        ledger_root=_ledger(tmp_path), user_email="c@test.com")


# ── AC8: bulk-confirm ─────────────────────────────────────────────────────────


def test_bulk_confirm_confirma_sugeridas(tmp_path):
    root = _ledger(tmp_path)
    svc = _promote(root)
    res = bulk_confirm("b1", entries=svc.entries(), ledger_root=root, user_email="c@test.com")
    assert res["confirmed"] == 2
    f = next((root / "imports" / "cartolas").glob("*2026-03.beancount")).read_text(encoding="utf-8")
    assert "! " not in f.replace("\n", " ")  # ya no quedan flags ! (se confirmaron)
    svc.load()
    assert list_pending(svc.entries()) == []


def test_bulk_confirm_scoped_solo_confirma_ese_batch(tmp_path):
    # Dos batches (períodos distintos → archivos distintos): bulk-confirm("b1") solo confirma b1.
    root = _ledger(tmp_path)
    imp = CartolaPdfImporter(BankAccountResolver(root / "accounts.beancount"), _FakeSuggested())
    _staging(root, [("JUMBO", 45000), ("FARMACIA", 12000)], batch_id="b1")
    assert promote("b1", imp, root)["success"]
    # misma cuenta TC → el Balance de cierre de b2 es acumulativo (b1 -57000 + b2 -9000 = -66000)
    _staging(root, [("LIDER", 9000)], batch_id="b2",
             period=("2026-04-01", "2026-04-30"), tx_date="2026-04-15", closing=66000)
    assert promote("b2", imp, root)["success"]
    svc = LedgerService(str(root / "main.beancount"))

    res = bulk_confirm("b1", entries=svc.entries(), ledger_root=root, user_email="c@test.com")
    assert res["confirmed"] == 2  # solo las 2 de b1, NO la de b2
    svc.load()
    pend = list_pending(svc.entries())
    assert [p["current_category_status"] for p in pend] == ["suggested"]  # la de b2 sigue pendiente
    assert pend[0]["narration"] == "LIDER"


# ── bulk-categorize: confirma seleccionadas con su categoría en un commit ──────


def test_bulk_categorize_confirma_con_categoria_un_commit(tmp_path):
    root = _ledger(tmp_path)
    svc = _promote(root)
    pend = sorted(list_pending(svc.entries()), key=lambda p: p["narration"])
    items = [(pend[0]["tx_id"], "Expenses:EAG:Farmacia"),   # FARMACIA
             (pend[1]["tx_id"], "Expenses:EAG:Super")]      # JUMBO
    res = bulk_categorize(items, entries=svc.entries(), ledger_root=root,
                          user_email="c@test.com", now_iso="2026-05-01T00:00:00Z")
    assert res["confirmed"] == 2
    f = next((root / "imports" / "cartolas").glob("*2026-03.beancount")).read_text(encoding="utf-8")
    assert "Expenses:EAG:Farmacia" in f
    assert 'category_status: "confirmed"' in f
    # ambas quedan en la history (alimenta la supra)
    hist = (root / "_meta" / "categorization-history.jsonl").read_text(encoding="utf-8")
    assert "Expenses:EAG:Farmacia" in hist and "Expenses:EAG:Super" in hist
    # tras recargar, nada pendiente
    svc.load()
    assert list_pending(svc.entries()) == []


def test_bulk_categorize_tx_inexistente(tmp_path):
    root = _ledger(tmp_path)
    svc = _promote(root)
    with pytest.raises(TxNotFound):
        bulk_categorize([("deadbeef0000", "Expenses:EAG:Super")], entries=svc.entries(),
                        ledger_root=root, user_email="c@test.com")


def test_rewrite_preserva_pata_liability_tc(tmp_path):
    """Regresión del bug que BORRABA la deuda: categorizar una compra TC debe reescribir SOLO la
    pata Expenses (Suspense→categoría) y PRESERVAR la pata `Liabilities:TC:Real`. Antes se reescribían
    ambas (la deuda TC:Real no resuelve del bank_account_id) → las 2 patas quedaban iguales → deuda 0."""
    from beancount.parser import parser
    from backend.app.api.v1.transactions.service import _rewrite_file, _tx_id_of

    f = tmp_path / "tc.beancount"
    f.write_text(
        '2026-04-10 * "COMPRA X"\n'
        '  bank_account_id: "e919b1db-be7d-430c-9f40-60fc58ae2bcb"\n'
        '  operation_type: "compra"\n'
        '  Liabilities:EAG:TC:Real:Tc1027VisaInfinity  -22042.0 CLP\n'
        '  Expenses:EAG:Suspense                        22042.0 CLP\n',
        encoding="utf-8")
    entries, _e, _o = parser.parse_file(str(f))
    tx_id = _tx_id_of(entries[0])

    _rewrite_file(f, {tx_id}, "Expenses:EAG:Remedios-430051")

    out, _e, _o = parser.parse_file(str(f))
    accts = [p.account for p in out[0].postings]
    assert "Liabilities:EAG:TC:Real:Tc1027VisaInfinity" in accts  # la deuda SIGUE
    assert "Expenses:EAG:Remedios-430051" in accts                # el gasto se recategorizó
    assert "Expenses:EAG:Suspense" not in accts                   # Suspense reemplazado
    # y el asiento sigue balanceado (2 patas distintas, no 2 iguales que se anulan)
    assert len(set(accts)) == 2


def test_update_category_commitea_la_history_jsonl(tmp_path, monkeypatch):
    # La history debe entrar en el commit (si no, el reset --hard del refresh la descarta).
    import pipeline.importers.laudus_run as lr
    captured = {}
    def _fake_push(repo_root, paths, message):
        captured["paths"] = list(paths)
        return "deadbeef0001"
    monkeypatch.setattr(lr, "git_commit_push", _fake_push)

    root = _ledger(tmp_path)
    svc = _promote(root)
    tx_id = list_pending(svc.entries())[0]["tx_id"]
    update_category(tx_id, "Expenses:EAG:Farmacia", entries=svc.entries(),
                    ledger_root=root, user_email="c@test.com", now_iso="2026-05-01T00:00:00Z")
    assert "ledger/_meta/categorization-history.jsonl" in captured["paths"]
    assert any("imports/cartolas/" in p for p in captured["paths"])


# ── RBAC ──────────────────────────────────────────────────────────────────────


def test_patch_rbac_family_403(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_BEANCOUNT_ENGINE_LEDGER", "true")
    from backend.app.api.v1.transactions.router import router
    app = FastAPI(); add_middleware(app); app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_ledger_service] = lambda: LedgerService(str(_ledger(tmp_path) / "main.beancount"))
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.patch("/api/v1/transactions/abc/category", json={"category_account": "Expenses:EAG:Super"},
                        cookies={"access_token": create_jwt(email="f@test.com", role="family")})
    assert resp.status_code == 403
