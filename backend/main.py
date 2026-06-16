"""FastAPI application entry point."""
import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from backend.app.api.v1.router import router as v1_router
from backend.app.middleware import add_middleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the ledger file watcher in the background (Story 9.2 AC1).

    Best-effort: a failure to start the watcher never blocks app startup.
    """
    from backend.app.dependencies import get_ledger_service

    watcher_task = None
    try:
        watcher_task = asyncio.create_task(get_ledger_service().watch_and_reload())
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Ledger watcher failed to start: %s", exc)
    try:
        yield
    finally:
        if watcher_task is not None:
            watcher_task.cancel()


app = FastAPI(
    title="EAG Family Office API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Register middleware and exception handlers
add_middleware(app)

# Mount v1 router
app.include_router(v1_router, prefix="/api/v1")


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
