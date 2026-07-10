"""Tests del inbox de comentarios — Story 7.2 (FR38/FR39, AC1-AC5, AC7).

GET /api/v1/comments pliega hilos + re-resuelve el ancla en caliente (resolved / re-anchored tras
re-import / orphaned con snapshot) + ordena por última actividad + filtra por status.
POST /api/v1/comments/{id}/reply appendea sin cerrar; hilo inexistente → 404 sin escritura; body
vacío → 422; sin-auth → 401.
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
    """Transacciones del ledger. `filename` distinto = re-import (tx_id cambia, anchor_key no)."""
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
    """Escribe un comentario raíz al JSONL anclado a COMPRA X sobre `entries`. Devuelve thread_id."""
    tx = next(e for e in entries if e.narration == "COMPRA X")
    anchor = ocw.build_anchor(ocw._tx_id_of(tx), entries, ledger_root=tmp_path)
    comment = ocw.build_comment(anchor=anchor, author_email=email, author_role=role, body=body, ts=ts)
    ocw.append_comment(comment, ocw.default_jsonl_path(tmp_path))
    return comment["thread_id"]


# ── AC1/AC2: hilo con ancla resuelta trae contexto completo ───────────────────


def test_inbox_lista_hilo_resuelto_con_contexto(tmp_path):
    entries = _entries()
    _seed_root(tmp_path, entries)
    client = _app(_ledger(tmp_path, entries))

    resp = client.get("/api/v1/comments", cookies=_cookie(role="contador"))
    assert resp.status_code == 200, resp.text
    threads = resp.json()
    assert len(threads) == 1
    t = threads[0]
    assert t["anchor_status"] == "resolved"
    assert t["resolution"] is None
    ctx = t["tx_context"]
    assert ctx["date"] == "2026-04-05"
    assert ctx["amount"] == -300.0
    assert ctx["currency"] == "CLP"
    assert ctx["account"] == "Liabilities:EAG:TC:Real:TestCard"
    assert ctx["narration"] == "COMPRA X"
    assert ctx["anchor_status"] == "resolved"


# ── AC2: re-import cambia el tx_id → el ancla re-resuelve (contexto vivo) ──────


def test_inbox_re_anchored_tras_reimport(tmp_path):
    # comentario creado sobre la versión original de la cartola…
    _seed_root(tmp_path, _entries("cartola-2026-04.beancount"))
    # …y el ledger vivo tiene la versión re-importada (mismo dato contable, distinto filename → tx_id nuevo)
    reimported = _entries("cartola-2026-04-reimport.beancount")
    client = _app(_ledger(tmp_path, reimported))

    threads = client.get("/api/v1/comments", cookies=_cookie(role="contador")).json()
    assert len(threads) == 1
    t = threads[0]
    assert t["anchor_status"] == "re-anchored"  # el spike 7.0 en acción
    # el contexto viene de la tx VIVA, no del snapshot
    assert t["tx_context"]["narration"] == "COMPRA X"
    assert t["tx_context"]["amount"] == -300.0


# ── AC2: tx desaparecida → orphaned, contexto desde el snapshot congelado ─────


def test_inbox_orphaned_usa_snapshot(tmp_path):
    _seed_root(tmp_path, _entries())
    client = _app(_ledger(tmp_path, []))  # ledger vivo SIN la tx

    threads = client.get("/api/v1/comments", cookies=_cookie(role="contador")).json()
    assert len(threads) == 1
    t = threads[0]
    assert t["anchor_status"] == "orphaned"
    # degradado, no roto: el contexto sale del tx_snapshot capturado al crear
    assert t["tx_context"]["date"] == "2026-04-05"
    assert t["tx_context"]["amount"] == -300.0
    assert t["tx_context"]["account"] == "Liabilities:EAG:TC:Real:TestCard"


# ── AC1: orden por última actividad (una respuesta reciente sube el hilo) ──────


def test_orden_por_ultima_actividad(tmp_path):
    entries = _entries()
    path = ocw.default_jsonl_path(tmp_path)
    tid_a = _seed_root(tmp_path, entries, body="hilo A viejo", ts="2026-05-01T10:00:00Z")
    tid_b = _seed_root(tmp_path, entries, body="hilo B nuevo", ts="2026-05-02T10:00:00Z")
    client = _app(_ledger(tmp_path, entries))

    # sin respuestas: B (más nuevo) primero
    threads = client.get("/api/v1/comments", cookies=_cookie(role="contador")).json()
    assert [t["thread_id"] for t in threads] == [tid_b, tid_a]

    # una respuesta a A con ts posterior → A pasa a ser el más activo
    ocw.append_reply(tid_a, {"author_email": "c@eag.cl", "author_role": "contador",
                             "body": "respondo", "ts": "2026-05-03T10:00:00Z"}, path)
    threads = client.get("/api/v1/comments", cookies=_cookie(role="contador")).json()
    assert [t["thread_id"] for t in threads] == [tid_a, tid_b]


# ── AC1: filtro por status (open / resolved / all) ────────────────────────────


def test_filtro_status(tmp_path):
    entries = _entries()
    path = ocw.default_jsonl_path(tmp_path)
    tid_open = _seed_root(tmp_path, entries, body="abierto", ts="2026-05-01T10:00:00Z")
    tid_res = _seed_root(tmp_path, entries, body="resuelto", ts="2026-05-02T10:00:00Z")
    ocw.append_resolution(tid_res, {"action": "resolve", "resolved_by": "c@eag.cl",
                                    "resolved_at": "2026-05-02T12:00:00Z"}, path)
    client = _app(_ledger(tmp_path, entries))

    # default = open → solo el abierto
    open_threads = client.get("/api/v1/comments", cookies=_cookie(role="contador")).json()
    assert [t["thread_id"] for t in open_threads] == [tid_open]

    # resolved → solo el resuelto
    res_threads = client.get("/api/v1/comments?status=resolved", cookies=_cookie(role="contador")).json()
    assert [t["thread_id"] for t in res_threads] == [tid_res]
    assert res_threads[0]["resolution"]["action"] == "resolve"

    # all → ambos
    all_ids = {t["thread_id"] for t in
               client.get("/api/v1/comments?status=all", cookies=_cookie(role="contador")).json()}
    assert all_ids == {tid_open, tid_res}


# ── AC3: responder appendea y NO cierra el hilo ───────────────────────────────


def test_reply_appendea_no_cierra(tmp_path):
    entries = _entries()
    tid = _seed_root(tmp_path, entries)
    client = _app(_ledger(tmp_path, entries))

    resp = client.post(f"/api/v1/comments/{tid}/reply",
                       json={"body": "es el arriendo de abril"},
                       cookies=_cookie(email="c@eag.cl", role="contador"))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["comment_id"]
    assert body["created_at"]

    threads = ocw.read_threads(ocw.default_jsonl_path(tmp_path))
    assert len(threads[0]["replies"]) == 1
    assert threads[0]["replies"][0]["body"] == "es el arriendo de abril"
    assert threads[0]["replies"][0]["author_role"] == "contador"
    assert threads[0]["resolution"] is None  # NO se cerró (7.3)


# ── AC5: responder un hilo ya resuelto → se permite (append puro, no reabre) ───


def test_reply_a_hilo_resuelto_se_permite(tmp_path):
    entries = _entries()
    path = ocw.default_jsonl_path(tmp_path)
    tid = _seed_root(tmp_path, entries)
    ocw.append_resolution(tid, {"action": "resolve", "resolved_by": "c@eag.cl",
                                "resolved_at": "2026-05-02T12:00:00Z"}, path)
    client = _app(_ledger(tmp_path, entries))

    resp = client.post(f"/api/v1/comments/{tid}/reply", json={"body": "una aclaración post-cierre"},
                       cookies=_cookie(role="family"))
    assert resp.status_code == 201, resp.text
    threads = ocw.read_threads(path)
    assert threads[0]["resolution"] is not None  # sigue resuelto (no reabre)
    assert len(threads[0]["replies"]) == 1


# ── AC5: hilo inexistente → 404 sin escritura ─────────────────────────────────


def test_reply_thread_inexistente_404_sin_escritura(tmp_path):
    entries = _entries()
    tid = _seed_root(tmp_path, entries)
    client = _app(_ledger(tmp_path, entries))

    resp = client.post("/api/v1/comments/no-existe-0000/reply", json={"body": "hola"},
                       cookies=_cookie(role="contador"))
    assert resp.status_code == 404
    # nada se appendeó: el único hilo sigue sin respuestas
    threads = ocw.read_threads(ocw.default_jsonl_path(tmp_path))
    assert threads[0]["thread_id"] == tid
    assert threads[0]["replies"] == []


# ── AC7: body vacío → 422 ─────────────────────────────────────────────────────


def test_reply_body_vacio_422(tmp_path):
    entries = _entries()
    tid = _seed_root(tmp_path, entries)
    client = _app(_ledger(tmp_path, entries))
    for bad in ("", "   "):
        resp = client.post(f"/api/v1/comments/{tid}/reply", json={"body": bad},
                           cookies=_cookie(role="contador"))
        assert resp.status_code == 422, resp.text


# ── AC4: sin auth → 401 (GET y reply) ─────────────────────────────────────────


def test_sin_auth_401(tmp_path):
    entries = _entries()
    tid = _seed_root(tmp_path, entries)
    client = _app(_ledger(tmp_path, entries))
    assert client.get("/api/v1/comments").status_code == 401
    assert client.post(f"/api/v1/comments/{tid}/reply", json={"body": "x"}).status_code == 401


# ── AC4: el back acota por rol — el family solo ve SUS hilos, el contador todos ─


def test_inbox_family_solo_ve_sus_hilos(tmp_path):
    entries = _entries()
    tid_mine = _seed_root(tmp_path, entries, email="ary@eag.cl", ts="2026-05-01T10:00:00Z")
    _seed_root(tmp_path, entries, email="otro@eag.cl", ts="2026-05-02T10:00:00Z")
    client = _app(_ledger(tmp_path, entries))

    # el family solo ve el suyo (no depende del filtro del front)
    mine = client.get("/api/v1/comments", cookies=_cookie(email="ary@eag.cl", role="family")).json()
    assert [t["thread_id"] for t in mine] == [tid_mine]

    # el contador ve ambos
    both = client.get("/api/v1/comments", cookies=_cookie(role="contador")).json()
    assert len(both) == 2


# ── AC4: un family NO participante no puede responder → 403 sin escritura ──────


def test_reply_family_no_participante_403_sin_escritura(tmp_path):
    entries = _entries()
    tid = _seed_root(tmp_path, entries, email="otro@eag.cl")
    client = _app(_ledger(tmp_path, entries))

    resp = client.post(f"/api/v1/comments/{tid}/reply", json={"body": "me meto"},
                       cookies=_cookie(email="ary@eag.cl", role="family"))
    assert resp.status_code == 403, resp.text
    # nada se appendeó
    threads = ocw.read_threads(ocw.default_jsonl_path(tmp_path))
    assert threads[0]["replies"] == []

    # el contador sí puede responder ese hilo
    ok = client.post(f"/api/v1/comments/{tid}/reply", json={"body": "yo sí"},
                     cookies=_cookie(email="c@eag.cl", role="contador"))
    assert ok.status_code == 201, ok.text
