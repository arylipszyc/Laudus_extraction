"""Tests for require_role() RBAC dependency — Story 1.4 + Story 9.13 (3 roles)."""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from jose import jwt

from backend.app.auth.service import create_jwt
from backend.app.dependencies import require_role
from backend.app.middleware import add_middleware


# ── Test app factory ───────────────────────────────────────────────────────


def make_test_app() -> TestClient:
    """Mini FastAPI app exercising the 3-role matrix from Story 9.13."""
    app = FastAPI()
    add_middleware(app)

    @app.post("/contador-write")
    def contador_write(user=Depends(require_role(["contador", "admin"]))):
        return {"ok": True, "role": user.role}

    @app.post("/admin-only")
    def admin_only(user=Depends(require_role(["admin"]))):
        return {"ok": True, "role": user.role}

    @app.get("/all-authenticated")
    def all_authenticated(user=Depends(require_role(["family", "contador", "admin"]))):
        return {"ok": True, "role": user.role}

    return TestClient(app, raise_server_exceptions=False)


def make_expired_token() -> str:
    """Create a JWT that expired 1 second ago."""
    payload = {
        "sub": "test@test.com",
        "role": "family",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    return jwt.encode(payload, "dev-secret-change-in-production", algorithm="HS256")


# ── 3-role matrix tests (AC9) ──────────────────────────────────────────────


def test_family_blocked_from_contador_write():
    """AC6 + AC9: family cannot call contador-write endpoints."""
    client = make_test_app()
    client.cookies.set("access_token", create_jwt(email="family@test.com", role="family"))
    response = client.post("/contador-write")
    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "HTTP_403"
    assert "Insufficient permissions" in error["message"]


def test_contador_can_call_contador_write():
    """AC7 + AC9: contador can call contador-write endpoints."""
    client = make_test_app()
    client.cookies.set("access_token", create_jwt(email="contador@test.com", role="contador"))
    response = client.post("/contador-write")
    assert response.status_code == 200
    assert response.json()["role"] == "contador"


def test_admin_can_call_contador_write():
    """AC8 + AC9: admin inherits everything contador can do."""
    client = make_test_app()
    client.cookies.set("access_token", create_jwt(email="ary@test.com", role="admin"))
    response = client.post("/contador-write")
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_family_blocked_from_admin_only():
    """AC9: family cannot reach admin-only endpoints."""
    client = make_test_app()
    client.cookies.set("access_token", create_jwt(email="family@test.com", role="family"))
    assert client.post("/admin-only").status_code == 403


def test_contador_blocked_from_admin_only():
    """AC7 + AC9: contador cannot reach admin-only endpoints."""
    client = make_test_app()
    client.cookies.set("access_token", create_jwt(email="contador@test.com", role="contador"))
    assert client.post("/admin-only").status_code == 403


def test_admin_can_call_admin_only():
    """AC8 + AC9: admin can reach admin-only endpoints."""
    client = make_test_app()
    client.cookies.set("access_token", create_jwt(email="ary@test.com", role="admin"))
    response = client.post("/admin-only")
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_all_three_roles_can_call_authenticated_read():
    """AC3 + AC6: dashboards Epic 3 visible para los 3 roles."""
    for role in ("family", "contador", "admin"):
        client = make_test_app()
        client.cookies.set("access_token", create_jwt(email=f"{role}@test.com", role=role))
        assert client.get("/all-authenticated").status_code == 200


# ── Legacy shim (AC2 / Task 4) ─────────────────────────────────────────────


def test_legacy_owner_jwt_treated_as_family(caplog):
    """AC2 Task 4: JWTs minted with role='owner' (pre-9.13) are mapped to family."""
    client = make_test_app()
    legacy_token = create_jwt(email="eduardo@eag.cl", role="owner")
    client.cookies.set("access_token", legacy_token)

    with caplog.at_level(logging.WARNING, logger="backend.app.dependencies"):
        # family role allowed on /all-authenticated; legacy owner should map to family.
        response = client.get("/all-authenticated")

    assert response.status_code == 200
    assert response.json()["role"] == "family"
    assert any("LEGACY_ROLE_OWNER_DETECTED" in rec.message for rec in caplog.records)


def test_legacy_owner_blocked_from_contador_write():
    """Shim maps owner→family, so legacy JWTs lose contador-only access (correct)."""
    client = make_test_app()
    client.cookies.set("access_token", create_jwt(email="eduardo@eag.cl", role="owner"))
    assert client.post("/contador-write").status_code == 403


# ── Auth gating (preserved from Story 1.4) ─────────────────────────────────


def test_missing_cookie_gets_401():
    client = make_test_app()
    assert client.post("/contador-write").status_code == 401


def test_expired_jwt_gets_401():
    client = make_test_app()
    client.cookies.set("access_token", make_expired_token())
    assert client.post("/contador-write").status_code == 401


def test_invalid_token_gets_401():
    bad_token = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiJ0ZXN0QHRlc3QuY29tIiwicm9sZSI6ImZhbWlseSJ9"
        ".AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    )
    client = make_test_app()
    client.cookies.set("access_token", bad_token)
    assert client.post("/contador-write").status_code == 401


def test_unknown_role_gets_401():
    """JWT with unrecognized role value is rejected at authentication, not authorization."""
    payload = {
        "sub": "attacker@test.com",
        "role": "superadmin",
        "exp": datetime.now(timezone.utc) + timedelta(hours=8),
    }
    token = jwt.encode(payload, "dev-secret-change-in-production", algorithm="HS256")
    client = make_test_app()
    client.cookies.set("access_token", token)
    assert client.post("/contador-write").status_code == 401


# ── Defense-in-depth logging (AC5) ────────────────────────────────────────


def test_rbac_denied_logs_structured_event(caplog):
    """AC5: 403 emits RBAC_DENIED with user_email, user_role, endpoint, required_roles."""
    client = make_test_app()
    client.cookies.set("access_token", create_jwt(email="family@test.com", role="family"))

    with caplog.at_level(logging.WARNING, logger="backend.app.dependencies"):
        client.post("/admin-only")

    rbac_logs = [rec for rec in caplog.records if "RBAC_DENIED" in rec.message]
    assert len(rbac_logs) == 1
    msg = rbac_logs[0].message
    assert "user_email=family@test.com" in msg
    assert "user_role=family" in msg
    assert "/admin-only" in msg
    assert "['admin']" in msg
