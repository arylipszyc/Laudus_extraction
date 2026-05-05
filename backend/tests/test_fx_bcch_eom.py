"""Tests para pipeline.importers.fx_bcch_eom — Story 9.10."""
import json
from datetime import date
from unittest.mock import patch

import pytest

from pipeline.importers.fx_bcch_eom import (
    NoPublicationFoundError,
    RefetchValidationError,
    refetch_eom,
)


# ── Validaciones de input ───────────────────────────────────────────────────

class TestValidations:
    @pytest.mark.parametrize("bad_input", ["", "2026", "2026-1", "2026/04", "abcd-ef", "2026-13", "2026-00"])
    def test_invalid_format_raises(self, bad_input, tmp_path):
        with pytest.raises(RefetchValidationError):
            refetch_eom(bad_input, ledger_path=tmp_path, today=date(2026, 5, 5))

    def test_future_month_raises(self, tmp_path):
        with pytest.raises(RefetchValidationError, match="futuro"):
            refetch_eom("2026-06", ledger_path=tmp_path, today=date(2026, 5, 5))

    def test_current_month_raises(self, tmp_path):
        with pytest.raises(RefetchValidationError, match="mes en curso"):
            refetch_eom("2026-05", ledger_path=tmp_path, today=date(2026, 5, 5))

    def test_past_month_passes_validation(self, tmp_path):
        with patch(
            "pipeline.importers.fx_bcch_eom.fetch_dolar_observado",
            return_value=950.0,
        ):
            result = refetch_eom("2026-04", ledger_path=tmp_path, today=date(2026, 5, 5))
        assert result.status == "fetched"
        assert result.year_month == "2026-04"


# ── Iterador hacia atrás ────────────────────────────────────────────────────

class TestLookbackIterator:
    def test_returns_first_publication_day(self, tmp_path):
        # April 2026: 30 = jueves (publicación). Fetch ese día directo.
        with patch("pipeline.importers.fx_bcch_eom.fetch_dolar_observado") as mock_fetch:
            mock_fetch.return_value = 950.45
            result = refetch_eom("2026-04", ledger_path=tmp_path, today=date(2026, 5, 5))
        assert result.bcch_date == "2026-04-30"
        assert result.rate_clp_per_usd == 950.45
        mock_fetch.assert_called_once_with(date(2026, 4, 30))

    def test_walks_back_when_last_day_has_no_publication(self, tmp_path):
        # Mes que cierra fin de semana: simulamos None para 30, 29, valor para 28.
        def fake_fetch(d):
            if d == date(2026, 4, 28):
                return 948.50
            return None
        with patch(
            "pipeline.importers.fx_bcch_eom.fetch_dolar_observado",
            side_effect=fake_fetch,
        ):
            result = refetch_eom("2026-04", ledger_path=tmp_path, today=date(2026, 5, 5))
        assert result.bcch_date == "2026-04-28"
        assert result.rate_clp_per_usd == 948.50

    def test_raises_when_seven_days_have_no_publication(self, tmp_path):
        with patch(
            "pipeline.importers.fx_bcch_eom.fetch_dolar_observado",
            return_value=None,
        ):
            with pytest.raises(NoPublicationFoundError):
                refetch_eom("2026-04", ledger_path=tmp_path, today=date(2026, 5, 5))

    def test_february_uses_correct_last_day(self, tmp_path):
        # 2026 no es bisiesto; febrero termina el 28
        with patch("pipeline.importers.fx_bcch_eom.fetch_dolar_observado") as mock_fetch:
            mock_fetch.return_value = 920.0
            result = refetch_eom("2026-02", ledger_path=tmp_path, today=date(2026, 5, 5))
        assert result.bcch_date == "2026-02-28"


# ── Persistencia + dedup ────────────────────────────────────────────────────

class TestPersistence:
    def test_appends_new_entry_to_jsonl(self, tmp_path):
        with patch("pipeline.importers.fx_bcch_eom.fetch_dolar_observado", return_value=950.45):
            refetch_eom("2026-04", ledger_path=tmp_path, today=date(2026, 5, 5))
        jsonl = tmp_path / "_meta" / "fx-bcch-eom.jsonl"
        assert jsonl.exists()
        lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["schema_version"] == "1.0"
        assert record["year_month"] == "2026-04"
        assert record["rate_clp_per_usd"] == 950.45
        assert record["source"] == "mindicador-dolar-observado"
        assert record["bcch_date"] == "2026-04-30"
        assert "fetched_at" in record

    def test_dedup_returns_existing_without_refetch(self, tmp_path):
        with patch("pipeline.importers.fx_bcch_eom.fetch_dolar_observado", return_value=950.45):
            refetch_eom("2026-04", ledger_path=tmp_path, today=date(2026, 5, 5))
        # Segunda llamada — fetch no debe ser invocado
        with patch("pipeline.importers.fx_bcch_eom.fetch_dolar_observado") as mock_fetch:
            result = refetch_eom("2026-04", ledger_path=tmp_path, today=date(2026, 5, 5))
        assert result.status == "skipped"
        assert result.rate_clp_per_usd == 950.45
        mock_fetch.assert_not_called()
        # JSONL sigue teniendo una sola línea
        jsonl = tmp_path / "_meta" / "fx-bcch-eom.jsonl"
        lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1

    def test_two_distinct_months_produce_two_lines(self, tmp_path):
        with patch("pipeline.importers.fx_bcch_eom.fetch_dolar_observado", return_value=950.0):
            refetch_eom("2026-03", ledger_path=tmp_path, today=date(2026, 5, 5))
            refetch_eom("2026-04", ledger_path=tmp_path, today=date(2026, 5, 5))
        jsonl = tmp_path / "_meta" / "fx-bcch-eom.jsonl"
        lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        months = {json.loads(line)["year_month"] for line in lines}
        assert months == {"2026-03", "2026-04"}

    def test_creates_meta_directory_if_missing(self, tmp_path):
        # tmp_path no tiene _meta/
        with patch("pipeline.importers.fx_bcch_eom.fetch_dolar_observado", return_value=950.0):
            refetch_eom("2026-04", ledger_path=tmp_path, today=date(2026, 5, 5))
        assert (tmp_path / "_meta").is_dir()

    def test_skips_malformed_lines_when_searching_for_dedup(self, tmp_path):
        meta = tmp_path / "_meta"
        meta.mkdir(parents=True)
        jsonl = meta / "fx-bcch-eom.jsonl"
        jsonl.write_text(
            "garbage-not-json\n"
            + json.dumps({"year_month": "2026-04", "rate_clp_per_usd": 950.0,
                          "bcch_date": "2026-04-30", "source": "x"}) + "\n",
            encoding="utf-8",
        )
        with patch("pipeline.importers.fx_bcch_eom.fetch_dolar_observado") as mock_fetch:
            result = refetch_eom("2026-04", ledger_path=tmp_path, today=date(2026, 5, 5))
        assert result.status == "skipped"
        mock_fetch.assert_not_called()
