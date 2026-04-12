"""Pydantic schemas for sync API endpoints."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DataTypeSyncStatus(BaseModel):
    last_sync: datetime | None = None


class SyncRunStats(BaseModel):
    balance_sheet_added: int | None = None
    ledger_added: int | None = None


class SyncStatusResponse(BaseModel):
    balance_sheet: DataTypeSyncStatus
    ledger: DataTypeSyncStatus
    job_status: Literal["idle", "running", "done", "failed"]
    job_id: str | None = None
    error: str | None = None
    stats: SyncRunStats | None = None


class TriggerRequest(BaseModel):
    mode: Literal["normal", "backfill"] = "normal"
    from_date: str | None = None  # ISO date "YYYY-MM-DD", required when mode="backfill"


class TriggerResponse(BaseModel):
    status: str  # always "triggered"
    job_id: str
