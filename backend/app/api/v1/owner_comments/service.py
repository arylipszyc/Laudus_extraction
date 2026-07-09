"""Servicio de owner-comments — Story 7.1 (FR36).

Crea el comentario RAÍZ de un hilo sobre una transacción, consumiendo el módulo habilitador de
7.0 (`owner_comments_writer`): captura el ancla de 3 capas, arma el comentario y lo persiste+commitea
bajo lock. NO reimplementa nada del writer; solo orquesta.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pipeline.importers.owner_comments_writer import (
    append_comment,
    build_anchor,
    build_comment,
    persist_and_commit,
)


def create_comment(
    tx_id: str,
    body: str,
    *,
    user_email: str,
    user_role: str,
    entries: list,
    ledger_root,
    now_iso: str | None = None,
) -> dict:
    """Crea el comentario raíz sobre `tx_id` y lo persiste (AC1).

    `build_anchor` levanta `AnchorNotFound` si el `tx_id` no resuelve → el router lo mapea a 404
    (nada se escribe). El commit/push va por `persist_and_commit` (no-op si git deshabilitado);
    si falla de verdad, el error se propaga → 500 (AC5)."""
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    anchor = build_anchor(tx_id, entries, ledger_root=ledger_root)
    comment = build_comment(
        anchor=anchor, author_email=user_email, author_role=user_role, body=body, ts=ts,
    )
    persist_and_commit(
        lambda p: append_comment(comment, p),
        f"[owner-comment] {user_role} sobre tx {tx_id[:8]}",
        ledger_root=ledger_root,
    )
    return {
        "thread_id": comment["thread_id"],
        "comment_id": comment["comment_id"],
        "created_at": ts,
    }
