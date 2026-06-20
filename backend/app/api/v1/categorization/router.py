"""Router de categorización — panel de revisión (Story 9.7 AC9).

GET /api/v1/categorization/pending — tx con category_status ∈ (suggested, pending).
RBAC: contador/admin. Beancount es la fuente única (cleanup c4, 9.16).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.v1.transactions.schemas import PendingTx
from backend.app.api.v1.transactions.service import list_pending
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import get_ledger_service, require_role
from backend.app.services.ledger_service import LedgerService, LedgerUnavailableError

router = APIRouter(prefix="/categorization", tags=["categorization"])


@router.get("/pending", response_model=list[PendingTx])
def get_pending(
    _user: UserSession = Depends(require_role(["contador", "admin"])),
    ledger: LedgerService = Depends(get_ledger_service),
):
    try:
        entries = ledger.entries()
    except LedgerUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"LEDGER_UNAVAILABLE: {exc.detail}")
    return list_pending(entries)
