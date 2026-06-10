"""Reportes router — GET /reportes/gastos (xlsx para contadores).

Reusa el repositorio (Sheets) y la RBAC existentes. La data se sincroniza con el
endpoint ya existente POST /sync/trigger (rol contador/admin); este endpoint solo
LEE lo que ya está en Sheets y arma el xlsx.
"""
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.app.api.v1.reportes.report_builder import build_report
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import get_repository, require_role
from backend.app.repositories.base import DataRepository

router = APIRouter(prefix="/reportes", tags=["reportes"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/gastos")
def reporte_gastos(
    start: date = Query(..., description="Fecha desde (YYYY-MM-DD)"),
    end: date = Query(..., description="Fecha hasta (YYYY-MM-DD)"),
    user: UserSession = Depends(require_role(["contador", "admin"])),
    repo: DataRepository = Depends(get_repository),
) -> StreamingResponse:
    """Genera el reporte de gastos (xlsx) desde Laudus para el rango dado."""
    if start > end:
        raise HTTPException(status_code=422, detail="start debe ser <= end")
    data = build_report(start, end, repo.get_records)
    fname = f"reporte_gastos_{start.isoformat()}_{end.isoformat()}.xlsx"
    return StreamingResponse(
        io.BytesIO(data),
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
