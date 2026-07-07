"""Tests de validación de extracción + conciliación — Story 9.9 (cuadre de extracción) + Story 6.1
(modelo A: la cartola se concilia contra Laudus y reporta diferencias; NO se postea al ledger)."""
import json
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.cartolas.service import (
    BalanceDiscrepancy,
    OverrideJustificationTooShort,
    StagingNotFound,
    validate_balance,
)
from backend.app.auth.service import create_jwt
from backend.app.middleware import add_middleware
from pipeline.importers.bank_account_resolver import BankAccountResolver
from pipeline.importers.cartola_pdf_importer import CartolaPdfImporter

TC_ID = "e919b1db-be7d-430c-9f40-60fc58ae2bcb"

# Modelo A (Story 6.1) = cuenta corriente. La TC tiene su propio flujo (corrección, Story 6.2);
# estos tests ejercen el cuadre de extracción + reconcile-sin-postear → cuenta corriente.
ACCOUNTS = """\
2020-12-31 open Assets:EAG:Bancos:BancoBciCtaCte-111005 CLP
  bank_account_id: "e919b1db-be7d-430c-9f40-60fc58ae2bcb"
  bank_account_type: "cta_corriente"
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
                   "account_type": "cta_corriente", "entity": "EAG"},
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


# ── Cuadre de extracción OK → concilia (modelo A: no postea) ──────────────────


def test_validate_balance_cuadra(tmp_path):
    root = _root(tmp_path)
    _staging(root, "0", "852689", [("ENEL", 852689)])
    res = validate_balance("b1", "0", "852689", None, user_email="c@test.com",
                           ledger_root=root, importer=_importer(root))
    assert res["status"] == "reconciled" and res["override"] is False
    # modelo A: la cartola NO se postea → no hay archivo final; el staging se consume.
    assert not list((root / "imports" / "cartolas").glob("*2026-03.beancount"))
    assert not (root / "imports" / "cartolas" / "_staging" / "b1.cartola.json").exists()
    # sin asientos Laudus para la cuenta → la línea es una diferencia (missing-in-laudus, no bloqueante).
    assert res["differences"] == 1 and res["blocking"] == 0


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


# ── Override de cuadre de extracción → procede a conciliar (modelo A: sin pad) ─


def test_validate_balance_override(tmp_path):
    root = _root(tmp_path)
    _staging(root, "0", "852689", [("ENEL", 852689)])
    res = validate_balance(
        "b1", "0", "999999",
        "Cartola cortada a mitad de mes, el banco no informó el cierre real todavía",
        user_email="c@test.com", ledger_root=root, importer=_importer(root),
        now_iso="2026-05-01T10:30:00Z",
    )
    # El override permite proceder pese al descuadre de extracción; modelo A no escribe pad ni archivo.
    assert res["status"] == "reconciled" and res["override"] is True
    assert not list((root / "imports" / "cartolas").glob("*2026-03.beancount"))


def test_override_corto_se_rechaza_server_side(tmp_path):
    # AC4 es el boundary: el server enforce ≥20 chars, no solo el cliente.
    root = _root(tmp_path)
    _staging(root, "0", "852689", [("ENEL", 852689)])
    with pytest.raises(OverrideJustificationTooShort):
        validate_balance("b1", "0", "999999", "muy corta", user_email="c@test.com",
                         ledger_root=root, importer=_importer(root))
    # no se promovió: staging persiste, sin archivo final
    assert (root / "imports" / "cartolas" / "_staging" / "b1.cartola.json").exists()
    assert not list((root / "imports" / "cartolas").glob("*2026-03.beancount"))


def test_override_innecesario_cuando_cuadra_no_genera_pad(tmp_path):
    # diff==0 + justificación → override False (no había descuadre que forzar).
    root = _root(tmp_path)
    _staging(root, "0", "852689", [("ENEL", 852689)])
    res = validate_balance(
        "b1", "0", "852689",
        "Justificación larga e innecesaria porque el balance ya cuadra perfectamente",
        user_email="c@test.com", ledger_root=root, importer=_importer(root))
    assert res["status"] == "reconciled" and res["override"] is False


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


# ── Cheap-checks sincrónicos del PATCH (batch 2 Fase 3: precheck_balance real, sin mocks) ──


def test_endpoint_400_justificacion_corta_sincrono(tmp_path, monkeypatch):
    """El 400 JUSTIFICATION_TOO_SHORT sigue llegando sincrónico y con el shape de siempre,
    ejercitando precheck_balance de verdad (los tests del router lo mockean)."""
    root = _root(tmp_path)
    monkeypatch.setenv("LEDGER_DIR", str(root))
    _staging(root, "0", "100", [("JUMBO", 50)])  # descuadra (100 ≠ 0+50)
    client = _app()
    resp = client.patch("/api/v1/cartolas/b1/validate-balance",
                        json={"opening": "0", "closing": "100", "override_justification": "corta"},
                        cookies={"access_token": create_jwt(email="c@test.com", role="contador")})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "JUSTIFICATION_TOO_SHORT"
    assert "20" in body["error"]["message"]


def test_endpoint_400_discrepancia_sincrono_con_diff(tmp_path, monkeypatch):
    """El 400 VALIDATION_FAILED sigue sincrónico con diff/calculated/stated exactos."""
    root = _root(tmp_path)
    monkeypatch.setenv("LEDGER_DIR", str(root))
    _staging(root, "0", "100", [("JUMBO", 50)])
    client = _app()
    resp = client.patch("/api/v1/cartolas/b1/validate-balance",
                        json={"opening": "0", "closing": "100"},
                        cookies={"access_token": create_jwt(email="c@test.com", role="contador")})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["diff"] == 50.0
    assert body["error"]["calculated"] == 50.0
    assert body["error"]["stated"] == 100.0
