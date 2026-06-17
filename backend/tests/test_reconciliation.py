"""Tests del backend de reconciliación — Story 9.12 AC1/AC2/AC3/AC4/AC9."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.reconciliation import service as svc
from backend.app.auth.service import create_jwt
from backend.app.middleware import add_middleware


def _jsonl(tmp_path, entries):
    p = tmp_path / "cartola-discrepancies.jsonl"
    p.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return p


def _disc(did, state, ym="2026-04", bank="acc1"):
    return {"schema_version": "1.0", "discrepancy_id": did, "ts": "2026-05-05T00:00:00Z",
            "batch_id": "b1", "bank_account_id": bank, "state": state,
            "cartola": {"line_no": 1, "date": f"{ym}-15", "amount": -45000, "currency": "CLP", "description": "X"},
            "laudus": {"journal_entry_id": "J1", "date": f"{ym}-15", "amount": -47000, "description": "Y"},
            "fx": {"implied": None, "bcch": None, "deviation_pct": None}, "resolution": None}


# ── AC1: lista + filtros + summary ────────────────────────────────────────────


def test_read_filtra_resueltas_y_arma_summary(tmp_path):
    p = _jsonl(tmp_path, [
        _disc("d1", "value-mismatch"),
        _disc("d2", "missing-in-laudus"),
        _disc("d3", "missing-in-laudus"),
        {"ref_discrepancy_id": "d2", "resolution": {"action": "confirm-cartola-only"}},  # d2 resuelta
    ])
    out = svc.read_discrepancies(path=p)
    ids = {d["discrepancy_id"] for d in out["discrepancies"]}
    assert ids == {"d1", "d3"}  # d2 resuelta → oculta
    assert out["summary"]["total"] == 2
    assert out["summary"]["by_state"] == {"value-mismatch": 1, "missing-in-laudus": 1}


def test_filtro_por_state_y_year_month(tmp_path):
    p = _jsonl(tmp_path, [_disc("d1", "value-mismatch", ym="2026-04"),
                          _disc("d2", "value-mismatch", ym="2026-03")])
    assert len(svc.read_discrepancies(path=p, year_month="2026-04")["discrepancies"]) == 1
    assert len(svc.read_discrepancies(path=p, state="missing-in-laudus")["discrepancies"]) == 0


def test_deep_link_por_id_incluye_resueltas(tmp_path):
    p = _jsonl(tmp_path, [_disc("d1", "value-mismatch"),
                          {"ref_discrepancy_id": "d1", "resolution": {"action": "accept-cartola"}}])
    # sin id, d1 está resuelta → no aparece
    assert svc.read_discrepancies(path=p)["discrepancies"] == []
    # con id (deep-link), aparece igual
    assert len(svc.read_discrepancies(path=p, discrepancy_id="d1")["discrepancies"]) == 1


# ── AC2: history ──────────────────────────────────────────────────────────────


def test_history(tmp_path):
    p = _jsonl(tmp_path, [_disc("d1", "value-mismatch"),
                          {"ref_discrepancy_id": "d1", "resolution": {"action": "accept-cartola"}}])
    h = svc.history("d1", path=p)
    assert len(h) == 2


# ── AC9: count {total, blocking} ──────────────────────────────────────────────


def test_count_blocking(tmp_path):
    p = _jsonl(tmp_path, [_disc("d1", "value-mismatch"), _disc("d2", "fx-out-of-tolerance"),
                          _disc("d3", "missing-in-laudus")])
    c = svc.pending_count(path=p)
    assert c == {"total": 3, "blocking": 2}  # value-mismatch + fx-out-of-tolerance


# ── AC3/AC4: resolve + escalate ───────────────────────────────────────────────


def test_resolve_appendea_y_oculta(tmp_path):
    p = _jsonl(tmp_path, [_disc("d1", "value-mismatch")])
    res = svc.resolve("d1", "accept-cartola", "el banco informó mal, voy a corregir Laudus",
                      user_email="c@test.com", now_iso="2026-05-05T00:00:00Z", path=p)
    assert res["status"] == "resolved"
    assert svc.read_discrepancies(path=p)["discrepancies"] == []  # ya oculta


def test_resolve_accion_invalida(tmp_path):
    p = _jsonl(tmp_path, [_disc("d1", "value-mismatch")])
    with pytest.raises(svc.ResolveError):
        svc.resolve("d1", "accept-bcch-fx", "x" * 20, user_email="c", now_iso="t", path=p)


def test_resolve_justificacion_corta(tmp_path):
    p = _jsonl(tmp_path, [_disc("d1", "value-mismatch")])
    with pytest.raises(svc.ResolveError):
        svc.resolve("d1", "accept-cartola", "corta", user_email="c", now_iso="t", path=p)


def test_escalate_no_cierra(tmp_path):
    p = _jsonl(tmp_path, [_disc("d1", "value-mismatch")])
    svc.resolve("d1", "escalate", None, user_email="c@test.com", now_iso="2026-05-05T00:00:00Z", path=p)
    # escalate no oculta la discrepancia (AC4)
    assert len(svc.read_discrepancies(path=p)["discrepancies"]) == 1


# ── RBAC ──────────────────────────────────────────────────────────────────────


def test_rbac_family_403():
    from backend.app.api.v1.reconciliation.router import router
    app = FastAPI(); add_middleware(app); app.include_router(router, prefix="/api/v1")
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/v1/reconciliation/discrepancies",
                      cookies={"access_token": create_jwt(email="f@test.com", role="family")})
    assert resp.status_code == 403
