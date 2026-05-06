"""API endpoints for bank_accounts registry."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.v1.bank_accounts.schemas import BankAccount, BankAccountCreate, BankAccountUpdate
from backend.app.api.v1.bank_accounts.service import (
    create_bank_account,
    list_bank_accounts,
    update_bank_account,
)
from backend.app.dependencies import get_current_user, require_role

router = APIRouter(tags=["bank-accounts"])


@router.get("/", response_model=list[BankAccount])
def get_bank_accounts(
    _user=Depends(get_current_user),
):
    """List all bank accounts (active and inactive) with linked account name."""
    try:
        return list_bank_accounts()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post("/", response_model=BankAccount, status_code=status.HTTP_201_CREATED)
def register_bank_account(
    data: BankAccountCreate,
    _user=Depends(require_role(["contador", "admin"])),
):
    """Register a new bank account. Requires: contador role.

    Returns 400 if account_number is not found in plan_de_cuentas.
    """
    return create_bank_account(data)


@router.patch("/{account_id}", response_model=BankAccount)
def patch_bank_account(
    account_id: UUID,
    data: BankAccountUpdate,
    _user=Depends(require_role(["contador", "admin"])),
):
    """Update a bank account (e.g. deactivate). Requires: contador role."""
    return update_bank_account(str(account_id), data)
