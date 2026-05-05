"""Pydantic models for the canonical cartola JSON v1.0.

Shape source: _bmad-output/planning-artifacts/architecture-c4.md §4.1.
Story 9.5 produces this shape; Story 9.6 (beangulp) consumes it.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

AccountType = Literal["tarjeta_credito", "cta_corriente", "linea_credito", "cta_inversiones"]
Entity = Literal["EAG", "Jocelyn", "Jeannette", "Johanna", "Jael"]
Currency = Literal["CLP", "USD"]
WarningCode = Literal[
    "DUPLICATE_LINE",
    "ZERO_AMOUNT",
    "LARGE_AMOUNT",
    "LOW_CONFIDENCE",
    "PARSE_AMBIGUOUS",
    "PERIOD_MISMATCH",
]


class CartolaSource(BaseModel):
    bank_account_id: UUID
    bank_name: str
    account_label: str
    account_type: AccountType
    entity: Entity


class CartolaPeriod(BaseModel):
    start: date
    end: date

    @model_validator(mode="after")
    def _start_le_end(self) -> "CartolaPeriod":
        if self.start > self.end:
            raise ValueError("period.start must be <= period.end")
        return self


class CartolaBalances(BaseModel):
    opening: Decimal
    closing: Decimal


class CartolaTransaction(BaseModel):
    line_no: int = Field(ge=1)
    date: date
    description: str
    amount: Decimal
    currency: Currency
    raw: dict | None = None


class CartolaWarning(BaseModel):
    code: WarningCode
    line_no: int | None = None
    detail: str


class CartolaExtraction(BaseModel):
    model: str
    extracted_at: datetime
    warnings: list[CartolaWarning] = Field(default_factory=list)


class CartolaCanonicalV1(BaseModel):
    schema_version: Literal["1.0"]
    source: CartolaSource
    period: CartolaPeriod
    currency: Currency
    balances: CartolaBalances
    transactions: list[CartolaTransaction]
    extraction: CartolaExtraction
