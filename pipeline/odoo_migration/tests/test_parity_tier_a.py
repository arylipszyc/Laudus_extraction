"""Verificador de paridad Tier A (E1.2, AC2 + AC4) sobre el golden slice.

Paridad-origen: Σ(líneas por x_laudus_account_code, por moneda) == saldo Laudus,
0 diffs. Gate de destino (FR12a) + conteos (FR12b). Incluye TESTS DE MUTACIÓN:
un verificador que no puede ponerse rojo es `tsc --noEmit` — cada corrupción
del output DEBE ser detectada.
"""

import os
from decimal import Decimal

import pytest
from beancount import loader

from pipeline.odoo_migration.mapping import load_mapping_table
from pipeline.odoo_migration.parity import (
    ParityError,
    run_tier_a,
    verify_counts,
    verify_destination,
    verify_origin_parity,
)
from pipeline.odoo_migration.transform import collapse

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "golden_slice.beancount")


@pytest.fixture(scope="module")
def entries():
    entries, errors, _ = loader.load_file(FIXTURE)
    assert errors == []
    return entries


@pytest.fixture(scope="module")
def table():
    return load_mapping_table()


@pytest.fixture()
def moves(entries, table):
    """Function-scoped: los tests de mutación alteran el output."""
    return collapse(entries, table)


# --- AC2: 0 diffs sobre el golden slice ---


def test_paridad_origen_0_diffs(entries, moves):
    assert verify_origin_parity(entries, moves) == []


def test_gate_destino_0_diffs(entries, moves, table):
    assert verify_destination(entries, moves, table) == []


def test_conteos_preservados(entries, moves):
    assert verify_counts(entries, moves) == []


def test_run_tier_a_verde(entries, moves, table):
    run_tier_a(entries, moves, table)  # no levanta


def test_valores_conocidos_del_slice(entries, moves):
    """Anclas al peso: el retiro Tecnión EAG y el caso USD (por moneda)."""
    from pipeline.odoo_migration.parity import laudus_balances, transformed_balances

    laudus = laudus_balances(entries)
    transformed = transformed_balances(moves)
    key_retiro = ("EAG", "310013", "CLP")
    key_usd = ("EAG", "111003", "USD")
    assert laudus[key_retiro] == Decimal("-1022700000.00")
    assert transformed[key_retiro] == Decimal("-1022700000.00")
    assert laudus[key_usd] == Decimal("100.00")
    assert transformed[key_usd] == Decimal("100.00")


def test_wash_netea_a_0_en_paridad(entries, moves):
    """El par apertura/cierre suma 0 por código: la paridad es invariante a que
    E1.3 lo excluya después (winston §6, caso de test obligatorio)."""
    from pipeline.odoo_migration.parity import laudus_balances

    laudus = laudus_balances(entries)
    assert laudus[("RUT2", "310009", "CLP")] == 0
    assert laudus[("RUT2", "211005", "CLP")] == 0


# --- Tests de mutación: el gate TIENE que poder fallar ---


def test_mutacion_monto_alterado_se_detecta(entries, moves):
    moves[0].lines[0].amount += Decimal("1")
    diffs = verify_origin_parity(entries, moves)
    assert len(diffs) == 1
    assert diffs[0].diff == Decimal("-1")


def test_mutacion_monto_alterado_rompe_destino(entries, moves, table):
    moves[0].lines[0].amount += Decimal("1")
    assert verify_destination(entries, moves, table) != []


def test_mutacion_linea_borrada_se_detecta(entries, moves):
    del moves[0].lines[0]
    assert verify_origin_parity(entries, moves) != []
    assert verify_counts(entries, moves) != []


def test_mutacion_code_cambiado_se_detecta(entries, moves):
    """Cambiar el código estampado descuadra los DOS códigos afectados."""
    line = moves[0].lines[0]
    original = line.laudus_code
    assert original != "310099"
    line.laudus_code = "310099"
    diffs = verify_origin_parity(entries, moves)
    assert {d.code for d in diffs} == {original, "310099"}


def test_mutacion_key_incompleta_no_colapsa_companias(entries, moves):
    """111005 existe en EAG y FFCC: mover el monto de la línea FFCC al mismo
    código de EAG debe dar diffs en AMBAS compañías (la key incluye company)."""
    ffcc_lines = [
        l for m in moves for l in m.lines
        if l.laudus_code == "111005" and m.company == "RUT2"
    ]
    assert ffcc_lines, "el slice debe tocar 111005 en FFCC (aporte Sade)"
    line = ffcc_lines[0]
    line.entity = "EAG"
    diffs = verify_origin_parity(entries, moves)
    companies = {d.company for d in diffs}
    assert companies == {"EAG", "RUT2"}


def test_run_tier_a_falla_con_output_corrupto(entries, moves, table):
    moves[0].lines[0].amount += Decimal("1")
    with pytest.raises(ParityError):
        run_tier_a(entries, moves, table)


# --- API de exclusiones esperadas (la usa E1.3 con los washes) ---


def test_exclusion_esperada_del_par_wash(entries, moves, table):
    """Caso E1.3: excluir el par wash completo (2 moves, 4 líneas) por IDENTIDAD
    mantiene la paridad en 0 (netea) y los conteos cuadran declarándolo."""
    wash_ids = {("RUT2", "9000001"), ("RUT2", "9000002")}
    filtered = [m for m in moves if (m.company, m.je_id) not in wash_ids]
    assert len(filtered) == len(moves) - 2

    # sin declarar la exclusión: los conteos acusan
    assert verify_counts(entries, filtered) != []
    # declarándola por identidad: conteos verdes y la paridad sigue en 0 (netea)
    assert verify_counts(entries, filtered, excluded_je_ids=wash_ids) == []
    assert verify_origin_parity(entries, filtered) == []
    run_tier_a(entries, filtered, table, excluded_je_ids=wash_ids)


def test_exclusion_del_par_equivocado_falla_por_identidad(entries, moves, table):
    """EL caso que el conteo ciego dejaba pasar (review E1.2): declarar la
    exclusión de un par que NO es el que falta debe fallar — la identidad de lo
    declarado tiene que coincidir con lo ausente, no solo el número."""
    wash_ids = {("RUT2", "9000001"), ("RUT2", "9000002")}
    filtered = [m for m in moves if (m.company, m.je_id) not in wash_ids]
    declarado_equivocado = {("EAG", "1237"), ("EAG", "9000003")}
    problems = verify_counts(entries, filtered, excluded_je_ids=declarado_equivocado)
    assert any("SIN declarar" in p for p in problems)
    assert any("SIGUE en el output" in p for p in problems)


def test_exclusion_fantasma_falla(entries, moves):
    """Declarar la exclusión de una identidad que NO existe en el mirror →
    alarma dedicada (el mensaje 'NO existen en el mirror')."""
    fantasma = {("EAG", "id-inexistente")}
    problems = verify_counts(entries, moves, excluded_je_ids=fantasma)
    assert any("NO existen en el mirror" in p for p in problems)


def test_exclusion_no_declarada_falla(entries, moves):
    """Un move ausente sin declaración explícita → alarma (nada se excluye en
    silencio, AC2 E1.3)."""
    filtered = [m for m in moves if (m.company, m.je_id) != ("RUT2", "9000001")]
    problems = verify_counts(entries, filtered)
    assert any("SIN declarar" in p for p in problems)


def test_exclusion_que_no_netea_falla(entries, moves):
    """Declarar la exclusión de un move que NO netea a 0 por código → alarma
    (solo pares completos iguales-y-opuestos pueden excluirse)."""
    excluded = {("EAG", "1237")}
    filtered = [m for m in moves if (m.company, m.je_id) not in excluded]
    problems = verify_counts(entries, filtered, excluded_je_ids=excluded)
    assert any("NO netea" in p for p in problems)


def test_exclusion_de_una_sola_pata_descuadra(entries, moves):
    """Excluir UNA pata del wash (no el par completo) SÍ descuadra la paridad —
    exactamente lo que E1.3 nunca debe hacer (winston §6)."""
    (wash,) = [m for m in moves if m.je_id == "9000001"]
    wash.lines = [l for l in wash.lines if l.laudus_code != "310009"]
    assert verify_origin_parity(entries, moves) != []


# --- Fail-loud del lado-Laudus (simetría con transform) ---


def test_pata_sin_monto_falla_en_laudus_balances(entries):
    from beancount.core import data

    from pipeline.odoo_migration.parity import laudus_balances

    broken = [
        e._replace(postings=[e.postings[0]._replace(units=None), *e.postings[1:]])
        if isinstance(e, data.Transaction) and e.meta.get("source") == "laudus-erp"
        else e
        for e in entries
    ]
    with pytest.raises(ValueError, match="sin monto"):
        laudus_balances(broken)


def test_cuenta_sin_code_falla_en_verify_destination(table):
    text = """
2020-12-31 open Assets:EAG:Bancos:BancoBci10160175-111005 CLP
  code: "111005"
2020-12-31 open Expenses:EAG:Suspense CLP

2026-01-15 * "JE 49"
  id: "49"
  source: "laudus-erp"
  Expenses:EAG:Suspense  1000.00 CLP
  Assets:EAG:Bancos:BancoBci10160175-111005  -1000.00 CLP
"""
    entries, errors, _ = loader.load_string(text)
    assert errors == []
    with pytest.raises(ValueError, match="meta `code`"):
        verify_destination(entries, [], table)
