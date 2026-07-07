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
    year_month: str | None = None,
) -> dict:
    """Construye la entrada de discrepancia con el shape de AC5 (sin escribirla).

    `source` (AC4): "cartola" (missing-in-laudus) / "laudus" (missing-in-cartola) / None.
    `year_month` (Story 6.5b): período del ESTADO DE CUENTA (`model.period.end`, `YYYY-MM`),
    distinto de la fecha de la transacción. El servicio agrupa/filtra por él (fallback a la fecha
    para discrepancias viejas sin el campo).
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "discrepancy_id": str(uuid.uuid4()),
        "ts": ts,
        "batch_id": batch_id,
        "bank_account_id": bank_account_id,
        "year_month": year_month,
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


def _key_of(discrepancy: dict) -> tuple:
    cart = discrepancy.get("cartola") or {}
    laud = discrepancy.get("laudus") or {}
    return _dedup_key(discrepancy.get("batch_id"), cart.get("line_no"),
                      laud.get("journal_entry_id"), discrepancy.get("state"))


def append_discrepancy(discrepancy: dict, jsonl_path: str | Path) -> bool:
    """Appendea una discrepancia si su clave de dedup no existe. Devuelve True si escribió."""
    path = Path(jsonl_path)
    if _key_of(discrepancy) in _existing_dedup_keys(path):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(discrepancy, ensure_ascii=False) + "\n")
    return True


def append_discrepancies(discrepancies: list[dict], jsonl_path: str | Path) -> int:
    """Appendea un batch con UNA lectura del JSONL (review 2026-07-06 D5).

    Equivale al loop de `append_discrepancy` (dedup vs disco E intra-batch — el loop
    re-leía el archivo incluyendo lo recién escrito) pero sin releer/re-parsear el
    archivo completo por cada discrepancia. Asume el contrato de escritores del repo:
    quien escribe discrepancias lo hace bajo `.import.lock` (hoy solo reconcile_cartola),
    así el snapshot de claves no puede quedar stale a mitad del batch. Devuelve cuántas
    escribió."""
    if not discrepancies:
        return 0
    path = Path(jsonl_path)
    seen = _existing_dedup_keys(path)
    lines: list[str] = []
    for d in discrepancies:
        key = _key_of(d)
        if key in seen:
            continue
        seen.add(key)
        lines.append(json.dumps(d, ensure_ascii=False))
    if lines:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for line in lines:  # línea por línea: misma granularidad ante crash que el loop previo
                fh.write(line + "\n")
    return len(lines)


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


def build_run(*, bank_account_id: str, year_month: str, reconciled_at: str,
              matched: int, differences: int, blocking: int, batch_id: str) -> dict:
    """Run-record de una reconciliación (Story 6.5 AC1) — registra que el período corrió.

    Distingue 'cartola perfecta (0 diferencias)' y 'todas resueltas' de 'nunca subida' (las tres
    se ven idénticas en el JSONL de discrepancias). El lector (`list_periods`) toma el último por
    (cuenta, mes); por eso no hay dedup ni id."""
    return {
        "schema_version": SCHEMA_VERSION,
        "bank_account_id": bank_account_id,
        "year_month": year_month,
        "reconciled_at": reconciled_at,
        "matched": matched,
        "differences": differences,
        "blocking": blocking,
        "batch_id": batch_id,
    }


def append_run(run: dict, jsonl_path: str | Path) -> None:
    """Appendea un run-record (Story 6.5 AC1). Append-only, sin dedup: cada reconciliación deja su
    run y el lector toma el más reciente por (cuenta, mes) — AC4."""
    path = Path(jsonl_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(run, ensure_ascii=False) + "\n")
