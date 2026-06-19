"""Schemas Pydantic — cuentas pendientes (Story 10.3)."""
from pydantic import BaseModel


class Suggestion(BaseModel):
    """Sugerencia derivada de las cuentas hermanas que comparten el prefijo numérico."""
    categoria1: str = ""
    categoria2: str = ""
    account: str = ""  # cuenta Beancount sugerida (vacía si no hay hermanas)


class PendingAccount(BaseModel):
    code: str
    pending_account: str  # Assets:EAG:PendingReview:Cuenta-{code}
    monto_acumulado: float  # suma de las JEs #pending-account que la referencian
    laudus_account_name: str | None = None
    suggestion: Suggestion


class PromoteRequest(BaseModel):
    categoria1: str
    categoria2: str
    categoria3: str  # rubro fino — obligatorio (validado en el router), requiere criterio humano (AC2)
    laudus_account_name: str = ""
    account: str = ""  # override opcional; default = la cuenta sugerida server-side


class PromoteResponse(BaseModel):
    code: str
    account: str
    git_commit_sha: str | None = None
    backfill_recommended: bool = True
    message: str
