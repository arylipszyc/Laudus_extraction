"""Router de categorización — panel de revisión (Story 9.7 AC9).

GET /api/v1/categorization/pending — tx con category_status ∈ (suggested, pending).
RBAC: contador/admin. Gated por USE_BEANCOUNT_ENGINE_LEDGER.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.v1.transactions.schemas import PendingTx
from backend.app.api.v1.transactions.service import list_pending
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import get_ledger_service, require_role
from backend.app.services.ledger_service import LedgerService, LedgerUnavailableError

router = APIRouter(prefix="/categorization", tags=["categorization"])


def _use_beancount() -> bool:
    return os.getenv("USE_BEANCOUNT_ENGINE_LEDGER", "false").strip().lower() in {"1", "true", "yes", "on"}


@router.get("/pending", response_model=list[PendingTx])
def get_pending(
    _user: UserSession = Depends(require_role(["contador", "admin"])),
    ledger: LedgerService = Depends(get_ledger_service),
):
    if not _use_beancount():
        return []
    try:
        entries = ledger.entries()
    except LedgerUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"LEDGER_UNAVAILABLE: {exc.detail}")
    return list_pending(entries)
