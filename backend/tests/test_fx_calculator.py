"""Tests del fx_calculator — Story 9.6b AC2/AC3."""
import json
from decimal import Decimal

from pipeline.importers.fx_calculator import calculate_fx, lookup_bcch


def test_fx_in_tolerance():
    r = calculate_fx(Decimal("-100"), Decimal("-95045"), Decimal("948.20"))
    assert r.implied == Decimal("950.45")
    assert r.deviation_pct == Decimal("0.24")
    assert r.state is None
    assert r.out_of_tolerance is False


def test_fx_out_of_tolerance():
    # implied = 110000/100 = 1100; bcch 950 → desviación ~15.8% > 5%
    r = calculate_fx(Decimal("-100"), Decimal("-110000"), Decimal("950"))
    assert r.state == "fx-out-of-tolerance"
    assert r.out_of_tolerance is True


def test_fx_bcch_missing():
    r = calculate_fx(Decimal("100"), Decimal("95000"), None)
    assert r.state == "fx-bcch-missing"
    assert r.implied == Decimal("950.00")
    assert r.deviation_pct is None


def test_fx_usd_cero_es_implausible():
    r = calculate_fx(Decimal("0"), Decimal("95000"), Decimal("950"))
    assert r.state == "fx-implausible"
    assert r.implied is None


def test_fx_implausible_rate():
    # 100 USD vs 500000 CLP → implied 5000 > 2000 → sospechoso
    r = calculate_fx(Decimal("100"), Decimal("500000"), Decimal("950"))
    assert r.state == "fx-implausible"


def test_lookup_bcch(tmp_path):
    p = tmp_path / "fx-bcch-eom.jsonl"
    p.write_text(
        json.dumps({"year_month": "2026-03", "rate_clp_per_usd": 930.5}) + "\n"
        + json.dumps({"year_month": "2026-04", "rate_clp_per_usd": 948.2}) + "\n",
        encoding="utf-8",
    )
    assert lookup_bcch(p, "2026-04") == Decimal("948.2")
    assert lookup_bcch(p, "2026-03") == Decimal("930.5")
    assert lookup_bcch(p, "2026-05") is None


def test_lookup_bcch_missing_file(tmp_path):
    assert lookup_bcch(tmp_path / "nope.jsonl", "2026-04") is None
