"""CategorizationService — pipeline de 5 stages (Story 9.7 AC1-AC6).

Orden: (1) regla supra ≥30 → gana siempre · (2) smart_importer threshold 0.85 ·
(3) historical 1-29 · (4) Gemini fallback (lista cerrada) · (5) Suspense.

smart_importer (stage 2) y Gemini (stage 4) se INYECTAN como adapters opcionales (seams,
Story 9.7 decisión Ary 2026-06-17). Sin adapter, el stage se saltea. La lista `allowed` de
Gemini son las cuentas Expenses de `accounts.beancount` (NO Supabase — deprecado en 9.11/9.14).

Reemplaza al `NoopCategoryPredictor` de 9.6a: expone `.predict(description, amount,
bank_account_id) → (category_account, match_source, flag)` (Task 5).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from pipeline.importers.categorization.history import CategorizationHistory
from pipeline.importers.categorization.normalizer import normalize

SUPRA_THRESHOLD = 30
CONFIDENCE_THRESHOLD = Decimal("0.85")
SUSPENSE_ACCOUNT = "Expenses:EAG:Suspense"


@dataclass
class CategorizationResult:
    category_account: str
    match_source: str   # historical-30+ | smart_importer | historical | gemini | pending
    confidence: float
    flag: str           # "*" | "!"


class SmartImporterAdapter(Protocol):
    """Seam stage 2 (AC3). Devuelve (categoría, confianza 0-1) o None si no predice."""
    def predict(self, description: str, amount: Decimal, bank_account_id: str) -> tuple[str, float] | None: ...


class GeminiCategorizer(Protocol):
    """Seam stage 4 (AC5). Devuelve una cuenta de `allowed` o None."""
    def suggest_category(self, description: str, amount: Decimal, allowed: list[str]) -> str | None: ...


class CategorizationService:
    def __init__(
        self,
        history: CategorizationHistory,
        *,
        smart_importer: SmartImporterAdapter | None = None,
        gemini: GeminiCategorizer | None = None,
        expense_accounts: list[str] | None = None,
        suspense_account: str = SUSPENSE_ACCOUNT,
    ) -> None:
        self._history = history
        self._smart = smart_importer
        self._gemini = gemini
        self._expense_accounts = expense_accounts or []
        self._suspense = suspense_account
        self._cache: dict[str, CategorizationResult] = {}

    def invalidate(self, description: str) -> None:
        """Invalida el cache para esa description (AC7 — tras una corrección)."""
        self._cache.pop(normalize(description), None)

    def categorize(self, description: str, amount: Decimal, bank_account_id: str) -> CategorizationResult:
        key = normalize(description)
        if key in self._cache:
            return self._cache[key]
        result = self._pipeline(key, description, amount, bank_account_id)
        self._cache[key] = result
        return result

    def _pipeline(self, key, description, amount, bank_account_id) -> CategorizationResult:
        # Stage 1 — regla supra (≥30 correcciones a la misma categoría) → gana siempre.
        dom_cat, dom_count = self._history.dominant_category(key)
        if dom_cat and dom_count >= SUPRA_THRESHOLD:
            return CategorizationResult(dom_cat, "historical-30+", 1.0, "*")

        # Stage 2 — smart_importer (seam). Si predice, corta acá (conf decide la flag).
        if self._smart is not None:
            pred = self._smart.predict(description, amount, bank_account_id)
            if pred is not None:
                cat, conf = pred
                flag = "*" if Decimal(str(conf)) >= CONFIDENCE_THRESHOLD else "!"
                return CategorizationResult(cat, "smart_importer", float(conf), flag)

        # Stage 3 — historical 1-29.
        if dom_cat and dom_count > 0:
            return CategorizationResult(dom_cat, "historical", dom_count / SUPRA_THRESHOLD, "!")

        # Stage 4 — Gemini fallback (seam), lista cerrada de cuentas Expenses.
        if self._gemini is not None and self._expense_accounts:
            suggestion = self._gemini.suggest_category(description, amount, self._expense_accounts)
            if suggestion in self._expense_accounts:
                return CategorizationResult(suggestion, "gemini", 0.5, "!")

        # Stage 5 — Suspense (sin sugerencia → review explícita).
        return CategorizationResult(self._suspense, "pending", 0.0, "!")

    # ── Adapter al predictor de 9.6a (Task 5) ─────────────────────────────────

    def predict(self, description: str, amount: Decimal, bank_account_id: str) -> tuple[str, str, str]:
        """Interface que consume `cartola_pdf_importer` (Story 9.6a) — (category, match_source, flag)."""
        r = self.categorize(description, amount, bank_account_id)
        return r.category_account, r.match_source, r.flag
