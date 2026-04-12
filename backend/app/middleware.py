"""Global error handler and CORS middleware."""
import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from backend.app.audit.service import log_write_operation

logger = logging.getLogger(__name__)

_WRITE_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})


def _extract_email_from_request(request: Request) -> str | None:
    """Extract user email from JWT cookie — best-effort, never raises."""
    try:
        from backend.app.auth.service import decode_jwt
        token = request.cookies.get("access_token")
        if token:
            payload = decode_jwt(token)
            return payload.get("sub")
    except Exception:
        pass
    return None


def add_middleware(app: FastAPI) -> None:
    """Register all middleware and exception handlers on the FastAPI app."""

    # ── Audit (write operations only) ─────────────────────────────────────────
    @app.middleware("http")
    async def audit_middleware(request: Request, call_next):
        response = await call_next(request)
        if request.method in _WRITE_METHODS:
            email = _extract_email_from_request(request)
            log_write_operation(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                user_email=email,
            )
        return response

    # ── Session (required by authlib for OAuth state) ─────────────────────────
    session_secret = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
    app.add_middleware(SessionMiddleware, secret_key=session_secret)

    # ── CORS ──────────────────────────────────────────────────────────────────
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── HTTP exceptions (404, 405, etc.) ─────────────────────────────────────
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": f"HTTP_{exc.status_code}",
                    "message": exc.detail,
                    "detail": None,
                }
            },
        )

    # ── Pydantic validation errors (422) ─────────────────────────────────────
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "detail": exc.errors(),
                }
            },
        )

    # ── Catch-all for unhandled exceptions ────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(exc),
                    "detail": None,
                }
            },
        )
