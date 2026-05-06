"""Post-process warnings for cartolas — Story 9.5 Task 5.

Pure functions over a parsed `CartolaCanonicalV1`. Detects warnings the prompt
explicitly delegates to the backend (DUPLICATE_LINE, ZERO_AMOUNT, PERIOD_MISMATCH).
LARGE_AMOUNT requires history; if unavailable, the function emits nothing
(see `detect_large_amount_warnings`).
"""
from __future__ import annotations

from decimal import Decimal
from statistics import mean

from backend.app.integrations.cartola_schema import (
    CartolaCanonicalV1,
    CartolaWarning,
)

LARGE_AMOUNT_THRESHOLD_FACTOR = 3  # FR27: > 3× promedio histórico
BALANCE_MISMATCH_TOLERANCE_CLP = Decimal("100")  # Story 9.5 patch: round-off tolerance


def detect_duplicate_lines(canonical: CartolaCanonicalV1) -> list[CartolaWarning]:
    """FR26: same date+amount+description as another line in the same cartola."""
    seen: dict[tuple, int] = {}
    warnings: list[CartolaWarning] = []
    for tx in canonical.transactions:
        key = (tx.date, tx.amount, tx.description.strip().lower())
        if key in seen:
            warnings.append(
                CartolaWarning(
                    code="DUPLICATE_LINE",
                    line_no=tx.line_no,
                    detail=f"same date+amount+description as line {seen[key]}",
                )
            )
        else:
            seen[key] = tx.line_no
    return warnings


def detect_zero_amounts(canonical: CartolaCanonicalV1) -> list[CartolaWarning]:
    """FR27: amount == 0 is suspicious (likely parse error)."""
    return [
        CartolaWarning(code="ZERO_AMOUNT", line_no=tx.line_no, detail="amount = 0")
        for tx in canonical.transactions
        if tx.amount == Decimal("0")
    ]


def detect_period_mismatch(canonical: CartolaCanonicalV1) -> list[CartolaWarning]:
    """AC6: verify period.start ≤ first_tx.date ≤ last_tx.date ≤ period.end."""
    if not canonical.transactions:
        return []
    dates = [tx.date for tx in canonical.transactions]
    first, last = min(dates), max(dates)
    if first < canonical.period.start:
        return [CartolaWarning(
            code="PERIOD_MISMATCH",
            detail=(
                f"first transaction date ({first.isoformat()}) is before "
                f"period.start ({canonical.period.start.isoformat()})"
            ),
        )]
    if last > canonical.period.end:
        return [CartolaWarning(
            code="PERIOD_MISMATCH",
            detail=(
                f"last transaction date ({last.isoformat()}) is after "
                f"period.end ({canonical.period.end.isoformat()})"
            ),
        )]
    return []


def detect_balance_mismatch(
    canonical: CartolaCanonicalV1,
    tolerance: Decimal = BALANCE_MISMATCH_TOLERANCE_CLP,
) -> list[CartolaWarning]:
    """Story 9.5 patch — empirical guardrail against incomplete extraction.

    For Liability accounts (TC, linea_credito) and Asset accounts alike, the
    invariant is: closing - opening == sum(transactions) (with sign convention
    matched to the account type). When Gemini omits a line, this no longer
    holds and BALANCE_MISMATCH flags it immediately.
    """
    expected = canonical.balances.closing - canonical.balances.opening
    actual = sum((tx.amount for tx in canonical.transactions), start=Decimal("0"))
    diff = abs(expected - actual)
    if diff > tolerance:
        return [CartolaWarning(
            code="BALANCE_MISMATCH",
            detail=(
                f"sum(transactions)={actual:.0f} vs (closing-opening)={expected:.0f}, "
                f"diff={diff:.0f} (tolerance={tolerance:.0f})"
            ),
        )]
    return []


def detect_large_amount_warnings(
    canonical: CartolaCanonicalV1,
    historical_amounts: list[Decimal] | None = None,
) -> list[CartolaWarning]:
    """FR27: amount > 3× absolute average of historical lines for this account.

    `historical_amounts` is the list of |amount| from previous cartolas of the
    same `bank_account_id`. If empty/None: return [] (no history → no signal).
    """
    if not historical_amounts:
        return []
    avg = mean(abs(a) for a in historical_amounts)
    if avg <= 0:
        return []
    threshold = avg * LARGE_AMOUNT_THRESHOLD_FACTOR
    return [
        CartolaWarning(
            code="LARGE_AMOUNT",
            line_no=tx.line_no,
            detail=(
                f"amount {tx.amount} exceeds {LARGE_AMOUNT_THRESHOLD_FACTOR}× "
                f"historical average ({float(avg):.2f})"
            ),
        )
        for tx in canonical.transactions
        if abs(tx.amount) > threshold
    ]


def apply_post_process(
    canonical: CartolaCanonicalV1,
    historical_amounts: list[Decimal] | None = None,
) -> CartolaCanonicalV1:
    """Append post-process warnings to a canonical, preserving Gemini's own.

    Returns a new model (Pydantic frozen-style) — does not mutate the input.
    """
    new_warnings = list(canonical.extraction.warnings)
    new_warnings.extend(detect_duplicate_lines(canonical))
    new_warnings.extend(detect_zero_amounts(canonical))
    new_warnings.extend(detect_period_mismatch(canonical))
    new_warnings.extend(detect_balance_mismatch(canonical))
    new_warnings.extend(detect_large_amount_warnings(canonical, historical_amounts))

    # Deduplicate (line_no, code) pairs — Gemini might have emitted overlapping ones.
    seen: set[tuple] = set()
    deduped: list[CartolaWarning] = []
    for w in new_warnings:
        key = (w.code, w.line_no, w.detail)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(w)

    return canonical.model_copy(
        update={
            "extraction": canonical.extraction.model_copy(
                update={"warnings": deduped}
            )
        }
    )
