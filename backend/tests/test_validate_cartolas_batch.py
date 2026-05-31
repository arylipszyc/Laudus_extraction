"""Tests for bootstrap/validate_cartolas_batch.py — Story 9.5c.

Pure-logic tests only. NO Gemini calls. Fixtures are hand-built RunResult
instances; no module here invokes `GeminiClient`.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from bootstrap.validate_cartolas_batch import (
    Color,
    PdfSummary,
    RunResult,
    _aggregate_by_bank,
    _sign_distribution_by_bank,
    classify_pdf,
    infer_bank_from_filename,
    is_stable,
    parse_override,
    resolve_pdf_metadata,
    summarize,
)
import argparse


# ── Helpers ───────────────────────────────────────────────────────────────


def _run(
    *,
    pdf_filename: str = "x.pdf",
    run_idx: int = 1,
    bank_name: str = "BCI",
    n_tx: int | None = 10,
    opening: str | None = "0",
    closing: str | None = "0",
    sum_amounts: str | None = "0",
    balance_diff: str | None = "0",
    warning_codes: list[str] | None = None,
    n_pos: int = 5,
    n_neg: int = 5,
    n_zero: int = 0,
    error: str = "",
) -> RunResult:
    return RunResult(
        pdf_filename=pdf_filename,
        run_idx=run_idx,
        bank_name=bank_name,
        n_transactions=n_tx,
        opening=Decimal(opening) if opening is not None else None,
        closing=Decimal(closing) if closing is not None else None,
        sum_amounts=Decimal(sum_amounts) if sum_amounts is not None else None,
        balance_diff=Decimal(balance_diff) if balance_diff is not None else None,
        warning_codes=warning_codes or [],
        n_positive=n_pos if not error else None,
        n_negative=n_neg if not error else None,
        n_zero=n_zero if not error else None,
        error=error,
    )


# ── infer_bank_from_filename (AC2) ────────────────────────────────────────


def test_infer_bank_bci():
    assert infer_bank_from_filename("bci-visa-202604.pdf") == "BCI"


def test_infer_bank_santander():
    assert infer_bank_from_filename("santander-mastercard-202604.pdf") == "Santander"


def test_infer_bank_banco_de_chile_long():
    assert infer_bank_from_filename("banco-de-chile-visa-202604.pdf") == "Banco de Chile"


def test_infer_bank_banco_de_chile_short():
    assert infer_bank_from_filename("bdechile-visa-202604.pdf") == "Banco de Chile"


def test_infer_bank_unknown_returns_none():
    assert infer_bank_from_filename("estado-de-cuenta (21).pdf") is None
    assert infer_bank_from_filename("a8a-uuid-1234.pdf") is None


def test_infer_bank_is_case_insensitive():
    assert infer_bank_from_filename("BCI-Visa-202604.pdf") == "BCI"


# ── parse_override (AC2) ──────────────────────────────────────────────────


def test_parse_override_happy_3_fields_defaults_clp():
    assert parse_override("estado-de-cuenta (21).pdf:Banco de Chile:1234") == (
        "estado-de-cuenta (21).pdf", "Banco de Chile", "1234", "CLP",
    )


def test_parse_override_happy_4_fields_with_currency():
    assert parse_override("estado-de-cuenta (21).pdf:BCI:9149:USD") == (
        "estado-de-cuenta (21).pdf", "BCI", "9149", "USD",
    )


def test_parse_override_currency_normalised_uppercase():
    assert parse_override("x.pdf:BCI:1234:usd")[3] == "USD"


def test_parse_override_invalid_currency_raises():
    with pytest.raises(argparse.ArgumentTypeError):
        parse_override("x.pdf:BCI:1234:JPY")


def test_parse_override_missing_part_raises():
    with pytest.raises(argparse.ArgumentTypeError):
        parse_override("only-two:parts")
    with pytest.raises(argparse.ArgumentTypeError):
        parse_override("::")


def test_parse_override_strips_whitespace():
    assert parse_override("  x.pdf : BCI : 1234 ") == ("x.pdf", "BCI", "1234", "CLP")


# ── resolve_pdf_metadata (AC2) ────────────────────────────────────────────


def test_resolve_with_inferred_bank_no_override():
    bank, last4, currency, fallback = resolve_pdf_metadata(Path("samples/bci-visa-202604.pdf"), {})
    assert (bank, last4, currency, fallback) == ("BCI", "9999", "CLP", False)


def test_resolve_with_override_takes_precedence_including_currency():
    overrides = {"bci-visa-202604.pdf": ("OverridenBank", "0001", "USD")}
    bank, last4, currency, fallback = resolve_pdf_metadata(
        Path("samples/bci-visa-202604.pdf"), overrides
    )
    assert (bank, last4, currency, fallback) == ("OverridenBank", "0001", "USD", False)


def test_resolve_unknown_falls_back_with_flag():
    bank, last4, currency, fallback = resolve_pdf_metadata(
        Path("samples/estado-de-cuenta (21).pdf"), {}
    )
    assert (bank, last4, currency, fallback) == ("Desconocido", "9999", "CLP", True)


# ── is_stable (AC4) ───────────────────────────────────────────────────────


def test_is_stable_identical_runs():
    runs = [_run(run_idx=i) for i in range(1, 4)]
    stable, drift = is_stable(runs)
    assert stable is True
    assert drift == []


def test_is_stable_drift_in_n_transactions():
    runs = [_run(run_idx=1, n_tx=10), _run(run_idx=2, n_tx=11)]
    stable, drift = is_stable(runs)
    assert stable is False
    assert "n_transactions" in drift


def test_is_stable_drift_in_opening():
    runs = [_run(run_idx=1, opening="100"), _run(run_idx=2, opening="101")]
    stable, drift = is_stable(runs)
    assert stable is False
    assert "opening" in drift


def test_is_stable_drift_in_closing():
    runs = [_run(run_idx=1, closing="500"), _run(run_idx=2, closing="600")]
    stable, drift = is_stable(runs)
    assert stable is False
    assert "closing" in drift


def test_is_stable_sum_diff_within_tolerance():
    runs = [_run(run_idx=1, sum_amounts="10000"),
            _run(run_idx=2, sum_amounts="10050")]
    stable, _ = is_stable(runs)
    assert stable is True  # diff 50 ≤ 100 CLP


def test_is_stable_sum_diff_above_tolerance():
    runs = [_run(run_idx=1, sum_amounts="10000"),
            _run(run_idx=2, sum_amounts="10200")]
    stable, drift = is_stable(runs)
    assert stable is False
    assert "sum_amounts" in drift


def test_is_stable_drift_in_warning_codes():
    runs = [_run(run_idx=1, warning_codes=["ZERO_AMOUNT"]),
            _run(run_idx=2, warning_codes=[])]
    stable, drift = is_stable(runs)
    assert stable is False
    assert "warning_codes" in drift


def test_is_stable_with_error_is_unstable():
    runs = [_run(run_idx=1), _run(run_idx=2, error="boom")]
    stable, drift = is_stable(runs)
    assert stable is False
    assert drift == ["error"]


# ── classify_pdf (AC5) — one test per color bucket ────────────────────────


def test_classify_verde_all_stable_no_warnings():
    runs = [_run(run_idx=i) for i in range(1, 4)]
    color, stable, drift = classify_pdf(runs)
    assert color is Color.VERDE
    assert stable is True
    assert drift == []


def test_classify_amarillo_by_drift_only():
    """Drift between runs but no warnings → amarillo."""
    runs = [_run(run_idx=1, n_tx=10), _run(run_idx=2, n_tx=11), _run(run_idx=3, n_tx=12)]
    color, *_ = classify_pdf(runs)
    assert color is Color.AMARILLO


def test_classify_amarillo_by_warning_codes_non_balance_mismatch():
    """Stable runs but with DUPLICATE_LINE warnings → amarillo."""
    runs = [_run(run_idx=i, warning_codes=["DUPLICATE_LINE"]) for i in range(1, 4)]
    color, *_ = classify_pdf(runs)
    assert color is Color.AMARILLO


def test_classify_rojo_by_exception():
    runs = [_run(run_idx=1), _run(run_idx=2, error="GeminiTimeout: dead")]
    color, *_ = classify_pdf(runs)
    assert color is Color.ROJO


def test_classify_rojo_by_balance_mismatch():
    runs = [_run(run_idx=i, warning_codes=["BALANCE_MISMATCH"]) for i in range(1, 4)]
    color, *_ = classify_pdf(runs)
    assert color is Color.ROJO


def test_classify_rojo_by_zero_transactions():
    runs = [_run(run_idx=i, n_tx=0) for i in range(1, 4)]
    color, *_ = classify_pdf(runs)
    assert color is Color.ROJO


def test_classify_rojo_wins_over_amarillo():
    """A PDF that's both unstable AND has BALANCE_MISMATCH → ROJO (priority)."""
    runs = [
        _run(run_idx=1, n_tx=10, warning_codes=["BALANCE_MISMATCH"]),
        _run(run_idx=2, n_tx=11, warning_codes=["BALANCE_MISMATCH"]),
    ]
    color, *_ = classify_pdf(runs)
    assert color is Color.ROJO


# ── Aggregator by bank (AC6) ──────────────────────────────────────────────


def _summary(pdf: str, bank: str, color: Color, runs: list[RunResult] | None = None) -> PdfSummary:
    return PdfSummary(
        pdf_filename=pdf, bank_name=bank, color=color, stable=True,
        drift_fields=[], warning_codes_distinct=[], runs=runs or [],
    )


def test_aggregate_by_bank_groups_correctly():
    summaries = [
        _summary("bci-1.pdf", "BCI", Color.VERDE),
        _summary("bci-2.pdf", "BCI", Color.VERDE),
        _summary("bci-3.pdf", "BCI", Color.ROJO),
        _summary("sant-1.pdf", "Santander", Color.AMARILLO),
        _summary("bdc-1.pdf", "Banco de Chile", Color.VERDE),
    ]
    rows = _aggregate_by_bank(summaries)
    by_bank = {row[0]: row for row in rows}
    assert by_bank["BCI"] == ("BCI", 3, 2, 0, 1, pytest.approx(66.6666, abs=0.01))
    assert by_bank["Santander"] == ("Santander", 1, 0, 1, 0, 0.0)
    assert by_bank["Banco de Chile"] == ("Banco de Chile", 1, 1, 0, 0, 100.0)


def test_aggregate_by_bank_handles_unknown_grouping():
    """`Desconocido` (fallback) should appear as its own bank in the table."""
    summaries = [
        _summary("estado-de-cuenta (21).pdf", "Desconocido", Color.AMARILLO),
        _summary("bci-visa-202604.pdf", "BCI", Color.VERDE),
    ]
    rows = _aggregate_by_bank(summaries)
    banks = {row[0] for row in rows}
    assert banks == {"Desconocido", "BCI"}


# ── Sign distribution (AC6) ───────────────────────────────────────────────


def test_sign_distribution_uses_first_run():
    s1 = _summary("a.pdf", "BCI", Color.VERDE, runs=[
        _run(pdf_filename="a.pdf", run_idx=1, n_pos=7, n_neg=3, n_zero=0),
        _run(pdf_filename="a.pdf", run_idx=2, n_pos=99, n_neg=1, n_zero=0),  # ignored
    ])
    s2 = _summary("b.pdf", "BCI", Color.VERDE, runs=[
        _run(pdf_filename="b.pdf", run_idx=1, n_pos=3, n_neg=7, n_zero=0),
    ])
    rows = _sign_distribution_by_bank([s1, s2])
    assert len(rows) == 1
    bank, pos, neg, zero = rows[0]
    assert bank == "BCI"
    # combined first-run: 10 pos, 10 neg → 50/50
    assert pos == pytest.approx(50.0)
    assert neg == pytest.approx(50.0)
    assert zero == pytest.approx(0.0)


def test_sign_distribution_skips_errored_first_runs():
    s = _summary("a.pdf", "BCI", Color.ROJO, runs=[
        _run(pdf_filename="a.pdf", run_idx=1, error="boom"),
    ])
    assert _sign_distribution_by_bank([s]) == []


# ── summarize() integration of classifier + drift ─────────────────────────


def test_summarize_packs_drift_and_warnings_in_notes():
    runs = [
        _run(run_idx=1, n_tx=10, warning_codes=["DUPLICATE_LINE"]),
        _run(run_idx=2, n_tx=11, warning_codes=["DUPLICATE_LINE"]),
    ]
    s = summarize(runs, "x.pdf", "BCI")
    assert s.color is Color.AMARILLO
    assert "n_transactions" in s.drift_fields
    assert s.warning_codes_distinct == ["DUPLICATE_LINE"]
    assert "drift" in s.notes


def test_summarize_counts_errored_runs_in_notes():
    runs = [_run(run_idx=1), _run(run_idx=2, error="boom"), _run(run_idx=3)]
    s = summarize(runs, "x.pdf", "BCI")
    assert s.color is Color.ROJO
    assert "errors:1/3" in s.notes


# ── Guard: tests don't instantiate GeminiClient (AC10) ────────────────────


def test_no_gemini_client_instantiation_in_test_module():
    """Guard: this test module must not call the Gemini SDK wrapper (AC10).

    We parse the module's AST and assert no call node has a function named
    `GeminiClient`. AST inspection avoids false positives from comments / strings.
    """
    import ast
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    needle = "Gemini" + "Client"  # split to keep this guard itself off the radar
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            assert name != needle, f"Tests must not instantiate {needle} (AC10)"
