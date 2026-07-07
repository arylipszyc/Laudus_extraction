"""Integration tests for /api/v1/cartolas/* — Story 9.5 Tasks 3 + 7 + 9.

Gemini is mocked. RBAC, multipart, validations, async flow, staging file.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.cartolas.router import router as cartolas_router, get_gemini_client
from backend.app.api.v1.cartolas.service import get_job_store
from backend.app.auth.service import create_jwt
from backend.app.integrations.bank_account_index import (
    BankAccountEntry,
    BankAccountIndex,
    get_bank_account_index,
)
from backend.app.middleware import add_middleware


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_jobs():
    get_job_store().reset_for_testing()
    yield
    get_job_store().reset_for_testing()


@pytest.fixture
def staging_dir(tmp_path: Path) -> Path:
    d = tmp_path / "_staging"
    d.mkdir()
    return d


def _entry(*, last4: str | None = "0175", currency: str = "CLP") -> BankAccountEntry:
    return BankAccountEntry(
        bank_account_id="uuid-bci",
        bank_name="BCI",
        account_label="BCI 10160175",
        account_type="cta_corriente",
        entity="EAG",
        currency=currency,
        last4=last4,
        beancount_account="Assets:EAG:Bancos:Bci-111005",
    )


def _fake_gemini_returning(payload: dict) -> MagicMock:
    fake = MagicMock()
    fake.model = "gemini-2.5-flash"
    fake.extract_pdf.return_value = payload
    return fake


def _valid_gemini_payload(*, currency: str = "CLP") -> dict:
    return {
        "schema_version": "1.0",
        "source": {
            "bank_account_id": "uuid-bci",
            "bank_name": "BCI",
            "account_label": "BCI 10160175",
            "account_type": "cta_corriente",
            "entity": "EAG",
        },
        "period": {"start": "2026-03-01", "end": "2026-03-31"},
        "currency": currency,
        "balances": {"opening": "150000.00", "closing": "95000.00"},
        "transactions": [
            {
                "line_no": 1,
                "date": "2026-03-05",
                "description": "SUPERMERCADO JUMBO",
                "amount": "-45000.00",
                "currency": currency,
                "raw": {},
            }
        ],
        "extraction": {
            "model": "gemini-2.5-flash",
            "extracted_at": "2026-04-30T15:00:00Z",
            "warnings": [],
        },
    }


def _make_app(
    *,
    index_entry: BankAccountEntry | None,
    gemini_mock: MagicMock,
    staging_dir: Path,
) -> TestClient:
    app = FastAPI()
    add_middleware(app)
    app.include_router(cartolas_router, prefix="/api/v1")

    fake_index = MagicMock(spec=BankAccountIndex)
    fake_index.get.return_value = index_entry
    app.dependency_overrides[get_bank_account_index] = lambda: fake_index
    app.dependency_overrides[get_gemini_client] = lambda: gemini_mock

    # Patch the staging dir on the service so we don't touch the real ledger.
    patcher = patch(
        "backend.app.api.v1.cartolas.service._DEFAULT_STAGING_DIR", staging_dir
    )
    patcher.start()

    client = TestClient(app, raise_server_exceptions=False)
    client._patcher = patcher  # type: ignore[attr-defined]
    return client


def _admin_cookie() -> dict[str, str]:
    return {"access_token": create_jwt(email="ary@test.com", role="admin")}


def _contador_cookie() -> dict[str, str]:
    return {"access_token": create_jwt(email="contador@test.com", role="contador")}


def _family_cookie() -> dict[str, str]:
    return {"access_token": create_jwt(email="eduardo@eag.cl", role="family")}


def _tc_result() -> dict:
    return {
        "batch_id": "b1", "status": "corrected", "currency": "USD", "fx": "930.85",
        "purchases": 40, "payments": 1, "opening_emitted": True,
        "fx_bcch": "861.19", "fx_deviation_pct": 8.1, "git_sha": None, "reason": None,
        "tc_real_account": None, "expense_tc_account": None, "year_month": None,
        "cuadre_bank_account_id": None,
    }


def test_validate_balance_tc_corrected_202_y_resultado_por_polling(tmp_path):
    # Batch 2 Fase 3: el PATCH devuelve 202 (antes 200 sincrónico de 30-120s) y el payload
    # TcCorrectionResponse llega vía GET /{batch_id} cuando el job termina. TestClient corre
    # el background task antes de devolver → el poll inmediato ya lo ve confirmed.
    from backend.app.dependencies import get_ledger_service

    client = _make_app(index_entry=None, gemini_mock=MagicMock(), staging_dir=tmp_path)
    client.app.dependency_overrides[get_ledger_service] = lambda: MagicMock()

    with patch("backend.app.api.v1.cartolas.router.precheck_balance", return_value=None),          patch("backend.app.api.v1.cartolas.service.validate_balance",
               return_value=_tc_result()):
        r = client.patch("/api/v1/cartolas/b1/validate-balance",
                         json={"opening": "0", "closing": "0"}, cookies=_contador_cookie())
    assert r.status_code == 202, r.text
    assert r.json() == {"status": "confirming", "batch_id": "b1"}

    s = client.get("/api/v1/cartolas/b1", cookies=_contador_cookie())
    assert s.status_code == 200, s.text
    body = s.json()
    assert body["status"] == "confirmed"
    assert body["result"]["status"] == "corrected"
    assert body["result"]["fx"] == "930.85"
    assert body["result"]["purchases"] == 40
    # El plumbing del cuadre no se filtra al payload:
    assert "tc_real_account" not in body["result"]


def test_validate_balance_double_submit_no_relanza_el_job(tmp_path):
    # Un confirm en vuelo: el 2º PATCH devuelve 202 idempotente SIN lanzar otro job.
    from backend.app.api.v1.cartolas.service import get_job_store

    client = _make_app(index_entry=None, gemini_mock=MagicMock(), staging_dir=tmp_path)
    get_job_store().create("b2")
    assert get_job_store().set_confirming("b2") is True    # 1er confirm adquiere
    calls = {"n": 0}

    def counting_job(*args, **kwargs):
        calls["n"] += 1

    with patch("backend.app.api.v1.cartolas.router.precheck_balance", return_value=None),          patch("backend.app.api.v1.cartolas.router.run_confirm_job", side_effect=counting_job):
        r = client.patch("/api/v1/cartolas/b2/validate-balance",
                         json={"opening": "0", "closing": "0"}, cookies=_contador_cookie())
    assert r.status_code == 202
    assert calls["n"] == 0, "con un confirm en vuelo NO debe lanzarse un segundo job"


def test_validate_balance_excepcion_en_job_deja_confirm_failed(tmp_path):
    # Una excepción no tipada en el camino pesado → poll ve confirm_failed INTERNAL_ERROR
    # (el job jamás queda colgado en confirming).
    from backend.app.dependencies import get_ledger_service

    client = _make_app(index_entry=None, gemini_mock=MagicMock(), staging_dir=tmp_path)
    client.app.dependency_overrides[get_ledger_service] = lambda: MagicMock()

    with patch("backend.app.api.v1.cartolas.router.precheck_balance", return_value=None),          patch("backend.app.api.v1.cartolas.service.validate_balance",
               side_effect=RuntimeError("git push murió")):
        r = client.patch("/api/v1/cartolas/b3/validate-balance",
                         json={"opening": "0", "closing": "0"}, cookies=_contador_cookie())
    assert r.status_code == 202

    s = client.get("/api/v1/cartolas/b3", cookies=_contador_cookie())
    body = s.json()
    assert body["status"] == "confirm_failed"
    assert body["error"]["code"] == "INTERNAL_ERROR"
    # Mensaje GENÉRICO: el str(exc) de git puede traer URLs/paths del server (patch review).
    assert "git push murió" not in body["error"]["message"]
    assert "logs" in body["error"]["message"]


def test_validate_balance_tc_blocked_llega_como_confirmed_blocked(tmp_path):
    # Matriz row 7: blocked es un RESULTADO (no un error) → poll ve confirmed con status blocked.
    from backend.app.dependencies import get_ledger_service

    client = _make_app(index_entry=None, gemini_mock=MagicMock(), staging_dir=tmp_path)
    client.app.dependency_overrides[get_ledger_service] = lambda: MagicMock()
    blocked = dict(_tc_result(), status="blocked", fx=None,
                   reason="FX derivado no cuadra vs BCCh")

    with patch("backend.app.api.v1.cartolas.router.precheck_balance", return_value=None),          patch("backend.app.api.v1.cartolas.service.validate_balance", return_value=blocked):
        r = client.patch("/api/v1/cartolas/b4/validate-balance",
                         json={"opening": "0", "closing": "0"}, cookies=_contador_cookie())
    assert r.status_code == 202

    body = client.get("/api/v1/cartolas/b4", cookies=_contador_cookie()).json()
    assert body["status"] == "confirmed"
    assert body["result"]["status"] == "blocked"
    assert "BCCh" in body["result"]["reason"]


def test_validate_balance_bean_check_failed_mapea_su_codigo(tmp_path):
    # Matriz row 6 (belt: BeanCheckFailed está inerte desde 6.1 — el flujo real devuelve
    # blocked — pero el mapping del código se fija sintéticamente por si revive).
    from backend.app.api.v1.cartolas.service import BeanCheckFailed
    from backend.app.dependencies import get_ledger_service

    client = _make_app(index_entry=None, gemini_mock=MagicMock(), staging_dir=tmp_path)
    client.app.dependency_overrides[get_ledger_service] = lambda: MagicMock()

    with patch("backend.app.api.v1.cartolas.router.precheck_balance", return_value=None),          patch("backend.app.api.v1.cartolas.service.validate_balance",
               side_effect=BeanCheckFailed("cuenta sin abrir: Expenses:X")):
        r = client.patch("/api/v1/cartolas/b5/validate-balance",
                         json={"opening": "0", "closing": "0"}, cookies=_contador_cookie())
    assert r.status_code == 202

    body = client.get("/api/v1/cartolas/b5", cookies=_contador_cookie()).json()
    assert body["status"] == "confirm_failed"
    assert body["error"]["code"] == "BEAN_CHECK_FAILED"
    assert "cuenta sin abrir" in body["error"]["detail"]


def _pdf_payload(content: bytes = b"%PDF-1.4 fake content") -> dict:
    return {
        "files": {"pdf_file": ("cartola.pdf", content, "application/pdf")},
        "data": {"bank_account_id": "uuid-bci"},
    }


# ── RBAC (Story 9.13 matriz) ──────────────────────────────────────────────


def test_upload_unauthenticated_returns_401(staging_dir):
    client = _make_app(
        index_entry=_entry(),
        gemini_mock=_fake_gemini_returning(_valid_gemini_payload()),
        staging_dir=staging_dir,
    )
    p = _pdf_payload()
    resp = client.post("/api/v1/cartolas/upload", files=p["files"], data=p["data"])
    assert resp.status_code == 401


def test_upload_family_returns_403(staging_dir):
    client = _make_app(
        index_entry=_entry(),
        gemini_mock=_fake_gemini_returning(_valid_gemini_payload()),
        staging_dir=staging_dir,
    )
    p = _pdf_payload()
    resp = client.post(
        "/api/v1/cartolas/upload",
        files=p["files"], data=p["data"], cookies=_family_cookie(),
    )
    assert resp.status_code == 403


def test_upload_contador_accepted(staging_dir):
    client = _make_app(
        index_entry=_entry(),
        gemini_mock=_fake_gemini_returning(_valid_gemini_payload()),
        staging_dir=staging_dir,
    )
    p = _pdf_payload()
    resp = client.post(
        "/api/v1/cartolas/upload",
        files=p["files"], data=p["data"], cookies=_contador_cookie(),
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "processing"
    assert "batch_id" in body


def test_upload_admin_accepted(staging_dir):
    client = _make_app(
        index_entry=_entry(),
        gemini_mock=_fake_gemini_returning(_valid_gemini_payload()),
        staging_dir=staging_dir,
    )
    p = _pdf_payload()
    resp = client.post(
        "/api/v1/cartolas/upload",
        files=p["files"], data=p["data"], cookies=_admin_cookie(),
    )
    assert resp.status_code == 202


def test_get_status_family_returns_403(staging_dir):
    client = _make_app(
        index_entry=_entry(),
        gemini_mock=_fake_gemini_returning(_valid_gemini_payload()),
        staging_dir=staging_dir,
    )
    resp = client.get("/api/v1/cartolas/anything", cookies=_family_cookie())
    assert resp.status_code == 403


# ── Input validation (AC1) ────────────────────────────────────────────────


def test_upload_missing_last4_returns_400(staging_dir):
    client = _make_app(
        index_entry=_entry(last4=None),
        gemini_mock=_fake_gemini_returning(_valid_gemini_payload()),
        staging_dir=staging_dir,
    )
    p = _pdf_payload()
    resp = client.post(
        "/api/v1/cartolas/upload",
        files=p["files"], data=p["data"], cookies=_contador_cookie(),
    )
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["code"] == "MISSING_LAST4"
    assert "Fava" in err["message"]


def test_upload_unknown_bank_account_returns_400(staging_dir):
    client = _make_app(
        index_entry=None,
        gemini_mock=_fake_gemini_returning(_valid_gemini_payload()),
        staging_dir=staging_dir,
    )
    p = _pdf_payload()
    resp = client.post(
        "/api/v1/cartolas/upload",
        files=p["files"], data=p["data"], cookies=_contador_cookie(),
    )
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["code"] == "VALIDATION_FAILED"
    assert "not registered" in err["message"]


def test_upload_oversize_pdf_returns_400(staging_dir):
    client = _make_app(
        index_entry=_entry(),
        gemini_mock=_fake_gemini_returning(_valid_gemini_payload()),
        staging_dir=staging_dir,
    )
    huge = b"%PDF-1.4 " + b"A" * (21 * 1024 * 1024)
    p = {
        "files": {"pdf_file": ("big.pdf", huge, "application/pdf")},
        "data": {"bank_account_id": "uuid-bci"},
    }
    resp = client.post(
        "/api/v1/cartolas/upload",
        files=p["files"], data=p["data"], cookies=_contador_cookie(),
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_FAILED"


def test_upload_wrong_mime_returns_400(staging_dir):
    client = _make_app(
        index_entry=_entry(),
        gemini_mock=_fake_gemini_returning(_valid_gemini_payload()),
        staging_dir=staging_dir,
    )
    p = {
        "files": {"pdf_file": ("img.png", b"%PDF-1.4 nope", "image/png")},
        "data": {"bank_account_id": "uuid-bci"},
    }
    resp = client.post(
        "/api/v1/cartolas/upload",
        files=p["files"], data=p["data"], cookies=_contador_cookie(),
    )
    assert resp.status_code == 400


def test_upload_non_pdf_magic_bytes_returns_400(staging_dir):
    client = _make_app(
        index_entry=_entry(),
        gemini_mock=_fake_gemini_returning(_valid_gemini_payload()),
        staging_dir=staging_dir,
    )
    p = {
        "files": {"pdf_file": ("fake.pdf", b"NOT A PDF", "application/pdf")},
        "data": {"bank_account_id": "uuid-bci"},
    }
    resp = client.post(
        "/api/v1/cartolas/upload",
        files=p["files"], data=p["data"], cookies=_contador_cookie(),
    )
    assert resp.status_code == 400


# ── Async flow (AC10) + staging file (AC8) ────────────────────────────────


def test_full_flow_upload_then_status_returns_canonical(staging_dir):
    fake = _fake_gemini_returning(_valid_gemini_payload())
    client = _make_app(index_entry=_entry(), gemini_mock=fake, staging_dir=staging_dir)
    p = _pdf_payload()

    upload_resp = client.post(
        "/api/v1/cartolas/upload",
        files=p["files"], data=p["data"], cookies=_contador_cookie(),
    )
    assert upload_resp.status_code == 202
    batch_id = upload_resp.json()["batch_id"]

    # FastAPI BackgroundTasks runs after the response is dispatched in the test
    # client. By the time we issue the GET, the task has completed.
    status_resp = client.get(
        f"/api/v1/cartolas/{batch_id}",
        cookies=_contador_cookie(),
    )
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "ready"
    assert body["canonical"]["schema_version"] == "1.0"
    assert body["canonical"]["source"]["bank_account_id"] == "uuid-bci"
    # AC5: server-side override of source — Gemini's source field is replaced.
    assert body["canonical"]["source"]["entity"] == "EAG"


def test_staging_file_written_after_processing(staging_dir):
    fake = _fake_gemini_returning(_valid_gemini_payload())
    client = _make_app(index_entry=_entry(), gemini_mock=fake, staging_dir=staging_dir)
    p = _pdf_payload()

    resp = client.post(
        "/api/v1/cartolas/upload",
        files=p["files"], data=p["data"], cookies=_contador_cookie(),
    )
    batch_id = resp.json()["batch_id"]

    # Wait for the background task — TestClient dispatches them eagerly post-response.
    expected = staging_dir / f"{batch_id}.cartola.json"
    assert expected.exists(), f"expected staging file at {expected}"
    import json as _json
    parsed = _json.loads(expected.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == "1.0"


def test_status_unknown_batch_returns_404(staging_dir):
    client = _make_app(
        index_entry=_entry(),
        gemini_mock=_fake_gemini_returning(_valid_gemini_payload()),
        staging_dir=staging_dir,
    )
    resp = client.get(
        "/api/v1/cartolas/does-not-exist",
        cookies=_contador_cookie(),
    )
    assert resp.status_code == 404


def test_invalid_gemini_response_marks_job_failed(staging_dir):
    """AC4: Pydantic validation failure → status=failed (not 422 since async)."""
    bad_payload = {"schema_version": "1.0"}  # missing required fields
    fake = _fake_gemini_returning(bad_payload)
    client = _make_app(index_entry=_entry(), gemini_mock=fake, staging_dir=staging_dir)
    p = _pdf_payload()

    upload = client.post(
        "/api/v1/cartolas/upload",
        files=p["files"], data=p["data"], cookies=_contador_cookie(),
    )
    batch_id = upload.json()["batch_id"]

    status = client.get(
        f"/api/v1/cartolas/{batch_id}", cookies=_contador_cookie(),
    )
    body = status.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "EXTRACTION_FAILED"


def test_post_process_warnings_appended_to_canonical(staging_dir):
    """End-to-end: duplicate transaction → backend appends DUPLICATE_LINE warning."""
    payload = _valid_gemini_payload()
    payload["transactions"] = [
        {"line_no": 1, "date": "2026-03-05", "description": "JUMBO",
         "amount": "-45000.00", "currency": "CLP", "raw": {}},
        {"line_no": 2, "date": "2026-03-05", "description": "JUMBO",
         "amount": "-45000.00", "currency": "CLP", "raw": {}},
    ]
    fake = _fake_gemini_returning(payload)
    client = _make_app(index_entry=_entry(), gemini_mock=fake, staging_dir=staging_dir)
    p = _pdf_payload()

    batch_id = client.post(
        "/api/v1/cartolas/upload",
        files=p["files"], data=p["data"], cookies=_contador_cookie(),
    ).json()["batch_id"]

    body = client.get(f"/api/v1/cartolas/{batch_id}", cookies=_contador_cookie()).json()
    codes = [w["code"] for w in body["canonical"]["extraction"]["warnings"]]
    assert "DUPLICATE_LINE" in codes
