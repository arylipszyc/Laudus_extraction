"""FastAPI application entry point."""
import uvicorn
from fastapi import FastAPI

from backend.app.api.v1.router import router as v1_router
from backend.app.middleware import add_middleware

app = FastAPI(
    title="EAG Family Office API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Register middleware and exception handlers
add_middleware(app)

# Mount v1 router
app.include_router(v1_router, prefix="/api/v1")


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
