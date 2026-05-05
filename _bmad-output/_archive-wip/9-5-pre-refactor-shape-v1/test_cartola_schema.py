"""Tests for CartolaCanonicalV1 — Story 9.5 Task 1."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.integrations.cartola_schema import CartolaCanonicalV1


SAMPLE_BANK_ACCOUNT_UUID = "9f3a0000-0000-4000-8000-000000000001"


def _valid_payload(**overrides) -> dict:
    payload = {
        "schema_version": "1.0",
        "source": {
            "bank_account_id": SAMPLE_BANK_ACCOUNT_UUID,
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
                {"code": "DUPLICATE_LINE", "line_no": 7, "detail": "same as line 4"}
            ],
        },
    }
    payload.update(overrides)
    return payload


def test_valid_canonical_payload_parses():
    obj = CartolaCanonicalV1.model_validate(_valid_payload())
    assert obj.schema_version == "1.0"
    assert obj.source.entity == "EAG"
    assert obj.balances.opening == Decimal("150000.00")
    assert obj.transactions[0].amount == Decimal("-45000.00")
    assert obj.extraction.warnings[0].code == "DUPLICATE_LINE"


def test_schema_version_must_be_1_0():
    with pytest.raises(ValidationError):
        CartolaCanonicalV1.model_validate(_valid_payload(schema_version="2.0"))


def test_account_type_literal_enforced():
    payload = _valid_payload()
    payload["source"]["account_type"] = "savings_account"
    with pytest.raises(ValidationError):
        CartolaCanonicalV1.model_validate(payload)


def test_entity_literal_enforced():
    payload = _valid_payload()
    payload["source"]["entity"] = "Unknown"
    with pytest.raises(ValidationError):
        CartolaCanonicalV1.model_validate(payload)


def test_currency_literal_enforced():
    payload = _valid_payload()
    payload["currency"] = "EUR"
    with pytest.raises(ValidationError):
        CartolaCanonicalV1.model_validate(payload)


def test_warning_code_literal_enforced():
    payload = _valid_payload()
    payload["extraction"]["warnings"] = [{"code": "RANDOM_WARN", "detail": "x"}]
    with pytest.raises(ValidationError):
        CartolaCanonicalV1.model_validate(payload)


def test_period_start_must_be_le_end():
    payload = _valid_payload()
    payload["period"] = {"start": "2026-04-01", "end": "2026-03-01"}
    with pytest.raises(ValidationError):
        CartolaCanonicalV1.model_validate(payload)


def test_transaction_line_no_must_be_positive():
    payload = _valid_payload()
    payload["transactions"][0]["line_no"] = 0
    with pytest.raises(ValidationError):
        CartolaCanonicalV1.model_validate(payload)


def test_transaction_raw_is_optional():
    payload = _valid_payload()
    del payload["transactions"][0]["raw"]
    obj = CartolaCanonicalV1.model_validate(payload)
    assert obj.transactions[0].raw is None


def test_transactions_can_be_empty():
    payload = _valid_payload(transactions=[])
    obj = CartolaCanonicalV1.model_validate(payload)
    assert obj.transactions == []


def test_warnings_default_to_empty_list():
    payload = _valid_payload()
    del payload["extraction"]["warnings"]
    obj = CartolaCanonicalV1.model_validate(payload)
    assert obj.extraction.warnings == []


def test_decimal_precision_preserved():
    payload = _valid_payload()
    payload["transactions"][0]["amount"] = "-450.123456"
    payload["transactions"][0]["currency"] = "USD"
    obj = CartolaCanonicalV1.model_validate(payload)
    assert obj.transactions[0].amount == Decimal("-450.123456")


def test_invalid_uuid_rejected():
    payload = _valid_payload()
    payload["source"]["bank_account_id"] = "not-a-uuid"
    with pytest.raises(ValidationError):
        CartolaCanonicalV1.model_validate(payload)
