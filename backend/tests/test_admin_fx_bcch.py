"""Tests del endpoint admin POST /api/v1/admin/fx-bcch/refetch — Story 9.10."""
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.auth.service import create_jwt
from backend.app.middleware import add_middleware
from pipeline.importers.fx_bcch_eom import (
    NoPublicationFoundError,
    RefetchResult,
    RefetchValidationError,
)


def _make_app():
    from backend.app.api.v1.admin.router import router as admin_router
    app = FastAPI()
    add_middleware(app)
    app.include_router(admin_router, prefix="/api/v1")
    return app


def _admin_cookie():
    return {"access_token": create_jwt(email="ary@test.com", role="admin")}


def _contador_cookie():
    return {"access_token": create_jwt(email="contador@test.com", role="contador")}


def _family_cookie():
    return {"access_token": create_jwt(email="eduardo@eag.cl", role="family")}


class TestRBAC:
    def test_unauthenticated_returns_401(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.post("/api/v1/admin/fx-bcch/refetch?year_month=2026-04")
        assert resp.status_code == 401

    def test_contador_returns_403(self):
        # Story 9.13: fx-bcch/refetch is admin-only — contador is denied.
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/admin/fx-bcch/refetch?year_month=2026-04",
            cookies=_contador_cookie(),
        )
        assert resp.status_code == 403

    def test_family_returns_403(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/admin/fx-bcch/refetch?year_month=2026-04",
            cookies=_family_cookie(),
        )
        assert resp.status_code == 403


class TestEndpointBehavior:
    def test_admin_fetched_returns_200_with_rate(self):
        fake = RefetchResult(
            status="fetched", year_month="2026-04", bcch_date="2026-04-30",
            rate_clp_per_usd=950.45, source="mindicador-dolar-observado",
        )
        with patch("backend.app.api.v1.admin.router.refetch_eom", return_value=fake):
            client = TestClient(_make_app())
            resp = client.post(
                "/api/v1/admin/fx-bcch/refetch?year_month=2026-04",
                cookies=_admin_cookie(),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "fetched"
        assert body["year_month"] == "2026-04"
        assert body["bcch_date"] == "2026-04-30"
        assert body["rate_clp_per_usd"] == 950.45
        assert body["source"] == "mindicador-dolar-observado"

    def test_dedup_returns_200_with_skipped(self):
        fake = RefetchResult(
            status="skipped", year_month="2026-04", bcch_date="2026-04-30",
            rate_clp_per_usd=950.45, source="mindicador-dolar-observado",
        )
        with patch("backend.app.api.v1.admin.router.refetch_eom", return_value=fake):
            client = TestClient(_make_app())
            resp = client.post(
                "/api/v1/admin/fx-bcch/refetch?year_month=2026-04",
                cookies=_admin_cookie(),
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "skipped"

    def test_validation_error_returns_400(self):
        with patch(
            "backend.app.api.v1.admin.router.refetch_eom",
            side_effect=RefetchValidationError("year_month 2026-06 es futuro"),
        ):
            client = TestClient(_make_app())
            resp = client.post(
                "/api/v1/admin/fx-bcch/refetch?year_month=2026-06",
                cookies=_admin_cookie(),
            )
        assert resp.status_code == 400
        assert "futuro" in resp.json()["error"]["message"]

    def test_no_publication_returns_502(self):
        with patch(
            "backend.app.api.v1.admin.router.refetch_eom",
            side_effect=NoPublicationFoundError("sin publicación BCCh tras 7 días"),
        ):
            client = TestClient(_make_app())
            resp = client.post(
                "/api/v1/admin/fx-bcch/refetch?year_month=2026-04",
                cookies=_admin_cookie(),
            )
        assert resp.status_code == 502

    def test_missing_year_month_returns_422(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.post("/api/v1/admin/fx-bcch/refetch", cookies=_admin_cookie())
        assert resp.status_code == 422
