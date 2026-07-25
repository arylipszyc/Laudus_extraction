"""Tests del transformador de colapso (E1.2, AC1) sobre el golden slice.

Cada línea transformada lleva la cuenta Odoo destino según la tabla Y el código
Laudus origen estampado (aunque N códigos colapsen a 1 cuenta). El universo es
SOLO Laudus (source: "laudus-erp"); nada se descarta en silencio.
"""

import os
from decimal import Decimal

import pytest
from beancount import loader
from beancount.core import data

from pipeline.odoo_migration.mapping import load_mapping_table
from pipeline.odoo_migration.transform import collapse, laudus_transactions

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "golden_slice.beancount")


@pytest.fixture(scope="module")
def entries():
    entries, errors, _ = loader.load_file(FIXTURE)
    assert errors == []
    return entries


@pytest.fixture(scope="module")
def table():
    return load_mapping_table()


@pytest.fixture(scope="module")
def moves(entries, table):
    return collapse(entries, table)


def _move(moves, je_id):
    (m,) = [m for m in moves if m.je_id == je_id]
    return m


# --- Conteos: ninguna fusión/partición silenciosa (base del FR12b) ---


def test_conteos_preservados(entries, moves):
    txns = laudus_transactions(entries)
    assert len(moves) == len(txns)
    assert sum(len(m.lines) for m in moves) == sum(len(t.postings) for t in txns)


# --- AC1: código origen estampado en cada línea ---


def test_toda_linea_lleva_codigo_origen(entries, moves):
    """Cada línea conserva el `code` del open de su cuenta Beancount origen."""
    codes = {
        e.account: e.meta.get("code")
        for e in entries
        if isinstance(e, data.Open)
    }
    by_je = {m.je_id: m for m in moves}
    for txn in laudus_transactions(entries):
        move = by_je[txn.meta["id"]]
        for posting, line in zip(txn.postings, move.lines, strict=True):
            assert line.laudus_code == codes[posting.account]
            assert line.entity == posting.account.split(":")[1]


def test_colapso_n_codigos_a_1_cuenta(moves):
    """Los 5 códigos RetirosTecnin (EAG + 4 hijas) colapsan al MISMO destino,
    conservando cada línea su código origen distinto."""
    retiro = _move(moves, "1237")
    income = [l for l in retiro.lines if l.amount < 0]
    codes = {l.laudus_code for l in income}
    destinations = {l.odoo_account for l in income}
    assert codes == {"310013", "670011", "770011", "870011", "970011"}
    assert destinations == {"Income:Retiros Tecnión"}


def test_retiro_reparte_5_entidades_misma_compania(moves):
    retiro = _move(moves, "1237")
    assert {l.entity for l in retiro.lines} == {
        "EAG", "Jocelyn", "Jeannette", "Johanna", "Jael",
    }
    assert retiro.company == "EAG"


def test_destino_segun_tabla_redirigida(moves):
    """La tabla ya redirige Sade a nivel cuenta (310011 FFCC → activo); E1.2 la
    mapea tal cual. Las reglas POR transacción son E1.3."""
    aporte = _move(moves, "3994")
    (sade,) = [l for l in aporte.lines if l.laudus_code == "310011"]
    assert sade.odoo_account == "Assets:FFCC:InversionesSade"
    assert aporte.company == "RUT2"


# --- je_id / metadata del move ---


def test_je_id_es_meta_id_no_je_num(moves):
    """id 1237 ≠ je_num 1234 (consistente con external_ids / E1.5)."""
    assert any(m.je_id == "1237" for m in moves)
    assert not any(m.je_id == "1234" for m in moves)


# --- Multi-moneda ---


def test_linea_usd_conserva_moneda_y_monto(moves):
    usd_move = _move(moves, "9000003")
    (usd_line,) = [l for l in usd_move.lines if l.currency == "USD"]
    assert usd_line.amount == Decimal("100.00")
    assert usd_line.laudus_code == "111003"
    (clp_line,) = [l for l in usd_move.lines if l.currency == "CLP"]
    assert clp_line.amount == Decimal("-80000.00")


# --- Filtro del universo Laudus ---


def test_asientos_no_laudus_quedan_fuera(table):
    """Un asiento manual del proyecto (sin source laudus-erp) NO entra a la
    migración — es el filtro del universo, no un descarte silencioso."""
    text = """
2020-12-31 open Assets:EAG:Bancos:BancoBci10160175-111005 CLP
  code: "111005"
2020-12-31 open Income:EAG:OtrosIngresos-310099 CLP
  code: "310099"

2026-01-15 * "ajuste manual del proyecto"
  Assets:EAG:Bancos:BancoBci10160175-111005  1000.00 CLP
  Income:EAG:OtrosIngresos-310099  -1000.00 CLP

2026-01-16 * "JE 42"
  id: "42"
  source: "laudus-erp"
  entity: "EAG"
  Assets:EAG:Bancos:BancoBci10160175-111005  500.00 CLP
  Income:EAG:OtrosIngresos-310099  -500.00 CLP
"""
    entries, errors, _ = loader.load_string(text)
    assert errors == []
    moves = collapse(entries, table)
    assert [m.je_id for m in moves] == ["42"]


# --- Fail-loud: nada se pierde en silencio ---


def test_cuenta_sin_code_falla(table):
    text = """
2020-12-31 open Assets:EAG:Bancos:BancoBci10160175-111005 CLP
  code: "111005"
2020-12-31 open Expenses:EAG:Suspense CLP

2026-01-15 * "JE 43"
  id: "43"
  source: "laudus-erp"
  entity: "EAG"
  Expenses:EAG:Suspense  1000.00 CLP
  Assets:EAG:Bancos:BancoBci10160175-111005  -1000.00 CLP
"""
    entries, errors, _ = loader.load_string(text)
    assert errors == []
    with pytest.raises(ValueError, match="Suspense"):
        collapse(entries, table)


def test_codigo_sin_mapeo_falla(table):
    text = """
2020-12-31 open Assets:EAG:Bancos:Fantasma-999999 CLP
  code: "999999"
2020-12-31 open Income:EAG:OtrosIngresos-310099 CLP
  code: "310099"

2026-01-15 * "JE 44"
  id: "44"
  source: "laudus-erp"
  entity: "EAG"
  Assets:EAG:Bancos:Fantasma-999999  1000.00 CLP
  Income:EAG:OtrosIngresos-310099  -1000.00 CLP
"""
    entries, errors, _ = loader.load_string(text)
    assert errors == []
    with pytest.raises(KeyError, match="999999"):
        collapse(entries, table)


def test_asiento_sin_id_falla(table):
    text = """
2020-12-31 open Assets:EAG:Bancos:BancoBci10160175-111005 CLP
  code: "111005"
2020-12-31 open Income:EAG:OtrosIngresos-310099 CLP
  code: "310099"

2026-01-15 * "sin id"
  source: "laudus-erp"
  entity: "EAG"
  Assets:EAG:Bancos:BancoBci10160175-111005  1000.00 CLP
  Income:EAG:OtrosIngresos-310099  -1000.00 CLP
"""
    entries, errors, _ = loader.load_string(text)
    assert errors == []
    with pytest.raises(ValueError, match="id"):
        collapse(entries, table)


def test_asiento_cruza_companias_falla(table):
    """El id de Laudus es por entidad legal: un asiento EAG+FFCC es data corrupta."""
    text = """
2020-12-31 open Assets:EAG:Bancos:BancoBci10160175-111005 CLP
  code: "111005"
2020-12-31 open Assets:FFCC:Bancos:BancoBci-111005 CLP
  code: "111005"

2026-01-15 * "cruza EAG y FFCC"
  id: "45"
  source: "laudus-erp"
  Assets:EAG:Bancos:BancoBci10160175-111005  1000.00 CLP
  Assets:FFCC:Bancos:BancoBci-111005  -1000.00 CLP
"""
    entries, errors, _ = loader.load_string(text)
    assert errors == []
    with pytest.raises(ValueError, match="cruza compañías"):
        collapse(entries, table)


def test_pata_sin_monto_falla(table):
    text = """
2020-12-31 open Assets:EAG:Bancos:BancoBci10160175-111005 CLP
  code: "111005"
2020-12-31 open Income:EAG:OtrosIngresos-310099 CLP
  code: "310099"

2026-01-15 * "JE 46"
  id: "46"
  source: "laudus-erp"
  Assets:EAG:Bancos:BancoBci10160175-111005  1000.00 CLP
  Income:EAG:OtrosIngresos-310099  -1000.00 CLP
"""
    entries, errors, _ = loader.load_string(text)
    assert errors == []
    broken = [
        e._replace(postings=[e.postings[0]._replace(units=None), *e.postings[1:]])
        if isinstance(e, data.Transaction)
        else e
        for e in entries
    ]
    with pytest.raises(ValueError, match="sin monto"):
        collapse(broken, table)


def test_je_id_duplicado_falla(table):
    """Un doble-import del mirror pasaría la paridad (ambos lados cuentan doble)
    pero colisionaría el external ID mv_<company>_<je_id> en E1.5 — fail-loud acá."""
    text = """
2020-12-31 open Assets:EAG:Bancos:BancoBci10160175-111005 CLP
  code: "111005"
2020-12-31 open Income:EAG:OtrosIngresos-310099 CLP
  code: "310099"

2026-01-15 * "JE 47"
  id: "47"
  source: "laudus-erp"
  Assets:EAG:Bancos:BancoBci10160175-111005  1000.00 CLP
  Income:EAG:OtrosIngresos-310099  -1000.00 CLP

2026-01-16 * "JE 47 duplicado"
  id: "47"
  source: "laudus-erp"
  Assets:EAG:Bancos:BancoBci10160175-111005  500.00 CLP
  Income:EAG:OtrosIngresos-310099  -500.00 CLP
"""
    entries, errors, _ = loader.load_string(text)
    assert errors == []
    with pytest.raises(ValueError, match="duplicado"):
        collapse(entries, table)


def test_asiento_sin_patas_falla(table):
    """Un move sin líneas quedaría con company vacía y pasaría los gates en
    silencio (0 líneas en ambos lados) — fail-loud en el transformador."""
    text = """
2020-12-31 open Assets:EAG:Bancos:BancoBci10160175-111005 CLP
  code: "111005"
2020-12-31 open Income:EAG:OtrosIngresos-310099 CLP
  code: "310099"

2026-01-15 * "JE 48"
  id: "48"
  source: "laudus-erp"
  Assets:EAG:Bancos:BancoBci10160175-111005  1000.00 CLP
  Income:EAG:OtrosIngresos-310099  -1000.00 CLP
"""
    entries, errors, _ = loader.load_string(text)
    assert errors == []
    broken = [
        e._replace(postings=[]) if isinstance(e, data.Transaction) else e
        for e in entries
    ]
    with pytest.raises(ValueError, match="sin patas"):
        collapse(broken, table)
