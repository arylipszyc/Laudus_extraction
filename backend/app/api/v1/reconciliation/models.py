"""Schemas de reconciliación — Story 9.12."""
from pydantic import BaseModel


class ResolveRequest(BaseModel):
    action: str
    justification: str | None = None
    # Story 6.3: cuenta de gasto destino al confirmar una línea de cartola ausente de Laudus.
    # Opcional (decisión Ary Q2): sin ella la tx entra a Suspense y la levanta /categorizacion.
    category_account: str | None = None


class ResolveResponse(BaseModel):
    status: str
    discrepancy_id: str
    action: str
    # Story 6.3: SHA del commit cuando la resolución anota una tx al ledger; None para el resto.
    git_commit_sha: str | None = None


class CountResponse(BaseModel):
    total: int
    blocking: int
