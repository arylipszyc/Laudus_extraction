"""Tests del normalizer de descripciones — Story 9.7 AC10."""
from pipeline.importers.categorization.normalizer import normalize


def test_case_y_espacios():
    assert normalize("SUPERMERCADO JUMBO") == normalize("supermercado jumbo  ")
    assert normalize("  Jumbo   Maipu ") == "JUMBO MAIPU"


def test_sufijo_numerico_largo_se_quita():
    assert normalize("SUPERMERCADO JUMBO 123456") == "SUPERMERCADO JUMBO"
    assert normalize("TRANSFERENCIA 9988776655") == "TRANSFERENCIA"


def test_numero_corto_se_preserva():
    # 4 dígitos o menos no se borra (puede ser parte del nombre)
    assert normalize("LINEA 24") == "LINEA 24"
    assert normalize("CUENTA 1027") == "CUENTA 1027"


def test_puntuacion_comun():
    assert normalize("FARMACIA AHUMADA, S.A.") == "FARMACIA AHUMADA SA"
    assert normalize("PAGO #4455 JUMBO") == "PAGO 4455 JUMBO"


def test_prefijo_ref():
    assert normalize("REF JUMBO COSTANERA") == "JUMBO COSTANERA"
    assert normalize("ref jumbo") == "JUMBO"


def test_equivalentes_del_storyfile():
    a = normalize("SUPERMERCADO JUMBO")
    b = normalize("supermercado jumbo  ")
    c = normalize("SUPERMERCADO JUMBO 12345")
    assert a == b == c


def test_unicode_y_vacio():
    assert normalize("") == ""
    assert normalize("   ") == ""
    assert normalize("CafÉ Owen") == "CAFÉ OWEN"


def test_colapsa_espacios_internos():
    assert normalize("BANCO    DE    CHILE") == "BANCO DE CHILE"


def test_idempotente():
    once = normalize("REF  Jumbo, Maipu  998877")
    assert normalize(once) == once


def test_solo_numeros_largos():
    assert normalize("123456789") == ""
