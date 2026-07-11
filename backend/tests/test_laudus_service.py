"""Tests de `get_info_API` — fix review 2026-07-06 (B2): descarga parcial NUNCA es éxito.

Un fallo a mitad de paginación devolvía la acumulación parcial como si fuera el dataset
completo; en modo backfill (`write_jes(..., replace=True)`) eso regeneraba los month files
solo con esas filas y BORRABA en silencio el resto del mes.
"""
import pytest

from pipeline.services import laudus_service


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise laudus_service.requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _fake_token(monkeypatch):
    """Evita el login real: token en caché (por libro desde 12.2; default = EAG)."""
    monkeypatch.setattr(laudus_service, "_tokens", {"EAG": "fake-token"})
    yield


def test_fallo_a_mitad_de_paginacion_lanza_no_devuelve_parcial(monkeypatch):
    """Página 1 OK, página 2 explota → raise (la corrida se marca failed), no parcial."""
    calls = {"n": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResponse({"data": [{"id": 1}], "page": 1, "totalPages": 3})
        raise laudus_service.requests.ConnectionError("timeout en página 2")

    monkeypatch.setattr(laudus_service.requests, "get", fake_get)

    with pytest.raises(RuntimeError, match="parcial"):
        laudus_service.get_info_API("https://api.test/jes", retry=False)


def test_fallo_a_mitad_de_paginacion_con_retry_reintenta_completo(monkeypatch):
    """Con retry=True el primer parcial dispara el re-request completo; si el segundo
    intento también queda parcial → raise igual (nunca se propaga un dataset a medias)."""
    calls = {"n": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["n"] += 1
        # Cada intento: página 1 OK, página 2 rota.
        if calls["n"] % 2 == 1:
            return _FakeResponse({"data": [{"id": 1}], "page": 1, "totalPages": 2})
        raise laudus_service.requests.ConnectionError("boom")

    monkeypatch.setattr(laudus_service.requests, "get", fake_get)

    with pytest.raises(RuntimeError, match="parcial"):
        laudus_service.get_info_API("https://api.test/jes")
    assert calls["n"] >= 3  # hubo reintento completo antes de rendirse


def test_fallo_sin_registros_acumulados_sigue_devolviendo_none(monkeypatch):
    """Contrato actual: si NO hay nada acumulado (falla la página 1), devuelve None."""
    def fake_get(url, headers=None, params=None, timeout=None):
        raise laudus_service.requests.ConnectionError("no responde")

    monkeypatch.setattr(laudus_service.requests, "get", fake_get)
    assert laudus_service.get_info_API("https://api.test/jes", retry=False) is None


def test_formato_inesperado_en_pagina_2_no_devuelve_parcial(monkeypatch):
    """Patch del review Fase 1: la rama de formato-inesperado en página >1 devolvía el
    dict crudo DESCARTANDO lo acumulado — misma clase de bug parcial-como-éxito."""
    calls = {"n": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResponse({"data": [{"id": 1}], "page": 1, "totalPages": 2})
        return _FakeResponse({"raro": True})

    monkeypatch.setattr(laudus_service.requests, "get", fake_get)
    with pytest.raises(RuntimeError, match="parcial"):
        laudus_service.get_info_API("https://api.test/jes", retry=False)


def test_formato_inesperado_en_primera_pagina_retorna_tal_cual(monkeypatch):
    """Contrato preservado: formato no reconocido SIN nada acumulado se retorna tal cual."""
    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeResponse({"raro": True})

    monkeypatch.setattr(laudus_service.requests, "get", fake_get)
    assert laudus_service.get_info_API("https://api.test/jes", retry=False) == {"raro": True}


def test_paginacion_completa_acumula_todo(monkeypatch):
    """Happy path intacto: 2 páginas OK → lista completa."""
    calls = {"n": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResponse({"data": [{"id": 1}], "page": 1, "totalPages": 2})
        return _FakeResponse({"data": [{"id": 2}], "page": 2, "totalPages": 2})

    monkeypatch.setattr(laudus_service.requests, "get", fake_get)
    assert laudus_service.get_info_API("https://api.test/jes", retry=False) == [{"id": 1}, {"id": 2}]


def test_paginacion_que_no_avanza_lanza_sin_reintentar(monkeypatch):
    """B8: una API que repite la misma página → PaginationError inmediato (antes: loop
    infinito sosteniendo .import.lock)."""
    calls = {"n": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["n"] += 1
        return _FakeResponse({"data": [{"id": calls["n"]}], "page": 2, "totalPages": 3})

    monkeypatch.setattr(laudus_service.requests, "get", fake_get)
    with pytest.raises(laudus_service.PaginationError, match="no avanza"):
        laudus_service.get_info_API("https://api.test/jes")
    assert calls["n"] <= 3, "no debe reintentar el loop entero"


def test_paginacion_supera_max_pages_lanza(monkeypatch):
    """B8: tope duro de páginas."""
    monkeypatch.setattr(laudus_service, "_MAX_PAGES", 5)

    def fake_get(url, headers=None, params=None, timeout=None):
        page = int((params or {}).get("page", 1))
        return _FakeResponse({"data": [{"id": page}], "page": page, "totalPages": 99})

    monkeypatch.setattr(laudus_service.requests, "get", fake_get)
    with pytest.raises(laudus_service.PaginationError, match="super"):
        laudus_service.get_info_API("https://api.test/jes")


def test_login_propaga_la_causa_real(monkeypatch):
    """B8: login() ya no traga la excepción (antes: None → genérico 'No hay token')."""
    monkeypatch.setattr(laudus_service, "_tokens", {})
    monkeypatch.setenv("LAUDUS_COMPANYVATID", "11.111.111-1")  # que no corte antes por env

    def fake_post(url, json=None, headers=None, timeout=None):
        raise laudus_service.requests.ConnectionError("DNS no resuelve api.laudus.cl")

    monkeypatch.setattr(laudus_service.requests, "post", fake_post)
    with pytest.raises(laudus_service.requests.ConnectionError, match="DNS"):
        laudus_service.login()


def test_login_cachea_token_por_libro(monkeypatch):
    """12.2 Task 1: el token ya no es global de módulo — cada libro tiene el suyo
    (un login EAG no sirve a RUT2 y viceversa)."""
    from pipeline.config.laudus_config import get_book

    monkeypatch.setattr(laudus_service, "_tokens", {})
    monkeypatch.setenv("LAUDUS_COMPANYVATID", "11.111.111-1")
    monkeypatch.setenv("LAUDUS_COMPANYVATID_RUT2", "12.345.678-2")
    vats_logueados = []

    def fake_post(url, json=None, headers=None, timeout=None):
        vats_logueados.append(json["companyVATId"])
        return _FakeResponse({"token": f"token-{json['companyVATId']}"})

    monkeypatch.setattr(laudus_service.requests, "post", fake_post)
    t_eag = laudus_service.login(get_book("EAG"))
    t_rut2 = laudus_service.login(get_book("RUT2"))
    assert t_eag != t_rut2
    assert vats_logueados == ["11.111.111-1", "12.345.678-2"]
    # Segunda llamada por libro: cache, sin nuevo POST.
    laudus_service.login(get_book("EAG"))
    laudus_service.login(get_book("RUT2"))
    assert len(vats_logueados) == 2


# ── verify_book_identity (12.2 AC3 / FR52) ───────────────────────────────────


def _fake_accounts_post(accounts_payload):
    def fake_post(url, json=None, headers=None, timeout=None):
        assert url == laudus_service.ACCOUNTS_LIST_URL
        return _FakeResponse(accounts_payload)
    return fake_post


def test_verify_book_identity_pasa_con_la_raiz_correcta(monkeypatch):
    from pipeline.config.laudus_config import get_book

    monkeypatch.setattr(laudus_service.requests, "post", _fake_accounts_post([
        {"accountNumber": "1", "name": "ACTIVO EAG"},
        {"accountNumber": "111005", "name": "Banco BCI"},
    ]))
    laudus_service.verify_book_identity(get_book("EAG"))  # no lanza


def test_verify_book_identity_aborta_si_la_empresa_es_otra(monkeypatch):
    """FR52: Laudus devuelve datos de OTRO libro sin fallar — el fingerprint de la
    cuenta raíz 1 lo detecta y aborta. Sin validación de DV (RUT placeholder)."""
    from pipeline.config.laudus_config import get_book

    monkeypatch.setattr(laudus_service, "_tokens", {"EAG": "t", "RUT2": "t"})
    monkeypatch.setattr(laudus_service.requests, "post", _fake_accounts_post([
        {"accountNumber": "1", "name": "ACTIVO EAG"},  # ← libro equivocado para RUT2
    ]))
    with pytest.raises(laudus_service.BookIdentityError, match="ACTIVO FFCC"):
        laudus_service.verify_book_identity(get_book("RUT2"))


def test_verify_book_identity_aborta_sin_cuenta_raiz(monkeypatch):
    from pipeline.config.laudus_config import get_book

    monkeypatch.setattr(laudus_service.requests, "post", _fake_accounts_post([
        {"accountNumber": "111005", "name": "Banco BCI"},  # sin raíz "1"
    ]))
    with pytest.raises(laudus_service.BookIdentityError):
        laudus_service.verify_book_identity(get_book("EAG"))


def test_verify_book_identity_aborta_con_respuesta_no_lista(monkeypatch):
    from pipeline.config.laudus_config import get_book

    monkeypatch.setattr(laudus_service.requests, "post",
                        _fake_accounts_post({"error": "algo raro"}))
    with pytest.raises(laudus_service.BookIdentityError, match="lista"):
        laudus_service.verify_book_identity(get_book("EAG"))
