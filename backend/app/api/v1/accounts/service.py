"""Listado del plan de cuentas desde el ledger Beancount — Story 6.4.

Devuelve las cuentas `open` que matchean un root (ej. `Expenses`), para poblar el
autocompletado de categoría del dashboard de reconciliación. Beancount es la fuente única.
"""
from __future__ import annotations

from beancount.core.data import Open


def list_accounts(entries: list, root: str) -> list[str]:
    """Cuentas abiertas cuyo nombre empieza con `root` (ej. `Expenses`), ordenadas y únicas.

    Excluye las cuentas de cuarentena (`*:PendingReview:*`) — no son destinos válidos de gasto.
    """
    out = {
        e.account
        for e in entries
        if isinstance(e, Open)
        and e.account.startswith(root)
        and ":PendingReview:" not in e.account
    }
    return sorted(out)
