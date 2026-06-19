"""Emisión append-only de discrepancias a JSONL — Story 9.6b AC5/AC7.

`ledger/_meta/cartola-discrepancies.jsonl` es la fuente única de las discrepancias de
reconciliación (sin mirror Supabase). Append-only: la resolución (Story 9.12) se appendea
como línea nueva referenciando el `discrepancy_id` original (audit trail completo).

Dedup por `(batch_id, cartola_line_no, laudus_je_id)` → re-correr el matching no duplica
entradas (AC7).
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

SCHEMA_VERSION = "1.0"


def _dedup_key(batch_id, cartola_line_no, laudus_je_id, state) -> tuple:
    return (str(batch_id), cartola_line_no, laudus_je_id, state)


def build_discrepancy(
    *,
    batch_id: str,
    bank_account_id: str,
    state: str,
    ts: str,
    cartola: dict | None,
    laudus: dict | None,
    fx: dict | None = None,
    source: str | None = None,
) -> dict:
    """Construye la entrada de discrepancia con el shape de AC5 (sin escribirla).

    `source` (AC4): "cartola" (missing-in-laudus) / "laudus" (missing-in-cartola) / None.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "discrepancy_id": str(uuid.uuid4()),
        "ts": ts,
        "batch_id": batch_id,
        "bank_account_id": bank_account_id,
        "state": state,
        "source": source,
        "cartola": cartola,
        "laudus": laudus,
        "fx": fx or {"implied": None, "bcch": None, "deviation_pct": None},
        "resolution": None,
    }


def _existing_dedup_keys(path: Path) -> set[tuple]:
    """Claves de dedup de las discrepancias YA escritas (ignora líneas de resolución)."""
    keys: set[tuple] = set()
    if not path.exists():
        return keys
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("resolution") is not None and entry.get("ref_discrepancy_id"):
            continue  # línea de resolución, no es una discrepancia original
        cart = entry.get("cartola") or {}
        laud = entry.get("laudus") or {}
        keys.add(_dedup_key(entry.get("batch_id"), cart.get("line_no"),
                            laud.get("journal_entry_id"), entry.get("state")))
    return keys


def append_discrepancy(discrepancy: dict, jsonl_path: str | Path) -> bool:
    """Appendea una discrepancia si su clave de dedup no existe. Devuelve True si escribió."""
    path = Path(jsonl_path)
    cart = discrepancy.get("cartola") or {}
    laud = discrepancy.get("laudus") or {}
    key = _dedup_key(discrepancy.get("batch_id"), cart.get("line_no"),
                     laud.get("journal_entry_id"), discrepancy.get("state"))
    if key in _existing_dedup_keys(path):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(discrepancy, ensure_ascii=False) + "\n")
    return True


def append_resolution(
    discrepancy_id: str,
    resolution: dict,
    jsonl_path: str | Path,
) -> None:
    """Appendea una línea de resolución que referencia la discrepancia original (AC5).

    `resolution` = {action, resolved_by, resolved_at, justification}. No reescribe nada.
    """
    path = Path(jsonl_path)
    record = {
        "schema_version": SCHEMA_VERSION,
        "ref_discrepancy_id": discrepancy_id,
        "resolution": resolution,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
