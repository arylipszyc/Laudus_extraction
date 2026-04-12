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


def owner_token():
    return create_jwt(email="owner@test.com", role="owner")


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


def test_sync_status_owner_can_read():
    """GET /sync/status is accessible to owner (read-only endpoint)."""
    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", owner_token())
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


def test_sync_trigger_owner_forbidden():
    """AC3: owner → 403."""
    client = make_sync_test_app(mock_repo=make_mock_repo())
    client.cookies.set("access_token", owner_token())
    response = client.post("/api/v1/sync/trigger")
    assert response.status_code == 403


def test_sync_trigger_contador_returns_triggered():
    """AC2: contador → 202 + {status: triggered, job_id: ...}."""
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

    with patch("sync.sync_api", side_effect=RuntimeError("Sheets write failed")):
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

    with patch("sync.sync_api"):
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
