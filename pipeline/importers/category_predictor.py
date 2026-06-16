"""CategoryPredictor — hook de categorización (Story 9.6a AC9, impl real en 9.7).

`predict(description, amount, bank_account_id) -> (category_account, match_source)`.
`match_source ∈ {historical, gemini, pending}`. En v1 el `NoopCategoryPredictor`
manda todo a `Expenses:EAG:Suspense` con `pending` → cada Transaction lleva flag `!`.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Protocol

SUSPENSE_ACCOUNT = "Expenses:EAG:Suspense"


class CategoryPredictor(Protocol):
    def predict(
        self, description: str, amount: Decimal, bank_account_id: str
    ) -> tuple[str, str]:
        ...


class NoopCategoryPredictor:
    """v1 — sin smart_importer. Todo a Suspense / pending (Story 9.7 lo reemplaza)."""

    def predict(self, description: str, amount: Decimal, bank_account_id: str) -> tuple[str, str]:
        return SUSPENSE_ACCOUNT, "pending"
