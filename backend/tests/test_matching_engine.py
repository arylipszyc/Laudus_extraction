"""Tests del MatchingEngine — Story 9.6b AC1/AC9 (fixtures por estado)."""
from datetime import date
from decimal import Decimal

from pipeline.importers.matching_engine import (
    CartolaLine,
    LaudusEntry,
    load_laudus_entries,
    match,
)

P2026 = date(2026, 4, 1)
P2024 = date(2024, 4, 1)


def _cl(line_no=1, d="2026-04-15", amount="-45000", currency="CLP", desc="JUMBO", cat=""):
    return CartolaLine(line_no, date.fromisoformat(d), Decimal(amount), currency, desc, cat)


def _le(je="1", d="2026-04-15", amount="-45000", desc="JUMBO", cat=""):
    return LaudusEntry(je, date.fromisoformat(d), Decimal(amount), desc, cat)


def _states(results):
    return [r.state for r in results]


def test_perfect_match():
    r = match([_cl()], [_le()], period_start=P2026)
    assert _states(r) == ["perfect"]
    assert r[0].confidence == 1.0


def test_value_mismatch_same_date_desc_distinto_monto():
    r = match([_cl(amount="-45000")], [_le(amount="-47000")], period_start=P2026)
    assert _states(r) == ["value-mismatch"]


def test_missing_in_laudus_sin_candidato():
    r = match([_cl(d="2026-04-15")], [_le(d="2026-04-25")], period_start=P2026)  # fuera de ±3d
    # la cartola queda sin match y el Laudus de otra fecha queda sobrante
    assert sorted(_states(r)) == ["missing-in-cartola", "missing-in-laudus"]


def test_missing_in_cartola_laudus_sobrante():
    r = match([], [_le()], period_start=P2026)
    assert _states(r) == ["missing-in-cartola"]


def test_date_mismatch_dentro_de_tolerancia():
    r = match([_cl(d="2026-04-15")], [_le(d="2026-04-13")], period_start=P2026)
    assert _states(r) == ["date-mismatch"]


def test_description_mismatch():
    r = match([_cl(desc="JUMBO MAIPU")], [_le(desc="Farmacia Ahumada")], period_start=P2026)
    # mismo monto + fecha → matchea por monto, pero la desc difiere
    assert _states(r) == ["description-mismatch"]


def test_category_mismatch():
    r = match(
        [_cl(cat="Expenses:EAG:Supermercado")],
        [_le(cat="Expenses:EAG:Farmacia")],
        period_start=P2026,
    )
    assert _states(r) == ["category-mismatch"]


def test_usd_matchea_por_fecha_y_desc_no_por_monto():
    # USD en cartola vs CLP en Laudus: no se compara monto; matchea por fecha+desc.
    cl = _cl(amount="-100.00", currency="USD", desc="Amazon")
    le = _le(amount="-95045", desc="Amazon")
    r = match([cl], [le], period_start=P2026)
    assert _states(r) == ["perfect"]


def test_pre_2026_usd_se_trata_como_clp():
    # AC9: antes de 2026 no hay era FX → el "USD" se compara como monto CLP (no matchea) → value/missing.
    cl = _cl(d="2024-04-15", amount="-100.00", currency="USD", desc="Amazon")
    le = _le(d="2024-04-15", amount="-95045", desc="Amazon")
    r = match([cl], [le], period_start=P2024)
    # mismo desc+fecha pero monto distinto (100 vs 95045) → value-mismatch (no se ignora el monto)
    assert _states(r) == ["value-mismatch"]


def test_greedy_no_reusa_laudus():
    # dos líneas de cartola, un solo Laudus → una matchea, la otra queda missing-in-laudus
    r = match([_cl(line_no=1), _cl(line_no=2)], [_le()], period_start=P2026)
    assert sorted(_states(r)) == ["missing-in-laudus", "perfect"]


def test_load_laudus_entries_filtra_por_cuenta_y_periodo(tmp_path):
    (tmp_path / "2026-04.beancount").write_text(
        '2026-04-10 * "JUMBO"\n'
        '  id: "J1"\n'
        "  Liabilities:EAG:TC:Citi   -45000 CLP\n"
        "  Expenses:EAG:Super         45000 CLP\n\n"
        '2026-04-12 * "otra cuenta"\n'
        '  id: "J2"\n'
        "  Assets:EAG:Bancos:Banco   -1000 CLP\n"
        "  Expenses:EAG:X             1000 CLP\n",
        encoding="utf-8",
    )
    out = load_laudus_entries(tmp_path, "Liabilities:EAG:TC:Citi", date(2026, 4, 1), date(2026, 4, 30))
    assert len(out) == 1
    assert out[0].je_id == "J1"
    assert out[0].amount == Decimal("-45000")
    assert out[0].category_account == "Expenses:EAG:Super"
