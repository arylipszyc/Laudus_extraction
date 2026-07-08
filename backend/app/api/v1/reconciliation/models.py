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


class BatchResolveItem(BaseModel):
    """Un item del batch (Story 6.7). La justificación es COMÚN al batch (va en el request), no acá."""
    discrepancy_id: str
    action: str
    category_account: str | None = None


class BatchResolveRequest(BaseModel):
    items: list[BatchResolveItem]
    # Story 6.7 (decisión Ary): UNA justificación común para todo el batch; se registra igual en cada
    # resolución. ≥10 chars salvo que TODAS las acciones sean escalate.
    justification: str | None = None


class BatchResolveResult(BaseModel):
    discrepancy_id: str
    status: str
    action: str
    git_commit_sha: str | None = None


class BatchResolveResponse(BaseModel):
    git_commit_sha: str | None = None
    results: list[BatchResolveResult]


class CountResponse(BaseModel):
    total: int
    blocking: int


class PeriodStatus(BaseModel):
    """Estado de un período de reconciliación (Story 6.5 AC3)."""
    bank_account_id: str | None = None
    year_month: str
    reconciled_at: str | None = None
    matched: int = 0
    differences: int = 0
    open: int
    status: str
