"""LedgerService — loads `ledger/main.beancount` into memory (Story 9.2 AC1).

Singleton loader for the Beancount ledger. Mirrors the proven pattern in
`integrations/bank_account_index.py` (synchronous load behind a threading lock,
usable from sync FastAPI endpoints) and adds the async `watchfiles.awatch`
background watcher required by AC1 so external edits (Fava, importers) trigger
a reload without waiting for the next request.

Load errors (`bean-check` failures) are logged but never crash the backend:
consumers call `connection()` / `entries()` which raise `LedgerUnavailableError`,
and the dashboard router translates that into HTTP 503 LEDGER_UNAVAILABLE.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone

import beanquery
from beancount import loader
from watchfiles import awatch

logger = logging.getLogger(__name__)


class LedgerUnavailableError(RuntimeError):
    """Raised when the ledger has parse errors and cannot be queried.

    Carries `detail` (a human-readable summary of the load errors) so the
    router can surface it in the 503 response body.
    """

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def _format_errors(errors: list) -> str:
    """Compact, human-readable summary of beancount load errors."""
    return "; ".join(str(getattr(e, "message", e)) for e in errors[:5])


class LedgerService:
    """Process-wide singleton holding the loaded Beancount ledger.

    Lazy-loads on first access; reloads on `load()` (called by the watcher or
    explicitly). Thread-safe via a single lock around the load.
    """

    def __init__(self, main_path: str) -> None:
        self._main_path = main_path
        self._entries: list | None = None
        self._errors: list | None = None
        self._options: dict | None = None
        self._loaded_at: datetime | None = None
        self._lock = threading.Lock()

    def _picklecache_path(self) -> str:
        """Ruta del picklecache de beancount para `main.beancount` (misma convención que la lib)."""
        d, base = os.path.split(self._main_path)
        return os.path.join(d, "." + base + ".picklecache")

    def load(self) -> None:
        """(Re)load the ledger from disk. Errors are stored, not raised."""
        with self._lock:
            # beancount cachea el ledger por mtime del top-file + includes CONOCIDOS. Una cartola
            # recién importada entra por glob (`include imports/cartolas/*.beancount`) sin cambiar el
            # mtime de main.beancount, así que el cache no se invalida y load_file devuelve datos
            # viejos (sin la cartola nueva). Borramos el cache para forzar re-parseo en cada reload.
            try:
                os.remove(self._picklecache_path())
            except FileNotFoundError:
                pass
            self._entries, self._errors, self._options = loader.load_file(self._main_path)
            self._loaded_at = datetime.now(timezone.utc)
            if self._errors:
                logger.warning(
                    "LedgerService: %s loaded with %d errors",
                    self._main_path, len(self._errors),
                )
            else:
                logger.info("LedgerService: loaded %d entries from %s",
                            len(self._entries), self._main_path)

    def _ensure_loaded(self) -> None:
        if self._entries is None:
            self.load()

    @property
    def main_path(self) -> str:
        """Ruta a `main.beancount`. Su dir es la raíz del ledger (Story 10.3 escribe ahí)."""
        return self._main_path

    @property
    def available(self) -> bool:
        """True if the ledger is loaded and has no parse errors."""
        self._ensure_loaded()
        return not self._errors

    @property
    def errors(self) -> list:
        self._ensure_loaded()
        return list(self._errors or [])

    @property
    def loaded_at(self) -> datetime | None:
        return self._loaded_at

    def entries(self) -> list:
        """Loaded entries. Raises LedgerUnavailableError if the ledger is broken."""
        self._ensure_loaded()
        if self._errors:
            raise LedgerUnavailableError(_format_errors(self._errors))
        return self._entries

    def connection(self) -> beanquery.Connection:
        """A fresh beanquery connection over the loaded entries.

        Raises LedgerUnavailableError if the ledger has parse errors.
        """
        self._ensure_loaded()
        if self._errors:
            raise LedgerUnavailableError(_format_errors(self._errors))
        return beanquery.connect(
            "beancount:",
            entries=self._entries,
            errors=self._errors,
            options=self._options,
        )

    async def watch_and_reload(self) -> None:
        """Background task: reload when any `.beancount` file in the ledger dir changes.

        No-op if the ledger directory does not exist (pre-bootstrap). Wired into
        the FastAPI lifespan in `backend/main.py`.
        """
        watch_dir = os.path.dirname(self._main_path) or "."
        if not os.path.isdir(watch_dir):
            logger.warning("LedgerService: watch dir %s missing — watcher disabled", watch_dir)
            return
        async for changes in awatch(watch_dir, recursive=True):
            if any(str(path).endswith(".beancount") for _, path in changes):
                logger.info("LedgerService: ledger change detected — reloading")
                self.load()
