"""Tests for audit service and HTTP audit middleware — Story 1.5."""
import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.audit.service import log_write_operation
from backend.app.middleware import add_middleware


# ── Test app factory ───────────────────────────────────────────────────────


def make_audit_test_app() -> TestClient:
    """Mini FastAPI app with write and read endpoints, audit middleware active."""
    app = FastAPI()
    add_middleware(app)

    @app.post("/data")
    def write_data():
        return {"ok": True}

    @app.put("/data")
    def update_data():
        return {"ok": True}

    @app.delete("/data")
    def delete_data():
        return {"ok": True}

    @app.get("/data")
    def read_data():
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


# ── Unit tests: log_write_operation ───────────────────────────────────────


def test_log_write_operation_emits_correct_json(caplog):
    """AC1: log entry has all required fields with correct values."""
    with caplog.at_level(logging.INFO, logger="audit"):
        log_write_operation(
            method="POST",
            path="/api/v1/data",
            status_code=200,
            user_email="test@test.com",
        )
    assert len(caplog.records) == 1
    entry = json.loads(caplog.records[0].message)
    assert entry["method"] == "POST"
    assert entry["path"] == "/api/v1/data"
    assert entry["status_code"] == 200
    assert entry["user_email"] == "test@test.com"
    assert "timestamp" in entry
    # Timestamp must be ISO 8601 with UTC marker
    assert "T" in entry["timestamp"]
    assert entry["timestamp"].endswith("+00:00") or entry["timestamp"].endswith("Z")


def test_log_write_operation_null_email(caplog):
    """AC1: user_email can be None for unauthenticated writes."""
    with caplog.at_level(logging.INFO, logger="audit"):
        log_write_operation(
            method="DELETE",
            path="/api/v1/resource",
            status_code=403,
            user_email=None,
        )
    assert len(caplog.records) == 1
    entry = json.loads(caplog.records[0].message)
    assert entry["user_email"] is None


def test_log_write_operation_uses_audit_logger(caplog):
    """Entries are emitted to the 'audit' logger, not root logger."""
    with caplog.at_level(logging.INFO, logger="audit"):
        log_write_operation(method="PUT", path="/x", status_code=200)
    assert all(r.name == "audit" for r in caplog.records)


# ── Integration tests: audit middleware ───────────────────────────────────


def test_post_request_triggers_audit_entry(caplog):
    """AC1: POST request produces one audit log entry."""
    client = make_audit_test_app()
    with caplog.at_level(logging.INFO, logger="audit"):
        response = client.post("/data")
    assert response.status_code == 200
    audit_records = [r for r in caplog.records if r.name == "audit"]
    assert len(audit_records) == 1
    entry = json.loads(audit_records[0].message)
    assert entry["method"] == "POST"
    assert entry["path"] == "/data"
    assert entry["status_code"] == 200


def test_put_request_triggers_audit_entry(caplog):
    """AC1: PUT request produces one audit log entry."""
    client = make_audit_test_app()
    with caplog.at_level(logging.INFO, logger="audit"):
        client.put("/data")
    audit_records = [r for r in caplog.records if r.name == "audit"]
    assert len(audit_records) == 1
    assert json.loads(audit_records[0].message)["method"] == "PUT"


def test_delete_request_triggers_audit_entry(caplog):
    """AC1: DELETE request produces one audit log entry."""
    client = make_audit_test_app()
    with caplog.at_level(logging.INFO, logger="audit"):
        client.delete("/data")
    audit_records = [r for r in caplog.records if r.name == "audit"]
    assert len(audit_records) == 1
    assert json.loads(audit_records[0].message)["method"] == "DELETE"


def test_patch_request_triggers_audit_entry(caplog):
    """AC1: PATCH request produces one audit log entry."""
    app = FastAPI()
    add_middleware(app)

    @app.patch("/data")
    def patch_data():
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger="audit"):
        client.patch("/data")
    audit_records = [r for r in caplog.records if r.name == "audit"]
    assert len(audit_records) == 1
    assert json.loads(audit_records[0].message)["method"] == "PATCH"


def test_get_request_does_not_trigger_audit(caplog):
    """AC1: GET requests are NOT logged (reads only, not writes)."""
    client = make_audit_test_app()
    with caplog.at_level(logging.INFO, logger="audit"):
        client.get("/data")
    audit_records = [r for r in caplog.records if r.name == "audit"]
    assert len(audit_records) == 0


def test_unauthenticated_write_logs_null_email(caplog):
    """AC1: write without cookie produces audit entry with user_email=null."""
    client = make_audit_test_app()
    with caplog.at_level(logging.INFO, logger="audit"):
        client.post("/data")  # no access_token cookie
    audit_records = [r for r in caplog.records if r.name == "audit"]
    assert len(audit_records) == 1
    entry = json.loads(audit_records[0].message)
    assert entry["user_email"] is None


def test_audit_middleware_does_not_alter_response(caplog):
    """Middleware is transparent — response body and status unchanged."""
    client = make_audit_test_app()
    with caplog.at_level(logging.INFO, logger="audit"):
        response = client.post("/data")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_audit_entry_records_actual_status_code(caplog):
    """AC1: audit entry captures the real HTTP status code returned."""
    client = make_audit_test_app()
    with caplog.at_level(logging.INFO, logger="audit"):
        # POST to non-existent route → 404, but audit should still fire
        client.post("/nonexistent")
    audit_records = [r for r in caplog.records if r.name == "audit"]
    # 404 from FastAPI is handled by exception handler — middleware still runs
    assert len(audit_records) == 1
    entry = json.loads(audit_records[0].message)
    assert entry["status_code"] == 404
