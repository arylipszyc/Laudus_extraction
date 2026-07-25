"""Gate de partición + cobertura E1.4 sobre el MIRROR COMPLETO — Tier A.

La cadena completa de 3 transformadores (`collapse → sincerar → dimensionar`)
sobre toda la historia al corte 2026-07-23 (carga compartida en
`conftest.full_mirror_chain`). El gate NUEVO de esta story es la PARTICIÓN
socio-dueño (AC2): Σ(patas por partner sobre 115xxx) == mirror, al peso.

Los ANCHORS pinneados son los saldos de la lista de partners de Valentina
(cat 1) — cross-check INDEPENDIENTE (ella los derivó de Laudus, no con este
código). Al implementar (2026-07-25), el mirror al corte dio EXACTAMENTE los
11 saldos de la lista, al peso — 0 diferencias que documentar.
"""

import dataclasses
from collections import Counter, defaultdict
from decimal import Decimal

import pytest

from pipeline.odoo_migration.dimensionar import (
    CAT_SOCIO_PARTICION,
    dimensionar,
    verify_particion,
)
from pipeline.odoo_migration.parity import run_tier_a
from pipeline.odoo_migration.sincerar import route_sincerado


@pytest.fixture(scope="module")
def dim_chain(full_mirror_chain):
    cut, table, aliases, _, sinc = full_mirror_chain
    dim = dimensionar(sinc.moves, table, alias_table=aliases)
    return cut, table, aliases, sinc, dim


def _saldos_particion(moves) -> dict:
    saldos: dict = defaultdict(Decimal)
    for m in moves:
        for l in m.lines:
            if l.partner_categoria == CAT_SOCIO_PARTICION:
                saldos[(l.partner, l.currency)] += l.amount
    return dict(saldos)


def test_tier_a_verde_cadena_completa(dim_chain):
    """La paridad es doblemente invariante: run_tier_a con los MISMOS
    route/excluded_je_ids que produjo E1.3 — si esto rompe, E1.4 tocó algo
    que no debía."""
    cut, table, aliases, sinc, dim = dim_chain
    run_tier_a(
        cut,
        dim.moves,
        table,
        route=route_sincerado(table, aliases),
        excluded_je_ids=sinc.excluded_je_ids,
    )


def test_invariante_estructural(dim_chain):
    """dimensionar NO altera odoo_account / amount / set de moves — en las
    57.5k patas de la historia completa."""
    *_, sinc, dim = dim_chain
    assert len(dim.moves) == len(sinc.moves)
    for antes, despues in zip(sinc.moves, dim.moves):
        assert antes.je_id == despues.je_id and len(antes.lines) == len(despues.lines)
        for a, d in zip(antes.lines, despues.lines):
            assert a.odoo_account == d.odoo_account and a.amount == d.amount
            assert a.currency == d.currency and a.laudus_code == d.laudus_code


def test_particion_gate_verde(dim_chain):
    """AC2: el partner ledger cuadra al peso con el mirror (la única partición
    que reconcilia)."""
    cut, *_, dim = dim_chain
    assert verify_particion(cut, dim.moves) == []


#: Anchors INDEPENDIENTES: saldos de la lista de Valentina §cat 1 (corte
#: 2026-07-23) — el mirror los reprodujo EXACTOS al implementar. "Otros hijos"
#: (115039) no aparece: saldo 0 y SIN movimientos al corte (por eso no hay key).
ANCHORS_PARTICION = {
    ("AAG", "CLP"): Decimal("-4438135788.00"),
    ("AZBA", "CLP"): Decimal("-493043375.00"),
    ("Ariel Borzutzky", "CLP"): Decimal("-534603111.00"),
    ("DAG", "CLP"): Decimal("-3362663937.00"),  # 115027 + 115028 (colapsa Autos)
    ("Denise Zeldis", "CLP"): Decimal("-485461560.00"),  # 115033 + 115034
    ("EAG", "CLP"): Decimal("-3587647995.00"),
    ("Israel", "CLP"): Decimal("4639535.00"),  # por CUENTA 115041, nunca por glosa
    ("José Alazraki", "CLP"): Decimal("-482345420.00"),
    ("Michelle Zeldis", "CLP"): Decimal("-494335026.00"),
    ("SAG", "CLP"): Decimal("260889862.00"),
}


def test_anchors_particion_pinneados(dim_chain):
    """Los saldos por partner contra los literales de la LISTA (no derivados
    de este código) — si un pin se altera o un colapso se rompe, falla acá."""
    *_, dim = dim_chain
    assert _saldos_particion(dim.moves) == ANCHORS_PARTICION


def test_cobertura_pinneada(dim_chain):
    """FR10 versión E1.4, al corte: conteos exactos por categoría y por plan;
    67 patas mencionadas-sin-resolver (contadas y listadas — el listado del
    sign-off AC5) y 264 con partner placeholder/dudoso a revisar."""
    *_, dim = dim_chain
    rep = dim.report
    assert rep.por_categoria == {
        "beneficiario": 796,
        "bucket": 169,
        "club": 30,
        "deudor": 65,
        "donacion": 84,
        "rendicion-p7": 769,
        "socio-disperso": 1254,
        "socio-particion": 5657,
    }
    assert rep.por_plan == {
        "area_centro": 10092,
        "offshore_vehiculo": 233,
        "por_cuenta_de": 2725,
        "propiedad_objeto": 12654,
        "socio_uso": 2428,
    }
    assert len(rep.sin_match) == 67
    assert Counter(r.regla for r in rep.sin_match) == {
        "glosa:beneficiario-sin-resolver": 35,
        "glosa:socio-uso-sin-resolver": 32,
    }
    assert len(rep.revisar) == 264
    # el listado del sign-off es auditable: cada ref trae glosa+cuenta+monto
    for ref in rep.sin_match:
        assert ref.desc and ref.code


# --- Tests de mutación: el gate DEBE poder fallar (learning E1.3-e) -----------
# Trabajan sobre una corrida FRESCA de dimensionar (el fixture compartido no se
# muta — los transformadores devuelven copias).


def _fresh_dim(full_mirror_chain):
    cut, table, aliases, _, sinc = full_mirror_chain
    return cut, dimensionar(sinc.moves, table, alias_table=aliases)


def test_mutacion_partner_equivocado_acusa(full_mirror_chain):
    """Un partner mal estampado en una 115xxx descuadra DOS particiones."""
    cut, dim = _fresh_dim(full_mirror_chain)
    for m in dim.moves:
        for l in m.lines:
            if l.laudus_code == "115023" and l.partner == "EAG" and l.amount:
                l.partner = "AAG"
                break
        else:
            continue
        break
    else:
        pytest.fail("no hay patas 115023 EAG no-cero al corte")
    problems = verify_particion(cut, dim.moves)
    assert any("'EAG'" in p for p in problems)
    assert any("'AAG'" in p for p in problems)


def test_mutacion_colapso_autos_roto_descuadra_dag(full_mirror_chain):
    """Si el colapso Autos pierde UNA pata no-cero de 115028, la partición DAG
    descuadra contra el mirror. (Ojo: 115028 NETEA a 0.00 al corte — 9 patas
    que se cancelan — así que romper el colapso COMPLETO es invisible para un
    gate de sumas; la pata individual es la señal real.)"""
    cut, dim = _fresh_dim(full_mirror_chain)
    for m in dim.moves:
        for l in m.lines:
            if (
                l.laudus_code == "115028"
                and l.partner_categoria == CAT_SOCIO_PARTICION
                and l.amount
            ):
                l.partner = ""
                l.partner_categoria = ""
                break
        else:
            continue
        break
    else:
        pytest.fail("no hay patas 115028 no-cero al corte")
    problems = verify_particion(cut, dim.moves)
    assert any("'DAG'" in p for p in problems)


def test_mutacion_move_perdido_descuadra(full_mirror_chain):
    """Sacar un move con pata de partición del output → el gate acusa (y
    run_tier_a también acusaría por conteos — doble alarma)."""
    cut, dim = _fresh_dim(full_mirror_chain)
    idx = next(
        i
        for i, m in enumerate(dim.moves)
        if any(l.partner_categoria == CAT_SOCIO_PARTICION and l.amount for l in m.lines)
    )
    del dim.moves[idx]
    assert verify_particion(cut, dim.moves) != []
