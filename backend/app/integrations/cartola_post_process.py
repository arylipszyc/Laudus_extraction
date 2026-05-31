"""Post-process warnings for cartolas — Story 9.5 Task 5.

Pure functions over a parsed `CartolaCanonicalV1`. Detects warnings the prompt
explicitly delegates to the backend (DUPLICATE_LINE, ZERO_AMOUNT, PERIOD_MISMATCH).
LARGE_AMOUNT requires history; if unavailable, the function emits nothing
(see `detect_large_amount_warnings`).
"""
from __future__ import annotations

import re
from decimal import Decimal
from statistics import mean

from backend.app.integrations.cartola_schema import (
    CartolaCanonicalV1,
    CartolaTransaction,
    CartolaWarning,
)

LARGE_AMOUNT_THRESHOLD_FACTOR = 3  # FR27: > 3× promedio histórico
BALANCE_MISMATCH_TOLERANCE_CLP = Decimal("100")  # Story 9.5 patch: round-off tolerance
# 9.5h iteración (smoke pass 1): el check estricto disparaba por boundary slop
# normal (tx 1-5 días antes de period.start es común en TC CL por corte de
# facturación). El check ahora dispara sólo ante una catástrofe — el LLM leyó
# mal el mes/año. Mitigación del coverage residual: UI post-upload para revisar
# y corregir el período (ver deferred-work.md → "review/edit period post-upload").
PERIOD_MISMATCH_RATIO_THRESHOLD = 0.80

# Story 9.5h: sufijo " (cuota X/N)" que el prompt agrega a cuotas pre-existentes.
# Captura X para distinguir pre-existentes (X≥1) de cuotas futuras (X=0).
_INSTALMENT_DESC_RE = re.compile(r"\(cuota (\d+)/\d+\)", re.IGNORECASE)


def _is_preexisting_installment(tx: CartolaTransaction) -> bool:
    """True si la transacción es una cuota X/N pre-existente.

    Su `date` es la fecha de la operación original (legítimamente anterior al
    período de la cartola actual), así que NO debe disparar PERIOD_MISMATCH.
    Señales (ver gemini_client._build_prompt): raw.cuotas o el sufijo
    " (cuota X/N)" en la description aportan el nº de cuota X; raw.operation_type
    == "cuota" es la señal de fallback cuando no hay X derivable.

    Una cuota futura (X=0, "0/N") NO se cobra este mes — el prompt la excluye de
    transactions; si aun así aparece, no es pre-existente y NO se exime del check.
    """
    raw = tx.raw or {}
    token = str(raw.get("cuotas") or "")
    m = re.match(r"\s*(\d+)\s*/\s*\d+", token) or _INSTALMENT_DESC_RE.search(tx.description or "")
    if m:
        return int(m.group(1)) >= 1
    return raw.get("operation_type") == "cuota"


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
    """AC6: detect catastrophic mismatch between extracted period and tx dates.

    Story 9.5h iteración (smoke pass 1, decisión Ary 2026-05-29): el check
    dispara SÓLO si ≥80% (PERIOD_MISMATCH_RATIO_THRESHOLD) de las transacciones
    no-cuota caen fuera del período — señal de que el LLM leyó mal el mes/año.
    Una o dos tx ligeramente fuera (boundary slop del corte de facturación, hasta
    5 días en la muestra real) NO dispara — es ruido. Cuotas pre-existentes X/N
    se siguen excluyendo (su fecha es legítimamente anterior). El coverage
    residual (años alucinados en pocas líneas) se mitiga vía UI post-upload
    (revisar/corregir período).
    """
    relevant = [
        tx for tx in canonical.transactions
        if not _is_preexisting_installment(tx)
    ]
    if not relevant:
        return []
    period_start, period_end = canonical.period.start, canonical.period.end
    out_of_period = [tx for tx in relevant if tx.date < period_start or tx.date > period_end]
    if len(out_of_period) / len(relevant) < PERIOD_MISMATCH_RATIO_THRESHOLD:
        return []
    dates = [tx.date for tx in out_of_period]
    first, last = min(dates), max(dates)
    return [CartolaWarning(
        code="PERIOD_MISMATCH",
        detail=(
            f"{len(out_of_period)} of {len(relevant)} transactions "
            f"({100 * len(out_of_period) / len(relevant):.0f}%) outside "
            f"period {period_start.isoformat()}..{period_end.isoformat()} "
            f"(out-of-period range {first.isoformat()}..{last.isoformat()})"
        ),
    )]


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
