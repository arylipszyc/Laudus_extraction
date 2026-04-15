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
    # Joined from plan_de_cuentas
    account_name: str | None = None

    @classmethod
    def from_supabase(cls, data: dict) -> "BankAccount":
        """Construct from a Supabase row that includes a plan_de_cuentas join."""
        plan = data.get("plan_de_cuentas") or {}
        return cls(
            id=data["id"],
            account_number=data["account_number"],
            account_type=data["account_type"],
            account_currency=data["account_currency"],
            bank_name=data.get("bank_name"),
            active=data["active"],
            account_name=plan.get("account_name") if isinstance(plan, dict) else None,
        )
