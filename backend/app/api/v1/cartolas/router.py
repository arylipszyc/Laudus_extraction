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
    UploadAcceptedResponse,
)
from backend.app.api.v1.cartolas.service import (
    CartolaValidationError,
    MAX_PDF_SIZE_BYTES,
    get_job_store,
    new_batch_id,
    run_job,
    validate_upload_inputs,
)
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import require_role
from backend.app.integrations.bank_account_index import (
    BankAccountIndex,
    get_bank_account_index,
)
from backend.app.integrations.gemini_client import GeminiClient

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


# Re-export for tests/runtime introspection.
__all__ = ["router", "get_gemini_client", "MAX_PDF_SIZE_BYTES"]
