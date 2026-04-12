"""Tests for require_role() RBAC dependency — Story 1.4."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from jose import jwt

from backend.app.auth.service import create_jwt
from backend.app.dependencies import get_current_user, require_role
from backend.app.middleware import add_middleware


# ── Test app factory ───────────────────────────────────────────────────────


def make_test_app() -> TestClient:
    """Mini FastAPI app with a single write-protected endpoint."""
    app = FastAPI()
    add_middleware(app)

    @app.post("/write-resource")
    def write_endpoint(user=Depends(require_role(["contador"]))):
        return {"ok": True, "role": user.role}

    @app.get("/read-resource")
    def read_endpoint(user=Depends(require_role(["owner", "contador"]))):
        return {"ok": True, "role": user.role}

    return TestClient(app, raise_server_exceptions=False)


def make_expired_token() -> str:
    """Create a JWT that expired 1 second ago."""
    payload = {
        "sub": "test@test.com",
        "role": "owner",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    return jwt.encode(payload, "dev-secret-change-in-production", algorithm="HS256")


# ── require_role unit tests ────────────────────────────────────────────────


def test_owner_calling_write_endpoint_gets_403():
    """AC2: owner cannot call write endpoints."""
    client = make_test_app()
    token = create_jwt(email="owner@test.com", role="owner")
    client.cookies.set("access_token", token)
    response = client.post("/write-resource")
    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "HTTP_403"
    assert "Insufficient permissions" in error["message"]


def test_contador_calling_write_endpoint_gets_200():
    """AC3: contador can call write endpoints."""
    client = make_test_app()
    token = create_jwt(email="contador@test.com", role="contador")
    client.cookies.set("access_token", token)
    response = client.post("/write-resource")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["role"] == "contador"


def test_owner_calling_read_endpoint_gets_200():
    """AC3: owner can call read endpoints (both roles allowed)."""
    client = make_test_app()
    token = create_jwt(email="owner@test.com", role="owner")
    client.cookies.set("access_token", token)
    response = client.get("/read-resource")
    assert response.status_code == 200
    assert response.json()["role"] == "owner"


def test_missing_cookie_gets_401():
    """AC1: missing cookie returns 401."""
    client = make_test_app()
    response = client.post("/write-resource")
    assert response.status_code == 401


def test_expired_jwt_gets_401():
    """AC4: expired JWT returns 401."""
    client = make_test_app()
    client.cookies.set("access_token", make_expired_token())
    response = client.post("/write-resource")
    assert response.status_code == 401


def test_invalid_token_gets_401():
    """AC1: valid JWT structure but wrong signature returns 401."""
    # Use a properly-formed 3-segment JWT with an invalid signature to exercise
    # the actual signature-verification failure path (not just format rejection)
    bad_token = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiJ0ZXN0QHRlc3QuY29tIiwicm9sZSI6Im93bmVyIn0"
        ".AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    )
    client = make_test_app()
    client.cookies.set("access_token", bad_token)
    response = client.post("/write-resource")
    assert response.status_code == 401


def test_unknown_role_gets_401():
    """P2: JWT with unrecognized role value is rejected at authentication, not authorization."""
    payload = {
        "sub": "attacker@test.com",
        "role": "superadmin",
        "exp": datetime.now(timezone.utc) + timedelta(hours=8),
    }
    token = jwt.encode(payload, "dev-secret-change-in-production", algorithm="HS256")
    client = make_test_app()
    client.cookies.set("access_token", token)
    # Unknown role → get_current_user raises 401 (invalid claims), not 403
    response = client.post("/write-resource")
    assert response.status_code == 401


def test_require_role_returns_user_session():
    """require_role returns the UserSession on success."""
    client = make_test_app()
    token = create_jwt(email="contador@test.com", role="contador")
    client.cookies.set("access_token", token)
    response = client.post("/write-resource")
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "contador"


def test_require_role_multiple_allowed_roles():
    """Both roles can access when both are listed."""
    client = make_test_app()

    # owner allowed
    token_owner = create_jwt(email="owner@test.com", role="owner")
    client_owner = make_test_app()
    client_owner.cookies.set("access_token", token_owner)
    assert client_owner.get("/read-resource").status_code == 200

    # contador allowed
    token_contador = create_jwt(email="contador@test.com", role="contador")
    client_contador = make_test_app()
    client_contador.cookies.set("access_token", token_contador)
    assert client_contador.get("/read-resource").status_code == 200
