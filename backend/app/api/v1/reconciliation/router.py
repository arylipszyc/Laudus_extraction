"""Router de reconciliación — Story 9.12 (lee cartola-discrepancies.jsonl, sin SQL).

GET  /api/v1/reconciliation/discrepancies          — lista filtrable + summary (AC1)
GET  /api/v1/reconciliation/history/{id}           — audit trail de una discrepancia (AC2)
GET  /api/v1/reconciliation/count                  — {total, blocking} para el chip (AC9)
GET  /api/v1/reconciliation/periods                — estado por (cuenta, mes) (Story 6.5 AC3)
POST /api/v1/reconciliation/discrepancies/{id}/resolve — resuelve/escala (AC3/AC4)
RBAC: contador/admin (family no accede).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.v1.reconciliation.models import (
    CountResponse,
    PeriodStatus,
    ResolveRequest,
    ResolveResponse,
)
from backend.app.api.v1.reconciliation.service import (
    AnnotationFailed,
    ResolveError,
    history,
    list_periods,
    pending_count,
    read_discrepancies,
    resolve,
)
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import require_role

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


@router.get("/discrepancies")
def get_discrepancies(
    state: str | None = None,
    year_month: str | None = None,
    bank_account_id: str | None = None,
    discrepancy_id: str | None = None,
    _user: UserSession = Depends(require_role(["contador", "admin"])),
) -> dict:
    return read_discrepancies(state=state, year_month=year_month,
                              bank_account_id=bank_account_id, discrepancy_id=discrepancy_id)


@router.get("/history/{discrepancy_id}")
def get_history(
    discrepancy_id: str,
    _user: UserSession = Depends(require_role(["contador", "admin"])),
) -> dict:
    return {"discrepancy_id": discrepancy_id, "entries": history(discrepancy_id)}


@router.get("/count", response_model=CountResponse)
def get_count(
    _user: UserSession = Depends(require_role(["contador", "admin"])),
) -> CountResponse:
    return CountResponse(**pending_count())


@router.get("/periods", response_model=list[PeriodStatus])
def get_periods(
    _user: UserSession = Depends(require_role(["contador", "admin"])),
) -> list[PeriodStatus]:
    return [PeriodStatus(**p) for p in list_periods()]


@router.post("/discrepancies/{discrepancy_id}/resolve", response_model=ResolveResponse)
def resolve_discrepancy(
    discrepancy_id: str,
    request: ResolveRequest,
    user: UserSession = Depends(require_role(["contador", "admin"])),
) -> ResolveResponse:
    try:
        result = resolve(discrepancy_id, request.action, request.justification,
                         user_email=user.email, now_iso=datetime.now(timezone.utc).isoformat(),
                         category_account=request.category_account)
    except ResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except AnnotationFailed as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return ResolveResponse(**result)
