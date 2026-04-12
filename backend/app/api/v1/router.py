"""Aggregates all v1 API routers."""
from fastapi import APIRouter

from backend.app.api.v1.dashboard.router import router as dashboard_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.sync.router import router as sync_router
from backend.app.auth.router import router as auth_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(sync_router)
router.include_router(dashboard_router)
