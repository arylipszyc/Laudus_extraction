"""Corrección de categorías sobre el ledger Beancount — Story 9.7 AC7/AC8/AC9/AC10(tx_id).

Localiza una transacción por `tx_id` estable, le cambia la cuenta de categoría + flag (`!`→`*`)
+ `category_status`, re-genera el archivo de cartola (write-and-replace, determinista como el
importer), corre bean-check, appendea la corrección a `categorization-history.jsonl` (alimenta
la regla supra de 9.7) y commitea. El cache del CategorizationService se invalida.
"""
from __future__ import annotations

import hashlib
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


def compute_tx_id(filename: str, lineno: int, narration: str, amount) -> str:
    """tx_id estable = sha256(file, line, narration, monto)[:12] (Story 9.7 Task 6).

    Estable entre commits del mismo archivo mientras beancount no re-numere líneas en un
    re-render determinista (el importer emite el mismo orden → mismas líneas)."""
    base = f"{Path(filename).name}:{lineno}:{narration}:{amount}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]


def _tx_id_of(entry: data.Transaction) -> str:
    first = entry.postings[0].units.number if entry.postings and entry.postings[0].units else ""
    return compute_tx_id(entry.meta.get("filename", ""), entry.meta.get("lineno", 0),
                         entry.narration or "", first)


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


def _rewrite_file(file_path: Path, tx_ids: set[str], new_category: str | None, bank_target: str) -> dict[str, str]:
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
                postings = [
                    p._replace(account=new_category) if p.account != bank_target else p
                    for p in postings
                ]
            meta = dict(e.meta or {})
            meta["category_status"] = "confirmed"
            affected[_tx_id_of(e)] = e.narration or ""
            e = e._replace(flag="*", postings=postings, meta=meta)
        out_entries.append(e)
    file_path.write_text(render_entries(out_entries), encoding="utf-8")
    return affected


def _resolve_bank_target(entry: data.Transaction, ledger_root: Path) -> str:
    """Cuenta del banco/TC de la tx (la posting que NO es la categoría)."""
    from pipeline.importers.bank_account_resolver import BankAccountResolver
    bank_id = (entry.meta or {}).get("bank_account_id")
    if bank_id:
        try:
            return BankAccountResolver(ledger_root / "accounts.beancount").resolve(str(bank_id))
        except Exception:  # noqa: BLE001
            pass
    # fallback: la posting Assets/Liabilities
    for p in entry.postings:
        if p.account.split(":")[0] in ("Assets", "Liabilities"):
            return p.account
    return entry.postings[0].account if entry.postings else ""


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
    bank_target = _resolve_bank_target(target, ledger_root)
    original_cat = next((p.account for p in target.postings
                         if p.account.split(":")[0] in ("Expenses", "Income")), None)
    main_path = ledger_root / "main.beancount"
    lock_path = ledger_root / ".import.lock"

    with acquire_lock(lock_path):
        original = file_path.read_text(encoding="utf-8")
        affected = _rewrite_file(file_path, {tx_id}, new_category, bank_target)
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
            affected = _rewrite_file(fp, ids, None, bank_target="")  # solo confirma, no cambia cuenta
            confirmed += len(affected)
            rels.append(f"ledger/imports/cartolas/{fp.name}")
        ok, detail = bean_check(main_path)
        if not ok:
            for fp, content in snapshots.items():
                fp.write_text(content, encoding="utf-8")
            raise CategoryEditError(detail)
        sha = git_commit_push(ledger_root, rels, f"[categorize] bulk-confirm {confirmed} tx")
    return {"confirmed": confirmed, "git_sha": sha}
