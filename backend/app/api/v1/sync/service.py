"""Sync orchestration service — job tracking + background runner."""
import logging
import threading
from datetime import datetime, timezone
from uuid import uuid4

from backend.app.repositories.base import DataRepository

logger = logging.getLogger(__name__)

# In-memory job state — volatile (lost on Cloud Run restart, acceptable for MVP)
_current_job: dict = {
    "job_id": None,
    "status": "idle",   # idle | running | done | failed
    "started_at": None,
    "completed_at": None,
    "error": None,
    "stats": None,
}
_job_lock = threading.Lock()


def get_sync_status(repo: DataRepository) -> dict:
    """Return current sync status: per-type last sync dates + current job state."""
    bs_last_sync = _read_balance_sheet_last_sync(repo)
    ledger_last_sync = _read_last_sync_date(repo)
    with _job_lock:
        return {
            "balance_sheet": {"last_sync": bs_last_sync},
            "ledger": {"last_sync": ledger_last_sync},
            "job_status": _current_job["status"],
            "job_id": _current_job["job_id"],
            "error": _current_job["error"],
            "stats": _current_job.get("stats"),
        }


def trigger_sync(
    repo: DataRepository,
    mode: str = "normal",
    from_date: str | None = None,
) -> str:
    """Start sync or backfill in a background thread. Returns job_id.

    Raises ValueError if a sync is already running.
    """
    with _job_lock:
        if _current_job["status"] == "running":
            raise ValueError("Sync already running")
        job_id = str(uuid4())
        _current_job.update({
            "job_id": job_id,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "error": None,
            "stats": None,
        })

    if mode == "backfill":
        thread = threading.Thread(target=_run_backfill, args=(job_id, repo, from_date), daemon=True)
    else:
        thread = threading.Thread(target=_run_sync, args=(job_id, repo), daemon=True)
    thread.start()
    return job_id


def _run_sync(job_id: str, repo: DataRepository) -> None:
    """Execute sync_api() in background thread. Counts records before/after for stats."""
    try:
        # Snapshot counts before sync (best-effort — silent on error)
        try:
            bs_before = len(repo.get_records("balance_sheet") or [])
            ledger_before = len(repo.get_records("ledger") or [])
        except Exception:
            bs_before = ledger_before = None

        from pipeline.sync import sync_api
        sync_api()

        # Snapshot counts after sync and compute delta
        stats = None
        if bs_before is not None:
            try:
                bs_after = len(repo.get_records("balance_sheet") or [])
                ledger_after = len(repo.get_records("ledger") or [])
                stats = {
                    "balance_sheet_added": max(0, bs_after - bs_before),
                    "ledger_added": max(0, ledger_after - ledger_before),
                }
            except Exception:
                pass  # stats unavailable — sync itself succeeded

        with _job_lock:
            if _current_job["job_id"] == job_id:
                _current_job.update({
                    "status": "done",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "stats": stats,
                })
    except Exception as exc:
        logger.error("Background sync failed: %s", exc, exc_info=True)
        with _job_lock:
            if _current_job["job_id"] == job_id:
                _current_job.update({
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(exc),
                    "stats": None,
                })


def _run_backfill(job_id: str, repo: DataRepository, from_date: str | None) -> None:
    """Execute run_backfill() in background thread. Updates _current_job on completion/failure."""
    try:
        from backend.app.api.v1.sync.backfill import run_backfill
        result = run_backfill(from_date, repo)
        stats = {
            "balance_sheet_added": result["balance_sheet_upserted"],
            "ledger_added": result["ledger_upserted"],
        }
        with _job_lock:
            if _current_job["job_id"] == job_id:
                _current_job.update({
                    "status": "done",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "stats": stats,
                })
    except Exception as exc:
        logger.error("Background backfill failed: %s", exc, exc_info=True)
        with _job_lock:
            if _current_job["job_id"] == job_id:
                _current_job.update({
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(exc),
                    "stats": None,
                })


def _read_balance_sheet_last_sync(repo: DataRepository) -> datetime | None:
    """Read balance sheet last sync from balance_sheet tab: max query_date."""
    try:
        records = repo.get_records("balance_sheet")
        if not records:
            return None
        dates = [str(r.get("query_date", "")) for r in records if r.get("query_date")]
        if not dates:
            return None
        return datetime.fromisoformat(max(dates)).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _read_last_sync_date(repo: DataRepository) -> datetime | None:
    """Read ledger last sync from date_range sheet: max dateTo."""
    try:
        records = repo.get_records("date_range")
        if not records:
            return None
        latest = max(records, key=lambda r: str(r.get("dateTo", "")))
        date_str = str(latest.get("dateTo", ""))
        if not date_str:
            return None
        return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    except Exception:
        return None
