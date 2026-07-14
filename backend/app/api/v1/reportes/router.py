"""Reportes router — GET /reportes/gastos (xlsx para contadores).

Lee las filas del ledger Beancount vía BQL (fuente canónica tras 9.11) y arma el xlsx.
Story 9.16 (cleanup c4): se removió el path Sheets (`ledger_final`), que el importer
Beancount ya no reconstruye.
"""
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.app.api.v1.reportes.report_builder import build_report
from backend.app.api.v1.reportes.report_builder_rut2 import build_report_rut2
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import get_ledger_service, require_role
from backend.app.services.ledger_service import LedgerService

router = APIRouter(prefix="/reportes", tags=["reportes"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/gastos")
def reporte_gastos(
    start: date = Query(..., description="Fecha desde (YYYY-MM-DD)"),
    end: date = Query(..., description="Fecha hasta (YYYY-MM-DD)"),
    user: UserSession = Depends(require_role(["contador", "admin"])),
    ledger: LedgerService = Depends(get_ledger_service),
) -> StreamingResponse:
    """Genera el reporte de gastos (xlsx) para el rango dado, leyendo del ledger Beancount."""
    if start > end:
        raise HTTPException(status_code=422, detail="start debe ser <= end")
    from backend.app.services.bql_queries import report_rows_via_beancount
    rows = report_rows_via_beancount(ledger, start.isoformat(), end.isoformat())
    get_records = lambda _name: rows  # noqa: E731 — build_report solo pide "ledger_final"
    data = build_report(start, end, get_records)
    fname = f"reporte_gastos_{start.isoformat()}_{end.isoformat()}.xlsx"
    return StreamingResponse(
        io.BytesIO(data),
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/fondo-comun")
def reporte_fondo_comun(
    start: date = Query(..., description="Fecha desde (YYYY-MM-DD)"),
    end: date = Query(..., description="Fecha hasta (YYYY-MM-DD)"),
    user: UserSession = Depends(require_role(["contador", "admin"])),
    ledger: LedgerService = Depends(get_ledger_service),
) -> StreamingResponse:
    """Reporte del Fondo Común (RUT2 · FFCC/JAB): gastos por encabezado +
    distribuciones (cuenta corriente de socios). Story 13.1. Read-only."""
    if start > end:
        raise HTTPException(status_code=422, detail="start debe ser <= end")
    from backend.app.services.bql_queries import (
        distribution_rows_via_beancount,
        report_rows_via_beancount,
    )
    rows = report_rows_via_beancount(ledger, start.isoformat(), end.isoformat(),
                                     group="FondoComun")
    dist = distribution_rows_via_beancount(ledger, start.isoformat(), end.isoformat(),
                                           group="FondoComun")
    data = build_report_rut2(start, end, rows, dist)
    fname = f"reporte_fondo_comun_{start.isoformat()}_{end.isoformat()}.xlsx"
    return StreamingResponse(
        io.BytesIO(data),
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
