"""Tests del transformador de dimensiones + partners (E1.4).

Dos niveles (story Dev Notes): unit con casos sintéticos (el golden slice está
curado para naturalezas — NO tiene 115xxx ni columnas prop/area/partner
pobladas), y sobre el golden solo la invariante estructural + `run_tier_a`
verde con la cadena de 3. El gate de partición con data real vive en
`test_dimensionado_full_mirror.py`.
"""

import dataclasses
import datetime
import os
from decimal import Decimal

import pytest
from beancount import loader

from pipeline.odoo_migration.dimensionar import (
    CAT_BENEFICIARIO,
    CAT_BUCKET,
    CAT_DEUDOR,
    CAT_RENDICION_P7,
    CAT_SOCIO_DISPERSO,
    CAT_SOCIO_PARTICION,
    PARTICION_CODES,
    PARTNER_CANONICO,
    PARTNER_PIN,
    SOCIO_CANONICO,
    dimensionar,
    verify_particion,
)
from pipeline.odoo_migration.mapping import load_mapping_table
from pipeline.odoo_migration.parity import run_tier_a
from pipeline.odoo_migration.sincerar import (
    FLAG_REVISAR,
    load_alias_table,
    normalize,
    resolve_alias,
    route_sincerado,
    sincerar,
)
from pipeline.odoo_migration.transform import OdooLineRecord, OdooMoveRecord, collapse

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
def aliases():
    return load_alias_table()


@pytest.fixture()
def sincerado(entries, table, aliases):
    return sincerar(collapse(entries, table), table, alias_table=aliases)


def _move(table, entity, code, desc="", amount="1", currency="CLP"):
    """Un move sintético de una pata sobre una cuenta REAL de la tabla."""
    row = table.get(entity, code)
    from pipeline.odoo_migration.mapping import company_for_entity

    return OdooMoveRecord(
        company=company_for_entity(entity),
        je_id="sint-1",
        date=datetime.date(2024, 1, 1),
        narration="",
        lines=[
            OdooLineRecord(
                n=0,
                odoo_account=row.odoo_account,
                laudus_code=code,
                entity=entity,
                currency=currency,
                amount=Decimal(amount),
                desc=desc,
            )
        ],
    )


def _dim1(table, aliases, entity, code, desc=""):
    """dimensionar sobre un move sintético de 1 pata → (línea, result)."""
    result = dimensionar([_move(table, entity, code, desc)], table, alias_table=aliases)
    return result.moves[0].lines[0], result


# --- Task 1: canonicalización — población cerrada (AC1, AC4) -----------------


def test_poblacion_cerrada_contra_tabla(table):
    """Todo valor real de `partner`/`socio`/`benef` del CSV tiene entrada en la
    tabla canónica (48 + 5 + 4 — un valor nuevo no pasa en silencio)."""
    partner_vals = {r.partner for r in table.rows if r.partner}
    socio_vals = {r.socio for r in table.rows if r.socio}
    benef_vals = {r.benef for r in table.rows if r.benef}
    assert len(partner_vals) == 48
    assert len(socio_vals) == 5
    assert len(benef_vals) == 4
    assert partner_vals <= set(PARTNER_CANONICO)
    assert socio_vals <= set(SOCIO_CANONICO)
    # benef nunca viene solo (siempre acompaña a `partner` con el mismo valor y
    # canónico beneficiario) — si el generador cambia eso, acusar acá.
    for r in table.rows:
        if r.benef:
            assert r.partner == r.benef, (r.entity, r.code)
            assert PARTNER_CANONICO[r.benef].categoria == CAT_BENEFICIARIO
    # y no hay entradas muertas en la tabla canónica (población cerrada en
    # ambos sentidos)
    assert set(PARTNER_CANONICO) == partner_vals
    assert set(SOCIO_CANONICO) == socio_vals


#: P-9 review (learning E1.3): la asignación partner-a-nivel-cuenta, pinneada
#: por (entity, code) — 89 filas (66 `partner` + 20 `socio` + 3 pins de lista).
#: Derivada UNA vez de la tabla al implementar; si alguien edita el CSV o la
#: tabla canónica, este snapshot acusa el flip.
PARTNER_SNAPSHOT = {
    ("EAG", "115001"): ("Cuentas Corrientes del Personal", "rendicion-p7"),
    ("EAG", "115005"): ("Fondos por Rendir", "rendicion-p7"),
    ("EAG", "115015"): ("Inmobiliaria Inv. Pirihueico SPA", "deudor"),
    ("EAG", "115017"): ("Grupo Gastronómico S.A.", "deudor"),
    ("EAG", "115018"): ("Tierra y Huertos SpA", "deudor"),
    ("EAG", "115019"): ("Deudores Varios", "bucket"),
    ("EAG", "310045"): ("Jhonny Guerra", "deudor"),
    ("EAG", "310047"): ("Jhonny Guerra", "deudor"),
    ("EAG", "430019"): ("Raquel Ventura", "beneficiario"),
    ("EAG", "430021"): ("Raquel Ventura", "beneficiario"),
    ("EAG", "430023"): ("Jacqueline Deutsch", "beneficiario"),
    ("EAG", "430024"): ("Patricia Deutsch", "beneficiario"),
    ("EAG", "430033"): ("Gloria Jiménez", "beneficiario"),
    ("EAG", "430081"): ("Keren Hayesod", "donacion"),
    ("EAG", "430083"): ("WIZO", "donacion"),
    ("EAG", "430089"): ("Coronas de Caridad", "donacion"),
    ("EAG", "430092"): ("Donaciones varias", "bucket"),
    ("FFCC", "115001"): ("Cuentas Corrientes del Personal", "rendicion-p7"),
    ("FFCC", "115003"): ("Fondo Fijo", "rendicion-p7"),
    ("FFCC", "115005"): ("Fondos por Rendir", "rendicion-p7"),
    ("FFCC", "115007"): ("Fondos por Rendir - US$", "rendicion-p7"),
    ("FFCC", "115019"): ("Deudores Varios", "bucket"),
    ("FFCC", "115021"): ("AAG", "socio-particion"),
    ("FFCC", "115023"): ("EAG", "socio-particion"),
    ("FFCC", "115025"): ("SAG", "socio-particion"),
    ("FFCC", "115027"): ("DAG", "socio-particion"),
    ("FFCC", "115028"): ("DAG", "socio-particion"),
    ("FFCC", "115029"): ("AZBA", "socio-particion"),
    ("FFCC", "115031"): ("José Alazraki", "socio-particion"),
    ("FFCC", "115033"): ("Denise Zeldis", "socio-particion"),
    ("FFCC", "115034"): ("Denise Zeldis", "socio-particion"),
    ("FFCC", "115035"): ("Michelle Zeldis", "socio-particion"),
    ("FFCC", "115037"): ("Ariel Borzutzky", "socio-particion"),
    ("FFCC", "115039"): ("Otros hijos", "socio-particion"),
    ("FFCC", "115041"): ("Israel", "socio-particion"),
    ("FFCC", "411004"): ("EAG", "socio-disperso"),
    ("FFCC", "413001"): ("AAG", "socio-disperso"),
    ("FFCC", "413003"): ("EAG", "socio-disperso"),
    ("FFCC", "413005"): ("SAG", "socio-disperso"),
    ("FFCC", "413007"): ("DAG", "socio-disperso"),
    ("FFCC", "415055"): ("Donaciones varias", "bucket"),
    ("FFCC", "431002"): ("Gloria Jiménez", "beneficiario"),
    ("FFCC", "433002"): ("Gloria Jiménez", "beneficiario"),
    ("FFCC", "437055"): ("Donaciones varias", "bucket"),
    ("JAB", "613001"): ("Cuentas Corrientes del Personal", "rendicion-p7"),
    ("JAB", "613003"): ("Fondo Fijo", "rendicion-p7"),
    ("JAB", "613005"): ("Fondos por Rendir", "rendicion-p7"),
    ("JAB", "613007"): ("Fondos por Rendir - US$", "rendicion-p7"),
    ("JAB", "613019"): ("Deudores Varios", "bucket"),
    ("JAB", "873001"): ("FGK", "socio-disperso"),
    ("JAB", "873003"): ("FGK", "socio-disperso"),
    ("JAB", "873005"): ("FGK", "socio-disperso"),
    ("JAB", "873013"): ("FGK", "socio-disperso"),
    ("JAB", "873017"): ("FGK", "socio-disperso"),
    ("JAB", "873023"): ("FGK", "socio-disperso"),
    ("JAB", "873025"): ("FGK", "socio-disperso"),
    ("JAB", "873027"): ("FGK", "socio-disperso"),
    ("JAB", "873053"): ("FGK", "socio-disperso"),
    ("JAB", "873097"): ("FGK", "socio-disperso"),
    ("JAB", "873099"): ("FGK", "socio-disperso"),
    ("JAB", "877001"): ("AAG", "socio-disperso"),
    ("JAB", "877003"): ("EAG", "socio-disperso"),
    ("JAB", "877005"): ("SAG", "socio-disperso"),
    ("JAB", "877007"): ("DAG", "socio-disperso"),
    ("JAB", "878001"): ("Coanil", "donacion"),
    ("JAB", "878003"): ("EZRA", "donacion"),
    ("JAB", "878005"): ("Hogar de Ancianos", "donacion"),
    ("JAB", "878007"): ("KKL", "donacion"),
    ("JAB", "878008"): ("Keren Hayesod", "donacion"),
    ("JAB", "878009"): ("WIZO", "donacion"),
    ("JAB", "878011"): ("CREJ", "donacion"),
    ("JAB", "878013"): ("CIS", "donacion"),
    ("JAB", "878015"): ("Hogar de Cristo", "donacion"),
    ("JAB", "878017"): ("C. Jafetz y Jaim", "donacion"),
    ("JAB", "878019"): ("Fundación Mar de Chile", "donacion"),
    ("JAB", "878021"): ("Fundación FOBEJU", "donacion"),
    ("JAB", "878099"): ("Donaciones varias", "bucket"),
    ("JAB", "879001"): ("Club Naval Las Salinas", "club"),
    ("JAB", "879003"): ("Club Naval de Valparaíso", "club"),
    ("JAB", "879005"): ("Museo Naval, Patrimonio", "club"),
    ("JAB", "879007"): ("Club de Golf La Dehesa", "club"),
    ("JAB", "879009"): ("Club de Campo Granadilla", "club"),
    ("JAB", "879011"): ("C.I. Sefaradi", "club"),
    ("JAB", "879013"): ("C.I. Santiago", "club"),
    ("JAB", "879019"): ("Fundación Mar de Chile", "donacion"),
    ("Jael", "950017"): ("Deudores Varios", "bucket"),
    ("Jeannette", "750017"): ("Deudores Varios", "bucket"),
    ("Jocelyn", "613019"): ("Deudores Varios", "bucket"),
    ("Johanna", "850001"): ("Deudores Varios", "bucket"),
}


def test_snapshot_partner_a_nivel_cuenta(table):
    """P-9: la asignación derivada de la tabla == snapshot versionado (89 filas)."""
    from pipeline.odoo_migration.dimensionar import _partner_por_cuenta

    derived = {}
    for r in table.rows:
        spec, _ = _partner_por_cuenta(r, r.entity, r.code)
        if spec is not None:
            derived[(r.entity, r.code)] = (spec.canonico, spec.categoria)
    assert derived == PARTNER_SNAPSHOT


def test_deutsch_son_dos_partners_separados():
    """AC1: Jacqueline y Patricia Deutsch NUNCA se fusionan."""
    j = PARTNER_CANONICO["Jacqueline Deutsch"]
    p = PARTNER_CANONICO["Patricia Deutsch"]
    assert j.canonico == "Jacqueline Deutsch"
    assert p.canonico == "Patricia Deutsch"
    assert j.canonico != p.canonico


def test_glosa_deutsch_exige_nombre_completo(aliases):
    """AC1: el mapeo por glosa exige nombre completo — 'deutsch' bare NO
    matchea (homónimo veta) y queda como candidata para el reporte."""
    assert resolve_alias(
        normalize("Regalo Jacqueline Deutsch"), aliases, "personas", tipo="beneficiario"
    ) == ("JacquelineDeutsch", True)  # candidata=True: 'deutsch' veta a Patricia
    name, candidata = resolve_alias(
        normalize("transferencia a Deutsch"), aliases, "personas", tipo="beneficiario"
    )
    assert name is None and candidata is True
    name, candidata = resolve_alias(
        normalize("aguinaldo Gloria"), aliases, "personas", tipo="beneficiario"
    )
    assert name is None and candidata is True  # varias Glorias — nunca bare


def test_autos_colapsan_al_padre():
    """Lista regla 1: sub-cuentas 'Autos' colapsan al mismo partner."""
    assert PARTNER_CANONICO["Cta Cte DAG - Autos"].canonico == "DAG"
    assert PARTNER_CANONICO["Denise Zeldis - Autos"].canonico == "Denise Zeldis"
    assert PARTNER_CANONICO["Cta Cte DAG - Autos"].categoria == CAT_SOCIO_PARTICION


def test_cis_son_tres_partners(table, aliases):
    """AC4 / lista regla 5: CIS, C.I. Santiago y C.I. Sefaradí NO se fusionan
    hasta que las contadoras confirmen — tres canónicos, todos con revisar."""
    canonicos = {
        PARTNER_CANONICO[v].canonico for v in ("CIS", "C.I. Santiago", "C.I. Sefaradi")
    }
    assert len(canonicos) == 3
    for v in ("CIS", "C.I. Santiago", "C.I. Sefaradi"):
        assert PARTNER_CANONICO[v].flag == FLAG_REVISAR
    line, result = _dim1(table, aliases, "JAB", "878013")
    assert line.partner == "CIS"
    assert result.report.revisar  # el placeholder queda listado, no silencioso


def test_dedup_cross_entidad_es_un_canonico(table):
    """Lista regla 4: Keren Hayesod / WIZO / Fundación Mar de Chile / Gloria
    Jiménez ya vienen con el MISMO string en el CSV — assertearlo (no re-mapear)."""
    for valor in ("Keren Hayesod", "WIZO", "Fundación Mar de Chile", "Gloria Jiménez"):
        filas = [r for r in table.rows if r.partner == valor]
        assert len(filas) >= 2, valor  # aparece en más de una cuenta/entidad
        assert PARTNER_CANONICO[valor].canonico == valor


def test_israel_por_cuenta_nunca_por_glosa(table, aliases):
    """AC2: Israel se resuelve por la cuenta 115041; 'israel' en glosa es
    país/nombre de pila → el alias YAML no tiene aliases y el homónimo veta."""
    line, _ = _dim1(table, aliases, "FFCC", "115041", desc="giro mensual")
    assert line.partner == "Israel"
    assert line.partner_categoria == CAT_SOCIO_PARTICION
    assert line.partner_flag == FLAG_REVISAR
    name, candidata = resolve_alias(
        normalize("giro a Israel de cuenta SADE"), aliases, "personas", tipo="apellido_azba"
    )
    assert name is None and candidata is True


def test_jhonny_pin_por_cuenta(table, aliases):
    """Las filas Jhonny traen `partner` VACÍO en el CSV — la lista cat 2 manda:
    un solo partner (madre+hijo) por (entity, code), grafía 'Jhonny'."""
    for code in ("310045", "310047"):
        line, _ = _dim1(table, aliases, "EAG", code, desc="Abono préstamo")
        assert line.partner == "Jhonny Guerra"
        assert line.partner_categoria == CAT_DEUDOR
        assert line.partner_regla == "cuenta:pin-lista"
        assert line.partner_flag == FLAG_REVISAR
    assert ("EAG", "310045") in PARTNER_PIN and ("EAG", "310047") in PARTNER_PIN


def test_raquel_tc_pin(table, aliases):
    """Pin (EAG, 430019): el CSV trae partner/benef vacíos (flag TC-especial,
    mapea a Liabilities:TC) pero el beneficiario sigue siendo Raquel (lista
    cat 4). Solo metadata — la cuenta destino no se toca."""
    line, _ = _dim1(table, aliases, "EAG", "430019", desc="T/C Raquel")
    assert line.partner == "Raquel Ventura"
    assert line.partner_categoria == CAT_BENEFICIARIO
    assert line.odoo_account == table.get("EAG", "430019").odoo_account


def test_deudores_varios_placeholder_por_entidad(table, aliases):
    """AC4: el bucket NO es una persona — placeholder por entidad, marcado."""
    for entity, code in (("EAG", "115019"), ("FFCC", "115019"), ("Jocelyn", "613019")):
        line, result = _dim1(table, aliases, entity, code)
        assert line.partner == f"Deudores Varios ({entity})"
        assert line.partner_categoria == CAT_BUCKET
        assert line.partner_flag == FLAG_REVISAR
        assert len(result.report.revisar) == 1


def test_rendiciones_p7_placeholder_sin_particion(table, aliases):
    """Rendiciones P-7 (115001–115007): fuera de scope E1 — placeholder
    verbatim, sin partición (no entran al gate)."""
    line, _ = _dim1(table, aliases, "FFCC", "115003")
    assert line.partner == "Fondo Fijo"
    assert line.partner_categoria == CAT_RENDICION_P7
    assert line.partner_categoria != CAT_SOCIO_PARTICION
    assert "115003" not in {c for cs in PARTICION_CODES.values() for c in cs}


# --- Task 3: dimensiones dispersas + personas (AC3) ---------------------------


def test_dims_desde_columnas_del_csv(table, aliases):
    """Estampado verbatim por línea desde las columnas (nivel cuenta)."""
    line, _ = _dim1(table, aliases, "JAB", "811001")
    assert line.dim_propiedad == "Vía Gris"
    line, _ = _dim1(table, aliases, "FFCC", "433003")
    assert line.dim_area == "OFICINA"
    line, _ = _dim1(table, aliases, "EAG", "113001")
    assert line.dim_offshore == "FM BCI - Alto Patrimonio"


def test_por_cuenta_de_no_es_area(table, aliases):
    """El valor `por-cuenta-de` de la columna `area` (8 filas Control y
    Liquidación) alimenta el plan por_cuenta_de, NO area_centro."""
    line, result = _dim1(table, aliases, "EAG", "115099")
    assert line.dim_por_cuenta_de == "por-cuenta-de"
    assert line.dim_area == ""
    assert result.report.por_plan.get("por_cuenta_de") == 1
    assert "area_centro" not in result.report.por_plan


def test_socio_columna_es_partner_disperso_no_plan(table, aliases):
    """Pin de mecanismo: la columna `socio` NO va a un plan analítico — es
    partner disperso con el MISMO canónico que la partición (no duplicar)."""
    line, _ = _dim1(table, aliases, "JAB", "873001")
    assert line.partner == "FGK"
    assert line.partner_categoria == CAT_SOCIO_DISPERSO
    assert line.dim_socio_uso == ""  # socio-dueño ≠ socio-uso
    line, _ = _dim1(table, aliases, "FFCC", "413003")
    assert line.partner == "EAG"
    assert line.partner_categoria == CAT_SOCIO_DISPERSO
    # (FFCC, 411004) "EAG - Complemento": socio + area a la vez
    line, _ = _dim1(table, aliases, "FFCC", "411004")
    assert line.partner == "EAG"
    assert line.dim_area == "SUELDO FAMILIA"


def test_socio_disperso_no_entra_al_gate_de_particion(entries, table, aliases):
    """El disperso EAG (impuestos/regalos) NO cuenta para la partición EAG:
    el gate suma SOLO categoría socio-particion."""
    result = dimensionar(
        [_move(table, "FFCC", "413003", amount="1000")], table, alias_table=aliases
    )
    # sin líneas de partición, el gate contra un mirror vacío no acusa nada
    assert verify_particion([], result.moves) == []


def test_raquel_por_glosa_en_gasto(table, aliases):
    """Regla (a): 'todo raquel es ella' (lista cat 4) en cuentas de gasto sin
    partner a nivel cuenta — disperso, nombre completo no exigido para Raquel
    (sin homónimos en la data)."""
    line, _ = _dim1(table, aliases, "EAG", "430051", desc="Compra remedios Raquel")
    assert line.partner == "Raquel Ventura"
    assert line.partner_categoria == CAT_BENEFICIARIO
    assert line.partner_regla == "glosa:RaquelVentura"


def test_glosa_dudosa_queda_sin_estampar_y_reporta(table, aliases):
    """AC5: la glosa que menciona sin resolver NO estampa y ENTRA al reporte
    (contada y listada — nunca perdida en silencio)."""
    line, result = _dim1(table, aliases, "EAG", "430051", desc="transferencia a Deutsch")
    assert line.partner == ""
    (ref,) = result.report.sin_match
    assert ref.regla == "glosa:beneficiario-sin-resolver"
    assert ref.desc == "transferencia a Deutsch"


def test_socio_uso_por_glosa_en_retiros(table, aliases):
    """Regla (b): socio-USO por glosa en retiros de uso → plan socio_uso, solo
    si el alias resuelve inequívoco (winston §5.1)."""
    line, result = _dim1(table, aliases, "FFCC", "115027", desc="Vuelo 3.5 hrs DAG")
    assert line.dim_socio_uso == "DAG"
    assert result.report.por_plan.get("socio_uso") == 1
    # ambiguo (dos socios) → sin estampar + reporte
    line, result = _dim1(table, aliases, "FFCC", "115027", desc="traspaso de AAG a DAG")
    assert line.dim_socio_uso == ""
    (ref,) = result.report.sin_match
    assert ref.regla == "glosa:socio-uso-sin-resolver"


def test_linea_sin_columnas_queda_limpia(table, aliases):
    """AC3: NO se exige 100% — una cuenta sin columnas ni glosa queda sin
    partner y sin dims, sin error y sin entrar a ningún reporte."""
    line, result = _dim1(table, aliases, "EAG", "111001", desc="depósito caja")
    assert line.partner == "" and line.partner_categoria == ""
    for dim in ("dim_propiedad", "dim_area", "dim_offshore", "dim_por_cuenta_de", "dim_socio_uso"):
        assert getattr(line, dim) == ""
    assert result.report.sin_match == [] and result.report.revisar == []


def test_alias_table_exige_seccion_personas(tmp_path):
    """P-2 (patrón E1.3): sin sección `personas`, las reglas por glosa de E1.4
    quedarían ciegas — fail-loud al cargar."""
    p = tmp_path / "alias.yaml"
    p.write_text("vehiculos:\n  MBI:\n    aliases: [mbi]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="personas"):
        load_alias_table(p)


# --- Review E1.4: endurecimientos (fail-louds y semántica pinneada) -----------


def test_partner_desconocido_revienta_con_contexto(table):
    """El fail-loud de población cerrada (columna `partner`) tiene que poder
    fallar — un valor nuevo del CSV no pasa en silencio."""
    from pipeline.odoo_migration.dimensionar import _partner_por_cuenta

    row = dataclasses.replace(table.get("EAG", "115019"), partner="Nadie Conocido")
    with pytest.raises(ValueError, match="PARTNER_CANONICO"):
        _partner_por_cuenta(row, "EAG", "115019")


def test_socio_desconocido_revienta_con_contexto(table):
    """Ídem para la columna `socio`."""
    from pipeline.odoo_migration.dimensionar import _partner_por_cuenta

    row = dataclasses.replace(table.get("JAB", "873001"), socio="XXX")
    with pytest.raises(ValueError, match="SOCIO_CANONICO"):
        _partner_por_cuenta(row, "JAB", "873001")


def test_beneficiarios_yaml_cubiertos_por_canonico(aliases):
    """Población cerrada YAML↔mapa: toda entrada tipo `beneficiario` del YAML
    tiene canónico en _BENEF_ALIAS_A_CANONICO (y viceversa)."""
    from pipeline.odoo_migration.dimensionar import _BENEF_ALIAS_A_CANONICO

    yaml_names = {e.name for e in aliases["personas"] if e.tipo == "beneficiario"}
    assert yaml_names == set(_BENEF_ALIAS_A_CANONICO)


def test_beneficiario_nuevo_sin_canonico_revienta(table):
    """Si el YAML gana un 5º beneficiario y una glosa lo matchea, el
    transformador acusa con contexto (no KeyError pelado)."""
    from pipeline.odoo_migration.sincerar import AliasEntry

    fake = {
        "personas": [
            AliasEntry(
                name="BettyDeutsch",
                aliases=(normalize("betty deutsch"),),
                excluir=(),
                tipo="beneficiario",
            )
        ]
    }
    with pytest.raises(ValueError, match="_BENEF_ALIAS_A_CANONICO"):
        dimensionar(
            [_move(table, "EAG", "430051", desc="regalo Betty Deutsch")],
            table,
            alias_table=fake,
        )


def test_socio_uso_fuera_de_poblacion_revienta(table):
    """Un typo/renombre tipo `socio` en el YAML no mis-estampa el plan
    socio_uso congelado — población cerrada, fail-loud."""
    from pipeline.odoo_migration.sincerar import AliasEntry

    fake = {
        "personas": [
            AliasEntry(
                name="EduardoAvayu",
                aliases=(normalize("eduardo avayu"),),
                excluir=(),
                tipo="socio",
            )
        ]
    }
    with pytest.raises(ValueError, match="socio_uso"):
        dimensionar(
            [_move(table, "FFCC", "115023", desc="retiro Eduardo Avayu")],
            table,
            alias_table=fake,
        )


def test_veto_por_spans_pinneado_para_vehiculos():
    """La generalización E1.4 cambió el veto también para `vehiculos`: un
    homónimo que es palabra completa DENTRO de un alias ya no veta (hoy
    inobservable — ningún vehículo real del YAML tiene esa forma — pero la
    semántica queda pinneada acá) y un homónimo suelto sigue vetando
    (semántica E1.3 'leo hernandez por leo limited' preservada)."""
    from pipeline.odoo_migration.sincerar import AliasEntry, resolve_vehiculo

    table = {
        "vehiculos": [
            AliasEntry(
                name="X",
                aliases=(normalize("fondo leo"),),
                excluir=(normalize("leo"),),
            )
        ]
    }
    assert resolve_vehiculo(normalize("aporte fondo leo"), table) == "X"
    assert resolve_vehiculo(normalize("aporte de leo"), table) is None


def test_alias_vacio_se_rechaza(tmp_path):
    """Un alias/homónimo que normaliza a '' matchearía cualquier glosa
    (incluida la vacía) — fail-loud al cargar."""
    p = tmp_path / "alias.yaml"
    p.write_text(
        "vehiculos:\n  MBI:\n    aliases: [mbi]\n"
        "personas:\n  Y:\n    aliases: ['   ']\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="vac"):
        load_alias_table(p)


# --- Task 4: invariantes sobre el golden slice --------------------------------


def test_invariante_estructural_sobre_golden(sincerado, table, aliases):
    """dimensionar NO altera odoo_account / amount / set de moves (la paridad
    es doblemente invariante en E1.4)."""
    result = dimensionar(sincerado.moves, table, alias_table=aliases)
    assert len(result.moves) == len(sincerado.moves)
    for antes, despues in zip(sincerado.moves, result.moves):
        assert antes.je_id == despues.je_id
        assert len(antes.lines) == len(despues.lines)
        for a, d in zip(antes.lines, despues.lines):
            assert a.odoo_account == d.odoo_account
            assert a.amount == d.amount
            assert a.laudus_code == d.laudus_code
            assert a.currency == d.currency


def test_funcion_pura_no_muta_el_input(sincerado, table, aliases):
    """El input de `dimensionar` (output de sincerar) queda intacto."""
    dimensionar(sincerado.moves, table, alias_table=aliases)
    for m in sincerado.moves:
        for l in m.lines:
            assert l.partner == "" and l.partner_categoria == ""
            assert l.dim_propiedad == "" and l.dim_socio_uso == ""


def test_tier_a_verde_con_cadena_de_tres(entries, sincerado, table, aliases):
    """Contrato E1: run_tier_a verde tras dimensionar con los MISMOS
    route/excluded_je_ids de E1.3 — E1.4 no excluye ni re-rutea nada."""
    result = dimensionar(sincerado.moves, table, alias_table=aliases)
    run_tier_a(
        entries,
        result.moves,
        table,
        route=route_sincerado(table, aliases),
        excluded_je_ids=sincerado.excluded_je_ids,
    )
