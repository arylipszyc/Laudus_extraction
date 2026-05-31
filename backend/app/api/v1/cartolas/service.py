"""Cartola upload service — Story 9.5.

Coordinates: validation → Gemini extraction → schema validation → post-process
warnings → staging file write. Tracks async jobs in an in-memory singleton
keyed by `batch_id` (TTL 1h, evicted opportunistically on read).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from backend.app.integrations.bank_account_index import (
    BankAccountEntry,
    BankAccountIndex,
)
from backend.app.integrations.cartola_post_process import apply_post_process
from backend.app.integrations.cartola_schema import CartolaCanonicalV1
from backend.app.integrations.gemini_client import (
    GeminiClient,
    GeminiExtractionError,
)

logger = logging.getLogger(__name__)

MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024  # NFR3: 20MB
JOB_TTL_SECONDS = 60 * 60  # 1 hour
# Story 9.5h: draws independientes ante fallo transitorio de Gemini (línea
# omitida → BALANCE_MISMATCH, o JSON truncado → GeminiExtractionError).
MAX_EXTRACTION_ATTEMPTS = 3

JobStatus = Literal["processing", "ready", "failed"]

_DEFAULT_STAGING_DIR = Path(
    os.getenv("CARTOLA_STAGING_DIR")
    or Path(__file__).resolve().parents[5] / "ledger" / "imports" / "cartolas" / "_staging"
)


def get_default_staging_dir() -> Path:
    """Module-level indirection so tests can monkey-patch _DEFAULT_STAGING_DIR
    and have it picked up at call time (function defaults freeze at def-time)."""
    return _DEFAULT_STAGING_DIR


# ── Domain errors (caller maps to HTTP) ───────────────────────────────────


class CartolaValidationError(Exception):
    """Pre-Gemini validation failure (HTTP 400)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ── Job store (singleton, thread-safe) ───────────────────────────────────


class _JobStore:
    """In-memory dict of batch_id → {status, canonical, error, created_at}.

    TTL eviction is lazy: we drop entries older than JOB_TTL_SECONDS on every
    read. Simpler than a background sweeper and good enough for a single-process
    deployment (Render single instance — no cross-worker state).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def create(self, batch_id: str) -> None:
        with self._lock:
            self._evict_expired_locked()
            self._jobs[batch_id] = {
                "status": "processing",
                "canonical": None,
                "error": None,
                "created_at": time.monotonic(),
            }

    def set_ready(self, batch_id: str, canonical: CartolaCanonicalV1) -> None:
        with self._lock:
            if batch_id in self._jobs:
                self._jobs[batch_id]["status"] = "ready"
                self._jobs[batch_id]["canonical"] = canonical

    def set_failed(self, batch_id: str, code: str, message: str) -> None:
        with self._lock:
            if batch_id in self._jobs:
                self._jobs[batch_id]["status"] = "failed"
                self._jobs[batch_id]["error"] = {"code": code, "message": message}

    def get(self, batch_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._evict_expired_locked()
            return self._jobs.get(batch_id)

    def _evict_expired_locked(self) -> None:
        cutoff = time.monotonic() - JOB_TTL_SECONDS
        expired = [bid for bid, j in self._jobs.items() if j["created_at"] < cutoff]
        for bid in expired:
            del self._jobs[bid]

    def reset_for_testing(self) -> None:
        with self._lock:
            self._jobs.clear()


_job_store = _JobStore()


def get_job_store() -> _JobStore:
    return _job_store


# ── Validation (AC1) ─────────────────────────────────────────────────────


def validate_upload_inputs(
    *,
    pdf_bytes: bytes,
    content_type: str | None,
    bank_account_id: str,
    index: BankAccountIndex,
) -> BankAccountEntry:
    """All AC1 checks. Returns the resolved bank account on success."""
    if not pdf_bytes:
        raise CartolaValidationError("VALIDATION_FAILED", "PDF file is empty")

    if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
        raise CartolaValidationError(
            "VALIDATION_FAILED",
            f"PDF exceeds the {MAX_PDF_SIZE_BYTES // (1024 * 1024)}MB limit",
        )

    if content_type and content_type.lower() != "application/pdf":
        raise CartolaValidationError(
            "VALIDATION_FAILED",
            f"Content-Type must be application/pdf (got {content_type})",
        )

    # Magic bytes — defense against client lying about MIME.
    if not pdf_bytes.startswith(b"%PDF"):
        raise CartolaValidationError(
            "VALIDATION_FAILED",
            "File does not look like a PDF (missing %PDF magic bytes)",
        )

    entry = index.get(bank_account_id)
    if entry is None:
        raise CartolaValidationError(
            "VALIDATION_FAILED",
            f"bank_account_id '{bank_account_id}' is not registered in accounts.beancount",
        )

    if entry.last4 is None:
        raise CartolaValidationError(
            "MISSING_LAST4",
            (
                "Esta cuenta bancaria no tiene `bank_account_last4` registrado en "
                "`accounts.beancount`. Editar vía Fava antes de subir cartolas "
                "(ver runbook contador-onboarding-fava.md)."
            ),
        )

    return entry


# ── Source resolution (AC5) ──────────────────────────────────────────────


def resolve_source_dict(entry: BankAccountEntry) -> dict[str, str]:
    """Build the `source` block of the canonical JSON from the index entry."""
    return {
        "bank_account_id": entry.bank_account_id,
        "bank_name": entry.bank_name,
        "account_label": entry.account_label,
        "account_type": entry.account_type,
        "entity": entry.entity,
    }


# ── Staging file (AC8) ────────────────────────────────────────────────────


def write_staging_file(canonical: CartolaCanonicalV1, batch_id: str,
                       staging_dir: Path | None = None) -> Path:
    """Persist the canonical JSON to `_staging/{batch_id}.cartola.json`.

    Returns the full path. Caller must NOT log the full PDF or any sensitive
    payload — only the path.
    """
    if staging_dir is None:
        staging_dir = get_default_staging_dir()
    staging_dir.mkdir(parents=True, exist_ok=True)
    target = staging_dir / f"{batch_id}.cartola.json"
    target.write_text(
        canonical.model_dump_json(indent=2, by_alias=False),
        encoding="utf-8",
    )
    return target


# ── Pipeline (the synchronous body of the job) ────────────────────────────


def _has_balance_mismatch(canonical: CartolaCanonicalV1) -> bool:
    return any(w.code == "BALANCE_MISMATCH" for w in canonical.extraction.warnings)


def _extract_and_enrich(
    *,
    pdf_bytes: bytes,
    bank_account_entry: BankAccountEntry,
    gemini: GeminiClient,
    history: list | None,
) -> CartolaCanonicalV1:
    """One extraction draw: Gemini → server-side stamps → validate → post-process.

    Raises GeminiExtractionError (bad/truncated JSON) or Pydantic ValidationError
    (invalid canonical shape).
    """
    raw_dict = gemini.extract_pdf(
        pdf_bytes=pdf_bytes,
        bank_account_id=bank_account_entry.bank_account_id,
        bank_name=bank_account_entry.bank_name,
        account_label=bank_account_entry.account_label,
        account_type=bank_account_entry.account_type,
        currency=bank_account_entry.currency,
        last4=bank_account_entry.last4,
    )

    # AC5: server-side overrides — we don't trust Gemini's source/extraction stamps.
    raw_dict["source"] = resolve_source_dict(bank_account_entry)
    raw_dict.setdefault("extraction", {})
    raw_dict["extraction"]["model"] = gemini.model
    raw_dict["extraction"]["extracted_at"] = datetime.now(timezone.utc).isoformat()
    raw_dict.setdefault("schema_version", "1.0")

    canonical = CartolaCanonicalV1.model_validate(raw_dict)
    return apply_post_process(canonical, historical_amounts=history)


def process_upload_sync(
    *,
    batch_id: str,
    pdf_bytes: bytes,
    bank_account_entry: BankAccountEntry,
    gemini: GeminiClient,
    historical_amounts_provider=None,
    staging_dir: Path | None = None,
) -> CartolaCanonicalV1:
    """Run the full pipeline and write the staging file. Returns the canonical.

    Story 9.5h: hasta MAX_EXTRACTION_ATTEMPTS draws independientes ante un fallo
    transitorio (GeminiExtractionError o BALANCE_MISMATCH). Corta apenas obtiene
    un resultado limpio. Si se agotan los intentos devuelve el mejor canonical
    válido obtenido (un BALANCE_MISMATCH persistente es legítimo y se surfacea
    como warning, no se oculta). Si nunca hubo canonical válido, propaga el
    último GeminiExtractionError. Raises Pydantic ValidationError sin reintentar
    (shape inválido = problema determinista; el caller lo marca como failed).
    """
    history = None
    if historical_amounts_provider is not None:
        history = historical_amounts_provider(bank_account_entry.bank_account_id)

    last_valid: CartolaCanonicalV1 | None = None
    last_extraction_error: GeminiExtractionError | None = None

    for attempt in range(1, MAX_EXTRACTION_ATTEMPTS + 1):
        try:
            enriched = _extract_and_enrich(
                pdf_bytes=pdf_bytes,
                bank_account_entry=bank_account_entry,
                gemini=gemini,
                history=history,
            )
        except GeminiExtractionError as exc:
            last_extraction_error = exc
            logger.warning(
                "cartola_upload: batch_id=%s extraction_error attempt %d/%d: %s",
                batch_id, attempt, MAX_EXTRACTION_ATTEMPTS, exc,
            )
            continue
        except ValidationError:
            # Shape inválido = problema determinista; NO se reintenta (AC4).
            # Pero si un intento previo ya produjo un canonical válido, no se
            # descarta: se devuelve ese (mejor resultado obtenido).
            if last_valid is not None:
                break
            raise

        last_valid = enriched
        if not _has_balance_mismatch(enriched):
            write_staging_file(enriched, batch_id, staging_dir)
            return enriched

        logger.warning(
            "cartola_upload: batch_id=%s balance_mismatch attempt %d/%d, retrying",
            batch_id, attempt, MAX_EXTRACTION_ATTEMPTS,
        )

    if last_valid is not None:
        # Best result obtained — BALANCE_MISMATCH persisted across all attempts.
        write_staging_file(last_valid, batch_id, staging_dir)
        return last_valid

    # All attempts raised GeminiExtractionError — never got a valid canonical.
    assert last_extraction_error is not None
    raise last_extraction_error


def run_job(
    *,
    batch_id: str,
    pdf_bytes: bytes,
    bank_account_entry: BankAccountEntry,
    gemini: GeminiClient,
    historical_amounts_provider=None,
    staging_dir: Path | None = None,
) -> None:
    """Wrap process_upload_sync in job-store updates. Errors are logged + stored."""
    try:
        canonical = process_upload_sync(
            batch_id=batch_id,
            pdf_bytes=pdf_bytes,
            bank_account_entry=bank_account_entry,
            gemini=gemini,
            historical_amounts_provider=historical_amounts_provider,
            staging_dir=staging_dir,
        )
        _job_store.set_ready(batch_id, canonical)
        logger.info(
            "cartola_upload: batch_id=%s ready bank_account_id=%s n_tx=%d",
            batch_id, bank_account_entry.bank_account_id, len(canonical.transactions),
        )
    except GeminiExtractionError as exc:
        _job_store.set_failed(batch_id, "EXTRACTION_FAILED", str(exc))
        logger.error("cartola_upload: batch_id=%s gemini failure: %s", batch_id, exc)
    except ValidationError as exc:
        _job_store.set_failed(batch_id, "EXTRACTION_FAILED", json.dumps(exc.errors()))
        logger.error(
            "cartola_upload: batch_id=%s schema validation failed (%d errors)",
            batch_id, len(exc.errors()),
        )
    except Exception as exc:  # noqa: BLE001
        _job_store.set_failed(batch_id, "INTERNAL_ERROR", str(exc))
        logger.exception("cartola_upload: batch_id=%s unexpected failure", batch_id)


def new_batch_id() -> str:
    return str(uuid.uuid4())
