"""Reportes router — GET /reportes/gastos (xlsx para contadores).

Reusa el repositorio (Sheets) y la RBAC existentes. La data se sincroniza con el
endpoint ya existente POST /sync/trigger (rol contador/admin); este endpoint solo
LEE lo que ya está en Sheets y arma el xlsx.
"""
import io
import os
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.app.api.v1.reportes.report_builder import build_report
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import get_ledger_service, get_repository, require_role
from backend.app.repositories.base import DataRepository
from backend.app.services.ledger_service import LedgerService

router = APIRouter(prefix="/reportes", tags=["reportes"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _use_beancount() -> bool:
    return os.getenv("USE_BEANCOUNT_ENGINE_LEDGER", "false").strip().lower() in {"1", "true", "yes", "on"}


@router.get("/gastos")
def reporte_gastos(
    start: date = Query(..., description="Fecha desde (YYYY-MM-DD)"),
    end: date = Query(..., description="Fecha hasta (YYYY-MM-DD)"),
    user: UserSession = Depends(require_role(["contador", "admin"])),
    repo: DataRepository = Depends(get_repository),
    ledger: LedgerService | None = Depends(get_ledger_service),
) -> StreamingResponse:
    """Genera el reporte de gastos (xlsx) para el rango dado.

    Con `USE_BEANCOUNT_ENGINE_LEDGER` on (y el ledger cargado) las filas se leen del
    ledger Beancount vía BQL — fuente canónica tras 9.11 — en vez de la pestaña
    `ledger_final` de Sheets, que el importer Beancount ya no reconstruye (#4).
    """
    if start > end:
        raise HTTPException(status_code=422, detail="start debe ser <= end")
    if ledger is not None and _use_beancount():
        from backend.app.services.bql_queries import report_rows_via_beancount
        rows = report_rows_via_beancount(ledger, start.isoformat(), end.isoformat())
        get_records = lambda _name: rows  # noqa: E731 — build_report solo pide "ledger_final"
    else:
        get_records = repo.get_records
    data = build_report(start, end, get_records)
    fname = f"reporte_gastos_{start.isoformat()}_{end.isoformat()}.xlsx"
    return StreamingResponse(
        io.BytesIO(data),
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
