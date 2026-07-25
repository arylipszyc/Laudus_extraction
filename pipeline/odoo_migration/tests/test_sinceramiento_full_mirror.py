"""Gate de destino FR12c sobre el MIRROR COMPLETO (E1.3, AC3) — Tier A.

Primera corrida de la cadena completa (`collapse → sincerar → run_tier_a`)
sobre toda la historia (16.633 asientos / 57.540 patas, EAG+RUT2, 2021→hoy).
Corre en <2s (la carga del ledger domina, ~0.5s) → Tier A por-commit.

Las cifras pinneadas son las del INVENTARIO de naturalezas (el cross-check
INDEPENDIENTE del transformador — Valentina las derivó con bean-query, no con
este código). El corte al 2026-07-23 y la carga compartida del mirror viven en
`conftest.py` (`full_mirror_chain`, session-scoped — E1.4 reusa la misma
carga). Si este test se pone rojo sin haber tocado el transformador, un
asiento retro-posteado (o tardío del día del corte) cambió la historia
pinneada — eso es un hallazgo a investigar, no un test flaky.
"""

from decimal import Decimal

import pytest

from pipeline.odoo_migration.parity import run_tier_a
from pipeline.odoo_migration.sincerar import ORIGEN_ASSETS, route_sincerado


@pytest.fixture(scope="module")
def chain(full_mirror_chain):
    return full_mirror_chain


def _suma(mv, pred):
    return sum((l.amount for m in mv for l in m.lines if pred(l)), Decimal(0))


def test_tier_a_verde_full_mirror(chain):
    """FR8 + FR12a/b sobre TODA la historia: 0 diffs de origen, destino y
    conteos (con los washes declarados por identidad)."""
    entries, table, aliases, _, result = chain
    run_tier_a(
        entries,
        result.moves,
        table,
        route=route_sincerado(table, aliases),
        excluded_je_ids=result.excluded_je_ids,
    )


def test_sade_exacto_inventario(chain):
    """Anchor independiente #1 (inventario §1.1): el aporte Sade completo vive
    en el activo, al peso."""
    *_, result = chain
    sade = _suma(
        result.moves,
        lambda l: l.odoo_account == "Assets:FFCC:InversionesSade" and l.currency == "CLP",
    )
    assert sade == Decimal("4876249792")


def test_molco_exacto_inventario(chain):
    """Anchor independiente #2 (inventario §1.1): el financiamiento Molco es
    GASTO (P-1 resuelta); JAB netea contra el gasto (−1.200M, SPEC §2.E)."""
    *_, result = chain
    ffcc = _suma(
        result.moves,
        lambda l: l.odoo_account == "Expenses:MolcoFinanciamiento" and l.entity == "FFCC",
    )
    jab = _suma(
        result.moves,
        lambda l: l.odoo_account == "Expenses:MolcoFinanciamiento" and l.entity == "JAB",
    )
    assert ffcc == Decimal("2895757384")
    assert jab == Decimal("-1200000000")


def test_ingreso_bajo_la_cifra_exacta(chain):
    """FR12c: el ingreso bajó EXACTAMENTE lo que el sinceramiento movió — el
    número real del libro al corte del inventario, NO el redondeo "~46B".
    (El delta −45.576.501.123 es B+H+G-ruteado; C y E ya habían salido del
    ingreso en el colapso — sumando C/E neto (+6.572M) se recupera el total
    de ingresos Laudus del SPEC §2: −78.253M. Verificado al implementar.)"""
    _, _, _, moves, result = chain
    pre = _suma(
        moves, lambda l: l.odoo_account.startswith("Income:") and l.currency == "CLP"
    )
    post = _suma(
        result.moves,
        lambda l: l.odoo_account.startswith("Income:") and l.currency == "CLP",
    )
    assert pre == Decimal("-84825124241")
    assert post == Decimal("-39248623118")
    assert pre - post == Decimal("-45576501123")


def test_jhonny_por_cobrar(chain):
    """H (N-3): madre + hijo al mismo por-cobrar."""
    *_, result = chain
    assert _suma(
        result.moves, lambda l: l.odoo_account == "Assets:EAG:PrestamoJhonnyGuerra"
    ) == Decimal("-8600000")


def test_washes_excluidos_identidad_completa(chain):
    """El log auditable, pinneado: 2 pares Comprobante cierre/apertura (RUT2) +
    3 pares reverso Latinoamericana (EAG, N-1) — 10 moves, ni uno más."""
    *_, result = chain
    assert result.excluded_je_ids == {
        ("RUT2", "4529"), ("RUT2", "4530"),
        ("RUT2", "4724"), ("RUT2", "4725"),
        ("EAG", "553"), ("EAG", "635"),
        ("EAG", "555"), ("EAG", "636"),
        ("EAG", "611"), ("EAG", "637"),
    }
    kinds = sorted(p.kind for p in result.excluded_pairs)
    assert kinds == ["comprobante", "comprobante", "latinoamericana", "latinoamericana", "latinoamericana"]


def test_activo_origen_por_vehiculo_cuadra_con_mirror(chain):
    """AC3 "por vehículo": para cada código B, lo que llegó a su activo de
    origen == Σ del código en el mirror (expectativa derivada del mirror crudo,
    sin pasar por el clasificador). Las únicas patas B fuera de su activo son
    las ambiguas N-2 — que en la data real resultaron ser un PAR espejado
    (ids 4158 −32,16M / 4159 +32,16M, mismo día) que netea a 0."""
    entries, table, aliases, moves, result = chain
    from collections import defaultdict

    from pipeline.odoo_migration.transform import account_codes, entity_of_account, laudus_transactions

    codes = account_codes(entries)
    mirror: dict = defaultdict(Decimal)
    for txn in laudus_transactions(entries):
        for posting in txn.postings:
            code = codes.get(posting.account)
            entity = entity_of_account(posting.account)
            if (entity, code) in ORIGEN_ASSETS and posting.units.currency == "CLP":
                mirror[(entity, code)] += posting.units.number

    en_activo: dict = defaultdict(Decimal)
    ambiguas: dict = defaultdict(Decimal)
    for m in result.moves:
        for l in m.lines:
            key = (l.entity, l.laudus_code)
            if key in ORIGEN_ASSETS and l.currency == "CLP":
                if l.odoo_account == ORIGEN_ASSETS[key]:
                    en_activo[key] += l.amount
                else:
                    ambiguas[key] += l.amount  # N-2: quedaron en Income marcadas

    for key, esperado in mirror.items():
        assert en_activo.get(key, 0) + ambiguas.get(key, 0) == esperado, key
    # las ambiguas son SOLO el caso N-2 (310016) y netean a 0 entre sí — nada
    # material queda fuera de su activo de origen
    assert set(ambiguas) == {("EAG", "310016")}
    assert ambiguas[("EAG", "310016")] == 0

    marcadas = {
        m.je_id
        for m in result.moves
        for l in m.lines
        if l.sinc_regla == "cuenta-vs-glosa"
    }
    assert marcadas == {"4158", "4159"}  # el par N-2, ambos marcados revisar


#: P-10 review (letra de Task 5): Σ CLP que aterrizó en cada cuenta de activo
#: vía sinceramiento, pinneado al peso. Derivado UNA vez del mirror al corte
#: (patrón "pinnear lo que DÉ" de E1.2). Los saldos negativos son los orígenes
#: provisionales (SPEC §3.3 — esperado; la valuación real es E1B).
ACTIVOS_PINNEADOS = {
    "Assets:EAG:InmobiliariaEspana": Decimal("-9046724895.00"),
    "Assets:EAG:InmobiliariaMetropolitana": Decimal("-409716257.00"),
    "Assets:EAG:InvNuevoCiclo": Decimal("-5931052205.00"),
    "Assets:EAG:InvTecnion": Decimal("-12203820337.00"),
    "Assets:EAG:JuliusBaer": Decimal("-3258724566.00"),
    "Assets:EAG:MBI": Decimal("-4766939011.00"),
    "Assets:EAG:Pleyades": Decimal("-8876905.00"),
    "Assets:EAG:PrestamoJhonnyGuerra": Decimal("-8600000.00"),
    "Assets:EAG:RetirosFondoComun": Decimal("-125000000.00"),
    "Assets:FFCC:InversionesSade": Decimal("4876249792.00"),
    "Assets:Jael:InvTecnion": Decimal("-2594974665.00"),
    "Assets:Jael:JuliusBaer": Decimal("-380042800.00"),
    "Assets:Jael:MBI": Decimal("-17459327.00"),
    "Assets:Jeannette:InvTecnion": Decimal("-2256790057.00"),
    "Assets:Jeannette:MBI": Decimal("-11369699.00"),
    "Assets:Jeannette:Pleyades": Decimal("-91515.00"),
    "Assets:Jocelyn:InvTecnion": Decimal("-2256790057.00"),
    "Assets:Jocelyn:MBI": Decimal("-9725464.00"),
    "Assets:Jocelyn:Pleyades": Decimal("-91515.00"),
    "Assets:Johanna:InvTecnion": Decimal("-2277790057.00"),
    "Assets:Johanna:MBI": Decimal("-11830276.00"),
    "Assets:Johanna:Pleyades": Decimal("-91515.00"),
}


def test_activo_origen_pinneado_al_peso(chain):
    """P-10 review: lo que aterrizó en cada activo, contra literales pinneados
    — independiente del ruteo compartido transformador↔verificador (el otro
    test por-vehículo deriva su esperado del mirror; este NO deriva nada)."""
    from collections import defaultdict

    *_, result = chain
    landed: dict = defaultdict(Decimal)
    for m in result.moves:
        for l in m.lines:
            if (
                l.sinc_naturaleza
                and l.odoo_account.startswith("Assets:")
                and l.currency == "CLP"
            ):
                landed[l.odoo_account] += l.amount
    assert dict(landed) == ACTIVOS_PINNEADOS


def test_cobertura_pinneada(chain):
    """El reporte de cobertura al corte del inventario (FR10 versión E1.3):
    342 patas MIXTO, 232 sin clasificar (visibles, nunca perdidas), 64 a
    revisar. Si el transformador cambia, estos números DEBEN moverse acá."""
    *_, result = chain
    rep = result.report
    assert rep.por_naturaleza == {
        "A": 318, "B": 127, "C": 31, "D": 41, "E": 115, "F": 422, "G": 342, "H": 67,
    }
    assert len(rep.sin_clasificar) == 232
    assert len(rep.revisar) == 64
