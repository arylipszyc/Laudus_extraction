"""Google Sheets implementation of DataRepository.

Wraps utils.gspread_utils — all gspread logic stays in that module.
NO direct gspread import in this file.
"""
import logging
from typing import Callable

from backend.app.repositories.base import DataRepository
from utils.gspread_utils import replace_sheet, upsert_to_sheet

logger = logging.getLogger(__name__)


class SheetsRepository(DataRepository):
    """DataRepository backed by Google Sheets via gspread_utils."""

    def __init__(self, spreadsheet) -> None:
        """
        Args:
            spreadsheet: A gspread Spreadsheet object (from config.gspread_config.get_spreadsheet()).
        """
        self._spreadsheet = spreadsheet

    @property
    def spreadsheet(self):
        return self._spreadsheet

    def upsert_records(
        self,
        sheet_name: str,
        records: list[dict],
        primary_key_func: Callable[[dict], str],
        headers: list[str],
    ) -> list[dict]:
        """Delegates to gspread_utils.upsert_to_sheet."""
        return upsert_to_sheet(self._spreadsheet, sheet_name, records, primary_key_func, headers)

    def replace_records(
        self,
        sheet_name: str,
        records: list[dict],
        headers: list[str],
    ) -> None:
        """Delegates to gspread_utils.replace_sheet."""
        replace_sheet(self._spreadsheet, sheet_name, records, headers)

    def get_records(self, sheet_name: str) -> list[dict]:
        """Returns all records from the named worksheet."""
        try:
            ws = self._spreadsheet.worksheet(sheet_name)
            return ws.get_all_records()
        except Exception:
            logger.exception("Failed to get records from sheet '%s'", sheet_name)
            return []
