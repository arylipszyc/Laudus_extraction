"""Request/response schemas for the cartolas API — Story 9.5 + 9.9."""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from backend.app.integrations.cartola_schema import CartolaCanonicalV1


class ValidateBalanceRequest(BaseModel):
    """PATCH /api/v1/cartolas/{batch_id}/validate-balance — Story 9.9."""
    opening: Decimal
    closing: Decimal
    override_justification: str | None = None


class ValidateBalanceResponse(BaseModel):
    """Resultado de conciliar una cartola (Story 6.1, modelo A). `reconciled` = el matching corrió.
    La cartola NO se postea al ledger; solo se reportan las diferencias cartola↔Laudus, que el
    dashboard 9.12 muestra para que el contador las revise (`blocking` = bloqueantes, chip rojo)."""
    status: Literal["reconciled"]
    differences: int
    blocking: int
    matched: int
    git_sha: str | None = None
    override: bool = False
    batch_id: str | None = None


class TcLaudusPayment(BaseModel):
    date: str
    narration: str
    amount: float
    bank_account: str | None = None


class TcCuadre(BaseModel):
    """Cuadre de la cartola contra el ledger (post-confirmación) — Valentina 2026-07-02."""
    c1_ok: bool                       # TC:Real al cierre == −cierre declarado
    tc_real_balance: float
    closing: float
    pago_cartola: float               # PAGO PAC de la cartola
    laudus_payment_total: float       # pago que Laudus registró para la tarjeta ese mes
    laudus_payments: list[TcLaudusPayment] = []
    pago_ok: bool                     # pago cartola == pago Laudus


class TcCorrectionResponse(BaseModel):
    """Resultado de corregir una cartola de TARJETA DE CRÉDITO (Story 6.2, flujo Valentina).

    A diferencia del modelo A (`ValidateBalanceResponse`, reconcilia sin postear), la TC SÍ postea el
    desglose al ledger, así que la forma de la respuesta es distinta: `corrected` (posteó) o `blocked`
    (no pudo derivar FX/lump). Los campos TC-específicos son opcionales (un `blocked` no trae `file`)."""
    status: Literal["corrected", "blocked"]
    batch_id: str
    currency: str
    fx: str | None = None
    purchases: int = 0
    payments: int = 0
    opening_emitted: bool = False
    unmapped: list = []
    fx_bcch: str | None = None
    fx_deviation_pct: float | None = None
    git_commit_sha: str | None = None
    file: str | None = None
    reason: str | None = None
    cuadre: TcCuadre | None = None


class UploadAcceptedResponse(BaseModel):
    """202 response from POST /api/v1/cartolas/upload — async pattern."""
    status: Literal["processing"] = "processing"
    batch_id: str


class StatusResponse(BaseModel):
    """GET /api/v1/cartolas/{batch_id}."""
    batch_id: str
    status: Literal["processing", "ready", "failed"]
    canonical: CartolaCanonicalV1 | None = None
    error: dict | None = None
    already_imported: bool = False  # ya existe una cartola para esta tarjeta/mes (avisar antes de sobrescribir)
