"""Dashboard query logic — servido desde el ledger Beancount (BQL).

Story 9.16 (cleanup c4): el path Sheets fue removido. El ledger Beancount es la
fuente única; la indisponibilidad del ledger la maneja `LedgerService` (503).
"""
import logging

logger = logging.getLogger(__name__)


def get_balance_sheets(
    entity: str,
    date_from: str | None = None,
    date_to: str | None = None,
    ledger=None,
) -> dict:
    """Return balance sheet records for entity, optionally filtered by date range."""
    from backend.app.services.bql_queries import balance_sheet_via_beancount
    return balance_sheet_via_beancount(ledger, entity, date_from, date_to)


def get_ledger_entries(
    entity: str,
    date_from: str | None = None,
    date_to: str | None = None,
    account_number: str | None = None,
    ledger=None,
) -> dict:
    """Return ledger entries for entity, optionally filtered by date range and/or account."""
    from backend.app.services.bql_queries import ledger_entries_via_beancount
    return ledger_entries_via_beancount(ledger, entity, date_from, date_to, account_number)
