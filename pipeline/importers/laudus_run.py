"""Laudus → Beancount importer orchestrator — Story 9.4.

Reemplaza la orquestación de `pipeline/sync.py` (que sigue activa para el path
Sheets durante F3, §7.8) para el sink Beancount. Modos:

- `incremental` (default): trae JEs desde `max(date)` ya escrito + 1 día hasta hoy,
  mergea por `id` (no pierde data previa).
- `backfill`: regenera todos los meses desde `from_date` (mismo modo que el bootstrap
  de Story 9.1).

Efectos colaterales (lock, bean-check, git, import-log) están aislados y el `fetch`
es inyectable, para poder testear el orquestador sin red ni git.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from beancount import loader

from pipeline.writers.beancount_writer import write_jes, _parse_existing_jes

logger = logging.getLogger(__name__)

_DEFAULT_FROM_DATE = "2021-01-01"


# ── Paths ───────────────────────────────────────────────────────────────────


def _ledger_root() -> Path:
    """Repo `ledger/` dir. `LEDGER_DIR` overrides (Render persistent disk)."""
    override = os.getenv("LEDGER_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "ledger"


# ── Lock file (AC8) ─────────────────────────────────────────────────────────


class LockTimeout(RuntimeError):
    pass


@contextmanager
def acquire_lock(lock_path, timeout: int = 60, max_age: int = 300, poll: int = 5,
                 heartbeat: float = 60.0):
    """Filesystem lock guarding against concurrent writers (AC8).

    Adquisición ATÓMICA vía `os.open(O_CREAT|O_EXCL)` — el exists()→write_text previo
    era TOCTOU: dos procesos podían "adquirir" a la vez, y dos waiters podían robar el
    mismo lock stale. El robo de un stale (mtime > max_age) va por RENAME atómico con
    re-verificación. El OWNERSHIP es por token: heartbeat y release verifican que el
    archivo siga siendo NUESTRO antes de tocarlo/borrarlo (un holder suspendido que
    revive ya no puede borrar el lock de quien lo robó legítimamente). Un thread
    heartbeat renueva el mtime cada `heartbeat`s mientras el holder vive — una
    operación legítimamente larga (backfill) no puede ser robada a los 300s.
    Residual documentado: con ≥3 contendientes + veredicto stale sobre un lock fresco
    (heartbeat muerto 5 min con el holder vivo) + timing de μs, la devolución del robo
    puede dejar un lock fantasma que se auto-sana en ≤max_age. Always released.
    """
    import uuid

    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}-{threading.get_ident()}-{uuid.uuid4().hex[:8]}"
    heartbeat = max(heartbeat, 0.05)  # 0/negativo sería un busy-loop de utime

    def _owns() -> bool:
        try:
            return lock_path.read_text(encoding="utf-8") == token
        except OSError:
            return False

    # GC de steal-files huérfanos (crash a mitad del baile de robo): son inertes pero
    # ensucian el working tree del repo del ledger.
    for orphan in lock_path.parent.glob(f"{lock_path.name}.steal-*"):
        try:
            if time.time() - orphan.stat().st_mtime > max_age:
                orphan.unlink(missing_ok=True)
        except OSError:
            pass

    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, token.encode("utf-8"))
            finally:
                os.close(fd)
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except FileNotFoundError:
                continue  # se liberó entre el open y el stat → re-competir ya
            if age > max_age:
                # Robo por RENAME atómico (no unlink directo): un unlink con veredicto
                # viejo podía borrar el lock FRESCO que otro waiter acababa de crear.
                # os.replace lo gana uno solo; después se re-verifica lo movido.
                steal = lock_path.with_name(
                    f"{lock_path.name}.steal-{os.getpid()}-{threading.get_ident()}")
                try:
                    os.replace(lock_path, steal)
                    stolen_age = time.time() - steal.stat().st_mtime
                except OSError:
                    # Otro waiter movió/liberó/recreó el lock en el medio — cualquier
                    # rareza del filesystem acá significa "perdí la carrera": re-evaluar.
                    steal.unlink(missing_ok=True)
                    continue
                if stolen_age > max_age:
                    logger.warning("Removing stale import lock (age %.0fs)", stolen_age)
                    steal.unlink(missing_ok=True)
                else:
                    # Era fresco (otro lo recreó en la ventana). Devolverlo SIN clobber:
                    # os.link falla si ya hay un lock nuevo en el path (no se pisa a un
                    # tercero, a diferencia de os.replace).
                    try:
                        os.link(steal, lock_path)
                        logger.warning("Lock fresco robado por veredicto viejo — devuelto intacto")
                    except OSError:
                        logger.error(
                            "Robé un lock FRESCO y no pude devolverlo (¿tercer writer en el "
                            "path?) — su holder corre sin archivo de lock hasta terminar")
                    steal.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                raise LockTimeout(f"Could not acquire {lock_path} within {timeout}s")
            time.sleep(poll)

    stop = threading.Event()

    def _beat() -> None:
        while not stop.wait(heartbeat):
            if not _owns():
                continue  # ausente un instante (baile de robo) o robado: no renovar un lock AJENO
            try:
                now = time.time()
                os.utime(lock_path, (now, now))
            except OSError:
                continue

    beater = threading.Thread(target=_beat, daemon=True, name="import-lock-heartbeat")
    beater.start()
    try:
        yield
    finally:
        stop.set()
        beater.join(timeout=heartbeat + 1)
        if _owns():
            lock_path.unlink(missing_ok=True)
        else:  # nos lo robaron (proceso suspendido >max_age): NO borrar el lock del ladrón
            logger.warning("Release sin ownership del lock %s — no se borra (¿robado?)", lock_path)


# Tope para cada subprocess de git. fetch/rebase/push van por red: sin timeout, un
# stall de SSH deja el request colgado para siempre reteniendo `.import.lock`.
GIT_TIMEOUT = 60

# ── bean-check (AC7) ────────────────────────────────────────────────────────


def bean_check(main_path) -> tuple[bool, str]:
    """Validate the ledger. Returns (ok, detail). Programmatic equivalent of the
    `bean-check` CLI — same loader/validation engine."""
    # beancount cachea por mtime del top-file + includes CONOCIDOS: un archivo recién
    # escrito que entra por glob (`include imports/cartolas/*.beancount`) es INVISIBLE
    # para el cache → bean_check validaría el ledger viejo y aprobaría cualquier cosa.
    # Mismo workaround que LedgerService.load().
    main_path = str(main_path)
    d, base = os.path.split(main_path)
    try:
        os.remove(os.path.join(d, "." + base + ".picklecache"))
    except FileNotFoundError:
        pass
    except OSError as exc:  # ej. PermissionError si otro thread lo está escribiendo (Windows)
        logger.warning("bean_check: no pude borrar el picklecache (%s) — sigo sin cache fresco", exc)
    _entries, errors, _options = loader.load_file(main_path)
    if not errors:
        return True, ""
    detail = "; ".join(str(getattr(e, "message", e)) for e in errors[:10])
    return False, detail


# ── import-log (AC7 / Task 7) ───────────────────────────────────────────────


def append_import_log(meta_dir, record: dict) -> None:
    """Append one JSON line to `_meta/import-log.jsonl` (read by Story 9.2 /sync/status)."""
    meta_dir = Path(meta_dir)
    meta_dir.mkdir(parents=True, exist_ok=True)
    with (meta_dir / "import-log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _rewrite_last_import_log(meta_dir, record: dict) -> None:
    """Reemplaza la ÚLTIMA línea del import-log por `record`.

    Se usa cuando un fallo de commit/push invalida una entrada `success=True` ya
    appendeada ANTES del commit: sin esto el lector (`_read_import_log_last_sync`, que
    toma el max-timestamp de las corridas success) leería la línea fantasma como un sync
    fresco aunque a origin no llegó nada. Reescribir en el working-tree —lo que el lector
    consume— la deja como `success=False` → el indicador no avanza."""
    path = Path(meta_dir) / "import-log.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[-1] = json.dumps(record, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── git commit/push (AC9) — guarded ─────────────────────────────────────────


def git_commit_push(repo_root, paths: list[str], message: str) -> str | None:
    """Commit + push the given paths. No-op unless `IMPORTER_GIT_ENABLED=true`.

    `paths` son relativos al toplevel del repo (ej. `ledger/imports/laudus/`); se resuelve el
    toplevel desde `repo_root` para stagearlos bien aunque `repo_root` apunte a una subcarpeta
    (el ledger vive en `<repo>/ledger`). Returns the commit SHA; None cuando git está
    deshabilitado o no hay nada que commitear (corrida idempotente). Un fallo real de git
    (add/commit/push — ej. deploy key sin permiso) se PROPAGA para que el orquestador marque la
    corrida como fallida en vez de enmascararla como éxito sin push. Push auth en producción usa
    la SSH key `BEANCOUNT_DEPLOY_KEY` configurada en el servicio Render.
    """
    if os.getenv("IMPORTER_GIT_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        logger.info("git disabled (IMPORTER_GIT_ENABLED not set) — skipping commit/push")
        return None
    toplevel = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"],
        check=True, capture_output=True, text=True, timeout=GIT_TIMEOUT,
    ).stdout.strip()
    subprocess.run(["git", "-C", toplevel, "add", *paths], check=True, timeout=GIT_TIMEOUT)
    # Nada staged → corrida idempotente (el writer es determinista; un re-fetch de la
    # ventana solapada regenera archivos bit-idénticos). No es un error: se omite el commit.
    if subprocess.run(["git", "-C", toplevel, "diff", "--cached", "--quiet"],
                      timeout=GIT_TIMEOUT).returncode == 0:
        logger.info("git: nada que commitear (corrida idempotente) — se omite commit/push")
        return None
    subprocess.run(["git", "-C", toplevel, "commit", "-m", message], check=True, timeout=GIT_TIMEOUT)
    # Sincroniza con el remoto ANTES de pushear: el ledger y el código viven en el MISMO repo/branch
    # (`main`), así que cualquier push de código mueve `origin` y dejaría este push rechazado
    # (non-fast-forward → "failed to fetch" en el import). Un fetch + rebase trae esos commits (tocan
    # archivos distintos → sin conflicto) y replaya el commit del ledger encima. Si el remoto no tiene
    # `main` todavía (primer push) el fetch falla → se omite el rebase y el push lo crea.
    fetched = subprocess.run(["git", "-C", toplevel, "fetch", "origin", "main"],
                             timeout=GIT_TIMEOUT).returncode == 0
    if fetched:
        try:
            rebase = subprocess.run(["git", "-C", toplevel, "rebase", "origin/main"], timeout=GIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            # Un rebase matado a mitad deja .git/rebase-merge → todo git posterior fallaría
            # para siempre. Abortar el rebase ANTES de propagar el timeout.
            subprocess.run(["git", "-C", toplevel, "rebase", "--abort"], timeout=GIT_TIMEOUT)
            raise
        if rebase.returncode != 0:
            subprocess.run(["git", "-C", toplevel, "rebase", "--abort"], timeout=GIT_TIMEOUT)
            raise RuntimeError(
                "git rebase sobre origin/main falló (conflicto inesperado — ledger y código deberían "
                "tocar archivos distintos); no se pushea para no corromper el remoto")
    sha = subprocess.run(   # tras el rebase el HEAD puede tener otro sha → capturarlo acá
        ["git", "-C", toplevel, "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, timeout=GIT_TIMEOUT,
    ).stdout.strip()
    subprocess.run(["git", "-C", toplevel, "push", "origin", "main"], check=True, timeout=GIT_TIMEOUT)
    return sha


# ── snapshot/restore for rollback (AC7) ─────────────────────────────────────


def _snapshot(paths: list[Path]) -> dict[Path, str | None]:
    return {p: (p.read_text(encoding="utf-8") if p.exists() else None) for p in paths}


def _rollback(target_dir: Path, snapshot: dict[Path, str | None]) -> None:
    """Restore the snapshot: delete month files created during the run + revert content."""
    snapshot_paths = set(snapshot)
    for path in target_dir.glob("*.beancount"):
        if path not in snapshot_paths:
            path.unlink(missing_ok=True)
    for path, content in snapshot.items():
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(content, encoding="utf-8")


# ── from_date resolution ────────────────────────────────────────────────────


def _incremental_start(jes: dict) -> str:
    """Primer día a re-pedir en modo incremental, desde JEs YA parseados.

    NO es forward-only: retrocede por la ventana solapada (misma lógica que el path Sheets,
    `pipeline.utils.dates.get_date_range`) para recuperar asientos posteados-tarde / con fecha
    contable retroactiva. Sin JEs previos → fecha de inicio por defecto (backfill completo).
    """
    dates = [je.date for je in jes.values() if je.date]
    if not dates:
        return _DEFAULT_FROM_DATE
    from pipeline.utils.dates import get_date_range
    date_from, _ = get_date_range(max(dates))
    return date_from.isoformat()


def _incremental_from_date(target_dir: Path) -> str:
    """Wrapper que parsea y delega (lo usan tests; `run_import` parsea una sola vez)."""
    return _incremental_start(_parse_existing_jes(target_dir))


# ── default fetch (real Laudus) ─────────────────────────────────────────────


def _min_account_number() -> str:
    """Lowest account code in accounts.beancount (for `accountNumberFrom`)."""
    from pipeline.writers.beancount_writer import load_account_index
    codes = list(load_account_index(_ledger_root() / "accounts.beancount").keys())
    return min(codes) if codes else "1"


def default_fetch(date_from: str, date_to: str) -> list[dict]:
    """Fetch + normalize Laudus ledger rows for the range (real API).

    The Laudus `/accounting/ledger` endpoint requires `accountNumberFrom` — without
    it the API returns 422 (same param the legacy `pipeline/sync.py` path sets).
    A None response means the fetch failed (auth/HTTP error) and is raised so the
    importer reports failure instead of masking it as "0 new rows".
    """
    from pipeline.config.laudus_config import get_endpoints
    from pipeline.services.ledger_service import fetch_ledger
    from pipeline.models import map_ledger_row

    cfg = get_endpoints(date_from, date_to)["GET_LEDGER"]
    cfg["params"]["accountNumberFrom"] = _min_account_number()
    raw = fetch_ledger(cfg["url"], cfg["params"])
    if raw is None:
        raise RuntimeError(
            f"Laudus ledger fetch failed for {date_from}..{date_to} "
            f"(HTTP/auth error — check credentials and API status)"
        )
    return [map_ledger_row(item, date_to) for item in raw]


# ── orchestrator ────────────────────────────────────────────────────────────


def run_import(
    mode: str = "incremental",
    from_date: str | None = None,
    fetch_fn=default_fetch,
    ledger_root: Path | None = None,
    refresh_clone=None,
) -> dict:
    """Run one import. Returns a result dict (also appended to import-log).

    `refresh_clone`: callable opcional que trae el clon a origin/main; corre DENTRO
    del lock (patrón beancount_promote) — antes corría afuera y un `reset --hard`
    podía pisar una escritura concurrente de categorización."""
    root = Path(ledger_root) if ledger_root else _ledger_root()
    target_dir = root / "imports" / "laudus"
    accounts_path = root / "accounts.beancount"
    pending_path = root / "imports" / "_new-accounts-pending.beancount"
    main_path = root / "main.beancount"
    meta_dir = root / "_meta"
    lock_path = root / ".import.lock"

    target_dir.mkdir(parents=True, exist_ok=True)
    to_date = datetime.now(timezone.utc).date().isoformat()
    replace = mode == "backfill"
    # El from_date incremental sale de parsear los JEs existentes — eso ocurre DENTRO
    # del lock (abajo): un solo parse compartido con write_jes, y sin TOCTOU con otro
    # writer (antes se parseaba acá afuera y write_jes re-parseaba adentro).
    start = (from_date or _DEFAULT_FROM_DATE) if replace else None

    result = {
        "importer": "laudus",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "from_date": start,
        "to_date": to_date,
        "jes_added": 0,
        "jes_dedup": 0,
        "pending_accounts": 0,
        "success": False,
        "error_msg": None,
        "git_commit_sha": None,
    }
    # ¿Ya appendeamos una línea `success=True` (antes del commit)? Si sí y luego el
    # commit/push falla, el except REESCRIBE esa línea en vez de appendear otra —
    # así el indicador no lee la entrada fantasma como sync fresco.
    success_logged = False

    try:
        with acquire_lock(lock_path):
            if refresh_clone is not None:
                refresh_clone()  # dentro del lock → nadie escribe entre el reset y el import
            existing_jes = None
            if not replace:
                existing_jes = _parse_existing_jes(target_dir)
                start = _incremental_start(existing_jes)
                result["from_date"] = start
            if start > to_date:
                logger.info("No new dates to sync (%s > %s)", start, to_date)
                result["success"] = True
                append_import_log(meta_dir, result)
                success_logged = True
                # Commitear el import-log aun sin datos nuevos → el indicador refleja el último
                # CHEQUEO de Laudus (lo que el usuario espera), no el último sync con cambios.
                result["git_commit_sha"] = git_commit_push(
                    root, ["ledger/_meta/import-log.jsonl"],
                    f"[importer-laudus] check {to_date}: sin cambios",
                )
                return result

            rows = fetch_fn(start, to_date)
            logger.info("Fetched %d Laudus ledger rows (%s → %s)", len(rows), start, to_date)

            snapshot = _snapshot(list(target_dir.glob("*.beancount")) + [pending_path])
            write_result = write_jes(rows, target_dir, accounts_path, pending_path,
                                     replace=replace, existing_jes=existing_jes)
            result.update(
                jes_added=write_result.jes_added,
                jes_dedup=write_result.jes_dedup,
                pending_accounts=write_result.pending_accounts,
            )

            ok, detail = bean_check(main_path)
            if not ok:
                _rollback(target_dir, snapshot)
                result["error_msg"] = f"bean-check failed: {detail}"
                logger.error(result["error_msg"])
                append_import_log(meta_dir, result)
                return result

            message = (
                f"[importer-laudus] sync {to_date}: "
                f"+{write_result.jes_added} JE, {write_result.jes_dedup} dedup, "
                f"{write_result.pending_accounts} pending account"
            )
            result["success"] = True
            # Appendear ANTES del commit para que la entrada entre en el MISMO commit que los
            # datos: así sobrevive el fetch+rebase de git_commit_push (antes appendeaba después
            # → la línea quedaba working-tree, el rebase la revertía y origin/import-log se
            # congelaba → el indicador "Datos de Laudus al:" mostraba una fecha vieja). El sha
            # queda null en la línea (chicken-egg: el commit aún no existe); el lector solo usa
            # timestamp/importer/success, así que no importa.
            append_import_log(meta_dir, result)
            success_logged = True
            result["git_commit_sha"] = git_commit_push(
                root,
                ["ledger/imports/laudus/", "ledger/imports/_new-accounts-pending.beancount",
                 "ledger/_meta/import-log.jsonl"],
                message,
            )
            logger.info(message)
            return result
    except LockTimeout as exc:
        result["error_msg"] = str(exc)
        logger.error("Import aborted: %s", exc)
        append_import_log(meta_dir, result)
        return result
    except Exception as exc:  # fetch/write/push failure → report, don't mask as success
        # success ya pudo quedar True (se setea antes de appendear el log para commitearlo en
        # el mismo commit); revertir para que un fallo de commit/push NO reporte éxito.
        result["success"] = False
        result["error_msg"] = str(exc)
        logger.error("Import failed: %s", exc, exc_info=True)
        if success_logged:
            # El fallo fue en el commit/push, DESPUÉS de appendear la línea success=True.
            # Reescribirla como success=False para que el lector no la cuente como sync fresco
            # (en vez de dejar dos líneas contradictorias con el mismo timestamp).
            _rewrite_last_import_log(meta_dir, result)
        else:
            append_import_log(meta_dir, result)
        return result


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    _mode = os.getenv("IMPORTER_MODE", "incremental")
    _from = os.getenv("IMPORTER_FROM_DATE")
    run_import(mode=_mode, from_date=_from)
