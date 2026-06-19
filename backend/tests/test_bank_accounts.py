"""Tests for bank_accounts endpoints — Story 9.14 (lee/escribe Beancount, no Supabase).

Reemplaza los mocks de SupabaseRepository por un ledger fixture en `tmp_path` (mismo patrón
que test_dashboard_beancount / test_cuentas_pendientes): GET arma el shape desde los `open`
con metadata bancaria; POST agrega metadata al open existente; PATCH cierra/reabre/edita.
"""
from subprocess import CalledProcessError

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.auth.service import create_jwt
from backend.app.dependencies import get_ledger_service
from backend.app.middleware import add_middleware
from backend.app.services.ledger_service import LedgerService

BCI_ID = "d844c24e-e5da-41c6-8734-039424f13613"
SANTANDER_ID = "a1111111-1111-1111-1111-111111111111"

ACCOUNTS = """\
2020-12-31 open Assets:EAG:Bancos:BancoBci-111005 CLP
  code: "111005"
  laudus_account_name: "Banco BCI - 10160175"
  bank_account_id: "d844c24e-e5da-41c6-8734-039424f13613"
  bank_name: "BCI"
  bank_account_type: "cta_corriente"
  bank_account_currency: "CLP"

2020-12-31 open Assets:EAG:Bancos:BancoSantander-111009 CLP
  code: "111009"
  laudus_account_name: "Banco Santander"
  bank_account_id: "a1111111-1111-1111-1111-111111111111"
  bank_name: "Santander"
  bank_account_type: "cta_corriente"
  bank_account_currency: "CLP"

2020-12-31 open Assets:EAG:Bancos:BancoNuevo-111011 CLP
  code: "111011"
  laudus_account_name: "Banco Nuevo sin registrar"

2020-12-31 open Expenses:EAG:Luz-413005 CLP
  code: "413005"
  laudus_account_name: "Luz"
  laudus_categoria1: "EGRESOS CASA SUR"
  laudus_categoria2: "Casa Sur"
  laudus_categoria3: "Servicios"
"""

MAIN = """\
option "operating_currency" "CLP"
1900-01-01 commodity CLP
include "accounts.beancount"
"""


def _make_ledger(tmp_path) -> LedgerService:
    (tmp_path / "accounts.beancount").write_text(ACCOUNTS, encoding="utf-8")
    main = tmp_path / "main.beancount"
    main.write_text(MAIN, encoding="utf-8")
    return LedgerService(str(main))


def _make_app(svc) -> TestClient:
    from backend.app.api.v1.bank_accounts.router import router as ba_router
    app = FastAPI()
    add_middleware(app)
    app.include_router(ba_router, prefix="/api/v1/bank-accounts")
    app.dependency_overrides[get_ledger_service] = lambda: svc
    return TestClient(app, raise_server_exceptions=False)


def _contador():
    return {"access_token": create_jwt(email="c@test.com", role="contador")}


def _family():
    return {"access_token": create_jwt(email="family@test.com", role="family")}


def _clean_env(monkeypatch):
    monkeypatch.delenv("IMPORTER_GIT_ENABLED", raising=False)  # git no-op
    monkeypatch.delenv("LEDGER_DIR", raising=False)            # refresh clone no-op


# ── AC1/AC2: GET lee de Beancount ───────────────────────────────────────────


def test_unauthenticated_returns_401(tmp_path):
    client = _make_app(_make_ledger(tmp_path))
    assert client.get("/api/v1/bank-accounts/").status_code == 401


def test_lista_solo_cuentas_bancarias_ordenadas(tmp_path):
    client = _make_app(_make_ledger(tmp_path))
    resp = client.get("/api/v1/bank-accounts/", cookies=_contador())
    assert resp.status_code == 200
    body = resp.json()
    # Solo las 2 con bank_account_id (NO la 111011 sin registrar ni la 413005 de gasto).
    assert [b["account_number"] for b in body] == ["111005", "111009"]
    bci = body[0]
    assert bci["id"] == BCI_ID
    assert bci["account_name"] == "Banco BCI - 10160175"
    assert bci["account_type"] == "cta_corriente"
    assert bci["account_currency"] == "CLP"
    assert bci["bank_name"] == "BCI"
    assert bci["active"] is True


def test_family_puede_listar(tmp_path):
    client = _make_app(_make_ledger(tmp_path))
    assert client.get("/api/v1/bank-accounts/", cookies=_family()).status_code == 200


# ── AC3: POST crea (agrega metadata al open existente) ──────────────────────


def test_create_agrega_metadata_a_cuenta_del_plan(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    svc = _make_ledger(tmp_path)
    client = _make_app(svc)
    resp = client.post(
        "/api/v1/bank-accounts/",
        json={"account_number": "111011", "account_type": "cta_corriente",
              "account_currency": "CLP", "bank_name": "Banco Nuevo"},
        cookies=_contador(),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["account_number"] == "111011"
    assert body["bank_name"] == "Banco Nuevo"
    assert body["active"] is True
    # Ahora aparece en la lista (3 cuentas bancarias).
    listed = client.get("/api/v1/bank-accounts/", cookies=_contador()).json()
    assert "111011" in [b["account_number"] for b in listed]
    # No duplicó el open (sigue habiendo un solo open de 111011).
    written = (tmp_path / "accounts.beancount").read_text(encoding="utf-8")
    assert written.count("open Assets:EAG:Bancos:BancoNuevo-111011") == 1


def test_create_account_number_inexistente_400(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    client = _make_app(_make_ledger(tmp_path))
    resp = client.post(
        "/api/v1/bank-accounts/",
        json={"account_number": "999999", "account_type": "cta_corriente", "account_currency": "CLP"},
        cookies=_contador(),
    )
    assert resp.status_code == 400


def test_create_ya_registrada_409(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    client = _make_app(_make_ledger(tmp_path))
    resp = client.post(
        "/api/v1/bank-accounts/",
        json={"account_number": "111005", "account_type": "cta_corriente", "account_currency": "CLP"},
        cookies=_contador(),
    )
    assert resp.status_code == 409


def test_create_family_403(tmp_path):
    client = _make_app(_make_ledger(tmp_path))
    resp = client.post(
        "/api/v1/bank-accounts/",
        json={"account_number": "111011", "account_type": "cta_corriente", "account_currency": "CLP"},
        cookies=_family(),
    )
    assert resp.status_code == 403


def test_create_tipo_invalido_422(tmp_path):
    client = _make_app(_make_ledger(tmp_path))
    resp = client.post(
        "/api/v1/bank-accounts/",
        json={"account_number": "111011", "account_type": "INVALIDO", "account_currency": "CLP"},
        cookies=_contador(),
    )
    assert resp.status_code == 422


# ── AC3: PATCH desactiva / reactiva / edita bank_name ───────────────────────


def test_patch_desactiva_escribe_close(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    svc = _make_ledger(tmp_path)
    client = _make_app(svc)
    resp = client.patch(f"/api/v1/bank-accounts/{BCI_ID}", json={"active": False}, cookies=_contador())
    assert resp.status_code == 200, resp.text
    assert resp.json()["active"] is False
    written = (tmp_path / "accounts.beancount").read_text(encoding="utf-8")
    assert "close Assets:EAG:Bancos:BancoBci-111005" in written
    # Reactivar quita el close.
    resp2 = client.patch(f"/api/v1/bank-accounts/{BCI_ID}", json={"active": True}, cookies=_contador())
    assert resp2.status_code == 200
    assert resp2.json()["active"] is True
    assert "close Assets:EAG:Bancos:BancoBci-111005" not in (tmp_path / "accounts.beancount").read_text(encoding="utf-8")


def test_patch_edita_bank_name(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    svc = _make_ledger(tmp_path)
    client = _make_app(svc)
    resp = client.patch(f"/api/v1/bank-accounts/{SANTANDER_ID}",
                        json={"bank_name": "Banco Santander Chile"}, cookies=_contador())
    assert resp.status_code == 200, resp.text
    assert resp.json()["bank_name"] == "Banco Santander Chile"


def test_patch_inexistente_404(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    client = _make_app(_make_ledger(tmp_path))
    resp = client.patch("/api/v1/bank-accounts/00000000-0000-0000-0000-000000000000",
                        json={"active": False}, cookies=_contador())
    assert resp.status_code == 404


def test_patch_vacio_400(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    client = _make_app(_make_ledger(tmp_path))
    resp = client.patch(f"/api/v1/bank-accounts/{BCI_ID}", json={}, cookies=_contador())
    assert resp.status_code == 400


def test_patch_family_403(tmp_path):
    client = _make_app(_make_ledger(tmp_path))
    resp = client.patch(f"/api/v1/bank-accounts/{BCI_ID}", json={"active": False}, cookies=_family())
    assert resp.status_code == 403


# ── Review: errores de escritura (espejo de 10.3) + toggle idempotente ──────


def test_patch_doble_desactivacion_es_idempotente(tmp_path, monkeypatch):
    # Desactivar una cuenta ya cerrada NO debe duplicar el close (que daría bean-check rojo/422).
    _clean_env(monkeypatch)
    svc = _make_ledger(tmp_path)
    client = _make_app(svc)
    assert client.patch(f"/api/v1/bank-accounts/{BCI_ID}", json={"active": False}, cookies=_contador()).status_code == 200
    r2 = client.patch(f"/api/v1/bank-accounts/{BCI_ID}", json={"active": False}, cookies=_contador())
    assert r2.status_code == 200, r2.text
    assert r2.json()["active"] is False
    written = (tmp_path / "accounts.beancount").read_text(encoding="utf-8")
    assert written.count("close Assets:EAG:Bancos:BancoBci-111005") == 1


def test_create_push_de_git_falla_502_no_500(tmp_path, monkeypatch):
    # bean-check pasó pero el push falló → 502 claro (no 500, no enmascarado como éxito).
    _clean_env(monkeypatch)
    import backend.app.api.v1.bank_accounts.service as service

    def _raise(*a, **k):
        raise CalledProcessError(1, ["git", "push"])

    monkeypatch.setattr(service, "apply_to_accounts", _raise)
    client = _make_app(_make_ledger(tmp_path))
    resp = client.post("/api/v1/bank-accounts/",
                       json={"account_number": "111011", "account_type": "cta_corriente", "account_currency": "CLP"},
                       cookies=_contador())
    assert resp.status_code == 502, resp.text


def test_patch_lock_ocupado_409_no_500(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    import backend.app.api.v1.bank_accounts.service as service
    from pipeline.importers.laudus_run import LockTimeout

    def _raise(*a, **k):
        raise LockTimeout("import lock ocupado")

    monkeypatch.setattr(service, "apply_to_accounts", _raise)
    client = _make_app(_make_ledger(tmp_path))
    resp = client.patch(f"/api/v1/bank-accounts/{BCI_ID}", json={"active": False}, cookies=_contador())
    assert resp.status_code == 409, resp.text
