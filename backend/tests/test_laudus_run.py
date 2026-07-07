"""Tests for the Laudus importer orchestrator — Story 9.4 AC2/AC5/AC7/AC8/AC9."""
import json
import subprocess
import time

import pytest

from pipeline.importers import laudus_run


def _init_git_repo(path):
    """Repo git mínimo y autónomo (sin firma ni red) para ejercitar git_commit_push."""
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@test"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "commit.gpgsign", "false"], check=True)

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


def test_git_commit_push_stages_from_repo_toplevel(tmp_path, monkeypatch):
    """code-review pathspec: git_commit_push resuelve el toplevel real del repo, así stagea
    `ledger/imports/...` aunque reciba la subcarpeta `ledger` como repo_root (regresión del bug
    `pathspec did not match` que dejaba success sin push)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    target = repo / "ledger" / "imports" / "laudus"
    target.mkdir(parents=True)
    (target / "2024-03.beancount").write_text("; data\n", encoding="utf-8")
    monkeypatch.setenv("IMPORTER_GIT_ENABLED", "true")

    sha = laudus_run.git_commit_push(repo / "ledger", ["ledger/imports/laudus/"], "msg")

    assert sha  # commit creado pese a recibir la subcarpeta como repo_root
    tracked = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "ledger/imports/laudus/"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "2024-03.beancount" in tracked


def test_git_commit_push_rebasea_cuando_origin_se_movio(tmp_path, monkeypatch):
    """El ledger y el código comparten `main`: si un push de código movió `origin` entre medio, el
    push del import haría non-fast-forward (el "failed to fetch"). git_commit_push hace fetch+rebase
    → trae el commit ajeno (archivo distinto), replaya el del ledger encima y pushea sin conflicto."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)

    # repo del backend: commit inicial + push (crea main en el remoto).
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "seed"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "push", "origin", "main"], check=True, capture_output=True)

    # otra copia mueve origin (simula un push de CÓDIGO): commit en un archivo distinto.
    other = tmp_path / "other"
    subprocess.run(["git", "clone", str(remote), str(other)], check=True, capture_output=True)
    _init_git_repo(other)  # config user en la copia
    subprocess.run(["git", "-C", str(other), "remote", "set-url", "origin", str(remote)], check=True)
    (other / "codigo.py").write_text("print('x')\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(other), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(other), "commit", "-m", "cambio de codigo"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(other), "push", "origin", "main"], check=True, capture_output=True)

    # el repo del backend quedó ATRÁS. Ahora importa (archivo del ledger) → antes daba push rechazado.
    target = repo / "ledger" / "imports" / "laudus"
    target.mkdir(parents=True)
    (target / "2024-03.beancount").write_text("; data\n", encoding="utf-8")
    monkeypatch.setenv("IMPORTER_GIT_ENABLED", "true")

    sha = laudus_run.git_commit_push(repo / "ledger", ["ledger/imports/laudus/"], "import ledger")

    assert sha  # pushó (fetch+rebase evitó el non-fast-forward)
    # tras rebase+push, el HEAD del repo tiene AMBOS: el commit ajeno de código Y el del ledger.
    files = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "codigo.py" in files                                   # el commit ajeno se trajo con el rebase
    assert "ledger/imports/laudus/2024-03.beancount" in files     # el del ledger quedó encima


def test_git_commit_push_noop_when_nothing_staged(tmp_path, monkeypatch):
    """Corrida idempotente (nada cambió) → None sin raise; no es un fallo (preserva review #10)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    target = repo / "ledger" / "imports" / "laudus"
    target.mkdir(parents=True)
    (target / "2024-03.beancount").write_text("; data\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)
    monkeypatch.setenv("IMPORTER_GIT_ENABLED", "true")

    # Segunda pasada sin cambios → no-op (None), no toca el remoto (no hay).
    assert laudus_run.git_commit_push(repo / "ledger", ["ledger/imports/laudus/"], "msg") is None


def test_run_import_marks_failure_when_push_fails(tmp_path, monkeypatch):
    """Anti silent-success: si el git push falla (sin remoto/deploy key), la corrida NO queda
    como success — el orquestador propaga el fallo a result['success']=False."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    root = _ledger_root(repo)  # ledger dentro del working tree git, sin 'origin' → push falla
    monkeypatch.setenv("IMPORTER_GIT_ENABLED", "true")

    result = laudus_run.run_import(fetch_fn=lambda f, t: _balanced(), ledger_root=root)

    assert result["success"] is False
    assert result["error_msg"]


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


def test_bean_check_ignores_stale_picklecache(tmp_path):
    """Fix review 2026-07-06 (B1): un archivo nuevo que entra por glob-include no invalida
    el picklecache de beancount → bean_check validaba el ledger VIEJO y aprobaba cualquier
    cosa (misma clase de bug que el fixture de d71f0fe, pero en el gate de producción)."""
    from beancount import loader as bean_loader

    import pickle

    root = _ledger_root(tmp_path)
    main = root / "main.beancount"
    # Prime del cache con el ledger válido. beancount solo escribe el picklecache
    # cuando el load tarda >1s (PICKLE_CACHE_THRESHOLD), así que lo fabricamos con
    # el MISMO contenido que escribiría la lib: el triple (entries, errors, options).
    result = bean_loader.load_file(str(main))
    assert "input_hash" in result[2], "precondición: el options_map debe traer input_hash"
    cache = root / ".main.beancount.picklecache"
    cache.write_bytes(pickle.dumps(result))
    # Sanity: sin cambios en los includes CONOCIDOS, el cache se consideraría fresco.
    assert bean_loader.needs_refresh(result[2]) is False

    # Archivo NUEVO y ROTO que entra por el glob `imports/laudus/*.beancount` sin
    # tocar el mtime de main.beancount → invisible para el cache.
    (root / "imports" / "laudus" / "zz-broken.beancount").write_text(
        '2024-05-01 * "desbalanceada"\n  Assets:EAG:Bancos:BancoBci-111005  100 CLP\n',
        encoding="utf-8",
    )

    # Control negativo: un load_file crudo CONSUME el cache stale y devuelve 0 errores
    # (no ve el archivo roto) — prueba que el escenario reproduce el bug de verdad.
    _e, cached_errors, _o = bean_loader.load_file(str(main))
    assert cached_errors == [], "precondición: sin el fix, el cache stale oculta el archivo roto"
    assert cache.exists(), "precondición: el cache stale sigue ahí para bean_check"

    ok, detail = laudus_run.bean_check(main)
    assert ok is False, "bean_check debe ver el archivo nuevo, no el cache viejo"
    assert detail


def test_git_commit_push_manda_timeout_en_todos_los_subprocess(tmp_path, monkeypatch):
    """Fix review 2026-07-06 (C1/D1): cada subprocess de git lleva timeout — sin él, un
    stall de red en fetch/push colgaba el request para siempre reteniendo .import.lock.
    El remote se siembra con un commit para que fetch SUCEDA y la rama del rebase
    (la más riesgosa) también se ejecute y quede cubierta por el assert."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "seed"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "push", "origin", "main"], check=True, capture_output=True)
    target = repo / "ledger" / "imports" / "laudus"
    target.mkdir(parents=True)
    (target / "2024-03.beancount").write_text("; data\n", encoding="utf-8")
    monkeypatch.setenv("IMPORTER_GIT_ENABLED", "true")

    real_run = subprocess.run
    seen: list[tuple[tuple, object]] = []

    def recording_run(cmd, *args, **kwargs):
        if cmd[0] == "git":
            seen.append((tuple(cmd), kwargs.get("timeout")))
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(laudus_run.subprocess, "run", recording_run)
    sha = laudus_run.git_commit_push(repo / "ledger", ["ledger/imports/laudus/"], "msg")

    assert sha
    assert any("rebase" in cmd for cmd, _ in seen), "el escenario debe ejercitar la rama del rebase"
    sin_timeout = [cmd for cmd, t in seen if t != laudus_run.GIT_TIMEOUT]
    assert not sin_timeout, f"subprocess git sin timeout: {sin_timeout}"


def test_git_commit_push_timeout_en_rebase_aborta_antes_de_propagar(tmp_path, monkeypatch):
    """Patch del review Fase 1: un rebase matado por timeout deja .git/rebase-merge y
    TODO git posterior falla — git_commit_push debe correr `rebase --abort` antes de
    propagar el TimeoutExpired."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "seed"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "push", "origin", "main"], check=True, capture_output=True)
    target = repo / "ledger" / "imports" / "laudus"
    target.mkdir(parents=True)
    (target / "2024-03.beancount").write_text("; data\n", encoding="utf-8")
    monkeypatch.setenv("IMPORTER_GIT_ENABLED", "true")

    real_run = subprocess.run
    aborts: list[tuple] = []

    def faking_run(cmd, *args, **kwargs):
        if cmd[0] == "git" and "rebase" in cmd:
            if "--abort" in cmd:
                aborts.append(tuple(cmd))
                return real_run(cmd, *args, **kwargs)
            raise subprocess.TimeoutExpired(cmd, laudus_run.GIT_TIMEOUT)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(laudus_run.subprocess, "run", faking_run)
    with pytest.raises(subprocess.TimeoutExpired):
        laudus_run.git_commit_push(repo / "ledger", ["ledger/imports/laudus/"], "msg")

    assert aborts, "TimeoutExpired en el rebase debe disparar `git rebase --abort`"


def test_incremental_parsea_existing_jes_una_sola_vez(tmp_path, monkeypatch):
    """Review 2026-07-06 D4b: el run incremental parseaba los JEs existentes DOS veces
    (from_date fuera del lock + write_jes adentro). Ahora: UN parse, dentro del lock,
    compartido con write_jes — y el from_date resultante no cambia."""
    from pipeline.writers import beancount_writer

    root = _ledger_root(tmp_path)
    # Primer run siembra JEs (parsea 1 vez un dir vacío).
    r1 = laudus_run.run_import(mode="incremental", fetch_fn=lambda f, t: _balanced(), ledger_root=root)
    assert r1["success"] is True

    calls = {"n": 0}
    real = beancount_writer._parse_existing_jes

    def counting(target_dir):
        calls["n"] += 1
        return real(target_dir)

    # Un solo símbolo real: laudus_run lo importó por nombre y write_jes usa el del módulo.
    monkeypatch.setattr(beancount_writer, "_parse_existing_jes", counting)
    monkeypatch.setattr(laudus_run, "_parse_existing_jes", counting)

    expected_from = laudus_run._incremental_from_date(root / "imports" / "laudus")
    calls["n"] = 0
    r2 = laudus_run.run_import(mode="incremental", fetch_fn=lambda f, t: _balanced(je_id=2, date="2024-04-10"),
                               ledger_root=root)
    assert r2["success"] is True
    assert calls["n"] == 1, f"_parse_existing_jes corrió {calls['n']} veces (debe ser 1)"
    assert r2["from_date"] == expected_from  # misma ventana solapada que antes


# ── Lock atómico + heartbeat (review 2026-07-06 B5) ─────────────────────────


def test_lock_contencion_solo_uno_adquiere(tmp_path):
    """B5a: con el lock tomado, un segundo intento con timeout=0 recibe LockTimeout
    (la adquisición es O_CREAT|O_EXCL, no exists()→write TOCTOU)."""
    import threading as th

    lock = tmp_path / ".import.lock"
    holding = th.Event()
    release = th.Event()
    results = []

    def holder():
        with laudus_run.acquire_lock(lock, timeout=0):
            holding.set()
            release.wait(timeout=10)

    t = th.Thread(target=holder)
    t.start()
    assert holding.wait(timeout=10)
    try:
        with pytest.raises(laudus_run.LockTimeout):
            with laudus_run.acquire_lock(lock, timeout=0):
                results.append("no debería entrar")
    finally:
        release.set()
        t.join(timeout=10)
    assert results == []
    assert not lock.exists()  # liberado por el holder


def test_lock_stale_robado_por_uno_solo(tmp_path):
    """B5a: dos waiters compiten por un lock stale — el unlink puede correr dos veces
    pero el O_EXCL del retry lo gana exactamente UNO; el otro ve el lock fresco del
    ganador y recibe LockTimeout (antes: ambos 'adquirían')."""
    import threading as th

    lock = tmp_path / ".import.lock"
    lock.write_text("999999", encoding="utf-8")
    old = time.time() - 600
    import os as _os
    _os.utime(lock, (old, old))

    barrier = th.Barrier(2)
    outcomes = []
    inside = th.Event()

    def waiter():
        barrier.wait(timeout=10)
        try:
            with laudus_run.acquire_lock(lock, timeout=0, max_age=300):
                inside.set()
                time.sleep(0.5)  # mantener el lock fresco mientras el otro reintenta
                outcomes.append("acquired")
        except laudus_run.LockTimeout:
            outcomes.append("timeout")
        except Exception as exc:  # noqa: BLE001 — visibilidad: un thread no puede morir mudo
            outcomes.append(f"error: {exc!r}")

    threads = [th.Thread(target=waiter) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    assert sorted(outcomes) == ["acquired", "timeout"], outcomes


def test_lock_heartbeat_renueva_mtime(tmp_path):
    """B5a: el heartbeat toca el mtime mientras el holder vive — una operación más
    larga que max_age ya no es 'stale' para un waiter."""
    lock = tmp_path / ".import.lock"
    with laudus_run.acquire_lock(lock, timeout=0, heartbeat=0.2):
        mtime_0 = lock.stat().st_mtime
        time.sleep(0.7)
        mtime_1 = lock.stat().st_mtime
        assert mtime_1 > mtime_0, "el heartbeat debe renovar el mtime del lock"
        # Y un waiter con max_age menor a lo dormido NO lo considera stale:
        age = time.time() - mtime_1
        assert age < 0.5
    assert not lock.exists()


def test_run_import_refresh_clone_corre_dentro_del_lock(tmp_path):
    """B5b: refresh_clone corre DENTRO del lock y ANTES del fetch — un reset --hard
    ya no puede pisar una escritura concurrente ni correr fuera de la sección crítica."""
    root = _ledger_root(tmp_path)
    lock = root / ".import.lock"
    events = []

    def refresh():
        events.append(("refresh", lock.exists()))

    def fetch(f, t):
        events.append(("fetch", lock.exists()))
        return _balanced()

    result = laudus_run.run_import(mode="incremental", fetch_fn=fetch,
                                   ledger_root=root, refresh_clone=refresh)
    assert result["success"] is True
    assert events == [("refresh", True), ("fetch", True)], events


def test_lock_release_no_borra_lock_ajeno(tmp_path):
    """Ownership por token (review batch 3): si el lock fue robado (proceso suspendido
    >max_age que revive), el release del holder original NO borra el lock del ladrón."""
    lock = tmp_path / ".import.lock"
    with laudus_run.acquire_lock(lock, timeout=0, heartbeat=30):
        # Simular el robo: otro writer reemplazó el lock con SU token.
        lock.write_text("otro-proceso-lock-ajeno", encoding="utf-8")
    assert lock.exists(), "el release sin ownership no debe borrar el lock del ladrón"
    assert lock.read_text(encoding="utf-8") == "otro-proceso-lock-ajeno"
    lock.unlink()


def test_lock_gc_de_steal_files_huerfanos(tmp_path):
    """Un crash a mitad del baile de robo deja `.import.lock.steal-*` huérfanos; la
    próxima adquisición los limpia si son viejos."""
    lock = tmp_path / ".import.lock"
    orphan = tmp_path / ".import.lock.steal-999-888"
    orphan.write_text("crash", encoding="utf-8")
    old = time.time() - 600
    import os as _os
    _os.utime(orphan, (old, old))
    fresh_orphan = tmp_path / ".import.lock.steal-777-666"
    fresh_orphan.write_text("reciente", encoding="utf-8")

    with laudus_run.acquire_lock(lock, timeout=0):
        pass
    assert not orphan.exists(), "steal viejo debe limpiarse"
    assert fresh_orphan.exists(), "steal reciente (baile en curso) no se toca"
