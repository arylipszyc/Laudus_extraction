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


def _fake_awatch(batches, seen_kwargs=None):
    """awatch de mentira: emite las tandas dadas y termina (el real nunca termina).
    Si se pasa `seen_kwargs`, captura los kwargs con que el watcher invoca a awatch."""
    async def _gen(*_args, **kwargs):
        if seen_kwargs is not None:
            seen_kwargs.update(kwargs)
        for batch in batches:
            yield batch
    return _gen


def test_watch_and_reload_load_runs_off_loop(tmp_path, monkeypatch):
    """Fix review 2026-07-06 (C1): el load corre vía asyncio.to_thread — un load
    sincrónico acá congelaba el event loop (incluido /health) y Render reiniciaba.
    Una tanda de N archivos = UNA sola recarga."""
    import threading

    from backend.app.services import ledger_service as mod

    main_path = tmp_path / "main.beancount"
    _write(main_path, VALID_LEDGER)
    svc = LedgerService(str(main_path))

    load_threads: list[int] = []
    real_load = svc.load

    def tracking_load():
        load_threads.append(threading.get_ident())
        real_load()

    seen_kwargs: dict = {}
    monkeypatch.setattr(svc, "load", tracking_load)
    monkeypatch.setattr(mod, "awatch", _fake_awatch([
        {(1, str(tmp_path / "imports" / "a.beancount")),
         (1, str(tmp_path / "imports" / "b.beancount"))},
    ], seen_kwargs))

    loop_thread = threading.get_ident()
    asyncio.run(asyncio.wait_for(svc.watch_and_reload(), timeout=10))

    assert len(load_threads) == 1, "una tanda de cambios debe producir UNA recarga"
    assert load_threads[0] != loop_thread, "load debe correr en thread, no sobre el event loop"
    # Wire-up real hacia awatch: agrupación de ráfagas + recursividad (un typo acá shippearía verde).
    assert seen_kwargs.get("debounce") == 2000
    assert seen_kwargs.get("recursive") is True


def test_watch_and_reload_survives_load_error(tmp_path, monkeypatch):
    """Fix review 2026-07-06 (C1): un load que explota no mata el watcher — la
    tanda siguiente vuelve a recargar."""
    from backend.app.services import ledger_service as mod

    main_path = tmp_path / "main.beancount"
    _write(main_path, VALID_LEDGER)
    svc = LedgerService(str(main_path))

    calls: list[int] = []

    def broken_load():
        calls.append(1)
        raise RuntimeError("parse roto")

    monkeypatch.setattr(svc, "load", broken_load)
    monkeypatch.setattr(mod, "awatch", _fake_awatch([
        {(1, str(tmp_path / "a.beancount"))},
        {(1, str(tmp_path / "b.beancount"))},
    ]))

    asyncio.run(asyncio.wait_for(svc.watch_and_reload(), timeout=10))
    assert len(calls) == 2, "el watcher debe sobrevivir al load roto y procesar la tanda siguiente"


def test_watch_and_reload_ignores_non_beancount_changes(tmp_path, monkeypatch):
    """Cambios que no tocan `.beancount` (ej. .git durante un reset) no recargan."""
    from backend.app.services import ledger_service as mod

    main_path = tmp_path / "main.beancount"
    _write(main_path, VALID_LEDGER)
    svc = LedgerService(str(main_path))

    calls: list[int] = []
    monkeypatch.setattr(svc, "load", lambda: calls.append(1))
    monkeypatch.setattr(mod, "awatch", _fake_awatch([
        {(1, str(tmp_path / ".git" / "index"))},
    ]))

    asyncio.run(asyncio.wait_for(svc.watch_and_reload(), timeout=10))
    assert calls == []
