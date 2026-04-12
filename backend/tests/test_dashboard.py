"""Tests for dashboard API endpoints — Story 3.1."""
import pytest
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.auth.service import create_jwt
from backend.app.dependencies import get_repository
from backend.app.middleware import add_middleware


# ── Sample data ───────────────────────────────────────────────────────────────

SAMPLE_BALANCE_RECORD = {
    "account_id": 273,
    "account_number": "111005",
    "account_name": "Caja Pesos",
    "debit": 100000.0,
    "credit": 0.0,
    "debit_balance": 100000.0,
    "credit_balance": 0.0,
    "query_date": "2026-03-31",
    "is_latest": "TRUE",
}

SAMPLE_BALANCE_RECORD_OLD = {
    "account_id": 274,
    "account_number": "111006",
    "account_name": "Caja Dólares",
    "debit": 5000.0,
    "credit": 0.0,
    "debit_balance": 5000.0,
    "credit_balance": 0.0,
    "query_date": "2025-12-31",
    "is_latest": "FALSE",
}

SAMPLE_LEDGER_RECORD = {
    "journalentryid": 12345,
    "journalentrynumber": 1001,
    "date": "2026-03-15",
    "accountnumber": "111005",
    "lineid": 1,
    "description": "Pago proveedor",
    "debit": 50000.0,
    "credit": 0.0,
    "currencycode": "CLP",
    "paritytomaincurrency": 1.0,
    "periodo": "2026-03-31",
}

SAMPLE_LEDGER_RECORD_OLD = {
    "journalentryid": 12344,
    "journalentrynumber": 1000,
    "date": "2025-11-20",
    "accountnumber": "211001",
    "lineid": 2,
    "description": "Ingreso arriendo",
    "debit": 0.0,
    "credit": 200000.0,
    "currencycode": "CLP",
    "paritytomaincurrency": 1.0,
    "periodo": "2025-11-30",
}


# ── Test app factory ──────────────────────────────────────────────────────────


def make_dashboard_test_app(mock_repo=None) -> TestClient:
    """Mini FastAPI app with dashboard router and mocked repository."""
    from backend.app.api.v1.dashboard.router import router as dashboard_router

    app = FastAPI()
    add_middleware(app)
    app.include_router(dashboard_router, prefix="/api/v1")

    if mock_repo is not None:
        app.dependency_overrides[get_repository] = lambda: mock_repo

    return TestClient(app, raise_server_exceptions=False)


def make_mock_repo(entity: str = "EAG", balance_records=None, ledger_records=None):
    """Return a MagicMock repository routing get_records by entity-specific sheet names."""
    repo = MagicMock()
    _bs = balance_records if balance_records is not None else []
    _ledger = ledger_records if ledger_records is not None else []

    def _get_records(sheet_name):
        if sheet_name == f"balance_sheet_{entity.lower()}":
            return _bs
        if sheet_name == f"ledger_{entity.lower()}":
            return _ledger
        return []

    repo.get_records.side_effect = _get_records
    return repo


def owner_token():
    return create_jwt(email="owner@test.com", role="owner")


def contador_token():
    return create_jwt(email="contador@test.com", role="contador")


# ── GET /api/v1/balance-sheets ────────────────────────────────────────────────


def test_balance_sheets_unauthenticated():
    """AC4: no auth cookie → 401."""
    client = make_dashboard_test_app(mock_repo=make_mock_repo())
    response = client.get("/api/v1/balance-sheets", params={"entity": "EAG"})
    assert response.status_code == 401


def test_balance_sheets_owner_can_read():
    """AC4: owner role → 200 (read access for both roles)."""
    client = make_dashboard_test_app(mock_repo=make_mock_repo(balance_records=[SAMPLE_BALANCE_RECORD]))
    response = client.get(
        "/api/v1/balance-sheets",
        params={"entity": "EAG"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 200


def test_balance_sheets_contador_can_read():
    """AC4: contador role → 200."""
    client = make_dashboard_test_app(mock_repo=make_mock_repo(balance_records=[SAMPLE_BALANCE_RECORD]))
    response = client.get(
        "/api/v1/balance-sheets",
        params={"entity": "EAG"},
        cookies={"access_token": contador_token()},
    )
    assert response.status_code == 200


def test_balance_sheets_returns_data_and_meta():
    """AC2: response has data list and meta.last_sync."""
    client = make_dashboard_test_app(mock_repo=make_mock_repo(balance_records=[SAMPLE_BALANCE_RECORD]))
    response = client.get(
        "/api/v1/balance-sheets",
        params={"entity": "EAG"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "meta" in body
    assert "last_sync" in body["meta"]
    assert len(body["data"]) == 1
    assert body["meta"]["last_sync"] == "2026-03-31"


def test_balance_sheets_filters_by_date_range():
    """AC2: records outside date_from/date_to are excluded."""
    records = [SAMPLE_BALANCE_RECORD, SAMPLE_BALANCE_RECORD_OLD]
    client = make_dashboard_test_app(mock_repo=make_mock_repo(balance_records=records))
    response = client.get(
        "/api/v1/balance-sheets",
        params={"entity": "EAG", "date_from": "2026-01-01", "date_to": "2026-12-31"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["query_date"] == "2026-03-31"


def test_balance_sheets_no_date_filter_returns_all():
    """AC8: no date params → all records returned."""
    records = [SAMPLE_BALANCE_RECORD, SAMPLE_BALANCE_RECORD_OLD]
    client = make_dashboard_test_app(mock_repo=make_mock_repo(balance_records=records))
    response = client.get(
        "/api/v1/balance-sheets",
        params={"entity": "EAG"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 2


def test_balance_sheets_invalid_entity_returns_422():
    """AC5: invalid entity → 422."""
    client = make_dashboard_test_app(mock_repo=make_mock_repo())
    response = client.get(
        "/api/v1/balance-sheets",
        params={"entity": "INVALID"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("entity", ["EAG", "Jocelyn", "Jeannette", "Johanna", "Jael"])
def test_balance_sheets_valid_entities_accepted(entity):
    """AC5: all 5 valid entities are accepted → 200."""
    client = make_dashboard_test_app(mock_repo=make_mock_repo(entity=entity))
    response = client.get(
        "/api/v1/balance-sheets",
        params={"entity": entity},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 200


def test_balance_sheets_empty_entity_returns_empty_list():
    """AC9: entity tab doesn't exist → data=[], meta.last_sync=null (not 500)."""
    # make_mock_repo with no records and entity mismatch → get_records returns []
    repo = MagicMock()
    repo.get_records.return_value = []
    client = make_dashboard_test_app(mock_repo=repo)
    response = client.get(
        "/api/v1/balance-sheets",
        params={"entity": "EAG"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["last_sync"] is None


def test_balance_sheets_amounts_are_float():
    """AC6: monetary fields are float (Pydantic coerces int → float)."""
    # Simulate Sheets returning ints for numeric cells
    record_with_ints = {**SAMPLE_BALANCE_RECORD, "debit": 100000, "credit": 0, "debit_balance": 100000, "credit_balance": 0}
    client = make_dashboard_test_app(mock_repo=make_mock_repo(balance_records=[record_with_ints]))
    response = client.get(
        "/api/v1/balance-sheets",
        params={"entity": "EAG"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 200
    record = response.json()["data"][0]
    assert isinstance(record["debit"], float)
    assert isinstance(record["credit"], float)
    assert isinstance(record["debit_balance"], float)
    assert isinstance(record["credit_balance"], float)


def test_balance_sheets_only_date_from_applied():
    """AC8: only date_from → records on or after date_from returned."""
    records = [SAMPLE_BALANCE_RECORD, SAMPLE_BALANCE_RECORD_OLD]
    client = make_dashboard_test_app(mock_repo=make_mock_repo(balance_records=records))
    response = client.get(
        "/api/v1/balance-sheets",
        params={"entity": "EAG", "date_from": "2026-01-01"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["query_date"] == "2026-03-31"


# ── GET /api/v1/ledger-entries ────────────────────────────────────────────────


def test_ledger_entries_unauthenticated():
    """AC4: no auth cookie → 401."""
    client = make_dashboard_test_app(mock_repo=make_mock_repo())
    response = client.get("/api/v1/ledger-entries", params={"entity": "EAG"})
    assert response.status_code == 401


def test_ledger_entries_returns_data_and_meta():
    """AC3: response has data list and meta.last_sync."""
    client = make_dashboard_test_app(mock_repo=make_mock_repo(ledger_records=[SAMPLE_LEDGER_RECORD]))
    response = client.get(
        "/api/v1/ledger-entries",
        params={"entity": "EAG"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "meta" in body
    assert "last_sync" in body["meta"]
    assert len(body["data"]) == 1
    assert body["meta"]["last_sync"] == "2026-03-15"


def test_ledger_entries_filters_by_date_range():
    """AC3: date range filter works on ledger date field."""
    records = [SAMPLE_LEDGER_RECORD, SAMPLE_LEDGER_RECORD_OLD]
    client = make_dashboard_test_app(mock_repo=make_mock_repo(ledger_records=records))
    response = client.get(
        "/api/v1/ledger-entries",
        params={"entity": "EAG", "date_from": "2026-01-01", "date_to": "2026-12-31"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["date"] == "2026-03-15"


def test_ledger_entries_account_number_filter():
    """AC7: account_number param filters ledger entries by accountnumber."""
    records = [SAMPLE_LEDGER_RECORD, SAMPLE_LEDGER_RECORD_OLD]
    client = make_dashboard_test_app(mock_repo=make_mock_repo(ledger_records=records))
    response = client.get(
        "/api/v1/ledger-entries",
        params={"entity": "EAG", "account_number": "111005"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 1
    # Patch 2: field renamed to snake_case (AC6)
    assert body["data"][0]["account_number"] == "111005"


def test_ledger_entries_amounts_are_float():
    """AC6: monetary fields in ledger are float."""
    record_with_ints = {**SAMPLE_LEDGER_RECORD, "debit": 50000, "credit": 0, "paritytomaincurrency": 1}
    client = make_dashboard_test_app(mock_repo=make_mock_repo(ledger_records=[record_with_ints]))
    response = client.get(
        "/api/v1/ledger-entries",
        params={"entity": "EAG"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 200
    record = response.json()["data"][0]
    assert isinstance(record["debit"], float)
    assert isinstance(record["credit"], float)
    # Patch 2: field renamed to snake_case (AC6)
    assert isinstance(record["parity_to_main_currency"], float)


def test_ledger_entries_invalid_entity_returns_422():
    """AC5: invalid entity on ledger endpoint → 422."""
    client = make_dashboard_test_app(mock_repo=make_mock_repo())
    response = client.get(
        "/api/v1/ledger-entries",
        params={"entity": "UNKNOWN"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 422


def test_ledger_entries_no_date_filter_returns_all():
    """AC8: no date params on ledger → all records."""
    records = [SAMPLE_LEDGER_RECORD, SAMPLE_LEDGER_RECORD_OLD]
    client = make_dashboard_test_app(mock_repo=make_mock_repo(ledger_records=records))
    response = client.get(
        "/api/v1/ledger-entries",
        params={"entity": "EAG"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 2


def test_ledger_entries_empty_returns_null_last_sync():
    """AC9: no ledger data → data=[], meta.last_sync=null."""
    repo = MagicMock()
    repo.get_records.return_value = []
    client = make_dashboard_test_app(mock_repo=repo)
    response = client.get(
        "/api/v1/ledger-entries",
        params={"entity": "EAG"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["last_sync"] is None


# ── Service unit tests ────────────────────────────────────────────────────────


def test_service_in_date_range_inclusive():
    """_in_date_range: both bounds are inclusive."""
    from backend.app.api.v1.dashboard.service import _in_date_range
    assert _in_date_range("2026-01-01", "2026-01-01", "2026-12-31") is True
    assert _in_date_range("2026-12-31", "2026-01-01", "2026-12-31") is True
    assert _in_date_range("2025-12-31", "2026-01-01", "2026-12-31") is False
    assert _in_date_range("2027-01-01", "2026-01-01", "2026-12-31") is False


def test_service_in_date_range_empty_date_excluded():
    """_in_date_range: empty or None record_date → False."""
    from backend.app.api.v1.dashboard.service import _in_date_range
    assert _in_date_range("", "2026-01-01", "2026-12-31") is False
    assert _in_date_range("None", "2026-01-01", "2026-12-31") is False


def test_service_max_date_returns_max():
    """_max_date: returns the lexicographic max ISO date string."""
    from backend.app.api.v1.dashboard.service import _max_date
    records = [{"query_date": "2026-03-31"}, {"query_date": "2025-12-31"}, {"query_date": "2026-01-01"}]
    assert _max_date(records, "query_date") == "2026-03-31"


def test_service_max_date_empty_returns_none():
    """_max_date: empty records → None."""
    from backend.app.api.v1.dashboard.service import _max_date
    assert _max_date([], "query_date") is None


# ── Patch 5: contador role on /ledger-entries (AC4) ──────────────────────────


def test_ledger_entries_contador_can_read():
    """AC4: contador role → 200 on /ledger-entries."""
    client = make_dashboard_test_app(mock_repo=make_mock_repo(ledger_records=[SAMPLE_LEDGER_RECORD]))
    response = client.get(
        "/api/v1/ledger-entries",
        params={"entity": "EAG"},
        cookies={"access_token": contador_token()},
    )
    assert response.status_code == 200


# ── Patch 6: parametrized entity test for /ledger-entries (AC5 + AC10) ───────


@pytest.mark.parametrize("entity", ["EAG", "Jocelyn", "Jeannette", "Johanna", "Jael"])
def test_ledger_entries_valid_entities_accepted(entity):
    """AC5: all 5 valid entities accepted on /ledger-entries → 200."""
    client = make_dashboard_test_app(mock_repo=make_mock_repo(entity=entity))
    response = client.get(
        "/api/v1/ledger-entries",
        params={"entity": entity},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 200


# ── Patch 3: ISO date format validation ──────────────────────────────────────


def test_balance_sheets_malformed_date_returns_422():
    """Patch 3: non-ISO date_from → 422."""
    client = make_dashboard_test_app(mock_repo=make_mock_repo())
    response = client.get(
        "/api/v1/balance-sheets",
        params={"entity": "EAG", "date_from": "not-a-date"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 422


def test_balance_sheets_inverted_range_returns_422():
    """Patch 3: date_from > date_to → 422."""
    client = make_dashboard_test_app(mock_repo=make_mock_repo())
    response = client.get(
        "/api/v1/balance-sheets",
        params={"entity": "EAG", "date_from": "2026-12-31", "date_to": "2026-01-01"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 422


def test_ledger_entries_malformed_date_returns_422():
    """Patch 3: non-ISO date_to on ledger → 422."""
    client = make_dashboard_test_app(mock_repo=make_mock_repo())
    response = client.get(
        "/api/v1/ledger-entries",
        params={"entity": "EAG", "date_to": "31-03-2026"},
        cookies={"access_token": owner_token()},
    )
    assert response.status_code == 422
