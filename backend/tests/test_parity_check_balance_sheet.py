"""Tests del núcleo puro del parity del balance-sheet (Story 9.15 AC1) — sin red ni creds.

Valida la agregación net por cuenta, la comparación con tolerancia y la clasificación de
diffs (TC/pasivo reclasificado a Liabilities = esperado; resto = investigar). La corrida real
contra Sheets+Beancount es QA con data prod (handoff).
"""
from scripts.parity_check_balance_sheet import (
    _snapshot_rows,
    aggregate_balance,
    classify,
    compare,
    main,
)


def _row(acc, debit_balance=0, credit_balance=0):
    return {"account_number": acc, "debit_balance": debit_balance, "credit_balance": credit_balance}


def test_aggregate_net_debit_minus_credit():
    rows = [_row("111005", debit_balance=70000), _row("211005", credit_balance=50000)]
    agg = aggregate_balance(rows)
    assert agg["111005"] == 70000.0
    assert agg["211005"] == -50000.0


def test_compare_flags_diff_and_sorts():
    sheets = {"a": 100.0, "b": 50.0, "c": 10.0}
    bean = {"a": 100.0, "b": 80.0, "c": 1010.0}
    diffs = compare(sheets, bean)
    assert [d["account"] for d in diffs] == ["c", "b"]
    assert diffs[0]["diff"] == 1000 and diffs[1]["diff"] == 30
    assert not any(d["account"] == "a" for d in diffs)


def test_compare_within_tolerance():
    assert compare({"a": 100.0}, {"a": 100.3}) == []


def test_classify_tc_liability_is_expected():
    diffs = [
        {"account": "230001", "sheets": 0, "beancount": -500000, "diff": -500000},  # TC → Liabilities
        {"account": "111005", "sheets": 100, "beancount": 200, "diff": 100},         # banco → inesperado
    ]
    roots = {"230001": "Liabilities", "111005": "Assets"}
    expected, unexpected = classify(diffs, roots)
    assert [d["account"] for d in expected] == ["230001"]
    assert [d["account"] for d in unexpected] == ["111005"]
    assert unexpected[0]["root"] == "Assets"


def test_classify_unknown_root_is_unexpected():
    diffs = [{"account": "999", "sheets": 0, "beancount": 1, "diff": 1}]
    expected, unexpected = classify(diffs, {})
    assert expected == []
    assert unexpected[0]["root"] == ""


# ── Review: snapshot point-in-time + fail-safe del gate ──────────────────────


def test_snapshot_rows_filtra_al_cierre_no_suma_meses():
    # La hoja es multi-snapshot (pk=account+query_date). Sin filtrar, aggregate sumaría ambos
    # meses (100+170) e inflaría el neto vs el point-in-time de Beancount.
    rows = [
        {"account_number": "111005", "query_date": "2026-04-30", "debit_balance": 100, "credit_balance": 0},
        {"account_number": "111005", "query_date": "2026-05-31", "debit_balance": 170, "credit_balance": 0},
    ]
    filtered = _snapshot_rows(rows, "2026-05-31")
    assert aggregate_balance(filtered)["111005"] == 170.0  # solo el cierre pedido, no 270


def test_snapshot_rows_hoja_plana_pasa_igual():
    rows = [{"account_number": "111005", "debit_balance": 100, "credit_balance": 0}]
    assert _snapshot_rows(rows, "2026-05-31") == rows  # sin query_date → sin dimensión de snapshot


def test_main_sin_entities_no_es_un_go(monkeypatch):
    # --entities vacío → el gate NO debe aprobar (exit 2), no exit 0 "Seguro flipear".
    monkeypatch.setattr("sys.argv", ["parity", "--entities", ""])
    assert main() == 2
