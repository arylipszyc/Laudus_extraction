"""Corrección de categorías sobre el ledger Beancount — Story 9.7 AC7/AC8/AC9/AC10(tx_id).

Localiza una transacción por `tx_id` estable, le cambia la cuenta de categoría + flag (`!`→`*`)
+ `category_status`, re-genera el archivo de cartola (write-and-replace, determinista como el
importer), corre bean-check, appendea la corrección a `categorization-history.jsonl` (alimenta
la regla supra de 9.7) y commitea. El cache del CategorizationService se invalida.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from beancount.core import data
from beancount.parser import parser

from pipeline.importers.categorization.history import build_record, append_correction

logger = logging.getLogger(__name__)


class TxNotFound(Exception):
    """No hay transacción con ese tx_id (HTTP 404)."""


class CategoryEditError(Exception):
    """bean-check falló tras el edit → rollback (HTTP 422)."""


from backend.app.services.ledger_service import compute_tx_id, tx_id_of as _tx_id_of


def list_pending(entries: list) -> list[dict]:
    """Transacciones con category_status ∈ (suggested, pending), agrupables por cuenta/período (AC9)."""
    out = []
    for e in entries:
        if not isinstance(e, data.Transaction):
            continue
        meta = e.meta or {}
        if meta.get("category_status") not in ("suggested", "pending"):
            continue
        cat = next((p.account for p in e.postings
                    if p.account.split(":")[0] in ("Expenses", "Income")), None)
        amt = e.postings[0].units.number if e.postings and e.postings[0].units else None
        # `confidence` es meta Beancount (editable a mano): un valor no numérico no debe 500ear
        # el endpoint entero — cae a None, como el try/except de `color_for`.
        try:
            conf = float(meta["confidence"]) if meta.get("confidence") is not None else None
        except (TypeError, ValueError):
            conf = None
        out.append({
            "tx_id": _tx_id_of(e),
            "bank_account_id": meta.get("bank_account_id"),
            "date": e.date.isoformat(),
            "narration": e.narration,
            "amount": float(amt) if amt is not None else None,
            "current_category": cat,
            "current_flag": e.flag,
            "current_match_source": meta.get("match_source"),
            "current_category_status": meta.get("category_status"),
            # Goal B (§10.2): color advisory + confianza, para que el contador vea de un vistazo
            # qué revisar (los rojos arriba). El TC builder los estampa en la meta del asiento (a).
            "current_color": meta.get("color"),
            "current_confidence": conf,
        })
    out.sort(key=lambda r: (r["bank_account_id"] or "", r["date"]))
    return out


def _rewrite_file(file_path: Path, tx_ids: set[str], new_category: str | None) -> dict[str, str]:
    """Re-genera el archivo: por cada tx en `tx_ids`, flag→*, status confirmed y (si new_category)
    cambia el posting de categoría. Devuelve {tx_id: narration} de las afectadas."""
    from pipeline.importers.cartola_pdf_importer import render_entries

    entries, _err, _opt = parser.parse_file(str(file_path))
    affected: dict[str, str] = {}
    out_entries = []
    for e in entries:
        if isinstance(e, data.Transaction) and _tx_id_of(e) in tx_ids:
            postings = e.postings
            if new_category is not None:
                # Recategorizar SOLO la pata de resultado (Expenses/Income). Las patas de plata
                # (Assets/Liabilities/Equity) se preservan SIEMPRE: en una TC la deuda es
                # `Liabilities:TC:Real` (no resuelve del bank_account_id), y reescribirla la
                # destruía dejando el asiento con las 2 patas iguales → deuda borrada.
                postings = [
                    p._replace(account=new_category)
                    if p.account.split(":")[0] in ("Expenses", "Income") else p
                    for p in postings
                ]
            meta = dict(e.meta or {})
            meta["category_status"] = "confirmed"
            affected[_tx_id_of(e)] = e.narration or ""
            e = e._replace(flag="*", postings=postings, meta=meta)
        out_entries.append(e)
    file_path.write_text(render_entries(out_entries), encoding="utf-8")
    return affected


def _find(entries: list, tx_id: str) -> data.Transaction | None:
    for e in entries:
        if isinstance(e, data.Transaction) and _tx_id_of(e) == tx_id:
            return e
    return None


def _commit(ledger_root: Path, file_path: Path, message: str, *, extra_paths: list[str] | None = None):
    from pipeline.importers.laudus_run import git_commit_push
    rels = [f"ledger/imports/cartolas/{file_path.name}", *(extra_paths or [])]
    return git_commit_push(ledger_root, rels, message)


def update_category(
    tx_id: str,
    new_category: str,
    *,
    entries: list,
    ledger_root: Path,
    user_email: str,
    history_path: Path | None = None,
    service=None,
    now_iso: str | None = None,
) -> dict:
    """AC7: corrige la categoría de una tx. lock + edit + bean-check (rollback) + history + git."""
    from pipeline.importers.laudus_run import acquire_lock, bean_check

    target = _find(entries, tx_id)
    if target is None:
        raise TxNotFound(tx_id)

    file_path = Path(target.meta["filename"])
    original_cat = next((p.account for p in target.postings
                         if p.account.split(":")[0] in ("Expenses", "Income")), None)
    main_path = ledger_root / "main.beancount"
    lock_path = ledger_root / ".import.lock"

    with acquire_lock(lock_path):
        original = file_path.read_text(encoding="utf-8")
        affected = _rewrite_file(file_path, {tx_id}, new_category)
        ok, detail = bean_check(main_path)
        if not ok:
            file_path.write_text(original, encoding="utf-8")
            raise CategoryEditError(detail)
        # history (alimenta la regla supra) — debe entrar en el MISMO commit, si no el
        # `git reset --hard` del refresh del backend la descarta y la supra nunca acumula.
        hp = history_path or (ledger_root / "_meta" / "categorization-history.jsonl")
        append_correction(hp, build_record(
            description=affected.get(tx_id, ""), corrected_category=new_category,
            original_suggestion=original_cat, user=user_email, ts=now_iso))
        sha = _commit(ledger_root, file_path, f"[categorize] {tx_id} → {new_category}",
                      extra_paths=["ledger/_meta/categorization-history.jsonl"])

    if service is not None:
        service.invalidate(affected.get(tx_id, ""))
    return {"tx_id": tx_id, "category_account": new_category, "flag": "*", "git_sha": sha}


def bulk_confirm(
    batch_id: str | None,
    *,
    entries: list,
    ledger_root: Path,
    user_email: str,
    now_iso: str | None = None,
) -> dict:
    """AC8: confirma las tx con flag `!` y match_source != pending (las pending NO).

    Si `batch_id` viene seteado, se restringe a las tx de ESE batch (meta `batch_id`, estampada
    por el importer); si viene vacío/None, confirma todas las sugeridas del ledger. Agrupa por
    archivo y re-genera cada uno una sola vez. No cambia la categoría: flag `!`→`*`, status
    confirmed. Un solo commit.
    """
    from pipeline.importers.laudus_run import acquire_lock, bean_check, git_commit_push

    by_file: dict[Path, set[str]] = {}
    for e in entries:
        if not isinstance(e, data.Transaction) or e.flag != "!":
            continue
        meta = e.meta or {}
        if meta.get("match_source") in (None, "pending"):
            continue
        if batch_id and meta.get("batch_id") != batch_id:
            continue
        by_file.setdefault(Path(meta["filename"]), set()).add(_tx_id_of(e))

    if not by_file:
        return {"confirmed": 0, "git_sha": None}

    main_path = ledger_root / "main.beancount"
    lock_path = ledger_root / ".import.lock"
    confirmed = 0
    with acquire_lock(lock_path):
        snapshots = {fp: fp.read_text(encoding="utf-8") for fp in by_file}
        rels = []
        for fp, ids in by_file.items():
            affected = _rewrite_file(fp, ids, None)  # solo confirma, no cambia cuenta
            confirmed += len(affected)
            rels.append(f"ledger/imports/cartolas/{fp.name}")
        ok, detail = bean_check(main_path)
        if not ok:
            for fp, content in snapshots.items():
                fp.write_text(content, encoding="utf-8")
            raise CategoryEditError(detail)
        sha = git_commit_push(ledger_root, rels, f"[categorize] bulk-confirm {confirmed} tx")
    return {"confirmed": confirmed, "git_sha": sha}


def bulk_categorize(
    items: list[tuple[str, str]],
    *,
    entries: list,
    ledger_root: Path,
    user_email: str,
    history_path: Path | None = None,
    now_iso: str | None = None,
) -> dict:
    """Confirma una selección de tx con la categoría elegida, en UN solo commit (batch de la UI).

    A diferencia de `bulk_confirm` (confirma sugeridas sin cambiar cuenta y saltea las pending),
    acá cada tx trae su categoría — el contador la sacó de Suspense. Agrupa por (archivo, categoría),
    reescribe cada grupo una vez, un solo bean-check con rollback, history + un git commit.
    """
    from pipeline.importers.laudus_run import acquire_lock, bean_check, git_commit_push

    by_file: dict[Path, dict[str, set[str]]] = {}
    records: list[tuple[str, str, str | None, str]] = []  # (tx_id, new_cat, original_cat, narration)
    for tx_id, new_cat in items:
        t = _find(entries, tx_id)
        if t is None:
            raise TxNotFound(tx_id)
        fp = Path(t.meta["filename"])
        original_cat = next((p.account for p in t.postings
                             if p.account.split(":")[0] in ("Expenses", "Income")), None)
        by_file.setdefault(fp, {}).setdefault(new_cat, set()).add(tx_id)
        records.append((tx_id, new_cat, original_cat, t.narration or ""))

    if not by_file:
        return {"confirmed": 0, "git_sha": None}

    main_path = ledger_root / "main.beancount"
    lock_path = ledger_root / ".import.lock"
    hp = history_path or (ledger_root / "_meta" / "categorization-history.jsonl")

    confirmed = 0
    with acquire_lock(lock_path):
        snapshots = {fp: fp.read_text(encoding="utf-8") for fp in by_file}
        rels = []
        for fp, by_cat in by_file.items():
            for cat, ids in by_cat.items():
                confirmed += len(_rewrite_file(fp, ids, cat))
            rels.append(f"ledger/imports/cartolas/{fp.name}")
        ok, detail = bean_check(main_path)
        if not ok:
            for fp, content in snapshots.items():
                fp.write_text(content, encoding="utf-8")
            raise CategoryEditError(detail)
        for tx_id, new_cat, original_cat, narration in records:
            append_correction(hp, build_record(
                description=narration, corrected_category=new_cat,
                original_suggestion=original_cat, user=user_email, ts=now_iso))
        rels.append("ledger/_meta/categorization-history.jsonl")
        sha = git_commit_push(ledger_root, rels, f"[categorize] bulk {confirmed} tx")
    return {"confirmed": confirmed, "git_sha": sha}
