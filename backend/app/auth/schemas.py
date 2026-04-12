"""Auth Pydantic models."""
from pydantic import BaseModel


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserSession(BaseModel):
    email: str
    role: str
