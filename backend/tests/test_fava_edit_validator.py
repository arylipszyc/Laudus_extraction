"""Unit tests for the Fava EditValidator extension — Story 9.0.

Covers AC1 (revert), AC3 (lock respect), AC4 (atomic restore), AC5 (audit log),
and the user-facing message file driven by Task 5.

Tests load the extension manually via FavaLedger so we exercise the real
``after_write_source`` plumbing end-to-end against a temp ledger.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator

import pytest

# Make the ledger/ extensions importable in tests (Fava normally does this
# at runtime via sys.path.insert in find_extensions).
ROOT = Path(__file__).resolve().parents[2]
LEDGER_TEMPLATE = ROOT / "ledger"
sys.path.insert(0, str(LEDGER_TEMPLATE))

from fava.core import FavaLedger  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────


def _copy_template_ledger(dst: Path) -> Path:
    """Copy the mock ledger to a tmp dir and return path to its main.beancount."""
    shutil.copytree(LEDGER_TEMPLATE, dst, dirs_exist_ok=True)
    # Strip persisted state from previous runs
    for name in ("edit-revert-log.jsonl", "last-revert-message.json"):
        (dst / "_meta" / name).unlink(missing_ok=True)
    snap_dir = dst / "_meta" / ".snapshots"
    if snap_dir.exists():
        shutil.rmtree(snap_dir)
    return dst / "main.beancount"


def _load_ledger(main_path: Path) -> FavaLedger:
    return FavaLedger(str(main_path.resolve()))


def _validator(ledger: FavaLedger):
    inst = ledger.extensions._instances["EditValidator"]
    return inst


@pytest.fixture()
def ledger_dir(tmp_path: Path) -> Path:
    main = _copy_template_ledger(tmp_path / "ledger")
    return main.parent


# ── AC1 / AC4 — happy path: valid edit is preserved ─────────────────


def test_valid_edit_passes_no_revert(ledger_dir: Path) -> None:
    main = ledger_dir / "main.beancount"
    target = ledger_dir / "manual" / "2026-04.beancount"
    pre = target.read_text("utf-8")
    new_source = pre + '\n;; harmless trailing comment added by editor\n'

    ledger = _load_ledger(main)
    ext = _validator(ledger)
    # Simulate what before_request would have done
    ext._snapshot_path_for(target).write_bytes(pre.encode("utf-8"))
    target.write_text(new_source, encoding="utf-8")

    ext.after_write_source(str(target), new_source)

    assert target.read_text("utf-8") == new_source, "valid edit must persist"
    snap = ext._snapshot_path_for(target)
    assert not snap.exists(), "snapshot must be cleaned up after success"
    assert not (ledger_dir / "_meta" / "last-revert-message.json").exists()


# ── AC1 / AC4 — invalid edit triggers atomic revert ─────────────────


def test_invalid_edit_is_reverted_and_logged(ledger_dir: Path) -> None:
    main = ledger_dir / "main.beancount"
    target = ledger_dir / "manual" / "2026-04.beancount"
    pre = target.read_text("utf-8")
    # Replace one amount with a non-balancing value
    broken = pre.replace("65690.00 CLP", "99999.00 CLP", 1)
    assert broken != pre, "fixture mutation must actually change the file"

    ledger = _load_ledger(main)
    ext = _validator(ledger)
    ext._snapshot_path_for(target).write_bytes(pre.encode("utf-8"))
    target.write_text(broken, encoding="utf-8")

    ext.after_write_source(str(target), broken)

    # AC1 — content is reverted
    assert target.read_text("utf-8") == pre

    # AC5 — audit log line appended
    log = ledger_dir / "_meta" / "edit-revert-log.jsonl"
    assert log.exists()
    lines = [json.loads(line) for line in log.read_text("utf-8").splitlines() if line]
    assert len(lines) == 1
    entry = lines[0]
    assert entry["file"] == "manual/2026-04.beancount"
    assert entry["post_hash"].startswith("sha256:")
    assert "bean-check" in entry["bean_check_error"].lower() or "balance" in entry["bean_check_error"].lower() or "error" in entry["bean_check_error"].lower()

    # Task 5 — user-facing message persisted
    msg = json.loads((ledger_dir / "_meta" / "last-revert-message.json").read_text("utf-8"))
    assert msg["file"] == "manual/2026-04.beancount"
    assert "revertido" in msg["message"].lower()


# ── AC3 — fresh import lock causes timeout-revert ───────────────────


def test_fresh_import_lock_times_out_and_reverts(
    ledger_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main = ledger_dir / "main.beancount"
    target = ledger_dir / "manual" / "2026-04.beancount"
    pre = target.read_text("utf-8")
    new_source = pre + '\n;; trivial comment\n'

    # Fresh lock (mtime = now)
    (ledger_dir / ".import.lock").write_text("locked", encoding="utf-8")

    ledger = _load_ledger(main)
    ext = _validator(ledger)
    # Make the wait return 'timeout' immediately so the test is fast
    monkeypatch.setattr(
        "ledger.fava_edit_validator.LOCK_WAIT_MAX_SEC", 0
    )

    ext._snapshot_path_for(target).write_bytes(pre.encode("utf-8"))
    target.write_text(new_source, encoding="utf-8")
    ext.after_write_source(str(target), new_source)

    # Even though the edit was syntactically valid, the lock timeout should revert
    assert target.read_text("utf-8") == pre
    msg = json.loads((ledger_dir / "_meta" / "last-revert-message.json").read_text("utf-8"))
    assert "ocupado" in msg["message"].lower()


# ── AC3 — stale import lock (>5min) is treated as free ──────────────


def test_stale_import_lock_does_not_block(ledger_dir: Path) -> None:
    main = ledger_dir / "main.beancount"
    target = ledger_dir / "manual" / "2026-04.beancount"
    pre = target.read_text("utf-8")
    new_source = pre + '\n;; trivial comment\n'

    # Stale lock — mtime far in the past
    lock = ledger_dir / ".import.lock"
    lock.write_text("locked", encoding="utf-8")
    stale = time.time() - 10 * 60  # 10 min ago
    os.utime(lock, (stale, stale))

    ledger = _load_ledger(main)
    ext = _validator(ledger)
    ext._snapshot_path_for(target).write_bytes(pre.encode("utf-8"))
    target.write_text(new_source, encoding="utf-8")
    ext.after_write_source(str(target), new_source)

    # bean-check passes → edit is preserved (lock was treated as stale)
    assert target.read_text("utf-8") == new_source


# ── AC4 — atomic restore: snapshot is the byte-for-byte source of truth ─


def test_atomic_restore_uses_snapshot_bytes(ledger_dir: Path) -> None:
    main = ledger_dir / "main.beancount"
    target = ledger_dir / "manual" / "2026-04.beancount"
    pre_bytes = target.read_bytes()
    broken = pre_bytes.replace(b"65690.00 CLP", b"99999.00 CLP", 1)
    assert broken != pre_bytes

    ledger = _load_ledger(main)
    ext = _validator(ledger)
    ext._snapshot_path_for(target).write_bytes(pre_bytes)
    target.write_bytes(broken)
    ext.after_write_source(str(target), broken.decode("utf-8"))

    # Bytes-equal restoration (preserves exact pre-edit, including line endings)
    assert target.read_bytes() == pre_bytes


# ── Sanity: bean-check is on PATH (smoke prerequisite) ──────────────


def test_bean_check_binary_available() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "beancount.scripts.check", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
