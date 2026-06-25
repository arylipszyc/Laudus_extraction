"""Story 6.5 — cierre de período de reconciliación (FR35).

`reconcile_cartola` deja un run-record por (cuenta, mes) en `_meta/reconciliation-runs.jsonl`
(incluso con cartola perfecta = 0 diferencias). `list_periods` cruza el último run-record con las
discrepancias abiertas (vía `read_discrepancies`, keyed por el `year_month` persistido de 6.5b) →
`complete` (0 abiertas) / `pending` (>0).
"""
import json

import pytest

from backend.app.api.v1.reconciliation.service import list_periods
from pipeline.importers.bank_account_resolver import BankAccountResolver
from pipeline.importers.cartola_pdf_importer import CartolaPdfImporter
from pipeline.importers.discrepancy_writer import append_resolution, append_run, build_run
from pipeline.importers.reconcile import reconcile_cartola

CC_ID = "11111111-1111-1111-1111-111111111111"
ACCOUNT = "Assets:EAG:Bancos:CtaCorriente-100200"

ACCOUNTS = """\
2020-12-31 open Assets:EAG:Bancos:CtaCorriente-100200 CLP
  bank_account_id: "11111111-1111-1111-1111-111111111111"
  bank_account_type: "cta_corriente"
  bank_account_currency: "CLP"
  bank_account_last4: "0200"
  bank_name: "Banco BCI"
2020-12-31 open Expenses:EAG:Suspense CLP, USD
2020-12-31 open Expenses:EAG:Super CLP
2020-12-31 open Equity:Reconciliation:Discrepancias CLP, USD
"""


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("IMPORTER_GIT_ENABLED", raising=False)
    monkeypatch.delenv("LEDGER_DISCREPANCIES", raising=False)
    monkeypatch.delenv("LEDGER_RECONCILIATION_RUNS", raising=False)
    monkeypatch.delenv("LEDGER_DIR", raising=False)


def _root(tmp_path):
    (tmp_path / "imports" / "cartolas" / "_staging").mkdir(parents=True, exist_ok=True)
    (tmp_path / "imports" / "laudus").mkdir(parents=True, exist_ok=True)
    (tmp_path / "accounts.beancount").write_text(ACCOUNTS, encoding="utf-8")
    return tmp_path


def _laudus(root, entries_text):
    (root / "imports" / "laudus" / "2026-03.beancount").write_text(entries_text, encoding="utf-8")


def _staging(root, txs, batch_id="b1", opening="0", closing=None):
    if closing is None:
        closing = str(int(opening) + sum(a for _, _, a in txs))
    payload = {
        "schema_version": "1.0",
        "source": {"bank_account_id": CC_ID, "bank_name": "Banco BCI", "account_label": "CC",
                   "account_type": "cta_corriente", "entity": "EAG"},
        "period": {"start": "2026-03-01", "end": "2026-03-31"},
        "currency": "CLP",
        "balances": {"opening": opening, "closing": closing},
        "transactions": [{"line_no": i + 1, "date": d, "description": desc, "amount": str(a),
                          "currency": "CLP", "raw": {}} for i, (d, desc, a) in enumerate(txs)],
        "extraction": {"model": "test", "extracted_at": "2026-04-01T10:00:00Z", "warnings": []},
    }
    (root / "imports" / "cartolas" / "_staging" / f"{batch_id}.cartola.json").write_text(
        json.dumps(payload), encoding="utf-8")


def _importer(root):
    return CartolaPdfImporter(BankAccountResolver(root / "accounts.beancount"))


def _laudus_jumbo():
    return f'2026-03-15 * "JUMBO"\n  {ACCOUNT}  -45000 CLP\n  Expenses:EAG:Super  45000 CLP\n'


def _disc_path(root):
    return root / "_meta" / "cartola-discrepancies.jsonl"


def _runs_file(root):
    return root / "_meta" / "reconciliation-runs.jsonl"


def _runs_lines(root):
    p = _runs_file(root)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _disc_lines(root):
    p = _disc_path(root)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _periods(root):
    return list_periods(path=_disc_path(root), runs_path=_runs_file(root))


# ── append_run / build_run (AC1) ──────────────────────────────────────────────


def test_append_run_escribe(tmp_path):
    rp = tmp_path / "_meta" / "reconciliation-runs.jsonl"
    append_run(build_run(bank_account_id="b", year_month="2026-03", reconciled_at="t",
                         matched=1, differences=0, blocking=0, batch_id="b1"), rp)
    lines = [json.loads(line) for line in rp.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0]["schema_version"] == "1.0"
    assert lines[0]["bank_account_id"] == "b" and lines[0]["differences"] == 0


# ── AC1/AC2: cartola perfecta (0 diferencias) igual deja run-record ───────────


def test_reconcile_perfecto_deja_run_record(tmp_path):
    root = _root(tmp_path)
    _laudus(root, _laudus_jumbo())
    _staging(root, [("2026-03-15", "JUMBO", -45000)])
    reconcile_cartola("b1", _importer(root), root, ts="2026-04-01T00:00:00Z")
    assert _disc_lines(root) == []          # perfecto → 0 diferencias en el JSONL
    runs = _runs_lines(root)
    assert len(runs) == 1                    # …pero SÍ run-record (clave de 6.5)
    assert runs[0]["year_month"] == "2026-03"
    assert runs[0]["bank_account_id"] == CC_ID
    assert runs[0]["differences"] == 0 and runs[0]["matched"] == 1


# ── AC3/AC5: complete (0 abiertas) y pending (>0 abiertas) ────────────────────


def test_list_periods_complete(tmp_path):
    root = _root(tmp_path)
    _laudus(root, _laudus_jumbo())
    _staging(root, [("2026-03-15", "JUMBO", -45000)])
    reconcile_cartola("b1", _importer(root), root, ts="2026-04-01T00:00:00Z")
    periods = _periods(root)
    assert len(periods) == 1
    assert periods[0]["status"] == "complete" and periods[0]["open"] == 0
    assert periods[0]["bank_account_id"] == CC_ID and periods[0]["year_month"] == "2026-03"


def test_list_periods_pending(tmp_path):
    root = _root(tmp_path)  # laudus vacío → la línea queda missing-in-laudus (abierta)
    _staging(root, [("2026-03-15", "TRANSFER DESCONOCIDA", -9999)])
    reconcile_cartola("b1", _importer(root), root, ts="2026-04-01T00:00:00Z")
    periods = _periods(root)
    assert len(periods) == 1
    assert periods[0]["status"] == "pending" and periods[0]["open"] == 1


# ── AC4: último run gana ──────────────────────────────────────────────────────


def test_ultimo_run_gana(tmp_path):
    root = _root(tmp_path)
    rp = _runs_file(root)
    append_run(build_run(bank_account_id="b", year_month="2026-03", reconciled_at="2026-04-01T00:00:00Z",
                         matched=1, differences=2, blocking=1, batch_id="b1"), rp)
    append_run(build_run(bank_account_id="b", year_month="2026-03", reconciled_at="2026-04-09T00:00:00Z",
                         matched=5, differences=0, blocking=0, batch_id="b2"), rp)
    periods = list_periods(path=_disc_path(root), runs_path=rp)
    assert len(periods) == 1                                 # un solo período (cuenta, mes)
    assert periods[0]["matched"] == 5 and periods[0]["differences"] == 0   # el más reciente
    assert periods[0]["reconciled_at"] == "2026-04-09T00:00:00Z"


# ── AC5: resolver la última diferencia pasa el período a complete ─────────────


def test_open_cae_a_cero_al_resolver(tmp_path):
    root = _root(tmp_path)
    _staging(root, [("2026-03-15", "TRANSFER DESCONOCIDA", -9999)])
    reconcile_cartola("b1", _importer(root), root, ts="2026-04-01T00:00:00Z")
    before = _periods(root)
    assert before[0]["status"] == "pending" and before[0]["open"] == 1
    # resolver la única discrepancia (audit trail, sin anotar al ledger) → open 0 sin tocar el run
    disc_id = _disc_lines(root)[0]["discrepancy_id"]
    append_resolution(disc_id, {"action": "confirm-cartola-only", "resolved_by": "c@test.com",
                                "resolved_at": "2026-04-02T00:00:00Z", "justification": "verificado"},
                      _disc_path(root))
    after = _periods(root)
    assert after[0]["status"] == "complete" and after[0]["open"] == 0
