"""Auth endpoints: login, callback, logout, me."""
import os

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from backend.app.auth.schemas import UserSession
from backend.app.auth.service import create_jwt, decode_jwt, get_role_for_email, oauth
from jose import JWTError

router = APIRouter(prefix="/auth", tags=["auth"])

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
COOKIE_MAX_AGE = int(os.getenv("JWT_EXPIRE_HOURS", "8")) * 3600


@router.get("/login")
async def login(request: Request):
    """Redirect user to Google OAuth consent screen."""
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="auth_callback")
async def callback(request: Request):
    """Exchange OAuth code for token, set httpOnly cookie, redirect to dashboard."""
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception:
        raise HTTPException(status_code=400, detail="OAuth callback failed")

    user_info = token.get("userinfo") or {}
    email = user_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email not provided by Google")

    role = get_role_for_email(email)
    if role is None:
        raise HTTPException(status_code=403, detail="User not authorized")

    jwt_token = create_jwt(email=email, role=role)

    response = RedirectResponse(url=f"{FRONTEND_URL}/dashboard")
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=COOKIE_MAX_AGE,
    )
    return response


@router.post("/logout")
async def logout():
    """Clear the auth cookie."""
    response = Response(status_code=200)
    response.delete_cookie(key="access_token", samesite="lax")
    return response


@router.get("/me", response_model=UserSession)
async def me(request: Request):
    """Return current user from JWT cookie (used by frontend to check session)."""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_jwt(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return UserSession(email=payload["sub"], role=payload["role"])
