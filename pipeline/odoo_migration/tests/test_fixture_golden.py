"""Sanidad + guardrail del fixture golden (AC2).

- Carga el slice con beancount.loader → 0 errores (equivalente a bean-check exit 0).
- Verifica que cada naturaleza de sinceramiento y ≥1 posting USD siguen presentes.
  Si alguien "simplifica" el fixture y borra un caso, este test se pone rojo.
"""

import os

from beancount import loader
from beancount.core import data

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "golden_slice.beancount")

# Naturalezas obligatorias (AC2). El caso USD se chequea aparte por commodity.
REQUIRED_NATURES = {"retiro", "aporte", "traspaso", "wash", "ambiguo"}


def _load():
    entries, errors, _ = loader.load_file(FIXTURE)
    return entries, errors


def test_fixture_loads_without_errors():
    """0 errores de carga = bean-check verde sobre el slice."""
    _, errors = _load()
    assert errors == [], f"bean-check falló sobre el fixture: {errors}"


def test_all_natures_present():
    entries, _ = _load()
    natures = {
        e.meta.get("nature")
        for e in entries
        if isinstance(e, data.Transaction) and e.meta.get("nature")
    }
    missing = REQUIRED_NATURES - natures
    assert not missing, f"El fixture perdió naturalezas obligatorias: {missing}"


def test_has_usd_posting():
    """AC2: ≥1 posting en USD (units.currency == 'USD') para ejercer amount_currency en E1.5."""
    entries, _ = _load()
    usd_postings = [
        p
        for e in entries
        if isinstance(e, data.Transaction)
        for p in e.postings
        if p.units and p.units.currency == "USD"
    ]
    assert usd_postings, "El fixture debe forzar ≥1 posting USD (el mirror no tiene ninguno)"


def test_wash_pair_nets_to_zero():
    """El par apertura/cierre (nature=wash) debe netear a 0 por cuenta (E1.3 lo lava)."""
    entries, _ = _load()
    by_account = {}
    for e in entries:
        if isinstance(e, data.Transaction) and e.meta.get("nature") == "wash":
            for p in e.postings:
                if p.units:
                    by_account[p.account] = by_account.get(p.account, 0) + p.units.number
    assert by_account, "No hay asientos wash en el fixture"
    for account, total in by_account.items():
        assert total == 0, f"El wash no netea a 0 en {account}: {total}"
