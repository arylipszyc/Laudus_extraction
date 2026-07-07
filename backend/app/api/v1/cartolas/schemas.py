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


class TcLine(BaseModel):
    """Línea genérica fecha/glosa/monto (ej. un asiento corrupto de C3)."""
    date: str
    narration: str
    amount: float


class TcCuadre(BaseModel):
    """Cuadre C1–C5 de la cartola contra el ledger (post-confirmación) — Valentina 2026-07-02 (v1),
    Story 6.6 (C2/C3/C5). Mismos campos que devuelve `compute_tc_cuadre`."""
    # C1 — invariante de cierre
    c1_ok: bool                       # TC:Real al cierre (CLP) == −cierre×fx
    tc_real_balance: float
    closing: float                    # moneda nativa
    closing_clp: float = 0.0          # cierre × fx (CLP), lo que compara C1
    currency: str = "CLP"
    fx: float = 1.0
    opening: float | None = None
    # C2 — contigüidad
    c2_ok: bool = False               # apertura[M] == cierre[M−1]
    c2_prior_closing: float | None = None
    c2_reason: str | None = None
    # C3 — integridad del asiento
    c3_ok: bool = True                # toda compra/cuota conserva su pata TC:Real
    c3_corrupted_count: int = 0
    c3_corrupted: list[TcLine] = []   # los asientos sin su pata de deuda (fecha/glosa/monto)
    # C4 — pago vs Laudus
    pago_cartola: float               # PAGO PAC de la cartola
    laudus_payment_total: float       # pago que Laudus registró para la tarjeta ese mes
    laudus_payments: list[TcLaudusPayment] = []
    pago_ok: bool                     # pago cartola == pago Laudus
    # C5 — lump residual
    c5_ok: bool = True                # el lump del mes quedó neteado (≈0)
    c5_residual: float = 0.0
    # semáforo agregado
    status: str = "green"             # green | yellow | red


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
    fx_source: str | None = None      # "inherited:YYYY-MM" si el fx se heredó (mes revolving)
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
    # processing/ready/failed = fase de extracción; confirming/confirmed/confirm_failed =
    # fase de confirm (batch 2 Fase 3: el PATCH devuelve 202 y el resultado llega por acá).
    status: Literal["processing", "ready", "failed",
                    "confirming", "confirmed", "confirm_failed"]
    canonical: CartolaCanonicalV1 | None = None
    error: dict | None = None
    result: dict | None = None  # payload del confirm (el que devolvía el PATCH sincrónico)
    already_imported: bool = False  # ya existe una cartola para esta tarjeta/mes (avisar antes de sobrescribir)


class ConfirmAcceptedResponse(BaseModel):
    """202 del PATCH /validate-balance — el confirm quedó corriendo en background."""
    status: Literal["confirming"] = "confirming"
    batch_id: str
