"""FastAPI dependencies — injectable for testing."""
import logging
from functools import lru_cache
from typing import Callable

from fastapi import Depends, HTTPException, Request
from jose import JWTError

from backend.app.auth.schemas import UserSession
from backend.app.auth.service import decode_jwt
from backend.app.repositories.sheets_repository import SheetsRepository

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_repository() -> SheetsRepository:
    """Returns the singleton SheetsRepository instance.

    Override in tests via app.dependency_overrides[get_repository].
    """
    from pipeline.config.gspread_config import get_spreadsheet
    return SheetsRepository(spreadsheet=get_spreadsheet())


_VALID_ROLES = frozenset({"family", "contador", "admin"})
# Story 9.13 Task 4: legacy alias — JWTs minted before the RBAC refactor carry
# `"role": "owner"`. Treat as `"family"` until the JWT TTL window (~24h) elapses.
_LEGACY_ROLE_ALIAS = {"owner": "family"}


def get_current_user(request: Request) -> UserSession:
    """Validate JWT from httpOnly cookie and return the current user.

    Raises HTTP 401 if cookie missing, expired, invalid, or contains unknown claims.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_jwt(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    email = payload.get("sub")
    role = payload.get("role")
    if role in _LEGACY_ROLE_ALIAS:
        logger.warning(
            "LEGACY_ROLE_OWNER_DETECTED email=%s legacy_role=%s mapped_to=%s",
            email, role, _LEGACY_ROLE_ALIAS[role],
        )
        role = _LEGACY_ROLE_ALIAS[role]
    if not email or role not in _VALID_ROLES:
        raise HTTPException(status_code=401, detail="Invalid token claims")
    return UserSession(email=email, role=role)


def require_role(allowed_roles: list[str]) -> Callable:
    """FastAPI dependency factory for role-based access control.

    Returns a dependency that verifies the authenticated user's role.
    Raises HTTP 403 if the user's role is not in allowed_roles.
    Logs `RBAC_DENIED` (AC5) for any 403.

    Usage:
        @router.post("/resource", dependencies=[Depends(require_role(["contador"]))])
        # or as a typed parameter:
        def endpoint(user: UserSession = Depends(require_role(["contador", "admin"]))):
    """
    def _check(request: Request, user: UserSession = Depends(get_current_user)) -> UserSession:
        if user.role not in allowed_roles:
            logger.warning(
                "RBAC_DENIED user_email=%s user_role=%s endpoint=%s required_roles=%s",
                user.email, user.role, request.url.path, list(allowed_roles),
            )
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return _check
