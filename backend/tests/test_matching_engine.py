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


# ── Performance sin cambio de resultados (review 2026-07-06 D3/D4a) ──────────


def test_load_laudus_entries_no_parsea_meses_fuera_del_periodo(tmp_path):
    """D4a: los archivos `YYYY-MM.beancount` fuera del rango de meses del período NO se
    parsean. Prueba: un archivo de mes lejano contiene una tx fechada DENTRO del período —
    si se parseara, el filtro por fecha la dejaría pasar; con el filtro por filename, no
    aparece. Un stem no conforme (`laudus.beancount`) se parsea igual (fallback)."""
    d = tmp_path / "laudus"
    d.mkdir()
    tx = ('2026-04-15 * "EN PERIODO"\n'
          '  Assets:EAG:Bancos:Test  -45000 CLP\n'
          '  Expenses:EAG:Varios      45000 CLP\n')
    (d / "2026-04.beancount").write_text(tx, encoding="utf-8")
    # Mes lejano con una tx EN el período (solo visible si el archivo se parsea):
    (d / "2020-01.beancount").write_text(tx.replace("EN PERIODO", "COLADA"), encoding="utf-8")
    # Stem no conforme → se parsea (conservador):
    (d / "laudus.beancount").write_text(tx.replace("EN PERIODO", "NO-CONFORME"), encoding="utf-8")

    out = load_laudus_entries(d, "Assets:EAG:Bancos:Test",
                              date(2026, 3, 29), date(2026, 5, 3))
    descs = sorted(e.description for e in out)
    assert descs == ["EN PERIODO", "NO-CONFORME"]  # sin "COLADA": 2020-01 no se parseó


def test_load_laudus_entries_padding_cruza_anio(tmp_path):
    """D4a: padding que cruza de enero al diciembre del año ANTERIOR — la comparación
    lexicográfica de stems ISO también ordena bien entre años."""
    d = tmp_path / "laudus"
    d.mkdir()
    tx = ('2025-12-30 * "FIN DE ANIO"\n'
          '  Assets:EAG:Bancos:Test  -1000 CLP\n'
          '  Expenses:EAG:Varios      1000 CLP\n')
    (d / "2025-12.beancount").write_text(tx, encoding="utf-8")
    (d / "2025-06.beancount").write_text(tx.replace("2025-12-30", "2025-06-15"), encoding="utf-8")
    out = load_laudus_entries(d, "Assets:EAG:Bancos:Test",
                              date(2025, 12, 29), date(2026, 2, 3))
    assert [e.description for e in out] == ["FIN DE ANIO"]  # 2025-06 filtrado, 2025-12 incluido


def test_load_laudus_entries_padding_cruza_mes(tmp_path):
    """D4a: el padding ±3d que cruza al mes anterior incluye ese archivo."""
    d = tmp_path / "laudus"
    d.mkdir()
    (d / "2026-03.beancount").write_text(
        '2026-03-30 * "BORDE"\n'
        '  Assets:EAG:Bancos:Test  -1000 CLP\n'
        '  Expenses:EAG:Varios      1000 CLP\n', encoding="utf-8")
    out = load_laudus_entries(d, "Assets:EAG:Bancos:Test",
                              date(2026, 3, 29), date(2026, 5, 3))
    assert [e.description for e in out] == ["BORDE"]


def test_match_computa_similitud_a_lo_mas_una_vez_por_par(monkeypatch):
    """D3: SequenceMatcher corre ≤1 vez por par (antes: 2-3 veces vía
    _acceptable/_score/_classify), y con candidatos de monto exacto ni se computa
    la similitud de los que no lo son."""
    import difflib as _difflib

    from pipeline.importers import matching_engine as mod

    calls: list[tuple] = []
    real = _difflib.SequenceMatcher

    class Counting(real):
        def __init__(self, isjunk, a, b, *args, **kwargs):
            calls.append((a, b))
            super().__init__(isjunk, a, b, *args, **kwargs)

    monkeypatch.setattr(mod.difflib, "SequenceMatcher", Counting)

    lines = [_cl(line_no=1, desc="JUMBO COMPRA"), _cl(line_no=2, desc="LIDER COMPRA", amount="-9999")]
    entries = [_le(je="1", desc="JUMBO COMPRA"), _le(je="2", desc="OTRA COSA"),
               _le(je="3", desc="LIDER", amount="-9999")]
    r = match(lines, entries, period_start=P2026)

    # Exactamente 3: línea 1 rankea sus 2 amount-matches (e1,e2); línea 2 clasifica su
    # único candidato (e3). Los amount-no-match jamás pasan por SequenceMatcher.
    assert len(calls) == 3, f"{len(calls)} corridas de SequenceMatcher (esperadas 3)"
    assert len(calls) == len(set(calls)), "similitud recomputada para el mismo par"
    # Los resultados siguen siendo los de siempre, incluidos los GANADORES por línea:
    assert _states(r) == ["perfect", "description-mismatch", "missing-in-cartola"]
    assert r[0].laudus_entry.je_id == "1"   # JUMBO ganó sobre OTRA COSA (sim)
    assert r[1].laudus_entry.je_id == "3"   # único amount-match de la línea 2
    assert r[2].laudus_entry.je_id == "2"   # el sobrante
