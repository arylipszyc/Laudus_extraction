"""Schemas de reconciliación — Story 9.12."""
from pydantic import BaseModel


class ResolveRequest(BaseModel):
    action: str
    justification: str | None = None


class ResolveResponse(BaseModel):
    status: str
    discrepancy_id: str
    action: str


class CountResponse(BaseModel):
    total: int
    blocking: int
