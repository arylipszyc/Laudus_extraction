"""Tests del conteo de no-leídos + marcador de lectura — Story 7.4 (FR37/FR41 in-app, AC1-AC5, AC7).

GET /comments/count devuelve {total, unread} SEGÚN el usuario del JWT: el contador cuenta
actividad del owner sin leer; el owner cuenta respuestas del contador sin leer. Solo hilos
abiertos. POST /comments/{id}/read appendea el marcador append-only (type="read") y baja el
unread de ESE usuario. La propia actividad nunca cuenta como no-leída (AC5).
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


def _reply(tmp_path, tid, *, email="c@eag.cl", role="contador", ts="2026-05-02T10:00:00Z"):
    ocw.append_reply(tid, {"author_email": email, "author_role": role,
                           "body": "respuesta", "ts": ts}, ocw.default_jsonl_path(tmp_path))


def _count(client, *, email, role):
    resp = client.get("/api/v1/comments/count", cookies=_cookie(email=email, role=role))
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── AC1/AC5: conteo según rol — la propia actividad no cuenta ─────────────────


def test_contador_cuenta_pregunta_del_owner_sin_leer(tmp_path):
    entries = _entries()
    _seed_root(tmp_path, entries)  # pregunta del owner
    client = _app(_ledger(tmp_path, entries))

    # el contador tiene 1 no-leído; el owner (autor) 0 (AC5: su propio comentario no le cuenta)
    assert _count(client, email="c@eag.cl", role="contador") == {"total": 1, "unread": 1}
    assert _count(client, email="ary@eag.cl", role="family") == {"total": 1, "unread": 0}


def test_owner_cuenta_respuesta_del_contador_sin_leer(tmp_path):
    entries = _entries()
    tid = _seed_root(tmp_path, entries)
    _reply(tmp_path, tid)  # respuesta del contador
    client = _app(_ledger(tmp_path, entries))

    # ahora el owner tiene 1 no-leído; el contador que respondió, 0 por su propia respuesta —
    # pero la pregunta original del owner sigue sin marcar como leída → sigue 1 para él
    assert _count(client, email="ary@eag.cl", role="family")["unread"] == 1
    contador = _count(client, email="c@eag.cl", role="contador")
    assert contador["unread"] == 1  # la pregunta del owner sigue sin leer (su reply no la marca)


# ── AC2/AC4: marcador de leído append-only baja el unread de ESE usuario ──────


def test_read_marker_baja_unread_solo_del_lector(tmp_path):
    entries = _entries()
    tid = _seed_root(tmp_path, entries)
    _reply(tmp_path, tid)
    client = _app(_ledger(tmp_path, entries))

    resp = client.post(f"/api/v1/comments/{tid}/read",
                       cookies=_cookie(email="ary@eag.cl", role="family"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["thread_id"] == tid

    # el owner leyó → su unread baja; el del contador NO cambia
    assert _count(client, email="ary@eag.cl", role="family")["unread"] == 0
    assert _count(client, email="c@eag.cl", role="contador")["unread"] == 1


def test_actividad_nueva_despues_de_leer_vuelve_a_contar(tmp_path):
    entries = _entries()
    tid = _seed_root(tmp_path, entries)
    _reply(tmp_path, tid, ts="2026-05-02T10:00:00Z")
    client = _app(_ledger(tmp_path, entries))

    client.post(f"/api/v1/comments/{tid}/read", cookies=_cookie(email="ary@eag.cl", role="family"))
    assert _count(client, email="ary@eag.cl", role="family")["unread"] == 0

    # nueva respuesta del contador POSTERIOR al read_at → vuelve a ser no-leído
    _reply(tmp_path, tid, ts="2027-01-01T10:00:00Z")
    assert _count(client, email="ary@eag.cl", role="family")["unread"] == 1


# ── AC1: los hilos resueltos no notifican ─────────────────────────────────────


def test_hilo_resuelto_no_cuenta(tmp_path):
    entries = _entries()
    tid = _seed_root(tmp_path, entries)
    ocw.append_resolution(tid, {"action": "resolve", "resolved_by": "c@eag.cl",
                                "resolved_at": "2026-05-03T10:00:00Z"},
                          ocw.default_jsonl_path(tmp_path))
    client = _app(_ledger(tmp_path, entries))

    assert _count(client, email="c@eag.cl", role="contador") == {"total": 0, "unread": 0}


# ── scoping family: el hilo de otro owner no cuenta ni se puede marcar ────────


def test_family_no_cuenta_hilos_ajenos(tmp_path):
    entries = _entries()
    tid_otro = _seed_root(tmp_path, entries, email="otro@eag.cl")
    _reply(tmp_path, tid_otro)  # respuesta del contador al OTRO owner
    client = _app(_ledger(tmp_path, entries))

    # ary no participa de ese hilo → ni total ni unread
    assert _count(client, email="ary@eag.cl", role="family") == {"total": 0, "unread": 0}
    # y no puede marcarlo leído (misma postura que reply/resolve)
    resp = client.post(f"/api/v1/comments/{tid_otro}/read",
                       cookies=_cookie(email="ary@eag.cl", role="family"))
    assert resp.status_code == 403


# ── read: hilo inexistente → 404; sin auth → 401 ──────────────────────────────


def test_read_inexistente_404_y_sin_auth_401(tmp_path):
    entries = _entries()
    tid = _seed_root(tmp_path, entries)
    client = _app(_ledger(tmp_path, entries))
    assert client.post("/api/v1/comments/no-existe/read",
                       cookies=_cookie(role="contador")).status_code == 404
    assert client.post(f"/api/v1/comments/{tid}/read").status_code == 401
    assert client.get("/api/v1/comments/count").status_code == 401


# ── ThreadView.unread en el inbox (para el indicador y el mark-read selectivo) ─


def test_inbox_expone_unread_por_usuario(tmp_path):
    entries = _entries()
    tid = _seed_root(tmp_path, entries)
    client = _app(_ledger(tmp_path, entries))

    threads = client.get("/api/v1/comments", cookies=_cookie(email="c@eag.cl", role="contador")).json()
    assert threads[0]["unread"] is True

    client.post(f"/api/v1/comments/{tid}/read", cookies=_cookie(email="c@eag.cl", role="contador"))
    threads = client.get("/api/v1/comments", cookies=_cookie(email="c@eag.cl", role="contador")).json()
    assert threads[0]["unread"] is False
