"""Google OAuth flow + JWT utilities."""
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from authlib.integrations.starlette_client import OAuth
from jose import jwt, JWTError

logger = logging.getLogger(__name__)

SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "8"))

# Story 9.13 — legacy roles in env var input are normalized to the 3-role taxonomy.
# Allows deployments still carrying `owner` in ALLOWED_USERS / RBAC_ROLE_MAPPING
# during the migration window without breaking auth.
_LEGACY_ROLE_NORMALIZE = {"owner": "family"}

oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def _normalize_role(role: str) -> str:
    return _LEGACY_ROLE_NORMALIZE.get(role, role)


def _parse_rbac_role_mapping() -> dict[str, str]:
    """Story 9.13 AC2: parse RBAC_ROLE_MAPPING env var (JSON) into {email: role}.

    Returns empty dict if env var missing or unparseable.
    """
    raw = os.getenv("RBAC_ROLE_MAPPING", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("RBAC_ROLE_MAPPING is not valid JSON; ignoring it")
        return {}
    if not isinstance(parsed, dict):
        logger.error("RBAC_ROLE_MAPPING must be a JSON object; ignoring it")
        return {}
    return {
        str(email).strip().lower(): _normalize_role(str(role).strip())
        for email, role in parsed.items()
    }


def _parse_allowed_users() -> dict[str, str]:
    """Parse legacy ALLOWED_USERS env var into {email: role} mapping.

    Kept as fallback so deployments can migrate to RBAC_ROLE_MAPPING without
    a breaking restart cycle.
    """
    raw = os.getenv("ALLOWED_USERS", "")
    mapping: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            email, role = entry.split(":", 1)
            mapping[email.strip().lower()] = _normalize_role(role.strip())
    return mapping


def get_role_for_email(email: str) -> str | None:
    """Return the role for an email, or None if not allowed.

    Story 9.13 AC2: prefers RBAC_ROLE_MAPPING (JSON). Falls back to legacy
    ALLOWED_USERS so the migration is reversible. Email not found → None
    (caller should reject the login with HTTP 403).
    """
    primary = _parse_rbac_role_mapping()
    if email.lower() in primary:
        return primary[email.lower()]
    return _parse_allowed_users().get(email.lower())


def create_jwt(email: str, role: str) -> str:
    payload = {
        "sub": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def decode_jwt(token: str) -> dict:
    return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
