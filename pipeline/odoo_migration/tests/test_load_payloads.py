"""Tests Tier A del payload builder (story E1.5) — Python puro, SIN Odoo.

Cubre: chart colapsado (aliases N→1, código representante, mapeo otype),
partners/analíticas desde la metadata E1.4, moves (signos, USD con
`amount_currency`, balance por move, campos x_laudus_*) y las MUTACIONES
obligatorias (un gate que no puede fallar es `tsc --noEmit`): otype corrupto /
inconsistente, USD sin price, move desbalanceado, colisión de slug.

Pins con literales derivados UNA vez (2026-07-25, patrón P-10) — no se
re-derivan llamando a los mismos helpers que se testean.
"""

import datetime
from decimal import Decimal

import pytest
from beancount import loader

from pipeline.odoo_migration.external_ids import analytic_xmlid, partner_xmlid, slug
from pipeline.odoo_migration.load import (
    ORIGIN_GROUP,
    OTYPE_TO_ACCOUNT_TYPE,
    LoadError,
    build_analytic,
    build_chart,
    build_moves,
    build_origin_accounts,
    build_partners,
)
from pipeline.odoo_migration.mapping import MappingRow, MappingTable, load_mapping_table
from pipeline.odoo_migration.dimensionar import dimensionar
from pipeline.odoo_migration.sincerar import load_alias_table, sincerar
from pipeline.odoo_migration.transform import OdooLineRecord, OdooMoveRecord, collapse

FIXTURE = "pipeline/odoo_migration/tests/fixtures/golden_slice.beancount"


@pytest.fixture(scope="module")
def table():
    return load_mapping_table()


@pytest.fixture(scope="module")
def golden_chain(table):
    """Cadena completa sobre el golden. Solo lectura (los tests de mutación
    construyen sus propios moves sintéticos)."""
    entries, errors, _ = loader.load_file(FIXTURE)
    assert errors == []
    aliases = load_alias_table()
    moves = collapse(entries, table)
    sinc = sincerar(moves, table, alias_table=aliases)
    dim = dimensionar(sinc.moves, table, alias_table=aliases)
    return dim.moves


@pytest.fixture(scope="module")
def golden_chart(table, golden_chain):
    """El chart que ve el loader: tabla colapsada + orígenes sincerados.
    El golden SÍ trae patas naturaleza-B reales (los retiros Tecnión del JE
    1237): E1.3 las re-rutea a 5 cuentas de ORIGEN `Assets:*:InvTecnion`
    (review P1)."""
    return build_chart(table) + build_origin_accounts(golden_chain, table)


def test_origenes_del_golden_pinneados(golden_chain, table):
    # Derivado una vez (2026-07-25): las 5 patas B del JE 1237 producen 5
    # cuentas de origen EAG (una por socio/hija con InvTecnion).
    origin = build_origin_accounts(golden_chain, table)
    assert [a.xmlid for a in origin] == [
        "accs_eag_assetseaginvtecnion",
        "accs_eag_assetsjaelinvtecnion",
        "accs_eag_assetsjeannetteinvtecnion",
        "accs_eag_assetsjocelyninvtecnion",
        "accs_eag_assetsjohannainvtecnion",
    ]
    assert all(a.account_type == "asset_current" for a in origin)
    assert all(a.x_laudus_group == ORIGIN_GROUP for a in origin)


# ---------------------------------------------------------------------------
# Chart colapsado
# ---------------------------------------------------------------------------


def test_chart_pinneado_full_tabla(table):
    chart = build_chart(table)
    # Derivado una vez (2026-07-25): 361 destinos colapsados, 79 con >1 código.
    assert len(chart) == 361
    assert sum(1 for a in chart if len(a.aliases) > 1) == 79
    # Cada fila de la tabla aporta exactamente UN alias acc_* (nada se pierde).
    assert sum(len(a.aliases) for a in chart) == len(table.rows)
    # Representantes únicos por compañía (la llave del upsert de cuentas).
    keys = [(a.company, a.code) for a in chart]
    assert len(keys) == len(set(keys))
    # El alias primario está entre los aliases, siempre.
    assert all(a.xmlid in a.aliases for a in chart)


def test_chart_cuenta_1a1_pinneada(table):
    # (EAG, 111005) Banco BCI — cuenta 1:1: conserva su código (spec §1.1).
    acc = {(a.company, a.code): a for a in build_chart(table)}[("EAG", "111005")]
    assert acc.name == "Bancos:Banco BCI - 10160175"
    assert acc.account_type == "asset_cash"
    assert acc.aliases == ("acc_eag_111005",)
    assert acc.xmlid == "acc_eag_111005"
    assert acc.x_laudus_group == "ACTIVOS CORRIENTES/DISPONIBLE - EAG"


def test_chart_colapso_alias_multiples_pinneado(table):
    # (RUT2, 'Donaciones') es el colapso más grande: 15 códigos → 1 cuenta,
    # representante = menor código (415055). Derivado una vez, 2026-07-25.
    donaciones = [
        a for a in build_chart(table) if a.company == "RUT2" and a.name == "Donaciones"
    ]
    assert len(donaciones) == 1
    acc = donaciones[0]
    assert acc.code == "415055"
    assert acc.xmlid == "acc_rut2_415055"
    assert len(acc.aliases) == 15
    # Representante en orden NUMÉRICO (largo, valor) — no el mismo min string
    # del builder, para que el pin no sea tautológico (review P7).
    assert acc.code == min((a.split("_")[-1] for a in acc.aliases), key=lambda c: (len(c), c))


def test_representante_orden_numerico_no_lexicografico():
    # "9999" < "111005" en orden numérico, pero > en orden string puro: el
    # representante debe ser el menor NUMÉRICO (spec §1.1 / review P7).
    rows = [_row("111005", odoo="X"), _row("9999", odoo="X")]
    [acc] = build_chart(_mini_table(rows))
    assert acc.code == "9999"
    assert acc.xmlid == "acc_eag_9999"
    assert set(acc.aliases) == {"acc_eag_9999", "acc_eag_111005"}


def test_otype_poblacion_cerrada_es_la_del_csv(table):
    # Los 7 valores reales del CSV — ni más ni menos (cierra defer E1.2).
    assert set(OTYPE_TO_ACCOUNT_TYPE) == {
        "asset", "bank", "receivable", "liability", "equity", "income", "expense",
    }
    assert {r.odoo_type for r in table.rows} <= set(OTYPE_TO_ACCOUNT_TYPE)


def _mini_table(rows):
    return MappingTable(rows, [])


def _row(code, entity="EAG", odoo="Caja", otype="asset"):
    return MappingRow(
        code=code, entity=entity, company="EAG" if entity == "EAG" else "RUT2",
        name=f"cuenta {code}", odoo_account=odoo, odoo_type=otype, sinc="", flag="",
    )


def test_mutacion_otype_desconocido_acusa():
    with pytest.raises(LoadError, match="desconocido"):
        build_chart(_mini_table([_row("111001", otype="aktiv")]))


def test_mutacion_otype_vacio_acusa():
    with pytest.raises(LoadError, match="desconocido"):
        build_chart(_mini_table([_row("111001", otype="")]))


def test_mutacion_otype_inconsistente_en_colapso_acusa():
    # Dos códigos → mismo destino con otype distinto = cuenta de tipo ambiguo.
    rows = [_row("111001", otype="asset"), _row("111002", otype="expense")]
    with pytest.raises(LoadError, match="INCONSISTENTE"):
        build_chart(_mini_table(rows))


# ---------------------------------------------------------------------------
# Partners + analíticas
# ---------------------------------------------------------------------------


def _linea(**kw):
    base = dict(
        n=0, odoo_account="Caja", laudus_code="111005", entity="EAG",
        currency="CLP", amount=Decimal("100"), desc="",
    )
    base.update(kw)
    return OdooLineRecord(**base)


def _move(lines, je_id="9100001", company="EAG"):
    return OdooMoveRecord(
        company=company, je_id=je_id, date=datetime.date(2022, 1, 1),
        narration="sintético", lines=list(lines),
    )


#: Chart mínimo para los moves sintéticos (la _linea default rutea a Caja).
def _chart_caja(extra_rows=()):
    return build_chart(_mini_table([_row("111005"), *extra_rows]))


def test_golden_sin_partners_y_analiticas_solo_entidad(golden_chain):
    # El golden NO trae columnas de dims/partner pobladas (verificado E1.4) —
    # la única analítica es la entidad, que E1.5 estampa desde line.entity.
    assert build_partners(golden_chain) == []
    analytic = build_analytic(golden_chain)
    assert [(a.xmlid, a.plan, a.name) for a in analytic] == [
        ("aa_entidad_eag", "entidad", "EAG"),
        ("aa_entidad_ffcc", "entidad", "FFCC"),
        ("aa_entidad_jael", "entidad", "Jael"),
        ("aa_entidad_jeannette", "entidad", "Jeannette"),
        ("aa_entidad_jocelyn", "entidad", "Jocelyn"),
        ("aa_entidad_johanna", "entidad", "Johanna"),
    ]
    assert all(a.plan_xmlid == "x_laudus_migration.plan_entidad" for a in analytic)


def test_metadata_sintetica_produce_partner_y_dims():
    # El write-path de partner/dims se prueba con metadata estampada a mano
    # (lección E1.4: no buscar cobertura golden que no existe).
    lines = [
        _linea(partner="José Alazraki", partner_categoria="socio-particion",
               dim_propiedad="Vía Gris", amount=Decimal("100")),
        _linea(n=1, dim_socio_uso="DAG", amount=Decimal("-100")),
    ]
    moves = [_move(lines)]
    partners = build_partners(moves)
    assert [(p.xmlid, p.name) for p in partners] == [("prt_josealazraki", "José Alazraki")]
    analytic = {(a.plan, a.name): a.xmlid for a in build_analytic(moves)}
    assert analytic[("propiedad_objeto", "Vía Gris")] == "aa_propiedadobjeto_viagris"
    assert analytic[("socio_uso", "DAG")] == "aa_sociouso_dag"
    assert analytic[("entidad", "EAG")] == "aa_entidad_eag"

    [payload] = build_moves(moves, _chart_caja())
    l0, l1 = payload.lines
    assert l0.partner_xmlid == "prt_josealazraki"
    assert l0.analytic_xmlids == ("aa_entidad_eag", "aa_propiedadobjeto_viagris")
    assert l1.partner_xmlid is None
    assert l1.analytic_xmlids == ("aa_entidad_eag", "aa_sociouso_dag")


def test_mutacion_colision_de_slug_acusa():
    # Dos canónicos DISTINTOS que slugifican igual → el upsert pisaría uno.
    lines = [
        _linea(partner="José Alazraki", amount=Decimal("100")),
        _linea(n=1, partner="Jose alazraki", amount=Decimal("-100")),
    ]
    with pytest.raises(LoadError, match="colisión de slug"):
        build_partners([_move(lines)])


def test_slug_sin_caracteres_rescatables_acusa():
    with pytest.raises(ValueError, match="vacío"):
        slug("¡¿·!")
    # Y los helpers lo propagan (población cerrada: mejor reventar que un
    # xmlid sin identidad).
    with pytest.raises(ValueError):
        partner_xmlid("···")
    with pytest.raises(ValueError):
        analytic_xmlid("entidad", "¡!")


# ---------------------------------------------------------------------------
# Moves — golden end-to-end
# ---------------------------------------------------------------------------


def test_moves_golden_pinneados(golden_chain, golden_chart):
    payloads = build_moves(golden_chain, golden_chart)
    # 7 asientos del slice − 2 washes excluidos por E1.3 = 5. Los washes
    # (9000001/9000002) NO llegan al loader — la base del AC3.
    assert sorted(m.xmlid for m in payloads) == [
        "mv_eag_1237", "mv_eag_29", "mv_eag_4158", "mv_eag_9000003", "mv_rut2_3994",
    ]
    by_id = {m.xmlid: m for m in payloads}
    assert by_id["mv_rut2_3994"].journal_code == "LAU2"
    assert by_id["mv_eag_29"].journal_code == "LAU1"
    # Todos balancean en CLP y toda línea lleva su entidad como analítica.
    for m in payloads:
        assert sum(l.debit - l.credit for l in m.lines) == 0
        for l in m.lines:
            assert l.x_laudus_account_code
            assert l.x_laudus_entity
            assert any(x.startswith("aa_entidad_") for x in l.analytic_xmlids)


def test_move_clp_signos_y_campos(golden_chain, golden_chart):
    # JE 1234 (id 1237): retiro repartido EAG + 4 hijas, 10 patas CLP.
    [m] = [m for m in build_moves(golden_chain, golden_chart) if m.xmlid == "mv_eag_1237"]
    assert m.x_laudus_je_id == "1237"
    assert m.date == datetime.date(2022, 3, 23)
    assert len(m.lines) == 10
    l0 = m.lines[0]  # +1.022.700.000 banco EAG → debit
    assert l0.xmlid == "aml_eag_1237_0"
    assert (l0.debit, l0.credit) == (Decimal("1022700000.00"), Decimal("0"))
    assert l0.currency is None and l0.amount_currency is None
    l1 = m.lines[1]  # −1.022.700.000 ingreso → credit
    assert (l1.debit, l1.credit) == (Decimal("0"), Decimal("1022700000.00"))
    # La pata de Jocelyn viaja a la MISMA compañía EAG con su entidad propia.
    l2 = m.lines[2]
    assert l2.x_laudus_entity == "Jocelyn"
    assert "aa_entidad_jocelyn" in l2.analytic_xmlids


def test_move_usd_amount_currency_pinneado(golden_chain, golden_chart):
    # AC4: 100.00 USD @ 800.00 CLP → debit 80.000 CLP + amount_currency 100.
    [m] = [m for m in build_moves(golden_chain, golden_chart) if m.xmlid == "mv_eag_9000003"]
    usd, clp = m.lines
    assert usd.xmlid == "aml_eag_9000003_0"
    assert usd.currency == "USD"
    assert usd.amount_currency == Decimal("100.00")
    assert (usd.debit, usd.credit) == (Decimal("80000"), Decimal("0"))
    assert clp.currency is None
    assert (clp.debit, clp.credit) == (Decimal("0"), Decimal("80000.00"))


def test_mutacion_usd_sin_price_acusa():
    move = _move([
        _linea(currency="USD", amount=Decimal("100"), price=None),
        _linea(n=1, amount=Decimal("-80000")),
    ])
    with pytest.raises(LoadError, match="SIN price"):
        build_moves([move], _chart_caja())


def test_mutacion_move_desbalanceado_acusa():
    move = _move([
        _linea(amount=Decimal("100")),
        _linea(n=1, amount=Decimal("-99")),
    ])
    with pytest.raises(LoadError, match="NO\\s+balancea"):
        build_moves([move], _chart_caja())


def test_mutacion_company_sin_diario_acusa():
    move = _move([_linea(amount=Decimal("0"))], company="ACME")
    with pytest.raises(LoadError, match="sin diario"):
        build_moves([move], [])


def test_contravalor_usd_quantize_half_up():
    # Precio real no-redondo: 100 USD @ 836.475 → 83.647,5 → 83.648 CLP
    # (half-up, la MISMA cuantización que Odoo aplica al escribir la línea).
    # Sin quantize el balance check exacto reventaría o —peor— dejaría pasar
    # un move que Odoo postea desbalanceado tras redondear (review P5).
    move = _move([
        _linea(currency="USD", amount=Decimal("100"), price=Decimal("836.475")),
        _linea(n=1, amount=Decimal("-83648")),
    ])
    [payload] = build_moves([move], _chart_caja())
    usd, clp = payload.lines
    assert (usd.debit, usd.credit) == (Decimal("83648"), Decimal("0"))
    assert usd.amount_currency == Decimal("100")
    assert (clp.debit, clp.credit) == (Decimal("0"), Decimal("83648"))


def test_name_de_linea_cae_al_ref_del_move():
    # El fallback desc-vacía→ref vive en el BUILDER (Tier A), no en la capa
    # RPC: el payload ES lo que aterriza en Odoo (review P8).
    [payload] = build_moves(
        [_move([_linea(desc=""), _linea(n=1, amount=Decimal("-100"), desc="x")])],
        _chart_caja(),
    )
    assert payload.lines[0].name == "sintético"
    assert payload.lines[1].name == "x"


def test_mutacion_je_id_duplicado_acusa():
    # Dos moves con el mismo (company, je_id) → mismo mv_*: el upsert los
    # crearía dos veces y ir.model.data reventaría DESPUÉS de escribir (P10).
    moves = [
        _move([_linea(), _linea(n=1, amount=Decimal("-100"))]),
        _move([_linea(), _linea(n=1, amount=Decimal("-100"))]),
    ]
    with pytest.raises(LoadError, match="duplicado"):
        build_moves(moves, _chart_caja())


# ---------------------------------------------------------------------------
# Ruteo por destino (review P1) — la pata sincerada va a SU cuenta final
# ---------------------------------------------------------------------------


def test_linea_sincerada_rutea_al_destino_final_no_al_colapso():
    # E1.3 reescribe odoo_account (destino sincerado) SIN tocar laudus_code.
    # La pata debe rutear a la cuenta del DESTINO (115001), no al colapso de
    # su código (111005 → Caja); x_laudus_account_code conserva el código.
    chart = _chart_caja(extra_rows=[_row("115001", odoo="Socios:CtaCte", otype="receivable")])
    lines = [
        _linea(odoo_account="Socios:CtaCte"),  # sincerada: código 111005, destino socios
        _linea(n=1, amount=Decimal("-100")),   # normal: colapso Caja
    ]
    [payload] = build_moves([_move(lines)], chart)
    sincerada, normal = payload.lines
    assert sincerada.account_xmlid == "acc_eag_115001"
    assert sincerada.x_laudus_account_code == "111005"
    assert normal.account_xmlid == "acc_eag_111005"


def test_destino_origen_fuera_de_tabla_entra_al_chart_y_rutea():
    # Destino sincerado que NO existe en la tabla (cuenta de ORIGEN E1.3):
    # build_origin_accounts la agrega con xmlid accs_* y build_moves la rutea.
    table = _mini_table([_row("111005")])
    lines = [
        _linea(odoo_account="Assets:EAG:JuliusBaer"),
        _linea(n=1, amount=Decimal("-100")),
    ]
    moves = [_move(lines)]
    origin = build_origin_accounts(moves, table)
    assert [(a.xmlid, a.company, a.name, a.account_type, a.code, a.x_laudus_group)
            for a in origin] == [
        ("accs_eag_assetseagjuliusbaer", "EAG", "Assets:EAG:JuliusBaer",
         "asset_current", "assetseagjuliusbaer", ORIGIN_GROUP),
    ]
    assert origin[0].aliases == ("accs_eag_assetseagjuliusbaer",)

    chart = build_chart(table) + origin
    [payload] = build_moves(moves, chart)
    assert payload.lines[0].account_xmlid == "accs_eag_assetseagjuliusbaer"


def test_mutacion_destino_sin_cuenta_en_chart_acusa():
    lines = [_linea(odoo_account="Socios:NoExiste"), _linea(n=1, amount=Decimal("-100"))]
    with pytest.raises(LoadError, match="no está en el chart"):
        build_moves([_move(lines)], _chart_caja())


def test_mutacion_origen_no_asset_acusa():
    # Población cerrada de orígenes E1.3: hoy todos son Assets:*; otro root
    # es una regla nueva sin mapear, no un tipo para adivinar.
    table = _mini_table([_row("111005")])
    moves = [_move([_linea(odoo_account="Gastos:Misterio")])]
    with pytest.raises(LoadError, match="no es una cuenta de activo"):
        build_origin_accounts(moves, table)


def test_price_viaja_desde_el_mirror(golden_chain):
    # El defer E1.2 quedó cerrado: la pata USD del golden trae su precio.
    for move in golden_chain:
        for line in move.lines:
            if line.currency == "USD":
                assert line.price == Decimal("800.00")
                return
    pytest.fail("el golden perdió su pata USD (guardrail E1.0)")
