"""Cartolas API router — Story 9.5.

POST /api/v1/cartolas/upload   — multipart PDF + bank_account_id
GET  /api/v1/cartolas/{batch_id} — async status polling
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import JSONResponse

from backend.app.api.v1.cartolas.schemas import (
    StatusResponse,
    TcCorrectionResponse,
    UploadAcceptedResponse,
    ValidateBalanceRequest,
    ValidateBalanceResponse,
)
from backend.app.api.v1.cartolas.service import (
    BalanceDiscrepancy,
    BeanCheckFailed,
    CartolaValidationError,
    MAX_PDF_SIZE_BYTES,
    OverrideJustificationTooShort,
    StagingNotFound,
    get_job_store,
    new_batch_id,
    run_job,
    validate_balance,
    validate_upload_inputs,
)
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import get_ledger_service, require_role
from backend.app.integrations.bank_account_index import (
    BankAccountIndex,
    get_bank_account_index,
)
from backend.app.integrations.gemini_client import GeminiClient
from backend.app.services.ledger_service import LedgerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cartolas", tags=["cartolas"])


# ── Dependency factories (override-able in tests) ────────────────────────


def get_gemini_client() -> GeminiClient:
    """Lazily instantiated. Tests override via app.dependency_overrides."""
    return GeminiClient()


# ── POST /upload ──────────────────────────────────────────────────────────


@router.post("/upload", status_code=202)
async def upload_cartola(
    background_tasks: BackgroundTasks,
    pdf_file: Annotated[UploadFile, File(description="Cartola PDF (≤ 20MB)")],
    bank_account_id: Annotated[str, Form(...)],
    user: UserSession = Depends(require_role(["contador", "admin"])),
    index: BankAccountIndex = Depends(get_bank_account_index),
    gemini: GeminiClient = Depends(get_gemini_client),
):
    """Accept a cartola PDF, validate inputs, kick off async extraction.

    Returns immediately with `{status: "processing", batch_id: ...}`. The
    frontend polls `GET /api/v1/cartolas/{batch_id}` until status flips to
    `ready` or `failed`.
    """
    pdf_bytes = await pdf_file.read()

    try:
        entry = validate_upload_inputs(
            pdf_bytes=pdf_bytes,
            content_type=pdf_file.content_type,
            bank_account_id=bank_account_id,
            index=index,
        )
    except CartolaValidationError as exc:
        # Use JSONResponse directly so we control the error envelope (the global
        # HTTPException handler would coerce the code to HTTP_400).
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "detail": None,
                }
            },
        )

    batch_id = new_batch_id()
    get_job_store().create(batch_id)

    logger.info(
        "cartola_upload: batch_id=%s bank_account_id=%s size=%d user=%s",
        batch_id, bank_account_id, len(pdf_bytes), user.email,
    )

    # Async — bytes are passed by reference, the file handle is closed by FastAPI.
    background_tasks.add_task(
        run_job,
        batch_id=batch_id,
        pdf_bytes=pdf_bytes,
        bank_account_entry=entry,
        gemini=gemini,
    )

    return UploadAcceptedResponse(status="processing", batch_id=batch_id).model_dump()


# ── GET /{batch_id} ───────────────────────────────────────────────────────


@router.get(
    "/{batch_id}",
    response_model=StatusResponse,
)
def get_cartola_status(
    batch_id: str,
    _user: UserSession = Depends(require_role(["contador", "admin"])),
) -> StatusResponse:
    job = get_job_store().get(batch_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"batch_id {batch_id} not found or expired"},
        )
    return StatusResponse(
        batch_id=batch_id,
        status=job["status"],
        canonical=job["canonical"],
        error=job["error"],
    )


@router.patch("/{batch_id}/validate-balance",
              response_model=ValidateBalanceResponse | TcCorrectionResponse)
def validate_balance_endpoint(
    batch_id: str,
    request: ValidateBalanceRequest,
    user: UserSession = Depends(require_role(["contador", "admin"])),
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Promueve el staging a archivo final con validación de balance (Story 9.9).

    OK → 200 validated. Discrepancia sin override → 400 VALIDATION_FAILED con el diff.
    Con `override_justification` → re-promote con pad+balance (la pad absorbe).
    """
    try:
        result = validate_balance(
            batch_id, request.opening, request.closing, request.override_justification,
            user_email=user.email,
        )
    except StagingNotFound:
        raise HTTPException(status_code=404, detail={
            "code": "NOT_FOUND", "message": f"staging {batch_id} no existe o expiró"})
    except OverrideJustificationTooShort as exc:
        return JSONResponse(status_code=400, content={"error": {
            "code": "JUSTIFICATION_TOO_SHORT",
            "message": f"La justificación del override debe tener al menos {exc.min_chars} caracteres",
        }})
    except BalanceDiscrepancy as exc:
        return JSONResponse(status_code=400, content={"error": {
            "code": "VALIDATION_FAILED",
            "message": "Discrepancia detectada — provea override_justification para confirmar",
            "diff": exc.diff, "calculated": exc.calculated, "stated": exc.stated,
        }})
    except BeanCheckFailed as exc:
        return JSONResponse(status_code=422, content={"error": {
            "code": "BEAN_CHECK_FAILED",
            "message": "La validación contable falló por un motivo distinto al balance enviado",
            "detail": str(exc),
        }})
    # La TC POSTEA (status corrected/blocked, otra forma) vs el modelo A reconcilia (status reconciled).
    if result.get("status") in ("corrected", "blocked"):
        # `corrected` escribió el desglose al ledger; refrescamos el ledger en memoria para que la
        # cola de categorización lo vea sin depender del file-watcher (poco fiable en el contenedor).
        if result.get("status") == "corrected":
            ledger.load()
        return TcCorrectionResponse(**result).model_dump()
    return ValidateBalanceResponse(**result).model_dump()


# Re-export for tests/runtime introspection.
__all__ = ["router", "get_gemini_client", "MAX_PDF_SIZE_BYTES"]
