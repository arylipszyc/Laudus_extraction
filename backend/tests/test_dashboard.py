"""Tests del dashboard — GET /balance-sheets y /ledger-entries.

Servidos desde el ledger Beancount (BQL). Story 9.2 (path Beancount) + 9.16
(cleanup c4: el path Sheets fue removido; este archivo absorbe la cobertura de
auth/validación de la antigua suite de Story 3.1). Cubre: data-path, 503 ledger
roto, auth, RBAC y validación de entity/fechas.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.auth.service import create_jwt
from backend.app.dependencies import get_ledger_service
from backend.app.middleware import add_middleware
from backend.app.services.ledger_service import LedgerService
from backend.tests.test_bql_queries import MINI_LEDGER


BROKEN_LEDGER = """\
option "operating_currency" "CLP"
1900-01-01 commodity CLP
2020-01-01 open Assets:EAG:Bancos:TestBank-111005 CLP
2024-03-15 * "Unbalanced"
  Assets:EAG:Bancos:TestBank-111005   100000 CLP
"""


def _make_app(tmp_path, ledger_content=MINI_LEDGER) -> TestClient:
    from backend.app.api.v1.dashboard.router import router as dashboard_router

    main = tmp_path / "main.beancount"
    main.write_text(ledger_content, encoding="utf-8")
    svc = LedgerService(str(main))

    app = FastAPI()
    add_middleware(app)
    app.include_router(dashboard_router, prefix="/api/v1")
    app.dependency_overrides[get_ledger_service] = lambda: svc
    return TestClient(app, raise_server_exceptions=False)


def _family():
    return create_jwt(email="family@test.com", role="family")


def _contador():
    return create_jwt(email="contador@test.com", role="contador")


# ── data path ─────────────────────────────────────────────────────────────────


def test_balance_sheets_beancount_path(tmp_path):
    """El endpoint sirve el balance-sheet derivado por BQL con el shape esperado."""
    client = _make_app(tmp_path)
    resp = client.get("/api/v1/balance-sheets", params={"entity": "EAG"},
                      cookies={"access_token": _family()})
    assert resp.status_code == 200
    body = resp.json()
    bank = next(r for r in body["data"] if r["account_number"] == "111005")
    assert bank["debit_balance"] == 70000.0
    # El response_model expone `account` (cuenta Beancount) para agrupar por raíz contable;
    # sin esto las cuentas de hijas/T/C caen en "Otros".
    assert bank["account"] == "Assets:EAG:Bancos:TestBank-111005"
    assert body["meta"]["last_sync"] is not None


def test_ledger_entries_beancount_path(tmp_path):
    """El endpoint sirve los asientos derivados por BQL, filtrables por cuenta."""
    client = _make_app(tmp_path)
    resp = client.get("/api/v1/ledger-entries", params={"entity": "EAG", "account_number": "111005"},
                      cookies={"access_token": _family()})
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]
    assert all(r["accountnumber"] == "111005" for r in body["data"])


# ── 503 cuando el ledger está roto ──────────────────────────────────────────────


def test_broken_ledger_returns_503(tmp_path):
    """Ledger con errores de parseo → 503 con body LEDGER_UNAVAILABLE."""
    client = _make_app(tmp_path, ledger_content=BROKEN_LEDGER)
    resp = client.get("/api/v1/balance-sheets", params={"entity": "EAG"},
                      cookies={"access_token": _family()})
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "LEDGER_UNAVAILABLE"
    assert body["error"]["detail"]


# ── auth ────────────────────────────────────────────────────────────────────────


def test_balance_sheets_unauthenticated(tmp_path):
    client = _make_app(tmp_path)
    resp = client.get("/api/v1/balance-sheets", params={"entity": "EAG"})
    assert resp.status_code == 401


def test_ledger_entries_unauthenticated(tmp_path):
    client = _make_app(tmp_path)
    resp = client.get("/api/v1/ledger-entries", params={"entity": "EAG"})
    assert resp.status_code == 401


# ── RBAC: family y contador leen (Story 9.13 AC6) ───────────────────────────────


def test_balance_sheets_contador_can_read(tmp_path):
    client = _make_app(tmp_path)
    resp = client.get("/api/v1/balance-sheets", params={"entity": "EAG"},
                      cookies={"access_token": _contador()})
    assert resp.status_code == 200


def test_ledger_entries_contador_can_read(tmp_path):
    client = _make_app(tmp_path)
    resp = client.get("/api/v1/ledger-entries", params={"entity": "EAG"},
                      cookies={"access_token": _contador()})
    assert resp.status_code == 200


# ── validación de entity ────────────────────────────────────────────────────────


def test_balance_sheets_invalid_entity_returns_422(tmp_path):
    client = _make_app(tmp_path)
    resp = client.get("/api/v1/balance-sheets", params={"entity": "INVALID"},
                      cookies={"access_token": _family()})
    assert resp.status_code == 422


def test_ledger_entries_invalid_entity_returns_422(tmp_path):
    client = _make_app(tmp_path)
    resp = client.get("/api/v1/ledger-entries", params={"entity": "UNKNOWN"},
                      cookies={"access_token": _family()})
    assert resp.status_code == 422


@pytest.mark.parametrize("entity", ["EAG", "Jocelyn", "Jeannette", "Johanna", "Jael"])
def test_valid_entities_accepted(tmp_path, entity):
    """Las 5 entidades válidas → 200 (data vacía es válida)."""
    client = _make_app(tmp_path)
    resp = client.get("/api/v1/balance-sheets", params={"entity": entity},
                      cookies={"access_token": _family()})
    assert resp.status_code == 200


# ── validación de fechas ISO ────────────────────────────────────────────────────


def test_balance_sheets_malformed_date_returns_422(tmp_path):
    client = _make_app(tmp_path)
    resp = client.get("/api/v1/balance-sheets", params={"entity": "EAG", "date_from": "not-a-date"},
                      cookies={"access_token": _family()})
    assert resp.status_code == 422


def test_balance_sheets_inverted_range_returns_422(tmp_path):
    client = _make_app(tmp_path)
    resp = client.get("/api/v1/balance-sheets",
                      params={"entity": "EAG", "date_from": "2026-12-31", "date_to": "2026-01-01"},
                      cookies={"access_token": _family()})
    assert resp.status_code == 422


def test_ledger_entries_malformed_date_returns_422(tmp_path):
    client = _make_app(tmp_path)
    resp = client.get("/api/v1/ledger-entries", params={"entity": "EAG", "date_to": "31-03-2026"},
                      cookies={"access_token": _family()})
    assert resp.status_code == 422
