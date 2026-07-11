"""Pydantic schemas for dashboard API endpoints."""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# EAG + hijas (libro principal) + FFCC/JAB (libro RUT2, Story 11.2/FR47).
# El grupo consolidado "FondoComun" NO entra: vive solo a nivel servicio (11.1).
VALID_ENTITIES = frozenset({"EAG", "Jocelyn", "Jeannette", "Johanna", "Jael", "FFCC", "JAB"})


class BalanceSheetRecord(BaseModel):
    # Patch 4: add defaults to all required string fields — guards against empty Sheets cells
    account_id: Any = None
    account_number: str = ""
    # Path beancount completo (ej. "Assets:Jocelyn:..."). El frontend agrupa por la raíz contable;
    # sin declararlo aquí, el response_model lo descartaba y las cuentas de las hijas (códigos 6/7/8/9)
    # y las T/C caían en "Otros". Default "" → el path legacy de Sheets (sin `account`) sigue válido.
    account: str = ""
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
    categoria2: str = Field(default="", alias="Categoria2")      # 2nd-level category from PlanCuentas
    categoria3: str = Field(default="", alias="Categoria3")      # 3rd-level category from PlanCuentas
    # 7.1b AC1: tx_id de la transacción padre del posting (ancla de owner-comments). Sin alias —
    # el nombre del wire es el mismo. Declarado para que el response_model no lo descarte (PR #18).
    tx_id: str | None = None


class DashboardMeta(BaseModel):
    last_sync: str | None


class BalanceSheetResponse(BaseModel):
    data: list[BalanceSheetRecord]
    meta: DashboardMeta


class LedgerEntriesResponse(BaseModel):
    data: list[LedgerEntryRecord]
    meta: DashboardMeta
