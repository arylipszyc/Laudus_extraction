"""Fava extension that validates editor saves against `bean-check`.

Story 9.0 (Epic 9). Approach: Option A from the Task 1 investigation —
hook the native ``after_write_source`` callback. Pre-edit content is captured
in ``before_request`` (Fava's editor uses ``PUT /<bfile>/api/source``), so when
``after_write_source`` fires we have the snapshot needed to revert atomically.

If ``bean-check`` fails the snapshot is restored via ``os.replace`` (POSIX
atomic), the attempt is appended to ``ledger/_meta/edit-revert-log.jsonl``,
and a user-facing message is written to ``ledger/_meta/last-revert-message.json``
for the next request to surface.

Lives under ``ledger/`` because Fava's ``find_extensions`` resolves extension
names relative to ``Path(main.beancount).parent``.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from fava.ext import FavaExtensionBase
from flask import request

LOCK_TIMEOUT_SEC = 300
LOCK_POLL_INTERVAL_SEC = 1.0
LOCK_WAIT_MAX_SEC = 60
BEAN_CHECK_TIMEOUT_SEC = 30

SAVE_ENDPOINTS = frozenset({"json_api.put_source", "json_api.put_source_slice"})


class EditValidator(FavaExtensionBase):
    """Validate every editor save against bean-check; revert on failure."""

    report_title = None  # backend-only — no UI report

    def __init__(self, ledger, config=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(ledger, config)
        self._ledger_root = Path(ledger.beancount_file_path).parent
        self._meta_dir = self._ledger_root / "_meta"
        self._snapshot_dir = self._meta_dir / ".snapshots"
        self._meta_dir.mkdir(parents=True, exist_ok=True)
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)

    # ── public hooks ──────────────────────────────────────────────────

    def before_request(self) -> None:
        """Snapshot the file Fava is about to overwrite (AC4 — atomicity)."""
        if request.endpoint not in SAVE_ENDPOINTS:
            return
        body = request.get_json(silent=True) or {}
        file_path = body.get("file_path")
        if not file_path:
            return
        target = Path(file_path)
        if not target.exists():
            return
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, self._snapshot_path_for(target))

    def after_write_source(self, path: str, source: str) -> None:
        """Run bean-check; revert atomically if it fails (AC1, AC4)."""
        target = Path(path)
        snap_path = self._snapshot_path_for(target)

        # AC3 — respect importer lock before validating
        if self._wait_for_import_lock() == "timeout":
            self._revert(
                target,
                snap_path,
                source,
                user_message="Sistema ocupado — reintentá en 1 minuto",
                bean_check_error=None,
            )
            return

        check = self._run_bean_check()
        if check.returncode == 0:
            snap_path.unlink(missing_ok=True)
            self._clear_revert_message()
            return

        error_text = (check.stdout or "") + (check.stderr or "")
        self._revert(
            target,
            snap_path,
            source,
            user_message="Tu edit fue revertido — corregí el error e intentá de nuevo",
            bean_check_error=error_text,
        )

    # ── helpers ───────────────────────────────────────────────────────

    def _snapshot_path_for(self, target: Path) -> Path:
        digest = hashlib.sha256(str(target.resolve()).encode("utf-8")).hexdigest()[:16]
        return self._snapshot_dir / f"{digest}.bak"

    def _run_bean_check(self) -> subprocess.CompletedProcess:
        # Use `python -m beancount.scripts.check` for portability — the
        # `bean-check` console-script may not be on PATH inside containers.
        return subprocess.run(  # noqa: S603 — fixed argv, no shell
            [sys.executable, "-m", "beancount.scripts.check", str(self.ledger.beancount_file_path)],
            capture_output=True,
            text=True,
            timeout=BEAN_CHECK_TIMEOUT_SEC,
            check=False,
        )

    def _wait_for_import_lock(self) -> str:
        """Block until ``ledger/.import.lock`` is free or stale.

        Returns ``'free'`` if no lock or it became stale (>5min); ``'timeout'``
        if a fresh lock was held for the full ``LOCK_WAIT_MAX_SEC``.
        """
        lock_path = self._ledger_root / ".import.lock"
        deadline = time.time() + LOCK_WAIT_MAX_SEC
        while time.time() < deadline:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except FileNotFoundError:
                return "free"
            if age > LOCK_TIMEOUT_SEC:
                return "free"
            time.sleep(LOCK_POLL_INTERVAL_SEC)
        return "timeout"

    def _revert(
        self,
        target: Path,
        snap_path: Path,
        attempted_source: str,
        user_message: str,
        bean_check_error: str | None,
    ) -> None:
        if snap_path.exists():
            self._atomic_restore(target, snap_path)
            try:
                self.ledger.load_file()
            except Exception:  # pragma: no cover — best-effort reload
                pass
        self._append_revert_log(target, attempted_source, bean_check_error, user_message)
        self._write_revert_message(target, user_message, bean_check_error)

    @staticmethod
    def _atomic_restore(target: Path, snap_path: Path) -> None:
        """Copy snapshot into target via a temp file + ``os.replace`` (atomic)."""
        fd, tmp_name = tempfile.mkstemp(
            dir=str(target.parent), prefix=".tmp_revert_", suffix=target.suffix
        )
        os.close(fd)
        try:
            shutil.copy2(snap_path, tmp_name)
            os.replace(tmp_name, target)
        except Exception:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
            raise
        finally:
            snap_path.unlink(missing_ok=True)

    def _append_revert_log(
        self,
        target: Path,
        attempted_source: str,
        bean_check_error: str | None,
        user_message: str,
    ) -> None:
        log_path = self._meta_dir / "edit-revert-log.jsonl"
        entry = {
            "ts": _utc_now_iso(),
            "file": str(target.relative_to(self._ledger_root)).replace("\\", "/"),
            "post_hash": "sha256:" + hashlib.sha256(attempted_source.encode("utf-8")).hexdigest(),
            "user": _fava_user(),
            "bean_check_error": bean_check_error or f"(no bean-check run: {user_message})",
        }
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _write_revert_message(
        self,
        target: Path,
        user_message: str,
        bean_check_error: str | None,
    ) -> None:
        msg_path = self._meta_dir / "last-revert-message.json"
        payload = {
            "ts": _utc_now_iso(),
            "file": str(target.relative_to(self._ledger_root)).replace("\\", "/"),
            "message": user_message,
            "bean_check_error": bean_check_error,
        }
        msg_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _clear_revert_message(self) -> None:
        (self._meta_dir / "last-revert-message.json").unlink(missing_ok=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _fava_user() -> str:
    """Best-effort identification of the contador via basic-auth or proxy header."""
    try:
        if request.authorization and request.authorization.username:
            return request.authorization.username
        return request.headers.get("X-Forwarded-User") or "(unknown)"
    except Exception:
        return "(unknown)"
