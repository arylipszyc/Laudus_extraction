"""Snapshot del plan + validaciones de la tabla de mapeo (E1.2, AC1 + verify §8).

La tabla CSV de Valentina es la fuente del colapso 569→N. Estos tests pinean
los números REALES de la tabla versionada (no los redondeos del resumen) y
garantizan que el loader falla fuerte ante una tabla corrupta.
"""

import pytest

from pipeline.odoo_migration.mapping import (
    MappingTable,
    company_for_entity,
    load_mapping_table,
)


@pytest.fixture(scope="module")
def table() -> MappingTable:
    return load_mapping_table()


# --- Snapshot del plan (verify §8 de la arquitectura) ---


def test_snapshot_569_filas_568_con_code(table):
    """La tabla trae 569 cuentas del mirror: 568 con código Laudus + 1 sin code
    (Expenses:EAG:Suspense — cuenta interna del proyecto, no viene de Laudus)."""
    assert len(table.rows) == 568
    assert len(table.skipped_no_code) == 1
    (skipped,) = table.skipped_no_code
    assert skipped["entity"] == "EAG"
    assert skipped["otype"] == "expense"


def test_snapshot_plan_colapsado(table):
    """569→335 destinos únicos globales (el "336" del resumen contaba también el
    'Gasto:' de la fila sin code). El plan operativo es POR compañía (charts no
    compartidos, winston §3): 361 cuentas (company, odoo)."""
    global_accounts = {r.odoo_account for r in table.rows}
    per_company = {(r.company, r.odoo_account) for r in table.rows}
    assert len(global_accounts) == 335
    assert len(per_company) == 361


def test_toda_cuenta_laudus_tiene_destino(table):
    assert all(r.odoo_account for r in table.rows)


def test_keys_unicas(table):
    """(entity, code) y (company, code) únicos — (company, code) protege el
    external ID congelado acc_<company>_<code> (E1.0)."""
    by_entity = {(r.entity, r.code) for r in table.rows}
    by_company = {(r.company, r.code) for r in table.rows}
    assert len(by_entity) == len(table.rows)
    assert len(by_company) == len(table.rows)


# --- Derivación de company (la columna CSV puede venir vacía) ---


def test_company_se_deriva_de_entity():
    assert company_for_entity("EAG") == "EAG"
    assert company_for_entity("Jocelyn") == "EAG"
    assert company_for_entity("Jael") == "EAG"
    assert company_for_entity("FFCC") == "RUT2"
    assert company_for_entity("JAB") == "RUT2"


def test_company_entity_vacia_falla():
    with pytest.raises(ValueError):
        company_for_entity("")


def test_equity_sinteticas_derivan_rut2(table):
    """Las 2 aperturas Equity sintéticas (900001 FFCC / 900002 JAB) vienen con
    company vacía en el CSV → el loader las deriva de la entity."""
    assert table.get("FFCC", "900001").company == "RUT2"
    assert table.get("JAB", "900002").company == "RUT2"


# --- Lookup fail-loud ---


def test_get_devuelve_fila(table):
    row = table.get("EAG", "310013")
    assert row.odoo_account == "Income:Retiros Tecnión"
    assert row.company == "EAG"


def test_get_codigo_repetido_entre_entidades(table):
    """111005 existe en EAG y FFCC: la key (entity, code) los distingue."""
    eag = table.get("EAG", "111005")
    ffcc = table.get("FFCC", "111005")
    assert eag.odoo_account != ffcc.odoo_account
    assert (eag.company, ffcc.company) == ("EAG", "RUT2")


def test_get_desconocido_falla_con_contexto(table):
    with pytest.raises(KeyError, match="999999"):
        table.get("EAG", "999999")


# --- El loader falla fuerte ante tabla corrupta ---


def _write_csv(tmp_path, rows):
    header = "code,entity,company,name,cat2,cat3,bal,odoo,otype,ent,prop,socio,benef,area,offshore,partner,sinc,flag"
    body = "\n".join(rows)
    path = tmp_path / "tabla.csv"
    path.write_text(header + "\n" + body + "\n", encoding="utf-8")
    return path


def test_duplicado_entity_code_falla(tmp_path):
    path = _write_csv(
        tmp_path,
        [
            "111001,EAG,EAG,Caja $,,,0,Caja CLP,asset,EAG,,,,,,,,",
            "111001,EAG,EAG,Caja bis,,,0,Caja CLP,asset,EAG,,,,,,,,",
        ],
    )
    with pytest.raises(ValueError, match="111001"):
        load_mapping_table(path)


def test_destino_vacio_falla(tmp_path):
    path = _write_csv(
        tmp_path,
        ["111001,EAG,EAG,Caja $,,,0,,asset,EAG,,,,,,,,"],
    )
    with pytest.raises(ValueError, match="111001"):
        load_mapping_table(path)


def test_header_renombrado_falla(tmp_path):
    """Sin este guard, un header renombrado haría que TODAS las filas cayeran a
    skipped_no_code y el loader retornara una tabla vacía sin error."""
    path = tmp_path / "tabla.csv"
    path.write_text(
        "codigo,entity,company,name,odoo,otype,sinc,flag\n"
        "111001,EAG,EAG,Caja $,Caja CLP,asset,,\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="code"):
        load_mapping_table(path)


def test_bom_de_excel_se_tolera(tmp_path):
    """Un re-guardado con Excel agrega BOM UTF-8; el loader lo absorbe
    (utf-8-sig) en vez de perder la columna `code`."""
    path = tmp_path / "tabla.csv"
    path.write_text(
        "﻿" "code,entity,company,name,odoo,otype,sinc,flag\n"
        "111001,EAG,EAG,Caja $,Caja CLP,asset,,\n",
        encoding="utf-8",
    )
    table = load_mapping_table(path)
    assert table.get("EAG", "111001").odoo_account == "Caja CLP"


def test_tabla_sin_filas_con_codigo_falla(tmp_path):
    path = _write_csv(tmp_path, [",EAG,EAG,Suspense,,,0,Gasto:,expense,EAG,,,,,,,,"])
    with pytest.raises(ValueError, match="vacía"):
        load_mapping_table(path)


def test_segunda_fila_sin_code_falla(tmp_path):
    """La promesa del docstring vive en el LOADER, no solo en el pin del
    snapshot: una segunda cuenta sin código no pasa en silencio."""
    path = _write_csv(
        tmp_path,
        [
            "111001,EAG,EAG,Caja $,,,0,Caja CLP,asset,EAG,,,,,,,,",
            ",EAG,EAG,Suspense,,,0,Gasto:,expense,EAG,,,,,,,,",
            ",EAG,EAG,Otra sin code,,,0,Gasto:,expense,EAG,,,,,,,,",
        ],
    )
    with pytest.raises(ValueError, match="sin código"):
        load_mapping_table(path)


def test_company_csv_contradice_entity_falla(tmp_path):
    """La columna `company` del CSV no se usa como fuente, pero SÍ como check de
    consistencia: si el generador y EAG_ENTITIES divergen, fail-loud."""
    path = _write_csv(
        tmp_path,
        ["111001,EAG,RUT2,Caja $,,,0,Caja CLP,asset,EAG,,,,,,,,"],
    )
    with pytest.raises(ValueError, match="divergen"):
        load_mapping_table(path)
