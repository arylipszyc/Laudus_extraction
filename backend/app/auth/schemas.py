"""Auth Pydantic models."""
from typing import Literal

from pydantic import BaseModel

UserRole = Literal["family", "contador", "admin"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserSession(BaseModel):
    email: str
    role: UserRole
