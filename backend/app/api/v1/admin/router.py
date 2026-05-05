"""Admin endpoints — Story 9.10 (fx-bcch refetch).

RBAC: rol `owner` requerido. En el sistema actual `owner` es el dueño (Ary);
no existe un rol `admin` separado, así que `owner` cumple la semántica
"admin only" del story file.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.api.v1.admin.schemas import FxBcchRefetchResponse
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import require_role
from pipeline.importers.fx_bcch_eom import (
    NoPublicationFoundError,
    RefetchValidationError,
    refetch_eom,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/fx-bcch/refetch", response_model=FxBcchRefetchResponse)
def fx_bcch_refetch(
    year_month: str = Query(..., description="Mes ya cerrado, formato YYYY-MM"),
    user: UserSession = Depends(require_role(["owner"])),
) -> FxBcchRefetchResponse:
    try:
        result = refetch_eom(year_month)
    except RefetchValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except NoPublicationFoundError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return FxBcchRefetchResponse(**result.to_dict())
