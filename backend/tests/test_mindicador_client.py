"""Tests para pipeline.integrations.mindicador_client — Story 9.10."""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import requests

from pipeline.integrations.mindicador_client import (
    MindicadorError,
    fetch_dolar_observado,
)


def _mock_response(status_code=200, json_payload=None, raise_for_status=False):
    resp = MagicMock()
    resp.status_code = status_code
    if raise_for_status:
        resp.raise_for_status.side_effect = requests.HTTPError("boom")
    else:
        resp.raise_for_status.return_value = None
    resp.json.return_value = json_payload or {}
    return resp


class TestFetchDolarObservado:
    def test_returns_rate_when_publication_exists(self):
        payload = {
            "version": "1.7.0",
            "serie": [{"fecha": "2026-04-30T00:00:00.000Z", "valor": 950.45}],
        }
        with patch("pipeline.integrations.mindicador_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(json_payload=payload)
            rate = fetch_dolar_observado(date(2026, 4, 30))
        assert rate == 950.45

    def test_returns_none_when_serie_is_empty(self):
        with patch("pipeline.integrations.mindicador_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(json_payload={"version": "1", "serie": []})
            rate = fetch_dolar_observado(date(2026, 5, 2))  # un sábado
        assert rate is None

    def test_returns_none_when_serie_lacks_target_date(self):
        # mindicador a veces devuelve la serie del mes incluso si el día puntual no existe
        payload = {
            "version": "1",
            "serie": [
                {"fecha": "2026-04-29T00:00:00.000Z", "valor": 949.00},
                {"fecha": "2026-04-28T00:00:00.000Z", "valor": 948.50},
            ],
        }
        with patch("pipeline.integrations.mindicador_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(json_payload=payload)
            rate = fetch_dolar_observado(date(2026, 4, 30))
        assert rate is None

    def test_url_uses_dd_mm_yyyy_format(self):
        with patch("pipeline.integrations.mindicador_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(json_payload={"serie": []})
            fetch_dolar_observado(date(2026, 4, 5))
        called_url = mock_get.call_args[0][0]
        assert called_url.endswith("/05-04-2026")

    def test_retries_then_succeeds(self):
        payload = {"serie": [{"fecha": "2026-04-30T00:00:00.000Z", "valor": 950.0}]}
        with patch("pipeline.integrations.mindicador_client.requests.get") as mock_get, \
             patch("pipeline.integrations.mindicador_client.time.sleep"):
            mock_get.side_effect = [
                requests.ConnectionError("net"),
                _mock_response(json_payload=payload),
            ]
            rate = fetch_dolar_observado(date(2026, 4, 30))
        assert rate == 950.0
        assert mock_get.call_count == 2

    def test_raises_after_three_failures(self):
        with patch("pipeline.integrations.mindicador_client.requests.get") as mock_get, \
             patch("pipeline.integrations.mindicador_client.time.sleep"):
            mock_get.side_effect = requests.ConnectionError("net down")
            with pytest.raises(MindicadorError):
                fetch_dolar_observado(date(2026, 4, 30))
        assert mock_get.call_count == 3

    def test_raises_on_unexpected_schema(self):
        with patch("pipeline.integrations.mindicador_client.requests.get") as mock_get, \
             patch("pipeline.integrations.mindicador_client.time.sleep"):
            mock_get.return_value = _mock_response(json_payload={"unexpected": "shape"})
            with pytest.raises(MindicadorError, match="serie"):
                fetch_dolar_observado(date(2026, 4, 30))

    def test_raises_when_valor_not_numeric(self):
        payload = {
            "serie": [{"fecha": "2026-04-30T00:00:00.000Z", "valor": "not-a-number"}],
        }
        with patch("pipeline.integrations.mindicador_client.requests.get") as mock_get, \
             patch("pipeline.integrations.mindicador_client.time.sleep"):
            mock_get.return_value = _mock_response(json_payload=payload)
            with pytest.raises(MindicadorError, match="numérico"):
                fetch_dolar_observado(date(2026, 4, 30))
