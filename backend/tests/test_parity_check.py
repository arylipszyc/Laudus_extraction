"""Tests del núcleo puro del parity check (Story 9.11 AC1) — sin red ni creds.

Valida la agregación por (cuenta, mes) con la convención de signo del reporte y la
comparación con tolerancia. La corrida real contra Sheets+Beancount es QA con data prod.
"""
from scripts.parity_check_sheets_vs_beancount import aggregate, compare


def _row(acc, date, cat1="", debit=0, credit=0):
    return {"accountnumber": acc, "date": date, "Categoria1": cat1,
            "debit": debit, "credit": credit}


def test_aggregate_sign_income_vs_expense():
    rows = [
        _row("411005", "2026-01-15", "INGRESOS EAG", credit=100000),   # ingreso → cr-de
        _row("511005", "2026-01-20", "GASTOS EAG", debit=30000),       # gasto → de-cr
    ]
    agg = aggregate(rows)
    assert agg[("411005", "2026-01")] == 100000.0
    assert agg[("511005", "2026-01")] == 30000.0


def test_aggregate_buckets_by_month():
    rows = [
        _row("511005", "2026-01-20", "GASTOS", debit=30000),
        _row("511005", "2026-02-10", "GASTOS", debit=5000),
    ]
    agg = aggregate(rows)
    assert agg[("511005", "2026-01")] == 30000.0
    assert agg[("511005", "2026-02")] == 5000.0


def test_aggregate_range_filter_inclusive():
    rows = [
        _row("511005", "2026-01-20", "GASTOS", debit=30000),
        _row("511005", "2026-02-10", "GASTOS", debit=5000),
        _row("511005", "2026-03-10", "GASTOS", debit=7000),
    ]
    agg = aggregate(rows, ym_from="2026-02", ym_to="2026-02")
    assert dict(agg) == {("511005", "2026-02"): 5000.0}


def test_aggregate_skips_unparseable_date():
    rows = [_row("511005", "no-date", "GASTOS", debit=30000)]
    assert dict(aggregate(rows)) == {}


def test_compare_flags_real_diff_and_sorts():
    sheets = {("a", "2026-01"): 100.0, ("b", "2026-01"): 50.0, ("c", "2026-01"): 10.0}
    bean = {("a", "2026-01"): 100.0, ("b", "2026-01"): 80.0, ("c", "2026-01"): 1010.0}
    diffs = compare(sheets, bean)
    assert [d["account"] for d in diffs] == ["c", "b"]   # ordenado por |diff| desc
    assert diffs[0]["diff"] == 1000 and diffs[1]["diff"] == 30
    assert not any(d["account"] == "a" for d in diffs)   # iguales no aparecen


def test_compare_ignores_within_tolerance():
    assert compare({("a", "m"): 100.0}, {("a", "m"): 100.3}) == []


def test_compare_missing_key_one_side():
    # cuenta presente solo en Beancount = diff completo (Sheets aporta 0)
    diffs = compare({}, {("x", "2026-01"): 500.0})
    assert diffs == [{"account": "x", "month": "2026-01", "sheets": 0, "beancount": 500, "diff": 500}]
