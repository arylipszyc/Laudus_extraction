"""Adaptadores thin a las fuentes de datos del bootstrap — Story 9.1.

Encapsulan las llamadas a Laudus API (plan de cuentas) y Supabase (taxonomía
Categoria1/2/3 + metadata bancaria) detrás de funciones simples para que
`generate_accounts.py` pueda orquestar sin saber de auth ni transport.
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from pipeline.services.laudus_service import login

logger = logging.getLogger(__name__)

LAUDUS_ACCOUNTS_LIST_URL = "https://api.laudus.cl/accounting/accounts/list"
LAUDUS_FIELDS = ["accountId", "accountNumber", "name", "notes"]


def fetch_laudus_accounts() -> list[dict[str, Any]]:
    """Trae las 293 cuentas del plan desde Laudus API.

    Endpoint: `POST /accounting/accounts/list` body `{"fields": [...]}`.
    Campos disponibles confirmados: accountId, accountNumber, name, notes.
    Laudus NO expone account_type ni jerarquía explícita — la jerarquía se
    deriva del prefijo numérico del accountNumber (convención chilena).

    Returns:
        Lista de dicts con `accountNumber` (str), `name` (str), `accountId`
        (int), `notes` (str). Sin filtros — todas las cuentas del plan.
    """
    token = login()
    if not token:
        raise RuntimeError("Laudus login devolvió token vacío. Revisar credenciales.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    response = requests.post(
        LAUDUS_ACCOUNTS_LIST_URL,
        headers=headers,
        json={"fields": LAUDUS_FIELDS},
        timeout=30,
    )
    response.raise_for_status()
    accounts = response.json()
    if not isinstance(accounts, list):
        raise RuntimeError(
            f"Laudus accounts/list devolvió tipo inesperado: {type(accounts).__name__}"
        )
    logger.info("Laudus: fetched %d cuentas", len(accounts))
    return accounts


def fetch_supabase_plan() -> list[dict[str, Any]]:
    """Trae el plan de cuentas con taxonomía desde Supabase (one-time read).

    Returns:
        Lista de dicts del plan. Shape esperado incluye `account_number`,
        `account_name`, `categoria1`, `categoria2`, `categoria3`, `active`.
        Hidratado por Story 4.0; será deprecado por 9.11.
    """
    from backend.app.repositories.supabase_repository import SupabaseRepository
    repo = SupabaseRepository()
    plan = repo.list_plan_de_cuentas(active_only=False)
    logger.info("Supabase plan_de_cuentas: fetched %d entries", len(plan))
    return plan


def fetch_supabase_bank_accounts() -> list[dict[str, Any]]:
    """Trae el registry de bank_accounts desde Supabase (one-time read).

    Returns:
        Lista de dicts con `id`, `account_number` (FK a plan), `account_type`,
        `account_currency`, `bank_name`, `account_last4`, `active`, etc.
    """
    from backend.app.repositories.supabase_repository import SupabaseRepository
    repo = SupabaseRepository()
    banks = repo.list_bank_accounts()
    logger.info("Supabase bank_accounts: fetched %d entries", len(banks))
    return banks
