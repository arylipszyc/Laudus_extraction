"""Aggregates all v1 API routers."""
from fastapi import APIRouter

from backend.app.api.v1.admin.router import router as admin_router
from backend.app.api.v1.cartolas.router import router as cartolas_router
from backend.app.api.v1.dashboard.router import router as dashboard_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.reportes.router import router as reportes_router
from backend.app.api.v1.sync.router import router as sync_router
from backend.app.auth.router import router as auth_router
from backend.app.api.v1.bank_accounts.router import router as bank_accounts_router
from backend.app.api.v1.cuentas_pendientes.router import router as cuentas_pendientes_router
from backend.app.api.v1.transactions.router import router as transactions_router
from backend.app.api.v1.categorization.router import router as categorization_router
from backend.app.api.v1.reconciliation.router import router as reconciliation_router
from backend.app.api.v1.tc_reconciliation.router import router as tc_reconciliation_router
from backend.app.api.v1.accounts.router import router as accounts_router
from backend.app.api.v1.owner_comments.router import router as owner_comments_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(sync_router)
router.include_router(dashboard_router)
router.include_router(bank_accounts_router, prefix="/bank-accounts")
router.include_router(cuentas_pendientes_router)
router.include_router(transactions_router)
router.include_router(categorization_router)
router.include_router(reconciliation_router)
router.include_router(tc_reconciliation_router)
router.include_router(accounts_router)
router.include_router(cartolas_router)
router.include_router(reportes_router)
router.include_router(owner_comments_router)
router.include_router(admin_router)
