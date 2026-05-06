"""Aggregates all v1 API routers."""
from fastapi import APIRouter

from backend.app.api.v1.admin.router import router as admin_router
from backend.app.api.v1.cartolas.router import router as cartolas_router
from backend.app.api.v1.dashboard.router import router as dashboard_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.sync.router import router as sync_router
from backend.app.auth.router import router as auth_router
from backend.app.api.v1.plan_de_cuentas.router import router as plan_de_cuentas_router
from backend.app.api.v1.bank_accounts.router import router as bank_accounts_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(sync_router)
router.include_router(dashboard_router)
router.include_router(plan_de_cuentas_router, prefix="/plan-de-cuentas")
router.include_router(bank_accounts_router, prefix="/bank-accounts")
router.include_router(cartolas_router)
router.include_router(admin_router)
