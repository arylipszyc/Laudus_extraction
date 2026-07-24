"""Configuración pytest del paquete de migración Odoo.

Registra el marker `odoo`: los tests marcados así son **Tier B** (opt-in, tocan
el contenedor Docker de Odoo) y NO corren por-commit. Se saltan por defecto y
solo corren con `-m odoo` explícito (gate de release). Lección `tsc --noEmit`:
el gate por-commit tiene que ser rápido y determinístico (Tier A: Python puro).
"""

import pytest


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
