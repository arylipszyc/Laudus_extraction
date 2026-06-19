"""Request/response schemas for the cartolas API — Story 9.5 + 9.9."""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from backend.app.integrations.cartola_schema import CartolaCanonicalV1


class ValidateBalanceRequest(BaseModel):
    """PATCH /api/v1/cartolas/{batch_id}/validate-balance — Story 9.9."""
    opening: Decimal
    closing: Decimal
    override_justification: str | None = None


class ValidateBalanceResponse(BaseModel):
    status: Literal["validated"]
    file: str
    git_sha: str | None = None
    override: bool = False


class UploadAcceptedResponse(BaseModel):
    """202 response from POST /api/v1/cartolas/upload — async pattern."""
    status: Literal["processing"] = "processing"
    batch_id: str


class StatusResponse(BaseModel):
    """GET /api/v1/cartolas/{batch_id}."""
    batch_id: str
    status: Literal["processing", "ready", "failed"]
    canonical: CartolaCanonicalV1 | None = None
    error: dict | None = None
