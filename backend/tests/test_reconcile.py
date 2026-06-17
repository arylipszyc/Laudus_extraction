"""Tests de discrepancy_writer + process_match_result — Story 9.6b AC4/AC5/AC7/AC3."""
from datetime import date
from decimal import Decimal

from pipeline.importers.discrepancy_writer import append_discrepancy, append_resolution, build_discrepancy
from pipeline.importers.fx_calculator import FXResult
from pipeline.importers.matching_engine import CartolaLine, LaudusEntry, MatchResult
from pipeline.importers.reconcile import process_match_result

TS = "2026-05-05T14:30:00Z"


def _mr(state, cl=True, le=True):
    cartola = CartolaLine(12, date(2026, 4, 15), Decimal("-45000"), "CLP", "JUMBO") if cl else None
    laudus = LaudusEntry("12345", date(2026, 4, 15), Decimal("-47000"), "Jumbo Costanera") if le else None
    return MatchResult(state, cartola, laudus, 1.0, "")


def _decide(state, fx=None, cl=True, le=True):
    return process_match_result(_mr(state, cl, le), fx, batch_id="b1", bank_account_id="acc1", ts=TS)


# ── AC4: comportamiento por estado ───────────────────────────────────────────


def test_perfect_emite_sin_discrepancia():
    d = _decide("perfect")
    assert d.emit is True and d.flag == "*" and d.discrepancies == []


def test_value_mismatch_no_emite_solo_discrepancia():
    d = _decide("value-mismatch")
    assert d.emit is False and d.flag is None
    assert len(d.discrepancies) == 1 and d.discrepancies[0]["state"] == "value-mismatch"


def test_missing_in_laudus_emite_flag_bang():
    d = _decide("missing-in-laudus", le=False)
    assert d.emit is True and d.flag == "!"
    assert d.discrepancies[0]["state"] == "missing-in-laudus"


def test_date_mismatch_emite_con_discrepancia():
    d = _decide("date-mismatch")
    assert d.emit is True and d.flag == "!"
    assert d.discrepancies[0]["state"] == "date-mismatch"


# ── AC3: overlay FX ───────────────────────────────────────────────────────────


def test_fx_out_of_tolerance_sobre_perfect_fuerza_flag_y_discrepancia_fx():
    fx = FXResult(implied=Decimal("1100"), bcch=Decimal("950"), deviation_pct=Decimal("15.8"),
                  state="fx-out-of-tolerance")
    d = _decide("perfect", fx=fx)
    assert d.emit is True and d.flag == "!"
    assert [x["state"] for x in d.discrepancies] == ["fx-out-of-tolerance"]
    assert d.discrepancies[0]["fx"]["deviation_pct"] == 15.8


def test_fx_bcch_missing_agrega_discrepancia():
    fx = FXResult(implied=Decimal("950"), bcch=None, deviation_pct=None, state="fx-bcch-missing")
    d = _decide("date-mismatch", fx=fx)
    assert d.flag == "!"
    assert sorted(x["state"] for x in d.discrepancies) == ["date-mismatch", "fx-bcch-missing"]


# ── AC5/AC7: JSONL append + dedup ─────────────────────────────────────────────


def test_append_y_dedup(tmp_path):
    p = tmp_path / "cartola-discrepancies.jsonl"
    disc = build_discrepancy(batch_id="b1", bank_account_id="acc1", state="value-mismatch", ts=TS,
                             cartola={"line_no": 12}, laudus={"journal_entry_id": "12345"})
    assert append_discrepancy(disc, p) is True
    # Re-correr con la MISMA clave (batch, line_no, je_id) no duplica.
    disc2 = build_discrepancy(batch_id="b1", bank_account_id="acc1", state="value-mismatch", ts=TS,
                              cartola={"line_no": 12}, laudus={"journal_entry_id": "12345"})
    assert append_discrepancy(disc2, p) is False
    assert len(p.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_resolution_se_appendea_sin_reescribir(tmp_path):
    p = tmp_path / "cartola-discrepancies.jsonl"
    disc = build_discrepancy(batch_id="b1", bank_account_id="acc1", state="value-mismatch", ts=TS,
                             cartola={"line_no": 1}, laudus={"journal_entry_id": "9"})
    append_discrepancy(disc, p)
    append_resolution(disc["discrepancy_id"],
                      {"action": "accept-laudus", "resolved_by": "ary", "resolved_at": TS, "justification": "ok"},
                      p)
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    # Una resolución nueva con la misma clave NO bloquea (la resolución no es discrepancia original).
    disc_b = build_discrepancy(batch_id="b2", bank_account_id="acc1", state="date-mismatch", ts=TS,
                               cartola={"line_no": 1}, laudus={"journal_entry_id": "9"})
    assert append_discrepancy(disc_b, p) is True  # distinto batch → distinta clave
