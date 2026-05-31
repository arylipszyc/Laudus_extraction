"""Tests for process_upload_sync retry logic — Story 9.5h Task 4/7.

Gemini is mocked with controlled sequences (extract_pdf.side_effect). No real
Gemini calls, no API key. The retry does INDEPENDENT draws (not retry-with-
feedback) on transient failures: GeminiExtractionError or BALANCE_MISMATCH.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from backend.app.api.v1.cartolas.service import process_upload_sync
from backend.app.integrations.bank_account_index import BankAccountEntry
from backend.app.integrations.gemini_client import GeminiExtractionError


@pytest.fixture
def staging_dir(tmp_path: Path) -> Path:
    d = tmp_path / "_staging"
    d.mkdir()
    return d


def _entry() -> BankAccountEntry:
    return BankAccountEntry(
        bank_account_id="uuid-bci",
        bank_name="BCI",
        account_label="BCI 10160175",
        account_type="tarjeta_credito",
        entity="EAG",
        currency="CLP",
        last4="0175",
        beancount_account="Liabilities:EAG:TC:Bci-0175",
    )


def _payload(*, opening: str, closing: str, amount: str = "300") -> dict:
    return {
        "schema_version": "1.0",
        "source": {  # overwritten server-side; kept shape-valid
            "bank_account_id": "uuid-bci", "bank_name": "BCI",
            "account_label": "BCI 10160175", "account_type": "tarjeta_credito",
            "entity": "EAG",
        },
        "period": {"start": "2026-03-01", "end": "2026-03-31"},
        "currency": "CLP",
        "balances": {"opening": opening, "closing": closing},
        "transactions": [
            {"line_no": 1, "date": "2026-03-05", "description": "JUMBO",
             "amount": amount, "currency": "CLP", "raw": {}},
        ],
        "extraction": {"model": "gemini-3.5-flash",
                       "extracted_at": "2026-04-30T15:00:00Z", "warnings": []},
    }


def _clean_payload() -> dict:
    return _payload(opening="0", closing="300", amount="300")  # diff 0 → no mismatch


def _mismatch_payload() -> dict:
    return _payload(opening="0", closing="1000", amount="300")  # diff 700 → BALANCE_MISMATCH


def _invalid_shape_payload() -> dict:
    """Parsea como JSON pero falla la validación Pydantic (line_no debe ser ≥1)."""
    p = _payload(opening="0", closing="300", amount="300")
    p["transactions"][0]["line_no"] = 0  # viola Field(ge=1) → ValidationError
    return p


def _fake_gemini(side_effect) -> MagicMock:
    fake = MagicMock()
    fake.model = "gemini-3.5-flash"
    fake.extract_pdf.side_effect = side_effect
    return fake


def _run(gemini: MagicMock, staging_dir: Path):
    return process_upload_sync(
        batch_id="b1", pdf_bytes=b"%PDF", bank_account_entry=_entry(),
        gemini=gemini, staging_dir=staging_dir,
    )


def _has_mismatch(canonical) -> bool:
    return any(w.code == "BALANCE_MISMATCH" for w in canonical.extraction.warnings)


def test_retry_balance_mismatch_then_clean(staging_dir):
    gemini = _fake_gemini([_mismatch_payload(), _clean_payload()])
    result = _run(gemini, staging_dir)
    assert gemini.extract_pdf.call_count == 2
    assert not _has_mismatch(result)


def test_retry_extraction_error_then_clean(staging_dir):
    gemini = _fake_gemini([GeminiExtractionError("truncated"), _clean_payload()])
    result = _run(gemini, staging_dir)
    assert gemini.extract_pdf.call_count == 2
    assert not _has_mismatch(result)


def test_all_attempts_balance_mismatch_returns_last_with_warning(staging_dir):
    gemini = _fake_gemini(
        [_mismatch_payload(), _mismatch_payload(), _mismatch_payload()]
    )
    result = _run(gemini, staging_dir)
    assert gemini.extract_pdf.call_count == 3
    # Persistent mismatch is surfaced, not hidden.
    assert _has_mismatch(result)


def test_all_attempts_extraction_error_propagates(staging_dir):
    gemini = _fake_gemini([
        GeminiExtractionError("e1"),
        GeminiExtractionError("e2"),
        GeminiExtractionError("e3"),
    ])
    with pytest.raises(GeminiExtractionError):
        _run(gemini, staging_dir)
    assert gemini.extract_pdf.call_count == 3


def test_clean_first_attempt_no_retry(staging_dir):
    gemini = _fake_gemini([_clean_payload()])
    result = _run(gemini, staging_dir)
    assert gemini.extract_pdf.call_count == 1
    assert not _has_mismatch(result)


def test_validation_error_after_valid_mismatch_returns_last_valid(staging_dir):
    """Patch 1 (9.5h review): un ValidationError en un intento posterior NO
    descarta un canonical válido obtenido antes. Se devuelve el último válido
    con su BALANCE_MISMATCH preservado, en vez de fallar el job entero."""
    gemini = _fake_gemini([_mismatch_payload(), _invalid_shape_payload()])
    result = _run(gemini, staging_dir)
    assert gemini.extract_pdf.call_count == 2
    assert _has_mismatch(result)


def test_validation_error_first_attempt_propagates(staging_dir):
    """Patch 1 (9.5h review): sin last_valid previo, ValidationError se propaga
    y NO se reintenta (shape inválido = determinista, AC4)."""
    gemini = _fake_gemini([_invalid_shape_payload(), _clean_payload()])
    with pytest.raises(ValidationError):
        _run(gemini, staging_dir)
    assert gemini.extract_pdf.call_count == 1
