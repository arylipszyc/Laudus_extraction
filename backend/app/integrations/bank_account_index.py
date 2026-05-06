"""In-memory index of bank accounts parsed from `accounts.beancount`.

Story 9.5 Task 4: replaces the Supabase `bank_accounts` table.
The metadata `bank_account_id`, `bank_name`, `bank_account_type`,
`bank_account_currency`, `bank_account_last4` live as `Open` directive metadata
in `ledger/accounts.beancount` (modelo unificado, decisión 2026-05-05).

Cache invalidation strategy: file mtime check on every read. Cheap (~µs) and
guarantees freshness without coupling to a file watcher.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from beancount.loader import load_file
from beancount.core.data import Open

logger = logging.getLogger(__name__)


# Story 9.13 + architecture-c4 §2.3 — Categoria1 (Laudus) → entity mapping.
# Centralised so 9.5 (cartola source resolution) and 9.7 (categorization) share
# the same authoritative table.
_ENTITY_PREFIXES: dict[str, str] = {
    # EAG-rooted
    "ACTIVO EAG": "EAG",
    "PASIVO": "EAG",
    "INGRESOS": "EAG",
    "GASTOS - EGRESOS": "EAG",
}
_FAMILY_NAMES = ("Jocelyn", "Jeannette", "Johanna", "Jael")


def _resolve_entity(categoria1: str | None) -> str | None:
    """Map laudus_categoria1 → entity per architecture-c4 §2.3.

    Returns None if categoria1 is missing or not in the mapping table; caller
    decides whether to error or default.
    """
    if not categoria1:
        return None
    if categoria1 in _ENTITY_PREFIXES:
        return _ENTITY_PREFIXES[categoria1]
    # `DISPONIBLE {NOMBRE}` / `EGRESOS {NOMBRE}` / `INGRESOS {NOMBRE}`
    for name in _FAMILY_NAMES:
        if name in categoria1:
            return name
    return None


@dataclass(frozen=True)
class BankAccountEntry:
    """Resolved metadata for a single bank account.

    Mirrors `CartolaSource` plus internal fields the index keeps for matching.
    """
    bank_account_id: str
    bank_name: str
    account_label: str
    account_type: str
    entity: str
    currency: str
    last4: str | None
    beancount_account: str  # full Beancount account name (Assets:EAG:Bancos:...)


class BankAccountIndex:
    """Thread-safe, lazily-loaded index keyed by `bank_account_id`.

    Reload triggers on `accounts.beancount` mtime change (cheap stat call) or on
    explicit `reload()` call (admin endpoint).
    """

    def __init__(self, accounts_file: Path) -> None:
        self._file = accounts_file
        self._lock = threading.Lock()
        self._mtime: float | None = None
        self._by_id: dict[str, BankAccountEntry] = {}
        self._load_errors: list[str] = []

    def _load(self) -> None:
        entries, errors, _ = load_file(str(self._file))
        if errors:
            self._load_errors = [str(e) for e in errors]
            logger.warning(
                "bank_account_index: accounts.beancount has %d load errors", len(errors)
            )
        else:
            self._load_errors = []

        by_id: dict[str, BankAccountEntry] = {}
        for entry in entries:
            if not isinstance(entry, Open):
                continue
            meta = entry.meta or {}
            bank_account_id = meta.get("bank_account_id")
            if not bank_account_id:
                continue
            bank_name = meta.get("bank_name") or ""
            account_type = meta.get("bank_account_type") or ""
            currency = meta.get("bank_account_currency") or (
                entry.currencies[0] if entry.currencies else ""
            )
            last4 = meta.get("bank_account_last4")
            laudus_account_name = meta.get("laudus_account_name") or entry.account
            categoria1 = meta.get("laudus_categoria1")
            entity = _resolve_entity(categoria1) or "EAG"

            by_id[str(bank_account_id)] = BankAccountEntry(
                bank_account_id=str(bank_account_id),
                bank_name=str(bank_name),
                account_label=str(laudus_account_name),
                account_type=str(account_type),
                entity=entity,
                currency=str(currency),
                last4=str(last4) if last4 is not None else None,
                beancount_account=entry.account,
            )

        self._by_id = by_id
        self._mtime = self._file.stat().st_mtime
        logger.info("bank_account_index: loaded %d bank accounts", len(by_id))

    def _ensure_fresh(self) -> None:
        with self._lock:
            try:
                current_mtime = self._file.stat().st_mtime
            except FileNotFoundError as exc:
                raise RuntimeError(
                    f"accounts.beancount not found at {self._file}"
                ) from exc
            if self._mtime is None or current_mtime != self._mtime:
                self._load()

    def reload(self) -> int:
        """Force reload (admin endpoint). Returns count of indexed accounts."""
        with self._lock:
            self._load()
        return len(self._by_id)

    def get(self, bank_account_id: str) -> BankAccountEntry | None:
        self._ensure_fresh()
        return self._by_id.get(bank_account_id)

    def list_active(self) -> list[BankAccountEntry]:
        """All indexed bank accounts. `accounts.beancount` only contains active
        accounts (closed accounts get a `close` directive); inactive ones are
        not exposed via `Open` directive metadata."""
        self._ensure_fresh()
        return list(self._by_id.values())

    @property
    def load_errors(self) -> list[str]:
        return list(self._load_errors)


# ── Singleton wiring ──────────────────────────────────────────────────────


_DEFAULT_ACCOUNTS_PATH = Path(
    os.getenv("LEDGER_ACCOUNTS_FILE")
    or Path(__file__).resolve().parents[3] / "ledger" / "accounts.beancount"
)

_singleton: BankAccountIndex | None = None
_singleton_lock = threading.Lock()


def get_bank_account_index() -> BankAccountIndex:
    """FastAPI dependency. Returns a process-wide singleton."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = BankAccountIndex(_DEFAULT_ACCOUNTS_PATH)
    return _singleton


def reset_bank_account_index_for_testing() -> None:
    """Test helper — clears the singleton between tests."""
    global _singleton
    with _singleton_lock:
        _singleton = None
