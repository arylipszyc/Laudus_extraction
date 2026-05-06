"""Tests for CartolaCanonicalV1 Pydantic schema — Story 9.5 Task 1."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.integrations.cartola_schema import (
    CartolaBalances,
    CartolaCanonicalV1,
    CartolaExtraction,
    CartolaPeriod,
    CartolaSource,
    CartolaTransaction,
    CartolaWarning,
)


def _valid_payload() -> dict:
    """Reference payload from architecture-c4.md §4.1."""
    return {
        "schema_version": "1.0",
        "source": {
            "bank_account_id": "9f3a-uuid",
            "bank_name": "BCI",
            "account_label": "T/C Eduardo BCI Visa Infinity",
            "account_type": "tarjeta_credito",
            "entity": "EAG",
        },
        "period": {"start": "2026-03-01", "end": "2026-03-31"},
        "currency": "CLP",
        "balances": {"opening": "150000.00", "closing": "95000.00"},
        "transactions": [
            {
                "line_no": 1,
                "date": "2026-03-05",
                "description": "SUPERMERCADO JUMBO",
                "amount": "-45000.00",
                "currency": "CLP",
                "raw": {"merchant_country": "CL", "operation_type": "compra"},
            }
        ],
        "extraction": {
            "model": "gemini-2.0-flash",
            "extracted_at": "2026-04-30T15:00:00Z",
            "warnings": [
                {"code": "DUPLICATE_LINE", "line_no": 7, "detail": "same date+amount+desc as line 4"}
            ],
        },
    }


# ── Happy path ────────────────────────────────────────────────────────────


def test_valid_canonical_parses():
    cart = CartolaCanonicalV1.model_validate(_valid_payload())
    assert cart.schema_version == "1.0"
    assert cart.source.bank_account_id == "9f3a-uuid"
    assert cart.source.entity == "EAG"
    assert cart.transactions[0].amount == Decimal("-45000.00")
    assert cart.balances.opening == Decimal("150000.00")
    assert cart.extraction.warnings[0].code == "DUPLICATE_LINE"


def test_transactions_can_be_empty():
    payload = _valid_payload()
    payload["transactions"] = []
    cart = CartolaCanonicalV1.model_validate(payload)
    assert cart.transactions == []


def test_warnings_default_empty():
    payload = _valid_payload()
    del payload["extraction"]["warnings"]
    cart = CartolaCanonicalV1.model_validate(payload)
    assert cart.extraction.warnings == []


def test_raw_default_empty_dict():
    payload = _valid_payload()
    del payload["transactions"][0]["raw"]
    cart = CartolaCanonicalV1.model_validate(payload)
    assert cart.transactions[0].raw == {}


# ── schema_version ────────────────────────────────────────────────────────


def test_wrong_schema_version_rejected():
    payload = _valid_payload()
    payload["schema_version"] = "2.0"
    with pytest.raises(ValidationError):
        CartolaCanonicalV1.model_validate(payload)


# ── Closed enums ──────────────────────────────────────────────────────────


def test_invalid_account_type_rejected():
    payload = _valid_payload()
    payload["source"]["account_type"] = "cripto_wallet"
    with pytest.raises(ValidationError):
        CartolaCanonicalV1.model_validate(payload)


def test_invalid_currency_rejected():
    payload = _valid_payload()
    payload["currency"] = "BTC"
    with pytest.raises(ValidationError):
        CartolaCanonicalV1.model_validate(payload)


def test_invalid_warning_code_rejected():
    payload = _valid_payload()
    payload["extraction"]["warnings"] = [
        {"code": "FOO_BAR", "line_no": 1, "detail": "x"}
    ]
    with pytest.raises(ValidationError):
        CartolaCanonicalV1.model_validate(payload)


def test_known_warning_codes_accepted():
    """All canonical warning codes parse successfully."""
    codes = ["DUPLICATE_LINE", "ZERO_AMOUNT", "LARGE_AMOUNT",
             "LOW_CONFIDENCE", "PARSE_AMBIGUOUS", "PERIOD_MISMATCH"]
    for code in codes:
        w = CartolaWarning(code=code, line_no=1, detail="x")
        assert w.code == code


# ── Period ─────────────────────────────────────────────────────────────────


def test_period_end_before_start_rejected():
    with pytest.raises(ValidationError) as exc:
        CartolaPeriod(start="2026-03-31", end="2026-03-01")
    assert "period.end must be >= period.start" in str(exc.value)


def test_period_same_day_accepted():
    p = CartolaPeriod(start="2026-03-15", end="2026-03-15")
    assert p.start == p.end


# ── Transaction line_no rules ────────────────────────────────────────────


def test_duplicate_line_no_rejected():
    payload = _valid_payload()
    payload["transactions"] = [
        {"line_no": 1, "date": "2026-03-05", "description": "A",
         "amount": "-100.00", "currency": "CLP", "raw": {}},
        {"line_no": 1, "date": "2026-03-06", "description": "B",
         "amount": "-200.00", "currency": "CLP", "raw": {}},
    ]
    with pytest.raises(ValidationError) as exc:
        CartolaCanonicalV1.model_validate(payload)
    assert "line_no must be unique" in str(exc.value)


def test_line_no_zero_rejected():
    with pytest.raises(ValidationError):
        CartolaTransaction(
            line_no=0, date="2026-03-05", description="X",
            amount="-100", currency="CLP",
        )


def test_negative_amount_accepted():
    """Outflows are negative — must round-trip."""
    tx = CartolaTransaction(
        line_no=1, date="2026-03-05", description="x",
        amount="-1234.56", currency="CLP",
    )
    assert tx.amount == Decimal("-1234.56")


def test_positive_amount_accepted():
    """Inflows (payments, refunds) are positive."""
    tx = CartolaTransaction(
        line_no=1, date="2026-03-05", description="pago tc",
        amount="50000", currency="CLP",
    )
    assert tx.amount == Decimal("50000")


def test_zero_amount_accepted_at_schema_level():
    """ZERO_AMOUNT is a warning emitted by post-process, not a schema rejection."""
    tx = CartolaTransaction(
        line_no=1, date="2026-03-05", description="x",
        amount="0", currency="CLP",
    )
    assert tx.amount == Decimal("0")


# ── Strict (extra=forbid) ─────────────────────────────────────────────────


def test_unknown_field_at_root_rejected():
    payload = _valid_payload()
    payload["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        CartolaCanonicalV1.model_validate(payload)


def test_unknown_field_in_source_rejected():
    payload = _valid_payload()
    payload["source"]["extra"] = "y"
    with pytest.raises(ValidationError):
        CartolaCanonicalV1.model_validate(payload)


# ── Sub-models in isolation ───────────────────────────────────────────────


def test_balances_decimal_precision_preserved():
    b = CartolaBalances(opening="150000.00", closing="95000.50")
    assert b.opening == Decimal("150000.00")
    assert b.closing == Decimal("95000.50")


def test_source_full_construction():
    s = CartolaSource(
        bank_account_id="uuid-1",
        bank_name="BCI",
        account_label="X",
        account_type="cta_corriente",
        entity="EAG",
    )
    assert s.account_type == "cta_corriente"


def test_extraction_construction():
    e = CartolaExtraction(
        model="gemini-2.5-flash",
        extracted_at="2026-05-06T12:00:00Z",
    )
    assert e.warnings == []
