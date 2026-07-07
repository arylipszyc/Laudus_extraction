"""Tests for sync API endpoints — GET /sync/status, POST /sync/trigger.

Story 9.16 (cleanup c4): el path Sheets fue removido. El sync ES el importer
Laudus→Beancount; el status deriva del import-log de ese importer. Este archivo
conserva la cobertura path-agnóstica (job-state, auth, RBAC, trigger) y la del
import-log; se borraron los tests del sync de Sheets (sync_api, get_date_range,
_run_sync/_run_backfill, replace_sheet).
"""
import time
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.auth.service import create_jwt
from backend.app.middleware import add_middleware


# ── Test app factory ──────────────────────────────────────────────────────


def make_sync_test_app() -> TestClient:
    from backend.app.api.v1.sync.router import router as sync_router

    app = FastAPI()
    add_middleware(app)
    app.include_router(sync_router, prefix="/api/v1")
    return TestClient(app, raise_server_exceptions=False)


def contador_token():
    return create_jwt(email="contador@test.com", role="contador")


def family_token():
    return create_jwt(email="family@test.com", role="family")


def admin_token():
    return create_jwt(email="ary@test.com", role="admin")


def reset_job_state():
    """Reset in-memory job state between tests."""
    import backend.app.api.v1.sync.service as svc
    with svc._job_lock:
        svc._current_job.update({
            "job_id": None,
            "status": "idle",
            "started_at": None,
            "completed_at": None,
            "error": None,
            "stats": None,
        })


def _no_import_log(monkeypatch, tmp_path):
    """Point the import-log at a nonexistent file → status reads null last_sync."""
    monkeypatch.setenv("LEDGER_IMPORT_LOG", str(tmp_path / "does-not-exist.jsonl"))


# ── GET /sync/status ──────────────────────────────────────────────────────


def test_sync_status_unauthenticated():
    """Unauthenticated → 401."""
    client = make_sync_test_app()
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 401


def test_sync_status_no_prior_sync(tmp_path, monkeypatch):
    """No prior importer run → null timestamps for both data types."""
    reset_job_state()
    _no_import_log(monkeypatch, tmp_path)
    client = make_sync_test_app()
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["balance_sheet"]["last_sync"] is None
    assert data["ledger"]["last_sync"] is None
    assert data["job_status"] == "idle"


def test_sync_status_family_can_read(tmp_path, monkeypatch):
    """GET /sync/status is accessible to family (authenticated read-only endpoint)."""
    _no_import_log(monkeypatch, tmp_path)
    client = make_sync_test_app()
    client.cookies.set("access_token", family_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200


def test_sync_status_reflects_failed_job_with_error():
    """GET /sync/status shows job_status=failed and error detail."""
    reset_job_state()
    import backend.app.api.v1.sync.service as svc
    with svc._job_lock:
        svc._current_job["status"] = "failed"
        svc._current_job["job_id"] = "failed-job-123"
        svc._current_job["error"] = "Connection timeout"

    client = make_sync_test_app()
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["job_status"] == "failed"
    assert data["error"] == "Connection timeout"
    reset_job_state()


def test_sync_status_reflects_running_job():
    """GET /sync/status reflects job_status=running while sync runs."""
    reset_job_state()
    import backend.app.api.v1.sync.service as svc
    with svc._job_lock:
        svc._current_job["status"] = "running"
        svc._current_job["job_id"] = "test-job-123"

    client = make_sync_test_app()
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["job_status"] == "running"
    assert data["job_id"] == "test-job-123"
    reset_job_state()


# ── Run stats ─────────────────────────────────────────────────────────────


def test_sync_status_stats_none_when_idle(tmp_path, monkeypatch):
    """stats is None when no sync has run."""
    reset_job_state()
    _no_import_log(monkeypatch, tmp_path)
    client = make_sync_test_app()
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    assert response.json()["stats"] is None


def test_sync_status_stats_none_on_failure():
    """stats is None when job failed (no partial stats on error)."""
    reset_job_state()
    import backend.app.api.v1.sync.service as svc
    with svc._job_lock:
        svc._current_job.update({
            "status": "failed",
            "job_id": "fail-job",
            "error": "Timeout",
            "stats": None,
        })

    client = make_sync_test_app()
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    assert response.json()["stats"] is None
    reset_job_state()


def test_sync_status_stats_present_after_completed_job():
    """stats object with record counts is present after a successful sync."""
    reset_job_state()
    import backend.app.api.v1.sync.service as svc
    with svc._job_lock:
        svc._current_job.update({
            "status": "done",
            "job_id": "done-job",
            "stats": {"balance_sheet_added": 3, "ledger_added": 7},
        })

    client = make_sync_test_app()
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["stats"]["balance_sheet_added"] == 3
    assert data["stats"]["ledger_added"] == 7
    reset_job_state()


# ── POST /sync/trigger ────────────────────────────────────────────────────


def test_sync_trigger_unauthenticated():
    """Unauthenticated → 401."""
    client = make_sync_test_app()
    response = client.post("/api/v1/sync/trigger")
    assert response.status_code == 401


def test_sync_trigger_family_forbidden():
    """Story 9.13 AC6: family → 403 on sync trigger (write endpoint)."""
    client = make_sync_test_app()
    client.cookies.set("access_token", family_token())
    response = client.post("/api/v1/sync/trigger")
    assert response.status_code == 403


def test_sync_trigger_contador_returns_triggered():
    """contador → 202 + {status: triggered, job_id: ...}."""
    reset_job_state()
    with patch("backend.app.api.v1.sync.service._run_laudus_import"):
        client = make_sync_test_app()
        client.cookies.set("access_token", contador_token())
        response = client.post("/api/v1/sync/trigger")
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "triggered"
    assert len(data["job_id"]) > 10  # UUID
    reset_job_state()


def test_sync_trigger_admin_returns_triggered():
    """Story 9.13 AC8: admin can trigger sync (inherits contador capabilities)."""
    reset_job_state()
    with patch("backend.app.api.v1.sync.service._run_laudus_import"):
        client = make_sync_test_app()
        client.cookies.set("access_token", admin_token())
        response = client.post("/api/v1/sync/trigger")
    assert response.status_code == 202
    assert response.json()["status"] == "triggered"
    reset_job_state()


def test_sync_trigger_returns_unique_job_ids():
    """Each trigger produces a unique job_id."""
    reset_job_state()
    with patch("backend.app.api.v1.sync.service._run_laudus_import"):
        client = make_sync_test_app()
        client.cookies.set("access_token", contador_token())
        r1 = client.post("/api/v1/sync/trigger")
    reset_job_state()
    with patch("backend.app.api.v1.sync.service._run_laudus_import"):
        client2 = make_sync_test_app()
        client2.cookies.set("access_token", contador_token())
        r2 = client2.post("/api/v1/sync/trigger")
    assert r1.json()["job_id"] != r2.json()["job_id"]
    reset_job_state()


def test_sync_trigger_returns_immediately():
    """Trigger returns before sync completes (non-blocking)."""
    reset_job_state()

    def slow(*args, **kwargs):
        time.sleep(10)

    with patch("backend.app.api.v1.sync.service._run_laudus_import", side_effect=slow):
        client = make_sync_test_app()
        client.cookies.set("access_token", contador_token())
        start = time.monotonic()
        response = client.post("/api/v1/sync/trigger")
        elapsed = time.monotonic() - start

    assert response.status_code == 202
    assert elapsed < 2.0
    reset_job_state()


def test_sync_trigger_already_running_returns_409():
    """Concurrent trigger while running → 409."""
    reset_job_state()
    import backend.app.api.v1.sync.service as svc
    with svc._job_lock:
        svc._current_job["status"] = "running"
        svc._current_job["job_id"] = "existing-job"

    client = make_sync_test_app()
    client.cookies.set("access_token", contador_token())
    response = client.post("/api/v1/sync/trigger")
    assert response.status_code == 409
    reset_job_state()


def test_sync_trigger_backfill_returns_triggered():
    """POST /trigger with mode=backfill + from_date → 202 + triggered."""
    reset_job_state()
    with patch("backend.app.api.v1.sync.service._run_laudus_import"):
        client = make_sync_test_app()
        client.cookies.set("access_token", contador_token())
        response = client.post(
            "/api/v1/sync/trigger",
            json={"mode": "backfill", "from_date": "2021-01-01"},
        )
    assert response.status_code == 202
    assert response.json()["status"] == "triggered"
    reset_job_state()


def test_sync_trigger_backfill_missing_from_date_returns_422():
    """backfill mode without from_date → 422."""
    reset_job_state()
    client = make_sync_test_app()
    client.cookies.set("access_token", contador_token())
    response = client.post("/api/v1/sync/trigger", json={"mode": "backfill"})
    assert response.status_code == 422
    reset_job_state()


def test_sync_trigger_backfill_invalid_from_date_returns_422():
    """backfill with non-ISO from_date → 422."""
    reset_job_state()
    client = make_sync_test_app()
    client.cookies.set("access_token", contador_token())
    response = client.post("/api/v1/sync/trigger", json={"mode": "backfill", "from_date": "not-a-date"})
    assert response.status_code == 422
    reset_job_state()


def test_sync_trigger_no_body_defaults_to_normal():
    """POST /trigger with no body defaults to normal mode → 202."""
    reset_job_state()
    with patch("backend.app.api.v1.sync.service._run_laudus_import"):
        client = make_sync_test_app()
        client.cookies.set("access_token", contador_token())
        response = client.post("/api/v1/sync/trigger")
    assert response.status_code == 202
    assert response.json()["status"] == "triggered"
    reset_job_state()


# ── Story 9.2 AC7: sync/status desde ledger/_meta/import-log.jsonl ────────────


def test_sync_status_jsonl_reads_last_laudus_run(tmp_path, monkeypatch):
    """balance_sheet and ledger last_sync derive from the last successful Laudus run."""
    log = tmp_path / "import-log.jsonl"
    log.write_text(
        '{"importer": "laudus", "timestamp": "2026-05-01T12:00:00+00:00", "records": 10, "success": true}\n'
        '{"importer": "laudus", "timestamp": "2026-05-10T08:30:00+00:00", "records": 12, "success": true}\n'
        '{"importer": "cartolas", "timestamp": "2026-05-15T09:00:00+00:00", "records": 3, "success": true}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("LEDGER_IMPORT_LOG", str(log))
    client = make_sync_test_app()
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert "2026-05-10" in data["balance_sheet"]["last_sync"]
    assert "2026-05-10" in data["ledger"]["last_sync"]


def test_sync_status_jsonl_ignores_failed_run(tmp_path, monkeypatch):
    """A later failed (rolled-back) run must not report a fresher last_sync."""
    log = tmp_path / "import-log.jsonl"
    log.write_text(
        '{"importer": "laudus", "timestamp": "2026-05-10T08:30:00+00:00", "success": true}\n'
        '{"importer": "laudus", "timestamp": "2026-05-12T08:30:00+00:00", "success": false, "error_msg": "bean-check failed"}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("LEDGER_IMPORT_LOG", str(log))
    client = make_sync_test_app()
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert "2026-05-10" in data["balance_sheet"]["last_sync"]
    assert "2026-05-10" in data["ledger"]["last_sync"]


def test_sync_status_jsonl_missing_file_returns_null(tmp_path, monkeypatch):
    """No import log (pre-bootstrap) → null per data type."""
    monkeypatch.setenv("LEDGER_IMPORT_LOG", str(tmp_path / "does-not-exist.jsonl"))
    client = make_sync_test_app()
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["balance_sheet"]["last_sync"] is None
    assert data["ledger"]["last_sync"] is None


def test_sync_status_jsonl_no_laudus_record_returns_null(tmp_path, monkeypatch):
    """Only cartolas records → balance_sheet/ledger last_sync null."""
    log = tmp_path / "import-log.jsonl"
    log.write_text(
        '{"importer": "cartolas", "timestamp": "2026-05-15T09:00:00+00:00", "records": 3}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("LEDGER_IMPORT_LOG", str(log))
    client = make_sync_test_app()
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["balance_sheet"]["last_sync"] is None
    assert data["ledger"]["last_sync"] is None


# ── Story 9.4: trigger despacha al importer Laudus→Beancount ──────────────────


def test_run_laudus_import_incremental_sets_done_with_stats(monkeypatch):
    """Corrida incremental exitosa → status=done, stats desde el resultado del importer."""
    import backend.app.api.v1.sync.service as svc
    reset_job_state()

    captured = {}

    def fake_run_import(mode="incremental", from_date=None, refresh_clone=None):
        captured["mode"] = mode
        captured["refresh_clone"] = refresh_clone
        return {"success": True, "jes_added": 42, "error_msg": None}

    monkeypatch.setattr("pipeline.importers.laudus_run.run_import", fake_run_import)

    job_id = "laudus-job"
    with svc._job_lock:
        svc._current_job.update({"job_id": job_id, "status": "running", "stats": None})
    svc._run_laudus_import(job_id, "incremental")

    with svc._job_lock:
        assert svc._current_job["status"] == "done"
        assert svc._current_job["stats"]["ledger_added"] == 42
    assert captured["mode"] == "incremental"
    # B5b (review batch 3): el refresh viaja como CALLBACK (corre dentro del lock de
    # run_import) — una regresión a "_refresh_ledger_clone(); run_import(...)" fallaría acá.
    assert captured["refresh_clone"] is svc._refresh_ledger_clone
    reset_job_state()


def test_run_laudus_import_backfill_passes_mode_and_from_date(monkeypatch):
    """Modo backfill → el importer recibe mode=backfill y from_date."""
    import backend.app.api.v1.sync.service as svc
    reset_job_state()

    captured = {}

    def fake_run_import(mode="incremental", from_date=None, refresh_clone=None):
        captured["mode"] = mode
        captured["from_date"] = from_date
        return {"success": True, "jes_added": 7, "error_msg": None}

    monkeypatch.setattr("pipeline.importers.laudus_run.run_import", fake_run_import)

    job_id = "laudus-backfill-job"
    with svc._job_lock:
        svc._current_job.update({"job_id": job_id, "status": "running", "stats": None})
    svc._run_laudus_import(job_id, "backfill", "2021-01-01")

    with svc._job_lock:
        assert svc._current_job["status"] == "done"
        assert svc._current_job["stats"]["ledger_added"] == 7
    assert captured["mode"] == "backfill"
    assert captured["from_date"] == "2021-01-01"
    reset_job_state()


def test_run_laudus_import_failure_sets_failed(monkeypatch):
    """Fallo del importer (p.ej. bean-check) → job_status=failed con error."""
    import backend.app.api.v1.sync.service as svc
    reset_job_state()

    monkeypatch.setattr(
        "pipeline.importers.laudus_run.run_import",
        lambda mode="incremental", from_date=None, refresh_clone=None: {"success": False, "jes_added": 0, "error_msg": "bean-check failed: boom"},
    )

    job_id = "laudus-fail-job"
    with svc._job_lock:
        svc._current_job.update({"job_id": job_id, "status": "running", "stats": None})
    svc._run_laudus_import(job_id, "incremental")

    with svc._job_lock:
        assert svc._current_job["status"] == "failed"
        assert "bean-check failed" in svc._current_job["error"]
    reset_job_state()


# ── get_date_range: ventana solapada (la usa el importer Laudus, laudus_run.py) ──

from datetime import date

from dateutil.relativedelta import relativedelta

from pipeline.utils.dates import get_date_range


def test_get_date_range_recent_watermark_reaches_back_window():
    """Watermark reciente → date_from retrocede al inicio de ventana, no a watermark+1."""
    today = date(2026, 6, 15)
    date_from, date_to = get_date_range("2026-06-15", today=today, overlap_months=13)
    assert date_to == today
    assert date_from == today - relativedelta(months=13)  # 2025-05-15


def test_get_date_range_old_watermark_keeps_history():
    """Watermark más viejo que la ventana → date_from = watermark+1 (no perder histórico)."""
    today = date(2026, 6, 15)
    date_from, _ = get_date_range("2023-01-01", today=today, overlap_months=13)
    assert date_from == date(2023, 1, 2)


def test_get_date_range_date_to_is_today():
    """date_to siempre es hoy."""
    today = date(2026, 6, 15)
    _, date_to = get_date_range("2026-06-15", today=today)
    assert date_to == today


def test_get_date_range_env_var_controls_window(monkeypatch):
    """SYNC_OVERLAP_WINDOW_MONTHS controla el tamaño de la ventana."""
    monkeypatch.setenv("SYNC_OVERLAP_WINDOW_MONTHS", "3")
    today = date(2026, 6, 15)
    date_from, _ = get_date_range("2026-06-15", today=today)
    assert date_from == today - relativedelta(months=3)  # 2026-03-15
