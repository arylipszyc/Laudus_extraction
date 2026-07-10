"""Router de owner-comments — Stories 7.1 (FR36) + 7.2 (FR38/FR39).

POST /api/v1/comments             — el owner crea un comentario raíz sobre una transacción (7.1).
GET  /api/v1/comments             — inbox de hilos (contador: todos; owner: los suyos, filtro en el front) (7.2).
POST /api/v1/comments/{id}/reply  — responder un hilo con contexto inline (7.2).
RBAC: family/contador/admin (**ambos roles participan del hilo**). Primer endpoint de ESCRITURA que
admite `family` (ver ADR 7.0).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.v1.owner_comments.schemas import (
    CreateCommentRequest,
    CreateCommentResponse,
    ReplyRequest,
    ReplyResponse,
    ResolveThreadRequest,
    ResolveThreadResponse,
    ThreadView,
)
from backend.app.api.v1.owner_comments.service import (
    NotParticipant,
    ThreadAlreadyResolved,
    ThreadNotFound,
    create_comment,
    list_threads,
    reply,
    resolve_thread,
)
from backend.app.auth.schemas import UserSession
from backend.app.dependencies import get_ledger_service, require_role
from backend.app.services.ledger_service import LedgerService, LedgerUnavailableError
from pipeline.importers.owner_comments_writer import AnchorNotFound

router = APIRouter(prefix="/comments", tags=["owner-comments"])


def _entries(ledger: LedgerService):
    try:
        return ledger.entries()
    except LedgerUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"LEDGER_UNAVAILABLE: {exc.detail}")


@router.post("", response_model=CreateCommentResponse, status_code=201)
def create_comment_endpoint(
    request: CreateCommentRequest,
    user: UserSession = Depends(require_role(["family", "contador", "admin"])),
    ledger: LedgerService = Depends(get_ledger_service),
):
    root = Path(ledger.main_path).parent
    entries = _entries(ledger)  # fuera del try: su HTTPException(503) debe propagar sin re-envolverse
    try:
        result = create_comment(
            request.tx_id, request.body,
            user_email=user.email, user_role=user.role,
            entries=entries, ledger_root=root,
        )
    except AnchorNotFound:
        raise HTTPException(status_code=404, detail=f"tx {request.tx_id} no encontrada")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as exc:
        # AC5: fallo real de persistencia/git (o LockTimeout, subclase de RuntimeError) → 500 CON
        # detalle, no el 500 genérico del handler default. El append local ya ocurrió dentro del lock
        # (boundary conocido, documentado en AC5); acá solo se garantiza que el cliente reciba el motivo.
        raise HTTPException(status_code=500, detail=f"COMMENT_PERSIST_FAILED: {exc}")
    return CreateCommentResponse(**result)


@router.get("", response_model=list[ThreadView])
def list_comments_endpoint(
    status: Literal["open", "resolved", "all"] = "open",
    user: UserSession = Depends(require_role(["family", "contador", "admin"])),
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Inbox de hilos (AC1/AC2). El back acota por rol: el `family` solo ve SUS hilos (por
    `author_email` del JWT); contador/admin ven todos. Re-resuelve el ancla en caliente contra el
    ledger vivo → contexto siempre actual."""
    root = Path(ledger.main_path).parent
    entries = _entries(ledger)  # fuera del try (no hay): su 503 debe propagar tal cual
    threads = list_threads(status, entries, root)
    if user.role == "family":
        threads = [t for t in threads if t["root"]["author_email"] == user.email]
    return threads


@router.post("/{thread_id}/reply", response_model=ReplyResponse, status_code=201)
def reply_endpoint(
    thread_id: str,
    request: ReplyRequest,
    user: UserSession = Depends(require_role(["family", "contador", "admin"])),
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Responde un hilo (AC3/AC5). NO lo cierra (7.3). No necesita los `entries` del ledger — la
    existencia del hilo se chequea contra el JSONL —, así que no puede fallar por 503 de ledger."""
    root = Path(ledger.main_path).parent
    try:
        result = reply(
            thread_id, request.body,
            user_email=user.email, user_role=user.role, ledger_root=root,
        )
    except ThreadNotFound:
        raise HTTPException(status_code=404, detail=f"hilo {thread_id} no existe")
    except NotParticipant:
        raise HTTPException(status_code=403, detail="no participás de este hilo")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as exc:
        # Mismo mapeo de errores de persistencia que el POST de 7.1 (AC3).
        raise HTTPException(status_code=500, detail=f"COMMENT_PERSIST_FAILED: {exc}")
    return ReplyResponse(**result)


@router.post("/{thread_id}/resolve", response_model=ResolveThreadResponse)
def resolve_endpoint(
    thread_id: str,
    request: ResolveThreadRequest,
    user: UserSession = Depends(require_role(["family", "contador", "admin"])),
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Resuelve un hilo (Story 7.3, FR40). Ambos roles pueden cerrar; el guard de idempotencia
    corre ANTES de escribir (doble resolución → 400, patrón ResolveError de reconciliación)."""
    root = Path(ledger.main_path).parent
    try:
        result = resolve_thread(
            thread_id, request.note,
            user_email=user.email, user_role=user.role, ledger_root=root,
        )
    except ThreadNotFound:
        raise HTTPException(status_code=404, detail=f"hilo {thread_id} no existe")
    except ThreadAlreadyResolved:
        raise HTTPException(status_code=400, detail=f"hilo {thread_id} ya está resuelto")
    except NotParticipant:
        raise HTTPException(status_code=403, detail="no participás de este hilo")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=f"COMMENT_PERSIST_FAILED: {exc}")
    return ResolveThreadResponse(**result)
