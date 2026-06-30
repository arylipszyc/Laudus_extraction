"""Schemas de transactions/categorization — Story 9.7."""
from pydantic import BaseModel


class PatchCategoryRequest(BaseModel):
    category_account: str


class PatchCategoryResponse(BaseModel):
    tx_id: str
    category_account: str
    flag: str
    git_sha: str | None = None


class BulkConfirmRequest(BaseModel):
    batch_id: str | None = None


class BulkConfirmResponse(BaseModel):
    confirmed: int
    git_sha: str | None = None


class PendingTx(BaseModel):
    tx_id: str
    bank_account_id: str | None = None
    date: str
    narration: str | None = None
    amount: float | None = None
    current_category: str | None = None
    current_flag: str | None = None
    current_match_source: str | None = None
    current_category_status: str | None = None
    current_color: str | None = None        # Goal B (§10.2): green | yellow | red
    current_confidence: float | None = None
