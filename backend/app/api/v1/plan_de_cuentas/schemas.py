"""Pydantic schemas for plan_de_cuentas endpoints."""
from datetime import datetime

from pydantic import BaseModel


class PlanDeCuentasEntry(BaseModel):
    account_number: str
    account_name: str
    account_type: str | None = None
    cat1: str | None = None
    cat2: str | None = None
    cat3: str | None = None
    active: bool = True
    synced_at: datetime | None = None


class SyncResponse(BaseModel):
    synced: int
    updated: int
