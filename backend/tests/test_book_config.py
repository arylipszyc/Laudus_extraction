"""Tests de BookConfig / get_book / login_payload — Story 12.2 (FR50/FR51/FR52)."""
import pytest

from pipeline.config.laudus_config import (
    ALL_BOOK_ENTITIES,
    BOOKS,
    get_book,
    login_payload,
)


# ── get_book: sin libro no hay corrida (AC1 / FR50) ──────────────────────────


@pytest.mark.parametrize("bad", [None, "", "OTRO-LIBRO", "eag", "ffcc"])
def test_get_book_rechaza_libro_ausente_o_desconocido(bad):
    with pytest.raises(ValueError, match="FR50"):
        get_book(bad)


def test_get_book_resuelve_los_dos_libros():
    assert get_book("EAG") is BOOKS["EAG"]
    assert get_book("RUT2") is BOOKS["RUT2"]


# ── Forma de los libros (subdir/cuarentena/entidades) ────────────────────────


def test_libro_eag_conserva_paths_y_nombres_legacy():
    eag = get_book("EAG")
    assert eag.subdir == "laudus"
    assert eag.pending_file == "_new-accounts-pending.beancount"
    assert eag.importer_name == "laudus"
    assert eag.entities == {"EAG", "Jocelyn", "Jeannette", "Johanna", "Jael"}
    assert eag.include_entityless is True


def test_libro_rut2_aislado_de_eag():
    rut2 = get_book("RUT2")
    assert rut2.subdir == "laudus-rut2"
    assert rut2.pending_file == "_new-accounts-pending-rut2.beancount"
    assert rut2.importer_name == "laudus-rut2"
    assert rut2.entities == {"FFCC", "JAB"}
    assert rut2.include_entityless is False
    assert "FFCC" in ALL_BOOK_ENTITIES and "EAG" in ALL_BOOK_ENTITIES


# ── Cuarentena por entidad del libro (AC2) ───────────────────────────────────


def test_pending_entity_eag_siempre_eag():
    eag = get_book("EAG")
    for code in ("111005", "411059", "999999", ""):
        assert eag.pending_entity(code) == "EAG"


@pytest.mark.parametrize(
    "code, entity",
    [
        ("111003", "FFCC"),   # raíz 1 (activo FFCC)
        ("211005", "FFCC"),   # raíz 2
        ("311001", "FFCC"),   # raíz 3
        ("433015", "FFCC"),   # raíz 4
        ("611001", "JAB"),    # raíz 6
        ("711001", "JAB"),    # raíz 7
        ("871005", "JAB"),    # raíz 8
        ("999999", "FFCC"),   # dígito desconocido → default FFCC (decisión story)
        ("512345", "FFCC"),   # raíz 5 no existe en el plan → default FFCC
    ],
)
def test_pending_entity_rut2_por_digito_de_raiz(code, entity):
    assert get_book("RUT2").pending_entity(code) == entity


# ── login_payload: companyVATId por libro, leído en runtime (Task 1) ─────────


def test_login_payload_usa_el_vat_del_libro(monkeypatch):
    monkeypatch.setenv("LAUDUS_USERNAME", "user")
    monkeypatch.setenv("LAUDUS_PASSWORD", "pass")
    monkeypatch.setenv("LAUDUS_COMPANYVATID", "99.999.999-9")
    monkeypatch.setenv("LAUDUS_COMPANYVATID_RUT2", "12.345.678-2")
    assert login_payload(get_book("EAG"))["companyVATId"] == "99.999.999-9"
    assert login_payload(get_book("RUT2"))["companyVATId"] == "12.345.678-2"


def test_login_payload_sin_vat_del_libro_falla_claro(monkeypatch):
    monkeypatch.delenv("LAUDUS_COMPANYVATID_RUT2", raising=False)
    with pytest.raises(RuntimeError, match="LAUDUS_COMPANYVATID_RUT2"):
        login_payload(get_book("RUT2"))
