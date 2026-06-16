"""BankAccountResolver — resuelve `bank_account_id` → cuenta Beancount (Story 9.6a AC2).

Lee `accounts.beancount` (parseado al boot, cached in-memory) e indexa por la
metadata `bank_account_id`. **NO consulta Supabase ni ningún registry separado**
(decisión 2026-05-05: modelo unificado, todo vive en accounts.beancount).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from beancount.core.data import Open
from beancount.parser import parser


@dataclass(frozen=True)
class ResolvedAccount:
    account: str          # full Beancount account name
    account_type: str     # tarjeta_credito | cta_corriente | ...
    currency: str
    last4: str | None
    bank_name: str


class UnknownBankAccount(KeyError):
    """`bank_account_id` no está en accounts.beancount."""


class BankAccountResolver:
    def __init__(self, accounts_path: str | os.PathLike) -> None:
        self._accounts_path = str(accounts_path)
        self._index: dict[str, ResolvedAccount] | None = None

    def _load(self) -> dict[str, ResolvedAccount]:
        entries, _errors, _options = parser.parse_file(self._accounts_path)
        index: dict[str, ResolvedAccount] = {}
        for e in entries:
            if not isinstance(e, Open):
                continue
            meta = e.meta or {}
            bank_account_id = meta.get("bank_account_id")
            if not bank_account_id:
                continue
            index[str(bank_account_id)] = ResolvedAccount(
                account=e.account,
                account_type=str(meta.get("bank_account_type", "")),
                currency=str(meta.get("bank_account_currency", "") or (e.currencies[0] if e.currencies else "CLP")),
                last4=str(meta["bank_account_last4"]) if meta.get("bank_account_last4") else None,
                bank_name=str(meta.get("bank_name", "")),
            )
        return index

    def _ensure(self) -> dict[str, ResolvedAccount]:
        if self._index is None:
            self._index = self._load()
        return self._index

    def reload(self) -> int:
        """Rebuild the index (admin endpoint / file-watcher signal). Returns count."""
        self._index = self._load()
        return len(self._index)

    def get(self, bank_account_id: str) -> ResolvedAccount:
        index = self._ensure()
        try:
            return index[str(bank_account_id)]
        except KeyError as exc:
            raise UnknownBankAccount(
                f"bank_account_id {bank_account_id!r} no está en {self._accounts_path}"
            ) from exc

    def resolve(self, bank_account_id: str) -> str:
        """Full Beancount account name for the bank account."""
        return self.get(bank_account_id).account
