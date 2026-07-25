"""Configuración pytest del paquete de migración Odoo.

Registra el marker `odoo`: los tests marcados así son **Tier B** (opt-in, tocan
el contenedor Docker de Odoo) y NO corren por-commit. Se saltan por defecto y
solo corren con `-m odoo` explícito (gate de release). Lección `tsc --noEmit`:
el gate por-commit tiene que ser rápido y determinístico (Tier A: Python puro).

También comparte el fixture del MIRROR COMPLETO al corte del inventario
(`full_mirror_chain`, session-scoped): los módulos full-mirror de E1.3 y E1.4
consumen la MISMA carga del ledger + cadena `collapse → sincerar` — el ledger
no se carga dos veces por corrida.
"""

import datetime
import os

import pytest

LEDGER = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "ledger", "main.beancount"
)

#: Fecha del inventario de naturalezas / lista de partners — la historia hasta
#: acá está pinneada. El mirror es un archivo VIVO (sync de Laudus): el corte
#: (INCLUSIVO del 2026-07-23) fija el universo para que los pins no se muevan
#: con syncs futuros. Si un full-mirror se pone rojo sin haber tocado los
#: transformadores, un asiento retro-posteado cambió la historia pinneada —
#: hallazgo a investigar, no test flaky.
CUTOFF = datetime.date(2026, 7, 23)


@pytest.fixture(scope="session")
def full_mirror_chain():
    """(cut, table, aliases, moves, result_sincerar) sobre TODA la historia al
    corte. Los consumidores NO deben mutar lo compartido (los transformadores
    devuelven copias — un test de mutación trabaja sobre una corrida fresca)."""
    from beancount import loader
    from beancount.core import data

    from pipeline.odoo_migration.mapping import load_mapping_table
    from pipeline.odoo_migration.sincerar import load_alias_table, sincerar
    from pipeline.odoo_migration.transform import collapse

    entries, errors, _ = loader.load_file(LEDGER)
    assert errors == []
    cut = [
        e
        for e in entries
        if not (isinstance(e, data.Transaction) and e.date > CUTOFF)
    ]
    table = load_mapping_table()
    aliases = load_alias_table()
    moves = collapse(cut, table)
    result = sincerar(moves, table, alias_table=aliases)
    return cut, table, aliases, moves, result


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "odoo: Tier B — smoke que levanta Odoo en Docker. Opt-in (corre solo con "
        "`-m odoo`), NO por-commit.",
    )


def pytest_collection_modifyitems(config, items):
    """Salta los tests `@pytest.mark.odoo` salvo que se pida `-m odoo` explícito."""
    marker_expr = config.getoption("markexpr", default="")
    if "odoo" in marker_expr:
        return  # el usuario pidió correrlos explícitamente
    skip_odoo = pytest.mark.skip(reason="Tier B (Docker Odoo): opt-in con `-m odoo`")
    for item in items:
        if "odoo" in item.keywords:
            item.add_marker(skip_odoo)
