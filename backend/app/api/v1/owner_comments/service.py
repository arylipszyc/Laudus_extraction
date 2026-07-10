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
    append_read_marker,
    append_reply,
    append_resolution,
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


class ThreadAlreadyResolved(Exception):
    """El hilo ya tiene línea de resolución → no se resuelve dos veces (HTTP 400, Story 7.3 AC3)."""


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


def _is_unread(thread: dict, user_email: str, user_role: str) -> bool:
    """¿El hilo tiene actividad de LA OTRA PARTE posterior al último `read_at` del usuario? (7.4 AC4)

    Relevante para contador/admin = eventos del owner (rol `family`); para `family` = eventos del
    contador/admin. La propia actividad nunca cuenta (AC5, doblemente guardada por rol y email).
    Comparación lexicográfica de ISO-8601 (mismo criterio que `_last_activity`)."""
    events = [thread.get("root") or {}] + list(thread.get("replies", []))
    if user_role == "family":
        relevant = [e for e in events if e.get("author_role") in ("contador", "admin")]
    else:
        relevant = [e for e in events if e.get("author_role") == "family"]
    relevant = [e for e in relevant if e.get("author_email") != user_email]
    if not relevant:
        return False
    last_relevant = max(e.get("ts", "") for e in relevant)
    reads = [r.get("read_at", "") for r in thread.get("reads", [])
             if r.get("reader_email") == user_email]
    last_read = max(reads) if reads else ""
    return last_relevant > last_read


def list_threads(status: str, entries: list, ledger_root, *,
                 user_email: str = "", user_role: str = "") -> list[dict]:
    """Pliega el JSONL a hilos, re-resuelve cada ancla EN CALIENTE y adjunta el contexto (AC1/AC2).

    `status` filtra por resolución: `open` (sin resolución), `resolved` (con resolución), `all` (ambos).
    Cada hilo pasa por `resolve_anchor` contra los `entries` vivos → `anchor_status` + `tx_context`
    reflejan la transacción ACTUAL (un re-import entre comentario y lectura no rompe el contexto).
    Orden: última actividad primero. Con `user_email`/`user_role`, cada hilo trae `unread` PARA ese
    usuario (7.4) — el front lo usa para el indicador y para marcar leído solo cuando hace falta."""
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
            # 7.1b AC2: el tx_id ACTUAL de la tx ancla (el nuevo si re-anchored, null si orphaned)
            # — permite al front cruzar hilos ↔ filas del drill-down aun después de un re-import.
            "tx_id": resolved.get("tx_id"),
            "tx_context": _tx_context(resolved["status"], resolved["entry"], root),
            # 7.4: no-leído para ESTE usuario; solo hilos abiertos notifican (AC1).
            "unread": is_open and _is_unread(thread, user_email, user_role),
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
        _require_participant(threads[0], user_email)
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


# ── Story 7.3: resolver un hilo (FR40) ───────────────────────────────────────


def _require_participant(thread: dict, user_email: str) -> None:
    """Un `family` solo actúa sobre hilos donde participa (raíz o alguna respuesta suya).

    Misma postura que el patch del review de 7.2 en `reply`: el scoping del inbox ya le esconde
    los hilos ajenos, esto cierra el acceso directo por id."""
    participants = {(thread.get("root") or {}).get("author_email")}
    participants |= {r.get("author_email") for r in thread.get("replies", [])}
    if user_email not in participants:
        raise NotParticipant(thread["thread_id"])


def resolve_thread(
    thread_id: str,
    note: str | None,
    *,
    user_email: str,
    user_role: str,
    ledger_root,
    now_iso: str | None = None,
) -> dict:
    """Marca el hilo como resuelto appendeando la línea de resolución (AC1). Espejo del patrón
    de reconciliación (`resolve()` + guard antes de escribir):

    - hilo inexistente → `ThreadNotFound` (404), nada se escribe (AC4);
    - `family` solo resuelve hilos donde participa (postura de `reply`); contador/admin cualquiera
      — la autorización corre ANTES del guard de estado (un family ajeno no aprende si el hilo
      está resuelto: siempre 403);
    - ya resuelto → `ThreadAlreadyResolved` (400) ANTES del append — nunca dos resoluciones (AC3).

    "Resuelto" se deriva de UNA sola cosa: la línea de resolución en el JSONL (misma definición
    que usa el filtro `status` del inbox de 7.2 — sin flag paralelo)."""
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    threads = read_threads(default_jsonl_path(ledger_root), thread_id=thread_id)
    if not threads:
        raise ThreadNotFound(thread_id)
    thread = threads[0]
    if user_role == "family":
        _require_participant(thread, user_email)
    if thread.get("resolution") is not None:
        raise ThreadAlreadyResolved(thread_id)
    resolution = {
        "action": "resolve",
        "resolved_by": user_email,
        "resolved_by_role": user_role,
        "resolved_at": ts,
        "note": note,
    }
    persist_and_commit(
        lambda p: append_resolution(thread_id, resolution, p),
        f"[owner-comment] resolve {user_role} hilo {thread_id[:8]}",
        ledger_root=ledger_root,
    )
    return {"thread_id": thread_id, "resolved_at": ts}


# ── Story 7.4: conteo de no-leídos + marcador de lectura (FR37/FR41 in-app) ──


def comments_count(*, user_email: str, user_role: str, ledger_root) -> dict:
    """`{total, unread}` PARA este usuario (AC1): total = hilos abiertos que le conciernen
    (family: solo los suyos, mismo scoping que el inbox); unread = los que tienen actividad de
    la otra parte posterior a su último marcador de lectura. Los resueltos no notifican."""
    threads = read_threads(default_jsonl_path(ledger_root))
    open_threads = [t for t in threads
                    if t.get("root") is not None and t.get("resolution") is None]
    if user_role == "family":
        open_threads = [t for t in open_threads
                        if (t.get("root") or {}).get("author_email") == user_email]
    unread = sum(1 for t in open_threads if _is_unread(t, user_email, user_role))
    return {"total": len(open_threads), "unread": unread}


def mark_read(
    thread_id: str,
    *,
    user_email: str,
    user_role: str,
    ledger_root,
    now_iso: str | None = None,
) -> dict:
    """Appendea el marcador de lectura del usuario sobre el hilo (AC2). 404 si no existe (sin
    escritura); un `family` solo marca hilos donde participa (misma postura que reply/resolve)."""
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    threads = read_threads(default_jsonl_path(ledger_root), thread_id=thread_id)
    if not threads:
        raise ThreadNotFound(thread_id)
    if user_role == "family":
        _require_participant(threads[0], user_email)
    persist_and_commit(
        lambda p: append_read_marker(thread_id, user_email, ts, p),
        f"[owner-comment] read {user_role} hilo {thread_id[:8]}",
        ledger_root=ledger_root,
    )
    return {"thread_id": thread_id, "read_at": ts}
