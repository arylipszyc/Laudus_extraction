"""Sync orchestration service — job tracking + background runner.

Story 9.16 (cleanup c4): se removió el path Sheets. El sync es el importer
Laudus→Beancount (Story 9.4); el status deriva del import-log de ese importer.
"""
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)


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


def get_sync_status() -> dict:
    """Return current sync status: last Laudus importer run + current job state.

    Ambos tipos de dato derivan de la misma corrida del importer Laudus (AC7).
    """
    run_ts = _read_import_log_last_sync()
    with _job_lock:
        return {
            "balance_sheet": {"last_sync": run_ts},
            "ledger": {"last_sync": run_ts},
            "job_status": _current_job["status"],
            "job_id": _current_job["job_id"],
            "error": _current_job["error"],
            "stats": _current_job.get("stats"),
        }


def trigger_sync(
    mode: str = "normal",
    from_date: str | None = None,
) -> str:
    """Start the Laudus→Beancount import (incremental or backfill) in a background
    thread. Returns job_id. Raises ValueError if a sync is already running.
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

    import_mode = "backfill" if mode == "backfill" else "incremental"
    thread = threading.Thread(
        target=_run_laudus_import, args=(job_id, import_mode, from_date), daemon=True
    )
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
        # timeout: el fetch va por red — sin tope, un stall de SSH colgaría el thread de sync.
        subprocess.run(["git", "-C", repo_root, "fetch", "origin", "main"],
                       check=True, capture_output=True, timeout=60)
        subprocess.run(["git", "-C", repo_root, "reset", "--hard", "origin/main"],
                       check=True, capture_output=True, timeout=60)
    except Exception as exc:  # noqa: BLE001 — refresh best-effort; el push de git_commit_push falla ruidoso si quedó atrás
        logger.warning("No pude refrescar el clon del ledger antes de importar: %s", exc)


def _run_laudus_import(job_id: str, mode: str, from_date: str | None = None) -> None:
    """Story 9.4: run the Beancount Laudus importer in this background thread."""
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
