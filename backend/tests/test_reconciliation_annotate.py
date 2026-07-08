"""Story 6.3 (modelo A) — aprobar una diferencia `missing-in-laudus` la ANOTA en Beancount.

`resolve(confirm-cartola-only)` sobre un `missing-in-laudus` renderiza la tx de la cartola y la
escribe a `manual/` (bean-check real + git no-op en tests). Atomicidad: si bean-check falla, la
discrepancia queda abierta. Las demás acciones cierran sin escribir (comportamiento de 9.12).
"""
import json

import pytest

from backend.app.api.v1.reconciliation.service import (
    AnnotationFailed,
    ResolveError,
    read_discrepancies,
    resolve,
)
from pipeline.importers.bank_account_resolver import BankAccountResolver
from pipeline.importers.cartola_pdf_importer import CartolaPdfImporter
from pipeline.importers.discrepancy_writer import append_discrepancy, build_discrepancy

CC_ID = "11111111-1111-1111-1111-111111111111"
ACCOUNT = "Assets:EAG:Bancos:CtaCorriente-100200"

ACCOUNTS = """\
2020-12-31 open Assets:EAG:Bancos:CtaCorriente-100200 CLP, USD
  bank_account_id: "11111111-1111-1111-1111-111111111111"
  bank_account_type: "cta_corriente"
  bank_account_currency: "CLP"
  bank_account_last4: "0200"
  bank_name: "Banco BCI"
2020-12-31 open Expenses:EAG:Suspense CLP, USD
2020-12-31 open Expenses:EAG:Super CLP
"""

_TS = "2026-04-01T00:00:00Z"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("IMPORTER_GIT_ENABLED", raising=False)
    monkeypatch.delenv("LEDGER_DISCREPANCIES", raising=False)


def _root(tmp_path):
    (tmp_path / "manual").mkdir(parents=True, exist_ok=True)
    (tmp_path / "accounts.beancount").write_text(ACCOUNTS, encoding="utf-8")
    (tmp_path / "main.beancount").write_text(
        'include "accounts.beancount"\ninclude "manual/*.beancount"\n', encoding="utf-8")
    return tmp_path


def _importer(root):
    return CartolaPdfImporter(BankAccountResolver(root / "accounts.beancount"))


def _jsonl(root):
    return root / "_meta" / "cartola-discrepancies.jsonl"


def _seed(root, *, state, cartola, laudus=None, fx=None, source="cartola"):
    """Siembra una discrepancia original y devuelve su id."""
    d = build_discrepancy(batch_id="b1", bank_account_id=CC_ID, state=state, ts=_TS,
                          cartola=cartola, laudus=laudus, fx=fx, source=source)
    append_discrepancy(d, _jsonl(root))
    return d["discrepancy_id"]


def _missing_in_laudus(root, *, amount=-45000.0, currency="CLP", fx=None):
    return _seed(root, state="missing-in-laudus", fx=fx, cartola={
        "line_no": 3, "date": "2026-03-15", "amount": amount,
        "currency": currency, "description": "GASTO REAL SIN LAUDUS"})


def _manual_files(root):
    return list((root / "manual").glob("*.beancount"))


def _resolution_lines(root):
    p = _jsonl(root)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip() and json.loads(l).get("ref_discrepancy_id")]


# ── AC1: confirm-cartola-only sobre missing-in-laudus → tx en manual/, cierra ──


def test_confirm_cartola_only_anota_y_cierra(tmp_path):
    root = _root(tmp_path)
    did = _missing_in_laudus(root)
    out = resolve(did, "confirm-cartola-only", "gasto real verificado vs banco",
                  user_email="c@test.com", now_iso=_TS, path=_jsonl(root),
                  ledger_root=root, importer=_importer(root), category_account="Expenses:EAG:Super")
    assert out["status"] == "resolved"
    # tx escrita a manual/ con la categoría elegida + metadata de traza
    files = _manual_files(root)
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "Expenses:EAG:Super" in content and ACCOUNT in content
    assert f'ref_discrepancy_id: "{did}"' in content
    assert 'category_status: "confirmed"' in content
    # discrepancia cerrada (ya no aparece en el dashboard) + 1 línea de resolución
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 0
    assert len(_resolution_lines(root)) == 1


# ── Story 6.7 (review): dedup del path single — no re-escribe una tx ya anotada ──


def test_single_dedup_no_reescribe_tx_ya_anotada(tmp_path):
    """Ventana crash: el batch commiteó la tx pero no cerró la discrepancia; cerrarla luego por el
    path single NO debe re-escribir la tx (doble-conteo). `annotate_discrepancy` dedup por ref."""
    from pipeline.importers.reconcile import annotate_discrepancy

    root = _root(tmp_path)
    did = _missing_in_laudus(root)
    disc = read_discrepancies(path=_jsonl(root), discrepancy_id=did)["discrepancies"][0]
    imp = _importer(root)
    r1 = annotate_discrepancy(disc, category_account="Expenses:EAG:Super",
                              importer=imp, ledger_root=root, ts=_TS)
    assert r1["success"]
    content1 = _manual_files(root)[0].read_text(encoding="utf-8")
    # segunda anotación del MISMO id (la tx ya está en el archivo) → no duplica
    r2 = annotate_discrepancy(disc, category_account="Expenses:EAG:Super",
                              importer=imp, ledger_root=root, ts=_TS)
    assert r2["success"]
    content2 = _manual_files(root)[0].read_text(encoding="utf-8")
    assert content1 == content2                                  # no re-escribió (dedup)
    assert content2.count(f'ref_discrepancy_id: "{did}"') == 1


# ── AC2: bean-check rojo → 422, discrepancia sigue abierta, sin resolución ─────


def test_atomicidad_bean_check_rojo_no_cierra(tmp_path):
    root = _root(tmp_path)
    did = _missing_in_laudus(root)
    # categoría a una cuenta NO declarada → bean-check falla → annotate falla
    with pytest.raises(AnnotationFailed):
        resolve(did, "confirm-cartola-only", "gasto real verificado vs banco",
                user_email="c@test.com", now_iso=_TS, path=_jsonl(root),
                ledger_root=root, importer=_importer(root),
                category_account="Expenses:EAG:NoExiste")
    # rollback: nada en manual/, discrepancia sigue abierta, sin línea de resolución
    assert _manual_files(root) == []
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 1
    assert _resolution_lines(root) == []


# ── AC3: confirm-laudus-only (missing-in-cartola) → cierra sin escribir ────────


def test_confirm_laudus_only_cierra_sin_escribir(tmp_path):
    root = _root(tmp_path)
    did = _seed(root, state="missing-in-cartola", source="laudus", cartola=None,
                laudus={"journal_entry_id": "JE9", "date": "2026-03-20",
                        "amount": -12000.0, "description": "SOLO-LAUDUS"})
    out = resolve(did, "confirm-laudus-only", "Laudus ya lo tiene, se confirma",
                  user_email="c@test.com", now_iso=_TS, path=_jsonl(root),
                  ledger_root=root, importer=_importer(root))
    assert out["status"] == "resolved" and out["git_commit_sha"] is None
    assert _manual_files(root) == []                       # NO escribe al ledger
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 0


# ── AC3: escalate → no cierra, no escribe ─────────────────────────────────────


def test_escalate_no_cierra_ni_escribe(tmp_path):
    root = _root(tmp_path)
    did = _missing_in_laudus(root)
    out = resolve(did, "escalate", None, user_email="c@test.com", now_iso=_TS,
                  path=_jsonl(root), ledger_root=root, importer=_importer(root))
    assert out["status"] == "escalated"
    assert _manual_files(root) == []
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 1  # sigue abierta


# ── AC6: doble aprobación rechazada (guard antes de escribir) ──────────────────


def test_doble_aprobacion_rechazada(tmp_path):
    root = _root(tmp_path)
    did = _missing_in_laudus(root)
    resolve(did, "confirm-cartola-only", "gasto real verificado vs banco",
            user_email="c@test.com", now_iso=_TS, path=_jsonl(root),
            ledger_root=root, importer=_importer(root), category_account="Expenses:EAG:Super")
    with pytest.raises(ResolveError, match="ya fue resuelta"):
        resolve(did, "confirm-cartola-only", "gasto real verificado vs banco",
                user_email="c@test.com", now_iso=_TS, path=_jsonl(root),
                ledger_root=root, importer=_importer(root), category_account="Expenses:EAG:Super")
    assert len(_manual_files(root)) == 1                   # no se escribió dos veces


# ── Q2: sin categoría → Suspense + pending (lo levanta /categorizacion) ────────


def test_sin_categoria_va_a_suspense_pending(tmp_path):
    root = _root(tmp_path)
    did = _missing_in_laudus(root)
    out = resolve(did, "confirm-cartola-only", "gasto real, categorizo despues",
                  user_email="c@test.com", now_iso=_TS, path=_jsonl(root),
                  ledger_root=root, importer=_importer(root))  # sin category_account
    assert out["status"] == "resolved"
    content = _manual_files(root)[0].read_text(encoding="utf-8")
    assert "Expenses:EAG:Suspense" in content
    assert 'category_status: "pending"' in content


# ── Q4: USD missing-in-laudus → tx con postings USD (price per-unit) ───────────


def test_confirm_cartola_only_usd_anota(tmp_path):
    root = _root(tmp_path)
    did = _missing_in_laudus(root, amount=-42.75, currency="USD",
                             fx={"implied": 950.0, "bcch": 950.0, "deviation_pct": 0.0})
    out = resolve(did, "confirm-cartola-only", "compra exterior real, sin Laudus",
                  user_email="c@test.com", now_iso=_TS, path=_jsonl(root),
                  ledger_root=root, importer=_importer(root), category_account="Expenses:EAG:Super")
    assert out["status"] == "resolved"
    content = _manual_files(root)[0].read_text(encoding="utf-8")
    assert "USD" in content and "950" in content            # price per-unit en CLP
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 0


# ── USD sin FX (BCCh ausente) → no se puede anotar → 422, discrepancia abierta ─


def test_usd_sin_fx_no_anota(tmp_path):
    root = _root(tmp_path)
    did = _missing_in_laudus(root, amount=-42.75, currency="USD",
                             fx={"implied": None, "bcch": None, "deviation_pct": None})
    with pytest.raises(AnnotationFailed, match="FX"):
        resolve(did, "confirm-cartola-only", "compra exterior sin tasa BCCh",
                user_email="c@test.com", now_iso=_TS, path=_jsonl(root),
                ledger_root=root, importer=_importer(root), category_account="Expenses:EAG:Super")
    assert _manual_files(root) == []
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 1


# ── Code review 6.3 (fail-closed): datos que no se pueden anotar → 422, abierta ─


def test_bank_account_desconocido_no_anota(tmp_path):
    """P1: un bank_account_id que ya no está en accounts.beancount → AnnotationFailed (422), no 500."""
    root = _root(tmp_path)
    d = build_discrepancy(batch_id="b1", bank_account_id="00000000-0000-0000-0000-000000000000",
                          state="missing-in-laudus", ts=_TS, source="cartola", laudus=None, fx=None,
                          cartola={"line_no": 3, "date": "2026-03-15", "amount": -45000.0,
                                   "currency": "CLP", "description": "GASTO CUENTA RETIRADA"})
    append_discrepancy(d, _jsonl(root))
    with pytest.raises(AnnotationFailed):
        resolve(d["discrepancy_id"], "confirm-cartola-only", "gasto real verificado vs banco",
                user_email="c@test.com", now_iso=_TS, path=_jsonl(root),
                ledger_root=root, importer=_importer(root), category_account="Expenses:EAG:Super")
    assert _manual_files(root) == []
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 1


def test_usd_fx_no_positivo_no_anota(tmp_path):
    """P2: fx.implied == 0 (o negativo) NO pasa el guard → no escribe un asiento @0."""
    root = _root(tmp_path)
    did = _missing_in_laudus(root, amount=-42.75, currency="USD",
                             fx={"implied": 0.0, "bcch": 0.0, "deviation_pct": None})
    with pytest.raises(AnnotationFailed, match="FX"):
        resolve(did, "confirm-cartola-only", "compra exterior con FX cero",
                user_email="c@test.com", now_iso=_TS, path=_jsonl(root),
                ledger_root=root, importer=_importer(root), category_account="Expenses:EAG:Super")
    assert _manual_files(root) == []
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 1


def test_moneda_no_soportada_no_anota(tmp_path):
    """P3: una moneda ≠ CLP/USD (EUR) no se rutea a build_usd_postings (hardcodea USD)."""
    root = _root(tmp_path)
    did = _missing_in_laudus(root, amount=-42.75, currency="EUR",
                             fx={"implied": 950.0, "bcch": 950.0, "deviation_pct": 0.0})
    with pytest.raises(AnnotationFailed, match="no soportada"):
        resolve(did, "confirm-cartola-only", "compra en euros, sin Laudus",
                user_email="c@test.com", now_iso=_TS, path=_jsonl(root),
                ledger_root=root, importer=_importer(root), category_account="Expenses:EAG:Super")
    assert _manual_files(root) == []
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 1
