"""Aggregates all v1 API routers.

Base limpia (reset): solo la plomería que sirve el espejo de Laudus. La reportería
y la ingesta de cartolas/TC se reconstruyen encima como capas nuevas.
"""
from fastapi import APIRouter

from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.sync.router import router as sync_router
from backend.app.api.v1.accounts.router import router as accounts_router
from backend.app.api.v1.bank_accounts.router import router as bank_accounts_router

router = APIRouter()
router.include_router(health_router)
router.include_router(sync_router)
router.include_router(accounts_router)
router.include_router(bank_accounts_router, prefix="/bank-accounts")
