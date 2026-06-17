"""Tests de validación de balance + promote — Story 9.9 AC1/AC4/AC5/AC6/AC8."""
import json
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.cartolas.service import (
    BalanceDiscrepancy,
    StagingNotFound,
    validate_balance,
)
from backend.app.auth.service import create_jwt
from backend.app.middleware import add_middleware
from pipeline.importers.bank_account_resolver import BankAccountResolver
from pipeline.importers.cartola_pdf_importer import CartolaPdfImporter

TC_ID = "e919b1db-be7d-430c-9f40-60fc58ae2bcb"

ACCOUNTS = """\
2020-12-31 open Liabilities:EAG:TC:VisaInfinity-430005 CLP
  bank_account_id: "e919b1db-be7d-430c-9f40-60fc58ae2bcb"
  bank_account_type: "tarjeta_credito"
  bank_account_currency: "CLP"
  bank_account_last4: "1027"
  bank_name: "Banco BCI"
2020-12-31 open Expenses:EAG:Suspense CLP, USD
2020-12-31 open Equity:Reconciliation:Discrepancias CLP, USD
"""


def _root(tmp_path):
    (tmp_path / "imports" / "cartolas" / "_staging").mkdir(parents=True, exist_ok=True)
    (tmp_path / "accounts.beancount").write_text(ACCOUNTS, encoding="utf-8")
    (tmp_path / "main.beancount").write_text(
        'option "operating_currency" "CLP"\n1900-01-01 commodity CLP\n'
        'include "accounts.beancount"\ninclude "imports/cartolas/*.beancount"\n', encoding="utf-8")
    (tmp_path / "imports" / "cartolas" / "_init.beancount").write_text(";; init\n", encoding="utf-8")
    return tmp_path


def _staging(root, opening, closing, txs, batch_id="b1"):
    payload = {
        "schema_version": "1.0",
        "source": {"bank_account_id": TC_ID, "bank_name": "Banco BCI", "account_label": "x",
                   "account_type": "tarjeta_credito", "entity": "EAG"},
        "period": {"start": "2026-03-01", "end": "2026-03-31"},
        "currency": "CLP",
        "balances": {"opening": opening, "closing": closing},
        "transactions": [{"line_no": i + 1, "date": "2026-03-15", "description": d,
                          "amount": str(a), "currency": "CLP", "raw": {}} for i, (d, a) in enumerate(txs)],
        "extraction": {"model": "gemini-3.5-flash", "extracted_at": "2026-04-01T10:00:00Z", "warnings": []},
    }
    (root / "imports" / "cartolas" / "_staging" / f"{batch_id}.cartola.json").write_text(
        json.dumps(payload), encoding="utf-8")
    return payload


def _importer(root):
    return CartolaPdfImporter(BankAccountResolver(root / "accounts.beancount"))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("IMPORTER_GIT_ENABLED", raising=False)


# ── AC1/AC8: happy path (cuadra) ──────────────────────────────────────────────


def test_validate_balance_cuadra(tmp_path):
    root = _root(tmp_path)
    _staging(root, "0", "852689", [("ENEL", 852689)])
    res = validate_balance("b1", "0", "852689", None, user_email="c@test.com",
                           ledger_root=root, importer=_importer(root))
    assert res["status"] == "validated" and res["override"] is False
    # archivo final creado, staging removido
    assert list((root / "imports" / "cartolas").glob("*2026-03.beancount"))
    assert not (root / "imports" / "cartolas" / "_staging" / "b1.cartola.json").exists()


# ── AC5/AC8: discrepancia sin override → BalanceDiscrepancy ───────────────────


def test_validate_balance_discrepancia_sin_override(tmp_path):
    root = _root(tmp_path)
    _staging(root, "0", "852689", [("ENEL", 852689)])
    # closing pedido NO cuadra con opening+Σ (852689) → bean-check rojo
    with pytest.raises(BalanceDiscrepancy) as exc:
        validate_balance("b1", "0", "999999", None, user_email="c@test.com",
                         ledger_root=root, importer=_importer(root))
    assert exc.value.diff != 0
    assert exc.value.stated == 999999.0
    # staging persiste (no se promovió)
    assert (root / "imports" / "cartolas" / "_staging" / "b1.cartola.json").exists()


# ── AC4/AC6/AC8: override con justificación → pad+balance ─────────────────────


def test_validate_balance_override(tmp_path):
    root = _root(tmp_path)
    _staging(root, "0", "852689", [("ENEL", 852689)])
    res = validate_balance(
        "b1", "0", "999999",
        "Cartola cortada a mitad de mes, el banco no informó el cierre real todavía",
        user_email="c@test.com", ledger_root=root, importer=_importer(root),
        now_iso="2026-05-01T10:30:00Z",
    )
    assert res["status"] == "validated" and res["override"] is True
    written = next((root / "imports" / "cartolas").glob("*2026-03.beancount")).read_text(encoding="utf-8")
    assert "pad" in written and "override_justification" in written


def test_staging_no_encontrado(tmp_path):
    root = _root(tmp_path)
    with pytest.raises(StagingNotFound):
        validate_balance("nope", "0", "0", None, user_email="c@test.com",
                         ledger_root=root, importer=_importer(root))


# ── Endpoint: RBAC + 404 ──────────────────────────────────────────────────────


def _app():
    from backend.app.api.v1.cartolas.router import router
    app = FastAPI()
    add_middleware(app)
    app.include_router(router, prefix="/api/v1")
    return TestClient(app, raise_server_exceptions=False)


def test_endpoint_family_403():
    client = _app()
    resp = client.patch("/api/v1/cartolas/b1/validate-balance",
                        json={"opening": "0", "closing": "0"},
                        cookies={"access_token": create_jwt(email="f@test.com", role="family")})
    assert resp.status_code == 403


def test_endpoint_404_staging_inexistente(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_DIR", str(_root(tmp_path)))
    client = _app()
    resp = client.patch("/api/v1/cartolas/nope/validate-balance",
                        json={"opening": "0", "closing": "0"},
                        cookies={"access_token": create_jwt(email="c@test.com", role="contador")})
    assert resp.status_code == 404
