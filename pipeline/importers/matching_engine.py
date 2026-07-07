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
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

DATE_TOLERANCE_DAYS = 3
# El atajo del ranking (ganador siempre en el subset amount-match) exige que el peor
# score con monto (100 − DATE_TOLERANCE_DAYS) supere al mejor sin monto (sim máx 1×10).
# Si alguna vez se agranda la tolerancia hacia ≥90, hay que volver al score global.
assert 100 - DATE_TOLERANCE_DAYS > 10

# Stems de archivos mensuales del importer (ASCII: un dígito unicode no debe colarse
# al filtro y saltarse el fallback conservador).
_MONTH_STEM = re.compile(r"[0-9]{4}-[0-9]{2}")
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
    currency: str = "CLP"        # moneda de la posting (para mostrarla bien en el dashboard, 6.4 AC7)


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
    # Los archivos se llaman YYYY-MM.beancount: filtrar por nombre ANTES de parsear
    # (parsear los ~68 meses para quedarse con 1-2 era el grueso del costo de cada
    # reconciliación). Comparación de strings funciona por el formato ISO, incluso
    # cruzando año. Se apoya en que el writer bucketea cada JE en el archivo de SU mes
    # (`write_jes`/_month_of lo garantizan para todo lo generado); una tx movida a mano
    # al archivo de otro mes quedaría invisible. Stems que no calzan el patrón se
    # parsean igual (fallback conservador).
    month_lo = period_start.strftime("%Y-%m")
    month_hi = period_end.strftime("%Y-%m")
    for path in sorted(target_dir.glob("*.beancount")):
        if path.name.startswith("_"):
            continue
        if _MONTH_STEM.fullmatch(path.stem) and not (month_lo <= path.stem <= month_hi):
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
                currency=mine[0].units.currency or "CLP",
            ))
    return out


def _norm(s: str) -> str:
    return (s or "").lower().strip()


def _classify(cl: CartolaLine, le: LaudusEntry, fx_era: bool, sim: float) -> tuple[str, float, str]:
    """Estado del par (cl, le) ya elegido como mejor candidato aceptable.

    `sim` viene precomputada del matching (una sola corrida de SequenceMatcher por par)."""
    is_usd = fx_era and cl.currency != "CLP"
    amount_match = True if is_usd else (cl.amount == le.amount)
    date_match = cl.date == le.date
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


def match(
    cartola_lines: list[CartolaLine],
    laudus_entries: list[LaudusEntry],
    *,
    period_start: date,
) -> list[MatchResult]:
    """Un MatchResult por cada línea de cartola + los Laudus sobrantes (missing-in-cartola).

    Matching greedy: para cada línea de cartola se elige el mejor Laudus aceptable dentro de
    ±3 días (sin reusar un asiento Laudus ya consumido). Aceptable = monto exacto (CLP) o
    descripción ≥ umbral; score = (100 si monto) + sim×10 − |Δdías|. `period_start >=
    2026-01-01` habilita la era FX (USD); antes es CLP-only (AC9).

    Performance (review 2026-07-06 D3), sin cambiar resultados: descripciones normalizadas
    una vez, similitud computada ≤1 vez por par (cache por línea), y si hay candidatos con
    monto exacto la similitud de los demás ni se computa — el peor amount-match puntúa
    100 − DATE_TOLERANCE_DAYS y el mejor no-match ≤10 (garantizado por el assert del
    módulo), así que el ganador siempre está en el subset de monto y el orden de
    desempate (primero-en-orden entre iguales) se preserva.
    """
    fx_era = period_start >= USD_FX_EPOCH
    used: set[int] = set()
    results: list[MatchResult] = []
    le_norms = [_norm(le.description) for le in laudus_entries]

    for cl in cartola_lines:
        cl_norm = _norm(cl.description)
        is_usd = fx_era and cl.currency != "CLP"
        sims: dict[int, float] = {}

        def _sim(i: int) -> float:
            if i not in sims:
                sims[i] = difflib.SequenceMatcher(None, cl_norm, le_norms[i]).ratio()
            return sims[i]

        window = [(i, le) for i, le in enumerate(laudus_entries)
                  if i not in used and abs((cl.date - le.date).days) <= DATE_TOLERANCE_DAYS]
        amount_ok = [(i, le) for i, le in window
                     if (True if is_usd else cl.amount == le.amount)]
        candidates = amount_ok or [(i, le) for i, le in window
                                   if _sim(i) >= DESC_SIMILARITY_THRESHOLD]
        if not candidates:
            results.append(MatchResult("missing-in-laudus", cl, None, 0.0,
                                       "sin candidato Laudus aceptable en ±3 días"))
            continue
        # `candidates` es o TODO amount-match o TODO desc-match; el bono se aplica igual
        # que en el score original (100 + sim×10 − |Δdías|) para que la aritmética float
        # sea BIT-idéntica a la previa (omitir el +100 podía distinguir scores que antes
        # empataban por absorción de bits y cambiar el desempate primero-gana).
        bonus = 100 if candidates is amount_ok else 0
        best_idx, best_le = max(
            candidates,
            key=lambda c: bonus + _sim(c[0]) * 10 - abs((cl.date - c[1].date).days))
        used.add(best_idx)
        state, conf, notes = _classify(cl, best_le, fx_era, _sim(best_idx))
        results.append(MatchResult(state, cl, best_le, conf, notes))

    for i, le in enumerate(laudus_entries):
        if i not in used:
            results.append(MatchResult("missing-in-cartola", None, le, 0.0,
                                       "asiento Laudus sin línea de cartola correspondiente"))

    return results
