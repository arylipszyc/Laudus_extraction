"""Business logic for bank_accounts CRUD."""
import logging

from fastapi import HTTPException, status

from backend.app.api.v1.bank_accounts.schemas import BankAccount, BankAccountCreate, BankAccountUpdate
from backend.app.repositories.supabase_repository import SupabaseRepository

logger = logging.getLogger(__name__)


def list_bank_accounts() -> list[BankAccount]:
    """Return all bank accounts with linked account name."""
    repo = SupabaseRepository()
    rows = repo.list_bank_accounts()
    return [BankAccount.from_supabase(row) for row in rows]


def create_bank_account(data: BankAccountCreate) -> BankAccount:
    """Create a new bank account.

    Validates that account_number exists in plan_de_cuentas.

    Raises:
        HTTPException 400: If account_number not found in plan_de_cuentas.
    """
    repo = SupabaseRepository()

    if not repo.plan_de_cuentas_exists(data.account_number):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"account_number '{data.account_number}' does not exist in plan_de_cuentas. "
                   "Run POST /api/v1/plan-de-cuentas/sync first.",
        )

    row = repo.create_bank_account(data.model_dump())
    # Fetch full record with join for response
    created = repo.get_bank_account_by_id(str(row["id"]))
    if not created:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve created record.")
    return BankAccount.from_supabase(created)


def update_bank_account(account_id: str, data: BankAccountUpdate) -> BankAccount:
    """Update an existing bank account.

    Raises:
        HTTPException 400: If no valid fields to update.
        HTTPException 404: If account not found.
    """
    patch = data.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update.")
    repo = SupabaseRepository()

    updated = repo.update_bank_account(account_id, patch)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bank account '{account_id}' not found.")

    full = repo.get_bank_account_by_id(account_id)
    if not full:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve updated record.")
    return BankAccount.from_supabase(full)
