"""Sync orchestration service — job tracking + background runner."""
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.app.repositories.base import DataRepository

logger = logging.getLogger(__name__)


def _flag(name: str) -> bool:
    """True if the env var is set to a truthy value (default false)."""
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


def _import_log_path() -> Path:
    """Path to the importer run log. `LEDGER_IMPORT_LOG` overrides the default."""
    override = os.getenv("LEDGER_IMPORT_LOG")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[5] / "ledger" / "_meta" / "import-log.jsonl"


def _read_import_log_last_sync() -> datetime | None:
    """Last Laudus importer run timestamp from `ledger/_meta/import-log.jsonl` (AC7).

    Under c4 the Laudus importer writes balance-sheet and ledger data in one pass,
    so both data types share this timestamp. Only successful runs count — a failed
    (rolled-back) run must not report a fresh last_sync. Returns None pre-bootstrap
    (file missing or no successful `laudus` record).
    """
    path = _import_log_path()
    if not path.exists():
        return None
    latest: datetime | None = None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("importer") != "laudus":
                continue
            if not record.get("success"):
                continue
            ts = record.get("timestamp")
            if not ts:
                continue
            parsed = datetime.fromisoformat(ts)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if latest is None or parsed > latest:
                latest = parsed
    except (ValueError, OSError) as exc:
        logger.warning("import-log.jsonl unreadable (%s): %s", path, exc)
        return None
    return latest

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
    if _flag("USE_BEANCOUNT_ENGINE_SYNC_STATUS"):
        # c4 path: both data types derive from the same Laudus importer run (AC7).
        run_ts = _read_import_log_last_sync()
        bs_last_sync = ledger_last_sync = run_ts
    else:
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


def _refresh_ledger_clone() -> None:
    """Trae el clon del ledger del backend a origin/main antes de importar.

    El backend y el cron son ambos writers del repo del ledger (Story 9.11). Sin esto,
    si el cron pusheó después del último clone/sync, el push del importer del backend
    sería non-fast-forward y fallaría. fetch + reset --hard deja el clon == main (el
    importer es determinista, así que resetear es seguro). No-op si LEDGER_DIR no apunta
    a un clon git (tests / local sin deploy key).
    """
    import subprocess

    ledger_dir = os.getenv("LEDGER_DIR")
    if not ledger_dir:
        return
    repo_root = os.path.dirname(ledger_dir.rstrip("/\\"))  # LEDGER_DIR = <repo>/ledger
    if not os.path.isdir(os.path.join(repo_root, ".git")):
        return
    try:
        subprocess.run(["git", "-C", repo_root, "fetch", "origin", "main"], check=True, capture_output=True)
        subprocess.run(["git", "-C", repo_root, "reset", "--hard", "origin/main"], check=True, capture_output=True)
    except Exception as exc:  # noqa: BLE001 — refresh best-effort; el push de git_commit_push falla ruidoso si quedó atrás
        logger.warning("No pude refrescar el clon del ledger antes de importar: %s", exc)


def _run_laudus_import(job_id: str, mode: str, from_date: str | None = None) -> None:
    """Story 9.4: run the Beancount Laudus importer in this background thread.

    Used instead of the Sheets path when `USE_BEANCOUNT_ENGINE_LEDGER=true`.
    """
    try:
        from pipeline.importers.laudus_run import run_import
        _refresh_ledger_clone()
        result = run_import(mode=mode, from_date=from_date)
        with _job_lock:
            if _current_job["job_id"] != job_id:
                return
            if result["success"]:
                _current_job.update({
                    "status": "done",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "stats": {"balance_sheet_added": 0, "ledger_added": result["jes_added"]},
                })
            else:
                _current_job.update({
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error": result["error_msg"],
                    "stats": None,
                })
    except Exception as exc:
        logger.error("Laudus importer failed: %s", exc, exc_info=True)
        with _job_lock:
            if _current_job["job_id"] == job_id:
                _current_job.update({
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(exc),
                    "stats": None,
                })


def _run_sync(job_id: str, repo: DataRepository) -> None:
    """Execute sync_api() in background thread. Counts records before/after for stats."""
    if _flag("USE_BEANCOUNT_ENGINE_LEDGER"):
        _run_laudus_import(job_id, mode="incremental")
        return
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
    if _flag("USE_BEANCOUNT_ENGINE_LEDGER"):
        _run_laudus_import(job_id, mode="backfill", from_date=from_date)
        return
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
