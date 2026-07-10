"""Servicio de owner-comments — Story 7.1 (FR36).

Crea el comentario RAÍZ de un hilo sobre una transacción, consumiendo el módulo habilitador de
7.0 (`owner_comments_writer`): captura el ancla de 3 capas, arma el comentario y lo persiste+commitea
bajo lock. NO reimplementa nada del writer; solo orquesta.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pipeline.importers.owner_comments_writer import (
    append_comment,
    append_reply,
    build_anchor,
    build_comment,
    default_jsonl_path,
    persist_and_commit,
    read_threads,
    resolve_anchor,
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


# ── Story 7.2: inbox de lectura + respuesta ──────────────────────────────────


class ThreadNotFound(Exception):
    """No existe un hilo con ese `thread_id` en el JSONL → no se puede responder (HTTP 404)."""


class NotParticipant(Exception):
    """Un `family` intenta responder un hilo del que no es participante → prohibido (HTTP 403)."""


def _tx_context(anchor_status: str, entry, root: dict) -> dict:
    """Arma el contexto de la tx ancla (AC2): de la tx viva si el ancla resolvió, del snapshot si no."""
    if anchor_status in ("resolved", "re-anchored") and entry is not None:
        posting = entry.postings[0] if entry.postings else None
        number = posting.units.number if posting and posting.units else None
        return {
            "date": entry.date.isoformat(),
            "amount": float(number) if number is not None else None,
            "currency": posting.units.currency if posting and posting.units else None,
            "account": posting.account if posting else None,
            "narration": entry.narration or "",
            "anchor_status": anchor_status,
        }
    # orphaned (o entry ausente): caer al snapshot congelado por build_anchor (7.1) — nunca vacío.
    snap = (root.get("anchor") or {}).get("tx_snapshot") or {}
    return {
        "date": snap.get("date"),
        "amount": snap.get("amount"),
        "currency": snap.get("currency"),
        "account": snap.get("account"),
        "narration": snap.get("narration") or "",
        "anchor_status": anchor_status,
    }


def _last_activity(thread: dict) -> str:
    """Timestamp de la última actividad del hilo (raíz o respuesta más nueva) para ordenar (AC1).

    ISO-8601 → orden lexicográfico == orden cronológico (mismo criterio que `reconciled_at` en 6.5)."""
    ts_values = [(thread.get("root") or {}).get("ts", "")]
    ts_values += [r.get("ts", "") for r in thread.get("replies", [])]
    return max(ts_values) if ts_values else ""


def list_threads(status: str, entries: list, ledger_root) -> list[dict]:
    """Pliega el JSONL a hilos, re-resuelve cada ancla EN CALIENTE y adjunta el contexto (AC1/AC2).

    `status` filtra por resolución: `open` (sin resolución), `resolved` (con resolución), `all` (ambos).
    Cada hilo pasa por `resolve_anchor` contra los `entries` vivos → `anchor_status` + `tx_context`
    reflejan la transacción ACTUAL (un re-import entre comentario y lectura no rompe el contexto).
    Orden: última actividad primero."""
    threads = read_threads(default_jsonl_path(ledger_root))
    out = []
    for thread in threads:
        root = thread.get("root")
        if root is None:
            continue  # hilo sin raíz (JSONL corrupto/parcial) → no se muestra
        is_open = thread.get("resolution") is None
        if status == "open" and not is_open:
            continue
        if status == "resolved" and is_open:
            continue
        resolved = resolve_anchor(root, entries)
        out.append({
            "thread_id": thread["thread_id"],
            "root": root,
            "replies": thread.get("replies", []),
            "resolution": thread.get("resolution"),
            "anchor_status": resolved["status"],
            "tx_context": _tx_context(resolved["status"], resolved["entry"], root),
        })
    out.sort(key=_last_activity, reverse=True)
    return out


def reply(
    thread_id: str,
    body: str,
    *,
    user_email: str,
    user_role: str,
    ledger_root,
    now_iso: str | None = None,
) -> dict:
    """Appendea una respuesta a un hilo existente (AC3). NO lo cierra (eso es 7.3).

    Valida que el hilo exista (`read_threads` filtrado → vacío ⇒ `ThreadNotFound` → 404, nada se
    escribe). Un `family` solo puede responder hilos de los que es participante (raíz o alguna
    respuesta suya) ⇒ si no, `NotParticipant` → 403 (contador/admin sin restricción). Persiste vía
    `persist_and_commit` (lock → append → git). Un `thread_id` ya resuelto igual acepta respuesta
    (append puro, auditoría — decisión Ary AC5)."""
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    threads = read_threads(default_jsonl_path(ledger_root), thread_id=thread_id)
    if not threads:
        raise ThreadNotFound(thread_id)
    if user_role == "family":
        thread = threads[0]
        participants = {(thread.get("root") or {}).get("author_email")}
        participants |= {r.get("author_email") for r in thread.get("replies", [])}
        if user_email not in participants:
            raise NotParticipant(thread_id)
    reply_id = str(uuid.uuid4())
    record = {
        "reply_id": reply_id,
        "author_email": user_email,
        "author_role": user_role,
        "body": body,
        "ts": ts,
    }
    persist_and_commit(
        lambda p: append_reply(thread_id, record, p),
        f"[owner-comment] reply {user_role} sobre hilo {thread_id[:8]}",
        ledger_root=ledger_root,
    )
    return {"comment_id": reply_id, "created_at": ts}
