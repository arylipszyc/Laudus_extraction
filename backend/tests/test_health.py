"""Tests for health endpoint and middleware."""
import pytest
from fastapi.testclient import TestClient


def get_test_client():
    from backend.main import app
    return TestClient(app)


def test_health_returns_200():
    client = get_test_client()
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_returns_ok_json():
    client = get_test_client()
    response = client.get("/api/v1/health")
    assert response.json() == {"status": "ok"}


def test_docs_accessible():
    client = get_test_client()
    response = client.get("/docs")
    assert response.status_code == 200


def test_unhandled_exception_returns_error_json():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.middleware import add_middleware

    test_app = FastAPI()
    add_middleware(test_app)

    @test_app.get("/boom")
    async def boom():
        raise RuntimeError("something went wrong")

    c = TestClient(test_app, raise_server_exceptions=False)
    response = c.get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "INTERNAL_ERROR"


def test_cors_header_present():
    client = get_test_client()
    response = client.get(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173"},
    )
    # CORS header present when origin matches allow list
    assert "access-control-allow-origin" in response.headers
