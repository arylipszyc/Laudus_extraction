"""FastAPI dependencies — injectable for testing."""
from functools import lru_cache
from typing import Callable

from fastapi import Depends, HTTPException, Request
from jose import JWTError

from backend.app.auth.schemas import UserSession
from backend.app.auth.service import decode_jwt
from backend.app.repositories.sheets_repository import SheetsRepository


@lru_cache(maxsize=1)
def get_repository() -> SheetsRepository:
    """Returns the singleton SheetsRepository instance.

    Override in tests via app.dependency_overrides[get_repository].
    """
    from config.gspread_config import get_spreadsheet
    return SheetsRepository(spreadsheet=get_spreadsheet())


_VALID_ROLES = frozenset({"owner", "contador"})


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
    if not email or role not in _VALID_ROLES:
        raise HTTPException(status_code=401, detail="Invalid token claims")
    return UserSession(email=email, role=role)


def require_role(allowed_roles: list[str]) -> Callable:
    """FastAPI dependency factory for role-based access control.

    Returns a dependency that verifies the authenticated user's role.
    Raises HTTP 403 if the user's role is not in allowed_roles.

    Usage:
        @router.post("/resource", dependencies=[Depends(require_role(["contador"]))])
        # or as a typed parameter:
        def endpoint(user: UserSession = Depends(require_role(["contador"]))):
    """
    def _check(user: UserSession = Depends(get_current_user)) -> UserSession:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return _check
