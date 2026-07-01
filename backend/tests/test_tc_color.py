"""Goal B (§10.2) — recomendación con colores en la corrección TC.

Cubre dos cosas:
- el mapeo puro `color_for(confidence, match_source)` → green | yellow | red (3 colores, sin naranja);
- que el asiento (a) PRESERVA `match_source` + `confidence` + `color` en su metadata cuando
  `category_for` devuelve un `CategorizationResult` (deja de descartarse con `predict(...)[0]`).

Archivo separado de test_tc_correction.py a propósito (otra tarea lo edita en paralelo).
"""
from decimal import Decimal

from beancount.core import data

from backend.app.integrations.cartola_schema import CartolaCanonicalV1
from pipeline.importers.categorization.service import CategorizationResult
from pipeline.importers.tc_correction import (
    COLOR_GREEN,
    COLOR_RED,
    COLOR_YELLOW,
    build_tc_correction_entries,
    color_for,
)

TC_REAL = "Liabilities:EAG:TC:Real:VisaTest"
EXP_TC = "Expenses:EAG:TC:TcTest-430099"
CAT = "Expenses:EAG:Super"


def _model(txs, *, opening="0", closing=None, currency="CLP", start="2026-03-01", end="2026-03-31"):
    """txs = list of (date, desc, amount_int, operation_type)."""
    if closing is None:
        closing = str(int(opening) + sum(a for _, _, a, _ in txs))
    payload = {
        "schema_version": "1.0",
        "source": {"bank_account_id": "tc-test", "bank_name": "Banco Test",
                   "account_label": "Visa Test 1234", "account_type": "tarjeta_credito", "entity": "EAG"},
        "period": {"start": start, "end": end},
        "currency": currency,
        "balances": {"opening": opening, "closing": closing},
        "transactions": [
            {"line_no": i + 1, "date": d, "description": desc, "amount": str(a),
             "currency": currency, "raw": {"operation_type": op}}
            for i, (d, desc, a, op) in enumerate(txs)
        ],
        "extraction": {"model": "test", "extracted_at": "2026-04-01T00:00:00Z", "warnings": []},
    }
    return CartolaCanonicalV1.model_validate(payload)


def _build(model, category_for):
    return build_tc_correction_entries(
        model=model, tc_real_account=TC_REAL, expense_tc_account=EXP_TC, fx=Decimal(1),
        lump_for=lambda tx: abs(tx.amount), category_for=category_for,
        batch_id="b1", bank_account_id="tc-test", emit_opening=False,
    )


# ── color_for: mapeo puro (§10.2) ─────────────────────────────────────────────


def test_color_historical_30plus_es_verde():
    assert color_for(1.0, "historical-30+") == COLOR_GREEN


def test_color_smart_importer_alta_confianza_es_verde():
    # confianza alta (≥0.85, el bar del flag `*` del pipeline) aunque la fuente sea smart_importer → verde.
    assert color_for(0.95, "smart_importer") == COLOR_GREEN


def test_color_smart_importer_confianza_media_es_amarillo():
    # Veredicto D2 (Valentina 2026-06-30): 0.5-0.85 = el pipeline lo flaggea `!` → amarillo, NO verde.
    assert color_for(0.7, "smart_importer") == COLOR_YELLOW
    assert color_for(0.4, "smart_importer") == COLOR_YELLOW


def test_color_historical_pocas_confirmaciones_es_amarillo():
    # historical 1-29 → confidence = #conf/30; pocas confirmaciones cae en amarillo.
    assert color_for(5 / 30, "historical") == COLOR_YELLOW


def test_color_historical_muchas_confirmaciones_es_verde():
    # ≥26 confirmaciones (≥0.85, corte alineado al pipeline) → verde; se pone más verde con cada pasada.
    assert color_for(26 / 30, "historical") == COLOR_GREEN
    assert color_for(20 / 30, "historical") == COLOR_YELLOW   # 0.67 < 0.85 → amarillo (D2)


def test_color_pending_suspense_es_rojo():
    assert color_for(0.0, "pending") == COLOR_RED


def test_color_gemini_es_rojo():
    # adivinanza de Gemini → rojo aunque su confidence nominal sea 0.5.
    assert color_for(0.5, "gemini") == COLOR_RED


def test_color_confianza_nula_es_rojo():
    assert color_for(0.0, "historical") == COLOR_RED


def test_color_confidence_no_numerico_no_crashea():
    assert color_for(None, "smart_importer") == COLOR_RED


# ── preservación de metadata en el asiento (a) ────────────────────────────────


def _asiento_a(entries):
    """La tx de consumo (operation_type compra), no el pago/apertura."""
    return next(e for e in entries
                if isinstance(e, data.Transaction) and (e.meta or {}).get("operation_type") == "compra")


def test_asiento_a_preserva_match_source_confidence_color():
    m = _model([("2026-03-10", "JUMBO", 45000, "compra")])
    res = CategorizationResult(CAT, "historical-30+", 1.0, "*")
    e = _asiento_a(_build(m, category_for=lambda tx: res))
    assert e.meta["match_source"] == "historical-30+"
    assert e.meta["confidence"] == "1.0"
    assert e.meta["color"] == COLOR_GREEN
    # el contador confirma SIEMPRE: nunca auto-confirmado.
    assert e.meta["category_status"] == "suggested"


def test_asiento_a_pending_queda_rojo_y_pending():
    m = _model([("2026-03-10", "RARO", 1000, "compra")])
    res = CategorizationResult("Expenses:EAG:Suspense", "pending", 0.0, "!")
    e = _asiento_a(_build(m, category_for=lambda tx: res))
    assert e.meta["color"] == COLOR_RED
    assert e.meta["category_status"] == "pending"


def test_category_for_str_no_emite_meta_de_color():
    # compat: si `category_for` devuelve un str (no CategorizationResult), no se estampa color.
    m = _model([("2026-03-10", "JUMBO", 45000, "compra")])
    e = _asiento_a(_build(m, category_for=lambda tx: CAT))
    assert "color" not in e.meta
    assert "match_source" not in e.meta
