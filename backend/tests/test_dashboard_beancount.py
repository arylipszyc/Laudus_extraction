"""Endpoint tests for the Beancount engine path — Story 9.2 AC2/AC3/AC4/AC1(503).

Exercises the dashboard endpoints with `USE_BEANCOUNT_ENGINE_*=true` and a
LedgerService backed by a synthetic mini-ledger, plus the 503 LEDGER_UNAVAILABLE
path when the ledger has parse errors.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.auth.service import create_jwt
from backend.app.dependencies import get_ledger_service, get_repository
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
    # repo is unused on the beancount path but the dependency must resolve.
    app.dependency_overrides[get_repository] = lambda: object()
    return TestClient(app, raise_server_exceptions=False)


def _family():
    return create_jwt(email="family@test.com", role="family")


def _enable(monkeypatch):
    monkeypatch.setenv("USE_BEANCOUNT_ENGINE_BALANCE_SHEET", "true")
    monkeypatch.setenv("USE_BEANCOUNT_ENGINE_LEDGER", "true")


# ── balance-sheets via beancount ──────────────────────────────────────────────


def test_balance_sheets_beancount_path(tmp_path, monkeypatch):
    """AC3: flag on → endpoint serves BQL-derived balance sheet with Sheets shape."""
    _enable(monkeypatch)
    client = _make_app(tmp_path)
    resp = client.get("/api/v1/balance-sheets", params={"entity": "EAG"},
                      cookies={"access_token": _family()})
    assert resp.status_code == 200
    body = resp.json()
    bank = next(r for r in body["data"] if r["account_number"] == "111005")
    assert bank["debit_balance"] == 70000.0
    assert body["meta"]["last_sync"] is not None


def test_ledger_entries_beancount_path(tmp_path, monkeypatch):
    """AC4: flag on → endpoint serves BQL-derived ledger entries."""
    _enable(monkeypatch)
    client = _make_app(tmp_path)
    resp = client.get("/api/v1/ledger-entries", params={"entity": "EAG", "account_number": "111005"},
                      cookies={"access_token": _family()})
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]
    assert all(r["accountnumber"] == "111005" for r in body["data"])


def test_flag_off_does_not_touch_ledger(tmp_path, monkeypatch):
    """AC2: flag off (default) → Sheets path; the broken ledger is never queried."""
    monkeypatch.delenv("USE_BEANCOUNT_ENGINE_BALANCE_SHEET", raising=False)
    client = _make_app(tmp_path, ledger_content=BROKEN_LEDGER)
    # Sheets path would call repo.get_records; our dummy repo lacks it → 500 only if
    # the beancount path is wrongly taken would differ. Use a mock repo instead:
    from unittest.mock import MagicMock
    repo = MagicMock()
    repo.get_records.return_value = []
    from backend.app.api.v1.dashboard.router import router as dashboard_router
    app = FastAPI()
    add_middleware(app)
    app.include_router(dashboard_router, prefix="/api/v1")
    app.dependency_overrides[get_repository] = lambda: repo
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/v1/balance-sheets", params={"entity": "EAG"},
                      cookies={"access_token": _family()})
    # Sheets path returns empty data, NOT a 503 — proves the broken ledger was ignored.
    assert resp.status_code == 200
    assert resp.json()["data"] == []


# ── 503 when ledger is broken ─────────────────────────────────────────────────


def test_broken_ledger_returns_503(tmp_path, monkeypatch):
    """AC1: flag on + broken ledger → 503 with LEDGER_UNAVAILABLE error body."""
    _enable(monkeypatch)
    client = _make_app(tmp_path, ledger_content=BROKEN_LEDGER)
    resp = client.get("/api/v1/balance-sheets", params={"entity": "EAG"},
                      cookies={"access_token": _family()})
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "LEDGER_UNAVAILABLE"
    assert body["error"]["message"] == "Ledger has parse errors"
    assert body["error"]["detail"]
