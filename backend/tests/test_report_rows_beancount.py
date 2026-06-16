"""Tests for report_rows_via_beancount — migración del reporte a Beancount (#4 / 9.11).

Valida que las filas estilo `ledger_final` derivadas del ledger Beancount tengan la
forma que `report_builder` consume, cubran TODAS las entidades (no filtra por entity),
hagan el split debit/credit por signo, y respeten el rango de fechas. Cierra con una
prueba de integración: las filas alimentan `build_report` y producen un xlsx válido.
"""
from datetime import date

from openpyxl import load_workbook
import io

from backend.app.api.v1.reportes.report_builder import build_report
from backend.app.services.bql_queries import report_rows_via_beancount
from backend.app.services.ledger_service import LedgerService


MINI_LEDGER = """\
option "operating_currency" "CLP"
1900-01-01 commodity CLP

2020-01-01 open Assets:EAG:Bancos:TestBank-111005 CLP
  code: "111005"
  laudus_account_name: "Banco Test EAG"
  laudus_categoria1: "ACTIVO EAG"
  laudus_categoria2: "ACTIVOS CORRIENTES"
  laudus_categoria3: "DISPONIBLE - EAG"
2020-01-01 open Income:EAG:Ventas-411005 CLP
  code: "411005"
2020-01-01 open Expenses:EAG:Gastos-511005 CLP
  code: "511005"
2020-01-01 open Assets:Jocelyn:Bancos:TestBankJ-610005 CLP
  code: "610005"
  laudus_account_name: "Banco Test Jocelyn"

2024-03-15 * "Pago cliente"
  Assets:EAG:Bancos:TestBank-111005   100000 CLP
  Income:EAG:Ventas-411005           -100000 CLP

2024-06-20 * "Compra insumos"
  Expenses:EAG:Gastos-511005           30000 CLP
  Assets:EAG:Bancos:TestBank-111005   -30000 CLP

2024-04-10 * "Gasto Jocelyn"
  Assets:Jocelyn:Bancos:TestBankJ-610005   50000 CLP
  Income:EAG:Ventas-411005                -50000 CLP
"""

# Las claves mínimas que report_builder lee de cada fila.
ROW_KEYS = {"date", "accountnumber", "accountName",
            "Categoria1", "Categoria2", "Categoria3", "debit", "credit"}


def _ledger(tmp_path):
    main = tmp_path / "main.beancount"
    main.write_text(MINI_LEDGER, encoding="utf-8")
    return LedgerService(str(main))


def test_rows_carry_report_builder_keys(tmp_path):
    rows = report_rows_via_beancount(_ledger(tmp_path))
    assert rows
    for r in rows:
        assert ROW_KEYS <= set(r.keys())


def test_includes_all_entities_no_entity_filter(tmp_path):
    """A diferencia de ledger_entries_via_beancount, NO filtra por entity:
    EAG y las hijas conviven (el reporte agrega sobre todas)."""
    rows = report_rows_via_beancount(_ledger(tmp_path))
    numbers = {r["accountnumber"] for r in rows}
    assert "111005" in numbers   # EAG
    assert "610005" in numbers   # Jocelyn


def test_debit_credit_split_by_sign(tmp_path):
    """Posting positivo → debit; negativo → credit. Es el signo que report_builder
    convierte en monto ((de-cr) gasto/activo, (cr-de) ingreso)."""
    rows = report_rows_via_beancount(_ledger(tmp_path))
    # El cargo al banco (+100000) y el ingreso contrapartida (-100000) del 2024-03-15.
    bank_in = next(r for r in rows if r["accountnumber"] == "111005" and r["date"] == "2024-03-15")
    assert bank_in["debit"] == 100000.0 and bank_in["credit"] == 0.0
    income = next(r for r in rows if r["accountnumber"] == "411005" and r["date"] == "2024-03-15")
    assert income["credit"] == 100000.0 and income["debit"] == 0.0


def test_date_range_bounds_rows(tmp_path):
    """date_from/date_to acotan los postings devueltos."""
    rows = report_rows_via_beancount(_ledger(tmp_path), date_from="2024-05-01")
    dates = {r["date"] for r in rows}
    assert dates == {"2024-06-20"}            # solo la compra de insumos
    rows2 = report_rows_via_beancount(_ledger(tmp_path), date_from="2024-04-01", date_to="2024-04-30")
    assert {r["date"] for r in rows2} == {"2024-04-10"}


def test_metadata_join_and_fallbacks(tmp_path):
    """accountnumber=code, categorías desde el Open; sin meta → accountName cae al
    nombre de cuenta y categorías quedan ''."""
    rows = report_rows_via_beancount(_ledger(tmp_path))
    bank = next(r for r in rows if r["accountnumber"] == "111005")
    assert bank["accountName"] == "Banco Test EAG"
    assert bank["Categoria1"] == "ACTIVO EAG"
    income = next(r for r in rows if r["accountnumber"] == "411005")
    assert income["Categoria1"] == ""        # el Open de Income no trae categoría
    assert income["accountName"]             # cae al nombre de cuenta, no vacío


def test_rows_feed_build_report(tmp_path):
    """Integración: las filas derivadas de Beancount alimentan build_report y
    producen un xlsx válido (mismo contrato que el path Sheets)."""
    rows = report_rows_via_beancount(_ledger(tmp_path))
    data = build_report(date(2024, 1, 1), date(2024, 12, 31), lambda _name: rows)
    assert isinstance(data, bytes) and data[:2] == b"PK"   # firma ZIP/xlsx
    wb = load_workbook(io.BytesIO(data))
    assert wb.active.title == "Reporte"
