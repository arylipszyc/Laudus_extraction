"""Tests for GeminiClient — Story 9.5 Task 2.

Real Gemini calls are NOT exercised here (smoke test runs locally with API key).
These tests cover SDK contract, prompt construction, and error handling.
"""
from unittest.mock import MagicMock, patch

import pytest

from backend.app.integrations.gemini_client import (
    GeminiClient,
    GeminiExtractionError,
    _BankAccountHint,
    _build_prompt,
)


# ── Prompt construction ───────────────────────────────────────────────────


def test_prompt_contains_bank_context():
    hint = _BankAccountHint(
        bank_account_id="abc-123",
        bank_name="BCI",
        account_label="Visa Infinity Eduardo",
        account_type="tarjeta_credito",
        currency="CLP",
        last4="1234",
    )
    prompt = _build_prompt(hint)
    assert "abc-123" in prompt
    assert "BCI" in prompt
    assert "Visa Infinity Eduardo" in prompt
    assert "tarjeta_credito" in prompt
    assert "CLP" in prompt
    assert '"1234"' in prompt


def test_prompt_omits_last4_clause_when_missing():
    hint = _BankAccountHint(
        bank_account_id="x", bank_name="y", account_label="z",
        account_type="cta_corriente", currency="CLP", last4=None,
    )
    prompt = _build_prompt(hint)
    assert "termina en" not in prompt


def test_prompt_documents_sign_rules_for_liability_account():
    """Story 9.5 Moishe re-review: TC = Beancount Liability → compras +, pagos -."""
    hint = _BankAccountHint(
        bank_account_id="x", bank_name="y", account_label="z",
        account_type="tarjeta_credito", currency="CLP", last4=None,
    )
    prompt = _build_prompt(hint)
    assert "PASIVO" in prompt
    assert "INCREMENTA la deuda" in prompt
    assert "DECREMENTA la deuda" in prompt
    # Concrete example must show compra=positive and pago=negative for liability.
    assert "45000.00" in prompt and "-200000.00" in prompt


def test_prompt_documents_sign_rules_for_asset_account():
    """cta_corriente = Beancount Asset → cargos -, abonos +."""
    hint = _BankAccountHint(
        bank_account_id="x", bank_name="y", account_label="z",
        account_type="cta_corriente", currency="CLP", last4=None,
    )
    prompt = _build_prompt(hint)
    assert "ACTIVO" in prompt
    assert "INCREMENTA el saldo" in prompt
    assert "DECREMENTA el saldo" in prompt


def test_prompt_includes_balance_check_invariant():
    hint = _BankAccountHint(
        bank_account_id="x", bank_name="y", account_label="z",
        account_type="tarjeta_credito", currency="CLP", last4=None,
    )
    prompt = _build_prompt(hint)
    assert "closing - balances.opening" in prompt or "closing) - opening" in prompt
    assert "sum(transactions" in prompt


def test_prompt_mandates_inclusion_of_pre_existing_instalments():
    hint = _BankAccountHint(
        bank_account_id="x", bank_name="y", account_label="z",
        account_type="tarjeta_credito", currency="CLP", last4=None,
    )
    prompt = _build_prompt(hint)
    # Cuotas X/N con X≥1 deben incluirse
    assert "X ≥ 1" in prompt
    assert "VALOR CUOTA MENSUAL" in prompt
    assert "(cuota X/N)" in prompt


def test_prompt_mandates_exclusion_of_future_instalments():
    hint = _BankAccountHint(
        bank_account_id="x", bank_name="y", account_label="z",
        account_type="tarjeta_credito", currency="CLP", last4=None,
    )
    prompt = _build_prompt(hint)
    # Cuotas 00/N (X=0) deben excluirse
    assert "X = 0" in prompt or "00/N" in prompt
    assert "FUTURAS" in prompt


def test_prompt_mandates_exclusion_of_subtotals():
    hint = _BankAccountHint(
        bank_account_id="x", bank_name="y", account_label="z",
        account_type="tarjeta_credito", currency="CLP", last4=None,
    )
    prompt = _build_prompt(hint)
    assert "TOTAL TARJETA" in prompt
    assert "MONTO FACTURADO" in prompt


def test_prompt_includes_balance_mismatch_in_post_process_warnings():
    hint = _BankAccountHint(
        bank_account_id="x", bank_name="y", account_label="z",
        account_type="tarjeta_credito", currency="CLP", last4=None,
    )
    prompt = _build_prompt(hint)
    assert "BALANCE_MISMATCH" in prompt


def test_prompt_lists_closed_enums():
    hint = _BankAccountHint(
        bank_account_id="x", bank_name="y", account_label="z",
        account_type="cta_corriente", currency="CLP", last4=None,
    )
    prompt = _build_prompt(hint)
    # All canonical account_type values
    for v in ["tarjeta_credito", "cta_corriente", "cta_vista", "cta_ahorro", "linea_credito"]:
        assert v in prompt
    # All currencies
    assert "CLP" in prompt and "USD" in prompt and "EUR" in prompt


def test_prompt_excludes_post_process_warnings():
    """Backend post-process detects DUPLICATE_LINE/ZERO_AMOUNT/etc — Gemini must NOT."""
    hint = _BankAccountHint(
        bank_account_id="x", bank_name="y", account_label="z",
        account_type="cta_corriente", currency="CLP", last4=None,
    )
    prompt = _build_prompt(hint)
    assert "NO los emitas tú" in prompt or "NO los emitas tu" in prompt


# ── Client construction ──────────────────────────────────────────────────


def test_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        GeminiClient()


def test_client_accepts_explicit_key():
    with patch("google.genai.Client") as mock_genai_client:
        client = GeminiClient(api_key="test-key", model="gemini-2.5-flash")
        assert client.model == "gemini-2.5-flash"
        mock_genai_client.assert_called_once_with(api_key="test-key")


def test_client_reads_env_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    with patch("google.genai.Client") as mock_genai_client:
        GeminiClient()
        mock_genai_client.assert_called_once_with(api_key="env-key")


# ── extract_pdf behaviour with mocked SDK ─────────────────────────────────


def _make_mocked_client(response_text: str) -> GeminiClient:
    fake_response = MagicMock()
    fake_response.text = response_text
    fake_genai_client = MagicMock()
    fake_genai_client.models.generate_content.return_value = fake_response

    with patch("google.genai.Client", return_value=fake_genai_client), \
         patch("google.genai.types") as fake_types:
        fake_types.Part.from_bytes.return_value = "PDF_PART"
        fake_types.GenerateContentConfig.return_value = "CONFIG"
        client = GeminiClient(api_key="x")
        client._fake_genai_client = fake_genai_client  # expose for assertions
        client._fake_types = fake_types
    return client


def test_extract_pdf_parses_valid_json_response():
    client = _make_mocked_client('{"schema_version": "1.0", "transactions": []}')
    result = client.extract_pdf(
        pdf_bytes=b"%PDF-1.4 fake",
        bank_account_id="x", bank_name="y", account_label="z",
        account_type="cta_corriente", currency="CLP", last4=None,
    )
    assert result == {"schema_version": "1.0", "transactions": []}


def test_extract_pdf_raises_on_invalid_json():
    client = _make_mocked_client("not valid json {")
    with pytest.raises(GeminiExtractionError, match="not valid JSON"):
        client.extract_pdf(
            pdf_bytes=b"%PDF-1.4",
            bank_account_id="x", bank_name="y", account_label="z",
            account_type="cta_corriente", currency="CLP", last4=None,
        )


def test_extract_pdf_raises_on_empty_response():
    client = _make_mocked_client("")
    with pytest.raises(GeminiExtractionError):
        client.extract_pdf(
            pdf_bytes=b"%PDF-1.4",
            bank_account_id="x", bank_name="y", account_label="z",
            account_type="cta_corriente", currency="CLP", last4=None,
        )


def test_extract_pdf_passes_pdf_bytes_to_sdk():
    """Verify pdf bytes reach the SDK as a typed Part with the correct mime."""
    fake_response = MagicMock(text='{}')
    fake_genai_client = MagicMock()
    fake_genai_client.models.generate_content.return_value = fake_response
    pdf_bytes = b"%PDF-1.4 hello"

    with patch("google.genai.Client", return_value=fake_genai_client), \
         patch("google.genai.types") as fake_types:
        fake_types.Part.from_bytes.return_value = "PDF_PART"
        fake_types.GenerateContentConfig.return_value = "CONFIG"

        client = GeminiClient(api_key="x", model="gemini-2.5-flash")
        client.extract_pdf(
            pdf_bytes=pdf_bytes,
            bank_account_id="abc", bank_name="BCI", account_label="X",
            account_type="cta_corriente", currency="CLP", last4="0175",
        )

    fake_types.Part.from_bytes.assert_called_once_with(
        data=pdf_bytes, mime_type="application/pdf"
    )
    call = fake_genai_client.models.generate_content.call_args
    assert call.kwargs["model"] == "gemini-2.5-flash"
    contents = call.kwargs["contents"]
    assert len(contents) == 2
    assert "abc" in contents[0]  # prompt has bank_account_id
    assert contents[1] == "PDF_PART"
