"""API endpoints for plan_de_cuentas (chart of accounts)."""
from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.v1.plan_de_cuentas.schemas import PlanDeCuentasEntry, SyncResponse
from backend.app.api.v1.plan_de_cuentas.service import sync_plan_de_cuentas, list_plan_de_cuentas
from backend.app.dependencies import get_current_user, require_role

router = APIRouter(tags=["plan-de-cuentas"])


@router.post("/sync", response_model=SyncResponse, status_code=status.HTTP_200_OK)
def sync_chart_of_accounts(
    _user=Depends(require_role(["contador", "admin"])),
):
    """Sync plan de cuentas from Google Sheets to Supabase.

    Requires: contador role.
    """
    try:
        result = sync_plan_de_cuentas()
        return SyncResponse(**result)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/", response_model=list[PlanDeCuentasEntry])
def get_chart_of_accounts(
    _user=Depends(get_current_user),
):
    """List all active accounts from plan_de_cuentas, ordered by account_number."""
    try:
        return list_plan_de_cuentas(active_only=True)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
