"""Tests for bank_accounts endpoints — Story 4.0."""
import pytest
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.auth.service import create_jwt
from backend.app.middleware import add_middleware


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_app():
    from backend.app.api.v1.bank_accounts.router import router as ba_router
    app = FastAPI()
    add_middleware(app)
    app.include_router(ba_router, prefix="/api/v1/bank-accounts")
    return app


def _contador_cookie():
    return {"access_token": create_jwt(email="c@test.com", role="contador")}


def _family_cookie():
    return {"access_token": create_jwt(email="family@test.com", role="family")}


SAMPLE_UUID = "12345678-1234-5678-1234-567812345678"

SAMPLE_BANK_ACCOUNT_ROW = {
    "id": SAMPLE_UUID,
    "account_number": "411001",
    "account_type": "tarjeta_credito",
    "account_currency": "CLP",
    "bank_name": "BCI",
    "active": True,
    "plan_de_cuentas": {"account_name": "Gastos Tarjeta"},
}

SAMPLE_BANK_ACCOUNT_RESPONSE = {
    "id": SAMPLE_UUID,
    "account_number": "411001",
    "account_type": "tarjeta_credito",
    "account_currency": "CLP",
    "bank_name": "BCI",
    "active": True,
    "account_name": "Gastos Tarjeta",
}


# ── Tests: GET / ──────────────────────────────────────────────────────────────

class TestListBankAccounts:
    def test_unauthenticated_returns_401(self):
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/bank-accounts/")
        assert resp.status_code == 401

    def test_family_can_list(self):
        with patch("backend.app.api.v1.bank_accounts.service.SupabaseRepository") as MockRepo:
            MockRepo.return_value.list_bank_accounts.return_value = [SAMPLE_BANK_ACCOUNT_ROW]
            app = _make_app()
            client = TestClient(app)
            resp = client.get("/api/v1/bank-accounts/", cookies=_family_cookie())
            assert resp.status_code == 200

    def test_returns_accounts_with_account_name(self):
        with patch("backend.app.api.v1.bank_accounts.service.SupabaseRepository") as MockRepo:
            MockRepo.return_value.list_bank_accounts.return_value = [SAMPLE_BANK_ACCOUNT_ROW]
            app = _make_app()
            client = TestClient(app)
            resp = client.get("/api/v1/bank-accounts/", cookies=_contador_cookie())
            assert resp.status_code == 200
            body = resp.json()
            assert len(body) == 1
            assert body[0]["account_name"] == "Gastos Tarjeta"
            assert body[0]["account_type"] == "tarjeta_credito"

    def test_returns_empty_list_when_none_registered(self):
        with patch("backend.app.api.v1.bank_accounts.service.SupabaseRepository") as MockRepo:
            MockRepo.return_value.list_bank_accounts.return_value = []
            app = _make_app()
            client = TestClient(app)
            resp = client.get("/api/v1/bank-accounts/", cookies=_contador_cookie())
            assert resp.status_code == 200
            assert resp.json() == []


# ── Tests: POST / ─────────────────────────────────────────────────────────────

class TestCreateBankAccount:
    def test_family_cannot_create(self):
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/bank-accounts/",
            json={"account_number": "411001", "account_type": "tarjeta_credito", "account_currency": "CLP"},
            cookies=_family_cookie(),
        )
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self):
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/bank-accounts/",
            json={"account_number": "411001", "account_type": "tarjeta_credito", "account_currency": "CLP"},
        )
        assert resp.status_code == 401

    def test_create_valid_account(self):
        with patch("backend.app.api.v1.bank_accounts.service.SupabaseRepository") as MockRepo:
            instance = MockRepo.return_value
            instance.plan_de_cuentas_exists.return_value = True
            instance.create_bank_account.return_value = {"id": SAMPLE_UUID}
            instance.get_bank_account_by_id.return_value = SAMPLE_BANK_ACCOUNT_ROW
            app = _make_app()
            client = TestClient(app)
            resp = client.post(
                "/api/v1/bank-accounts/",
                json={"account_number": "411001", "account_type": "tarjeta_credito", "account_currency": "CLP", "bank_name": "BCI"},
                cookies=_contador_cookie(),
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["account_number"] == "411001"
            assert body["account_name"] == "Gastos Tarjeta"

    def test_create_with_unknown_account_number_returns_400(self):
        """AC4: account_number not in plan_de_cuentas → HTTP 400."""
        with patch("backend.app.api.v1.bank_accounts.service.SupabaseRepository") as MockRepo:
            MockRepo.return_value.plan_de_cuentas_exists.return_value = False
            app = _make_app()
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/api/v1/bank-accounts/",
                json={"account_number": "NONEXISTENT", "account_type": "tarjeta_credito", "account_currency": "CLP"},
                cookies=_contador_cookie(),
            )
            assert resp.status_code == 400

    def test_create_invalid_account_type_returns_422(self):
        """Invalid account_type is rejected at schema validation level."""
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/bank-accounts/",
            json={"account_number": "411001", "account_type": "INVALID_TYPE", "account_currency": "CLP"},
            cookies=_contador_cookie(),
        )
        assert resp.status_code == 422

    def test_create_invalid_currency_returns_422(self):
        """Invalid currency is rejected at schema validation level."""
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/bank-accounts/",
            json={"account_number": "411001", "account_type": "tarjeta_credito", "account_currency": "EUR"},
            cookies=_contador_cookie(),
        )
        assert resp.status_code == 422


# ── Tests: PATCH /{id} ────────────────────────────────────────────────────────

class TestUpdateBankAccount:
    def test_family_cannot_update(self):
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.patch(
            f"/api/v1/bank-accounts/{SAMPLE_UUID}",
            json={"active": False},
            cookies=_family_cookie(),
        )
        assert resp.status_code == 403

    def test_deactivate_account(self):
        """AC6: Deactivating sets active=false."""
        deactivated_row = {**SAMPLE_BANK_ACCOUNT_ROW, "active": False}
        with patch("backend.app.api.v1.bank_accounts.service.SupabaseRepository") as MockRepo:
            instance = MockRepo.return_value
            instance.update_bank_account.return_value = {"id": SAMPLE_UUID}
            instance.get_bank_account_by_id.return_value = deactivated_row
            app = _make_app()
            client = TestClient(app)
            resp = client.patch(
                f"/api/v1/bank-accounts/{SAMPLE_UUID}",
                json={"active": False},
                cookies=_contador_cookie(),
            )
            assert resp.status_code == 200
            assert resp.json()["active"] is False

    def test_update_nonexistent_returns_404(self):
        with patch("backend.app.api.v1.bank_accounts.service.SupabaseRepository") as MockRepo:
            MockRepo.return_value.update_bank_account.return_value = None
            app = _make_app()
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.patch(
                f"/api/v1/bank-accounts/{SAMPLE_UUID}",
                json={"active": False},
                cookies=_contador_cookie(),
            )
            assert resp.status_code == 404

    def test_empty_patch_returns_400(self):
        """Patch with no valid fields returns 400."""
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.patch(
            f"/api/v1/bank-accounts/{SAMPLE_UUID}",
            json={},
            cookies=_contador_cookie(),
        )
        assert resp.status_code == 400


# ── Tests: BankAccount.from_supabase ─────────────────────────────────────────

class TestBankAccountFromSupabase:
    def test_extracts_account_name_from_join(self):
        from backend.app.api.v1.bank_accounts.schemas import BankAccount
        result = BankAccount.from_supabase(SAMPLE_BANK_ACCOUNT_ROW)
        assert result.account_name == "Gastos Tarjeta"
        assert str(result.id) == SAMPLE_UUID

    def test_handles_missing_plan_join(self):
        from backend.app.api.v1.bank_accounts.schemas import BankAccount
        row = {**SAMPLE_BANK_ACCOUNT_ROW, "plan_de_cuentas": None}
        result = BankAccount.from_supabase(row)
        assert result.account_name is None
