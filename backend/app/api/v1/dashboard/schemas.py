"""Pydantic schemas for dashboard API endpoints."""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


VALID_ENTITIES = frozenset({"EAG", "Jocelyn", "Jeannette", "Johanna", "Jael"})


class BalanceSheetRecord(BaseModel):
    # Patch 4: add defaults to all required string fields — guards against empty Sheets cells
    account_id: Any = None
    account_number: str = ""
    account_name: str = ""
    debit: float = 0.0
    credit: float = 0.0
    debit_balance: float = 0.0
    credit_balance: float = 0.0
    query_date: str = ""
    is_latest: str = ""


class LedgerEntryRecord(BaseModel):
    # Patch 1: rename non-snake_case Sheets column names using validation_alias (AC6)
    # Patch 4: add defaults to all required fields
    model_config = ConfigDict(populate_by_name=True)

    journal_entry_id: Any = Field(default=None, validation_alias="journalentryid")
    journal_entry_number: Any = Field(default=None, validation_alias="journalentrynumber")
    date: str = ""
    account_number: Any = Field(default="", validation_alias="accountnumber")
    line_id: Any = Field(default=None, validation_alias="lineid")
    description: str = ""
    debit: float = 0.0
    credit: float = 0.0
    currency_code: str = Field(default="", validation_alias="currencycode")
    parity_to_main_currency: float = Field(default=1.0, validation_alias="paritytomaincurrency")
    periodo: str = ""


class DashboardMeta(BaseModel):
    last_sync: str | None


class BalanceSheetResponse(BaseModel):
    data: list[BalanceSheetRecord]
    meta: DashboardMeta


class LedgerEntriesResponse(BaseModel):
    data: list[LedgerEntryRecord]
    meta: DashboardMeta
