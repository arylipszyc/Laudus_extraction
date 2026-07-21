"""FastAPI dependencies — injectable for testing."""
import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def get_ledger_service():
    """Returns the singleton LedgerService (Story 9.2 AC1).

    Path from `LEDGER_PATH` env var, default `<repo>/ledger/main.beancount`.
    Lazy — the ledger file is not read until a beancount-engine endpoint queries it.
    """
    from backend.app.services.ledger_service import LedgerService
    default_path = Path(__file__).resolve().parents[2] / "ledger" / "main.beancount"
    return LedgerService(os.getenv("LEDGER_PATH") or str(default_path))
