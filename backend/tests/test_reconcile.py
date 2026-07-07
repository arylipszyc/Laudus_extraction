"""Tests de discrepancy_writer + process_match_result — Story 9.6b AC4/AC5/AC7/AC3."""
import json
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
    assert d.discrepancies[0]["source"] == "cartola"  # AC4: la cartola tiene el dato


def test_missing_in_cartola_no_emite_source_laudus():
    # Decisión Ary 2026-06-17: la cartola es la fuente de verdad → no se contabiliza el
    # asiento que solo está en Laudus; solo discrepancia (source=laudus) para que 9.12 lo borre.
    d = _decide("missing-in-cartola", cl=False)
    assert d.emit is False and d.flag is None
    assert len(d.discrepancies) == 1
    assert d.discrepancies[0]["state"] == "missing-in-cartola"
    assert d.discrepancies[0]["source"] == "laudus"


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
    # Re-correr con la MISMA clave de contenido (cuenta, mes, line_no, je_id, state) no duplica.
    disc2 = build_discrepancy(batch_id="b1", bank_account_id="acc1", state="value-mismatch", ts=TS,
                              cartola={"line_no": 12}, laudus={"journal_entry_id": "12345"})
    assert append_discrepancy(disc2, p) is False
    assert len(p.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_state_y_fx_discrepancia_coexisten_al_persistir(tmp_path):
    # Misma (batch, line_no, je_id) pero distinto state: la discrepancia FX NO debe pisar a la
    # de estado al persistir (la dedup key ahora incluye state).
    p = tmp_path / "cartola-discrepancies.jsonl"
    fx = FXResult(implied=Decimal("1100"), bcch=Decimal("950"), deviation_pct=Decimal("15.8"),
                  state="fx-out-of-tolerance")
    d = _decide("date-mismatch", fx=fx)
    assert [append_discrepancy(x, p) for x in d.discrepancies] == [True, True]
    states = sorted(json.loads(l)["state"] for l in p.read_text(encoding="utf-8").splitlines() if l.strip())
    assert states == ["date-mismatch", "fx-out-of-tolerance"]


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
    assert append_discrepancy(disc_b, p) is True  # distinto STATE → distinta clave (el batch ya no participa)


def test_append_discrepancies_batch_una_lectura_y_mismo_dedup(tmp_path, monkeypatch):
    """Review 2026-07-06 D5: el batch lee el JSONL UNA vez y deduplica igual que el loop
    de append_discrepancy (vs disco e intra-batch); re-corrida no duplica."""
    from pipeline.importers import discrepancy_writer as dw

    p = tmp_path / "disc.jsonl"
    d1 = build_discrepancy(batch_id="b1", bank_account_id="acc1", state="value-mismatch", ts=TS,
                           cartola={"line_no": 1}, laudus={"journal_entry_id": "9"})
    d2 = build_discrepancy(batch_id="b1", bank_account_id="acc1", state="date-mismatch", ts=TS,
                           cartola={"line_no": 2}, laudus={"journal_entry_id": "10"})
    d2_dup = build_discrepancy(batch_id="b1", bank_account_id="acc1", state="date-mismatch", ts=TS,
                               cartola={"line_no": 2}, laudus={"journal_entry_id": "10"})

    reads = {"n": 0}
    real = dw._existing_dedup_keys

    def counting(path):
        reads["n"] += 1
        return real(path)

    monkeypatch.setattr(dw, "_existing_dedup_keys", counting)

    # Batch con un duplicado intra-batch → escribe 2, lee el archivo 1 vez.
    assert dw.append_discrepancies([d1, d2, d2_dup], p) == 2
    assert reads["n"] == 1
    # Re-corrida del mismo batch → 0 nuevas (dedup vs disco).
    assert dw.append_discrepancies([d1, d2], p) == 0
    # El archivo quedó bien formado: 2 líneas JSON parseables.
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    import json as _json
    parsed = [_json.loads(l) for l in lines]  # lanza si alguna línea quedó malformada
    assert [x["state"] for x in parsed] == ["value-mismatch", "date-mismatch"]
    # B4 (review 2026-07-06): re-upload = batch_id NUEVO pero mismo contenido → NO duplica
    # (la clave vieja llevaba batch_id y cada re-subida duplicaba las discrepancias abiertas).
    d3 = build_discrepancy(batch_id="b2", bank_account_id="acc1", state="value-mismatch", ts=TS,
                           cartola={"line_no": 1}, laudus={"journal_entry_id": "9"})
    assert append_discrepancy(d3, p) is False
    # Contenido realmente distinto (otro mes) sí entra:
    d4 = build_discrepancy(batch_id="b2", bank_account_id="acc1", state="value-mismatch", ts=TS,
                           cartola={"line_no": 1}, laudus={"journal_entry_id": "9"},
                           year_month="2026-05")
    assert append_discrepancy(d4, p) is True


def test_dedup_reupload_mismo_mes_no_duplica_estados_distintos_si(tmp_path):
    """B4: la clave de dedup es identidad de contenido (cuenta, mes, línea, je, estado) —
    re-subir la misma cartola no duplica, pero estados DISTINTOS de la misma línea
    coexisten (regresión 9.6b: la disc de FX no pisa la de estado)."""
    p = tmp_path / "d.jsonl"
    base = dict(bank_account_id="acc1", ts=TS, cartola={"line_no": 7},
                laudus={"journal_entry_id": "42"}, year_month="2026-04")
    d1 = build_discrepancy(batch_id="upload-1", state="value-mismatch", **base)
    assert append_discrepancy(d1, p) is True
    # Re-upload: batch nuevo, mismo contenido → dedup.
    d2 = build_discrepancy(batch_id="upload-2", state="value-mismatch", **base)
    assert append_discrepancy(d2, p) is False
    # Mismo par línea/je pero OTRO estado (fx-out-of-tolerance) → entra.
    d3 = build_discrepancy(batch_id="upload-2", state="fx-out-of-tolerance", **base)
    assert append_discrepancy(d3, p) is True
