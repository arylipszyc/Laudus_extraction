"""Tests de la estrategia de ancla de 3 capas — Story 7.0 (AC2, AC3, AC4, AC5).

El corazón del spike: `anchor_key` sobrevive un re-import (cambia `tx_id`, no `anchor_key`);
`resolve_anchor` re-ancla en caliente; una tx borrada degrada a `orphaned` sin perder el hilo.
"""
import pytest
from beancount.core import data
from beancount.parser import parser

from pipeline.importers import owner_comments_writer as ocw

# Dos "renders" del MISMO mes con la MISMA transacción de interés ("COMPRA X"), pero con un
# movimiento previo distinto → beancount le asigna otro `lineno` a "COMPRA X" en el re-import.
# filename también cambia (mismo slug re-generado). Los DATOS contables de "COMPRA X" (fecha,
# monto, cuenta, glosa) son idénticos → `anchor_key` idéntica, `tx_id` distinto.
RENDER_1 = """
2026-04-05 * "COMPRA X"
  Liabilities:EAG:TC:Real:TestCard   -300.00 CLP
  Expenses:EAG:Suspense               300.00 CLP
"""

RENDER_2_REIMPORT = """
2026-04-02 * "COMPRA PREVIA NUEVA"
  Liabilities:EAG:TC:Real:TestCard   -50.00 CLP
  Expenses:EAG:Suspense               50.00 CLP

2026-04-05 * "COMPRA X"
  Liabilities:EAG:TC:Real:TestCard   -300.00 CLP
  Expenses:EAG:Suspense               300.00 CLP
"""


def _parse(text, filename):
    entries, errors, _ = parser.parse_string(text)
    assert not errors, errors
    for e in entries:
        if isinstance(e, data.Transaction):
            e.meta["filename"] = filename  # simula el archivo de cartola (slug re-generado)
    return [e for e in entries if isinstance(e, data.Transaction)]


def _compra_x(entries):
    return next(e for e in entries if e.narration == "COMPRA X")


# ── AC2: compute_anchor_key ──────────────────────────────────────────────────


def test_anchor_key_normaliza_capitalizacion_acentos_espacios():
    a = ocw.compute_anchor_key("2026-04-05", "-300.00", "Liabilities:EAG:TC", "Café  con   Leche")
    b = ocw.compute_anchor_key("2026-04-05", "-300.00", "Liabilities:EAG:TC", "cafe con leche")
    assert a == b


def test_anchor_key_estable_ante_reimport():
    """Mismo (date, amount, account, narration) con distinto filename/lineno → distinto tx_id,
    MISMA anchor_key (AC2, el invariante que blinda el spike)."""
    e1 = _compra_x(_parse(RENDER_1, "cartola-2026-04.beancount"))
    e2 = _compra_x(_parse(RENDER_2_REIMPORT, "cartola-2026-04-v2.beancount"))
    assert ocw._tx_id_of(e1) != ocw._tx_id_of(e2)          # el tx_id cambió (re-import)
    assert ocw._anchor_key_of(e1) == ocw._anchor_key_of(e2)  # la anchor_key sobrevivió


def test_anchor_key_distinta_si_cambian_datos_contables():
    base = ocw.compute_anchor_key("2026-04-05", "-300.00", "Liabilities:EAG:TC", "COMPRA X")
    assert base != ocw.compute_anchor_key("2026-04-06", "-300.00", "Liabilities:EAG:TC", "COMPRA X")
    assert base != ocw.compute_anchor_key("2026-04-05", "-301.00", "Liabilities:EAG:TC", "COMPRA X")


# ── AC4/AC5: build_anchor + ledger_head_sha ──────────────────────────────────


def test_build_anchor_captura_snapshot_y_key(monkeypatch):
    monkeypatch.setattr(ocw, "ledger_head_sha", lambda root=None: "sha123")
    entries = _parse(RENDER_1, "cartola-2026-04.beancount")
    tx_id = ocw._tx_id_of(_compra_x(entries))
    anchor = ocw.build_anchor(tx_id, entries, ledger_root="/whatever")
    assert anchor["tx_id"] == tx_id
    assert anchor["anchor_key"] == ocw._anchor_key_of(_compra_x(entries))
    assert anchor["ledger_git_sha"] == "sha123"
    snap = anchor["tx_snapshot"]
    assert snap == {"date": "2026-04-05", "amount": -300.0, "currency": "CLP",
                    "account": "Liabilities:EAG:TC:Real:TestCard", "narration": "COMPRA X"}


def test_build_anchor_tx_inexistente_error():
    entries = _parse(RENDER_1, "cartola-2026-04.beancount")
    with pytest.raises(ocw.AnchorNotFound):
        ocw.build_anchor("noexiste0000", entries, ledger_root=".")


def test_ledger_head_sha_sin_git_devuelve_none(tmp_path):
    """Dir que no es repo git → None, no crashea (AC5)."""
    assert ocw.ledger_head_sha(tmp_path) is None


# ── AC3: resolve_anchor de 3 capas ───────────────────────────────────────────


def _make_comment(entries, ledger_root="."):
    tx_id = ocw._tx_id_of(_compra_x(entries))
    anchor = ocw.build_anchor(tx_id, entries, ledger_root=ledger_root)
    return ocw.build_comment(anchor=anchor, author_email="a@x", author_role="family",
                             body="?", ts="t")


def test_resolve_capa1_por_tx_id(monkeypatch):
    monkeypatch.setattr(ocw, "ledger_head_sha", lambda root=None: None)
    entries = _parse(RENDER_1, "cartola-2026-04.beancount")
    comment = _make_comment(entries)
    r = ocw.resolve_anchor(comment, entries)  # mismos entries → tx_id vivo
    assert r["status"] == "resolved"
    assert r["entry"] is _compra_x(entries)


def test_resolve_capa2_reancla_tras_reimport(monkeypatch):
    """El tx_id viejo ya no resuelve pero la anchor_key sí → re-anchored con el NUEVO tx_id (AC3)."""
    monkeypatch.setattr(ocw, "ledger_head_sha", lambda root=None: None)
    v1 = _parse(RENDER_1, "cartola-2026-04.beancount")
    comment = _make_comment(v1)                       # comentario creado contra el render 1
    v2 = _parse(RENDER_2_REIMPORT, "cartola-2026-04-v2.beancount")  # re-import: tx_id cambió

    r = ocw.resolve_anchor(comment, v2)
    assert r["status"] == "re-anchored"
    assert r["entry"] is _compra_x(v2)
    assert r["tx_id"] == ocw._tx_id_of(_compra_x(v2))
    assert r["tx_id"] != comment["anchor"]["tx_id"]   # es un tx_id nuevo


def test_resolve_capa3_orphaned_si_tx_borrada(monkeypatch):
    """Ni tx_id ni anchor_key matchean (tx eliminada) → orphaned; el hilo sobrevive con su snapshot."""
    monkeypatch.setattr(ocw, "ledger_head_sha", lambda root=None: None)
    v1 = _parse(RENDER_1, "cartola-2026-04.beancount")
    comment = _make_comment(v1)
    otros = _parse('2026-04-09 * "OTRA COSA"\n  Assets:X 1 CLP\n  Assets:Y -1 CLP\n', "otro.beancount")

    r = ocw.resolve_anchor(comment, otros)
    assert r["status"] == "orphaned"
    assert r["entry"] is None
    # el snapshot congelado sigue disponible → nunca se muestra un hilo vacío
    assert comment["anchor"]["tx_snapshot"]["narration"] == "COMPRA X"


def test_resolve_capa3_orphaned_si_anchor_key_ambigua(monkeypatch):
    """Dos transacciones idénticas en date+amount+account+narration → anchor_key duplicada →
    orphaned conservador (no re-ancla al azar). Residual documentado en el ADR."""
    monkeypatch.setattr(ocw, "ledger_head_sha", lambda root=None: None)
    v1 = _parse(RENDER_1, "cartola-2026-04.beancount")
    comment = _make_comment(v1)
    # dos COMPRA X idénticas (con distinto filename → distinto tx_id, misma anchor_key)
    dupes = _parse(RENDER_1 + RENDER_1, "cartola-dupes.beancount")
    assert len([e for e in dupes if e.narration == "COMPRA X"]) == 2

    r = ocw.resolve_anchor(comment, dupes)
    assert r["status"] == "orphaned"
    assert r["entry"] is None
