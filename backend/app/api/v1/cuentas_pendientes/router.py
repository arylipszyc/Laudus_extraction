"""Router de cuentas pendientes — Story 10.3.

GET  /cuentas-pendientes/                  → lista cuentas en cuarentena + sugerencia
POST /cuentas-pendientes/{code}/promover   → escribe el open final al plan (helper reusable)

Gated por RBAC contador/admin (Story 9.13). Beancount es la fuente única (cleanup c4, 9.16).
"""
from __future__ import annotations

import logging
from pathlib import Path
from subprocess import CalledProcessError

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.app.api.v1.cuentas_pendientes.schemas import (
    PendingAccount,
    PromoteRequest,
    PromoteResponse,
)
from backend.app.api.v1.cuentas_pendientes.service import list_pending, suggest_for_code, _real_opens
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import get_ledger_service, require_role
from backend.app.services.beancount_promote import PromoteError, is_valid_account, promote_account
from backend.app.services.ledger_service import LedgerService, LedgerUnavailableError
from pipeline.importers.laudus_run import LockTimeout

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cuentas-pendientes", tags=["cuentas-pendientes"])


@router.get("/", response_model=list[PendingAccount])
def get_pending(
    _user: UserSession = Depends(require_role(["contador", "admin"])),
    ledger: LedgerService = Depends(get_ledger_service),
) -> list[PendingAccount]:
    """Lista las cuentas que el importer dejó en cuarentena, con monto + sugerencia."""
    try:
        entries = ledger.entries()
    except LedgerUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"LEDGER_UNAVAILABLE: {exc.detail}")
    return list_pending(entries)


@router.post("/{code}/promover", response_model=PromoteResponse)
def promover(
    code: str,
    request: PromoteRequest = Body(...),
    _user: UserSession = Depends(require_role(["contador", "admin"])),
    ledger: LedgerService = Depends(get_ledger_service),
) -> PromoteResponse:
    """Escribe el `open` final + metadata al plan (lock + bean-check + git), refresca el ledger."""
    if not request.categoria3 or not request.categoria3.strip():
        raise HTTPException(
            status_code=422,
            detail="categoria3 es obligatoria (el rubro fino requiere criterio humano)",
        )
    try:
        entries = ledger.entries()
    except LedgerUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"LEDGER_UNAVAILABLE: {exc.detail}")

    pending = {pa.code: pa for pa in list_pending(entries)}
    if code not in pending:
        raise HTTPException(status_code=404, detail=f"La cuenta {code} no está en cuarentena")

    # Cuenta destino: el override del body o la sugerida server-side desde las hermanas.
    account = request.account.strip()
    if not account:
        account = suggest_for_code(code, _real_opens(entries), request.laudus_account_name).account
    if not account:
        raise HTTPException(
            status_code=422,
            detail="No se pudo sugerir una cuenta Beancount (sin hermanas por prefijo); especificá 'account'",
        )
    if not is_valid_account(account):
        raise HTTPException(status_code=422, detail=f"Cuenta Beancount inválida: {account}")

    ledger_root = Path(ledger.main_path).parent
    from backend.app.api.v1.sync.service import _refresh_ledger_clone
    try:
        sha = promote_account(
            code=code,
            account=account,
            laudus_account_name=request.laudus_account_name or pending[code].laudus_account_name or "",
            categoria1=request.categoria1.strip(),
            categoria2=request.categoria2.strip(),
            categoria3=request.categoria3.strip(),
            ledger_root=ledger_root,
            refresh_clone=_refresh_ledger_clone,
        )
    except PromoteError as exc:
        raise HTTPException(status_code=422, detail=f"bean-check falló: {exc.detail}")
    except LockTimeout as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except CalledProcessError as exc:
        # bean-check pasó y la escritura local persiste; sólo falló el push de git. Degradar con
        # gracia (mismo patrón que el importer): reportar el fallo, no enmascararlo, no rollback.
        logger.error("promote: push de git falló para %s (escritura local persiste): %s", code, exc)
        ledger.load()
        return PromoteResponse(
            code=code,
            account=account,
            git_commit_sha=None,
            backfill_recommended=True,
            message=(
                f"Cuenta {code} categorizada localmente, PERO el push a git falló. El cambio NO "
                "está respaldado en el repo del ledger todavía — reintentá o avisá al admin antes "
                "de correr el backfill."
            ),
        )

    ledger.load()  # el reporte en proceso ve la cuenta nueva sin esperar redeploy (AC6)
    return PromoteResponse(
        code=code,
        account=account,
        git_commit_sha=sha,
        backfill_recommended=True,
        message=(
            "Cuenta promovida. Las JEs históricas siguen apuntando a la cuenta de cuarentena "
            "hasta correr un backfill (POST /sync/trigger mode=backfill); las JEs nuevas ya "
            "resolverán a la cuenta real."
        ),
    )
