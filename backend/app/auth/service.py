"""Google OAuth flow + JWT utilities."""
import os
from datetime import datetime, timedelta, timezone

from authlib.integrations.starlette_client import OAuth
from jose import jwt, JWTError

SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "8"))

oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def _parse_allowed_users() -> dict[str, str]:
    """Parse ALLOWED_USERS env var into {email: role} mapping."""
    raw = os.getenv("ALLOWED_USERS", "")
    mapping: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            email, role = entry.split(":", 1)
            mapping[email.strip().lower()] = role.strip()
    return mapping


def get_role_for_email(email: str) -> str | None:
    """Return the role for an email, or None if not allowed."""
    allowed = _parse_allowed_users()
    return allowed.get(email.lower())


def create_jwt(email: str, role: str) -> str:
    payload = {
        "sub": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def decode_jwt(token: str) -> dict:
    return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
