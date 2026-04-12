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
    # alias= used (not validation_alias) so FastAPI serializes using the Sheets column names
    model_config = ConfigDict(populate_by_name=True)

    journal_entry_id: Any = Field(default=None, alias="journalentryid")
    journal_entry_number: Any = Field(default=None, alias="journalentrynumber")
    date: str = ""
    account_number: Any = Field(default="", alias="accountnumber")
    line_id: Any = Field(default=None, alias="lineid")
    description: str = ""
    debit: float = 0.0
    credit: float = 0.0
    currency_code: str = Field(default="CLP", alias="currencycode")  # absent in ledger_final, default CLP
    parity_to_main_currency: float = Field(default=1.0, alias="paritytomaincurrency")
    periodo: str = ""
    account_name: str = Field(default="", alias="accountName")  # from ledger_final enrichment
    categoria1: str = Field(default="", alias="Categoria1")      # top-level category from PlanCuentas


class DashboardMeta(BaseModel):
    last_sync: str | None


class BalanceSheetResponse(BaseModel):
    data: list[BalanceSheetRecord]
    meta: DashboardMeta


class LedgerEntriesResponse(BaseModel):
    data: list[LedgerEntryRecord]
    meta: DashboardMeta
