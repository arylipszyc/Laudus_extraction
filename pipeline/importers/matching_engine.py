"""Motor de reconciliación cartola ↔ Laudus — Story 9.6b AC1/AC9.

Cruza cada línea de cartola contra los asientos Laudus del período (mismo bank account)
y clasifica en uno de 7 estados de matching. La semántica FX (USD) + JSONL de discrepancias
+ comportamiento por estado viven en `fx_calculator.py` / `discrepancy_writer.py` /
`reconcile.py` (esta clase solo decide el estado de cada par).

Tolerancias (Dev Notes Q4): fecha ±3 días, similitud de descripción ≥ 0.85, monto exacto
para CLP. Para USD no se compara monto (moneda distinta a la del asiento CLP de Laudus) →
el match se decide por fecha + descripción y la FX se deriva después.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

DATE_TOLERANCE_DAYS = 3
DESC_SIMILARITY_THRESHOLD = 0.85
USD_FX_EPOCH = date(2026, 1, 1)  # AC9: pre-2026 es CLP-only, sin lógica FX

STATES = frozenset({
    "perfect", "value-mismatch", "missing-in-laudus", "missing-in-cartola",
    "date-mismatch", "description-mismatch", "category-mismatch",
})


@dataclass
class CartolaLine:
    """Línea de cartola normalizada para matching (subset de CartolaTransaction)."""
    line_no: int
    date: date
    amount: Decimal       # firmado; en la moneda de `currency`
    currency: str         # CLP | USD | EUR
    description: str
    suggested_category: str = ""   # cuenta de categoría sugerida (category_predictor)


@dataclass
class LaudusEntry:
    """Asiento Laudus normalizado: la posting al account del banco + su contrapartida."""
    je_id: str
    date: date
    amount: Decimal       # firmado, CLP, sobre el account del banco/TC
    description: str
    category_account: str = ""   # cuenta de contrapartida (gasto/ingreso), para category-mismatch


@dataclass
class MatchResult:
    state: str
    cartola_line: CartolaLine | None
    laudus_entry: LaudusEntry | None
    confidence: float
    notes: str = ""


def load_laudus_entries(target_dir, account: str, period_start: date, period_end: date) -> list[LaudusEntry]:
    """Asientos Laudus del período que tocan `account` — desde imports/laudus/*.beancount.

    Por cada Transaction con una posting al `account` dentro de [period_start, period_end],
    emite un LaudusEntry (monto = esa posting; category_account = la contrapartida más grande).
    Es la entrada de `match()` para el flujo real (el importer 9.4 ya escribió esos archivos).
    """
    from pathlib import Path

    from beancount.core.data import Transaction
    from beancount.parser import parser

    out: list[LaudusEntry] = []
    target_dir = Path(target_dir)
    if not target_dir.is_dir():
        return out
    for path in sorted(target_dir.glob("*.beancount")):
        if path.name.startswith("_"):
            continue
        entries, _err, _opt = parser.parse_file(str(path))
        for e in entries:
            if not isinstance(e, Transaction) or not (period_start <= e.date <= period_end):
                continue
            mine = [p for p in e.postings if p.account == account and p.units is not None]
            if not mine:
                continue
            others = [p for p in e.postings if p.account != account and p.units is not None]
            category = max(others, key=lambda p: abs(p.units.number)).account if others else ""
            out.append(LaudusEntry(
                je_id=str((e.meta or {}).get("id", "")),
                date=e.date,
                amount=mine[0].units.number,
                description=e.narration or "",
                category_account=category,
            ))
    return out


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, (a or "").lower().strip(), (b or "").lower().strip()).ratio()


def _classify(cl: CartolaLine, le: LaudusEntry, fx_era: bool) -> tuple[str, float, str]:
    """Estado del par (cl, le) ya elegido como mejor candidato aceptable."""
    is_usd = fx_era and cl.currency != "CLP"
    amount_match = True if is_usd else (cl.amount == le.amount)
    date_match = cl.date == le.date
    sim = _similarity(cl.description, le.description)
    desc_match = sim >= DESC_SIMILARITY_THRESHOLD

    if not amount_match:
        return "value-mismatch", 1.0, f"monto cartola={cl.amount} vs laudus={le.amount}"
    if not date_match:
        return "date-mismatch", sim, f"fecha cartola={cl.date} vs laudus={le.date}"
    if not desc_match:
        return "description-mismatch", sim, f"desc sim={sim:.2f} < {DESC_SIMILARITY_THRESHOLD}"
    if cl.suggested_category and le.category_account and cl.suggested_category != le.category_account:
        return "category-mismatch", sim, f"cat cartola={cl.suggested_category} vs laudus={le.category_account}"
    return "perfect", 1.0, ""


def _acceptable(cl: CartolaLine, le: LaudusEntry, fx_era: bool) -> bool:
    """Un candidato (dentro de ±3 días) es 'el mismo movimiento' si coincide el monto
    (CLP) o la descripción es suficientemente parecida — si no, es otro movimiento."""
    is_usd = fx_era and cl.currency != "CLP"
    amount_match = True if is_usd else (cl.amount == le.amount)
    desc_match = _similarity(cl.description, le.description) >= DESC_SIMILARITY_THRESHOLD
    return amount_match or desc_match


def _score(cl: CartolaLine, le: LaudusEntry, fx_era: bool) -> float:
    is_usd = fx_era and cl.currency != "CLP"
    amount_match = True if is_usd else (cl.amount == le.amount)
    sim = _similarity(cl.description, le.description)
    dd = abs((cl.date - le.date).days)
    return (100 if amount_match else 0) + sim * 10 - dd


def match(
    cartola_lines: list[CartolaLine],
    laudus_entries: list[LaudusEntry],
    *,
    period_start: date,
) -> list[MatchResult]:
    """Un MatchResult por cada línea de cartola + los Laudus sobrantes (missing-in-cartola).

    Matching greedy: para cada línea de cartola se elige el mejor Laudus aceptable dentro de
    ±3 días (sin reusar un asiento Laudus ya consumido). `period_start >= 2026-01-01` habilita
    la era FX (USD); antes es CLP-only (AC9).
    """
    fx_era = period_start >= USD_FX_EPOCH
    used: set[int] = set()
    results: list[MatchResult] = []

    for cl in cartola_lines:
        candidates = [
            (i, le) for i, le in enumerate(laudus_entries)
            if i not in used
            and abs((cl.date - le.date).days) <= DATE_TOLERANCE_DAYS
            and _acceptable(cl, le, fx_era)
        ]
        if not candidates:
            results.append(MatchResult("missing-in-laudus", cl, None, 0.0,
                                       "sin candidato Laudus aceptable en ±3 días"))
            continue
        best_idx, best_le = max(candidates, key=lambda c: _score(cl, c[1], fx_era))
        used.add(best_idx)
        state, conf, notes = _classify(cl, best_le, fx_era)
        results.append(MatchResult(state, cl, best_le, conf, notes))

    for i, le in enumerate(laudus_entries):
        if i not in used:
            results.append(MatchResult("missing-in-cartola", None, le, 0.0,
                                       "asiento Laudus sin línea de cartola correspondiente"))

    return results
