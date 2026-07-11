"""Tests for BQL dashboard queries — Story 9.2 AC3/AC4.

Validates the Sheets-compatible SHAPE and basic correctness of the Beancount
engine against a synthetic mini-ledger. Amount parity vs. real Laudus/Sheets
data is covered (xfail) by test_beancount_parity.py.
"""
from backend.app.services.bql_queries import (
    CONSOLIDATION_GROUPS,
    balance_sheet_via_beancount,
    ledger_entries_via_beancount,
)
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
2020-01-01 open Liabilities:EAG:Tarjeta-211005 CLP
  code: "211005"
  laudus_account_name: "Tarjeta EAG"
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

BALANCE_SHEET_KEYS = {
    "account_id", "account_number", "account", "account_name", "debit", "credit",
    "debit_balance", "credit_balance", "query_date", "is_latest",
}
LEDGER_KEYS = {
    "journalentryid", "journalentrynumber", "date", "accountnumber", "lineid",
    "description", "debit", "credit", "currencycode", "paritytomaincurrency",
    "periodo", "accountName", "Categoria1", "Categoria2", "Categoria3", "tx_id",
}


def _ledger(tmp_path):
    main = tmp_path / "main.beancount"
    main.write_text(MINI_LEDGER, encoding="utf-8")
    return LedgerService(str(main))


# ── balance_sheet_via_beancount (AC3) ─────────────────────────────────────────


def test_balance_sheet_shape(tmp_path):
    """AC3: every record carries exactly the Sheets balance-sheet keys."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "EAG")
    assert set(result.keys()) == {"data", "meta"}
    assert "last_sync" in result["meta"]
    for record in result["data"]:
        assert set(record.keys()) == BALANCE_SHEET_KEYS


def test_balance_sheet_exposes_account_root(tmp_path):
    """El frontend agrupa por la raíz contable → `account` (path beancount) debe venir en cada fila."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "EAG")
    by_code = {r["account_number"]: r["account"] for r in result["data"]}
    assert by_code["111005"].startswith("Assets:")  # banco → raíz Assets (Activos)
    assert all(r["account"] for r in result["data"])  # toda fila trae el path


def test_balance_sheet_excludes_income_and_expenses(tmp_path):
    """AC3: balance sheet only includes Assets/Liabilities/Equity, not Income/Expenses."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "EAG")
    numbers = {r["account_number"] for r in result["data"]}
    assert "111005" in numbers          # Assets:EAG appears
    assert "411005" not in numbers      # Income excluded
    assert "511005" not in numbers      # Expenses excluded


def test_balance_sheet_cumulative_balance(tmp_path):
    """AC3: Assets:EAG balance = 100000 - 30000 = 70000 (debit-natured)."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "EAG")
    bank = next(r for r in result["data"] if r["account_number"] == "111005")
    assert bank["debit_balance"] == 70000.0
    assert bank["credit_balance"] == 0.0
    assert bank["account_name"] == "Banco Test EAG"


def test_balance_sheet_as_of_date(tmp_path):
    """AC3: date_to bounds the cumulative balance (AT date_range.end)."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "EAG", date_to="2024-04-01")
    bank = next(r for r in result["data"] if r["account_number"] == "111005")
    assert bank["debit_balance"] == 100000.0  # only the 2024-03-15 tx counts
    assert result["meta"]["last_sync"] == "2024-04-01"


def test_balance_sheet_eag_is_consolidated(tmp_path):
    """EAG es la entidad matriz: su balance-sheet incluye a las hijas (consolidado)."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "EAG")
    numbers = {r["account_number"] for r in result["data"]}
    assert "111005" in numbers  # cuenta propia de EAG
    assert "610005" in numbers  # cuenta de Jocelyn, consolidada bajo EAG


def test_balance_sheet_child_slice_isolated(tmp_path):
    """Seleccionar una hija devuelve SU slice — sin las cuentas propias de EAG."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "Jocelyn")
    numbers = {r["account_number"] for r in result["data"]}
    assert "610005" in numbers      # cuenta de Jocelyn
    assert "111005" not in numbers  # cuenta de EAG excluida


def test_balance_sheet_empty_entity(tmp_path):
    """AC3: an entity with no balance-sheet postings → empty data, null last_sync."""
    result = balance_sheet_via_beancount(_ledger(tmp_path), "Jeannette")
    assert result["data"] == []


# ── ledger_entries_via_beancount (AC4) ────────────────────────────────────────


def test_ledger_entries_shape(tmp_path):
    """AC4: every record carries exactly the Sheets ledger-entry alias keys."""
    result = ledger_entries_via_beancount(_ledger(tmp_path), "EAG")
    assert set(result.keys()) == {"data", "meta"}
    for record in result["data"]:
        assert set(record.keys()) == LEDGER_KEYS


def test_ledger_entries_entity_filter(tmp_path):
    """AC4: only EAG postings returned; Jocelyn's asset posting excluded."""
    result = ledger_entries_via_beancount(_ledger(tmp_path), "EAG")
    numbers = {r["accountnumber"] for r in result["data"]}
    assert "610005" not in numbers
    assert {"111005", "411005", "511005"} <= numbers


def test_ledger_entries_debit_credit_split(tmp_path):
    """AC4: positive number → debit, negative → credit; amounts are floats."""
    result = ledger_entries_via_beancount(_ledger(tmp_path), "EAG", account_number="111005")
    # account 111005 has +100000 (debit) and -30000 (credit)
    debits = sorted(r["debit"] for r in result["data"])
    credits = sorted(r["credit"] for r in result["data"])
    assert 100000.0 in debits
    assert 30000.0 in credits
    for r in result["data"]:
        assert isinstance(r["debit"], float)
        assert isinstance(r["credit"], float)
        assert r["paritytomaincurrency"] == 1.0
        assert r["currencycode"] == "CLP"


def test_ledger_entries_account_number_filter(tmp_path):
    """AC4: account_number filters to that account only."""
    result = ledger_entries_via_beancount(_ledger(tmp_path), "EAG", account_number="111005")
    assert result["data"]
    assert all(r["accountnumber"] == "111005" for r in result["data"])


def test_ledger_entries_date_range(tmp_path):
    """AC4: date_from/date_to bound the postings by date."""
    result = ledger_entries_via_beancount(
        _ledger(tmp_path), "EAG", date_from="2024-06-01", date_to="2024-06-30"
    )
    assert result["data"]
    assert all(r["date"].startswith("2024-06") for r in result["data"])


def test_ledger_entries_last_sync_is_max_date(tmp_path):
    """AC4: meta.last_sync is the most recent posting date."""
    result = ledger_entries_via_beancount(_ledger(tmp_path), "EAG")
    assert result["meta"]["last_sync"] == "2024-06-20"


def test_ledger_entries_categoria_enrichment(tmp_path):
    """AC4: records are enriched with Categoria1..3 from Open metadata."""
    result = ledger_entries_via_beancount(_ledger(tmp_path), "EAG", account_number="111005")
    record = result["data"][0]
    assert record["Categoria1"] == "ACTIVO EAG"
    assert record["accountName"] == "Banco Test EAG"


# ── tx_id por fila (Story 7.1b AC1) ───────────────────────────────────────────


def test_ledger_entries_tx_id_matches_parent_tx(tmp_path):
    """7.1b AC1: cada fila trae el tx_id de la TRANSACCIÓN padre (== _tx_id_of canónico)."""
    from beancount.core.data import Transaction as Txn
    from backend.app.api.v1.transactions.service import _tx_id_of

    ledger = _ledger(tmp_path)
    result = ledger_entries_via_beancount(ledger, "EAG", account_number="511005")
    assert result["data"]
    row = result["data"][0]
    parent = next(e for e in ledger.entries()
                  if isinstance(e, Txn) and e.narration == "Compra insumos")
    assert row["tx_id"] == _tx_id_of(parent)


def test_ledger_entries_tx_id_shared_across_legs(tmp_path):
    """7.1b AC1: una tx con 2 patas visibles bajo EAG → ambas filas comparten tx_id."""
    result = ledger_entries_via_beancount(_ledger(tmp_path), "EAG")
    rows = [r for r in result["data"] if r["description"] == "Compra insumos"]
    assert len(rows) == 2  # pata gasto (511005) + pata banco (111005)
    assert rows[0]["tx_id"] == rows[1]["tx_id"]
    assert rows[0]["tx_id"]  # no vacío


def test_ledger_entries_tx_id_stable_across_builds(tmp_path):
    """7.1b AC1: el tx_id es estable entre dos cargas del mismo ledger."""
    first = ledger_entries_via_beancount(_ledger(tmp_path), "EAG")
    second = ledger_entries_via_beancount(_ledger(tmp_path), "EAG")
    ids_a = [r["tx_id"] for r in first["data"]]
    ids_b = [r["tx_id"] for r in second["data"]]
    assert ids_a == ids_b
    assert all(ids_a)


def test_ledger_entries_order_date_desc(tmp_path):
    """7.1b AC1: el orden `date DESC` del BQL saliente se preserva."""
    result = ledger_entries_via_beancount(_ledger(tmp_path), "EAG")
    dates = [r["date"] for r in result["data"]]
    assert dates == sorted(dates, reverse=True)


# ── Grupos de consolidación explícitos (Story 11.1, FR45/FR46) ────────────────

# Cuentas del libro EAG cuyo 2º segmento NO es una entidad (legacy del ledger
# real) + un libro RUT2 (FFCC/JAB) conviviendo en el mismo ledger.
EQUITY_LEGACY_BLOCK = """\

2020-01-01 open Equity:Apertura:TarjetasSinDetalle CLP
2020-01-01 open Equity:Reconciliation:Discrepancias CLP

2024-02-01 * "Apertura TC sin detalle"
  Liabilities:EAG:Tarjeta-211005          -80000 CLP
  Equity:Apertura:TarjetasSinDetalle       80000 CLP

2024-02-02 * "Discrepancia reconciliación"
  Assets:EAG:Bancos:TestBank-111005         -500 CLP
  Equity:Reconciliation:Discrepancias        500 CLP
"""

RUT2_BLOCK = """\

2020-01-01 open Assets:FFCC:Test-410001 CLP
  code: "410001"
2020-01-01 open Equity:FFCC:Apertura CLP
2020-01-01 open Assets:JAB:Banco-810001 CLP
  code: "810001"
2020-01-01 open Equity:JAB:Apertura CLP

2024-05-05 * "Aporte FFCC"
  Assets:FFCC:Test-410001    200000 CLP
  Equity:FFCC:Apertura      -200000 CLP

2024-05-06 * "Movimiento JAB"
  Assets:JAB:Banco-810001     70000 CLP
  Equity:JAB:Apertura        -70000 CLP
"""


def _multilibro_ledger(tmp_path, name="multi.beancount"):
    main = tmp_path / name
    main.write_text(MINI_LEDGER + EQUITY_LEGACY_BLOCK + RUT2_BLOCK, encoding="utf-8")
    return LedgerService(str(main))


def test_consolidation_group_rut2_members():
    """AC3: el grupo RUT2 resuelve exactamente a {FFCC, JAB} y es disjunto de EAG."""
    assert CONSOLIDATION_GROUPS["FondoComun"] == frozenset({"FFCC", "JAB"})
    assert not (CONSOLIDATION_GROUPS["FondoComun"] & CONSOLIDATION_GROUPS["EAG"])


def test_balance_sheet_eag_isolated_from_rut2(tmp_path):
    """AC2 (FR45): las cuentas FFCC/JAB no aparecen ni alteran ningún total del
    consolidado EAG — el resultado es idéntico con o sin el libro RUT2 presente."""
    without = tmp_path / "sin_rut2.beancount"
    without.write_text(MINI_LEDGER + EQUITY_LEGACY_BLOCK, encoding="utf-8")
    base = balance_sheet_via_beancount(LedgerService(str(without)), "EAG")
    with_rut2 = balance_sheet_via_beancount(_multilibro_ledger(tmp_path), "EAG")
    assert with_rut2 == base
    numbers = {r["account_number"] for r in with_rut2["data"]}
    assert "410001" not in numbers and "810001" not in numbers


def test_balance_sheet_eag_keeps_entityless_equity(tmp_path):
    """Guard TRAP #1: Equity:Apertura/Equity:Reconciliation (sin segmento de
    entidad) SIGUEN dentro del consolidado de EAG."""
    result = balance_sheet_via_beancount(_multilibro_ledger(tmp_path), "EAG")
    accounts = {r["account"] for r in result["data"]}
    assert "Equity:Apertura:TarjetasSinDetalle" in accounts
    assert "Equity:Reconciliation:Discrepancias" in accounts


def test_balance_sheet_rut2_group_consolidates_ffcc_jab(tmp_path):
    """AC3 (FR46): el consolidado del grupo RUT2 devuelve FFCC+JAB y excluye EAG
    (incluidos sus namespaces de Equity legacy)."""
    result = balance_sheet_via_beancount(_multilibro_ledger(tmp_path), "FondoComun")
    numbers = {r["account_number"] for r in result["data"]}
    accounts = {r["account"] for r in result["data"]}
    assert "410001" in numbers and "810001" in numbers      # FFCC + JAB
    assert "111005" not in numbers and "610005" not in numbers  # EAG + hija fuera
    assert not any(a.startswith("Equity:Apertura") for a in accounts)
    assert not any(a.startswith("Equity:Reconciliation") for a in accounts)


def test_balance_sheet_eag_excludes_case_variant_entity(tmp_path):
    """Patch code-review 11.1 (FR45): beanquery evalúa `~` con IGNORECASE — el
    aislamiento de grupo debe ser case-sensitive para que una entidad futura
    case-variante de un miembro EAG (JAEL) o de un namespace Equity legacy
    (APERTURA) no se consolide en silencio dentro de EAG."""
    extra = """\

2020-01-01 open Assets:JAEL:Banco-910001 CLP
  code: "910001"
2020-01-01 open Equity:APERTURA:Otro CLP

2024-06-01 * "Movimiento libro ajeno case-variante"
  Assets:JAEL:Banco-910001    50000 CLP
  Equity:APERTURA:Otro       -50000 CLP
"""
    main = tmp_path / "case.beancount"
    main.write_text(MINI_LEDGER + extra, encoding="utf-8")
    result = balance_sheet_via_beancount(LedgerService(str(main)), "EAG")
    numbers = {r["account_number"] for r in result["data"]}
    accounts = {r["account"] for r in result["data"]}
    assert "910001" not in numbers
    assert not any(a.startswith("Equity:APERTURA") for a in accounts)
