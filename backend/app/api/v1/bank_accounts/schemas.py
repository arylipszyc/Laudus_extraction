"""Pydantic schemas for bank_accounts endpoints."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

AccountType = Literal["tarjeta_credito", "cta_corriente", "linea_credito", "cta_inversiones"]
AccountCurrency = Literal["CLP", "USD"]


class BankAccountCreate(BaseModel):
    account_number: str
    account_type: AccountType
    account_currency: AccountCurrency
    bank_name: str | None = None


class BankAccountUpdate(BaseModel):
    active: bool | None = None
    bank_name: str | None = None


class BankAccount(BaseModel):
    id: UUID
    account_number: str
    account_type: str
    account_currency: str
    bank_name: str | None
    active: bool
    # Nombre legible de la cuenta (desde la metadata del `open` en accounts.beancount)
    account_name: str | None = None

    @classmethod
    def from_ledger_open(cls, account_name: str, meta: dict, active: bool) -> "BankAccount":
        """Construye desde la metadata de un `open` de accounts.beancount (modelo unificado 9.1).

        `account_name` = nombre completo de la cuenta Beancount (no se expone). Story 9.14 AC1.
        """
        return cls(
            id=str(meta["bank_account_id"]),
            account_number=str(meta.get("code", "")),
            account_type=str(meta.get("bank_account_type", "")),
            account_currency=str(meta.get("bank_account_currency", "")),
            bank_name=str(meta["bank_name"]) if meta.get("bank_name") is not None else None,
            active=active,
            account_name=str(meta["laudus_account_name"]) if meta.get("laudus_account_name") else None,
        )
