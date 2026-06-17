"""Lectura/resolución de discrepancias de reconciliación — Story 9.12.

Fuente única: `ledger/_meta/cartola-discrepancies.jsonl` (emitido por 9.6b, sin Supabase).
Parseo lazy line-by-line + filtros in-memory. Una discrepancia está RESUELTA si existe una
línea de resolución (`ref_discrepancy_id`) que la referencia — esas se ocultan del dashboard
(quedan como audit trail, accesibles vía history).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Estados bloqueantes (chip rojo, AC9): valor que no cuadra (no se importa) o FX fuera de tolerancia.
BLOCKING_STATES = {"value-mismatch", "fx-out-of-tolerance"}

# Acciones permitidas por estado (AC4). `escalate` no cierra la discrepancia.
ACTIONS_BY_STATE = {
    "value-mismatch": {"accept-cartola", "accept-laudus", "escalate"},
    "missing-in-laudus": {"confirm-cartola-only", "escalate"},
    "missing-in-cartola": {"confirm-laudus-only", "escalate"},
    "date-mismatch": {"accept-cartola-date", "accept-laudus-date", "escalate"},
    "description-mismatch": {"accept-cartola-description", "accept-laudus-description", "merge", "escalate"},
    "category-mismatch": {"accept-cartola-category", "accept-laudus-category", "manual-category", "escalate"},
    "fx-out-of-tolerance": {"accept-derived-fx", "accept-bcch-fx", "manual-fx", "escalate"},
}


class ResolveError(Exception):
    """Acción inválida o justificación faltante (HTTP 400)."""


def _jsonl_path() -> Path:
    override = os.getenv("LEDGER_DISCREPANCIES")
    if override:
        return Path(override)
    ledger_dir = os.getenv("LEDGER_DIR")
    root = Path(ledger_dir) if ledger_dir else Path(__file__).resolve().parents[5] / "ledger"
    return root / "_meta" / "cartola-discrepancies.jsonl"


def _iter_lines(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _year_month(entry: dict) -> str:
    for side in ("cartola", "laudus"):
        d = (entry.get(side) or {}).get("date")
        if d:
            return str(d)[:7]
    return ""


def _resolved_ids(path: Path) -> set[str]:
    """IDs con resolución que CIERRA la discrepancia. `escalate` no cierra (AC4) → no cuenta."""
    out = set()
    for e in _iter_lines(path):
        res = e.get("resolution")
        if e.get("ref_discrepancy_id") and res is not None and res.get("action") != "escalate":
            out.add(e["ref_discrepancy_id"])
    return out


def _is_original(entry: dict) -> bool:
    return entry.get("discrepancy_id") is not None and "ref_discrepancy_id" not in entry


def read_discrepancies(*, state=None, year_month=None, bank_account_id=None,
                       discrepancy_id=None, path: Path | None = None) -> dict:
    """Discrepancias sin resolver (o una específica por id, incluso resuelta) + summary (AC1)."""
    path = path or _jsonl_path()
    resolved = _resolved_ids(path)
    items, by_state = [], {}
    for e in _iter_lines(path):
        if not _is_original(e):
            continue
        if discrepancy_id is not None:
            if e["discrepancy_id"] == discrepancy_id:
                items.append({**e, "year_month": _year_month(e)})
            continue
        if e["discrepancy_id"] in resolved:
            continue
        if bank_account_id and e.get("bank_account_id") != bank_account_id:
            continue
        if year_month and _year_month(e) != year_month:
            continue
        # El summary cuenta por estado SIN aplicar el filtro `state`, para que los chips de los
        # demás estados sigan visibles al filtrar por uno (si no, la UI los pierde).
        by_state[e.get("state")] = by_state.get(e.get("state"), 0) + 1
        if state and e.get("state") != state:
            continue
        items.append({**e, "year_month": _year_month(e)})
    total = len(items) if discrepancy_id is not None else sum(by_state.values())
    return {"discrepancies": items, "summary": {"total": total, "by_state": by_state}}


def history(discrepancy_id: str, path: Path | None = None) -> list[dict]:
    """Todas las líneas con ese discrepancy_id (original + resoluciones), en orden de archivo (AC2)."""
    path = path or _jsonl_path()
    out = []
    for e in _iter_lines(path):
        if e.get("discrepancy_id") == discrepancy_id or e.get("ref_discrepancy_id") == discrepancy_id:
            out.append(e)
    return out


def pending_count(path: Path | None = None) -> dict:
    """{total, blocking} de las discrepancias sin resolver (AC9 — color del chip)."""
    data = read_discrepancies(path=path)
    total = data["summary"]["total"]
    blocking = sum(n for st, n in data["summary"]["by_state"].items() if st in BLOCKING_STATES)
    return {"total": total, "blocking": blocking}


def resolve(discrepancy_id: str, action: str, justification: str | None,
            *, user_email: str, now_iso: str, path: Path | None = None) -> dict:
    """Valida la acción vs el estado, appendea la resolución al JSONL (AC3/AC4).

    El re-emit del `.beancount` por acción se apoya en el seam de 9.6b (`commit_reconciliation`),
    que se activa con el wiring del upload de cartolas (ver 9.6b Completion Notes). Acá se registra
    la resolución (audit trail) y la discrepancia desaparece del dashboard.
    """
    from pipeline.importers.discrepancy_writer import append_resolution

    path = path or _jsonl_path()
    # encontrar la discrepancia original para conocer su estado
    original = next((e for e in _iter_lines(path)
                     if _is_original(e) and e["discrepancy_id"] == discrepancy_id), None)
    if original is None:
        raise ResolveError(f"discrepancy_id {discrepancy_id} no existe")
    if discrepancy_id in _resolved_ids(path):
        raise ResolveError(f"discrepancy_id {discrepancy_id} ya fue resuelta")
    state = original.get("state")
    # `escalate` no cierra y sirve para cualquier estado (incl. fx-bcch-missing/fx-implausible que
    # 9.6b emite y no están en la tabla) → siempre permitido, evita dead-ends. El resto se valida.
    if action != "escalate" and action not in ACTIONS_BY_STATE.get(state, set()):
        raise ResolveError(f"acción '{action}' no permitida para estado '{state}'")
    if action != "escalate" and (not justification or len(justification.strip()) < 10):
        raise ResolveError("justification ≥ 10 caracteres requerida (excepto escalate)")

    resolution = {"action": action, "resolved_by": user_email, "resolved_at": now_iso,
                  "justification": (justification or "").strip()}
    if action == "escalate":
        resolution["escalated_at"] = now_iso  # no cierra la discrepancia
    append_resolution(discrepancy_id, resolution, path)
    return {"status": "escalated" if action == "escalate" else "resolved",
            "discrepancy_id": discrepancy_id, "action": action}
