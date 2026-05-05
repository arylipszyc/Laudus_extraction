"""Schemas para endpoints admin — Story 9.10."""
from typing import Literal

from pydantic import BaseModel, Field


class FxBcchRefetchResponse(BaseModel):
    status: Literal["fetched", "skipped"]
    year_month: str = Field(..., description="YYYY-MM solicitado")
    bcch_date: str = Field(..., description="Fecha real (ISO YYYY-MM-DD) con publicación BCCh")
    rate_clp_per_usd: float
    source: str
