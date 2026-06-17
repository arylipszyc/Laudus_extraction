"""Tests de CategorizationHistory + CategorizationService — Story 9.7 AC1-AC6."""
import json
from decimal import Decimal

from pipeline.importers.categorization.history import (
    CategorizationHistory,
    append_correction,
    build_record,
)
from pipeline.importers.categorization.service import CategorizationService


def _history(tmp_path, records):
    p = tmp_path / "categorization-history.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return CategorizationHistory(p)


def _rec(desc_norm, cat):
    return {"description_normalized": desc_norm, "corrected_category": cat}


# ── CategorizationHistory ─────────────────────────────────────────────────────


def test_history_count_y_dominant(tmp_path):
    h = _history(tmp_path, [_rec("JUMBO", "Expenses:EAG:Super")] * 3
                 + [_rec("JUMBO", "Expenses:EAG:Otro")])
    assert h.count_for("JUMBO", "Expenses:EAG:Super") == 3
    assert h.dominant_category("JUMBO") == ("Expenses:EAG:Super", 3)
    assert h.dominant_category("DESCONOCIDO") == (None, 0)


def test_append_correction_y_build_record(tmp_path):
    p = tmp_path / "categorization-history.jsonl"
    rec = build_record(description="Supermercado Jumbo 123456", corrected_category="Expenses:EAG:Super",
                       original_suggestion="Expenses:EAG:Otro", user="c@test.com", ts="2026-05-01T00:00:00Z")
    assert rec["description_normalized"] == "SUPERMERCADO JUMBO"  # normalizada
    append_correction(p, rec)
    h = CategorizationHistory(p)
    assert h.count_for("SUPERMERCADO JUMBO", "Expenses:EAG:Super") == 1


# ── CategorizationService: los 5 stages ───────────────────────────────────────


class _FakeSmart:
    def __init__(self, result): self._r = result
    def predict(self, description, amount, bank_account_id): return self._r


class _FakeGemini:
    def __init__(self, result): self._r = result
    def suggest_category(self, description, amount, allowed): return self._r


def test_stage1_supra_gana_siempre(tmp_path):
    # ≥30 correcciones → supra, aunque smart_importer diga otra cosa con alta confianza
    h = _history(tmp_path, [_rec("JUMBO", "Expenses:EAG:Super")] * 30)
    svc = CategorizationService(h, smart_importer=_FakeSmart(("Expenses:EAG:Otro", 0.99)))
    r = svc.categorize("JUMBO", Decimal("-1000"), "acc")
    assert (r.match_source, r.flag, r.confidence) == ("historical-30+", "*", 1.0)
    assert r.category_account == "Expenses:EAG:Super"


def test_stage2_smart_alta_confianza(tmp_path):
    h = _history(tmp_path, [])
    svc = CategorizationService(h, smart_importer=_FakeSmart(("Expenses:EAG:Super", 0.90)))
    r = svc.categorize("JUMBO", Decimal("-1000"), "acc")
    assert r.match_source == "smart_importer" and r.flag == "*"


def test_stage2_smart_baja_confianza_flag_review(tmp_path):
    h = _history(tmp_path, [])
    svc = CategorizationService(h, smart_importer=_FakeSmart(("Expenses:EAG:Super", 0.60)))
    r = svc.categorize("JUMBO", Decimal("-1000"), "acc")
    assert r.match_source == "smart_importer" and r.flag == "!"


def test_stage3_historical_1_29(tmp_path):
    h = _history(tmp_path, [_rec("JUMBO", "Expenses:EAG:Super")] * 5)
    svc = CategorizationService(h)  # sin smart_importer
    r = svc.categorize("JUMBO", Decimal("-1000"), "acc")
    assert r.match_source == "historical" and r.flag == "!"
    assert abs(r.confidence - 5 / 30) < 1e-9


def test_stage4_gemini_fallback(tmp_path):
    h = _history(tmp_path, [])
    svc = CategorizationService(
        h, gemini=_FakeGemini("Expenses:EAG:Super"), expense_accounts=["Expenses:EAG:Super"])
    r = svc.categorize("ALGO NUEVO", Decimal("-1000"), "acc")
    assert r.match_source == "gemini" and r.flag == "!" and r.confidence == 0.5


def test_stage4_gemini_fuera_de_lista_cae_a_suspense(tmp_path):
    h = _history(tmp_path, [])
    svc = CategorizationService(
        h, gemini=_FakeGemini("texto libre invalido"), expense_accounts=["Expenses:EAG:Super"])
    r = svc.categorize("ALGO", Decimal("-1000"), "acc")
    assert r.match_source == "pending"


def test_stage5_suspense(tmp_path):
    svc = CategorizationService(_history(tmp_path, []))
    r = svc.categorize("DESCONOCIDO", Decimal("-1000"), "acc")
    assert (r.category_account, r.match_source, r.flag, r.confidence) == \
        ("Expenses:EAG:Suspense", "pending", "!", 0.0)


def test_predict_adapter_9_6a_devuelve_tripla(tmp_path):
    svc = CategorizationService(_history(tmp_path, []))
    assert svc.predict("X", Decimal("-1"), "acc") == ("Expenses:EAG:Suspense", "pending", "!")


def test_cache_y_invalidate(tmp_path):
    h = _history(tmp_path, [])
    svc = CategorizationService(h, smart_importer=_FakeSmart(("Expenses:EAG:A", 0.9)))
    assert svc.categorize("X", Decimal("-1"), "acc").category_account == "Expenses:EAG:A"
    svc._smart = _FakeSmart(("Expenses:EAG:B", 0.9))  # cambia el motor
    assert svc.categorize("X", Decimal("-1"), "acc").category_account == "Expenses:EAG:A"  # cacheado
    svc.invalidate("X")
    assert svc.categorize("X", Decimal("-1"), "acc").category_account == "Expenses:EAG:B"
