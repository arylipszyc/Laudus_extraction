"""Tests de resolución de hilos — Story 7.3 (FR40, AC1-AC5, AC7).

POST /api/v1/comments/{thread_id}/resolve appendea la línea de resolución (append-only, 7.0) y el
hilo sale de ?status=open. Idempotencia: doble resolución → 400 sin segunda escritura. Hilo
inexistente → 404 sin escritura. Ambos roles pueden resolver; un family solo hilos donde participa
(misma postura que reply, patch del review de 7.2).
"""
import json

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


def _entries(filename="cartola-2026-04.beancount"):
    entries, errors, _ = parser.parse_string(LEDGER)
    assert not errors, errors
    txns = [e for e in entries if isinstance(e, data.Transaction)]
    for e in txns:
        e.meta["filename"] = filename
    return txns


class _FakeLedger:
    def __init__(self, main_path, entries):
        self._main_path = main_path
        self._entries = entries

    @property
    def main_path(self):
        return self._main_path

    def entries(self):
        return self._entries


def _ledger(tmp_path, entries):
    (tmp_path / "main.beancount").write_text(";; main\n", encoding="utf-8")
    return _FakeLedger(str(tmp_path / "main.beancount"), entries)


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


def _cookie(email="ary@eag.cl", role="family"):
    return {"access_token": create_jwt(email=email, role=role)}


def _seed_root(tmp_path, entries, *, body="¿qué es este cargo?", email="ary@eag.cl",
               role="family", ts="2026-05-01T10:00:00Z"):
    tx = next(e for e in entries if e.narration == "COMPRA X")
    anchor = ocw.build_anchor(ocw._tx_id_of(tx), entries, ledger_root=tmp_path)
    comment = ocw.build_comment(anchor=anchor, author_email=email, author_role=role, body=body, ts=ts)
    ocw.append_comment(comment, ocw.default_jsonl_path(tmp_path))
    return comment["thread_id"]


def _resolution_lines(tmp_path):
    path = ocw.default_jsonl_path(tmp_path)
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").split("\n")
            if l.strip() and json.loads(l).get("type") == "resolution"]


# ── AC1: resolver un hilo abierto → línea de resolución + sale de open ─────────


def test_resolve_hilo_abierto(tmp_path):
    entries = _entries()
    tid = _seed_root(tmp_path, entries)
    client = _app(_ledger(tmp_path, entries))

    resp = client.post(f"/api/v1/comments/{tid}/resolve", json={},
                       cookies=_cookie(email="c@eag.cl", role="contador"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["thread_id"] == tid
    assert body["resolved_at"]

    # la línea de resolución quedó en el JSONL con quién/cuándo
    lines = _resolution_lines(tmp_path)
    assert len(lines) == 1
    res = lines[0]["resolution"]
    assert res["resolved_by"] == "c@eag.cl"
    assert res["resolved_by_role"] == "contador"
    assert res["resolved_at"] == body["resolved_at"]

    # AC5: sale de open, aparece en resolved y all (con su bloque resolution)
    assert client.get("/api/v1/comments", cookies=_cookie(role="contador")).json() == []
    resolved = client.get("/api/v1/comments?status=resolved", cookies=_cookie(role="contador")).json()
    assert [t["thread_id"] for t in resolved] == [tid]
    assert resolved[0]["resolution"]["resolved_by"] == "c@eag.cl"
    all_ = client.get("/api/v1/comments?status=all", cookies=_cookie(role="contador")).json()
    assert [t["thread_id"] for t in all_] == [tid]


def test_resolve_con_nota_opcional(tmp_path):
    entries = _entries()
    tid = _seed_root(tmp_path, entries)
    client = _app(_ledger(tmp_path, entries))

    resp = client.post(f"/api/v1/comments/{tid}/resolve", json={"note": "era el arriendo"},
                       cookies=_cookie(email="c@eag.cl", role="contador"))
    assert resp.status_code == 200, resp.text
    assert _resolution_lines(tmp_path)[0]["resolution"]["note"] == "era el arriendo"


# ── AC2: ambos roles pueden resolver — el family (participante) también ────────


def test_family_participante_resuelve(tmp_path):
    entries = _entries()
    tid = _seed_root(tmp_path, entries, email="ary@eag.cl")  # ary es el autor
    client = _app(_ledger(tmp_path, entries))

    resp = client.post(f"/api/v1/comments/{tid}/resolve", json={},
                       cookies=_cookie(email="ary@eag.cl", role="family"))
    assert resp.status_code == 200, resp.text


def test_family_no_participante_403_sin_escritura(tmp_path):
    """Misma postura que reply (patch 7.2): un family ajeno al hilo no puede resolverlo."""
    entries = _entries()
    tid = _seed_root(tmp_path, entries, email="otro@eag.cl")
    client = _app(_ledger(tmp_path, entries))

    resp = client.post(f"/api/v1/comments/{tid}/resolve", json={},
                       cookies=_cookie(email="ary@eag.cl", role="family"))
    assert resp.status_code == 403, resp.text
    assert _resolution_lines(tmp_path) == []


# ── AC3: idempotencia — doble resolución rechazada sin segunda escritura ───────


def test_doble_resolucion_400_sin_segunda_linea(tmp_path):
    entries = _entries()
    tid = _seed_root(tmp_path, entries)
    client = _app(_ledger(tmp_path, entries))

    first = client.post(f"/api/v1/comments/{tid}/resolve", json={},
                        cookies=_cookie(email="c@eag.cl", role="contador"))
    assert first.status_code == 200
    second = client.post(f"/api/v1/comments/{tid}/resolve", json={},
                         cookies=_cookie(email="c@eag.cl", role="contador"))
    assert second.status_code == 400, second.text
    assert len(_resolution_lines(tmp_path)) == 1  # una sola línea, la segunda no escribió


# ── AC4: thread_id inexistente → 404 sin escritura ─────────────────────────────


def test_resolve_thread_inexistente_404_sin_escritura(tmp_path):
    entries = _entries()
    _seed_root(tmp_path, entries)
    client = _app(_ledger(tmp_path, entries))

    resp = client.post("/api/v1/comments/no-existe-0000/resolve", json={},
                       cookies=_cookie(role="contador"))
    assert resp.status_code == 404
    assert _resolution_lines(tmp_path) == []


# ── sin auth → 401 ─────────────────────────────────────────────────────────────


def test_resolve_sin_auth_401(tmp_path):
    entries = _entries()
    tid = _seed_root(tmp_path, entries)
    client = _app(_ledger(tmp_path, entries))
    assert client.post(f"/api/v1/comments/{tid}/resolve", json={}).status_code == 401
