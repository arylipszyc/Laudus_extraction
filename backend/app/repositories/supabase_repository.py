"""Supabase implementation of DataRepository.

Wraps the supabase-py client — all Supabase logic stays in this module.
NO direct supabase import anywhere else in the application.
"""
import logging
import os
from typing import Callable

from supabase import create_client, Client

from backend.app.repositories.base import DataRepository

logger = logging.getLogger(__name__)


def _get_supabase_client() -> Client:
    """Initialize Supabase client from environment variables.

    Raises:
        RuntimeError: If SUPABASE_URL or SUPABASE_KEY are not set.
    """
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set in environment variables. "
            "See .env.example for required values."
        )
    return create_client(url, key)


class SupabaseRepository(DataRepository):
    """DataRepository backed by Supabase (managed PostgreSQL).

    Implements the same DataRepository interface as SheetsRepository so it
    can be used as a drop-in addition with zero changes to the API layer.

    Also exposes Supabase-specific helpers used directly by Phase 2 services.
    """

    def __init__(self) -> None:
        self._client: Client = _get_supabase_client()

    # ── DataRepository interface ──────────────────────────────────────────────

    def upsert_records(
        self,
        sheet_name: str,
        records: list[dict],
        primary_key_func: Callable[[dict], str],
        headers: list[str],
    ) -> list[dict]:
        """Upsert records into a Supabase table by primary key."""
        if not records:
            return []
        result = self._client.table(sheet_name).upsert(records).execute()
        return result.data or []

    def replace_records(
        self,
        sheet_name: str,
        records: list[dict],
        headers: list[str],
    ) -> None:
        """Replace all records in a Supabase table (delete-then-insert)."""
        self._client.table(sheet_name).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        if records:
            self._client.table(sheet_name).insert(records).execute()

    def get_records(self, sheet_name: str) -> list[dict]:
        """Return all records from a Supabase table."""
        try:
            result = self._client.table(sheet_name).select("*").execute()
            return result.data or []
        except Exception:
            logger.exception("Failed to get records from table '%s'", sheet_name)
            return []

    # ── Plan de cuentas helpers ───────────────────────────────────────────────

    def upsert_plan_de_cuentas(self, records: list[dict]) -> dict:
        """Upsert chart of accounts entries. Returns counts."""
        if not records:
            return {"synced": 0, "updated": 0}

        existing = {r["account_number"] for r in self.get_records("plan_de_cuentas")}
        new_count = sum(1 for r in records if r["account_number"] not in existing)
        updated_count = len(records) - new_count

        self._client.table("plan_de_cuentas").upsert(
            records, on_conflict="account_number"
        ).execute()

        return {"synced": new_count, "updated": updated_count}

    def list_plan_de_cuentas(self, active_only: bool = True) -> list[dict]:
        """List chart of accounts ordered by account_number."""
        query = self._client.table("plan_de_cuentas").select("*").order("account_number")
        if active_only:
            query = query.eq("active", True)
        return query.execute().data or []

    # ── Bank accounts helpers ─────────────────────────────────────────────────

    def list_bank_accounts(self) -> list[dict]:
        """List all bank accounts with linked account name from plan_de_cuentas."""
        result = (
            self._client.table("bank_accounts")
            .select("*, plan_de_cuentas(account_name)")
            .order("account_number")
            .execute()
        )
        return result.data or []

    def get_bank_account_by_id(self, account_id: str) -> dict | None:
        """Get a single bank account by UUID."""
        result = (
            self._client.table("bank_accounts")
            .select("*, plan_de_cuentas(account_name)")
            .eq("id", account_id)
            .maybe_single()
            .execute()
        )
        return result.data

    def plan_de_cuentas_exists(self, account_number: str) -> bool:
        """Check if an account_number exists in plan_de_cuentas."""
        result = (
            self._client.table("plan_de_cuentas")
            .select("account_number")
            .eq("account_number", account_number)
            .maybe_single()
            .execute()
        )
        return result.data is not None

    def create_bank_account(self, data: dict) -> dict:
        """Insert a new bank account row. Returns the created record."""
        result = self._client.table("bank_accounts").insert(data).execute()
        return result.data[0] if result.data else {}

    def update_bank_account(self, account_id: str, data: dict) -> dict | None:
        """Update a bank account by UUID. Returns updated record or None."""
        result = (
            self._client.table("bank_accounts")
            .update(data)
            .eq("id", account_id)
            .execute()
        )
        return result.data[0] if result.data else None

    # ── Cartola helpers (used by Stories 4.1+) ───────────────────────────────

    def get_active_bank_accounts_for_account_number(self, account_number: str) -> list[dict]:
        """Get active bank_accounts entries linked to a plan_de_cuentas account_number."""
        result = (
            self._client.table("bank_accounts")
            .select("*")
            .eq("account_number", account_number)
            .eq("active", True)
            .execute()
        )
        return result.data or []
