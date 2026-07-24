"""Tests del helper de external IDs (AC3). El formato se congela acá — estos
tests son el guardrail contra un cambio accidental de la convención de la que
depende la idempotencia del loader (E1.5)."""

import pytest

from pipeline.odoo_migration.external_ids import (
    account_xmlid,
    line_xmlid,
    move_xmlid,
)


# --- Formato exacto (congelado) ---

def test_account_xmlid_format():
    assert account_xmlid("EAG", "111005") == "acc_eag_111005"


def test_move_xmlid_format():
    assert move_xmlid("EAG", "5881") == "mv_eag_5881"


def test_line_xmlid_format():
    assert line_xmlid("5881", 0) == "aml_5881_0"


# --- Determinismo: mismo input → mismo output ---

def test_deterministic():
    assert account_xmlid("RUT2", "310011") == account_xmlid("RUT2", "310011")
    assert move_xmlid("RUT2", "3994") == move_xmlid("RUT2", "3994")
    assert line_xmlid("3994", 2) == line_xmlid("3994", 2)


# --- Unicidad EAG vs RUT2 para el mismo code (no colisionan) ---

def test_same_code_distinct_companies():
    assert account_xmlid("EAG", "111005") != account_xmlid("RUT2", "111005")
    assert move_xmlid("EAG", "100") != move_xmlid("RUT2", "100")


# --- company case-insensitive: misma entidad → mismo id (feature de idempotencia) ---

def test_company_case_insensitive():
    assert account_xmlid("EAG", "111005") == account_xmlid("eag", "111005")
    assert move_xmlid("RUT2", "5") == move_xmlid("rut2", "5")


# --- `n` es índice 0-based; distintos índices → ids distintos ---

def test_line_index_distinct():
    je = "5881"
    assert line_xmlid(je, 0) != line_xmlid(je, 1)
    assert line_xmlid(je, 10) == "aml_5881_10"


def test_line_accepts_int_and_str_index():
    assert line_xmlid("5881", 3) == line_xmlid("5881", "3") == "aml_5881_3"


# --- Fail-loud: componentes inválidos ---

@pytest.mark.parametrize("bad", ["", "  ", "abc def", "1.2", "a/b"])
def test_invalid_code_raises(bad):
    with pytest.raises(ValueError):
        account_xmlid("EAG", bad)


def test_empty_company_raises():
    with pytest.raises(ValueError):
        account_xmlid("", "111005")


def test_negative_line_index_raises():
    with pytest.raises(ValueError):
        line_xmlid("5881", -1)
