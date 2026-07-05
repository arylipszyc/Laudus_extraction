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
def acquire_lock(lock_path, timeout: int = 60, max_age: int = 300, poll: int = 5):
    """Filesystem lock guarding against concurrent writers (AC8).

    Waits while a fresh lock exists (polling); removes a stale lock (mtime older
    than `max_age`); raises LockTimeout after `timeout` seconds. Always released.
    """
    lock_path = Path(lock_path)
    waited = 0
    while lock_path.exists():
        age = time.time() - lock_path.stat().st_mtime
        if age > max_age:
            logger.warning("Removing stale import lock (age %.0fs)", age)
            lock_path.unlink(missing_ok=True)
            break
        if waited >= timeout:
            raise LockTimeout(f"Could not acquire {lock_path} within {timeout}s")
        time.sleep(poll)
        waited += poll
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(str(os.getpid()), encoding="utf-8")
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


# ── bean-check (AC7) ────────────────────────────────────────────────────────


def bean_check(main_path) -> tuple[bool, str]:
    """Validate the ledger. Returns (ok, detail). Programmatic equivalent of the
    `bean-check` CLI — same loader/validation engine."""
    _entries, errors, _options = loader.load_file(str(main_path))
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
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    subprocess.run(["git", "-C", toplevel, "add", *paths], check=True)
    # Nada staged → corrida idempotente (el writer es determinista; un re-fetch de la
    # ventana solapada regenera archivos bit-idénticos). No es un error: se omite el commit.
    if subprocess.run(["git", "-C", toplevel, "diff", "--cached", "--quiet"]).returncode == 0:
        logger.info("git: nada que commitear (corrida idempotente) — se omite commit/push")
        return None
    subprocess.run(["git", "-C", toplevel, "commit", "-m", message], check=True)
    # Sincroniza con el remoto ANTES de pushear: el ledger y el código viven en el MISMO repo/branch
    # (`main`), así que cualquier push de código mueve `origin` y dejaría este push rechazado
    # (non-fast-forward → "failed to fetch" en el import). Un fetch + rebase trae esos commits (tocan
    # archivos distintos → sin conflicto) y replaya el commit del ledger encima. Si el remoto no tiene
    # `main` todavía (primer push) el fetch falla → se omite el rebase y el push lo crea.
    fetched = subprocess.run(["git", "-C", toplevel, "fetch", "origin", "main"]).returncode == 0
    if fetched:
        rebase = subprocess.run(["git", "-C", toplevel, "rebase", "origin/main"])
        if rebase.returncode != 0:
            subprocess.run(["git", "-C", toplevel, "rebase", "--abort"])
            raise RuntimeError(
                "git rebase sobre origin/main falló (conflicto inesperado — ledger y código deberían "
                "tocar archivos distintos); no se pushea para no corromper el remoto")
    sha = subprocess.run(   # tras el rebase el HEAD puede tener otro sha → capturarlo acá
        ["git", "-C", toplevel, "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    subprocess.run(["git", "-C", toplevel, "push", "origin", "main"], check=True)
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


def _incremental_from_date(target_dir: Path) -> str:
    """Primer día a re-pedir en modo incremental.

    NO es forward-only: retrocede por la ventana solapada (misma lógica que el path Sheets,
    `pipeline.utils.dates.get_date_range`) para recuperar asientos posteados-tarde / con fecha
    contable retroactiva. Sin JEs previos → fecha de inicio por defecto (backfill completo).
    """
    jes = _parse_existing_jes(target_dir)
    dates = [je.date for je in jes.values() if je.date]
    if not dates:
        return _DEFAULT_FROM_DATE
    from pipeline.utils.dates import get_date_range
    date_from, _ = get_date_range(max(dates))
    return date_from.isoformat()


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
) -> dict:
    """Run one import. Returns a result dict (also appended to import-log)."""
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
    if mode == "backfill":
        start = from_date or _DEFAULT_FROM_DATE
    else:
        start = _incremental_from_date(target_dir)

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

    try:
        with acquire_lock(lock_path):
            if start > to_date:
                logger.info("No new dates to sync (%s > %s)", start, to_date)
                result["success"] = True
                append_import_log(meta_dir, result)
                return result

            rows = fetch_fn(start, to_date)
            logger.info("Fetched %d Laudus ledger rows (%s → %s)", len(rows), start, to_date)

            snapshot = _snapshot(list(target_dir.glob("*.beancount")) + [pending_path])
            write_result = write_jes(rows, target_dir, accounts_path, pending_path, replace=replace)
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
            result["git_commit_sha"] = git_commit_push(
                root, ["ledger/imports/laudus/", "ledger/imports/_new-accounts-pending.beancount"], message,
            )
            result["success"] = True
            append_import_log(meta_dir, result)
            logger.info(message)
            return result
    except LockTimeout as exc:
        result["error_msg"] = str(exc)
        logger.error("Import aborted: %s", exc)
        append_import_log(meta_dir, result)
        return result
    except Exception as exc:  # fetch/write failure → report, don't mask as success
        result["error_msg"] = str(exc)
        logger.error("Import failed: %s", exc, exc_info=True)
        append_import_log(meta_dir, result)
        return result


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    _mode = os.getenv("IMPORTER_MODE", "incremental")
    _from = os.getenv("IMPORTER_FROM_DATE")
    run_import(mode=_mode, from_date=_from)
