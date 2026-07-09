"""Tests del endpoint POST /api/v1/comments — Story 7.1 (FR36, AC1-AC5, AC7).

Primer endpoint de ESCRITURA que admite el rol `family`. Verifica el flujo completo:
el owner crea → 201 + línea persistida con ancla de 3 capas; tx inexistente → 404 sin escritura;
body vacío → 422. RBAC: family/contador/admin permitidos (allowlist = todos los roles válidos,
por eso un token sin auth válida cae en 401, no 403 — el 403 de `require_role` es inalcanzable acá).
"""
import pytest
from beancount.core import data
from beancount.parser import parser
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.auth.service import create_jwt
from backend.app.dependencies import get_ledger_service
from backend.app.middleware import add_middleware
from pipeline.importers import owner_comments_writer as ocw

LEDGER = """
2026-04-05 * "COMPRA X"
  Liabilities:EAG:TC:Real:TestCard   -300.00 CLP
  Expenses:EAG:Suspense               300.00 CLP
"""


def _entries():
    entries, errors, _ = parser.parse_string(LEDGER)
    assert not errors, errors
    for e in entries:
        if isinstance(e, data.Transaction):
            e.meta["filename"] = "cartola-2026-04.beancount"
    return [e for e in entries if isinstance(e, data.Transaction)]


def _tx_id():
    return ocw._tx_id_of(next(e for e in _entries() if e.narration == "COMPRA X"))


class _FakeLedger:
    def __init__(self, main_path, entries):
        self._main_path = main_path
        self._entries = entries

    @property
    def main_path(self):
        return self._main_path

    def entries(self):
        return self._entries


def _app(ledger):
    from backend.app.api.v1.owner_comments.router import router
    app = FastAPI()
    add_middleware(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_ledger_service] = lambda: ledger
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _no_git(monkeypatch):
    monkeypatch.delenv("IMPORTER_GIT_ENABLED", raising=False)


def _ledger(tmp_path):
    (tmp_path / "main.beancount").write_text(";; main\n", encoding="utf-8")
    return _FakeLedger(str(tmp_path / "main.beancount"), _entries())


# ── AC1/AC2/AC4: family crea → 201 + ancla completa persistida ────────────────


def test_family_crea_comentario_201_con_ancla_completa(tmp_path):
    client = _app(_ledger(tmp_path))
    resp = client.post(
        "/api/v1/comments",
        json={"tx_id": _tx_id(), "body": "¿qué es este cargo?"},
        cookies={"access_token": create_jwt(email="ary@eag.cl", role="family")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["thread_id"] == body["comment_id"]  # el raíz define el hilo
    assert body["created_at"]

    # AC4: la línea persistida trae la ancla de 3 capas + snapshot + autor
    threads = ocw.read_threads(ocw.default_jsonl_path(tmp_path))
    assert len(threads) == 1
    root = threads[0]["root"]
    assert root["author_email"] == "ary@eag.cl"
    assert root["author_role"] == "family"
    assert root["body"] == "¿qué es este cargo?"
    anchor = root["anchor"]
    assert anchor["tx_id"] == _tx_id()
    assert anchor["anchor_key"]
    assert anchor["tx_snapshot"]["narration"] == "COMPRA X"
    assert anchor["tx_snapshot"]["amount"] == -300.0


# ── AC2: contador y admin también pueden crear (allowlist = 3 roles) ──────────


def test_contador_y_admin_pueden_crear(tmp_path):
    for role in ("contador", "admin"):
        client = _app(_ledger(tmp_path))
        resp = client.post(
            "/api/v1/comments",
            json={"tx_id": _tx_id(), "body": f"comentario de {role}"},
            cookies={"access_token": create_jwt(email=f"{role}@eag.cl", role=role)},
        )
        assert resp.status_code == 201, resp.text


# ── AC3: tx inexistente → 404 sin escritura ───────────────────────────────────


def test_tx_inexistente_404_sin_escritura(tmp_path):
    client = _app(_ledger(tmp_path))
    resp = client.post(
        "/api/v1/comments",
        json={"tx_id": "noexiste0000", "body": "hola"},
        cookies={"access_token": create_jwt(email="ary@eag.cl", role="family")},
    )
    assert resp.status_code == 404
    # nada se escribió al JSONL
    assert ocw.read_threads(ocw.default_jsonl_path(tmp_path)) == []


# ── AC7: body vacío → 422 ─────────────────────────────────────────────────────


def test_body_vacio_422(tmp_path):
    client = _app(_ledger(tmp_path))
    for bad in ("", "   "):
        resp = client.post(
            "/api/v1/comments",
            json={"tx_id": _tx_id(), "body": bad},
            cookies={"access_token": create_jwt(email="ary@eag.cl", role="family")},
        )
        assert resp.status_code == 422, resp.text


# ── AC2 (auth): sin cookie / rol desconocido → 401 (el 403 es inalcanzable) ────


def test_sin_auth_401(tmp_path):
    client = _app(_ledger(tmp_path))
    resp = client.post("/api/v1/comments", json={"tx_id": _tx_id(), "body": "x"})
    assert resp.status_code == 401


def test_rol_desconocido_401(tmp_path):
    """Un JWT con rol fuera de {family,contador,admin} se rechaza en autenticación (401),
    no en autorización (403): la allowlist del endpoint son los 3 roles válidos."""
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    token = jwt.encode(
        {"sub": "x@x.cl", "role": "superadmin",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "dev-secret-change-in-production", algorithm="HS256",
    )
    client = _app(_ledger(tmp_path))
    resp = client.post("/api/v1/comments", json={"tx_id": _tx_id(), "body": "x"},
                       cookies={"access_token": token})
    assert resp.status_code == 401
