"""Tests for the Laudus importer orchestrator — Story 9.4 AC2/AC5/AC7/AC8/AC9."""
import json
import time

import pytest

from pipeline.importers import laudus_run

MINI_ACCOUNTS = """\
2020-12-31 open Assets:EAG:Bancos:BancoBci-111005 CLP
  code: "111005"
2020-12-31 open Income:EAG:Ventas-411005 CLP
  code: "411005"
"""

MAIN = (
    'option "operating_currency" "CLP"\n'
    '1900-01-01 commodity CLP\n'
    'include "accounts.beancount"\n'
    'include "imports/laudus/*.beancount"\n'
    'include "imports/_new-accounts-pending.beancount"\n'
)


def _ledger_root(tmp_path):
    root = tmp_path / "ledger"
    (root / "imports" / "laudus").mkdir(parents=True)
    # Mirror prod: _init.beancount keeps the `imports/laudus/*.beancount` glob non-empty.
    (root / "imports" / "laudus" / "_init.beancount").write_text(";; init\n", encoding="utf-8")
    (root / "accounts.beancount").write_text(MINI_ACCOUNTS, encoding="utf-8")
    (root / "main.beancount").write_text(MAIN, encoding="utf-8")
    (root / "imports" / "_new-accounts-pending.beancount").write_text(";; pending\n", encoding="utf-8")
    return root


def _balanced(je_id=1, date="2024-03-15"):
    base = {"journalentrynumber": 1001, "currencycode": "CLP", "paritytomaincurrency": 1.0, "periodo": "2024-03-31"}
    return [
        {**base, "journalentryid": je_id, "lineid": 1, "date": date, "accountnumber": "111005", "description": "Pago", "debit": 100000, "credit": 0},
        {**base, "journalentryid": je_id, "lineid": 2, "date": date, "accountnumber": "411005", "description": "Pago", "debit": 0, "credit": 100000},
    ]


# ── happy path + import-log (AC7) ────────────────────────────────────────────


def test_incremental_run_writes_and_logs(tmp_path):
    root = _ledger_root(tmp_path)
    result = laudus_run.run_import(mode="incremental", fetch_fn=lambda f, t: _balanced(), ledger_root=root)
    assert result["success"] is True
    assert result["jes_added"] == 1
    assert (root / "imports" / "laudus" / "2024-03.beancount").exists()
    # import-log line carries importer="laudus" + timestamp (consumed by Story 9.2).
    log_line = (root / "_meta" / "import-log.jsonl").read_text(encoding="utf-8").strip()
    record = json.loads(log_line)
    assert record["importer"] == "laudus"
    assert record["timestamp"]
    assert record["success"] is True


def test_git_disabled_by_default(tmp_path):
    root = _ledger_root(tmp_path)
    result = laudus_run.run_import(fetch_fn=lambda f, t: _balanced(), ledger_root=root)
    assert result["git_commit_sha"] is None


# ── incremental from_date resolution (AC2) ───────────────────────────────────


def test_incremental_from_date_advances(tmp_path):
    root = _ledger_root(tmp_path)
    seen = []

    def fetch(date_from, date_to):
        seen.append(date_from)
        return _balanced(je_id=len(seen), date="2024-03-15")

    laudus_run.run_import(fetch_fn=fetch, ledger_root=root)   # first run, no prior data
    laudus_run.run_import(fetch_fn=fetch, ledger_root=root)   # second run
    assert seen[0] == "2021-01-01"          # default start
    assert seen[1] == "2024-03-16"          # day after the latest written JE


def test_incremental_from_date_applies_overlap_window(tmp_path):
    """Story 2.4 / code-review #1: con un JE reciente, el from_date incremental retrocede por la
    ventana solapada (no forward-only) → recupera asientos backdateados en la nueva fuente Beancount."""
    from datetime import date
    from dateutil.relativedelta import relativedelta

    root = _ledger_root(tmp_path)
    recent = date.today().replace(day=15)
    laudus_run.run_import(fetch_fn=lambda f, t: _balanced(date=recent.isoformat()), ledger_root=root)

    nxt = date.fromisoformat(laudus_run._incremental_from_date(root / "imports" / "laudus"))
    # No es recent+1 (forward-only): retrocede ~13 meses por la ventana.
    assert nxt <= date.today() - relativedelta(months=12)


def test_no_new_dates_skips_fetch(tmp_path):
    root = _ledger_root(tmp_path)
    called = []
    # backfill with a future from_date → start > today → no fetch.
    result = laudus_run.run_import(
        mode="backfill", from_date="2099-01-01",
        fetch_fn=lambda f, t: called.append(1) or _balanced(), ledger_root=root,
    )
    assert result["success"] is True
    assert called == []


# ── bean-check failure → rollback (AC7) ──────────────────────────────────────


def test_bean_check_failure_rolls_back(tmp_path):
    root = _ledger_root(tmp_path)

    # Single-posting JE → does not balance → bean-check fails.
    def bad_fetch(f, t):
        return [{
            "journalentryid": 9, "journalentrynumber": 1, "date": "2024-04-10",
            "accountnumber": "111005", "lineid": 1, "description": "Unbalanced",
            "debit": 500, "credit": 0, "currencycode": "CLP",
            "paritytomaincurrency": 1.0, "periodo": "2024-04-30",
        }]

    result = laudus_run.run_import(fetch_fn=bad_fetch, ledger_root=root)
    assert result["success"] is False
    assert "bean-check failed" in result["error_msg"]
    # rollback: the month file was removed (did not exist before the run).
    assert not (root / "imports" / "laudus" / "2024-04.beancount").exists()


def test_fetch_error_reported_not_masked(tmp_path):
    """A fetch failure (e.g. Laudus 422/auth) → success False + import-log, not silent +0 JE."""
    root = _ledger_root(tmp_path)

    def boom(date_from, date_to):
        raise RuntimeError("Laudus ledger fetch failed (HTTP 422)")

    result = laudus_run.run_import(fetch_fn=boom, ledger_root=root)
    assert result["success"] is False
    assert "422" in result["error_msg"]
    log = (root / "_meta" / "import-log.jsonl").read_text(encoding="utf-8").strip()
    assert json.loads(log)["success"] is False


# ── lock file (AC8) ──────────────────────────────────────────────────────────


def test_lock_released_after_use(tmp_path):
    lock = tmp_path / ".import.lock"
    with laudus_run.acquire_lock(lock):
        assert lock.exists()
    assert not lock.exists()


def test_lock_timeout_when_fresh_lock_present(tmp_path):
    lock = tmp_path / ".import.lock"
    lock.write_text("999999", encoding="utf-8")  # fresh foreign lock
    with pytest.raises(laudus_run.LockTimeout):
        with laudus_run.acquire_lock(lock, timeout=0):
            pass


def test_lock_removes_stale(tmp_path):
    lock = tmp_path / ".import.lock"
    lock.write_text("999999", encoding="utf-8")
    old = time.time() - 600  # 10 min ago > max_age 300
    import os
    os.utime(lock, (old, old))
    with laudus_run.acquire_lock(lock, timeout=0, max_age=300):
        assert lock.exists()  # acquired (stale removed, re-created by us)
    assert not lock.exists()


# ── bean_check helper ────────────────────────────────────────────────────────


def test_bean_check_ok_and_fail(tmp_path):
    root = _ledger_root(tmp_path)
    ok, _ = laudus_run.bean_check(root / "main.beancount")
    assert ok is True
    bad = tmp_path / "bad.beancount"
    bad.write_text('2024-01-01 * "x"\n  Assets:Foo 1 CLP\n', encoding="utf-8")
    ok2, detail = laudus_run.bean_check(bad)
    assert ok2 is False
    assert detail
