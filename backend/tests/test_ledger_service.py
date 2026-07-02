"""Tests for LedgerService — Story 9.2 AC1."""
import asyncio

import pytest

from backend.app.services.ledger_service import LedgerService, LedgerUnavailableError


VALID_LEDGER = """\
option "operating_currency" "CLP"
1900-01-01 commodity CLP

2020-01-01 open Assets:EAG:Bancos:TestBank-111005 CLP
  code: "111005"

2024-03-15 * "Pago cliente"
  Assets:EAG:Bancos:TestBank-111005   100000 CLP
  Equity:EAG:Opening                 -100000 CLP

2020-01-01 open Equity:EAG:Opening CLP
"""

BROKEN_LEDGER = """\
option "operating_currency" "CLP"
1900-01-01 commodity CLP

2020-01-01 open Assets:EAG:Bancos:TestBank-111005 CLP

2024-03-15 * "Unbalanced — should raise a load error"
  Assets:EAG:Bancos:TestBank-111005   100000 CLP
"""


def _write(path, content):
    path.write_text(content, encoding="utf-8")
    return str(path)


# ── load + get entries ──────────────────────────────────────────────────────


def test_load_populates_entries(tmp_path):
    """AC1: load() populates entries from a valid ledger."""
    main = _write(tmp_path / "main.beancount", VALID_LEDGER)
    svc = LedgerService(main)
    svc.load()
    assert svc.available is True
    assert len(svc.entries()) > 0
    assert svc.loaded_at is not None


def test_lazy_load_on_first_access(tmp_path):
    """AC1: entries() lazy-loads on first call without an explicit load()."""
    main = _write(tmp_path / "main.beancount", VALID_LEDGER)
    svc = LedgerService(main)
    assert svc.entries()  # triggers load
    assert svc.available is True


def test_reload_reflects_file_change(tmp_path):
    """AC1: a second load() after the file changes returns updated entries."""
    main_path = tmp_path / "main.beancount"
    _write(main_path, VALID_LEDGER)
    svc = LedgerService(str(main_path))
    svc.load()
    count_before = len(svc.entries())

    _write(main_path, VALID_LEDGER + """
2024-04-01 * "Otra transacción"
  Assets:EAG:Bancos:TestBank-111005   5000 CLP
  Equity:EAG:Opening                 -5000 CLP
""")
    svc.load()
    assert len(svc.entries()) > count_before


def test_load_removes_stale_picklecache(tmp_path):
    """Regresión: load() borra el picklecache de beancount. Una cartola nueva entra por glob sin
    cambiar el mtime de main.beancount, así que el cache no se invalida solo y load_file devolvería
    datos viejos (la cartola no aparece en Categorías Pendientes) — por eso lo borramos en cada load."""
    main_path = tmp_path / "main.beancount"
    _write(main_path, VALID_LEDGER)
    svc = LedgerService(str(main_path))
    svc.load()
    cache = tmp_path / ".main.beancount.picklecache"
    cache.write_bytes(b"stale-cache")
    svc.load()
    assert not cache.exists()


# ── broken ledger → unavailable + 503 path ───────────────────────────────────


def test_broken_ledger_marks_unavailable(tmp_path):
    """AC1: a ledger with parse/validation errors → available False, errors logged."""
    main = _write(tmp_path / "main.beancount", BROKEN_LEDGER)
    svc = LedgerService(main)
    svc.load()
    assert svc.available is False
    assert len(svc.errors) > 0


def test_broken_ledger_entries_raises(tmp_path):
    """AC1: entries() raises LedgerUnavailableError when the ledger is broken."""
    main = _write(tmp_path / "main.beancount", BROKEN_LEDGER)
    svc = LedgerService(main)
    with pytest.raises(LedgerUnavailableError):
        svc.entries()


def test_broken_ledger_connection_raises(tmp_path):
    """AC1: connection() raises LedgerUnavailableError when the ledger is broken."""
    main = _write(tmp_path / "main.beancount", BROKEN_LEDGER)
    svc = LedgerService(main)
    with pytest.raises(LedgerUnavailableError):
        svc.connection()


def test_connection_usable_for_bql(tmp_path):
    """AC1: connection() returns a usable beanquery connection for valid ledgers."""
    main = _write(tmp_path / "main.beancount", VALID_LEDGER)
    svc = LedgerService(main)
    conn = svc.connection()
    cur = conn.execute('SELECT account WHERE account ~ "^Assets:EAG"')
    assert len(cur.fetchall()) >= 1


# ── watcher ───────────────────────────────────────────────────────────────────


def test_watch_and_reload_no_op_on_missing_dir(tmp_path):
    """AC1: watcher returns immediately (no hang) if the ledger dir is missing."""
    svc = LedgerService(str(tmp_path / "missing" / "main.beancount"))
    # Should complete near-instantly, not block on awatch.
    asyncio.run(asyncio.wait_for(svc.watch_and_reload(), timeout=5))
