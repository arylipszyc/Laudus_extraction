"""Tests del transformador de sinceramiento (E1.3) sobre el golden slice.

Los casos canónicos los trae el fixture (curado en E1.0 para esto): retiro
Tecnión 5 entidades (1237), aporte Sade (3994), traspaso G sin vehículo (29),
dividendo ambiguo N-2 (4158), par wash Comprobante cierre/apertura sobre
Latinoamericana (9000001/9000002), caso USD (9000003).
"""

import os
from decimal import Decimal

import pytest
from beancount import loader

from pipeline.odoo_migration.mapping import load_mapping_table
from pipeline.odoo_migration.parity import (
    run_tier_a,
    verify_counts,
    verify_destination,
)
from pipeline.odoo_migration.sincerar import (
    FLAG_REVISAR,
    FLAG_SIN_CLASIFICAR,
    ORIGEN_ASSETS,
    Classification,
    classify_line,
    load_alias_table,
    naturaleza_de,
    normalize,
    resolve_vehiculo,
    route_sincerado,
    sincerar,
)
from pipeline.odoo_migration.transform import collapse

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "golden_slice.beancount")

WASH_IDS = {("RUT2", "9000001"), ("RUT2", "9000002")}


@pytest.fixture(scope="module")
def entries():
    entries, errors, _ = loader.load_file(FIXTURE)
    assert errors == []
    return entries


@pytest.fixture(scope="module")
def table():
    return load_mapping_table()


@pytest.fixture(scope="module")
def aliases():
    return load_alias_table()


@pytest.fixture()
def moves(entries, table):
    return collapse(entries, table)


@pytest.fixture()
def result(moves, table, aliases):
    return sincerar(moves, table, alias_table=aliases)


def _lines(result, je_id):
    (m,) = [m for m in result.moves if m.je_id == je_id]
    return m.lines


# --- Normalización y alias (winston §6·B.3) ---------------------------------


def test_normalize():
    assert normalize("  Inv.  TECNIÓN   Ltda ") == "inv. tecnion ltda"
    assert normalize("Devolución de Préstamos") == "devolucion de prestamos"
    assert normalize("") == ""


def test_alias_word_boundary(aliases):
    """Tokens cortos exigen word-boundary; 'servicio tecnico' NO es Tecnión."""
    assert resolve_vehiculo(normalize("Retiro de Inversiones Tecnion Limitada"), aliases) == "Tecnion"
    assert resolve_vehiculo(normalize("pago servicio tecnico calefont"), aliases) is None
    assert resolve_vehiculo(normalize("Inversion en MBI"), aliases) == "MBI"
    assert resolve_vehiculo(normalize("cambio de timbi"), aliases) is None


def test_alias_homonimo_veta(aliases):
    """Un homónimo presente en la glosa veta al vehículo (conservador)."""
    assert resolve_vehiculo(normalize("transferencia Leo Limited Partnership"), aliases) == "Leo"
    assert resolve_vehiculo(normalize("pago a Leo Hernandez por leo limited"), aliases) is None


def test_dos_vehiculos_es_ambiguo(aliases):
    assert resolve_vehiculo(normalize("traspaso tecnion a tauro"), aliases) is None


# --- Clasificador: población cerrada + completitud --------------------------


def test_poblacion_cerrada_toda_fila_sinc_clasifica(table, aliases):
    """Las 83 filas con `sinc` en la tabla clasifican sin error (cross-check
    tabla ↔ tabla-madre 0/A–H; un label nuevo revienta fuerte)."""
    filas = [r for r in table.rows if r.sinc]
    assert len(filas) == 83
    for r in filas:
        cls = classify_line(
            r.entity, r.code, r.sinc, "glosa cualquiera", Decimal(1), r.odoo_account, aliases
        )
        assert isinstance(cls, Classification)
        assert cls.naturaleza in set("0ABCDEFGH")


#: P-9 review (letra de Task 1): naturaleza pinneada de las 83 filas con `sinc`,
#: keyed (entity, code). La columna del CSV es el seed; este snapshot es el
#: cross-check versionado en código — si alguien edita el CSV, acusa el flip.
NATURALEZA_SNAPSHOT = {
    ("EAG", "310001"): "A",
    ("EAG", "310003"): "A",
    ("EAG", "310005"): "A",
    ("EAG", "310006"): "B",
    ("EAG", "310009"): "A",
    ("EAG", "310010"): "H",
    ("EAG", "310011"): "A",
    ("EAG", "310013"): "B",
    ("EAG", "310015"): "B",
    ("EAG", "310016"): "B",
    ("EAG", "310017"): "B",
    ("EAG", "310018"): "B",
    ("EAG", "310019"): "B",
    ("EAG", "310021"): "A",
    ("EAG", "310022"): "A",
    ("EAG", "310023"): "A",
    ("EAG", "310024"): "A",
    ("EAG", "310025"): "A",
    ("EAG", "310027"): "B",
    ("EAG", "310029"): "B",
    ("EAG", "310035"): "A",
    ("EAG", "310037"): "F",
    ("EAG", "310039"): "F",
    ("EAG", "310041"): "F",
    ("EAG", "310043"): "F",
    ("EAG", "310045"): "H",
    ("EAG", "310047"): "H",
    ("EAG", "310049"): "F",
    ("EAG", "310059"): "D",
    ("EAG", "310091"): "D",
    ("EAG", "310095"): "A",
    ("EAG", "310099"): "G",
    ("EAG", "510001"): "A",
    ("EAG", "510007"): "A",
    ("EAG", "510009"): "A",
    ("EAG", "510011"): "B",
    ("EAG", "510021"): "A",
    ("EAG", "510023"): "A",
    ("FFCC", "310001"): "A",
    ("FFCC", "310003"): "B",
    ("FFCC", "310005"): "E",
    ("FFCC", "310007"): "B",
    ("FFCC", "310009"): "H",
    ("FFCC", "310011"): "C",
    ("FFCC", "310019"): "F",
    ("FFCC", "310091"): "D",
    ("FFCC", "310099"): "G",
    ("JAB", "710005"): "E",
    ("JAB", "710099"): "G",
    ("Jael", "970001"): "A",
    ("Jael", "970005"): "A",
    ("Jael", "970010"): "B",
    ("Jael", "970011"): "B",
    ("Jael", "970013"): "B",
    ("Jael", "970021"): "A",
    ("Jael", "970023"): "B",
    ("Jael", "970051"): "F",
    ("Jael", "970091"): "D",
    ("Jael", "970099"): "G",
    ("Jeannette", "770001"): "A",
    ("Jeannette", "770005"): "A",
    ("Jeannette", "770011"): "B",
    ("Jeannette", "770013"): "B",
    ("Jeannette", "770021"): "A",
    ("Jeannette", "770023"): "B",
    ("Jeannette", "770091"): "D",
    ("Jeannette", "770099"): "G",
    ("Jocelyn", "670001"): "A",
    ("Jocelyn", "670005"): "A",
    ("Jocelyn", "670011"): "B",
    ("Jocelyn", "670013"): "B",
    ("Jocelyn", "670021"): "A",
    ("Jocelyn", "670023"): "B",
    ("Jocelyn", "670091"): "D",
    ("Jocelyn", "670099"): "G",
    ("Johanna", "870001"): "A",
    ("Johanna", "870005"): "A",
    ("Johanna", "870011"): "B",
    ("Johanna", "870013"): "B",
    ("Johanna", "870021"): "A",
    ("Johanna", "870023"): "B",
    ("Johanna", "870091"): "D",
    ("Johanna", "870099"): "G",
}


def test_snapshot_naturalezas_pinneado(table):
    """P-9 review: la clasificación de TODAS las filas con `sinc`, contra el
    snapshot versionado en código (patrón snapshot E1.2). Un flip en el CSV
    (el seed) no pasa en silencio: la autoridad es la tabla-madre 0/A–H."""
    derivadas = {
        (r.entity, r.code): naturaleza_de(r.entity, r.code, r.sinc)
        for r in table.rows
        if r.sinc
    }
    assert derivadas == NATURALEZA_SNAPSHOT


def test_completitud_origen_assets(table):
    """Toda fila RETIRO tiene activo de origen, y no sobra ninguno."""
    retiros = {
        (r.entity, r.code) for r in table.rows if r.sinc == "RETIRO→activo origen"
    }
    assert retiros == set(ORIGEN_ASSETS)


def test_cuenta_income_sin_naturaleza_falla(aliases):
    with pytest.raises(ValueError, match="cerrada"):
        classify_line("EAG", "999999", "", "x", Decimal(1), "Income:Fantasma", aliases)


def test_label_sinc_desconocido_falla():
    with pytest.raises(ValueError, match="desconocido"):
        naturaleza_de("EAG", "310013", "NATURALEZA-NUEVA")


def test_revisar_sin_resolucion_pinneada_falla():
    with pytest.raises(ValueError, match="pinneada"):
        naturaleza_de("EAG", "999998", "REAL?(revisar)")


def test_cascada_prestamo_antes_que_reembolso(table, aliases):
    """'Devolución de préstamos' es capital (H/c de la cascada), NO reembolso —
    y con vehículo resoluble va al activo de origen."""
    cls = classify_line(
        "EAG", "310099", "MIXTO→regla por-glosa",
        "Nuevo Ciclo: Devolución de préstamos", Decimal(-100), "Income:Otros Ingresos", aliases,
    )
    assert cls.odoo_account == "Assets:EAG:InvNuevoCiclo"
    assert cls.flag == ""


# --- Patches del review E1.3 (P-1, P-3, P-4) --------------------------------


def test_comprobante_sin_par_nunca_re_rutea(aliases):
    """P-1: una pata B dentro de un comprobante huérfano (sin par) NO se inyecta
    al activo de origen — queda en su cuenta de colapso + revisar, visible."""
    cls = classify_line(
        "EAG", "310013", "RETIRO→activo origen",
        "Comprobante de apertura 01/01/2024", Decimal("-100"),
        "Income:Retiros Tecnión", aliases,
    )
    assert cls.odoo_account == "Income:Retiros Tecnión"
    assert cls.regla == "glosa:comprobante-sin-par"
    assert cls.flag == FLAG_REVISAR


def test_regex_boundaries_capital_y_prestamo(aliases):
    """P-3: 'transferencia cta' no es 'a cta'; 'desabono' no es 'abono de
    prestamo' — sin boundary izquierdo ambas matcheaban por substring."""
    cls = classify_line(
        "EAG", "310099", "MIXTO→regla por-glosa",
        "transferencia cta corriente", Decimal("-1"), "Income:Otros Ingresos", aliases,
    )
    assert cls.regla == "glosa:sin-match"
    cls = classify_line(
        "EAG", "310099", "MIXTO→regla por-glosa",
        "desabono de prestamos tecnion", Decimal("-1"), "Income:Otros Ingresos", aliases,
    )
    assert cls.regla == "glosa:sin-match"


def test_ingreso_real_plurales(aliases):
    """P-3: 'arriendos'/'sueldos' (plural) también gatillan el conflicto
    cuenta-vs-glosa N-2 — antes se ruteaban al activo sin marca."""
    cls = classify_line(
        "EAG", "310013", "RETIRO→activo origen",
        "Arriendos oficina enero", Decimal("-1"), "Income:Retiros Tecnión", aliases,
    )
    assert cls.regla == "cuenta-vs-glosa"
    assert cls.flag == FLAG_REVISAR


def test_destino_g_no_acuna_cuentas_fuera_de_allowlist(aliases):
    """P-4: la regla G solo rutea a cuentas de la allowlist — Assets:JAB:MBI no
    existe en ningún plan, y una glosa EAG con 'sade' no puede cruzar de
    company (contaminaría el ancla pinneada de Sade)."""
    cls = classify_line(
        "JAB", "710099", "MIXTO→regla por-glosa",
        "Retiro inversion MBI", Decimal("-100"), "Income:JAB:OtrosIngresos", aliases,
    )
    assert cls.odoo_account == "Income:JAB:OtrosIngresos"
    assert cls.flag == FLAG_SIN_CLASIFICAR
    cls = classify_line(
        "EAG", "310099", "MIXTO→regla por-glosa",
        "Aporte inversiones Sade", Decimal("100"), "Income:Otros Ingresos", aliases,
    )
    assert cls.odoo_account == "Income:Otros Ingresos"
    assert cls.flag == FLAG_SIN_CLASIFICAR


# --- Golden slice: los 6 casos canónicos ------------------------------------


def test_wash_par_excluido_por_identidad(result):
    assert result.excluded_je_ids == WASH_IDS
    (pair,) = result.excluded_pairs
    assert pair.kind == "comprobante"
    assert pair.company == "RUT2"
    assert set(pair.je_ids) == {"9000001", "9000002"}
    # P-5: el log trae la magnitud del wash POR código (Task 2)
    assert any(code == "310009" for code, _, _ in pair.montos)
    assert not any(m.je_id in {"9000001", "9000002"} for m in result.moves)


def test_retiro_1237_rutea_a_activo_origen(result):
    lines = _lines(result, "1237")
    income = [l for l in lines if l.sinc_naturaleza == "B"]
    assert {l.laudus_code for l in income} == {
        "310013", "670011", "770011", "870011", "970011",
    }
    for l in income:
        assert l.odoo_account == f"Assets:{l.entity}:InvTecnion"
        assert l.odoo_account_colapso.startswith("Income:")
        assert l.sinc_flag == ""
    # las patas de banco no son del universo de sinceramiento
    bancos = [l for l in lines if l.sinc_naturaleza == ""]
    assert bancos and all(l.odoo_account_colapso == "" for l in bancos)


def test_310013_al_peso_bajo_activo(result):
    """El ancla de E1.2 (−1.022.700.000) ahora vive bajo el activo de origen,
    con el código origen intacto (la paridad es invariante)."""
    total = sum(
        l.amount
        for m in result.moves
        for l in m.lines
        if l.laudus_code == "310013"
        and l.odoo_account == "Assets:EAG:InvTecnion"
        and l.currency == "CLP"
    )
    assert total == Decimal("-1022700000.00")


def test_sade_estampada_C_sin_re_ruteo(result):
    (sade,) = [l for l in _lines(result, "3994") if l.laudus_code == "310011"]
    assert sade.odoo_account == "Assets:FFCC:InversionesSade"  # ya venía del colapso
    assert sade.sinc_naturaleza == "C"
    assert sade.sinc_flag == ""


def test_traspaso_sin_vehiculo_queda_sin_clasificar(result):
    (pata,) = [l for l in _lines(result, "29") if l.laudus_code == "310099"]
    assert pata.odoo_account.startswith("Income:")  # NO se re-rutea
    assert pata.sinc_flag == FLAG_SIN_CLASIFICAR
    assert pata.sinc_regla == "glosa:capital-sin-vehiculo"
    assert any(r.je_id == "29" for r in result.report.sin_clasificar)


def test_ambiguo_dividendo_nuevo_ciclo(result):
    """N-2 (AC5): pata en cuenta B con glosa 'Dividendo' → conflicto
    cuenta-vs-glosa → queda en Income + revisar (manda el epic)."""
    (pata,) = [l for l in _lines(result, "4158") if l.laudus_code == "310016"]
    assert pata.odoo_account.startswith("Income:")
    assert pata.sinc_naturaleza == "B"
    assert pata.sinc_regla == "cuenta-vs-glosa"
    assert pata.sinc_flag == FLAG_REVISAR
    assert any(r.je_id == "4158" for r in result.report.revisar)


def test_usd_intacta(result):
    lines = _lines(result, "9000003")
    (usd,) = [l for l in lines if l.currency == "USD"]
    assert usd.amount == Decimal("100.00")
    assert usd.sinc_naturaleza == ""  # cuentas de activo: fuera del universo


def test_input_no_mutado(moves, result):
    """`sincerar` es función pura: el output de `collapse` queda intacto."""
    (m1237,) = [m for m in moves if m.je_id == "1237"]
    assert all(l.sinc_naturaleza == "" for l in m1237.lines)
    assert any(l.odoo_account == "Income:Retiros Tecnión" for l in m1237.lines)


def test_reporte_cobertura(result):
    rep = result.report
    assert rep.por_naturaleza["B"] >= 5  # 1237 (5 patas) + 4158
    assert rep.por_naturaleza["C"] == 1  # Sade
    assert rep.por_naturaleza["G"] == 1  # id 29
    assert len(rep.sin_clasificar) == 1
    assert "sin clasificar=1" in rep.resumen()


# --- El contrato: run_tier_a verde tras el transformador (AC3, AC4) ---------


def test_run_tier_a_verde_post_sinceramiento(entries, result, table, aliases):
    run_tier_a(
        entries,
        result.moves,
        table,
        route=route_sincerado(table, aliases),
        excluded_je_ids=result.excluded_je_ids,
    )


def test_paridad_origen_0_diffs_post_sinceramiento(entries, result):
    from pipeline.odoo_migration.parity import verify_origin_parity

    assert verify_origin_parity(entries, result.moves) == []


# --- Mutaciones: el gate TIENE que poder fallar -----------------------------


def test_mutacion_excluir_media_pareja_falla(entries, moves, table):
    """Excluir UNA mitad del par wash (declarada) → el conjunto no netea → alarma."""
    solo_cierre = {("RUT2", "9000001")}
    filtered = [m for m in moves if (m.company, m.je_id) not in solo_cierre]
    problems = verify_counts(entries, filtered, excluded_je_ids=solo_cierre)
    assert any("NO netea" in p for p in problems)


def test_mutacion_vehiculo_equivocado_rompe_destino(entries, result, table, aliases):
    """Una pata B ruteada al vehículo equivocado descuadra el gate de destino
    (la paridad-origen NO lo ve — para eso existe FR12a)."""
    victima = next(
        l
        for m in result.moves
        for l in m.lines
        if l.odoo_account == "Assets:EAG:InvTecnion"
    )
    victima.odoo_account = "Assets:EAG:MBI"
    diffs = verify_destination(
        entries,
        result.moves,
        table,
        route=route_sincerado(table, aliases),
        excluded_je_ids=result.excluded_je_ids,
    )
    cuentas = {d.odoo_account for d in diffs}
    assert "Assets:EAG:InvTecnion" in cuentas
    assert "Assets:EAG:MBI" in cuentas
