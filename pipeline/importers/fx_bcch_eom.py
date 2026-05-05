"""Refetch del dólar observado de cierre de mes — orquestador idempotente.

Story 9.10. Llamado por el endpoint admin `POST /api/v1/admin/fx-bcch/refetch`
y disponible también como CLI: `python -m pipeline.importers.fx_bcch_eom 2026-04`.

Comportamiento:
    1. Valida que `year_month` sea un mes terminado (no futuro, no en curso).
    2. Itera hacia atrás desde el último día calendario del mes hasta encontrar
       el primer día con publicación BCCh (max 7 días: cubre fin de semana
       largo + feriados).
    3. Dedup por `year_month` contra `ledger/_meta/fx-bcch-eom.jsonl` —
       segunda llamada para el mismo mes devuelve el registro existente.
    4. Append al JSONL si no existía.
"""
from __future__ import annotations

import calendar
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from pipeline.integrations.mindicador_client import fetch_dolar_observado

logger = logging.getLogger(__name__)

JSONL_RELATIVE_PATH = Path("_meta/fx-bcch-eom.jsonl")
SCHEMA_VERSION = "1.0"
SOURCE_LABEL = "mindicador-dolar-observado"
LOOKBACK_DAYS = 7


class RefetchValidationError(ValueError):
    """`year_month` inválido (formato, futuro o mes en curso)."""


class NoPublicationFoundError(RuntimeError):
    """Tras `LOOKBACK_DAYS` no se encontró ningún día con publicación BCCh."""


@dataclass
class RefetchResult:
    status: str           # "fetched" | "skipped"
    year_month: str
    bcch_date: str
    rate_clp_per_usd: float
    source: str

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "year_month": self.year_month,
            "bcch_date": self.bcch_date,
            "rate_clp_per_usd": self.rate_clp_per_usd,
            "source": self.source,
        }


def refetch_eom(
    year_month: str,
    *,
    ledger_path: Optional[Path] = None,
    today: Optional[date] = None,
) -> RefetchResult:
    """Resuelve y persiste el rate de cierre del `year_month` indicado.

    Args:
        year_month: "YYYY-MM" — solo meses ya terminados.
        ledger_path: raíz del directorio ledger/ (default: LEDGER_PATH env var
            o ./ledger). Inyectable para tests.
        today: fecha actual. Inyectable para tests.

    Returns:
        RefetchResult con `status="fetched"` (escribió línea nueva) o
        `status="skipped"` (ya existía entrada para ese mes).
    """
    target_year, target_month = _parse_year_month(year_month)
    _validate_month_is_closed(target_year, target_month, today=today or date.today())

    jsonl_path = _resolve_jsonl_path(ledger_path)
    existing = _find_existing(jsonl_path, year_month)
    if existing is not None:
        logger.info("dedup hit for %s — skipping fetch", year_month)
        return RefetchResult(
            status="skipped",
            year_month=existing["year_month"],
            bcch_date=existing["bcch_date"],
            rate_clp_per_usd=existing["rate_clp_per_usd"],
            source=existing["source"],
        )

    bcch_date, rate = _fetch_last_publication(target_year, target_month)
    record = {
        "schema_version": SCHEMA_VERSION,
        "year_month": year_month,
        "rate_clp_per_usd": rate,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": SOURCE_LABEL,
        "bcch_date": bcch_date.isoformat(),
    }
    _append_jsonl(jsonl_path, record)
    logger.info("appended fx-bcch entry: %s = %s CLP/USD (bcch_date %s)",
                year_month, rate, bcch_date.isoformat())
    return RefetchResult(
        status="fetched",
        year_month=year_month,
        bcch_date=bcch_date.isoformat(),
        rate_clp_per_usd=rate,
        source=SOURCE_LABEL,
    )


def _parse_year_month(year_month: str) -> tuple[int, int]:
    if not isinstance(year_month, str) or len(year_month) != 7 or year_month[4] != "-":
        raise RefetchValidationError(
            f"year_month debe tener formato YYYY-MM, recibido: {year_month!r}"
        )
    try:
        year = int(year_month[:4])
        month = int(year_month[5:])
    except ValueError as exc:
        raise RefetchValidationError(f"year_month inválido: {year_month!r}") from exc
    if month < 1 or month > 12:
        raise RefetchValidationError(f"month fuera de rango 1-12: {month}")
    return year, month


def _validate_month_is_closed(year: int, month: int, *, today: date) -> None:
    """Rechaza meses futuros y el mes en curso (todavía no cerró)."""
    if (year, month) > (today.year, today.month):
        raise RefetchValidationError(
            f"year_month {year:04d}-{month:02d} es futuro respecto a hoy ({today.isoformat()})"
        )
    if (year, month) == (today.year, today.month):
        raise RefetchValidationError(
            f"year_month {year:04d}-{month:02d} es el mes en curso — esperá al cierre"
        )


def _fetch_last_publication(year: int, month: int) -> tuple[date, float]:
    """Itera hacia atrás desde fin de mes hasta encontrar publicación BCCh."""
    last_day = calendar.monthrange(year, month)[1]
    cursor = date(year, month, last_day)
    attempts: list[str] = []

    for _ in range(LOOKBACK_DAYS):
        rate = fetch_dolar_observado(cursor)
        if rate is not None:
            return cursor, rate
        attempts.append(cursor.isoformat())
        cursor = cursor - timedelta(days=1)

    raise NoPublicationFoundError(
        f"sin publicación BCCh tras {LOOKBACK_DAYS} días desde fin de mes "
        f"{year:04d}-{month:02d}; intentados: {attempts}"
    )


def _resolve_jsonl_path(ledger_path: Optional[Path]) -> Path:
    if ledger_path is None:
        env_path = os.getenv("LEDGER_PATH")
        ledger_path = Path(env_path) if env_path else Path("ledger")
    return ledger_path / JSONL_RELATIVE_PATH


def _find_existing(jsonl_path: Path, year_month: str) -> Optional[dict]:
    if not jsonl_path.exists():
        return None
    with jsonl_path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("skipping malformed JSONL line in %s", jsonl_path)
                continue
            if entry.get("year_month") == year_month:
                return entry
    return None


def _append_jsonl(jsonl_path: Path, record: dict) -> None:
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")


def _cli() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m pipeline.importers.fx_bcch_eom YYYY-MM", file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = refetch_eom(sys.argv[1])
    except RefetchValidationError as exc:
        print(f"validation error: {exc}", file=sys.stderr)
        return 2
    except NoPublicationFoundError as exc:
        print(f"no publication: {exc}", file=sys.stderr)
        return 3
    print(json.dumps(result.to_dict(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
