"""Tests for cartola post-process warnings — Story 9.5 Task 5."""
from decimal import Decimal

import pytest

from backend.app.integrations.cartola_post_process import (
    apply_post_process,
    detect_balance_mismatch,
    detect_duplicate_lines,
    detect_large_amount_warnings,
    detect_period_mismatch,
    detect_zero_amounts,
)
from backend.app.integrations.cartola_schema import (
    CartolaCanonicalV1,
    CartolaWarning,
)


def _build(transactions: list[dict], **overrides) -> CartolaCanonicalV1:
    payload = {
        "schema_version": "1.0",
        "source": {
            "bank_account_id": "uuid-x",
            "bank_name": "BCI",
            "account_label": "X",
            "account_type": "tarjeta_credito",
            "entity": "EAG",
        },
        "period": {"start": "2026-03-01", "end": "2026-03-31"},
        "currency": "CLP",
        "balances": {"opening": "0", "closing": "0"},
        "transactions": [
            {
                "line_no": i + 1,
                "date": "2026-03-15",
                "description": "X",
                "amount": "-1000",
                "currency": "CLP",
                "raw": {},
                **tx,
            }
            for i, tx in enumerate(transactions)
        ],
        "extraction": {
            "model": "gemini-2.5-flash",
            "extracted_at": "2026-04-30T15:00:00Z",
            "warnings": [],
        },
    }
    payload.update(overrides)
    return CartolaCanonicalV1.model_validate(payload)


# ── DUPLICATE_LINE ────────────────────────────────────────────────────────


def test_duplicate_lines_same_date_amount_description():
    cart = _build([
        {"line_no": 1, "date": "2026-03-05", "description": "JUMBO", "amount": "-45000"},
        {"line_no": 2, "date": "2026-03-05", "description": "Lider", "amount": "-30000"},
        {"line_no": 3, "date": "2026-03-05", "description": "JUMBO", "amount": "-45000"},
    ])
    warnings = detect_duplicate_lines(cart)
    assert len(warnings) == 1
    assert warnings[0].line_no == 3
    assert "line 1" in warnings[0].detail


def test_duplicate_lines_case_insensitive_description():
    cart = _build([
        {"line_no": 1, "date": "2026-03-05", "description": "Jumbo", "amount": "-100"},
        {"line_no": 2, "date": "2026-03-05", "description": "JUMBO", "amount": "-100"},
    ])
    assert len(detect_duplicate_lines(cart)) == 1


def test_duplicate_lines_no_match_when_different_date():
    cart = _build([
        {"line_no": 1, "date": "2026-03-05", "description": "JUMBO", "amount": "-100"},
        {"line_no": 2, "date": "2026-03-06", "description": "JUMBO", "amount": "-100"},
    ])
    assert detect_duplicate_lines(cart) == []


def test_duplicate_lines_three_in_a_row_emits_two_warnings():
    cart = _build([
        {"line_no": 1, "date": "2026-03-05", "description": "X", "amount": "-100"},
        {"line_no": 2, "date": "2026-03-05", "description": "X", "amount": "-100"},
        {"line_no": 3, "date": "2026-03-05", "description": "X", "amount": "-100"},
    ])
    warnings = detect_duplicate_lines(cart)
    assert len(warnings) == 2
    assert {w.line_no for w in warnings} == {2, 3}


# ── ZERO_AMOUNT ────────────────────────────────────────────────────────────


def test_zero_amount_detected():
    cart = _build([
        {"line_no": 1, "amount": "-100"},
        {"line_no": 2, "amount": "0"},
        {"line_no": 3, "amount": "100"},
    ])
    warnings = detect_zero_amounts(cart)
    assert len(warnings) == 1
    assert warnings[0].line_no == 2


def test_zero_amount_empty_when_none():
    cart = _build([{"line_no": 1, "amount": "-100"}])
    assert detect_zero_amounts(cart) == []


# ── PERIOD_MISMATCH ───────────────────────────────────────────────────────


def test_period_mismatch_first_tx_before_period_start():
    cart = _build(
        [{"line_no": 1, "date": "2026-02-25", "amount": "-100"}],
        period={"start": "2026-03-01", "end": "2026-03-31"},
    )
    warnings = detect_period_mismatch(cart)
    assert len(warnings) == 1
    assert warnings[0].code == "PERIOD_MISMATCH"
    assert "outside period" in warnings[0].detail and "2026-02-25" in warnings[0].detail


def test_period_mismatch_last_tx_after_period_end():
    cart = _build(
        [{"line_no": 1, "date": "2026-04-05", "amount": "-100"}],
        period={"start": "2026-03-01", "end": "2026-03-31"},
    )
    warnings = detect_period_mismatch(cart)
    assert len(warnings) == 1
    assert "outside period" in warnings[0].detail and "2026-04-05" in warnings[0].detail


def test_period_mismatch_no_warning_when_in_range():
    cart = _build(
        [
            {"line_no": 1, "date": "2026-03-01", "amount": "-100"},
            {"line_no": 2, "date": "2026-03-31", "amount": "-200"},
        ],
        period={"start": "2026-03-01", "end": "2026-03-31"},
    )
    assert detect_period_mismatch(cart) == []


def test_period_mismatch_no_warning_when_no_transactions():
    cart = _build([])
    assert detect_period_mismatch(cart) == []


# ── PERIOD_MISMATCH cuota-aware (Story 9.5h AC3) ──────────────────────────


def test_period_mismatch_excludes_instalment_by_operation_type():
    """Cuota pre-existente (fecha anterior al período) identificada por raw.operation_type."""
    cart = _build(
        [{"line_no": 1, "date": "2026-01-10", "amount": "5000",
          "raw": {"operation_type": "cuota", "cuotas": "3/6"}}],
        period={"start": "2026-03-01", "end": "2026-03-31"},
    )
    assert detect_period_mismatch(cart) == []


def test_period_mismatch_excludes_instalment_by_raw_cuotas():
    cart = _build(
        [{"line_no": 1, "date": "2026-01-10", "amount": "5000",
          "raw": {"cuotas": "3/6"}}],
        period={"start": "2026-03-01", "end": "2026-03-31"},
    )
    assert detect_period_mismatch(cart) == []


def test_period_mismatch_excludes_instalment_by_description_suffix():
    """Sin raw, la cuota se reconoce por el sufijo ' (cuota X/N)' de la description."""
    cart = _build(
        [{"line_no": 1, "date": "2026-01-10", "amount": "5000",
          "description": "NETFLIX (cuota 3/6)", "raw": {}}],
        period={"start": "2026-03-01", "end": "2026-03-31"},
    )
    assert detect_period_mismatch(cart) == []


def test_period_mismatch_still_flags_non_instalment_before_start():
    """Una compra normal (no-cuota) anterior al período SIGUE siendo anomalía."""
    cart = _build(
        [{"line_no": 1, "date": "2026-02-25", "amount": "-100",
          "description": "JUMBO", "raw": {"operation_type": "compra"}}],
        period={"start": "2026-03-01", "end": "2026-03-31"},
    )
    warnings = detect_period_mismatch(cart)
    assert len(warnings) == 1
    assert warnings[0].code == "PERIOD_MISMATCH"


def test_period_mismatch_still_flags_non_instalment_after_end():
    cart = _build(
        [{"line_no": 1, "date": "2026-04-05", "amount": "-100",
          "description": "JUMBO", "raw": {}}],
        period={"start": "2026-03-01", "end": "2026-03-31"},
    )
    assert len(detect_period_mismatch(cart)) == 1


def test_period_mismatch_mix_instalment_out_and_normal_in_range():
    """Cuota fuera de período + compra normal dentro → no warning (la única fuera es cuota)."""
    cart = _build(
        [
            {"line_no": 1, "date": "2026-01-10", "amount": "5000",
             "raw": {"operation_type": "cuota", "cuotas": "2/12"}},
            {"line_no": 2, "date": "2026-03-15", "amount": "-100",
             "description": "JUMBO", "raw": {"operation_type": "compra"}},
        ],
        period={"start": "2026-03-01", "end": "2026-03-31"},
    )
    assert detect_period_mismatch(cart) == []


def test_period_mismatch_all_instalments_out_of_range():
    cart = _build(
        [
            {"line_no": 1, "date": "2026-01-10", "amount": "5000",
             "raw": {"operation_type": "cuota", "cuotas": "2/12"}},
            {"line_no": 2, "date": "2025-12-10", "amount": "5000",
             "raw": {"operation_type": "cuota", "cuotas": "1/12"}},
        ],
        period={"start": "2026-03-01", "end": "2026-03-31"},
    )
    assert detect_period_mismatch(cart) == []


# ── PERIOD_MISMATCH ratio rule (Story 9.5h iteración smoke pass 1) ────────


def test_period_mismatch_silenced_when_minority_out_of_period():
    """Boundary slop: 1 tx fuera de 5 (20%) < 80% threshold → NO warn.

    Caso real medido en el smoke 2026-05-29: TC chilenas tienen tx normales
    1-5 días antes de period.start por corte de facturación. Es ruido.
    """
    cart = _build(
        [
            {"line_no": 1, "date": "2026-02-28", "amount": "-100",  # 1 día antes
             "raw": {"operation_type": "compra"}},
            {"line_no": 2, "date": "2026-03-05", "amount": "-100"},
            {"line_no": 3, "date": "2026-03-10", "amount": "-100"},
            {"line_no": 4, "date": "2026-03-20", "amount": "-100"},
            {"line_no": 5, "date": "2026-03-25", "amount": "-100"},
        ],
        period={"start": "2026-03-01", "end": "2026-03-31"},
    )
    assert detect_period_mismatch(cart) == []


def test_period_mismatch_fires_when_majority_out_of_period():
    """Catástrofe: 4 tx fuera de 5 (80%) ≥ threshold → SÍ warn.

    Señal de que el LLM leyó mal el mes/año del período.
    """
    cart = _build(
        [
            {"line_no": 1, "date": "2026-02-10", "amount": "-100",
             "raw": {"operation_type": "compra"}},
            {"line_no": 2, "date": "2026-02-15", "amount": "-100"},
            {"line_no": 3, "date": "2026-02-20", "amount": "-100"},
            {"line_no": 4, "date": "2026-02-25", "amount": "-100"},
            {"line_no": 5, "date": "2026-03-05", "amount": "-100"},  # única dentro
        ],
        period={"start": "2026-03-01", "end": "2026-03-31"},
    )
    warnings = detect_period_mismatch(cart)
    assert len(warnings) == 1
    assert warnings[0].code == "PERIOD_MISMATCH"
    assert "4 of 5" in warnings[0].detail


# ── LARGE_AMOUNT ──────────────────────────────────────────────────────────


def test_large_amount_no_history_returns_empty():
    cart = _build([{"line_no": 1, "amount": "-100000"}])
    assert detect_large_amount_warnings(cart, historical_amounts=None) == []
    assert detect_large_amount_warnings(cart, historical_amounts=[]) == []


def test_large_amount_above_3x_average_flagged():
    cart = _build([{"line_no": 1, "amount": "-50000"}])
    history = [Decimal("10000"), Decimal("12000"), Decimal("8000")]  # avg 10000
    warnings = detect_large_amount_warnings(cart, history)
    assert len(warnings) == 1
    assert warnings[0].code == "LARGE_AMOUNT"
    assert warnings[0].line_no == 1


def test_large_amount_below_3x_average_not_flagged():
    cart = _build([{"line_no": 1, "amount": "-25000"}])
    history = [Decimal("10000"), Decimal("12000"), Decimal("8000")]  # avg 10000, threshold 30000
    assert detect_large_amount_warnings(cart, history) == []


def test_large_amount_uses_absolute_value():
    """Outflow of -50000 with positive avg history → still flagged."""
    cart = _build([{"line_no": 1, "amount": "-50000"}])
    history = [Decimal("10000"), Decimal("10000")]
    warnings = detect_large_amount_warnings(cart, history)
    assert len(warnings) == 1


# ── apply_post_process integration ────────────────────────────────────────


def test_apply_post_process_preserves_gemini_warnings():
    cart = _build(
        [{"line_no": 1, "amount": "-100"}],
        extraction={
            "model": "gemini-2.5-flash",
            "extracted_at": "2026-04-30T15:00:00Z",
            "warnings": [
                {"code": "LOW_CONFIDENCE", "line_no": 1, "detail": "blurry text"}
            ],
        },
    )
    enriched = apply_post_process(cart)
    codes = [w.code for w in enriched.extraction.warnings]
    assert "LOW_CONFIDENCE" in codes


def test_apply_post_process_combines_all_categories():
    # 9.5h iter: las 3 tx caen fuera del período (100% > 80% threshold) para
    # que PERIOD_MISMATCH dispare bajo la nueva regla de ratio.
    cart = _build(
        [
            {"line_no": 1, "date": "2026-04-05", "description": "X", "amount": "0"},
            {"line_no": 2, "date": "2026-04-05", "description": "X", "amount": "0"},
            {"line_no": 3, "date": "2026-04-10", "description": "Y", "amount": "-100"},
        ],
        period={"start": "2026-03-01", "end": "2026-03-31"},
    )
    enriched = apply_post_process(cart)
    codes = sorted({w.code for w in enriched.extraction.warnings})
    assert codes == ["DUPLICATE_LINE", "PERIOD_MISMATCH", "ZERO_AMOUNT"]


def test_apply_post_process_dedupes_overlapping_warnings():
    """If Gemini already emitted DUPLICATE_LINE for the same line/detail, don't double up."""
    cart = _build(
        [
            {"line_no": 1, "date": "2026-03-05", "description": "X", "amount": "-100"},
            {"line_no": 2, "date": "2026-03-05", "description": "X", "amount": "-100"},
        ],
        extraction={
            "model": "gemini-2.5-flash",
            "extracted_at": "2026-04-30T15:00:00Z",
            "warnings": [
                {"code": "DUPLICATE_LINE", "line_no": 2,
                 "detail": "same date+amount+description as line 1"}
            ],
        },
    )
    enriched = apply_post_process(cart)
    duplicates = [w for w in enriched.extraction.warnings if w.code == "DUPLICATE_LINE"]
    assert len(duplicates) == 1


def test_apply_post_process_does_not_mutate_input():
    cart = _build([{"line_no": 1, "amount": "0"}])
    apply_post_process(cart)
    # Original still has no warnings.
    assert cart.extraction.warnings == []


# ── BALANCE_MISMATCH (Story 9.5 patch — guardrail empírico) ───────────────


def test_balance_mismatch_clean_sum_matches_no_warning():
    """Liability convention: closing - opening == sum(transactions)."""
    cart = _build(
        [
            {"line_no": 1, "amount": "100"},
            {"line_no": 2, "amount": "200"},
        ],
        balances={"opening": "0", "closing": "300"},
    )
    assert detect_balance_mismatch(cart) == []


def test_balance_mismatch_diff_above_tolerance_flagged():
    """Sum off by more than 100 CLP → BALANCE_MISMATCH."""
    cart = _build(
        [
            {"line_no": 1, "amount": "100"},
            {"line_no": 2, "amount": "200"},
        ],
        balances={"opening": "0", "closing": "1000"},  # expected 1000, actual 300, diff 700
    )
    warnings = detect_balance_mismatch(cart)
    assert len(warnings) == 1
    assert warnings[0].code == "BALANCE_MISMATCH"
    assert "diff=700" in warnings[0].detail


def test_balance_mismatch_within_tolerance_no_warning():
    """Round-off ≤ 100 CLP is tolerated silently."""
    cart = _build(
        [{"line_no": 1, "amount": "150"}],
        balances={"opening": "0", "closing": "200"},  # diff 50, within tolerance
    )
    assert detect_balance_mismatch(cart) == []


def test_balance_mismatch_negative_pago_decrements_liability():
    """TC pago = NEGATIVE; opening 1000, pago -300, compras +500 → closing 1200."""
    cart = _build(
        [
            {"line_no": 1, "amount": "-300"},  # pago
            {"line_no": 2, "amount": "500"},   # compras
        ],
        balances={"opening": "1000", "closing": "1200"},
    )
    assert detect_balance_mismatch(cart) == []


def test_balance_mismatch_empty_transactions_with_zero_balances():
    cart = _build(
        [],
        balances={"opening": "0", "closing": "0"},
    )
    assert detect_balance_mismatch(cart) == []


def test_apply_post_process_includes_balance_mismatch():
    """Integration: BALANCE_MISMATCH appears in apply_post_process output."""
    cart = _build(
        [{"line_no": 1, "amount": "100"}],
        balances={"opening": "0", "closing": "1000"},
    )
    enriched = apply_post_process(cart)
    codes = [w.code for w in enriched.extraction.warnings]
    assert "BALANCE_MISMATCH" in codes
