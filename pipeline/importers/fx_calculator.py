"""Cálculo de FX implícita por línea USD + validación BCCh — Story 9.6b AC2/AC3.

FX implícita = CLP_laudus / USD_cartola (Q4 Opción D: la cartola trae el USD original que
Laudus perdió; el CLP del contador es la verdad del monto). Se valida contra el dólar
observado de cierre de mes (`ledger/_meta/fx-bcch-eom.jsonl`, poblado por Story 9.10) con
threshold de desviación 5%.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

logger = logging.getLogger(__name__)

TOLERANCE_PCT = Decimal("5")
FX_IMPLAUSIBLE = Decimal("2000")  # CLP/USD por encima de esto = dato sospechoso


@dataclass
class FXResult:
    implied: Decimal | None
    bcch: Decimal | None
    deviation_pct: Decimal | None
    state: str | None        # None (ok) | "fx-out-of-tolerance" | "fx-bcch-missing" | "fx-implausible"

    @property
    def out_of_tolerance(self) -> bool:
        return self.state == "fx-out-of-tolerance"


def lookup_bcch(jsonl_path: str | Path, year_month: str) -> Decimal | None:
    """Rate CLP/USD de cierre del `year_month` desde fx-bcch-eom.jsonl, o None si falta."""
    path = Path(jsonl_path)
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("línea malformada en %s", path)
            continue
        if entry.get("year_month") == year_month and entry.get("rate_clp_per_usd") is not None:
            return Decimal(str(entry["rate_clp_per_usd"]))
    return None


def latest_bcch(jsonl_path: str | Path) -> Decimal | None:
    """Rate CLP/USD del mes MÁS RECIENTE en fx-bcch-eom.jsonl, o None si el archivo falta/vacío.

    Ancla de plausibilidad para el matcher de pagos consolidados cuando NO hay BCCh del mes exacto:
    la banda pasa a ser `último BCCh ±tolerancia` (decisión Ary 2026-06-30) en vez de un rango
    hardcoded. Sin ningún BCCh → None → el matcher bloquea (falla segura, no adivina).
    """
    path = Path(jsonl_path)
    if not path.exists():
        return None
    best_ym: str | None = None
    best_rate: Decimal | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("línea malformada en %s", path)
            continue
        ym = entry.get("year_month")
        rate = entry.get("rate_clp_per_usd")
        if ym and rate is not None and (best_ym is None or ym > best_ym):  # "YYYY-MM" → orden lex = cronológico
            best_ym, best_rate = ym, Decimal(str(rate))
    return best_rate


def calculate_fx(usd_cartola: Decimal, clp_laudus: Decimal, bcch_rate: Decimal | None) -> FXResult:
    """FX implícita + clasificación vs BCCh.

    Args:
        usd_cartola: monto USD de la cartola (firmado; se usa magnitud).
        clp_laudus: monto CLP del asiento Laudus (firmado; se usa magnitud).
        bcch_rate: rate de cierre del mes (None si Story 9.10 no lo tiene → fx-bcch-missing).
    """
    usd = abs(usd_cartola)
    if usd == 0:
        return FXResult(implied=None, bcch=bcch_rate, deviation_pct=None, state="fx-implausible")

    implied = (abs(clp_laudus) / usd).quantize(Decimal("0.01"))
    if implied > FX_IMPLAUSIBLE:
        return FXResult(implied=implied, bcch=bcch_rate, deviation_pct=None, state="fx-implausible")

    if bcch_rate is None or bcch_rate == 0:
        return FXResult(implied=implied, bcch=None, deviation_pct=None, state="fx-bcch-missing")

    deviation = (abs(implied - bcch_rate) / bcch_rate * Decimal("100")).quantize(Decimal("0.01"))
    state = "fx-out-of-tolerance" if deviation > TOLERANCE_PCT else None
    return FXResult(implied=implied, bcch=bcch_rate, deviation_pct=deviation, state=state)
