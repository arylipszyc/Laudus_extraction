"""Business logic for bank_accounts — Story 9.14: lee/escribe Beancount, no Supabase.

La metadata bancaria vive en los `open` de `accounts.beancount` (modelo unificado 9.1).
La lectura arma `BankAccount` desde el `LedgerService`; la escritura (crear/editar/desactivar)
reusa la máquina de promoción de 10.3 (`apply_to_accounts`: lock + bean-check + git).
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from uuid import uuid4

from beancount.core.data import Close, Open
from fastapi import HTTPException, status

from backend.app.api.v1.bank_accounts.schemas import BankAccount, BankAccountCreate, BankAccountUpdate
from backend.app.services.beancount_promote import (
    PromoteError,
    add_meta_to_open,
    append_close,
    apply_to_accounts,
    remove_close,
    set_open_meta,
)
from backend.app.services.ledger_service import LedgerService

logger = logging.getLogger(__name__)


def _write_ctx(ledger: LedgerService):
    """(ledger_root, refresh_clone) para las escrituras — derivados del LedgerService."""
    from backend.app.api.v1.sync.service import _refresh_ledger_clone
    return Path(ledger.main_path).parent, _refresh_ledger_clone


def _all_opens(entries: list) -> list[Open]:
    return [e for e in entries if isinstance(e, Open)]


def _bank_opens(entries: list) -> list[Open]:
    """Opens con metadata bancaria (`bank_account_id`) — el subset 'bank-accounts' del plan."""
    return [e for e in _all_opens(entries) if (e.meta or {}).get("bank_account_id")]


def list_bank_accounts(ledger: LedgerService) -> list[BankAccount]:
    """Lista las cuentas bancarias desde Beancount, ordenadas por `account_number` (AC1)."""
    entries = ledger.entries()
    closed = {e.account for e in entries if isinstance(e, Close)}
    out = [
        BankAccount.from_ledger_open(e.account, e.meta or {}, active=e.account not in closed)
        for e in _bank_opens(entries)
    ]
    out.sort(key=lambda b: b.account_number)
    return out


def create_bank_account(data: BankAccountCreate, ledger: LedgerService) -> BankAccount:
    """Marca una cuenta del plan como bank-account agregando metadata bancaria a su `open` (AC3).

    En el modelo unificado la cuenta YA tiene un `open` en accounts.beancount, así que crear =
    agregar metadata (NO appendear un open nuevo, que duplicaría → bean-check rojo).
    """
    entries = ledger.entries()
    open_for_code = next(
        (e for e in _all_opens(entries) if str((e.meta or {}).get("code", "")) == data.account_number),
        None,
    )
    if open_for_code is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"account_number '{data.account_number}' no existe en el plan de cuentas (accounts.beancount).",
        )
    if (open_for_code.meta or {}).get("bank_account_id"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"account_number '{data.account_number}' ya está registrada como bank-account.",
        )

    new_id = str(uuid4())
    meta = {
        "bank_account_id": new_id,
        "bank_account_type": data.account_type,
        "bank_account_currency": data.account_currency,
    }
    if data.bank_name is not None:
        meta["bank_name"] = data.bank_name

    root, refresh = _write_ctx(ledger)
    try:
        apply_to_accounts(
            lambda t: add_meta_to_open(t, data.account_number, meta),
            f"[bank-account] registra {data.account_number} ({data.account_type})",
            ledger_root=root, refresh_clone=refresh,
        )
    except PromoteError as exc:
        raise HTTPException(status_code=422, detail=f"bean-check falló: {exc.detail}")

    ledger.load()
    return _find_by_id(ledger, new_id)


def update_bank_account(account_id: str, data: BankAccountUpdate, ledger: LedgerService) -> BankAccount:
    """Edita una bank-account (AC3): `active=false` → `close`; `active=true` → reabrir;
    `bank_name` → edita la metadata del `open`."""
    patch = data.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update.")

    entries = ledger.entries()
    target = next(
        (e for e in _bank_opens(entries) if str((e.meta or {}).get("bank_account_id", "")) == account_id),
        None,
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bank account '{account_id}' not found.")

    def mutate(text: str) -> str:
        if patch.get("bank_name") is not None:
            text = set_open_meta(text, bank_account_id=account_id, key="bank_name", value=patch["bank_name"])
        if "active" in patch:
            if patch["active"] is False:
                text = append_close(text, target.account, date.today().isoformat())
            else:
                text = remove_close(text, target.account)
        return text

    root, refresh = _write_ctx(ledger)
    try:
        apply_to_accounts(
            mutate,
            f"[bank-account] actualiza {account_id} ({', '.join(patch)})",
            ledger_root=root, refresh_clone=refresh,
        )
    except PromoteError as exc:
        raise HTTPException(status_code=422, detail=f"bean-check falló: {exc.detail}")

    ledger.load()
    return _find_by_id(ledger, account_id)


def _find_by_id(ledger: LedgerService, account_id: str) -> BankAccount:
    for b in list_bank_accounts(ledger):
        if str(b.id) == account_id:
            return b
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="No se pudo releer la cuenta tras escribir.")
