"""Abstract DataRepository interface.

All data access in the application goes through this interface.
Phase 1 implementation: SheetsRepository (Google Sheets).
Phase 2 implementation: PostgresRepository (drop-in replacement).
"""
from abc import ABC, abstractmethod
from typing import Callable


class DataRepository(ABC):
    """Storage-agnostic data access interface."""

    @abstractmethod
    def upsert_records(
        self,
        sheet_name: str,
        records: list[dict],
        primary_key_func: Callable[[dict], str],
        headers: list[str],
    ) -> list[dict]:
        """Insert or update records using primary_key_func for deduplication.

        Returns the merged list of records (existing + new).
        """
        ...

    @abstractmethod
    def replace_records(
        self,
        sheet_name: str,
        records: list[dict],
        headers: list[str],
    ) -> None:
        """Replace all records in sheet_name with the provided records."""
        ...

    @abstractmethod
    def get_records(self, sheet_name: str) -> list[dict]:
        """Return all records from sheet_name as a list of dicts."""
        ...
