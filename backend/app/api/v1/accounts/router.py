"""Router del plan de cuentas — Story 6.4.

GET /accounts?root=Expenses → lista de cuentas para el autocompletado de categoría.
RBAC: contador/admin (igual que reconciliación/cuentas-pendientes).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.v1.accounts.service import list_accounts
from backend.app.auth.basic import require_auth
from backend.app.dependencies import get_ledger_service
from backend.app.services.ledger_service import LedgerService, LedgerUnavailableError

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/")
def get_accounts(
    root: str = "Expenses",
    _user=Depends(require_auth),
    ledger: LedgerService = Depends(get_ledger_service),
) -> dict:
    """Lista las cuentas del plan que empiezan con `root` (default `Expenses`)."""
    try:
        entries = ledger.entries()
    except LedgerUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"LEDGER_UNAVAILABLE: {exc.detail}")
    return {"accounts": list_accounts(entries, root)}
