"""Router de owner-comments — Story 7.1 (FR36).

POST /api/v1/comments  — el owner (rol `family`) crea un comentario raíz sobre una transacción.
RBAC: family/contador/admin. **Primer endpoint de ESCRITURA que admite `family`** (ver ADR 7.0).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.v1.owner_comments.schemas import (
    CreateCommentRequest,
    CreateCommentResponse,
)
from backend.app.api.v1.owner_comments.service import create_comment
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import get_ledger_service, require_role
from backend.app.services.ledger_service import LedgerService, LedgerUnavailableError
from pipeline.importers.owner_comments_writer import AnchorNotFound

router = APIRouter(prefix="/comments", tags=["owner-comments"])


def _entries(ledger: LedgerService):
    try:
        return ledger.entries()
    except LedgerUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"LEDGER_UNAVAILABLE: {exc.detail}")


@router.post("", response_model=CreateCommentResponse, status_code=201)
def create_comment_endpoint(
    request: CreateCommentRequest,
    user: UserSession = Depends(require_role(["family", "contador", "admin"])),
    ledger: LedgerService = Depends(get_ledger_service),
):
    root = Path(ledger.main_path).parent
    try:
        result = create_comment(
            request.tx_id, request.body,
            user_email=user.email, user_role=user.role,
            entries=_entries(ledger), ledger_root=root,
        )
    except AnchorNotFound:
        raise HTTPException(status_code=404, detail=f"tx {request.tx_id} no encontrada")
    return CreateCommentResponse(**result)
