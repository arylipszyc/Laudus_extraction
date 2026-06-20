"""Router de transactions — corrección de categorías (Story 9.7 AC7/AC8).

PATCH /api/v1/transactions/{tx_id}/category   — corrige + confirma una tx
POST  /api/v1/transactions/bulk-confirm        — confirma las sugeridas de un batch
RBAC: contador/admin. Beancount es la fuente única (cleanup c4, 9.16).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.app.api.v1.transactions.schemas import (
    BulkConfirmRequest,
    BulkConfirmResponse,
    PatchCategoryRequest,
    PatchCategoryResponse,
)
from backend.app.api.v1.transactions.service import (
    CategoryEditError,
    TxNotFound,
    bulk_confirm,
    update_category,
)
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import get_ledger_service, require_role
from backend.app.services.ledger_service import LedgerService, LedgerUnavailableError

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _entries(ledger: LedgerService):
    try:
        return ledger.entries()
    except LedgerUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"LEDGER_UNAVAILABLE: {exc.detail}")


@router.patch("/{tx_id}/category", response_model=PatchCategoryResponse)
def patch_category(
    tx_id: str,
    request: PatchCategoryRequest,
    user: UserSession = Depends(require_role(["contador", "admin"])),
    ledger: LedgerService = Depends(get_ledger_service),
):
    root = Path(ledger.main_path).parent
    try:
        result = update_category(tx_id, request.category_account,
                                 entries=_entries(ledger), ledger_root=root, user_email=user.email)
    except TxNotFound:
        raise HTTPException(status_code=404, detail=f"tx {tx_id} no encontrada")
    except CategoryEditError as exc:
        raise HTTPException(status_code=422, detail=f"bean-check falló: {exc}")
    ledger.load()
    return PatchCategoryResponse(**result)


@router.post("/bulk-confirm", response_model=BulkConfirmResponse)
def bulk_confirm_endpoint(
    request: BulkConfirmRequest = Body(default=BulkConfirmRequest()),
    user: UserSession = Depends(require_role(["contador", "admin"])),
    ledger: LedgerService = Depends(get_ledger_service),
):
    root = Path(ledger.main_path).parent
    try:
        result = bulk_confirm(request.batch_id, entries=_entries(ledger),
                              ledger_root=root, user_email=user.email)
    except CategoryEditError as exc:
        raise HTTPException(status_code=422, detail=f"bean-check falló: {exc}")
    ledger.load()
    return BulkConfirmResponse(**result)
