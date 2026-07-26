"""Tests Tier A del verificador lado-Odoo (story E1.6) — Python puro, SIN Odoo.

Cubre: lado esperado (origen == mirror puro, destino desde los payloads,
conteos derivados), el check de sinceramiento (Δ DIRECCIONAL pre−post, pinneado
FR12c sobre el mirror completo), la selección determinística del muestreo
(seed pinneada), los diffs de los 3 planos con MUTACIONES (un gate que no puede
fallar es `tsc --noEmit`), los diffs programáticos de `ParityError` (cierra
defer E1.2) y el reporte de muestreo (determinístico, con firma y anexos).

Pins con literales derivados UNA vez (2026-07-26, patrón P-10) — no se
re-derivan llamando a los mismos helpers que se testean. Los ÚNICOS pins
literales son del golden; los conteos full-mirror se derivan en runtime
(D-1 abierta los movería — guarda de la story).
"""

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from beancount import loader

from pipeline.odoo_migration.dimensionar import dimensionar
from pipeline.odoo_migration.load import (
    build_chart,
    build_moves,
    build_origin_accounts,
)
from pipeline.odoo_migration.mapping import load_mapping_table
from pipeline.odoo_migration.parity import ParityError, laudus_balances, run_tier_a
from pipeline.odoo_migration.sincerar import load_alias_table, sincerar
from pipeline.odoo_migration.transform import collapse
from pipeline.odoo_migration.verify_odoo import (
    CODIGO_APERTURA,
    MUESTREO_SEED,
    SINCERAMIENTO_DELTA_FULL,
    ExpectedCounts,
    OdooCounts,
    build_muestreo_report,
    diff_counts,
    diff_destination,
    diff_origin,
    expected_counts,
    expected_destination,
    expected_origin,
    glosa_histogram,
    select_sample,
    sinceramiento_check,
)

FIXTURE = "pipeline/odoo_migration/tests/fixtures/golden_slice.beancount"


@pytest.fixture(scope="module")
def table():
    return load_mapping_table()


@pytest.fixture(scope="module")
def golden(table):
    """(entries, moves colapsados, result sincerar, moves dimensionados,
    payloads) sobre el golden. Solo lectura."""
    entries, errors, _ = loader.load_file(FIXTURE)
    assert errors == []
    aliases = load_alias_table()
    moves = collapse(entries, table)
    sinc = sincerar(moves, table, alias_table=aliases)
    dim = dimensionar(sinc.moves, table, alias_table=aliases)
    chart = build_chart(table) + build_origin_accounts(dim.moves, table)
    payloads = build_moves(dim.moves, chart)
    return entries, moves, sinc, dim.moves, payloads


# ---------------------------------------------------------------------------
# Lado esperado (Task 1)
# ---------------------------------------------------------------------------


def test_expected_origin_es_laudus_balances():
    # El AC lo exige textual: reusar el agrupador de E1.2 TAL CUAL — el mismo
    # (company, code, currency) que ya dio 0 diffs en el Tier B de E1.5. No un
    # wrapper, no otro agregador: EL MISMO objeto función.
    assert expected_origin is laudus_balances


def test_expected_destination_golden_pinneado(golden):
    *_, payloads = golden
    dest = expected_destination(payloads)
    # Derivado una vez (2026-07-26): 16 destinos con movimiento en el golden,
    # incluidas las 5 cuentas de ORIGEN SINCERADO reales (las patas
    # naturaleza-B del JE 1237 → Assets:*:InvTecnion, lección P1).
    assert len(dest) == 16
    accs = {k: v for k, v in dest.items() if k[1].startswith("accs_")}
    assert accs == {
        ("EAG", "accs_eag_assetseaginvtecnion"): Decimal("-1022700000"),
        ("EAG", "accs_eag_assetsjaelinvtecnion"): Decimal("-170450000"),
        ("EAG", "accs_eag_assetsjeannetteinvtecnion"): Decimal("-170450000"),
        ("EAG", "accs_eag_assetsjocelyninvtecnion"): Decimal("-170450000"),
        ("EAG", "accs_eag_assetsjohannainvtecnion"): Decimal("-170450000"),
    }
    # Todos los moves balancean → el libro completo suma 0 (invariante).
    assert sum(dest.values(), Decimal(0)) == 0


def test_expected_counts_golden_pinneado(golden):
    *_, payloads = golden
    counts = expected_counts(payloads)
    assert counts.n_moves == 5
    assert counts.n_lines == 18
    assert counts.identities == frozenset({
        ("EAG", "29"), ("EAG", "1237"), ("EAG", "4158"),
        ("EAG", "9000003"), ("RUT2", "3994"),
    })
    # En el GOLDEN 211005 queda sin líneas (su único uso era el par wash
    # excluido) — pero el valor está DERIVADO del payload, no pinneado en el
    # verificador: en el full history sobreviven 2 patas sin par.
    assert counts.lines_211005 == (0, Decimal(0))


def test_sinceramiento_check_golden(golden):
    _, _, _, dim_moves, _ = golden
    delta, por_destino = sinceramiento_check(dim_moves)
    # Derivado una vez (2026-07-26): las 5 patas B del JE 1237 salen de Income
    # hacia sus activos de origen. El Δ es DIRECCIONAL pre − post (negativo:
    # el ingreso BAJA).
    assert delta == Decimal("-1704500000")
    assert por_destino == {
        ("EAG", "Assets:EAG:InvTecnion"): Decimal("-1022700000"),
        ("EAG", "Assets:Jael:InvTecnion"): Decimal("-170450000"),
        ("EAG", "Assets:Jeannette:InvTecnion"): Decimal("-170450000"),
        ("EAG", "Assets:Jocelyn:InvTecnion"): Decimal("-170450000"),
        ("EAG", "Assets:Johanna:InvTecnion"): Decimal("-170450000"),
    }
    # Coherencia interna: el Δ es exactamente lo que aterrizó en los destinos.
    assert sum(por_destino.values(), Decimal(0)) == delta


def test_sinceramiento_check_pata_no_clp_falla_con_alarma():
    # Nunca en silencio: una pata sincerada no-CLP subestimaría el Δ FR12c
    # (que se calcula en CLP) — caso nuevo debe reventar con contexto, no
    # descartarse del filtro.
    line = SimpleNamespace(
        sinc_naturaleza="B",
        odoo_account="Assets:EAG:InvTecnion",
        odoo_account_colapso="Income:EAG:Otros",
        currency="USD",
        amount=Decimal("-100"),
        entity="EAG",
        laudus_code="310013",
    )
    with pytest.raises(RuntimeError, match="no-CLP"):
        sinceramiento_check([SimpleNamespace(lines=(line,))])


def test_sinceramiento_delta_full_mirror_pinneado(full_mirror_chain):
    """AC2 — la cifra FR12c, DIRECCIONAL: `pre − post == −45.576.501.123`
    (la expresión EXACTA de `test_sinceramiento_full_mirror.py`; un
    `post − pre` natural da +45.576B y falla). Derivada acá de las LÍNEAS
    ruteadas — otra ruta que la del gate original, mismo número."""
    *_, result = full_mirror_chain
    delta, por_destino = sinceramiento_check(result.moves)
    assert delta == SINCERAMIENTO_DELTA_FULL
    assert sum(por_destino.values(), Decimal(0)) == delta
    # Molco NO está acá: E (gasto) ya viene ruteado a nivel cuenta por la
    # tabla, no por el sinceramiento de patas ("activos de origen" del AC es
    # shorthand del epic).
    assert not any("Molco" in k[1] for k in por_destino)


# ---------------------------------------------------------------------------
# Muestreo dirigido (Task 3)
# ---------------------------------------------------------------------------


def _fake_move(xmlid: str, debit: int):
    return SimpleNamespace(
        xmlid=xmlid,
        lines=(SimpleNamespace(debit=Decimal(debit)),),
    )


def test_select_sample_golden_todos_sin_duplicar(golden):
    *_, payloads = golden
    # Con 5 moves: los 5 salen (top los absorbe), sin duplicar.
    sample = select_sample(payloads)
    assert sorted(m.xmlid for m in sample) == sorted(m.xmlid for m in payloads)
    assert len(sample) == len({m.xmlid for m in sample}) == 5
    # Pinneado (derivado una vez, 2026-07-26): orden por magnitud descendente.
    assert [m.xmlid for m in sample] == [
        "mv_rut2_3994", "mv_eag_1237", "mv_eag_4158", "mv_eag_29",
        "mv_eag_9000003",
    ]


def test_select_sample_estable_y_sin_solape():
    # 50 moves sintéticos: 20 mayores + 20 aleatorios del RESTO (si un move
    # está en ambos grupos, el aleatorio toma el siguiente — sin reposición
    # sobre el pool depurado). Misma selección en cada corrida (NFR1).
    payloads = [_fake_move(f"mv_eag_{i:03d}", debit=1000 - i) for i in range(50)]
    sample_1 = select_sample(payloads)
    sample_2 = select_sample(payloads)
    assert [m.xmlid for m in sample_1] == [m.xmlid for m in sample_2]
    assert len(sample_1) == 40
    assert len({m.xmlid for m in sample_1}) == 40
    # Los 20 primeros son EXACTAMENTE los de mayor Σ debit (000..019).
    assert [m.xmlid for m in sample_1[:20]] == [f"mv_eag_{i:03d}" for i in range(20)]
    # Los 20 aleatorios salen del resto (020..049), nunca del top.
    assert all(int(m.xmlid.split("_")[-1]) >= 20 for m in sample_1[20:])
    assert MUESTREO_SEED == 20260723  # la seed es un literal pinneado (NFR1)


def test_select_sample_seed_distinta_cambia_la_muestra():
    # El gate puede fallar: la selección NO es independiente de la seed (si lo
    # fuera, "determinístico" sería vacuo).
    payloads = [_fake_move(f"mv_eag_{i:03d}", debit=1000 - i) for i in range(50)]
    con_pin = select_sample(payloads)
    con_otra = select_sample(payloads, seed=999)
    assert [m.xmlid for m in con_pin] != [m.xmlid for m in con_otra]


# ---------------------------------------------------------------------------
# Diffs de los 3 planos — mutaciones puras (Task 2)
# ---------------------------------------------------------------------------


def test_diff_origin_0_diffs_y_wash_ausente_ok():
    expected = {
        ("EAG", "111005", "CLP"): Decimal("500"),
        ("RUT2", "211005", "CLP"): Decimal("0"),  # wash excluido: netea a 0
    }
    odoo = {("EAG", "111005", "CLP"): Decimal("500.00")}
    # Código ausente en Odoo con saldo mirror 0 → OK (patrón AC3 E1.5).
    assert diff_origin(expected, odoo) == []


def test_diff_origin_acusa_mutacion_y_ausencia_con_saldo():
    expected = {
        ("EAG", "111005", "CLP"): Decimal("500"),
        ("EAG", "310013", "CLP"): Decimal("-100"),
    }
    odoo = {("EAG", "111005", "CLP"): Decimal("501.00")}  # mutado +1
    diffs = diff_origin(expected, odoo)
    assert [(d.company, d.code, d.currency, d.diff) for d in diffs] == [
        ("EAG", "111005", "CLP", Decimal("-1.00")),
        ("EAG", "310013", "CLP", Decimal("-100")),  # ausente con saldo ≠ 0
    ]


def test_diff_origin_no_diff_fantasma_por_decimales():
    # Odoo redondea `amount_currency` a la precisión de la moneda al escribir
    # (loader_rpc._f): un monto no-CLP del mirror con >2 decimales NO debe dar
    # diff fantasma — ambos lados se comparan cuantizados a 0.01 (HALF_UP).
    expected = {("EAG", "111007", "USD"): Decimal("100.005")}
    odoo = {("EAG", "111007", "USD"): Decimal("100.01")}
    assert diff_origin(expected, odoo) == []


def test_diff_origin_acusa_saldo_fantasma_en_odoo():
    # Odoo tiene un código que el mirror no conoce → diff, nunca silencio.
    diffs = diff_origin({}, {("EAG", "999999", "CLP"): Decimal("7.00")})
    assert len(diffs) == 1
    assert diffs[0].laudus == Decimal(0)


def test_diff_destination_resuelve_alias_n_a_1():
    # El chart colapsado: 2 alias acc_* → el MISMO res_id (7). El esperado usa
    # el REPRESENTANTE; el matching debe encontrarlo entre los N nombres.
    expected = {("EAG", "acc_eag_415055"): Decimal("300")}
    odoo = {("EAG", 7): Decimal("300.00")}
    xmlids = {7: ("acc_eag_415055", "acc_eag_415056")}
    assert diff_destination(expected, odoo, xmlids) == []


def test_diff_destination_acusa_linea_movida_de_cuenta():
    # La mutación P1: una línea movida de cuenta re-agrupa `balance` — el
    # plano destino la ve como DOS diffs (una cuenta de más, otra de menos).
    expected = {
        ("EAG", "acc_eag_111005"): Decimal("500"),
        ("EAG", "accs_eag_assetseaginvtecnion"): Decimal("-500"),
    }
    odoo = {("EAG", 1): Decimal("400.00"), ("EAG", 2): Decimal("-400.00")}
    xmlids = {1: ("acc_eag_111005",), 2: ("accs_eag_assetseaginvtecnion",)}
    diffs = diff_destination(expected, odoo, xmlids)
    assert [(d.account_xmlid, d.diff) for d in diffs] == [
        ("acc_eag_111005", Decimal("100.00")),
        ("accs_eag_assetseaginvtecnion", Decimal("-100.00")),
    ]


def test_diff_destination_acusa_cuenta_sin_xmlid():
    # Saldo en una cuenta fuera del namespace __laudus__: nadie más escribe en
    # esta db → diff etiquetado, no silencio.
    diffs = diff_destination({}, {("EAG", 99): Decimal("10.00")}, {})
    assert len(diffs) == 1
    assert "account_id=99" in diffs[0].account_xmlid


def _expected_counts_simple():
    return ExpectedCounts(
        n_moves=2,
        n_lines=4,
        identities=frozenset({("EAG", "1"), ("RUT2", "2")}),
        lines_211005=(0, Decimal(0)),
    )


def _odoo_counts(**overrides):
    base = dict(
        identities=(("EAG", "1"), ("RUT2", "2")),
        n_lines=4,
        non_posted=(),
        incomplete_lines=0,
        lines_211005=(0, Decimal(0)),
    )
    base.update(overrides)
    return OdooCounts(**base)


def test_diff_counts_verde():
    assert diff_counts(_expected_counts_simple(), _odoo_counts()) == []


@pytest.mark.parametrize(
    "overrides, fragmento",
    [
        (dict(identities=(("EAG", "1"),), n_lines=2), "AUSENTES"),
        (dict(identities=(("EAG", "1"), ("RUT2", "2"), ("EAG", "9"))), "NO emitió"),
        (dict(identities=(("EAG", "1"), ("EAG", "1"), ("RUT2", "2"))), "DUPLICADAS"),
        (dict(n_lines=5), "líneas"),
        (dict(non_posted=(("EAG", "1"),)), "NO posteados"),
        (dict(incomplete_lines=3), "x_laudus_"),
        (dict(lines_211005=(1, Decimal("-751912981"))), CODIGO_APERTURA),
    ],
)
def test_diff_counts_acusa_cada_invariante(overrides, fragmento):
    problems = diff_counts(_expected_counts_simple(), _odoo_counts(**overrides))
    assert problems, overrides
    assert any(fragmento in p for p in problems), (problems, fragmento)


def test_diff_counts_211005_derivado_no_pinneado():
    # La guarda del review de story: en el full history 211005 SÍ existe en
    # Odoo (2 patas sin par, Σ −751.912.981). Si el payload lo emite y Odoo lo
    # tiene, NO es diff — un "invariante 211005 vacía" daría falsa alarma.
    expected = ExpectedCounts(
        n_moves=1, n_lines=2,
        identities=frozenset({("RUT2", "5")}),
        lines_211005=(2, Decimal("-751912981")),
    )
    odoo = _odoo_counts(
        identities=(("RUT2", "5"),), n_lines=2,
        lines_211005=(2, Decimal("-751912981.00")),
    )
    assert diff_counts(expected, odoo) == []


# ---------------------------------------------------------------------------
# ParityError con diffs programáticos (cierra defer E1.2)
# ---------------------------------------------------------------------------


def test_parity_error_diffs_programaticos(golden, table):
    import dataclasses

    entries, moves, *_ = golden
    # Mutación sobre el COLAPSO (sin sinceramiento — mismo setup que
    # test_parity_tier_a): un monto alterado rompe origen Y destino.
    mutated = [dataclasses.replace(m, lines=list(m.lines)) for m in moves]
    mutated[0].lines[0] = dataclasses.replace(
        mutated[0].lines[0], amount=mutated[0].lines[0].amount + Decimal("1000")
    )
    with pytest.raises(ParityError) as exc_info:
        run_tier_a(entries, mutated, table)
    exc = exc_info.value
    # Los diffs COMPLETOS viajan como atributos, no solo 5 reprs en el mensaje.
    assert exc.origin_diffs, "origin_diffs vacío — el defer E1.2 no está cerrado"
    assert exc.destination_diffs
    assert all(d.diff != 0 for d in exc.origin_diffs)
    assert exc.count_diffs == []  # el conteo de moves/líneas no cambió
    assert "Tier A FAIL" in str(exc)  # el mensaje NO cambió de formato


def test_parity_error_default_sin_diffs():
    # Construcción pelada (tests existentes / callers viejos): atributos vacíos.
    exc = ParityError("mensaje")
    assert (exc.origin_diffs, exc.destination_diffs, exc.count_diffs) == ([], [], [])


# ---------------------------------------------------------------------------
# Histograma de glosa + reporte (Task 3)
# ---------------------------------------------------------------------------


def test_glosa_histogram_normaliza_y_ordena():
    refs = [
        SimpleNamespace(desc="Traspaso  Fondos"),
        SimpleNamespace(desc="traspaso fondos"),  # misma glosa normalizada
        SimpleNamespace(desc="TRASPASO FONDOS"),
        SimpleNamespace(desc="Abono único"),
        SimpleNamespace(desc=""),
    ]
    assert glosa_histogram(refs) == [
        ("traspaso fondos", 3),
        ("(glosa vacía)", 1),
        ("abono unico", 1),
    ]


def _fake_payload_move():
    line = SimpleNamespace(
        xmlid="aml_eag_1237_0",
        x_laudus_account_code="310013",
        account_xmlid="accs_eag_assetseaginvtecnion",
        debit=Decimal("0"),
        credit=Decimal("100"),
        partner_xmlid=None,
    )
    line_2 = SimpleNamespace(
        xmlid="aml_eag_1237_1",
        x_laudus_account_code="111005",
        account_xmlid="acc_eag_111005",
        debit=Decimal("100"),
        credit=Decimal("0"),
        partner_xmlid="prt_josealazraki",
    )
    return SimpleNamespace(
        xmlid="mv_eag_1237",
        company="EAG",
        x_laudus_je_id="1237",
        date=datetime.date(2023, 5, 2),
        ref="Retiro Tecnión",
        lines=(line, line_2),
    )


def test_reporte_muestreo_deterministico_y_con_firma():
    move = _fake_payload_move()
    odoo_rows = {
        "mv_eag_1237": [
            # PRIMERA de la lista una fila que el payload NO emitió: un pareo
            # posicional la cruzaría con la línea 0 del payload; el pareo por
            # identidad `aml_*` la manda a la tabla de EXTRA.
            {
                "xmlid": None,
                "x_laudus_account_code": "999999",
                "account_id": [9, "Cuenta Fantasma"],
                "partner_id": False,
                "currency_id": [44, "CLP"],
                "amount_currency": 7.0,
                "analytic_distribution": None,
                "debit": 7.0,
                "credit": 0.0,
            },
            {
                "xmlid": "aml_eag_1237_0",
                "x_laudus_account_code": "310013",
                "account_id": [7, "assetseaginvtecnion InvTecnion"],
                "partner_id": False,
                "currency_id": [44, "CLP"],
                "amount_currency": -100.0,
                "analytic_distribution": {"3": 100},
                "debit": 0.0,
                "credit": 100.0,
            },
            # aml_eag_1237_1 no está en Odoo → se reporta AUSENTE.
        ]
    }
    report_1 = build_muestreo_report(
        [move], odoo_rows, analytic_names={"3": "entidad:EAG"}
    )
    report_2 = build_muestreo_report(
        [move], odoo_rows, analytic_names={"3": "entidad:EAG"}
    )
    assert report_1 == report_2  # sin timestamps: 2 corridas → mismo archivo
    assert "## Firma" in report_1
    assert "| Valentina |" in report_1
    # Pareo por IDENTIDAD: la línea 0 del payload muestra la cuenta y los
    # montos LEÍDOS de Odoo de SU fila aml_*, no de la primera de la lista.
    assert "assetseaginvtecnion InvTecnion" in report_1
    assert "| 0 / 0.00 | 100 / 100.00 |" in report_1  # esperado / Odoo
    assert "entidad:EAG" in report_1
    assert "LÍNEA AUSENTE" in report_1  # el reporte acusa, no rellena
    # La fila EXTRA se VUELCA con sus datos (lo sospechoso, a la vista):
    assert "que el payload NO emitió" in report_1
    assert "Cuenta Fantasma" in report_1
    assert "999999" in report_1


def test_reporte_anexo_cobertura_glosa():
    sinc_report = SimpleNamespace(
        resumen=lambda: "cobertura sinceramiento: G=2 | sin clasificar=2 | revisar=0",
        sin_clasificar=[
            SimpleNamespace(desc="abono sin origen"),
            SimpleNamespace(desc="Abono SIN origen"),
        ],
    )
    dim_report = SimpleNamespace(
        resumen=lambda: "cobertura dimensionado: sin match=1",
        sin_match=[
            SimpleNamespace(
                company="EAG", je_id="42", code="310030",
                desc="pago a persona x", regla="glosa:ambigua",
            )
        ],
    )
    report = build_muestreo_report(
        [], {}, sinc_report=sinc_report, dim_report=dim_report
    )
    assert "Cobertura de glosa" in report
    assert "| abono sin origen | 2 |" in report  # histograma normalizado
    assert "| EAG | 42 | 310030 | pago a persona x | glosa:ambigua |" in report


def test_reporte_escapa_pipes_en_celdas():
    # Una glosa Laudus con `|` correría las columnas del documento firmado.
    dim_report = SimpleNamespace(
        resumen=lambda: "cobertura dimensionado: sin match=1",
        sin_match=[
            SimpleNamespace(
                company="EAG", je_id="42", code="310030",
                desc="pago | raro", regla="glosa:ambigua",
            )
        ],
    )
    report = build_muestreo_report([], {}, dim_report=dim_report)
    assert "pago \\| raro" in report
