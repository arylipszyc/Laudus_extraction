"""Sync API router — GET /sync/status, POST /sync/trigger."""
from datetime import date
from fastapi import APIRouter, Body, Depends, HTTPException

from backend.app.api.v1.sync.schemas import (
    DataTypeSyncStatus,
    SyncRunStats,
    SyncStatusResponse,
    TriggerRequest,
    TriggerResponse,
)
from backend.app.api.v1.sync.service import get_sync_status, trigger_sync
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import get_current_user, get_repository, require_role
from backend.app.repositories.base import DataRepository

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/status", response_model=SyncStatusResponse)
def sync_status(
    user: UserSession = Depends(get_current_user),
    repo: DataRepository = Depends(get_repository),
) -> SyncStatusResponse:
    """Return last sync timestamp per data type and current job status."""
    state = get_sync_status(repo)
    raw_stats = state["stats"]
    return SyncStatusResponse(
        balance_sheet=DataTypeSyncStatus(last_sync=state["balance_sheet"]["last_sync"]),
        ledger=DataTypeSyncStatus(last_sync=state["ledger"]["last_sync"]),
        job_status=state["job_status"],
        job_id=state["job_id"],
        error=state["error"],
        stats=SyncRunStats(**raw_stats) if raw_stats else None,
    )


@router.post("/trigger", response_model=TriggerResponse, status_code=202)
def sync_trigger(
    request: TriggerRequest = Body(default=TriggerRequest()),
    user: UserSession = Depends(require_role(["contador"])),
    repo: DataRepository = Depends(get_repository),
) -> TriggerResponse:
    """Trigger async sync (normal) or backfill. Returns job_id immediately."""
    if request.mode == "backfill":
        if not request.from_date:
            raise HTTPException(status_code=422, detail="from_date is required when mode='backfill'")
        try:
            date.fromisoformat(request.from_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="from_date must be a valid ISO date YYYY-MM-DD")
    try:
        job_id = trigger_sync(repo, mode=request.mode, from_date=request.from_date)
    except ValueError:
        raise HTTPException(status_code=409, detail="Sync already running")
    return TriggerResponse(status="triggered", job_id=job_id)
