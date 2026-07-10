"""Schemas de owner-comments — Story 7.1 (FR36)."""
from typing import Annotated

from pydantic import BaseModel, StringConstraints

# body: texto plano, no vacío (se recorta y exige ≥1 char → "" y "   " dan 422). Decisión de
# diseño 7.1: sin markdown en el MVP. `max_length` es un tope defensivo (no un límite de producto):
# es el primer write que admite `family` y el body se commitea a git de forma irreversible, así que
# se acota para que un body patológico no infle el repo (10k chars ≫ cualquier comentario real →
# no toca la UX). `StringConstraints` produce un error de validación estándar/serializable (a
# diferencia de un validator que levante ValueError, cuyo `ctx` con el objeto excepción rompe el
# serializador del middleware de errores).
CommentBody = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)]


class CreateCommentRequest(BaseModel):
    tx_id: str
    body: CommentBody


class CreateCommentResponse(BaseModel):
    thread_id: str
    comment_id: str
    created_at: str


# ── Story 7.2: inbox de lectura + respuesta ──────────────────────────────────


class TxContext(BaseModel):
    """Contexto de la transacción ancla, re-resuelto en caliente al listar (AC2).

    Viene de la tx VIVA cuando el ancla resolvió (`resolved`/`re-anchored`), o del `tx_snapshot`
    congelado cuando quedó `orphaned` (nunca se muestra un hilo sin contexto)."""
    date: str | None
    amount: float | None
    currency: str | None
    account: str | None
    narration: str
    anchor_status: str


class ThreadView(BaseModel):
    """Hilo plegado (`read_threads`) + estado de ancla + contexto de la tx (AC1)."""
    thread_id: str
    root: dict
    replies: list[dict]
    resolution: dict | None
    anchor_status: str
    tx_id: str | None = None
    tx_context: TxContext


class ReplyRequest(BaseModel):
    # Mismo `CommentBody` que 7.1 (StringConstraints, NO field_validator): body no vacío, tope 10k.
    body: CommentBody


class ReplyResponse(BaseModel):
    comment_id: str
    created_at: str
