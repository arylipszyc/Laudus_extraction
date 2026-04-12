"""Tests for DataRepository interface and SheetsRepository implementation."""
import pytest
from unittest.mock import MagicMock, patch, call
from backend.app.repositories.base import DataRepository
from backend.app.repositories.sheets_repository import SheetsRepository


# ── DataRepository is abstract ─────────────────────────────────────────────

def test_data_repository_is_abstract():
    """Cannot instantiate DataRepository directly."""
    with pytest.raises(TypeError):
        DataRepository()


def test_data_repository_requires_upsert_records():
    class Incomplete(DataRepository):
        def replace_records(self, sheet_name, records, headers): pass
        def get_records(self, sheet_name): pass

    with pytest.raises(TypeError):
        Incomplete()


def test_data_repository_requires_replace_records():
    class Incomplete(DataRepository):
        def upsert_records(self, sheet_name, records, primary_key_func, headers): pass
        def get_records(self, sheet_name): pass

    with pytest.raises(TypeError):
        Incomplete()


def test_data_repository_requires_get_records():
    class Incomplete(DataRepository):
        def upsert_records(self, sheet_name, records, primary_key_func, headers): pass
        def replace_records(self, sheet_name, records, headers): pass

    with pytest.raises(TypeError):
        Incomplete()


# ── SheetsRepository implements DataRepository ────────────────────────────

def make_repo():
    mock_spreadsheet = MagicMock()
    return SheetsRepository(spreadsheet=mock_spreadsheet), mock_spreadsheet


def test_sheets_repository_is_data_repository():
    repo, _ = make_repo()
    assert isinstance(repo, DataRepository)


def test_sheets_repository_no_gspread_import():
    """SheetsRepository must not import gspread directly."""
    import ast, inspect
    import backend.app.repositories.sheets_repository as module
    source = inspect.getsource(module)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "gspread", "Direct gspread import found in SheetsRepository"
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "gspread", "Direct gspread import found in SheetsRepository"


def test_upsert_records_delegates_to_gspread_utils():
    repo, mock_spreadsheet = make_repo()
    records = [{"account": "1001", "date": "2026-01-01", "amount": 100.0}]
    pk_func = lambda r: f"{r['account']}_{r['date']}"
    headers = ["account", "date", "amount"]

    with patch("backend.app.repositories.sheets_repository.upsert_to_sheet") as mock_upsert:
        mock_upsert.return_value = records
        result = repo.upsert_records("BalanceSheet", records, pk_func, headers)

    mock_upsert.assert_called_once_with(mock_spreadsheet, "BalanceSheet", records, pk_func, headers)
    assert result == records


def test_replace_records_delegates_to_gspread_utils():
    repo, mock_spreadsheet = make_repo()
    records = [{"account": "1001", "amount": 500.0}]
    headers = ["account", "amount"]

    with patch("backend.app.repositories.sheets_repository.replace_sheet") as mock_replace:
        repo.replace_records("LedgerFinal", records, headers)

    mock_replace.assert_called_once_with(mock_spreadsheet, "LedgerFinal", records, headers)


def test_get_records_returns_all_records():
    repo, mock_spreadsheet = make_repo()
    expected = [{"account": "1001", "amount": 100.0}]
    mock_ws = MagicMock()
    mock_ws.get_all_records.return_value = expected
    mock_spreadsheet.worksheet.return_value = mock_ws

    result = repo.get_records("BalanceSheet")

    mock_spreadsheet.worksheet.assert_called_once_with("BalanceSheet")
    mock_ws.get_all_records.assert_called_once()
    assert result == expected


def test_get_records_returns_empty_list_on_missing_sheet():
    repo, mock_spreadsheet = make_repo()
    mock_spreadsheet.worksheet.side_effect = Exception("Worksheet not found")

    result = repo.get_records("NonExistentSheet")

    assert result == []
