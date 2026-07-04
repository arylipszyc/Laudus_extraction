"""Router de la vista de cuadre TC — Story 6.6.

GET /api/v1/tc/reconciliation?card=<bank_account_id>[&year_month=YYYY-MM]
  → una fila por cartola importada de la tarjeta con los cinco chequeos C1–C5, números lado a lado
    (cartola vs. ledger vs. Laudus) y los movimientos para el detalle. READ-ONLY (no postea ni muta).
RBAC: contador/admin.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.v1.tc_reconciliation.schemas import TcReconciliationRow
from backend.app.api.v1.tc_reconciliation.service import build_rows
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import get_ledger_service, require_role
from backend.app.services.ledger_service import LedgerService
from pipeline.importers.bank_account_resolver import BankAccountResolver, UnknownBankAccount
from pipeline.importers.tc_correction import TcCorrectionBlocked, tc_real_account

router = APIRouter(prefix="/tc", tags=["tc-reconciliation"])


@router.get("/reconciliation", response_model=list[TcReconciliationRow])
def get_tc_reconciliation(
    card: str,
    year_month: str | None = None,
    _user: UserSession = Depends(require_role(["contador", "admin"])),
    ledger: LedgerService = Depends(get_ledger_service),
) -> list[TcReconciliationRow]:
    """Cuadre C1–C5 por mes de la tarjeta `card` (= `bank_account_id`)."""
    root = Path(ledger.main_path).parent
    resolver = BankAccountResolver(root / "accounts.beancount")
    try:
        expense_tc = resolver.resolve(card)          # cuenta-gasto Laudus (lump)
    except UnknownBankAccount:
        raise HTTPException(status_code=404, detail={
            "code": "UNKNOWN_CARD", "message": f"tarjeta '{card}' no está en accounts.beancount"})
    try:
        tc_real = tc_real_account(expense_tc)        # Liabilities:EAG:TC:Real:<stem>
    except TcCorrectionBlocked:
        raise HTTPException(status_code=400, detail={
            "code": "NOT_A_TC", "message": f"'{card}' no es una tarjeta de crédito (cuenta {expense_tc})"})

    rows = build_rows(ledger.entries(), tc_real_account=tc_real, lump_account=expense_tc,
                      bank_account_id=card, year_month=year_month)
    return [TcReconciliationRow(**r) for r in rows]
