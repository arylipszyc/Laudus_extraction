"""Lógica de cuentas pendientes — listado + motor de sugerencia por prefijo (Story 10.3).

Lee del ledger Beancount cargado (`LedgerService.entries()`): cuentas en cuarentena
(`Assets:EAG:PendingReview:Cuenta-{code}`, escritas por el importer 9.4) y el plan ya
existente (`accounts.beancount`) para sugerir Cat1/Cat2 desde las cuentas hermanas que
comparten el prefijo numérico. NO lee Supabase ni Sheets.
"""
from __future__ import annotations

from beancount.core.data import Open, Transaction

from backend.app.api.v1.cuentas_pendientes.schemas import PendingAccount, Suggestion
from backend.app.services.beancount_promote import camel_leaf

_PENDING_PREFIX = "Assets:EAG:PendingReview:Cuenta-"


def _numeric_prefix(code: str) -> str:
    """Prefijo numérico (3 dígitos) del code — la unidad que mapea 1:1 a Cat1/Cat2."""
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    return digits[:3]


def _is_pending_open(entry) -> bool:
    return (
        isinstance(entry, Open)
        and (entry.account.startswith(_PENDING_PREFIX)
             or str((entry.meta or {}).get("pending_review", "")).upper() == "TRUE")
    )


def _real_opens(entries: list) -> list[tuple[str, dict]]:
    """Opens del plan ya existente (con `code`, no de cuarentena) → (account, meta)."""
    out = []
    for e in entries:
        if isinstance(e, Open) and not _is_pending_open(e):
            meta = e.meta or {}
            if meta.get("code") is not None:
                out.append((e.account, meta))
    return out


def suggest_for_code(code: str, real_opens: list[tuple[str, dict]], laudus_account_name: str) -> Suggestion:
    """Sugiere Cat1/Cat2 + cuenta Beancount desde las hermanas que comparten el prefijo.

    Cat3 NUNCA se sugiere (AC2). Sin hermanas con ese prefijo → todo vacío (el humano fija).
    """
    prefix = _numeric_prefix(code)
    if not prefix:
        return Suggestion()
    siblings = [
        (acc, m) for acc, m in real_opens
        if _numeric_prefix(str(m.get("code", ""))) == prefix
    ]
    if not siblings:
        return Suggestion()
    # Determinista: la hermana de menor code.
    siblings.sort(key=lambda x: str(x[1].get("code", "")))
    acc, m = siblings[0]
    root_entity = ":".join(acc.split(":")[:2])  # ej. "Expenses:EAG"
    leaf = camel_leaf(laudus_account_name)
    return Suggestion(
        categoria1=str(m.get("laudus_categoria1", "")),
        categoria2=str(m.get("laudus_categoria2", "")),
        account=f"{root_entity}:{leaf}-{code}",
    )


def list_pending(entries: list) -> list[PendingAccount]:
    """Lista las cuentas en cuarentena con monto acumulado + sugerencia (AC1/AC2)."""
    real_opens = _real_opens(entries)

    # Monto acumulado por cuenta de cuarentena: suma de magnitudes de las postings de las
    # JEs #pending-account que la referencian (para que el contador priorice).
    montos: dict[str, float] = {}
    for e in entries:
        if not isinstance(e, Transaction):
            continue
        if "pending-account" not in (e.tags or frozenset()):
            continue
        for p in e.postings:
            if p.account.startswith(_PENDING_PREFIX) and p.units is not None and p.units.number is not None:
                montos[p.account] = montos.get(p.account, 0.0) + abs(float(p.units.number))

    out: list[PendingAccount] = []
    for e in entries:
        if not _is_pending_open(e):
            continue
        meta = e.meta or {}
        code = str(meta.get("code", "")) or e.account.removeprefix(_PENDING_PREFIX)
        laudus_name = meta.get("laudus_account_name")
        laudus_name = str(laudus_name) if laudus_name is not None else None
        out.append(PendingAccount(
            code=code,
            pending_account=e.account,
            monto_acumulado=round(montos.get(e.account, 0.0), 2),
            laudus_account_name=laudus_name,
            suggestion=suggest_for_code(code, real_opens, laudus_name or ""),
        ))
    out.sort(key=lambda pa: pa.code)
    return out
