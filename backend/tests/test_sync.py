"""Tests for sync API endpoints — Stories 2.1 + 2.2."""
import time
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.auth.service import create_jwt
from backend.app.dependencies import get_repository
from backend.app.middleware import add_middleware


# ── Test app factory ──────────────────────────────────────────────────────


def make_sync_test_app(mock_repo=None) -> TestClient:
    """Mini FastAPI app with sync router and mocked repository."""
    from backend.app.api.v1.sync.router import router as sync_router

    app = FastAPI()
    add_middleware(app)
    app.include_router(sync_router, prefix="/api/v1")

    if mock_repo is not None:
        app.dependency_overrides[get_repository] = lambda: mock_repo

    return TestClient(app, raise_server_exceptions=False)


def make_mock_repo(date_range_records=None, balance_sheet_records=None):
    """Return a MagicMock repository routing get_records by sheet name.

    - date_range_records: records returned for get_records("date_range")
    - balance_sheet_records: records returned for get_records("balance_sheet")
    - Any other sheet name returns [].
    """
    repo = MagicMock()
    _date_range = date_range_records if date_range_records is not None else []
    _balance_sheet = balance_sheet_records if balance_sheet_records is not None else []

    def _get_records(sheet_name):
        if sheet_name == "balance_sheet":
            return _balance_sheet
        if sheet_name == "date_range":
            return _date_range
        return []

    repo.get_records.side_effect = _get_records
    return repo


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


# ── GET /sync/status ──────────────────────────────────────────────────────


def test_sync_status_unauthenticated():
    """AC4: unauthenticated → 401."""
    client = make_sync_test_app(mock_repo=make_mock_repo())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 401


def test_sync_status_no_prior_sync():
    """AC1: no prior sync → null timestamps for both data types."""
    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["balance_sheet"]["last_sync"] is None
    assert data["ledger"]["last_sync"] is None
    assert data["job_status"] == "idle"


def test_sync_status_with_prior_sync():
    """AC1: prior sync → ISO 8601 timestamps from respective sheets."""
    mock_repo = make_mock_repo(
        balance_sheet_records=[{"query_date": "2026-04-10", "account_id": 1}],
        date_range_records=[{"dateTo": "2026-04-10", "dateFrom": "2026-04-01"}],
    )
    client = make_sync_test_app(mock_repo=mock_repo)
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["balance_sheet"]["last_sync"] is not None
    assert "2026-04-10" in data["balance_sheet"]["last_sync"]
    assert data["ledger"]["last_sync"] is not None
    assert "2026-04-10" in data["ledger"]["last_sync"]


def test_sync_status_family_can_read():
    """GET /sync/status is accessible to family (authenticated read-only endpoint)."""
    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", family_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200


def test_sync_status_multiple_date_range_records_uses_latest():
    """AC1: multiple date_range records → ledger.last_sync uses most recent dateTo."""
    mock_repo = make_mock_repo(
        date_range_records=[
            {"dateTo": "2026-03-31", "dateFrom": "2026-03-01"},
            {"dateTo": "2026-04-10", "dateFrom": "2026-04-01"},
        ]
    )
    client = make_sync_test_app(mock_repo=mock_repo)
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert "2026-04-10" in data["ledger"]["last_sync"]


# ── POST /sync/trigger ────────────────────────────────────────────────────


def test_sync_trigger_unauthenticated():
    """AC4: unauthenticated → 401."""
    client = make_sync_test_app(mock_repo=make_mock_repo())
    response = client.post("/api/v1/sync/trigger")
    assert response.status_code == 401


def test_sync_trigger_family_forbidden():
    """Story 9.13 AC6: family → 403 on sync trigger (write endpoint)."""
    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", family_token())
    response = client.post("/api/v1/sync/trigger")
    assert response.status_code == 403


def test_sync_trigger_contador_returns_triggered():
    """AC2 + Story 9.13 AC7: contador → 202 + {status: triggered, job_id: ...}."""
    reset_job_state()
    with patch("backend.app.api.v1.sync.service._run_sync"):
        client = make_sync_test_app(mock_repo=make_mock_repo())
        client.cookies.set("access_token", contador_token())
        response = client.post("/api/v1/sync/trigger")
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "triggered"
    assert "job_id" in data
    assert len(data["job_id"]) > 10  # UUID


def test_sync_trigger_admin_returns_triggered():
    """Story 9.13 AC8: admin can trigger sync (inherits contador capabilities)."""
    reset_job_state()
    with patch("backend.app.api.v1.sync.service._run_sync"):
        client = make_sync_test_app(mock_repo=make_mock_repo())
        client.cookies.set("access_token", admin_token())
        response = client.post("/api/v1/sync/trigger")
    assert response.status_code == 202
    assert response.json()["status"] == "triggered"


def test_sync_trigger_returns_unique_job_ids():
    """AC2: each trigger produces a unique job_id."""
    reset_job_state()
    with patch("backend.app.api.v1.sync.service._run_sync"):
        client = make_sync_test_app(mock_repo=make_mock_repo())
        client.cookies.set("access_token", contador_token())
        r1 = client.post("/api/v1/sync/trigger")

    reset_job_state()
    with patch("backend.app.api.v1.sync.service._run_sync"):
        client2 = make_sync_test_app(mock_repo=make_mock_repo())
        client2.cookies.set("access_token", contador_token())
        r2 = client2.post("/api/v1/sync/trigger")

    assert r1.json()["job_id"] != r2.json()["job_id"]


def test_sync_trigger_returns_immediately():
    """AC2: trigger returns before sync completes (non-blocking)."""
    reset_job_state()

    def slow_sync(job_id, repo):
        time.sleep(10)

    with patch("backend.app.api.v1.sync.service._run_sync", side_effect=slow_sync):
        client = make_sync_test_app(mock_repo=make_mock_repo())
        client.cookies.set("access_token", contador_token())
        start = time.monotonic()
        response = client.post("/api/v1/sync/trigger")
        elapsed = time.monotonic() - start

    assert response.status_code == 202
    assert elapsed < 2.0


def test_sync_trigger_already_running_returns_409():
    """Concurrent trigger while running → 409."""
    reset_job_state()

    import backend.app.api.v1.sync.service as svc
    with svc._job_lock:
        svc._current_job["status"] = "running"
        svc._current_job["job_id"] = "existing-job"

    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", contador_token())
    response = client.post("/api/v1/sync/trigger")
    assert response.status_code == 409

    reset_job_state()


def test_sync_status_reflects_failed_job_with_error():
    """P4: GET /sync/status shows job_status=failed and error detail."""
    reset_job_state()

    import backend.app.api.v1.sync.service as svc
    with svc._job_lock:
        svc._current_job["status"] = "failed"
        svc._current_job["job_id"] = "failed-job-123"
        svc._current_job["error"] = "Connection timeout"

    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["job_status"] == "failed"
    assert data["error"] == "Connection timeout"

    reset_job_state()


def test_sync_status_reflects_running_job():
    """AC5: GET /sync/status reflects job_status=running while sync runs."""
    reset_job_state()

    import backend.app.api.v1.sync.service as svc
    with svc._job_lock:
        svc._current_job["status"] = "running"
        svc._current_job["job_id"] = "test-job-123"

    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["job_status"] == "running"
    assert data["job_id"] == "test-job-123"

    reset_job_state()


# ── Story 2.2: Per-type last_sync (AC6) ──────────────────────────────────


def test_sync_status_per_type_last_sync_different_dates():
    """AC6: balance_sheet.last_sync and ledger.last_sync tracked independently."""
    mock_repo = make_mock_repo(
        balance_sheet_records=[{"query_date": "2026-03-31", "account_id": 1}],
        date_range_records=[{"dateTo": "2026-04-10", "dateFrom": "2026-04-01"}],
    )
    client = make_sync_test_app(mock_repo=mock_repo)
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert "2026-03-31" in data["balance_sheet"]["last_sync"]
    assert "2026-04-10" in data["ledger"]["last_sync"]


def test_sync_status_balance_sheet_reads_from_balance_sheet_tab():
    """AC6: balance_sheet.last_sync reads query_date from balance_sheet tab, not date_range."""
    mock_repo = make_mock_repo(
        balance_sheet_records=[
            {"query_date": "2026-02-28", "account_id": 1},
            {"query_date": "2026-03-31", "account_id": 2},
        ],
        date_range_records=[],
    )
    client = make_sync_test_app(mock_repo=mock_repo)
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    # Should pick max query_date from balance_sheet tab
    assert "2026-03-31" in data["balance_sheet"]["last_sync"]
    # No date_range records → ledger last_sync is None
    assert data["ledger"]["last_sync"] is None


# ── Story 2.2: Run stats (AC7) ────────────────────────────────────────────


def test_sync_status_stats_none_when_idle():
    """AC7: stats is None when no sync has run."""
    reset_job_state()
    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["stats"] is None


def test_sync_status_stats_none_on_failure():
    """AC7: stats is None when job failed (no partial stats on error)."""
    reset_job_state()
    import backend.app.api.v1.sync.service as svc
    with svc._job_lock:
        svc._current_job.update({
            "status": "failed",
            "job_id": "fail-job",
            "error": "Timeout",
            "stats": None,
        })

    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["stats"] is None

    reset_job_state()


def test_sync_status_stats_present_after_completed_job():
    """AC7: stats object with record counts is present after a successful sync."""
    reset_job_state()
    import backend.app.api.v1.sync.service as svc
    with svc._job_lock:
        svc._current_job.update({
            "status": "done",
            "job_id": "done-job",
            "stats": {"balance_sheet_added": 3, "ledger_added": 7},
        })

    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["stats"] is not None
    assert data["stats"]["balance_sheet_added"] == 3
    assert data["stats"]["ledger_added"] == 7

    reset_job_state()


def test_run_sync_sets_failed_state_on_sync_error():
    """P1: _run_sync sets status=failed, error=str(exc), stats=None when sync_api() raises."""
    import backend.app.api.v1.sync.service as svc
    reset_job_state()

    mock_repo = MagicMock()
    mock_repo.get_records.return_value = []

    job_id = "fail-test-job"
    with svc._job_lock:
        svc._current_job.update({"job_id": job_id, "status": "running", "stats": None})

    with patch("pipeline.sync.sync_api", side_effect=RuntimeError("Sheets write failed")):
        svc._run_sync(job_id, mock_repo)

    with svc._job_lock:
        assert svc._current_job["status"] == "failed"
        assert svc._current_job["error"] == "Sheets write failed"
        assert svc._current_job["stats"] is None


def test_run_sync_captures_stats_on_success():
    """AC7: _run_sync counts records before/after sync_api() and stores stats."""
    import backend.app.api.v1.sync.service as svc
    reset_job_state()

    mock_repo = MagicMock()
    # Sequential calls: balance_sheet before, ledger before, balance_sheet after, ledger after
    mock_repo.get_records.side_effect = [
        [{"query_date": "2026-04-10"}] * 5,           # balance_sheet before: 5 records
        [{"journalentryid": i} for i in range(10)],   # ledger before: 10 records
        [{"query_date": "2026-04-10"}] * 7,           # balance_sheet after: 7 records
        [{"journalentryid": i} for i in range(13)],   # ledger after: 13 records
    ]

    job_id = "stats-test-job"
    with svc._job_lock:
        svc._current_job.update({"job_id": job_id, "status": "running", "stats": None})

    with patch("pipeline.sync.sync_api"):
        svc._run_sync(job_id, mock_repo)

    with svc._job_lock:
        stats = svc._current_job.get("stats")
        status = svc._current_job["status"]

    assert status == "done"
    assert stats is not None
    assert stats["balance_sheet_added"] == 2    # 7 - 5
    assert stats["ledger_added"] == 3           # 13 - 10


# ── Story 2.3: Backfill mode — POST /trigger ─────────────────────────────────


def test_sync_trigger_backfill_returns_triggered():
    """AC1: POST /trigger with mode=backfill + from_date → 202 + triggered."""
    reset_job_state()
    with patch("backend.app.api.v1.sync.service._run_backfill"):
        client = make_sync_test_app(mock_repo=make_mock_repo())
        client.cookies.set("access_token", contador_token())
        response = client.post(
            "/api/v1/sync/trigger",
            json={"mode": "backfill", "from_date": "2021-01-01"},
        )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "triggered"
    assert "job_id" in data
    reset_job_state()


def test_sync_trigger_backfill_missing_from_date_returns_422():
    """AC3: backfill mode without from_date → 422."""
    reset_job_state()
    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", contador_token())
    response = client.post("/api/v1/sync/trigger", json={"mode": "backfill"})
    assert response.status_code == 422
    reset_job_state()


def test_sync_trigger_backfill_invalid_from_date_returns_422():
    """P6: backfill with non-ISO from_date → 422 (Pydantic validator)."""
    reset_job_state()
    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", contador_token())
    response = client.post("/api/v1/sync/trigger", json={"mode": "backfill", "from_date": "not-a-date"})
    assert response.status_code == 422
    reset_job_state()


def test_sync_trigger_no_body_defaults_to_normal():
    """AC4: POST /trigger with no body defaults to normal mode → 202."""
    reset_job_state()
    with patch("backend.app.api.v1.sync.service._run_sync"):
        client = make_sync_test_app(mock_repo=make_mock_repo())
        client.cookies.set("access_token", contador_token())
        response = client.post("/api/v1/sync/trigger")
    assert response.status_code == 202
    assert response.json()["status"] == "triggered"
    reset_job_state()


# ── Story 2.3: _run_backfill unit tests ──────────────────────────────────────


def test_run_backfill_sets_done_state_with_stats():
    """AC5: _run_backfill sets status=done and stats from run_backfill result."""
    import backend.app.api.v1.sync.service as svc
    reset_job_state()

    mock_repo = MagicMock()
    job_id = "backfill-test-job"
    with svc._job_lock:
        svc._current_job.update({"job_id": job_id, "status": "running"})

    with patch(
        "backend.app.api.v1.sync.backfill.run_backfill",
        return_value={"balance_sheet_upserted": 120, "ledger_upserted": 450},
    ):
        svc._run_backfill(job_id, mock_repo, "2021-01-01")

    with svc._job_lock:
        assert svc._current_job["status"] == "done"
        assert svc._current_job["stats"]["balance_sheet_added"] == 120
        assert svc._current_job["stats"]["ledger_added"] == 450

    reset_job_state()


def test_run_backfill_sets_failed_state_on_error():
    """P1: _run_backfill sets status=failed and error when run_backfill() raises."""
    import backend.app.api.v1.sync.service as svc
    reset_job_state()

    mock_repo = MagicMock()
    job_id = "backfill-fail-job"
    with svc._job_lock:
        svc._current_job.update({"job_id": job_id, "status": "running"})

    with patch(
        "backend.app.api.v1.sync.backfill.run_backfill",
        side_effect=RuntimeError("API timeout"),
    ):
        svc._run_backfill(job_id, mock_repo, "2021-01-01")

    with svc._job_lock:
        assert svc._current_job["status"] == "failed"
        assert svc._current_job["error"] == "API timeout"
        assert svc._current_job["stats"] is None

    reset_job_state()


def test_run_backfill_calls_upsert_for_both_sheets():
    """AC1+2: run_backfill() calls repo.upsert_records for balance_sheet and ledger."""
    from backend.app.api.v1.sync.backfill import run_backfill

    mock_repo = MagicMock()
    mock_repo.upsert_records.return_value = []

    balance_item = {
        "accountId": 1, "accountNumber": "1-1", "accountName": "Caja",
        "debit": 100, "credit": 0, "debitBalance": 100, "creditBalance": 0,
    }

    with patch("backend.app.api.v1.sync.backfill.fetch_balance_sheet", return_value=[balance_item]):
        with patch("backend.app.api.v1.sync.backfill.fetch_ledger", return_value=[]):
            result = run_backfill("2026-04-01", mock_repo)

    assert mock_repo.upsert_records.call_count == 2
    sheet_names = [c.args[0] for c in mock_repo.upsert_records.call_args_list]
    assert "balance_sheet" in sheet_names
    assert "ledger" in sheet_names
    assert "balance_sheet_upserted" in result
    assert "ledger_upserted" in result
    assert result["balance_sheet_upserted"] == 1  # one eom date × one item
    assert result["ledger_upserted"] == 0


def test_run_backfill_raises_on_none_from_date():
    """P1: run_backfill raises ValueError when from_date_str is None."""
    from backend.app.api.v1.sync.backfill import run_backfill
    mock_repo = MagicMock()
    import pytest
    with pytest.raises(ValueError, match="from_date is required"):
        run_backfill(None, mock_repo)


def test_run_backfill_raises_on_future_from_date():
    """P2: run_backfill raises ValueError when from_date is in the future."""
    from backend.app.api.v1.sync.backfill import run_backfill
    mock_repo = MagicMock()
    import pytest
    with pytest.raises(ValueError, match="cannot be in the future"):
        run_backfill("2099-01-01", mock_repo)


def test_run_backfill_upsert_called_once_per_sheet():
    """P4: upsert_records called exactly once per sheet (not once per month)."""
    from backend.app.api.v1.sync.backfill import run_backfill

    mock_repo = MagicMock()
    mock_repo.upsert_records.return_value = []

    balance_item = {
        "accountId": 1, "accountNumber": "1-1", "accountName": "Caja",
        "debit": 0, "credit": 0, "debitBalance": 0, "creditBalance": 0,
    }

    # 3-month range → 3 API calls but only 1 upsert_records call per sheet
    with patch("backend.app.api.v1.sync.backfill.fetch_balance_sheet", return_value=[balance_item]):
        with patch("backend.app.api.v1.sync.backfill.fetch_ledger", return_value=[]):
            run_backfill("2026-02-01", mock_repo)

    # Should be exactly 2 total calls: one for balance_sheet, one for ledger
    assert mock_repo.upsert_records.call_count == 2


# ── Story 9.2 AC7: sync/status from ledger/_meta/import-log.jsonl ─────────────


def _enable_jsonl(monkeypatch, log_path):
    monkeypatch.setenv("USE_BEANCOUNT_ENGINE_SYNC_STATUS", "true")
    monkeypatch.setenv("LEDGER_IMPORT_LOG", str(log_path))


def test_sync_status_jsonl_reads_last_laudus_run(tmp_path, monkeypatch):
    """AC7: flag on → balance_sheet and ledger last_sync derive from last Laudus run."""
    log = tmp_path / "import-log.jsonl"
    log.write_text(
        '{"importer": "laudus", "timestamp": "2026-05-01T12:00:00+00:00", "records": 10, "success": true}\n'
        '{"importer": "laudus", "timestamp": "2026-05-10T08:30:00+00:00", "records": 12, "success": true}\n'
        '{"importer": "cartolas", "timestamp": "2026-05-15T09:00:00+00:00", "records": 3, "success": true}\n',
        encoding="utf-8",
    )
    _enable_jsonl(monkeypatch, log)
    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    # Both data types share the latest Laudus run (single-pass importer under c4).
    assert "2026-05-10" in data["balance_sheet"]["last_sync"]
    assert "2026-05-10" in data["ledger"]["last_sync"]


def test_sync_status_jsonl_ignores_failed_run(tmp_path, monkeypatch):
    """AC7: a later failed (rolled-back) run must not report a fresher last_sync than
    the last successful run."""
    log = tmp_path / "import-log.jsonl"
    log.write_text(
        '{"importer": "laudus", "timestamp": "2026-05-10T08:30:00+00:00", "success": true}\n'
        '{"importer": "laudus", "timestamp": "2026-05-12T08:30:00+00:00", "success": false, "error_msg": "bean-check failed"}\n',
        encoding="utf-8",
    )
    _enable_jsonl(monkeypatch, log)
    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    # Last successful run (05-10), not the failed run (05-12).
    assert "2026-05-10" in data["balance_sheet"]["last_sync"]
    assert "2026-05-10" in data["ledger"]["last_sync"]


def test_sync_status_jsonl_missing_file_returns_null(tmp_path, monkeypatch):
    """AC7: flag on + no import log (pre-bootstrap) → null per data type."""
    _enable_jsonl(monkeypatch, tmp_path / "does-not-exist.jsonl")
    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["balance_sheet"]["last_sync"] is None
    assert data["ledger"]["last_sync"] is None


def test_sync_status_jsonl_no_laudus_record_returns_null(tmp_path, monkeypatch):
    """AC7: flag on + only cartolas records → balance_sheet/ledger last_sync null."""
    log = tmp_path / "import-log.jsonl"
    log.write_text(
        '{"importer": "cartolas", "timestamp": "2026-05-15T09:00:00+00:00", "records": 3}\n',
        encoding="utf-8",
    )
    _enable_jsonl(monkeypatch, log)
    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["balance_sheet"]["last_sync"] is None
    assert data["ledger"]["last_sync"] is None


def test_sync_status_flag_off_still_uses_sheets(tmp_path, monkeypatch):
    """AC7/AC2: flag off (default) → Sheets path unchanged even if a log exists."""
    log = tmp_path / "import-log.jsonl"
    log.write_text(
        '{"importer": "laudus", "timestamp": "2026-05-10T08:30:00+00:00"}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("LEDGER_IMPORT_LOG", str(log))
    monkeypatch.delenv("USE_BEANCOUNT_ENGINE_SYNC_STATUS", raising=False)
    mock_repo = make_mock_repo(
        balance_sheet_records=[{"query_date": "2026-04-10", "account_id": 1}],
        date_range_records=[{"dateTo": "2026-04-10", "dateFrom": "2026-04-01"}],
    )
    client = make_sync_test_app(mock_repo=mock_repo)
    client.cookies.set("access_token", contador_token())
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    # Sheets value (2026-04-10), not the JSONL value (2026-05-10).
    assert "2026-04-10" in data["balance_sheet"]["last_sync"]


# ── Story 9.4 AC4/AC5: on-demand dispatches to the Beancount importer ─────────


def test_run_sync_dispatches_to_laudus_importer_when_flag_on(monkeypatch):
    """AC4: flag on → _run_sync runs the Laudus importer (incremental), stats from result."""
    import backend.app.api.v1.sync.service as svc
    reset_job_state()
    monkeypatch.setenv("USE_BEANCOUNT_ENGINE_LEDGER", "true")

    captured = {}

    def fake_run_import(mode="incremental", from_date=None):
        captured["mode"] = mode
        return {"success": True, "jes_added": 42, "error_msg": None}

    monkeypatch.setattr("pipeline.importers.laudus_run.run_import", fake_run_import)

    job_id = "laudus-job"
    with svc._job_lock:
        svc._current_job.update({"job_id": job_id, "status": "running", "stats": None})
    svc._run_sync(job_id, MagicMock())

    with svc._job_lock:
        assert svc._current_job["status"] == "done"
        assert svc._current_job["stats"]["ledger_added"] == 42
    assert captured["mode"] == "incremental"
    reset_job_state()


def test_run_backfill_dispatches_to_laudus_importer_when_flag_on(monkeypatch):
    """AC5: flag on → _run_backfill runs the importer in backfill mode."""
    import backend.app.api.v1.sync.service as svc
    reset_job_state()
    monkeypatch.setenv("USE_BEANCOUNT_ENGINE_LEDGER", "true")

    captured = {}

    def fake_run_import(mode="incremental", from_date=None):
        captured["mode"] = mode
        captured["from_date"] = from_date
        return {"success": True, "jes_added": 7, "error_msg": None}

    monkeypatch.setattr("pipeline.importers.laudus_run.run_import", fake_run_import)

    job_id = "laudus-backfill-job"
    with svc._job_lock:
        svc._current_job.update({"job_id": job_id, "status": "running", "stats": None})
    svc._run_backfill(job_id, MagicMock(), "2021-01-01")

    with svc._job_lock:
        assert svc._current_job["status"] == "done"
        assert svc._current_job["stats"]["ledger_added"] == 7
    assert captured["mode"] == "backfill"
    assert captured["from_date"] == "2021-01-01"
    reset_job_state()


def test_run_sync_laudus_failure_sets_failed(monkeypatch):
    """AC7: importer failure (e.g. bean-check) → job_status=failed with error."""
    import backend.app.api.v1.sync.service as svc
    reset_job_state()
    monkeypatch.setenv("USE_BEANCOUNT_ENGINE_LEDGER", "true")

    monkeypatch.setattr(
        "pipeline.importers.laudus_run.run_import",
        lambda mode="incremental", from_date=None: {"success": False, "jes_added": 0, "error_msg": "bean-check failed: boom"},
    )

    job_id = "laudus-fail-job"
    with svc._job_lock:
        svc._current_job.update({"job_id": job_id, "status": "running", "stats": None})
    svc._run_sync(job_id, MagicMock())

    with svc._job_lock:
        assert svc._current_job["status"] == "failed"
        assert "bean-check failed" in svc._current_job["error"]
    reset_job_state()


# ── Story 2.4: ventana solapada + rebuild de ledger_final que no falla en silencio ──

from contextlib import ExitStack
from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

import pipeline.sync as sync_module
from pipeline.models import LEDGER_HEADERS
from pipeline.utils.dates import get_date_range


class _FakeWorksheet:
    """Worksheet de gspread en memoria — soporta el subconjunto usado por sync_api."""

    def __init__(self, title, rows=None):
        self.title = title
        self._rows = [list(r) for r in (rows or [])]  # [0] = headers

    def get_all_values(self):
        return [list(r) for r in self._rows]

    def get_all_records(self):
        if not self._rows:
            return []
        headers = self._rows[0]
        records = []
        for raw in self._rows[1:]:
            record = {headers[i]: (raw[i] if i < len(raw) else "") for i in range(len(headers))}
            if any(str(v) != "" for v in record.values()):
                records.append(record)
        return records

    def clear(self):
        self._rows = []

    def update(self, values=None, range_name=None, value_input_option=None):
        self._rows = [list(r) for r in values]

    def append_row(self, row):
        self._rows.append(list(row))


class _FakeSpreadsheet:
    def __init__(self):
        self._sheets = {}

    def seed(self, name, headers, records):
        rows = [list(headers)] + [[rec.get(h, "") for h in headers] for rec in records]
        self._sheets[name] = _FakeWorksheet(name, rows)

    def worksheet(self, name):
        if name in self._sheets:
            return self._sheets[name]
        raise Exception(f"Worksheet '{name}' not found")

    def add_worksheet(self, title, rows, cols):
        ws = _FakeWorksheet(title, [])
        self._sheets[title] = ws
        return ws


def _raw_ledger_item(jeid, lineid, date_str, account="413900", debit=1000, credit=0):
    """Item crudo al estilo del endpoint accounting/ledger de Laudus."""
    return {
        "journalEntryId": jeid,
        "journalEntryNumber": jeid,
        "date": date_str,
        "accountNumber": account,
        "lineId": lineid,
        "description": "test",
        "debit": debit,
        "credit": credit,
        "currencyCode": "CLP",
        "parityToMainCurrency": 1,
    }


def _base_fake(watermark):
    sh = _FakeSpreadsheet()
    sh.seed("PlanCuentas", ["Cuenta"], [])
    sh.seed("date_range", ["dateTo", "dateFrom"], [{"dateTo": watermark, "dateFrom": watermark}])
    sh.seed("ledger", LEDGER_HEADERS, [])
    return sh


def _run_sync_api_with_fake(sh, ledger_items, replace_override=None):
    """Corre pipeline.sync.sync_api() contra un spreadsheet fake con la IO externa parcheada.
    upsert_to_sheet/replace_sheet quedan REALES (ejercitan dedup/merge de verdad) salvo override."""
    with ExitStack() as stack:
        stack.enter_context(patch("pipeline.sync.get_spreadsheet", return_value=sh))
        stack.enter_context(patch("pipeline.sync.fetch_balance_sheet", return_value=[]))
        stack.enter_context(patch("pipeline.sync.fetch_ledger", return_value=ledger_items))
        stack.enter_context(patch(
            "pipeline.sync.build_plan_cuentas_lookup",
            return_value={"413900": {"accountName": "x", "Categoria1": "a", "Categoria2": "b", "Categoria3": "c"}},
        ))
        stack.enter_context(patch(
            "pipeline.sync.get_endpoints",
            return_value={"GET_LEDGER": {"url": "http://x", "params": {}}},
        ))
        if replace_override is not None:
            stack.enter_context(patch("pipeline.sync.replace_sheet", side_effect=replace_override))
        sync_module.sync_api()


# ── AC1: get_date_range ventana solapada ──────────────────────────────────


def test_get_date_range_recent_watermark_reaches_back_window():
    """AC1: watermark reciente → date_from retrocede al inicio de ventana, no a watermark+1."""
    today = date(2026, 6, 15)
    date_from, date_to = get_date_range("2026-06-15", today=today, overlap_months=13)
    assert date_to == today
    assert date_from == today - relativedelta(months=13)  # 2025-05-15


def test_get_date_range_old_watermark_keeps_history():
    """AC1: watermark más viejo que la ventana → date_from = watermark+1 (no perder histórico)."""
    today = date(2026, 6, 15)
    date_from, _ = get_date_range("2023-01-01", today=today, overlap_months=13)
    assert date_from == date(2023, 1, 2)


def test_get_date_range_date_to_is_today():
    """AC1: date_to siempre es hoy."""
    today = date(2026, 6, 15)
    _, date_to = get_date_range("2026-06-15", today=today)
    assert date_to == today


def test_get_date_range_env_var_controls_window(monkeypatch):
    """AC1: SYNC_OVERLAP_WINDOW_MONTHS controla el tamaño de la ventana."""
    monkeypatch.setenv("SYNC_OVERLAP_WINDOW_MONTHS", "3")
    today = date(2026, 6, 15)
    date_from, _ = get_date_range("2026-06-15", today=today)
    assert date_from == today - relativedelta(months=3)  # 2026-03-15


# ── AC2/AC3/AC5: integración sync_api contra fake ─────────────────────────


def test_sync_recovers_backdated_entry_within_window():
    """AC3: un asiento backdateado dentro de la ventana, ingresado tras el avance del
    watermark, aparece en ledger tras el sync. (Forward-only no lo recuperaba: con el
    watermark ya en hoy, date_from sería hoy+1 > hoy y el fetch se saltaba.)"""
    today = date.today()
    sh = _base_fake(today.isoformat())  # watermark ya en hoy
    backdated = (today - relativedelta(months=2)).isoformat()
    _run_sync_api_with_fake(sh, [_raw_ledger_item("JE-BACK", "1", backdated)])
    ledger_ids = {str(r["journalentryid"]) for r in sh.worksheet("ledger").get_all_records()}
    assert "JE-BACK" in ledger_ids


def test_sync_idempotent_two_runs_same_ledger():
    """AC2: dos corridas con el mismo input dejan ledger sin filas duplicadas."""
    today = date.today()
    sh = _base_fake(today.isoformat())
    month_ago = (today - relativedelta(months=1)).isoformat()
    items = [
        _raw_ledger_item("JE-1", "1", month_ago),
        _raw_ledger_item("JE-2", "1", month_ago),
    ]
    _run_sync_api_with_fake(sh, items)
    _run_sync_api_with_fake(sh, items)
    rows = sh.worksheet("ledger").get_all_records()
    assert len(rows) == 2


def test_sync_advances_watermark_to_today_on_success():
    """AC5: tras una corrida completa exitosa (incl. rebuild), date_range avanza a hoy."""
    today = date.today()
    sh = _base_fake("2026-01-01")
    _run_sync_api_with_fake(sh, [_raw_ledger_item("JE-1", "1", today.isoformat())])
    dates = [str(r["dateTo"]) for r in sh.worksheet("date_range").get_all_records()]
    assert today.isoformat() in dates


# ── AC4/AC5: el fallo del rebuild deja de ser silencioso ──────────────────


def test_sync_api_raises_when_rebuild_fails_and_watermark_not_advanced():
    """AC4+AC5: si el rebuild de ledger_final lanza, sync_api propaga (no se traga) y
    date_range NO avanza → la corrida es re-intentable."""
    today = date.today()
    sh = _base_fake("2026-01-01")

    def boom_on_final(spreadsheet, sheet_name, data_list, headers):
        if sheet_name == "ledger_final":
            raise RuntimeError("write boom")

    with pytest.raises(RuntimeError, match="write boom"):
        _run_sync_api_with_fake(
            sh, [_raw_ledger_item("JE-1", "1", today.isoformat())], replace_override=boom_on_final
        )

    dates = [str(r["dateTo"]) for r in sh.worksheet("date_range").get_all_records()]
    assert today.isoformat() not in dates  # watermark NO avanzó
    assert "2026-01-01" in dates


def test_sync_api_raises_on_ledger_final_count_mismatch():
    """AC4: si ledger_final queda con distinto número de filas que ledger (rebuild parcial),
    sync_api propaga en vez de avanzar a ciegas."""
    today = date.today()
    sh = _base_fake("2026-01-01")
    items = [
        _raw_ledger_item("JE-1", "1", today.isoformat()),
        _raw_ledger_item("JE-2", "1", today.isoformat()),
    ]
    real_replace = sync_module.replace_sheet

    def truncating(spreadsheet, sheet_name, data_list, headers):
        if sheet_name == "ledger_final":
            real_replace(spreadsheet, sheet_name, data_list[:-1], headers)  # pierde una fila
        else:
            real_replace(spreadsheet, sheet_name, data_list, headers)

    with pytest.raises(RuntimeError, match="inconsistente"):
        _run_sync_api_with_fake(sh, items, replace_override=truncating)

    dates = [str(r["dateTo"]) for r in sh.worksheet("date_range").get_all_records()]
    assert today.isoformat() not in dates  # watermark NO avanzó tras el mismatch
