"""Tests for plan_de_cuentas endpoints — Story 4.0."""
import pytest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.auth.service import create_jwt
from backend.app.middleware import add_middleware


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_app(mock_repo):
    """Build a test FastAPI app with SupabaseRepository overridden."""
    from backend.app.api.v1.plan_de_cuentas.router import router as pdc_router

    app = FastAPI()
    add_middleware(app)
    app.include_router(pdc_router, prefix="/api/v1/plan-de-cuentas")
    return app


def _contador_cookie():
    token = create_jwt(email="c@test.com", role="contador")
    return {"access_token": token}


def _family_cookie():
    token = create_jwt(email="family@test.com", role="family")
    return {"access_token": token}


SAMPLE_ACCOUNTS = [
    {
        "account_number": "111001",
        "account_name": "Caja CLP",
        "account_type": None,
        "cat1": "ACTIVO",
        "cat2": "Activo Circulante",
        "cat3": None,
        "active": True,
        "synced_at": "2026-04-15T10:00:00+00:00",
    },
    {
        "account_number": "411001",
        "account_name": "Gastos Operacionales",
        "account_type": None,
        "cat1": "GASTOS",
        "cat2": "Gastos Fijos",
        "cat3": None,
        "active": True,
        "synced_at": "2026-04-15T10:00:00+00:00",
    },
]


# ── Tests: POST /sync ──────────────────────────────────────────────────────────

class TestSyncPlanDeCuentas:
    def test_sync_requires_contador_role(self):
        """Owner role cannot trigger sync."""
        with patch("backend.app.api.v1.plan_de_cuentas.router.sync_plan_de_cuentas") as mock_sync:
            mock_sync.return_value = {"synced": 10, "updated": 5}
            app = _make_app(None)
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/api/v1/plan-de-cuentas/sync", cookies=_family_cookie())
            assert resp.status_code == 403

    def test_sync_unauthenticated_returns_401(self):
        """Unauthenticated request is rejected."""
        with patch("backend.app.api.v1.plan_de_cuentas.router.sync_plan_de_cuentas"):
            app = _make_app(None)
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/api/v1/plan-de-cuentas/sync")
            assert resp.status_code == 401

    def test_sync_contador_returns_counts(self):
        """Contador can trigger sync and gets synced/updated counts."""
        with patch("backend.app.api.v1.plan_de_cuentas.router.sync_plan_de_cuentas") as mock_sync:
            mock_sync.return_value = {"synced": 10, "updated": 5}
            app = _make_app(None)
            client = TestClient(app)
            resp = client.post("/api/v1/plan-de-cuentas/sync", cookies=_contador_cookie())
            assert resp.status_code == 200
            body = resp.json()
            assert body["synced"] == 10
            assert body["updated"] == 5

    def test_sync_service_error_returns_503(self):
        """RuntimeError from service returns 503."""
        with patch("backend.app.api.v1.plan_de_cuentas.router.sync_plan_de_cuentas") as mock_sync:
            mock_sync.side_effect = RuntimeError("Cannot connect to Sheets")
            app = _make_app(None)
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/api/v1/plan-de-cuentas/sync", cookies=_contador_cookie())
            assert resp.status_code == 503


# ── Tests: GET / ──────────────────────────────────────────────────────────────

class TestListPlanDeCuentas:
    def test_list_requires_authentication(self):
        """Unauthenticated request is rejected."""
        with patch("backend.app.api.v1.plan_de_cuentas.router.list_plan_de_cuentas"):
            app = _make_app(None)
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/plan-de-cuentas/")
            assert resp.status_code == 401

    def test_list_family_can_access(self):
        """Owner role can list accounts."""
        with patch("backend.app.api.v1.plan_de_cuentas.router.list_plan_de_cuentas") as mock_list:
            mock_list.return_value = SAMPLE_ACCOUNTS
            app = _make_app(None)
            client = TestClient(app)
            resp = client.get("/api/v1/plan-de-cuentas/", cookies=_family_cookie())
            assert resp.status_code == 200

    def test_list_returns_accounts_ordered(self):
        """Accounts are returned as a list with expected fields."""
        with patch("backend.app.api.v1.plan_de_cuentas.router.list_plan_de_cuentas") as mock_list:
            mock_list.return_value = SAMPLE_ACCOUNTS
            app = _make_app(None)
            client = TestClient(app)
            resp = client.get("/api/v1/plan-de-cuentas/", cookies=_contador_cookie())
            assert resp.status_code == 200
            body = resp.json()
            assert len(body) == 2
            assert body[0]["account_number"] == "111001"
            assert body[0]["account_name"] == "Caja CLP"
            assert body[1]["account_number"] == "411001"

    def test_list_empty_returns_empty_list(self):
        """Empty Supabase table returns empty list."""
        with patch("backend.app.api.v1.plan_de_cuentas.router.list_plan_de_cuentas") as mock_list:
            mock_list.return_value = []
            app = _make_app(None)
            client = TestClient(app)
            resp = client.get("/api/v1/plan-de-cuentas/", cookies=_contador_cookie())
            assert resp.status_code == 200
            assert resp.json() == []


# ── Tests: _map_sheet_row ─────────────────────────────────────────────────────

class TestMapSheetRow:
    def test_maps_valid_row(self):
        from backend.app.api.v1.plan_de_cuentas.service import _map_sheet_row
        row = {
            "account_number": "111001",
            "account_name": "Caja CLP",
            "1\u00b0 Category": "ACTIVO",
            "2\u00b0 Category": "Activo Circulante",
            "3\u00b0 Category": "",
        }
        result = _map_sheet_row(row, "2026-04-15T10:00:00+00:00")
        assert result is not None
        assert result["account_number"] == "111001"
        assert result["cat1"] == "ACTIVO"
        assert result["cat2"] == "Activo Circulante"
        assert result["cat3"] is None  # Empty string → None

    def test_skips_row_without_account_number(self):
        from backend.app.api.v1.plan_de_cuentas.service import _map_sheet_row
        row = {"account_number": "", "account_name": "Ghost"}
        assert _map_sheet_row(row, "2026-04-15") is None

    def test_empty_category_becomes_none(self):
        from backend.app.api.v1.plan_de_cuentas.service import _map_sheet_row
        row = {
            "account_number": "999",
            "account_name": "Test",
            "1\u00b0 Category": "",
            "2\u00b0 Category": "  ",
            "3\u00b0 Category": "Valid",
        }
        result = _map_sheet_row(row, "2026-04-15")
        assert result["cat1"] is None
        assert result["cat2"] is None
        assert result["cat3"] == "Valid"
