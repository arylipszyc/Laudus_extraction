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
