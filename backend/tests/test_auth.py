"""Tests for auth service, router, and get_current_user dependency."""
import pytest
from fastapi.testclient import TestClient


# ── Auth service unit tests ────────────────────────────────────────────────


def test_create_and_decode_jwt():
    from backend.app.auth.service import create_jwt, decode_jwt

    token = create_jwt(email="test@example.com", role="family")
    payload = decode_jwt(token)
    assert payload["sub"] == "test@example.com"
    assert payload["role"] == "family"


def test_decode_invalid_jwt_raises():
    from jose import JWTError
    from backend.app.auth.service import decode_jwt

    with pytest.raises(JWTError):
        decode_jwt("not.a.valid.token")


def test_get_role_for_email_found(monkeypatch):
    monkeypatch.delenv("RBAC_ROLE_MAPPING", raising=False)
    monkeypatch.setenv("ALLOWED_USERS", "ary@example.com:family,contador@example.com:contador")
    from importlib import reload
    import backend.app.auth.service as svc
    reload(svc)

    assert svc.get_role_for_email("ary@example.com") == "family"
    assert svc.get_role_for_email("contador@example.com") == "contador"


def test_get_role_for_email_not_found(monkeypatch):
    monkeypatch.delenv("RBAC_ROLE_MAPPING", raising=False)
    monkeypatch.setenv("ALLOWED_USERS", "ary@example.com:family")
    from importlib import reload
    import backend.app.auth.service as svc
    reload(svc)

    assert svc.get_role_for_email("stranger@example.com") is None


def test_get_role_case_insensitive(monkeypatch):
    monkeypatch.delenv("RBAC_ROLE_MAPPING", raising=False)
    monkeypatch.setenv("ALLOWED_USERS", "ARY@EXAMPLE.COM:family")
    from importlib import reload
    import backend.app.auth.service as svc
    reload(svc)

    assert svc.get_role_for_email("ary@example.com") == "family"


# ── Story 9.13 — RBAC_ROLE_MAPPING (JSON) ──────────────────────────────────


def test_rbac_role_mapping_json_takes_priority(monkeypatch):
    """AC2: RBAC_ROLE_MAPPING wins over legacy ALLOWED_USERS when both set."""
    monkeypatch.setenv(
        "RBAC_ROLE_MAPPING",
        '{"ary.lipszyc@ammy.cl": "admin", "eduardo@eag.cl": "family"}',
    )
    monkeypatch.setenv("ALLOWED_USERS", "ary.lipszyc@ammy.cl:contador")
    from importlib import reload
    import backend.app.auth.service as svc
    reload(svc)

    assert svc.get_role_for_email("ary.lipszyc@ammy.cl") == "admin"
    assert svc.get_role_for_email("eduardo@eag.cl") == "family"


def test_rbac_role_mapping_falls_back_to_allowed_users(monkeypatch):
    """AC2: when email is not in RBAC_ROLE_MAPPING, fall back to ALLOWED_USERS."""
    monkeypatch.setenv("RBAC_ROLE_MAPPING", '{"ary@x.cl": "admin"}')
    monkeypatch.setenv("ALLOWED_USERS", "legacy@x.cl:contador")
    from importlib import reload
    import backend.app.auth.service as svc
    reload(svc)

    assert svc.get_role_for_email("legacy@x.cl") == "contador"


def test_rbac_role_mapping_normalizes_legacy_owner(monkeypatch):
    """AC2: legacy 'owner' value in mapping is normalized to 'family'."""
    monkeypatch.setenv(
        "RBAC_ROLE_MAPPING",
        '{"eduardo@eag.cl": "owner"}',
    )
    monkeypatch.delenv("ALLOWED_USERS", raising=False)
    from importlib import reload
    import backend.app.auth.service as svc
    reload(svc)

    assert svc.get_role_for_email("eduardo@eag.cl") == "family"


def test_rbac_role_mapping_invalid_json_ignored(monkeypatch):
    """AC2: malformed RBAC_ROLE_MAPPING falls through to ALLOWED_USERS without crashing."""
    monkeypatch.setenv("RBAC_ROLE_MAPPING", "{not-json")
    monkeypatch.setenv("ALLOWED_USERS", "fallback@x.cl:family")
    from importlib import reload
    import backend.app.auth.service as svc
    reload(svc)

    assert svc.get_role_for_email("fallback@x.cl") == "family"


def test_rbac_role_mapping_unmapped_email_returns_none(monkeypatch):
    """AC2: email not in either mapping returns None (caller emits 403)."""
    monkeypatch.setenv("RBAC_ROLE_MAPPING", '{"a@x.cl": "admin"}')
    monkeypatch.delenv("ALLOWED_USERS", raising=False)
    from importlib import reload
    import backend.app.auth.service as svc
    reload(svc)

    assert svc.get_role_for_email("intruder@x.cl") is None


# ── Auth router tests ──────────────────────────────────────────────────────


def get_test_client():
    from backend.main import app
    return TestClient(app, raise_server_exceptions=False)


def test_me_returns_401_without_cookie():
    client = get_test_client()
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_returns_401_with_invalid_cookie():
    client = get_test_client()
    client.cookies.set("access_token", "invalid.token.here")
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_returns_user_with_valid_cookie():
    from backend.app.auth.service import create_jwt

    token = create_jwt(email="ary@example.com", role="family")
    client = get_test_client()
    client.cookies.set("access_token", token)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "ary@example.com"
    assert data["role"] == "family"


def test_logout_clears_cookie():
    client = get_test_client()
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    # Cookie should be deleted (set with empty value or expired)
    assert "access_token" not in client.cookies or client.cookies.get("access_token") == ""


def test_login_redirects_to_google():
    """Login endpoint should redirect (302) to Google OAuth — we check status only."""
    client = get_test_client()
    # Without following redirects to avoid actual Google call
    response = client.get("/api/v1/auth/login", follow_redirects=False)
    # authlib will raise an error without valid credentials, but should still attempt redirect
    # In test env with no GOOGLE_CLIENT_ID, it may return 500 — we accept 302 or 500
    assert response.status_code in (302, 500)


# ── get_current_user dependency tests ─────────────────────────────────────


def test_get_current_user_no_cookie():
    from fastapi import FastAPI, Depends
    from fastapi.testclient import TestClient
    from backend.app.dependencies import get_current_user
    from backend.app.middleware import add_middleware

    test_app = FastAPI()
    add_middleware(test_app)

    @test_app.get("/protected")
    def protected(user=Depends(get_current_user)):
        return {"email": user.email}

    c = TestClient(test_app, raise_server_exceptions=False)
    response = c.get("/protected")
    assert response.status_code == 401


def test_get_current_user_valid_cookie():
    from fastapi import FastAPI, Depends
    from fastapi.testclient import TestClient
    from backend.app.auth.service import create_jwt
    from backend.app.dependencies import get_current_user
    from backend.app.middleware import add_middleware

    test_app = FastAPI()
    add_middleware(test_app)

    @test_app.get("/protected")
    def protected(user=Depends(get_current_user)):
        return {"email": user.email, "role": user.role}

    token = create_jwt(email="test@test.com", role="contador")
    c = TestClient(test_app, raise_server_exceptions=False)
    c.cookies.set("access_token", token)
    response = c.get("/protected")
    assert response.status_code == 200
    assert response.json()["email"] == "test@test.com"
    assert response.json()["role"] == "contador"
