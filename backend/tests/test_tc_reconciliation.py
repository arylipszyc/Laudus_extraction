"""Story 6.6 — vista de cuadre TC (`GET /tc/reconciliation`).

`build_rows` enumera las cartolas TC importadas de una tarjeta (por bank_account_id) y computa C1–C5
por período. El endpoint resuelve la cuenta desde accounts.beancount y aplica RBAC contador/admin.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.tc_reconciliation.service import build_rows
from backend.app.auth.service import create_jwt
from backend.app.dependencies import get_ledger_service
from backend.app.middleware import add_middleware
from beancount.parser import parser

REAL = "Liabilities:EAG:TC:Real:TestCard"
LUMP = "Expenses:EAG:TC:TestCard-430005"
CARD = "BCI_1027"

# Dos cartolas contiguas de la misma tarjeta (mar 0→1000, abr 1000→1300).
LEDGER = """
2026-03-10 * "COMPRA MARZO"
  operation_type: "compra"
  source: "cartola-tc"
  period: "2026-03"
  bank_account_id: "BCI_1027"
  opening: "0"
  closing: "1000"
  currency: "CLP"
  Liabilities:EAG:TC:Real:TestCard   -1000.00 CLP
  Expenses:EAG:Suspense               1000.00 CLP

2026-04-05 * "COMPRA ABRIL"
  operation_type: "compra"
  source: "cartola-tc"
  period: "2026-04"
  bank_account_id: "BCI_1027"
  opening: "1000"
  closing: "1300"
  currency: "CLP"
  Liabilities:EAG:TC:Real:TestCard   -300.00 CLP
  Expenses:EAG:Suspense               300.00 CLP
"""

ACCOUNTS = """\
2020-12-31 open Expenses:EAG:TC:TestCard-430005 CLP
  bank_account_id: "BCI_1027"
  bank_account_type: "tarjeta_credito"
  bank_account_currency: "CLP"
  bank_name: "Banco BCI"
2020-12-31 open Liabilities:EAG:TC:Real:TestCard CLP
2020-12-31 open Expenses:EAG:Suspense CLP
"""


def _entries():
    entries, errors, _ = parser.parse_string(LEDGER)
    assert not errors, errors
    return entries


def test_build_rows_agrupa_por_periodo():
    rows = build_rows(_entries(), tc_real_account=REAL, lump_account=LUMP, bank_account_id=CARD)
    assert [r["year_month"] for r in rows] == ["2026-04", "2026-03"]  # mes descendente
    abril = rows[0]
    assert abril["c1_ok"] is True            # −1300 == −1300
    assert abril["c2_ok"] is True            # apertura 1000 == cierre marzo 1000
    assert abril["sum_compras"] == 300.0
    assert abril["card"] == CARD
    assert abril["tc_real_account"] == REAL
    assert len(abril["movements"]) == 1


def test_build_rows_year_month_filtra():
    rows = build_rows(_entries(), tc_real_account=REAL, lump_account=LUMP, bank_account_id=CARD,
                      year_month="2026-03")
    assert len(rows) == 1 and rows[0]["year_month"] == "2026-03"
    assert rows[0]["c2_ok"] is False         # marzo no tiene cartola anterior


class _FakeLedger:
    def __init__(self, main_path, entries):
        self._main_path = main_path
        self._entries = entries

    @property
    def main_path(self):
        return self._main_path

    def entries(self):
        return self._entries


def _app(ledger=None):
    from backend.app.api.v1.tc_reconciliation.router import router
    app = FastAPI()
    add_middleware(app)
    app.include_router(router, prefix="/api/v1")
    if ledger is not None:
        app.dependency_overrides[get_ledger_service] = lambda: ledger
    return app


def test_endpoint_rbac_family_403():
    client = TestClient(_app(), raise_server_exceptions=False)
    resp = client.get("/api/v1/tc/reconciliation?card=BCI_1027",
                      cookies={"access_token": create_jwt(email="f@test.com", role="family")})
    assert resp.status_code == 403


def test_endpoint_ok(tmp_path):
    (tmp_path / "accounts.beancount").write_text(ACCOUNTS, encoding="utf-8")
    ledger = _FakeLedger(str(tmp_path / "main.beancount"), _entries())
    client = TestClient(_app(ledger), raise_server_exceptions=False)
    resp = client.get("/api/v1/tc/reconciliation?card=BCI_1027",
                      cookies={"access_token": create_jwt(email="c@test.com", role="contador")})
    assert resp.status_code == 200
    body = resp.json()
    assert [r["year_month"] for r in body] == ["2026-04", "2026-03"]
    assert body[0]["c1_ok"] is True


def test_endpoint_unknown_card_404(tmp_path):
    (tmp_path / "accounts.beancount").write_text(ACCOUNTS, encoding="utf-8")
    ledger = _FakeLedger(str(tmp_path / "main.beancount"), _entries())
    client = TestClient(_app(ledger), raise_server_exceptions=False)
    resp = client.get("/api/v1/tc/reconciliation?card=NOPE",
                      cookies={"access_token": create_jwt(email="c@test.com", role="contador")})
    assert resp.status_code == 404
