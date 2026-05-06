"""Pydantic schema for the canonical cartola JSON v1.0.

Contract: `_bmad-output/planning-artifacts/architecture-c4.md` §4.1.
This is the validated output of Story 9.5 (PDF upload + Gemini extraction)
and the input of Story 9.6a (beangulp importer JSON → Beancount directives).
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Closed enums (architecture-c4.md §4.1)
AccountType = Literal[
    "tarjeta_credito",
    "cta_corriente",
    "cta_vista",
    "cta_ahorro",
    "linea_credito",
]
Currency = Literal["CLP", "USD", "EUR"]
WarningCode = Literal[
    "DUPLICATE_LINE",
    "ZERO_AMOUNT",
    "LARGE_AMOUNT",
    "LOW_CONFIDENCE",
    "PARSE_AMBIGUOUS",
    "PERIOD_MISMATCH",
    "BALANCE_MISMATCH",
]


class CartolaSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bank_account_id: str
    bank_name: str
    account_label: str
    account_type: AccountType
    entity: str


class CartolaPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: date
    end: date

    @model_validator(mode="after")
    def _start_le_end(self) -> "CartolaPeriod":
        if self.end < self.start:
            raise ValueError("period.end must be >= period.start")
        return self


class CartolaBalances(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opening: Decimal
    closing: Decimal


class CartolaTransaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_no: int = Field(..., ge=1)
    date: date
    description: str
    amount: Decimal
    currency: Currency
    raw: dict[str, Any] = Field(default_factory=dict)


class CartolaWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: WarningCode
    line_no: int | None = None
    detail: str


class CartolaExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    extracted_at: datetime
    warnings: list[CartolaWarning] = Field(default_factory=list)


class CartolaCanonicalV1(BaseModel):
    """Canonical cartola JSON — schema_version 1.0.

    Reglas de campos relevantes (architecture-c4.md §4.1):
    - `transactions[].amount` is SIGNED (negative = outflow for the holder).
    - `currency` top-level is the statement currency; per-transaction `currency`
      may differ (e.g. credit-card USD with CLP charges).
    - `bank_account_id` ata la cartola a una bank account específica
      (resuelta server-side desde `accounts.beancount` metadata).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    source: CartolaSource
    period: CartolaPeriod
    currency: Currency
    balances: CartolaBalances
    transactions: list[CartolaTransaction]
    extraction: CartolaExtraction

    @field_validator("transactions")
    @classmethod
    def _line_no_unique_and_ordered(cls, v: list[CartolaTransaction]) -> list[CartolaTransaction]:
        line_nos = [t.line_no for t in v]
        if len(set(line_nos)) != len(line_nos):
            raise ValueError("transactions[].line_no must be unique")
        return v
