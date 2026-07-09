"""Schemas de owner-comments — Story 7.1 (FR36)."""
from typing import Annotated

from pydantic import BaseModel, StringConstraints

# body: texto plano, no vacío (se recorta y exige ≥1 char → "" y "   " dan 422). Decisión de
# diseño 7.1: sin markdown ni límite máximo en el MVP. `StringConstraints` produce un error de
# validación estándar/serializable (a diferencia de un validator que levante ValueError, cuyo
# `ctx` con el objeto excepción rompe el serializador del middleware de errores).
CommentBody = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CreateCommentRequest(BaseModel):
    tx_id: str
    body: CommentBody


class CreateCommentResponse(BaseModel):
    thread_id: str
    comment_id: str
    created_at: str
